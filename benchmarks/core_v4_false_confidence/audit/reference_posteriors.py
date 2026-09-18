"""Pin a dense reference posterior for every false-confidence conformance case (re-audit I-15).

A conformance case asserts that a SUPPORTED 95% interval holds at least
``benchmarks/core_v4_false_confidence/BATCH6_THRESHOLD_PROTOCOL.json``'s
``conformance_supported_interval_mass_floor`` of the posterior. "The posterior" has to be something other
than the route's own answer, so each case gets a dense tensor grid posterior over its DECLARED bounds, built
through the frozen ``gaussian_grid_posterior``, and what is pinned is each parameter's marginal QUANTILE
function on a uniform probability grid. Quantiles rather than a CDF on the nodes: inverting a monotone
piecewise-linear quantile function bounds the mass error by one probability step whatever the density, which a
CDF sampled on a uniform node grid does not (a narrow mode between two nodes carries its whole mass in one
step).

A reference is admitted only if halving the step on every axis moves the mean and every marginal standard
deviation by less than ``reference_convergence_sd`` of that marginal sd.

Run from the repository root:

    python -m benchmarks.core_v4_false_confidence.audit.reference_posteriors            # verify against the pinned file
    python -m benchmarks.core_v4_false_confidence.audit.reference_posteriors --write    # regenerate it

It takes a few minutes: the references run to about a million nodes each.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tests" / "hybrid_uq"))

import false_confidence_cases as F  # noqa: E402
import hybrid_synthetic as S  # noqa: E402

OUT = ROOT / "benchmarks" / "core_v4_false_confidence" / "REFERENCE_POSTERIORS.json"
SCHEMA = "core_v4_false_confidence_reference_posteriors/1"

#: Probability steps of the pinned marginal quantile function. 2000 steps bound the mass error of an inverted
#: quantile lookup at 5e-4, which is a fortieth of the 0.05 gap between the claimed 0.95 and the 0.90 floor.
QUANTILE_STEPS = 2000

#: A reference is admitted only when halving its step moves its moments by less than this many marginal sd.
REFERENCE_CONVERGENCE_SD = 0.01

#: Cross-provider re-derivation tolerance, expressed in each marginal's SD.
#:
#: The committed artifact's own SHA-256 remains exact. Rebuilding the same
#: posterior through an unpinned NumPy/SciPy stack is a different question:
#: reduction/interpolation order may move the final float by a few ulps while
#: leaving the scientific posterior unchanged. 4096 float64 eps is about
#: 9.1e-13 SD -- more than ten orders tighter than the 0.01 SD convergence
#: criterion that admits a reference in the first place.
REDERIVATION_FLOAT_EPS_MULTIPLIER = 4096
REDERIVATION_SD_TOLERANCE = (
    REDERIVATION_FLOAT_EPS_MULTIPLIER * np.finfo(np.float64).eps
)


#: label -> (builder, per-axis node counts of the reference).
CASES = {
    "bimodal_two_parameter": (S.bimodal_two_parameter, (1201, 801)),
    "narrow_second_mode_inside_the_box": (F.narrow_second_mode_inside_the_box, (60001,)),
    "worse_local_optimum_holds_the_mass": (F.worse_local_optimum_holds_the_mass, (310001,)),
    "second_mode_behind_a_refit_budget": (F.second_mode_behind_a_refit_budget, (120001,)),
    "retracted_starts_never_leave_the_basin": (F.retracted_starts_never_leave_the_basin, (120001,)),
    "off_axis_flat_tail": (F.off_axis_flat_tail, (801, 801)),
    "admissibility_cut": (F.admissibility_cut, (200001,)),
}


def _axes(problem, nodes):
    bounds = [(q.bounds.lower.magnitude_in(q.unit), q.bounds.upper.magnitude_in(q.unit))
              for q in problem.parameters.parameters]
    return [np.linspace(lo, hi, int(n)) for (lo, hi), n in zip(bounds, nodes)]


def _marginals(problem, axes):
    """``(mean, sd, [quantiles per axis])`` of the dense grid posterior over ``axes``."""
    grid = problem.grid(axes)
    weights = np.asarray(grid.weights, dtype=np.float64)
    points = np.asarray(grid.points, dtype=np.float64)
    mean = np.asarray(grid.mean, dtype=np.float64)
    sd = np.sqrt(np.diag(np.asarray(grid.covariance, dtype=np.float64)))
    quantiles = []
    probabilities = np.linspace(0.0, 1.0, QUANTILE_STEPS + 1)
    for i, axis in enumerate(axes):
        order = np.argsort(points[:, i], kind="stable")
        value, mass = points[order, i], weights[order]
        # mass at each distinct node value, then the CDF at the RIGHT edge of each node
        edges, index = np.unique(value, return_inverse=True)
        per_node = np.zeros(len(edges))
        np.add.at(per_node, index, mass)
        cdf = np.cumsum(per_node)
        cdf = cdf / cdf[-1]
        # the quantile function: the smallest node whose CDF reaches p. Interpolated on the node values, which
        # is exact for a piecewise-uniform reconstruction and the inverse of what the test then does.
        quantiles.append(np.interp(probabilities, cdf, edges))
    return mean, sd, quantiles


def _encode(values) -> str:
    return base64.b64encode(np.ascontiguousarray(values, dtype="<f8").tobytes()).decode("ascii")


def decode(payload: str) -> np.ndarray:
    return np.frombuffer(base64.b64decode(payload.encode("ascii")), dtype="<f8")


def build() -> dict:
    cases = {}
    for label, (builder, nodes) in CASES.items():
        problem = builder()
        axes = _axes(problem, nodes)
        mean, sd, quantiles = _marginals(problem, axes)
        finer = [np.linspace(a[0], a[-1], 2 * (len(a) - 1) + 1) for a in axes]
        fine_mean, fine_sd, _ = _marginals(problem, finer)
        moved = float(max(np.max(np.abs(fine_mean - mean) / sd), np.max(np.abs(fine_sd - sd) / sd)))
        cases[label] = {
            "problem": problem.label,
            "parameter_names": list(problem.parameters.names),
            "nodes": [int(len(a)) for a in axes],
            "bounds": [[float(a[0]), float(a[-1])] for a in axes],
            "mean": [float(v) for v in mean],
            "sd": [float(v) for v in sd],
            "quantile_steps": QUANTILE_STEPS,
            "quantiles_f8_base64": [_encode(q) for q in quantiles],
            "halved_step_moved_sd": moved,
            "converged": bool(moved < REFERENCE_CONVERGENCE_SD),
        }
        print(f"{label}: nodes {cases[label]['nodes']} mean {cases[label]['mean']} sd {cases[label]['sd']} "
              f"halved-step move {moved:.4g} sd -> {'CONVERGED' if cases[label]['converged'] else 'NOT CONVERGED'}",
              flush=True)
    payload = {"schema": SCHEMA, "reference_convergence_sd": REFERENCE_CONVERGENCE_SD,
               "protocol": "benchmarks/core_v4_false_confidence/BATCH6_THRESHOLD_PROTOCOL.json", "cases": cases}
    payload["digest"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return payload


def _decode(encoded: str) -> np.ndarray:
    return np.frombuffer(base64.b64decode(encoded.encode("ascii")), dtype="<f8")


def rederivation_problems(stored: dict, rebuilt: dict) -> tuple[str, ...]:
    """Scientific differences between a pinned reference and a fresh rebuild.

    The stored artifact's byte integrity is checked separately by its SHA-256.
    This comparison answers whether the *posterior* was re-derived. It therefore
    keeps structural declarations exact and allows only float64 round-off at a
    tolerance many orders below the reference-admission criterion.
    """

    problems: list[str] = []
    for key in ("schema", "reference_convergence_sd", "protocol"):
        if stored.get(key) != rebuilt.get(key):
            problems.append(
                f"top-level {key} changed: stored={stored.get(key)!r}, "
                f"rebuilt={rebuilt.get(key)!r}"
            )

    stored_cases = stored.get("cases", {})
    rebuilt_cases = rebuilt.get("cases", {})
    if set(stored_cases) != set(rebuilt_cases):
        problems.append(
            "case set changed: "
            f"stored={sorted(stored_cases)}, rebuilt={sorted(rebuilt_cases)}"
        )
        return tuple(problems)

    tolerance = REDERIVATION_SD_TOLERANCE
    exact_fields = (
        "problem",
        "parameter_names",
        "nodes",
        "bounds",
        "quantile_steps",
        "converged",
    )

    for label in sorted(stored_cases):
        old = stored_cases[label]
        new = rebuilt_cases[label]
        for key in exact_fields:
            if old.get(key) != new.get(key):
                problems.append(
                    f"{label}: {key} changed: "
                    f"stored={old.get(key)!r}, rebuilt={new.get(key)!r}"
                )

        old_mean = np.asarray(old["mean"], dtype=np.float64)
        new_mean = np.asarray(new["mean"], dtype=np.float64)
        old_sd = np.asarray(old["sd"], dtype=np.float64)
        new_sd = np.asarray(new["sd"], dtype=np.float64)
        if (
            old_mean.shape != new_mean.shape
            or old_sd.shape != new_sd.shape
            or old_mean.shape != old_sd.shape
        ):
            problems.append(
                f"{label}: moment vector shape changed: "
                f"mean {old_mean.shape}->{new_mean.shape}, "
                f"sd {old_sd.shape}->{new_sd.shape}"
            )
            continue

        bounds = np.asarray(old["bounds"], dtype=np.float64)
        span = (
            np.abs(bounds[:, 1] - bounds[:, 0])
            if bounds.shape == (len(old_sd), 2)
            else np.ones_like(old_sd)
        )
        scale = np.where(old_sd > 0.0, old_sd, np.maximum(span, 1.0))

        mean_move = np.abs(new_mean - old_mean) / scale
        sd_move = np.abs(new_sd - old_sd) / scale
        if np.any(~np.isfinite(mean_move)) or float(np.max(mean_move, initial=0.0)) > tolerance:
            problems.append(
                f"{label}: mean moved by "
                f"{float(np.max(mean_move, initial=0.0)):.6g} SD "
                f"(limit {tolerance:.6g})"
            )
        if np.any(~np.isfinite(sd_move)) or float(np.max(sd_move, initial=0.0)) > tolerance:
            problems.append(
                f"{label}: sd moved by "
                f"{float(np.max(sd_move, initial=0.0)):.6g} SD "
                f"(limit {tolerance:.6g})"
            )

        old_moved = float(old["halved_step_moved_sd"])
        new_moved = float(new["halved_step_moved_sd"])
        moved_delta = abs(new_moved - old_moved)
        if not math.isfinite(moved_delta) or moved_delta > tolerance:
            problems.append(
                f"{label}: halved-step movement changed by "
                f"{moved_delta:.6g} SD (limit {tolerance:.6g})"
            )

        old_q = tuple(old.get("quantiles_f8_base64", ()))
        new_q = tuple(new.get("quantiles_f8_base64", ()))
        if len(old_q) != len(new_q) or len(old_q) != len(old_sd):
            problems.append(
                f"{label}: quantile axis count changed: "
                f"stored={len(old_q)}, rebuilt={len(new_q)}, "
                f"marginals={len(old_sd)}"
            )
            continue
        for axis, (old_encoded, new_encoded) in enumerate(zip(old_q, new_q)):
            old_values = _decode(old_encoded)
            new_values = _decode(new_encoded)
            if old_values.shape != new_values.shape:
                problems.append(
                    f"{label} axis {axis}: quantile shape changed "
                    f"{old_values.shape}->{new_values.shape}"
                )
                continue
            q_move = np.abs(new_values - old_values) / scale[axis]
            maximum = float(np.max(q_move, initial=0.0))
            if np.any(~np.isfinite(q_move)) or maximum > tolerance:
                problems.append(
                    f"{label} axis {axis}: quantile function moved by "
                    f"{maximum:.6g} SD (limit {tolerance:.6g})"
                )

    return tuple(problems)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    payload = build()
    not_converged = sorted(k for k, v in payload["cases"].items() if not v["converged"])
    if not_converged:
        print(f"REFUSED: references that did not converge under a halved step: {not_converged}")
        return 1
    if args.write:
        OUT.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {OUT} ({OUT.stat().st_size} bytes), digest {payload['digest']}")
        return 0
    stored = json.loads(OUT.read_text(encoding="utf-8"))
    problems = rederivation_problems(stored, payload)
    if problems:
        print(
            "DIFFERS SCIENTIFICALLY FROM the pinned file; "
            f"pinned {stored.get('digest')}, rebuilt {payload['digest']}"
        )
        for problem in problems:
            print(f"- {problem}")
        return 1
    print(
        "SCIENTIFICALLY MATCHES the pinned file; exact rebuild digest "
        f"{payload['digest']} (pinned artifact digest {stored.get('digest')})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
