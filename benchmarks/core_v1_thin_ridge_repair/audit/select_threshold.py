"""Apply THRESHOLD_PROTOCOL.json: score every validation case, then select the threshold by its declared rule.

    python -X utf8 benchmarks/core_v1_thin_ridge_repair/audit/select_threshold.py

Writes benchmarks/core_v1_thin_ridge_repair/THRESHOLD_SELECTION.json. The diagnostic values come from
the private functions in src/engcore/inference/calibration.py that the guard itself calls, run while
the guard is still unwired (_ALIASING_NUMBER_MINIMUM is None), so scoring cannot depend on a threshold.
"""

from __future__ import annotations

import json
import math
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[3]
ROUND = ROOT / "benchmarks" / "core_v1_thin_ridge_repair"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "inference"))

import engcore.inference.calibration as cal  # noqa: E402
from engcore.inference import AdmittedForwardTable, GaussianObservation, ObservationSet, gaussian_grid_posterior  # noqa: E402
from engcore.scientific.units.quantity import Quantity  # noqa: E402

PROTOCOL = json.loads((ROUND / "THRESHOLD_PROTOCOL.json").read_text(encoding="utf-8"))
LADDER = PROTOCOL["candidate_thresholds"]["values"]


def posterior_from_linear(label, predict, y, sigma, axes):
    obs = ObservationSet(tuple(GaussianObservation(condition_id=f"o{i}", observable_name="y", value=Quantity(float(v), "dimensionless"),
                                                   sigma=Quantity(float(sigma), "dimensionless"), source_ref=f"validation:{label}:{i}")
                               for i, v in enumerate(y)), dataset_id=f"threshold-validation.{label}")
    mesh = np.array(np.meshgrid(*axes, indexing="ij")).reshape(len(axes), -1).T
    table = AdmittedForwardTable(parameter_names=tuple(f"t{i + 1}" for i in range(len(axes))), observation_keys=obs.keys, points=mesh,
                                 values=np.asarray(predict(mesh), float), admissible_mask=np.ones(len(mesh), bool),
                                 admission_refs=tuple(tuple(f"analytic:{label}" for _ in obs.keys) for _ in mesh), rejection_reasons=tuple("" for _ in mesh))
    return gaussian_grid_posterior(table, obs)


def gaussian_posterior(label, mu, sigma, axes):
    A = np.linalg.inv(np.linalg.cholesky(sigma))
    return posterior_from_linear(label, lambda pts: pts @ A.T, A @ mu, 1.0, axes)


def material(post, mu, cov):
    sd_t = np.sqrt(np.diag(cov))
    mean_err = float(np.max(np.abs(post.mean - mu) / sd_t))
    ratio = np.sqrt(np.diag(post.covariance)) / sd_t
    lam, vec = np.linalg.eigh(cov)
    u = vec[:, 0]
    thin = math.sqrt(max(float(u @ post.covariance @ u), 0.0)) / math.sqrt(lam[0])
    thin_mean = abs(float(u @ (post.mean - mu))) / math.sqrt(lam[0])
    bad = bool(mean_err > 0.1 or ratio.min() < 0.9 or ratio.max() > 1.1 or not 0.9 <= thin <= 1.1 or thin_mean > 0.1)
    return bad, {"max_mean_error_in_sd": mean_err, "sd_ratio": ratio.tolist(), "thin_sd_ratio": thin, "thin_mean_error": thin_mean}


def score(post):
    """Diagnostic values exactly as the guard computes them, threshold-free."""
    p = post.points.shape[1]
    need = (p + 1) * (p + 2) // 2
    usable = int(np.count_nonzero(np.isfinite(post.log_likelihood) & post.admissible_mask))
    steps = cal._tensor_lattice_steps(post.points)
    ess = cal.posterior_effective_sample_size(post)
    diag = cal.posterior_grid_diagnostics(post)
    old_refuses = bool(ess < 8.0 and max(diag["spacing_to_std"]) >= 1.0)
    companion = None
    aliasing = None
    fit = None
    if usable < need:
        companion = "TOO_FEW_NODES"
    elif steps is None:
        companion = "NOT_A_TENSOR_LATTICE"
    elif ess < p + 1:
        companion = "ESS_BELOW_P_PLUS_1"
    else:
        S, fit = cal._fitted_lattice_covariance(post, steps)
        if S is None:
            companion = "CURVATURE_FIT_FAILED"
        else:
            value = cal._minimum_aliasing_number(S, 1.0e6)
            aliasing = math.inf if value is None else value
    return {"old_guard_refuses": old_refuses, "companion_refusal": companion, "aliasing_number": aliasing, "ess": ess, "fit": fit}


