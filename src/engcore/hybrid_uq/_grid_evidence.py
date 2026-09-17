"""What a grid must show before its moments may stand as a posterior for a request. Private.

Resolution (the frozen V1 checks) says a grid samples its own likelihood finely enough. It does not say that the
likelihood is the request's, that the declared noise explains the data, or that the grid's box holds the posterior.
Each of those failed at the 2026-09-16 audit (CORE-005, CORE-001, CORE-002), and each is checked here, for supplied
grids in the router and for grids a caller hands to ``grid_predictive_uncertainty``.
"""

from __future__ import annotations

import hashlib
import itertools
import math

import numpy as np

from ..inference.calibration import (
    _ALIASING_NUMBER_MINIMUM,
    _FLAT_DIRECTION_PRECISION,
    _FLAT_DIRECTION_RELATIVE_PRECISION,
    _minimum_aliasing_number,
    _tensor_lattice_steps,
    CalibrationResult,
)
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


#: R-05: a quadratic fitted about a mode may not deviate from the node log-likelihoods it was fitted to by more than
#: this, or its covariance certifies nothing. The V1 aliasing bound is declared as an AMPLITUDE:
#: ``_ALIASING_NUMBER_MINIMUM = 2 ln 100`` is the value at which the aliased component's amplitude ``exp(-A / 2)`` is
#: 1 %. Expressed in the log-density the fit is measured in, that same tolerance is ``ln 100`` nats -- the existing
#: constant halved. Measured margins: 0.0 nats on an exactly Gaussian grid, 0.50 on an 11-maximum ridge staircase whose
#: moments are stable to 6 digits, against 8.7 and 17.7 for the audited aliased modes.
MODE_FIT_RESIDUAL_NATS = _ALIASING_NUMBER_MINIMUM / 2.0

#: R-05: the most local maxima this check will fit. A node log-likelihood with more than a thousand local maxima within
#: a factor 1e6 of its peak is not a resolved sampling of a smooth posterior, which is what the reason says; the
#: measured counts on real grids are 1, 2 and 11. It bounds the work at 1024 small least-squares fits.
MODE_FIT_LIMIT = 1024


def _grid_lattice(grid: PosteriorGrid):
    """``(log_likelihood_on_the_lattice, shape, axes)``, or None when the points are not a tensor lattice.

    Inadmissible and non-finite nodes are ``-inf``, as they are everywhere else in this module. The lattice is
    filled by looking each point up on its axes rather than by reshaping, so the row order does not matter.
    """
    points = np.asarray(grid.points, dtype=np.float64)
    values = np.asarray(grid.log_likelihood, dtype=np.float64)
    usable = np.asarray(grid.admissible_mask, dtype=bool) & np.isfinite(values)
    p = points.shape[1]
    axes = [np.unique(points[:, i]) for i in range(p)]
    shape = tuple(int(axis.size) for axis in axes)
    if int(np.prod([float(n) for n in shape])) != values.size or np.unique(points, axis=0).shape[0] != values.size:
        return None
    index = tuple(np.searchsorted(axes[i], points[:, i]) for i in range(p))
    lattice = np.full(shape, -np.inf)
    lattice[index] = np.where(usable, values, -np.inf)
    return lattice, shape, axes


def _grid_modes(grid: PosteriorGrid):
    """``(lattice, shape, modes, axes)``, or None when the points are not a tensor lattice (R-05).

    A mode is an INTERIOR lattice node, admissible and finite, within ``EDGE_LOG_LIKELIHOOD_DROP`` of the peak,
    whose log-likelihood is at least that of every one of its ``3^p - 1`` lattice neighbours. The full stencil
    matters: over the ``2p`` AXIS neighbours alone an exactly Gaussian TILTED ridge staircases into several
    spurious maxima (3 and 4 on ``hybrid_synthetic.affine`` at 41 and 61 nodes per axis), while over the full
    stencil those grids have exactly one.

    Spurious maxima are tolerated by construction: a thin tilted ridge can still staircase when its crest passes
    between nodes, and each staircase node then yields the RIDGE's own curvature, which passes the checks with a
    wide margin. What the scan must not do is MISS a maximum, which is why maximality is non-strict.
    """
    got = _grid_lattice(grid)
    if got is None:
        return None
    lattice, shape, _axes = got
    p = len(shape)
    peak = float(np.max(lattice))
    candidate = np.isfinite(lattice) & (peak - lattice < EDGE_LOG_LIKELIHOOD_DROP)
    for i in range(p):
        if shape[i] < 3:
            return lattice, shape, [], _axes
        face = [slice(None)] * p
        face[i] = 0
        candidate[tuple(face)] = False
        face[i] = shape[i] - 1
        candidate[tuple(face)] = False
    padded = np.pad(lattice, 1, constant_values=-np.inf)
    for offset in itertools.product((-1, 0, 1), repeat=p):
        if not any(offset):
            continue
        window = tuple(slice(1 + offset[i], 1 + offset[i] + shape[i]) for i in range(p))
        candidate &= lattice >= padded[window]
    return lattice, shape, [tuple(int(v) for v in index) for index in zip(*np.nonzero(candidate))], _axes


