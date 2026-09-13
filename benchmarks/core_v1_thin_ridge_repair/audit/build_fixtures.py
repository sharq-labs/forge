"""Build the compact regression fixtures for the V1 thin-ridge repair.

    python -X utf8 benchmarks/core_v1_thin_ridge_repair/audit/build_fixtures.py --k2 <scratch>/k2_grid.npz

Writes tests/inference/fixtures/grid_resolution/{k2_multi,k2_weak_c2,battery_p2,battery_p3}.npz and
PROVENANCE.json. Each fixture stores the tensor axes and the grid's log-likelihood (inadmissible nodes
as -inf) -- exactly what gaussian_grid_posterior computed -- so a test rebuilds the PosteriorGrid with
the frozen weight arithmetic, without re-running an 11,163-solve CSTR grid or a production battery grid.

K2: from benchmarks/core_gap_thin_ridge/audit/k2_grid.py (K2's own frozen builder); must reproduce
experiments/kinetics_k2/k2_report.md to 1e-9 before it is written. C2 predictions are stored for the
predictive-UQ regression. Battery: B3's committed grid rule through the production adapter.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import math
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "tests" / "inference" / "fixtures" / "grid_resolution"


def axes_of(points):
    axes = [np.unique(points[:, i]) for i in range(points.shape[1])]
    mesh = np.array(np.meshgrid(*axes, indexing="ij")).reshape(len(axes), -1).T
    if mesh.shape != points.shape or not np.array_equal(mesh, points):
        raise SystemExit("points are not the ij-ordered tensor product of their axes")
    return axes


def save(name, **arrays):
    buf = io.BytesIO()
    np.savez_compressed(buf, **arrays)
    blob = buf.getvalue()
    (OUT / f"{name}.npz").write_bytes(blob)
    return hashlib.sha256(blob).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k2", required=True)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    from engcore.inference import AdmittedForwardTable, gaussian_grid_posterior
    prov = {"schema": "grid_resolution_fixtures/1", "fixtures": {}}

    from experiments.kinetics_k2 import k2_config as C, k2_forward as F
    z = np.load(args.k2, allow_pickle=False)
    keys = tuple(json.loads(str(z["observation_keys"])))
    table = AdmittedForwardTable(parameter_names=C.PARAMETER_NAMES, observation_keys=keys, points=z["points"], values=z["values"],
                                 admissible_mask=z["admissible_mask"], admission_refs=tuple(tuple(r) for r in json.loads(str(z["admission_refs"]))),
                                 rejection_reasons=tuple(json.loads(str(z["rejection_reasons"]))))
    primary = F.observation_set_from_truth_means(F.truth_means(), seed=C.PRIMARY_SEED, condition_ids=C.MULTI_CONDITION_IDS)
    weak = primary.subset(C.WEAK_CONDITION_IDS, dataset_id="K2-primary-weak-C2")
    report = {"k2_multi": (primary, [20.979314794931746, 8775.076414950117], [0.15202805349527396, 49.51789691706498]),
              "k2_weak_c2": (weak, [21.07347982427268, 8806.143839722085], [1.1959411184598971, 388.8372838352901])}
    axes = axes_of(table.points)
    c2 = [keys.index("C2:C_A:final"), keys.index("C2:T:final")]
    for name, (obs, mean, sd) in report.items():
        post = gaussian_grid_posterior(table, obs)
        if not (np.allclose(post.mean, mean, rtol=1e-9) and np.allclose(np.sqrt(np.diag(post.covariance)), sd, rtol=1e-9)):
            raise SystemExit(f"{name} does not reproduce k2_report.md")
        digest = save(name, axis0=axes[0], axis1=axes[1], log_likelihood=post.log_likelihood, admissible_mask=post.admissible_mask,
                      c2_predictions=table.values[:, c2])
        prov["fixtures"][name] = {"sha256": digest, "parameters": list(C.PARAMETER_NAMES), "grid_points": int(len(post.weights)),
                                  "reproduces": "experiments/kinetics_k2/k2_report.md posterior mean and sd to 1e-9",
                                  "source": "K2's frozen builder (experiments/kinetics_k2/k2_forward.build_forward_table_with_stats), 61x61 grid, 3,686/3,721 admitted",
                                  "c2_prediction_columns": ["C2:C_A:final", "C2:T:final"],
                                  "dataset_id": obs.dataset_id}

    spec = importlib.util.spec_from_file_location("_b3_fix", ROOT / "benchmarks" / "battery_flagship_b3" / "audit" / "run_b3.py")
    H = importlib.util.module_from_spec(spec)
    sys.modules["_b3_fix"] = H
    spec.loader.exec_module(H)
    data = H.Data()
    for model_id in ("P2", "P3"):
        param = H.parameterization(model_id)
        full = H.wls(param, data.split.calibration, data)
        g = H.MODELS[model_id]["grid"]
        se = np.sqrt(np.diag(full["cov"]))
        grid_axes = [np.linspace(t - g["span_marginal_standard_errors"] * e, t + g["span_marginal_standard_errors"] * e, g["per_axis"]) for t, e in zip(full["theta"], se)]
        grid = [tuple(map(float, r)) for r in np.array(np.meshgrid(*grid_axes, indexing="ij")).reshape(len(grid_axes), -1).T]
        post = gaussian_grid_posterior(H.forward_table(model_id, "calibration", grid, data, 1), data.split.calibration)
        committed = json.loads((ROOT / "benchmarks" / "battery_flagship_b3" / "RESULTS.json").read_text(encoding="utf-8"))["models"][model_id]["routes"]["CORE_GRID"]["posterior"]
        if not np.allclose(post.mean, committed["mean_v"], rtol=1e-12):
            raise SystemExit(f"{model_id} does not reproduce the committed B3 grid posterior")
        a = axes_of(post.points)
        digest = save(f"battery_{model_id.lower()}", **{f"axis{i}": a[i] for i in range(len(a))}, log_likelihood=post.log_likelihood,
                      admissible_mask=post.admissible_mask, exact_linear_gaussian_mean=full["theta"], exact_linear_gaussian_covariance=full["cov"])
        prov["fixtures"][f"battery_{model_id.lower()}"] = {
            "sha256": digest, "parameters": list(param.names), "grid_points": int(len(post.weights)),
            "reproduces": "benchmarks/battery_flagship_b3/RESULTS.json CORE_GRID posterior mean to 1e-12",
            "source": "B3 grid rule through the production battery adapter; the model is affine in its voltages, so the WLS Gaussian stored beside it is the exact posterior",
            "dataset_id": post.dataset_id}
        print(model_id, "ok", flush=True)
    (OUT / "PROVENANCE.json").write_bytes((json.dumps(prov, indent=1) + "\n").encode("utf-8"))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