def refused_at(row, T):
    return bool(row["old_guard_refuses"] or row["companion_refusal"] is not None or (row["aliasing_number"] is not None and row["aliasing_number"] < T))


def held_back():
    rng = np.random.default_rng(PROTOCOL["validation_sets"]["HELD_BACK_SYNTHETIC"]["seed"])
    fams = PROTOCOL["validation_sets"]["HELD_BACK_SYNTHETIC"]["families"]
    rows = []

    def add(tag, family, mu, sig, axes):
        post = gaussian_posterior(tag, mu, sig, axes)
        bad, detail = material(post, mu, sig)
        rows.append({"tag": tag, "family": family, "materially_wrong": bad, "materiality": detail, **score(post)})

    f = fams["2D_correlation"]
    for rho in f["rho"]:
        for W in f["window_marginal_sd"]:
            for m in f["per_axis"]:
                for ph in range(f["lattice_phases"]):
                    sig = np.asarray([[1.0, rho], [rho, 1.0]])
                    h = 2 * W / (m - 1)
                    mu = rng.uniform(-0.5, 0.5, 2) * h
                    add(f"corr.rho{rho}.W{W}.m{m}.ph{ph}", "2D_correlation", mu, sig, [np.linspace(-W, W, m)] * 2)
    f = fams["2D_rotation"]
    for w in f["thin_width"]:
        for ang in f["angle_deg"]:
            for m in f["per_axis"]:
                for ph in range(f["lattice_phases"]):
                    c, s = math.cos(math.radians(ang)), math.sin(math.radians(ang))
                    V = np.asarray([[c, -s], [s, c]])
                    sig = V @ np.diag([1.0, w * w]) @ V.T
                    sd = np.sqrt(np.diag(sig))
                    h = 12 * sd / (m - 1)
                    mu = rng.uniform(-0.5, 0.5, 2) * h
                    add(f"rot.w{w}.a{ang}.m{m}.ph{ph}", "2D_rotation", mu, sig, [np.linspace(-6 * sd[i], 6 * sd[i], m) for i in range(2)])
    f = fams["2D_scaling_consistent"]
    for sc in f["scale"]:
        for m in f["per_axis"]:
            for ph in range(f["lattice_phases"]):
                S = np.diag([1.0, sc])
                sig = S @ np.asarray([[1.0, 0.995], [0.995, 1.0]]) @ S
                h = 12 / (m - 1)
                mu = S @ (rng.uniform(-0.5, 0.5, 2) * h)
                add(f"scale{sc}.m{m}.ph{ph}", "2D_scaling_consistent", mu, sig, [np.linspace(-6, 6, m), np.linspace(-6 * sc, 6 * sc, m)])
    f = fams["3D_one_thin_oblique_direction"]
    u = np.asarray([1.0, 2.0, 3.0]) / math.sqrt(14.0)
    for w in f["thin_width"]:
        for m in f["per_axis"]:
            for ph in range(f["lattice_phases"]):
                sig = np.eye(3) - (1 - w * w) * np.outer(u, u)
                sd = np.sqrt(np.diag(sig))
                h = 12 * sd / (m - 1)
                mu = rng.uniform(-0.5, 0.5, 3) * h
                add(f"3d.w{w}.m{m}.ph{ph}", "3D_one_thin_oblique_direction", mu, sig, [np.linspace(-6 * sd[i], 6 * sd[i], m) for i in range(3)])
    f = fams["1D"]
    for r in f["spacing_over_sd"]:
        for ph in range(f["lattice_phases"]):
            h = r
            m = int(2 * math.ceil(6 / h)) + 1
            mu = np.asarray([rng.uniform(-0.5, 0.5) * h])
            add(f"1d.r{r}.ph{ph}", "1D", mu, np.asarray([[1.0]]), [np.linspace(-(m - 1) / 2 * h, (m - 1) / 2 * h, m)])
    return rows