def _mode_lattice_covariance(lattice, shape, index, axes, steps):
    """``(covariance_in_lattice_units, largest_absolute_residual, radius)`` about one mode; ``(None, inf, None)``.

    A least-squares quadratic in LATTICE units -- node coordinates minus the mode's, divided by the axis steps,
    which is V1's own convention -- over the smallest lattice box whose usable nodes number at least twice the
    quadratic's coefficients, which is V1's own node requirement. Flat and convex directions are floored exactly
    as V1 floors them. The locality is the whole point: V1 fits once about the global argmax over a window of 50
    nats or more, so a second mode in the box pollutes that fit (audit R-05).
    """
    p = len(shape)
    coefficients = (p + 1) * (p + 2) // 2
    needed = 2 * coefficients
    for radius in range(1, int(max(shape))):
        cut = tuple(slice(max(0, index[i] - radius), min(shape[i], index[i] + radius + 1)) for i in range(p))
        values = lattice[cut].reshape(-1)
        keep = np.isfinite(values)
        if int(np.count_nonzero(keep)) < needed:
            continue
        spans = [(np.asarray(axes[i][cut[i]], dtype=np.float64) - float(axes[i][index[i]])) / float(steps[i])
                 for i in range(p)]
        offsets = np.stack(np.meshgrid(*spans, indexing="ij"), axis=-1).reshape(-1, p).astype(np.float64)
        x, y = offsets[keep], values[keep]
        columns = [np.ones(y.size)] + [x[:, i] for i in range(p)]
        columns += [x[:, i] * x[:, j] for i in range(p) for j in range(i, p)]
        design = np.column_stack(columns)
        norms = np.linalg.norm(design, axis=0)
        if not np.all(np.isfinite(design)) or np.any(norms == 0.0):
            continue
        try:
            singular = np.linalg.svd(design / norms, compute_uv=False)
        except np.linalg.LinAlgError:
            continue
        if singular[-1] < 1.0e-8 * singular[0]:
            continue
        solution, *_ = np.linalg.lstsq(design, y, rcond=None)
        residual = float(np.max(np.abs(design @ solution - y)))
        hessian = np.zeros((p, p))
        k = 1 + p
        for i in range(p):
            for j in range(i, p):
                if i == j:
                    hessian[i, i] = 2.0 * solution[k]
                else:
                    hessian[i, j] = hessian[j, i] = solution[k]
                k += 1
        if not np.all(np.isfinite(hessian)):
            continue
        precision, vectors = np.linalg.eigh(-0.5 * (hessian + hessian.T))
        floor = max(_FLAT_DIRECTION_RELATIVE_PRECISION * float(np.max(precision)), _FLAT_DIRECTION_PRECISION)
        precision = np.maximum(precision, floor)
        return (vectors / precision) @ vectors.T, residual, radius
    return None, math.inf, None


