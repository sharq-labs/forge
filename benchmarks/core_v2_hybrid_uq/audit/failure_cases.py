"""Part 13: adversarial cases -- the V2 route must refuse or downgrade wherever its assumptions fail.

    python -X utf8 benchmarks/core_v2_hybrid_uq/audit/failure_cases.py

Synthetic analytic models (tests/hybrid_uq/hybrid_synthetic.py) through the frozen ``calibrate`` and the public V2
API. For each case this reports:

* the local route's claim and reasons;
* what the router does, with and without a grid-rebuild policy;
* a dense reference over the declared bounds;
* identifiability, separately.

Every expectation is written into the case BEFORE it runs, and ``met`` records whether it held.

Scientific core audit 2026-09-16, batch 1 (benchmarks/core_v4_false_confidence/BATCH1_THRESHOLD_PROTOCOL.json). Two
expectations changed before this file was re-run, both already seen in tests/hybrid_uq: strong_nonlinearity's rebuilt grid
spans both declared bounds of its decay rate and is passed over GRID_POSTERIOR_BOUND_DOMINATED (its sd was the upper bound's:
1.75 at 20, 2.57 at 40, 5.81 at 80), and the renamed non-tensor point set is refused as not the request's evidence before
V1 is asked (CORE-005). The batch-1 cases below the original ones were written before this file first ran them.

Writes benchmarks/core_v2_hybrid_uq/FAILURE_CASES.json.
"""

from __future__ import annotations

import sys

import numpy as np

from common import ROOT, dump

sys.path.insert(0, str(ROOT / "tests" / "hybrid_uq"))
import hybrid_synthetic as S  # noqa: E402

from engcore.hybrid_uq import (  # noqa: E402
    GridRebuildPolicy, HybridUQError, MultistartPolicy, RouteClaim, RouteDecision, RouteReason, RouteRefusedError, assess_routed_identifiability,
    local_gaussian_posterior, route_uncertainty,
)
from engcore.inference import GridResolutionError, PosteriorGrid  # noqa: E402


def poorly_scaled():
    return S.Problem("poorly_scaled", lambda t, x: t[0] * 1e-9 + t[1] * 1e4 * x, np.linspace(0.0, 1.0, 12), (2e9, 1e-4), 0.05,
                     (0.0, -1.0), (1e10, 1.0), (1e9, 0.0))


CASES = [
    ("strong_nonlinearity", S.strong_nonlinearity, [np.linspace(0.01, 20.0, 481), np.linspace(0.01, 10.0, 481)],
     {"local": "REFUSED", "reason": "NONLINEAR_BEYOND_LOCAL_GAUSSIAN", "rebuild": "REFUSED",
      "rebuild_reason": "GRID_POSTERIOR_BOUND_DOMINATED"}),
    ("parameter_at_bound", S.at_bound, [np.linspace(0.8, 1.2, 401), np.linspace(0.0, 0.3, 401)],
     {"local": "REFUSED", "reason": "PARAMETER_AT_BOUND", "rebuild": "GRID_REBUILT_FROM_LOCAL_COVARIANCE"}),
    ("nearly_singular_jacobian", S.nearly_singular, None,
     {"local": "REFUSED", "reason": "NUMERICALLY_SINGULAR_JACOBIAN", "rebuild": "REFUSED"}),
    ("mirror_mode", S.mirror_mode, [np.linspace(-3.0, 3.0, 6001)],
     {"local": "REFUSED", "reason": "SECOND_MODE_FOUND", "rebuild": "GRID_REBUILT_FROM_LOCAL_COVARIANCE"}),
    ("multimodal_two_parameter", S.bimodal_two_parameter, [np.linspace(-3.0, 3.0, 1201), np.linspace(-2.0, 2.0, 801)],
     {"local": "REFUSED", "reason": "SECOND_MODE_FOUND", "rebuild": "GRID_REBUILT_FROM_LOCAL_COVARIANCE"}),
    ("log_parameterization_of_a_linear_model", lambda: S.log_parameterization("log"), None,
     {"local": "REFUSED", "reason": "NONLINEAR_BEYOND_LOCAL_GAUSSIAN"}),
    ("poorly_scaled_parameterization", poorly_scaled, None,
     {"local": "DOWNGRADED", "reason": "POORLY_SCALED_PARAMETERIZATION", "multistart": None}),
    ("weak_identification", S.weak_identification, None,
     {"local": "SUPPORTED", "identifiability": "PARAMETERS_NOT_IDENTIFIABLE"}),
    ("thin_correlated_ridge_with_aliased_bounds_grid", S.thin_ridge, [np.linspace(-50, 50, 401), np.linspace(-5, 5, 401)],
     {"local": "SUPPORTED", "grid_as_supplied": "REFUSED_BY_V1", "router": "LOCAL_GAUSSIAN"}),
    # --- scientific core audit 2026-09-16, batch 1 -------------------------------------------------------------------
    ("CORE001_gross_misfit", lambda: _misfit(0.01), None,
     {"local": "REFUSED", "reason": "MODEL_MISFIT_BEYOND_DECLARED_NOISE", "rebuild": "REFUSED",
      "rebuild_reason": "MODEL_MISFIT_BEYOND_DECLARED_NOISE"}),
    ("CORE001_moderate_misfit", lambda: _misfit(0.165), None,
     {"local": "DOWNGRADED", "reason": "RESIDUALS_EXCEED_DECLARED_NOISE"}),
    ("CORE003_tail_beyond_the_2_sd_probes", lambda: _tail(), None,
     {"local": "REFUSED", "reason": "TAIL_HEAVIER_THAN_LOCAL_GAUSSIAN"}),
]


