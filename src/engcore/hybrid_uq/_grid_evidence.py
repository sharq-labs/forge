"""What a grid must show before its moments may stand as a posterior for a request. Private.

Resolution (the frozen V1 checks) says a grid samples its own likelihood finely enough. It does not say that the
likelihood is the request's, that the declared noise explains the data, or that the grid's box holds the posterior.
Each of those failed at the 2026-09-16 audit (CORE-005, CORE-001, CORE-002), and each is checked here, for supplied
grids in the router and for grids a caller hands to ``grid_predictive_uncertainty``.
"""

from __future__ import annotations

import hashlib
import math

import numpy as np

from ..inference.calibration import CalibrationResult
from ..inference.grid import ObservationSet, PosteriorGrid
from .local_gaussian import MISFIT_REASONS, _goodness_of_fit, _leverage_null_cumulants, _leverage_weights
from .sensitivity import (
    DEFAULT_RELATIVE_STEP,
    central_difference,
    evaluate,
    inference_bounds,
    to_inference,
    to_natural,
    transforms_of,
)
from .vocabulary import HybridUQError, RouteRefusedError, RouteReason

#: A grid must contain its posterior: on every face, the largest log-likelihood must sit at least this far below the
#: grid's maximum (density below 1e-6 of the peak).
EDGE_LOG_LIKELIHOOD_DROP = math.log(1.0e6)

#: Interior nodes of a supplied grid re-evaluated through the forward model, chosen from a digest of the grid's bytes,
#: on top of its first and last node, its highest-likelihood node and the node nearest a calibrated estimate.
SPOT_CHECK_INTERIOR_NODES = 4

#: CORE-010: an axis is uniform in its inference coordinate when no step differs from the mean step by more than this
#: fraction of it. A float64 linspace, and its image through exp or log, stays far inside.
UNIFORM_STEP_RELATIVE_TOLERANCE = 1.0e-6

#: A recomputed chi-square must agree with the grid's to every standardized residual within this many sigma: the
#: agreement SUPPLIED_PREDICTION_AGREEMENT_SD already declares for a supplied prediction.
RESIDUAL_AGREEMENT_SD = 1.0e-6


def _log_normalizer(observations: ObservationSet) -> float:
    _observed, sigma = observations.numeric_vectors()
    return -0.5 * float(np.sum(np.log(2.0 * math.pi * sigma * sigma)))


def require_grid_is_this_evidence(grid: PosteriorGrid, calibration, observations: ObservationSet, forward) -> None:
    """Refuse a grid whose likelihood is not the request's observations under the request's forward model (CORE-005).

    A shared ``dataset_id`` is a label. At deterministic nodes the forward evaluator's admission must equal the grid's,
    and the chi-square recomputed from the forward evaluator and the observations must equal the one the grid's
    log-likelihood implies. A grid altered only at nodes that are not checked is not caught.
    """
    observed, sigma = observations.numeric_vectors()
    keys = observations.keys
    units = tuple(o.value.units for o in observations.observations)
    references = tuple(o.value for o in observations.observations)
    normalizer = _log_normalizer(observations)
    points = np.asarray(grid.points, dtype=np.float64)
    ll = np.asarray(grid.log_likelihood, dtype=np.float64)
    usable = np.asarray(grid.admissible_mask, dtype=bool) & np.isfinite(ll)
    count = len(points)
    rows = {0, count - 1, int(np.argmax(np.where(usable, ll, -np.inf)))}
    if isinstance(calibration, CalibrationResult) and calibration.estimate_vector:
        span = np.ptp(points, axis=0)
        span = np.where(span > 0.0, span, 1.0)
        rows.add(int(np.argmin(np.sum(((points - np.asarray(calibration.estimate_vector)) / span) ** 2, axis=1))))
    seed = hashlib.sha256(np.ascontiguousarray(points, dtype="<f8").tobytes()
                          + np.ascontiguousarray(ll, dtype="<f8").tobytes()
                          + np.ascontiguousarray(usable, dtype=np.uint8).tobytes()).digest()
    rows.update(int.from_bytes(seed[4 * k:4 * k + 4], "little") % count for k in range(SPOT_CHECK_INTERIOR_NODES))
    n = len(observed)
    for row in sorted(rows):
        value = evaluate(forward, points[row], keys, units, references)
        where = f"node {row} ({points[row].tolist()})"
        if value is None:
            if usable[row]:
                raise HybridUQError(f"the grid carries a likelihood at {where}, which the forward evaluator refuses: the grid is "
                                    f"not this request's evidence")
            continue
        if not usable[row]:
            raise HybridUQError(f"the grid has no likelihood at {where}, which the forward evaluator admits: the grid is not "
                                f"this request's evidence")
        chi_forward = float(np.sum(((value - observed) / sigma) ** 2))
        chi_grid = -2.0 * (float(ll[row]) - normalizer)
        roundoff = 64.0 * float(np.finfo(float).eps) * (abs(normalizer) + abs(float(ll[row])) + chi_forward + n)
        tolerance = 2.0 * RESIDUAL_AGREEMENT_SD * math.sqrt(n * chi_forward) + n * RESIDUAL_AGREEMENT_SD ** 2 + roundoff + 1e-9
        if not abs(chi_grid - chi_forward) <= tolerance:
            raise HybridUQError(
                f"the grid's likelihood at {where} implies chi-square {chi_grid:.6g}; the forward evaluator and the request's "
                f"observations give {chi_forward:.6g}. A grid computed from other data or another model is not this "
                f"request's evidence, whatever its dataset id says")