def grid_mode_resolution(grid: PosteriorGrid) -> tuple[RouteReason, str] | None:
    """Every mode in the ln 1e6 band resolved on its OWN nodes, or why not (R-05).

    V1 checks the effective sample size, the node count, the lattice and then ONE quadratic about the global
    argmax. Nothing tests how well that quadratic fits, and nothing looks at another local maximum, so a
    posterior with a second mode inside the box passes: the fit pools both modes, its lattice variance comes out
    at 285 to 7e3, and the aliasing check switches itself off. This is the additive V2 check; V1 is unchanged.
    """
    got = _grid_modes(grid)
    if got is None:
        return None
    lattice, shape, modes, axes = got
    if not modes:
        return None
    if len(modes) > MODE_FIT_LIMIT:
        return (RouteReason.GRID_MODE_UNRESOLVED,
                f"the node log-likelihood has {len(modes)} local maxima within ln 1e6 of its peak, more than the "
                f"{MODE_FIT_LIMIT} this check will fit: that is not a resolved sampling of a smooth posterior")
    steps = _tensor_lattice_steps(np.asarray(grid.points, dtype=np.float64))
    if steps is None:
        return None
    peak = float(np.max(lattice))
    for index in modes:
        covariance, residual, _radius = _mode_lattice_covariance(lattice, shape, index, axes, steps)
        drop = peak - float(lattice[index])
        where = f"the local maximum {drop:.3g} nats below the peak at lattice node {list(index)}"
        if covariance is None:
            return (RouteReason.GRID_MODE_UNRESOLVED,
                    f"no curvature could be fitted about {where}: too few usable nodes around it, or a design the "
                    f"lattice cannot fix")
        if residual > MODE_FIT_RESIDUAL_NATS:
            return (RouteReason.GRID_MODE_UNRESOLVED,
                    f"the quadratic fitted about {where} misses its own nodes by {residual:.3g} nats, above the "
                    f"{MODE_FIT_RESIDUAL_NATS:.3g} the aliasing bound's own 1 % amplitude allows, so its curvature "
                    f"certifies nothing")
        aliasing = _minimum_aliasing_number(covariance, _ALIASING_NUMBER_MINIMUM)
        if aliasing is not None:
            return (RouteReason.GRID_MODE_UNRESOLVED,
                    f"{where} has lattice aliasing number {aliasing:.3g}, below {_ALIASING_NUMBER_MINIMUM:.3g}: along "
                    f"an off-axis lattice direction that mode is narrower than the grid can sample, so its mass is "
                    f"aliased however small the axis steps look against the posterior's marginal sd")
    return None


def admissibility_cut_axes(lattice, shape) -> list[int]:
    """The axes on which an admissible node the posterior REACHES has an inadmissible lattice neighbour (R-17).

    ``lattice`` is ``-inf`` off the admissible, finite nodes, so "inadmissible neighbour" is "non-finite
    neighbour". A cut the posterior does not reach truncates nothing its moments depend on, which is why the band
    is the one the containment check already uses.
    """
    peak = float(np.max(lattice))
    if not math.isfinite(peak):
        return []
    reached = np.isfinite(lattice) & (peak - lattice < EDGE_LOG_LIKELIHOOD_DROP)
    gone = ~np.isfinite(lattice)
    found = []
    for i in range(len(shape)):
        if shape[i] < 2:
            continue
        low = [slice(None)] * len(shape)
        high = [slice(None)] * len(shape)
        low[i] = slice(0, shape[i] - 1)
        high[i] = slice(1, shape[i])
        below, above = tuple(low), tuple(high)
        if bool(np.any(reached[below] & gone[above])) or bool(np.any(reached[above] & gone[below])):
            found.append(i)
    return found


def grid_admissibility_truncation(grid: PosteriorGrid) -> tuple[RouteReason, str] | None:
    """A posterior cut off INSIDE the box by the forward model's admissible region, or None (R-17).

    ``grid_containment`` takes each face's peak over ADMISSIBLE nodes only, so a face with no admissible node
    scores -inf and passes: a posterior cut off inside the box never reaches a face at all. The router already
    holds that truncated moments cannot be shown to have converged without refinement, and acts on it at declared
    bounds; this is the same hard edge, and the V1 aliasing argument assumes a smooth density and does not bound
    the O(step) error at a cut.
    """
    got = _grid_lattice(grid)
    if got is None:
        return None
    lattice, shape, _axes = got
    found = admissibility_cut_axes(lattice, shape)
    if not found:
        return None
    return (RouteReason.GRID_CUT_BY_INADMISSIBILITY,
            f"the forward model's admissible region ends inside this grid's box on axis/axes {found}: a node the "
            f"posterior reaches within ln 1e6 of its peak has an inadmissible lattice neighbour there. Growing the box "
            f"cannot fix that, and the moments across the cut have not been shown to converge")


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
            or grid_containment(grid, calibration)
            or grid_admissibility_truncation(grid)
            or grid_mode_resolution(grid))
