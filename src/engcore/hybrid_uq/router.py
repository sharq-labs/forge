"""The hybrid router: a resolved grid, a supported local Gaussian, a verified regrid, a downgraded local Gaussian,
or a refusal -- deterministically, in that order, with every route it tried recorded.

The grid route is the repaired V1 grid route and nothing looser: a grid is used only when the frozen
``assess_identifiability`` accepts it (tensor lattice, ESS, the ESS-and-spacing rule, lattice aliasing, a usable
curvature fit). The router has no way to accept a grid V1 refuses.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from ..inference.calibration import (
    CalibrationResult, ForwardEvaluator, GridResolutionError, _ALIASING_NUMBER_MINIMUM, _minimum_aliasing_number,
    assess_identifiability,
)
from ..inference.grid import AdmittedForwardTable, ObservationSet, PosteriorGrid, gaussian_grid_posterior
from ..scientific.ir.problem import ModelReference
from ..scientific.twins import TwinReference
from ..uq.predictive import PredictiveObservableSpec
from ._records import decode_matrix, decode_vector, digest_of, encode_matrix, encode_vector, require_schema
from .identifiability import RoutedIdentifiability, assess_routed_identifiability
from .local_gaussian import LocalGaussianPosterior, MultistartPolicy, local_gaussian_posterior
from .predictive import RoutedPredictiveUncertainty, grid_digest, grid_predictive_uncertainty, linearized_predictive_uq
from .sensitivity import to_natural
from .vocabulary import (
    GRID_ROUTE_MAXIMUM_PARAMETERS, ApproximationClass, HybridUQError, RouteClaim, RouteDecision, RouteReason, RouteRefusedError,
)

HYBRID_UQ_RESULT_SCHEMA = "hybrid_uq.hybrid_uq_result/1"

#: Reasons after which a grid is not rebuilt: without a usable covariance there is nothing to design it from.
_STRUCTURAL = frozenset({
    RouteReason.CALIBRATION_NOT_CONVERGED, RouteReason.FORWARD_INADMISSIBLE_NEAR_ESTIMATE,
    RouteReason.NO_RESIDUAL_DEGREES_OF_FREEDOM, RouteReason.STRUCTURALLY_UNIDENTIFIABLE,
    RouteReason.NUMERICALLY_SINGULAR_JACOBIAN,
})


@dataclass(frozen=True)
class GridRebuildPolicy:
    """How the router may build a verification grid from a local covariance. Export-only: it holds a callable."""

    table_builder: Callable[[Sequence[Sequence[float]]], AdmittedForwardTable]
    sigma_span: float = 6.0
    maximum_points: int = 250_000
    aliasing_margin: float = 4.0

    def __post_init__(self) -> None:
        if not callable(self.table_builder):
            raise HybridUQError("table_builder must be callable")
        if not float(self.sigma_span) > 0.0 or int(self.maximum_points) < 8 or not float(self.aliasing_margin) >= 1.0:
            raise HybridUQError("sigma_span > 0, maximum_points >= 8 and aliasing_margin >= 1 are required")

    def to_dict(self) -> dict[str, Any]:
        return {"sigma_span": float(self.sigma_span), "maximum_points": int(self.maximum_points),
                "aliasing_margin": float(self.aliasing_margin), "table_builder": "caller-supplied callable (not serialized)"}


@dataclass(frozen=True)
class HybridUQResult:
    """What the router decided, the numbers of the route it chose, and every route it considered."""

    decision: RouteDecision
    approximation_class: ApproximationClass | None
    claim: RouteClaim
    parameter_names: tuple[str, ...]
    coordinates: str
    mean: tuple[float, ...] | None
    covariance: tuple[tuple[float, ...], ...] | None
    local_posterior: LocalGaussianPosterior | None
    grid_summary: Mapping[str, Any] | None
    considered: tuple[Mapping[str, str], ...]
    identifiability: RoutedIdentifiability | None
    grid: PosteriorGrid | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        decision = RouteDecision(self.decision)
        claim = RouteClaim(self.claim)
        object.__setattr__(self, "decision", decision)
        object.__setattr__(self, "claim", claim)
        cls = None if self.approximation_class is None else ApproximationClass(self.approximation_class)
        object.__setattr__(self, "approximation_class", cls)
        expected = {RouteDecision.GRID_AS_SUPPLIED: ApproximationClass.POSTERIOR_GRID,
                    RouteDecision.GRID_REBUILT_FROM_LOCAL_COVARIANCE: ApproximationClass.POSTERIOR_GRID,
                    RouteDecision.LOCAL_GAUSSIAN: ApproximationClass.LOCAL_GAUSSIAN_APPROXIMATION,
                    RouteDecision.REFUSED: None}[decision]
        if cls is not expected:
            raise HybridUQError(f"decision {decision.value} is produced by {expected}, not {cls}")
        if decision is RouteDecision.REFUSED:
            if claim is not RouteClaim.REFUSED or self.mean is not None or self.covariance is not None or self.identifiability is not None:
                raise HybridUQError("a refused routing emits no mean, covariance or identifiability")
        else:
            if claim is RouteClaim.REFUSED or self.mean is None or self.covariance is None:
                raise HybridUQError(f"decision {decision.value} carries a mean and a covariance and is not REFUSED")
            object.__setattr__(self, "mean", tuple(float(v) for v in self.mean))
            object.__setattr__(self, "covariance", tuple(tuple(float(v) for v in row) for row in self.covariance))
        if decision is RouteDecision.LOCAL_GAUSSIAN and (self.local_posterior is None or self.local_posterior.claim is not claim):
            raise HybridUQError("a LOCAL_GAUSSIAN decision carries the local posterior whose claim it reports")
        if decision in (RouteDecision.GRID_AS_SUPPLIED, RouteDecision.GRID_REBUILT_FROM_LOCAL_COVARIANCE) and claim is not RouteClaim.SUPPORTED:
            raise HybridUQError("a grid route is used only when V1 accepts the grid, so it is SUPPORTED")
        if self.coordinates not in ("natural", "inference", "none"):
            raise HybridUQError("coordinates is natural, inference or none")
        object.__setattr__(self, "parameter_names", tuple(self.parameter_names))
        object.__setattr__(self, "considered", tuple(dict(c) for c in self.considered))

    @property
    def exact_posterior(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": HYBRID_UQ_RESULT_SCHEMA, "decision": self.decision.value,
            "approximation_class": None if self.approximation_class is None else self.approximation_class.value,
            "exact_posterior": False, "claim": self.claim.value, "parameter_names": list(self.parameter_names),
            "coordinates": self.coordinates, "mean": None if self.mean is None else encode_vector(self.mean),
            "covariance": encode_matrix(self.covariance),
            "local_posterior": None if self.local_posterior is None else self.local_posterior.to_dict(),
            "grid_summary": None if self.grid_summary is None else dict(self.grid_summary),
            "considered": [dict(c) for c in self.considered],
            "identifiability": None if self.identifiability is None else self.identifiability.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HybridUQResult":
        require_schema(payload, HYBRID_UQ_RESULT_SCHEMA)
        if payload.get("exact_posterior") is not False:
            raise HybridUQError("a routed result claiming an exact posterior is refused")
        return cls(
            decision=RouteDecision(payload["decision"]),
            approximation_class=None if payload["approximation_class"] is None else ApproximationClass(payload["approximation_class"]),
            claim=RouteClaim(payload["claim"]), parameter_names=tuple(payload["parameter_names"]), coordinates=payload["coordinates"],
            mean=None if payload["mean"] is None else decode_vector(payload["mean"]), covariance=decode_matrix(payload["covariance"]),
            local_posterior=None if payload["local_posterior"] is None else LocalGaussianPosterior.from_dict(payload["local_posterior"]),
            grid_summary=payload["grid_summary"], considered=tuple(payload["considered"]),
            identifiability=None if payload["identifiability"] is None else RoutedIdentifiability.from_dict(payload["identifiability"]),
        )

    @property
    def digest(self) -> str:
        payload = self.to_dict()
        if payload["local_posterior"] is not None:
            payload["local_posterior"] = self.local_posterior.digest
        if payload["identifiability"] is not None:
            payload["identifiability"] = self.identifiability.digest
        return digest_of(payload)


def _grid_summary(grid: PosteriorGrid, how: str) -> dict[str, Any]:
    return {"route": how, "dataset_id": grid.dataset_id, "points": int(len(grid.weights)), "grid_digest": grid_digest(grid)}


#: A rebuilt grid must contain its posterior: on every face that is not a declared bound, the largest
#: log-likelihood must sit at least this far below the grid's maximum (density below 1e-6 of the peak).
#: The frozen V1 checks verify resolution, not containment, so the router checks containment itself.
EDGE_LOG_LIKELIHOOD_DROP = math.log(1.0e6)
_MAXIMUM_BOX_EXPANSIONS = 6
#: When V1 refuses a rebuilt grid, the aliasing target is raised 4x (steps halved) and the grid rebuilt, at most
#: this many times and always within the point budget.
_MAXIMUM_REFINEMENTS = 3
#: Where a DECLARED bound cuts the posterior off, the density is not smooth at the edge and the V1 aliasing
#: argument does not bound the discretization error there. The step on every such axis is halved (nested) until
#: the grid's means and standard deviations move by less than this many posterior sd.
TRUNCATION_CONVERGENCE_SD = 0.05
_MAXIMUM_TRUNCATION_HALVINGS = 5


def _node_counts(cov, lo, hi, target, budget):
    """Per-axis node counts over [lo, hi] whose predicted lattice aliasing number clears ``target``."""
    span = hi - lo
    nodes = np.full(len(lo), 11, dtype=np.int64)
    for _ in range(8):
        steps = span / (nodes - 1)
        shortfall = _minimum_aliasing_number(cov / np.outer(steps, steps), target)
        if shortfall is None:
            break
        scale = math.sqrt(target / max(shortfall, 1e-300)) * 1.05
        nodes = np.maximum(nodes, np.ceil((nodes - 1) * scale).astype(np.int64) + 1)
        if float(np.prod(nodes.astype(float))) > budget:
            return None, f"{int(np.prod(nodes.astype(float)))} points exceed the budget of {budget}"
    else:
        return None, "the design did not clear the aliasing target"
    if float(np.prod(nodes.astype(float))) > budget:
        return None, f"{int(np.prod(nodes.astype(float)))} points exceed the budget of {budget}"
    return nodes, None


def _require_requested_grid(table, names, natural):
    """Refuse a table that is not the grid that was asked for, row for row.

    Its log-likelihood is reshaped onto the requested node layout and its faces are read by index, so a table
    for other coordinates, the same coordinates in another row order, or the same numbers under other
    parameter names would be checked for containment and certified as a grid it is not. The builder is handed
    float64 coordinates and a table stores float64, so the comparison is exact: no sort, no tolerance.
    """
    if tuple(table.parameter_names) != tuple(names):
        raise HybridUQError(f"table_builder returned a table over parameters {list(table.parameter_names)}; "
                            f"the rebuilt grid was requested over {list(names)}, in that order")
    requested = np.asarray(natural, dtype=np.float64).reshape(len(natural), len(names))
    if table.points.shape != requested.shape:
        raise HybridUQError(f"table_builder returned {table.points.shape[0]} point(s) of dimension {table.points.shape[1]}; "
                            f"{requested.shape[0]} point(s) of dimension {requested.shape[1]} were requested")
    mismatched = np.flatnonzero(np.any(table.points != requested, axis=1))
    if mismatched.size:
        first = int(mismatched[0])
        raise HybridUQError(f"table_builder returned points that are not the requested grid in the requested order: "
                            f"{mismatched.size} row(s) differ, first at row {first} "
                            f"({table.points[first].tolist()} returned, {requested[first].tolist()} requested)")


def _build(local, policy, observations, lo, hi, nodes):
    p = len(lo)
    axes = [np.linspace(lo[i], hi[i], int(nodes[i])) for i in range(p)]
    mesh = np.array(np.meshgrid(*axes, indexing="ij")).reshape(p, -1).T
    natural = [tuple(float(v) for v in to_natural(row, local.inference_transforms)) for row in mesh]
    table = policy.table_builder(natural)
    if not isinstance(table, AdmittedForwardTable):
        raise HybridUQError("table_builder must return an AdmittedForwardTable")
    _require_requested_grid(table, local.parameter_names, natural)
    rebuilt = gaussian_grid_posterior(table, observations)
    usable = rebuilt.admissible_mask & np.isfinite(rebuilt.log_likelihood)
    ll = np.where(usable, rebuilt.log_likelihood, -np.inf).reshape(tuple(int(n) for n in nodes))
    return rebuilt, ll


def _rebuild_grid(local, policy, observations, refinement=0):
    """Design, build, check containment and truncation convergence. ``(posterior, detail)`` or ``(None, (reason, detail))``.

    The design is the local Gaussian in inference coordinates. The box covers +/-sigma_span sd around the
    estimate and every mode multistart found, clipped to the declared bounds, and grows wherever posterior
    density reaches a face that is not a declared bound. Node counts keep the predicted aliasing number above
    ``aliasing_margin`` times the V1 minimum. Where a declared bound truncates the posterior, steps on that axis
    are halved until the moments converge. Whether the result is RESOLVED is decided afterwards by V1.
    """
    cov = getattr(local, "_design_covariance", None)
    if cov is None:
        return None, (RouteReason.GRID_REBUILD_UNRESOLVED, "no covariance to design a grid from")
    z0 = np.asarray(local.inference_point)
    lower, upper = np.asarray(local.lower_bounds), np.asarray(local.upper_bounds)
    sd = np.sqrt(np.diag(cov))
    centres = np.asarray([z0, *getattr(local, "_modes", ())])
    lo = np.maximum(centres.min(axis=0) - policy.sigma_span * sd, lower)
    hi = np.minimum(centres.max(axis=0) + policy.sigma_span * sd, upper)
    target = float(policy.aliasing_margin) * float(_ALIASING_NUMBER_MINIMUM) * 4.0 ** int(refinement)
    budget = int(policy.maximum_points)
    p = len(z0)
    tolerance = 1e-12 * (np.abs(upper - lower) + 1.0)

    for attempt in range(_MAXIMUM_BOX_EXPANSIONS + 1):
        if np.any(hi - lo <= 0.0):
            return None, (RouteReason.GRID_REBUILD_UNRESOLVED, "a degenerate design box")
        nodes, problem = _node_counts(cov, lo, hi, target, budget)
        if nodes is None:
            return None, (RouteReason.GRID_REBUILD_OVER_BUDGET, problem)
        rebuilt, ll = _build(local, policy, observations, lo, hi, nodes)
        peak = float(np.max(ll))
        grew = False
        truncated = []
        for i in range(p):
            width = hi[i] - lo[i]
            for side, index, bound in (("low", 0, lower[i]), ("high", -1, upper[i])):
                edge = lo[i] if side == "low" else hi[i]
                face = float(np.max(np.take(ll, index, axis=i)))
                reaches = peak - face < EDGE_LOG_LIKELIHOOD_DROP
                if abs(edge - bound) <= tolerance[i]:
                    if reaches:
                        truncated.append(i)
                    continue
                if reaches:
                    if side == "low":
                        lo[i] = max(lo[i] - 0.5 * width, lower[i])
                    else:
                        hi[i] = min(hi[i] + 0.5 * width, upper[i])
                    grew = True
        if not grew:
            break
    else:
        return None, (RouteReason.GRID_REBUILD_UNRESOLVED,
                      f"posterior density still reaches a non-bound face after {_MAXIMUM_BOX_EXPANSIONS} expansions")

    halvings = 0
    truncated = sorted(set(truncated))
    while truncated:
        finer = nodes.copy()
        for i in truncated:
            finer[i] = 2 * (finer[i] - 1) + 1
        if float(np.prod(finer.astype(float))) > budget:
            return None, (RouteReason.GRID_REBUILD_OVER_BUDGET,
                          f"a declared bound truncates the posterior and the moments had not converged within the budget "
                          f"of {budget} points after {halvings} halving(s)")
        candidate, _ = _build(local, policy, observations, lo, hi, finer)
        scale = np.sqrt(np.maximum(np.diag(candidate.covariance), 1e-300))
        moved = max(float(np.max(np.abs(candidate.mean - rebuilt.mean) / scale)),
                    float(np.max(np.abs(np.sqrt(np.diag(candidate.covariance)) - np.sqrt(np.diag(rebuilt.covariance))) / scale)))
        rebuilt, nodes = candidate, finer
        halvings += 1
        if moved < TRUNCATION_CONVERGENCE_SD:
            break
        if halvings >= _MAXIMUM_TRUNCATION_HALVINGS:
            return None, (RouteReason.GRID_REBUILD_UNRESOLVED,
                          f"a declared bound truncates the posterior and its moments still moved {moved:.3g} sd "
                          f"after {halvings} halving(s)")
    return rebuilt, (f"{int(np.prod(nodes.astype(float)))} points, nodes {[int(n) for n in nodes]}, {attempt} box expansion(s), "
                     f"{halvings} truncation halving(s) on axes {truncated}, {int(refinement)} refinement(s)")


def route_uncertainty(
    *,
    grid: PosteriorGrid | None = None,
    calibration: CalibrationResult | None = None,
    observations: ObservationSet | None = None,
    forward: ForwardEvaluator | None = None,
    multistart: MultistartPolicy | None = None,
    rebuild: GridRebuildPolicy | None = None,
    maximum_grid_parameters: int = GRID_ROUTE_MAXIMUM_PARAMETERS,
) -> HybridUQResult:
    """Route an uncertainty request. See docs/CORE_V2_API_DESIGN.md section 3.6 for the rule."""
    if int(maximum_grid_parameters) > GRID_ROUTE_MAXIMUM_PARAMETERS or int(maximum_grid_parameters) < 1:
        raise HybridUQError(f"maximum_grid_parameters must lie in [1, {GRID_ROUTE_MAXIMUM_PARAMETERS}], the validated grid range")
    if rebuild is not None and not isinstance(rebuild, GridRebuildPolicy):
        raise HybridUQError("rebuild must be a GridRebuildPolicy")
    considered: list[dict[str, str]] = []

    # 1. the grid as supplied
    if grid is None:
        considered.append({"route": "GRID_AS_SUPPLIED", "outcome": "SKIPPED", "reason": RouteReason.GRID_NOT_SUPPLIED.value})
    elif not isinstance(grid, PosteriorGrid):
        raise HybridUQError("grid must be a PosteriorGrid")
    elif len(grid.parameter_names) > int(maximum_grid_parameters):
        considered.append({"route": "GRID_AS_SUPPLIED", "outcome": "PASSED_OVER",
                           "reason": RouteReason.GRID_BEYOND_VALIDATED_DIMENSION.value})
    else:
        try:
            identifiability = assess_routed_identifiability(grid)
        except GridResolutionError as exc:
            considered.append({"route": "GRID_AS_SUPPLIED", "outcome": "REFUSED_BY_V1",
                               "reason": RouteReason.GRID_UNRESOLVED.value, "detail": str(exc)[:400]})
        else:
            considered.append({"route": "GRID_AS_SUPPLIED", "outcome": "USED", "reason": ""})
            return HybridUQResult(
                decision=RouteDecision.GRID_AS_SUPPLIED, approximation_class=ApproximationClass.POSTERIOR_GRID,
                claim=RouteClaim.SUPPORTED, parameter_names=grid.parameter_names, coordinates="natural",
                mean=tuple(grid.mean), covariance=tuple(map(tuple, grid.covariance)), local_posterior=None,
                grid_summary=_grid_summary(grid, "GRID_AS_SUPPLIED"), considered=tuple(considered),
                identifiability=identifiability, grid=grid)

    # 2. the local Gaussian route
    local = None
    if calibration is None or observations is None or forward is None:
        considered.append({"route": "LOCAL_GAUSSIAN", "outcome": "SKIPPED", "reason": RouteReason.LOCAL_INPUTS_NOT_SUPPLIED.value})
    else:
        local = local_gaussian_posterior(calibration, observations, forward, multistart=multistart)
        reasons = ",".join(r.value for r in local.reasons)
        if local.claim is RouteClaim.SUPPORTED:
            considered.append({"route": "LOCAL_GAUSSIAN", "outcome": "USED", "reason": ""})
            return _local_result(local, considered)
        considered.append({"route": "LOCAL_GAUSSIAN", "outcome": local.claim.value, "reason": reasons})

    # 3. a grid rebuilt from the local covariance, then verified by the frozen V1 checks
    if rebuild is not None and local is not None:
        p = len(local.parameter_names)
        if p > int(maximum_grid_parameters):
            considered.append({"route": "GRID_REBUILT_FROM_LOCAL_COVARIANCE", "outcome": "PASSED_OVER",
                               "reason": RouteReason.GRID_BEYOND_VALIDATED_DIMENSION.value})
        elif set(local.diagnostics.refusals) & _STRUCTURAL:
            considered.append({"route": "GRID_REBUILT_FROM_LOCAL_COVARIANCE", "outcome": "PASSED_OVER",
                               "reason": "no usable local covariance to design a grid from"})
        else:
            for refinement in range(_MAXIMUM_REFINEMENTS + 1):
                rebuilt, detail = _rebuild_grid(local, rebuild, observations, refinement)
                if rebuilt is None:
                    reason, why = detail
                    considered.append({"route": "GRID_REBUILT_FROM_LOCAL_COVARIANCE", "outcome": "PASSED_OVER",
                                       "reason": reason.value, "detail": why})
                    break
                try:
                    identifiability = assess_routed_identifiability(rebuilt)
                except GridResolutionError as exc:
                    considered.append({"route": "GRID_REBUILT_FROM_LOCAL_COVARIANCE", "outcome": "REFUSED_BY_V1",
                                       "reason": RouteReason.GRID_REBUILD_UNRESOLVED.value,
                                       "detail": f"refinement {refinement}: {str(exc)[:360]}"})
                    continue
                considered.append({"route": "GRID_REBUILT_FROM_LOCAL_COVARIANCE", "outcome": "USED", "reason": "",
                                   "detail": detail})
                return HybridUQResult(
                    decision=RouteDecision.GRID_REBUILT_FROM_LOCAL_COVARIANCE, approximation_class=ApproximationClass.POSTERIOR_GRID,
                    claim=RouteClaim.SUPPORTED, parameter_names=rebuilt.parameter_names, coordinates="natural",
                    mean=tuple(rebuilt.mean), covariance=tuple(map(tuple, rebuilt.covariance)), local_posterior=local,
                    grid_summary=_grid_summary(rebuilt, "GRID_REBUILT_FROM_LOCAL_COVARIANCE"), considered=tuple(considered),
                    identifiability=identifiability, grid=rebuilt)

    # 4. the local Gaussian, downgraded
    if local is not None and local.claim is RouteClaim.DOWNGRADED:
        considered.append({"route": "LOCAL_GAUSSIAN_DOWNGRADED", "outcome": "USED", "reason": ",".join(r.value for r in local.reasons)})
        return _local_result(local, considered)

    # 5. nothing established
    names = local.parameter_names if local is not None else (grid.parameter_names if grid is not None else ())
    return HybridUQResult(decision=RouteDecision.REFUSED, approximation_class=None, claim=RouteClaim.REFUSED, parameter_names=names,
                          coordinates="none", mean=None, covariance=None, local_posterior=local, grid_summary=None,
                          considered=tuple(considered), identifiability=None)


def _local_result(local: LocalGaussianPosterior, considered) -> HybridUQResult:
    return HybridUQResult(
        decision=RouteDecision.LOCAL_GAUSSIAN, approximation_class=ApproximationClass.LOCAL_GAUSSIAN_APPROXIMATION, claim=local.claim,
        parameter_names=local.parameter_names, coordinates="inference", mean=local.inference_point, covariance=local.covariance,
        local_posterior=local, grid_summary=None, considered=tuple(considered),
        identifiability=assess_routed_identifiability(local))


def routed_predictive_uncertainty(
    result: HybridUQResult,
    specs: Sequence[PredictiveObservableSpec],
    *,
    predict: ForwardEvaluator | None = None,
    predictive_table: AdmittedForwardTable | None = None,
    twin: TwinReference | None = None,
    model: ModelReference | None = None,
    source_ref: str | None = None,
    confidence_level: float = 0.95,
) -> tuple[RoutedPredictiveUncertainty, ...]:
    """Predictive uncertainty through whichever route the result used. A refused result has none."""
    if not isinstance(result, HybridUQResult):
        raise HybridUQError("routed_predictive_uncertainty takes a HybridUQResult")
    if result.decision is RouteDecision.REFUSED:
        raise RouteRefusedError("the routing was REFUSED; no route established a posterior to predict from")
    if result.decision is RouteDecision.LOCAL_GAUSSIAN:
        if predict is None:
            raise HybridUQError("a LOCAL_GAUSSIAN result predicts through a forward evaluator: pass predict")
        return linearized_predictive_uq(result.local_posterior, predict, specs, confidence_level=confidence_level)
    if result.grid is None:
        raise HybridUQError("this grid result was read back from a record; the grid itself is data-plane and was not serialized")
    if predictive_table is None or twin is None or model is None or source_ref is None:
        raise HybridUQError("a grid result predicts through a table over result.grid.points: pass predictive_table, twin, model, source_ref")
    return tuple(grid_predictive_uncertainty(result.grid, predictive_table, spec, twin=twin, model=model, source_ref=source_ref,
                                             confidence_level=confidence_level) for spec in specs)