def _grid_leverage(grid: PosteriorGrid, row: int, observations: ObservationSet, calibration, forward):
    """``(statistic, cumulants)`` of the leverage test at one grid node, or None when the curvature is not there.

    R-03's dilution is a property of the RULE, not of its caller: a supplied grid over a padded dataset passes
    the pooled test for the same reason and with the same covariance error. So the grid is held to the same two
    tests, at the node its chi-square minimum comes from -- the residuals from one forward evaluation there,
    the weights from the hat diagonal of a convergence-checked Jacobian there. The Jacobian is the cost this
    check did not have before: at least 4p + 1 forward evaluations, on a route whose grid is exponential in p
    and therefore small.
    """
    if not isinstance(calibration, CalibrationResult) or forward is None:
        return None
    parameters = calibration.spec.parameters
    if tuple(parameters.names) != tuple(grid.parameter_names):
        return None
    transforms = transforms_of(parameters)
    lower, upper = inference_bounds(parameters)
    observed, sigma = observations.numeric_vectors()
    keys = observations.keys
    units = tuple(o.value.units for o in observations.observations)
    references = tuple(o.value for o in observations.observations)
    node = np.asarray(grid.points, dtype=np.float64)[int(row)]

    def fun(z):
        return evaluate(forward, to_natural(z, transforms), keys, units, references)

    try:
        base, jacobian, _steps, _one_sided, _evaluations = central_difference(
            fun, to_inference(node, transforms), lower, upper, DEFAULT_RELATIVE_STEP, weights=sigma)
    except RouteRefusedError:
        return None
    weighted = np.asarray(jacobian, dtype=np.float64) / np.asarray(sigma, dtype=np.float64)[:, None]
    residual = (np.asarray(base, dtype=np.float64) - observed) / sigma
    weights, basis = _leverage_weights(weighted)
    return float(np.sum(weights * residual ** 2)), _leverage_null_cumulants(weights, basis)


def grid_goodness_of_fit(grid: PosteriorGrid, observations: ObservationSet, *, calibration=None,
                         forward=None) -> tuple[RouteReason, str] | None:
    """The CORE-001 rule on a grid: its smallest chi-square over admissible nodes, an upper bound on the minimum.

    Given the calibration and forward evaluator that bind the grid to its evidence, the leverage test runs too
    (R-03). A grid whose fit cannot be tested where the information is -- no curvature at its best node -- is
    passed over: a grid claim is SUPPORTED or absent, so the check that decides it has to be as strong as the
    local route's. Only the reasons in ``MISFIT_REASONS`` pass a grid over, which is exactly the behaviour
    before the rule grew a second test: GOODNESS_OF_FIT_UNDERPOWERED says the noise model was untestable, not
    that the residuals contradict it, and a grid has no DOWNGRADED claim to carry it with.
    """
    ll = np.asarray(grid.log_likelihood, dtype=np.float64)
    usable = np.asarray(grid.admissible_mask, dtype=bool) & np.isfinite(ll)
    chi_square = -2.0 * (ll - _log_normalizer(observations))
    row = int(np.arange(len(ll))[usable][int(np.argmin(chi_square[usable]))])
    chi_minimum = max(float(chi_square[row]), 0.0)
    n, p = len(observations.observations), len(grid.parameter_names)
    statistic, cumulants = math.nan, ()
    if calibration is not None and forward is not None:
        measured = _grid_leverage(grid, row, observations, calibration, forward)
        if measured is None:
            return (RouteReason.GOODNESS_OF_FIT_NOT_MEASURABLE,
                    "no curvature could be built at the grid's best node, so the goodness of fit cannot be tested "
                    "where the information is; a grid claim is SUPPORTED or absent")
        statistic, cumulants = measured
    refusals, downgrades = _goodness_of_fit(chi_minimum, n, p, statistic, cumulants)
    for reason in sorted((refusals | downgrades) & MISFIT_REASONS, key=lambda r: r.value):
        return reason, (f"chi-square {chi_minimum:.6g} on {n - p} degrees of freedom at the grid's best node, and a "
                        f"leverage-weighted {statistic:.6g} against a null mean of "
                        f"{cumulants[0] if cumulants else float('nan'):.6g}: the declared noise does not explain the "
                        f"residuals where the information is, and a grid claim cannot be downgraded")
    return None