def real_cases():
    import test_grid_resolution_repair as T
    rows = []

    def add(tag, post, truth, role):
        row = {"tag": tag, "role": role, **score(post)}
        if truth is not None:
            bad, detail = material(post, *truth)
            row.update({"materially_wrong": bad, "materiality": detail})
        rows.append(row)

    mu, cov = T._f5_exact()
    for per in (201, 401, 801):
        add(f"F5_bounds_{per}", T._f5_posterior([np.linspace(T.F5_LOWER[i], T.F5_UPPER[i], per) for i in range(2)], f"f5.{per}"), (mu, cov), "known_materially_wrong")
    post, m, C = T._tcr([300.0, 320.0, 340.0, 360.0, 380.0, 400.0, 420.0, 440.0])
    add("TCR_WIDE_41", post, (m, C), "required_healthy_if_truth_confirms")
    post, m, C = T._tcr([299.0, 299.5, 300.0, 300.5, 301.0, 301.5])
    add("TCR_NARROW_41", post, (m, C), "known_materially_wrong")
    post, m, C = T._tcr([299.0, 299.5, 300.0, 300.5, 301.0, 301.5], per_axis=161)
    add("TCR_NARROW_161", post, (m, C), "required_healthy_if_truth_confirms")
    for name in ("battery_p2", "battery_p3"):
        post, z = T._fixture_posterior(name, name)
        add(name.upper(), post, (z["exact_linear_gaussian_mean"], z["exact_linear_gaussian_covariance"]), "required_healthy_if_truth_confirms")
    post, _ = T._fixture_posterior("k2_multi", "K2-seed-20260809")
    proxy = T._k2_proxy_covariance()
    local = json.loads((ROOT / "benchmarks" / "core_gap_hd_uq" / "DOMAIN_KINETICS.json").read_text(encoding="utf-8"))["MULTI"]
    add("K2_MULTI", post, None, "known_materially_wrong")
    lam, vec = np.linalg.eigh(proxy)
    rows[-1].update({"materially_wrong": True, "materiality": {"proxy_thin_sd_ratio": math.sqrt(float(vec[:, 0] @ post.covariance @ vec[:, 0])) / math.sqrt(lam[0]),
                                                               "reference": "local-Gaussian proxy (importance ESS 0.997)"}})
    post, _ = T._fixture_posterior("k2_weak_c2", "K2-primary-weak-C2")
    add("K2_WEAK_C2", post, None, "reported_not_threshold_bearing")
    return rows


def main():
    held = held_back()
    real = real_cases()
    evaluation = {}
    for T in LADDER:
        wrong = [r for r in held + real if r.get("materially_wrong")]
        missed = [r["tag"] for r in wrong if not refused_at(r, T)]
        required = [r for r in real if r["role"] == "required_healthy_if_truth_confirms"]
        confirmed = [r for r in required if r.get("materially_wrong") is False]
        unconfirmed_required = [r["tag"] for r in required if r.get("materially_wrong") is not False]
        lost = [r["tag"] for r in confirmed if refused_at(r, T)]
        healthy_synth = [r for r in held if not r["materially_wrong"]]
        refused_synth = [r["tag"] for r in healthy_synth if refused_at(r, T)]
        rate = len(refused_synth) / max(len(healthy_synth), 1)
        evaluation[f"{T:.6g}"] = {
            "T": T, "rule_i_all_materially_wrong_refused": not missed, "missed": missed,
            "rule_ii_required_healthy_kept": not lost, "lost": lost, "required_not_confirmed_healthy": unconfirmed_required,
            "rule_iii_false_refusal_rate": rate, "rule_iii_ok": rate <= 0.10, "falsely_refused_synthetic": refused_synth,
            "satisfies_all": (not missed) and (not lost) and rate <= 0.10}
    passing = [e["T"] for e in evaluation.values() if e["satisfies_all"]]
    chosen = max(passing) if passing else None
    out = {"schema": "core_v1_thin_ridge_repair_threshold_selection/1", "protocol_sha256": __import__("hashlib").sha256((ROUND / "THRESHOLD_PROTOCOL.json").read_bytes()).hexdigest(),
           "cases": {"held_back_synthetic": len(held), "held_back_materially_wrong": sum(r["materially_wrong"] for r in held), "real": len(real)},
           "evaluation_by_rung": evaluation, "chosen_threshold": chosen,
           "verdict": "SELECTED" if chosen is not None else "BLOCKED: no ladder value satisfies the declared rule",
           "held_back_rows": held, "real_rows": real}
    (ROUND / "THRESHOLD_SELECTION.json").write_bytes((json.dumps(out, indent=1, default=lambda x: x if not isinstance(x, float) or math.isfinite(x) else str(x)) + "\n").encode("utf-8"))
    for k, e in evaluation.items():
        print(f"T={k:>8}: missed {len(e['missed'])} lost {e['lost']} false-refusal {e['rule_iii_false_refusal_rate']:.3f} -> {e['satisfies_all']}")
    for r in real:
        print(r["tag"], r["role"], "A", r["aliasing_number"], r["companion_refusal"], "ESS %.2f" % r["ess"], "wrong", r.get("materially_wrong"))
    print("chosen", chosen)


if __name__ == "__main__":
    main()