def _misfit(sigma):
    x = np.linspace(0.0, 1.0, 12)
    return S.Problem("CORE001_misfit", lambda t, x: t[0] + t[1] * x, x, (1.0, 2.0), sigma, (-50.0, -50.0), (50.0, 50.0),
                     (0.0, 0.0), observed=1.0 + 2.0 * x + 3.0 * x ** 2)


def _tail(eps=0.01, c=2.05):
    import math

    def model(t, x):
        th = float(t[0]) - 100.0
        return np.asarray([max(-c, min(c, th)), math.sqrt(eps * max(abs(th) - c, 0.0)), 0.0])
    return S.Problem("CORE003_tail", model, [0.0, 1.0, 2.0], (100.0,), 1.0, (-900.0,), (1100.0,), (100.3,), observed=[0.0, 0.0, 0.0])


def main():
    out = {"schema": "core_v2_hybrid_uq_failure_cases/1", "cases": {}}
    for label, make, axes, expect in CASES:
        P = make()
        calibration = P.calibrate()
        multistart = expect.get("multistart", MultistartPolicy())
        post = local_gaussian_posterior(calibration, P.observations, P.forward, multistart=multistart)
        row = {"expect": expect, "calibration": calibration.status.value, "estimate": list(calibration.estimate_vector),
               "local": {"claim": post.claim.value, "refusals": [r.value for r in post.diagnostics.refusals],
                         "downgrades": [r.value for r in post.diagnostics.downgrades], "uniqueness": post.diagnostics.uniqueness,
                         "nonlinearity_index": post.diagnostics.nonlinearity_index, "jacobian_condition": post.diagnostics.jacobian_condition,
                         "raw_jacobian_condition": post.diagnostics.raw_jacobian_condition, "emits_covariance": post.covariance is not None}}
        try:
            row["identifiability"] = assess_routed_identifiability(post).status.value
        except RouteRefusedError:
            row["identifiability"] = "NONE (route refused)"
        met = post.claim.value == expect["local"] and (expect.get("reason") is None or expect["reason"] in [r.value for r in post.reasons])
        if "identifiability" in expect:
            met = met and row["identifiability"] == expect["identifiability"]
        if axes is not None:
            reference = P.grid(axes)
            row["dense_reference"] = {"mean": list(reference.mean), "sd": list(np.sqrt(np.diag(reference.covariance))),
                                      "nodes": [len(a) for a in axes]}
        if "rebuild" in expect:
            routed = route_uncertainty(calibration=calibration, observations=P.observations, forward=P.forward, multistart=MultistartPolicy(),
                                       rebuild=GridRebuildPolicy(P.table_builder()))
            row["router_with_rebuild"] = {"decision": routed.decision.value, "claim": routed.claim.value, "considered": routed.considered,
                                          "mean": routed.mean, "sd": None if routed.covariance is None else list(np.sqrt(np.diag(routed.covariance)))}
            met = met and routed.decision.value == expect["rebuild"]
            if "rebuild_reason" in expect:
                met = met and any(c.get("reason") == expect["rebuild_reason"] for c in routed.considered)
            if routed.covariance is not None and axes is not None:
                sd = np.asarray(row["dense_reference"]["sd"])
                shift = np.abs(np.asarray(routed.mean) - np.asarray(row["dense_reference"]["mean"])) / sd
                ratio = np.sqrt(np.diag(routed.covariance)) / sd
                row["router_with_rebuild"].update({"mean_shift_reference_sd": shift.tolist(), "sd_ratio_reference": ratio.tolist()})
                met = met and bool(np.all(shift < 0.05) and np.all(np.abs(ratio - 1) < 0.05))
            routed_plain = route_uncertainty(calibration=calibration, observations=P.observations, forward=P.forward, multistart=MultistartPolicy())
            row["router_without_rebuild"] = {"decision": routed_plain.decision.value, "emits_numbers": routed_plain.covariance is not None}
            met = met and (routed_plain.decision is RouteDecision.REFUSED) == (post.claim is RouteClaim.REFUSED)
        if "grid_as_supplied" in expect:
            grid = P.grid(axes)
            routed = route_uncertainty(grid=grid, calibration=calibration, observations=P.observations, forward=P.forward, multistart=MultistartPolicy())
            row["router_with_aliased_grid"] = {"decision": routed.decision.value, "considered": routed.considered,
                                               "aliased_grid_mean": list(grid.mean), "route_mean": routed.mean}
            met = met and routed.considered[0]["outcome"] == expect["grid_as_supplied"] and routed.decision.value == expect["router"]
        row["met"] = bool(met)
        out["cases"][label] = row
        print(f"{label:48s} local={post.claim.value:10s} {[r.value for r in post.reasons]} ident={row['identifiability']} met={met}", flush=True)

    # mapped / non-tensor point set: a linearly mapped grid is not a tensor lattice, so V1 refuses and so must the router
    P = S.affine()
    grid = P.grid([np.linspace(0.6, 1.3, 61), np.linspace(1.4, 2.7, 61)])
    T = np.asarray([[1.0, 0.0], [-1.0, 1.0]])
    mapped = PosteriorGrid(parameter_names=("a", "b_minus_a"), points=grid.points @ T.T, weights=grid.weights,
                           log_likelihood=grid.log_likelihood, admissible_mask=grid.admissible_mask, dataset_id=grid.dataset_id)
    alone = route_uncertainty(grid=mapped)
    calibration = P.calibrate()
    # Audit HUQ-06: a supplied grid must be over the parameters the request calibrates. The mapped grid is over
    # (a, b_minus_a) and the request calibrates (theta1, theta2), so routing the two together is refused outright. The
    # same non-tensor points under the request's own names keep this case's original question: V1 refuses the point
    # set, and the router must fall through to the local route.
    try:
        route_uncertainty(grid=mapped, calibration=calibration, observations=P.observations, forward=P.forward, multistart=MultistartPolicy())
        other_names = "ROUTED"
    except HybridUQError as exc:
        other_names = f"HybridUQError: {str(exc)[:160]}"
    renamed = PosteriorGrid(parameter_names=grid.parameter_names, points=mapped.points, weights=mapped.weights,
                            log_likelihood=mapped.log_likelihood, admissible_mask=mapped.admissible_mask, dataset_id=mapped.dataset_id)
    # CORE-005: the renamed points are not where the grid's likelihood was computed, so the grid is not this request's
    # evidence; the router says so before V1 is asked.
    try:
        with_local = route_uncertainty(grid=renamed, calibration=calibration, observations=P.observations, forward=P.forward,
                                       multistart=MultistartPolicy())
        renamed_outcome, renamed_refused_as_other_evidence = f"ROUTED {with_local.decision.value}", False
    except HybridUQError as exc:
        renamed_outcome = f"HybridUQError: {str(exc)[:160]}"
        renamed_refused_as_other_evidence = "not this request's evidence" in str(exc)
    try:
        from engcore.inference import assess_identifiability

        assess_identifiability(mapped)
        v1 = "accepted"
    except GridResolutionError as exc:
        v1 = str(exc)[:160]
    out["cases"]["mapped_non_tensor_point_set"] = {
        "expect": {"router_grid_only": "REFUSED", "router_with_local_other_parameter_names": "HybridUQError",
                   "router_with_local": "HybridUQError (CORE-005: not this request's evidence)"}, "v1": v1,
        "router_grid_only": {"decision": alone.decision.value, "considered": alone.considered},
        "router_with_local_other_parameter_names": other_names,
        "router_with_local": renamed_outcome,
        "met": (alone.decision is RouteDecision.REFUSED and other_names.startswith("HybridUQError")
                and renamed_refused_as_other_evidence),
    }
    print("mapped_non_tensor_point_set", alone.decision.value, other_names[:40], renamed_outcome[:60], flush=True)
    out["all_met"] = all(c["met"] for c in out["cases"].values())
    dump("FAILURE_CASES.json", out)


if __name__ == "__main__":
    main()