def grid_containment(grid: PosteriorGrid, calibration) -> tuple[RouteReason, str] | None:
    """The rebuilt grid's containment rule on a supplied tensor grid (CORE-002).

    A face at a declared bound (known only from a calibration) that the posterior reaches is still a refusal here:
    showing that the truncated moments have converged needs refinement, which only a rebuild can do.
    """
    points = np.asarray(grid.points, dtype=np.float64)
    ll = np.asarray(grid.log_likelihood, dtype=np.float64)
    usable = np.asarray(grid.admissible_mask, dtype=bool) & np.isfinite(ll)
    peak = float(np.max(ll[usable]))
    bounds = None
    if isinstance(calibration, CalibrationResult):
        bounds = [(q.bounds.lower.magnitude_in(q.unit), q.bounds.upper.magnitude_in(q.unit))
                  for q in calibration.spec.parameters.parameters]
    for i, name in enumerate(grid.parameter_names):
        axis = np.unique(points[:, i])
        for side, edge in (("low", axis[0]), ("high", axis[-1])):
            face = (points[:, i] == edge) & usable
            face_peak = float(np.max(ll[face])) if np.any(face) else -math.inf
            if peak - face_peak >= EDGE_LOG_LIKELIHOOD_DROP:
                continue
            at_bound = bounds is not None and abs(edge - bounds[i][side == "high"]) <= 1e-12 * (abs(bounds[i][1] - bounds[i][0]) + 1.0)
            detail = (f"posterior density on the {side} face of {name!r} (at {edge:.6g}) is within ln 1e6 of the grid's peak, "
                      f"so the grid's box, not the data, bounds this posterior")
            if at_bound:
                detail += ("; the face is a declared bound, and a supplied grid cannot show that moments truncated there have "
                           "converged -- supply a rebuild policy")
            return RouteReason.GRID_DOES_NOT_CONTAIN_POSTERIOR, detail
    return None


def grid_prior_uniformity(grid: PosteriorGrid, calibration) -> tuple[RouteReason, str] | None:
    """CORE-010: equal node mass is the declared prior only on axes uniform in each parameter's inference coordinate.

    ``gaussian_grid_posterior`` gives every node the same prior mass, so node density IS the prior density: a log-spaced
    axis of an IDENTITY parameter is a prior uniform in its logarithm, and a clustered axis is a prior heaped where the
    nodes are. Transforms come from the calibration; without one every axis must be uniform in its natural coordinate.
    """
    from ..inference.parameters import ParameterTransform

    transforms = {}
    if isinstance(calibration, CalibrationResult):
        transforms = {q.name: q.transform for q in calibration.spec.parameters.parameters}
    points = np.asarray(grid.points, dtype=np.float64)
    for i, name in enumerate(grid.parameter_names):
        transform = transforms.get(name, ParameterTransform.IDENTITY)
        axis = np.unique(points[:, i])
        if axis.size < 3:
            continue
        if transform is ParameterTransform.LOG:
            if np.any(axis <= 0.0):
                return (RouteReason.GRID_PRIOR_NOT_UNIFORM_IN_INFERENCE_COORDINATES,
                        f"{name!r} is declared LOG but the grid has non-positive nodes")
            axis = np.log(axis)
        steps = np.diff(axis)
        mean = float(np.mean(steps))
        worst = float(np.max(np.abs(steps - mean)))
        if not worst <= UNIFORM_STEP_RELATIVE_TOLERANCE * mean:
            return (RouteReason.GRID_PRIOR_NOT_UNIFORM_IN_INFERENCE_COORDINATES,
                    f"the nodes of {name!r} are not evenly spaced in its {transform.value} coordinate (largest step deviation "
                    f"{worst / mean:.3g} of the mean step); every node carries equal prior mass, so their density would be an "
                    f"undeclared prior on {name!r}")
    return None


def supplied_grid_problem(grid: PosteriorGrid, calibration, observations: ObservationSet, forward) -> tuple[RouteReason, str] | None:
    """Binding (raises), then goodness of fit, then containment: why a resolved supplied grid may not stand, or None."""
    require_grid_is_this_evidence(grid, calibration, observations, forward)
    return (grid_prior_uniformity(grid, calibration)
            or grid_goodness_of_fit(grid, observations, calibration=calibration, forward=forward)
            or grid_containment(grid, calibration))
