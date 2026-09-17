"""The hybrid router: a resolved grid, a supported local Gaussian, a verified regrid, a downgraded local Gaussian,
or a refusal -- deterministically, in that order, with every route it tried recorded.

The grid route is the repaired V1 grid route and nothing looser: a grid is used only when the frozen
``assess_identifiability`` accepts it (tensor lattice, ESS, the ESS-and-spacing rule, lattice aliasing, a usable
curvature fit). The router has no way to accept a grid V1 refuses.

Resolution is not enough (scientific core audit 2026-09-16). A supplied grid must also be the request's evidence --
bound by content to the observations and forward model, not by dataset id (CORE-005) -- the declared noise must
explain its residuals (CORE-001), and its box must contain the posterior (CORE-002). A local route whose residuals
the declared noise does not explain is never rebuilt into a grid, and a rebuilt grid whose posterior spans both
declared bounds of an axis is not used: the width it reports there is the bounds', not the data's.
"""

from __future__ import annotations

import hashlib
import math
import secrets
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
from ._records import (
    decode_matrix, decode_vector, digest_of, encode_matrix, encode_vector, require_schema, require_valid_covariance,
)
from ..scientific.results.immutable import freeze
from ._grid_evidence import (
    EDGE_LOG_LIKELIHOOD_DROP, admissibility_cut_axes, grid_admissibility_truncation, grid_containment,
    SPOT_CHECK_INADMISSIBLE_ROWS, SPOT_CHECK_WEIGHTED_ROWS,
    grid_goodness_of_fit, grid_is_this_evidence, grid_mode_resolution, grid_prior_uniformity,
    supplied_grid_problem,
)
from .identifiability import (
    RoutedIdentifiability, _grid_axes_digest, _grid_report_problems, _report_differences, assess_routed_identifiability,
)
from .local_gaussian import (
    MISFIT_REASONS, LocalGaussianPosterior, MultistartPolicy, _posterior_record_problems, local_gaussian_posterior,
)
from .predictive import (
    RoutedPredictiveUncertainty, _grid_record, _grid_route_claim, _prediction_domain_reasons,
    _require_weights_follow_likelihood, grid_digest,
    grid_predictive_uncertainty, linearized_predictive_uq, _table_reasons,
)
from .sensitivity import SUPPLIED_PREDICTION_AGREEMENT_SD, evaluate, to_natural
from .vocabulary import (
    GRID_ROUTE_MAXIMUM_PARAMETERS, ApproximationClass, HybridUQError, RouteClaim, RouteDecision, RouteReason, RouteRefusedError,
    claim_for,
)

HYBRID_UQ_RESULT_SCHEMA = "hybrid_uq.hybrid_uq_result/1"

#: Reasons after which a grid is not rebuilt: without a usable covariance there is nothing to design it from.
_STRUCTURAL = frozenset({
    RouteReason.CALIBRATION_NOT_CONVERGED, RouteReason.FORWARD_INADMISSIBLE_NEAR_ESTIMATE,
    RouteReason.NO_RESIDUAL_DEGREES_OF_FREEDOM, RouteReason.STRUCTURALLY_UNIDENTIFIABLE,
    RouteReason.NUMERICALLY_SINGULAR_JACOBIAN,
})

#: The uniqueness words that say no adequate search stands behind a single mode: nothing looked, or what
#: looked was below the minimum search (R-01, re-audit 2026-09-16). The word is read rather than the reason
#: set because an early refusal records NOT_ASSESSED with no downgrade reason at all, and because the word is
#: re-derived from the recorded starts by ``_multistart_verdict`` -- it cannot disagree with them.
UNRESOLVED_UNIQUENESS = frozenset({"NOT_ASSESSED", "MULTISTART_INCOMPLETE", "MULTISTART_BELOW_MINIMUM_SEARCH"})

#: How an unresolved uniqueness word is reported when it passes a grid route over.
_UNRESOLVED_REASON = {
    "NOT_ASSESSED": RouteReason.GLOBAL_UNIQUENESS_NOT_ASSESSED,
    "MULTISTART_INCOMPLETE": RouteReason.MULTISTART_INCOMPLETE,
    "MULTISTART_BELOW_MINIMUM_SEARCH": RouteReason.MULTISTART_INCOMPLETE,
}


def _bound_tolerance(lower, upper):
    """The float64 round-trip allowance for "this coordinate IS that declared bound".

    The same expression ``grid_containment`` and ``_rebuild_grid`` already use, so a face that counts as a
    declared bound there counts as one here: one rule, one number.
    """
    return 1.0e-12 * (np.abs(np.asarray(upper, dtype=float) - np.asarray(lower, dtype=float)) + 1.0)


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
            if not all(math.isfinite(v) for v in self.mean):
                raise HybridUQError(f"decision {decision.value} reports a mean with a non-finite entry: {list(self.mean)}")
            object.__setattr__(self, "covariance", tuple(tuple(float(v) for v in row) for row in self.covariance))
            require_valid_covariance(self.covariance, len(self.mean))
        if decision is RouteDecision.LOCAL_GAUSSIAN and (self.local_posterior is None or self.local_posterior.claim is not claim):
            raise HybridUQError("a LOCAL_GAUSSIAN decision carries the local posterior whose claim it reports")
        if decision in (RouteDecision.GRID_AS_SUPPLIED, RouteDecision.GRID_REBUILT_FROM_LOCAL_COVARIANCE) and claim is not RouteClaim.SUPPORTED:
            raise HybridUQError("a grid route is used only when V1 accepts the grid, so it is SUPPORTED")
        if self.coordinates not in ("natural", "inference", "none"):
            raise HybridUQError("coordinates is natural, inference or none")
        object.__setattr__(self, "parameter_names", tuple(self.parameter_names))
        # Frozen at construction (audit HUQ-13): a validated record's nested mappings cannot be edited in place.
        object.__setattr__(self, "considered", tuple(freeze(dict(c)) for c in self.considered))
        if self.grid_summary is not None:
            object.__setattr__(self, "grid_summary", freeze(dict(self.grid_summary)))
        self._require_one_truth()

    def _require_one_truth(self) -> None:
        """Refuse a record whose top-level numbers and the records it carries say different things.

        A serialized result holds its parameter names, mean, covariance and claim twice: at the top level, and in
        the local posterior and identifiability records it carries. If they could disagree, a reader would have
        two scientific answers in one record and no way to know which one the router produced.

        The digests a record carries are integrity-only: anyone can recompute them. So the claims are also re-derived
        from the numbers (audit HUQ-09): a local result's identifiability is recomputed from its covariance under the
        router's thresholds; a grid result's identifiability is held to its covariance and to the frozen rule; the
        route diagnostics re-derive their own reasons; the local posterior's point, bounds and covariance reproduce
        its recorded bound distances. What no field carries -- the Jacobian, the grid itself -- cannot be re-derived.
        """
        decision, names, local, ident = self.decision, self.parameter_names, self.local_posterior, self.identifiability
        if local is not None and not isinstance(local, LocalGaussianPosterior):
            raise HybridUQError("local_posterior must be a LocalGaussianPosterior")
        if ident is not None and not isinstance(ident, RoutedIdentifiability):
            raise HybridUQError("identifiability must be a RoutedIdentifiability")
        problems = []
        if local is not None:
            problems.extend(_posterior_record_problems(local))
        if decision is RouteDecision.LOCAL_GAUSSIAN:
            # R-25 (I-14 part E): THE LABEL IS WHAT TURNS THE RE-DERIVATIONS OFF.
            #
            # `_posterior_record_problems` re-derives the bound distances only for the DECLARED
            # parameterization; for any other label it returns after checking that the estimate equals the
            # point, because a mapped posterior's diagnostics describe its PARENT and are deliberately not
            # tied to its own covariance. So renaming a record to 'linear_map:forged' and dividing its
            # covariance by 1e4 read back SUPPORTED with sd [0.00027151, 0.00045993] -- the whole defence
            # switched off by a string. The router builds declared posteriors and nothing else, so a routed
            # record carrying another label was not produced by it. `reparameterized` stays a caller's tool
            # and a mapped posterior stays usable on its own.
            if local is not None and local.parameterization != "declared":
                problems.append(
                    f"a LOCAL_GAUSSIAN routed result carries a posterior in the declared parameterization; "
                    f"this one is {local.parameterization!r}, for which the bound distances, the near-bound "
                    f"set and every other re-derivation are not performed")
            if self.coordinates != "inference":
                problems.append("coordinates are not 'inference'")
            if names != local.parameter_names:
                problems.append("parameter names differ from the local posterior's")
            if self.mean != local.inference_point:
                problems.append("mean differs from the local posterior's inference point")
            if self.covariance != local.covariance:
                problems.append("covariance differs from the local posterior's")
            if ident is None:
                problems.append("no identifiability for a route that reports numbers")
            else:
                if ident.approximation_class is not ApproximationClass.LOCAL_GAUSSIAN_APPROXIMATION:
                    problems.append("identifiability was read from another approximation")
                if ident.parameterization_digest != local.parameterization_digest:
                    problems.append("identifiability names another parameterization")
                if ident.route_claim is not self.claim:
                    problems.append("identifiability carries another claim")
                if local.covariance is not None and not problems:
                    # re-derived from the carried covariance under the router's thresholds (audit HUQ-09)
                    problems.extend(_report_differences(ident.report, assess_routed_identifiability(local).report))
        elif decision is RouteDecision.REFUSED:
            if self.coordinates != "none":
                problems.append("a refused routing has no coordinates")
            if local is not None and (local.claim is not RouteClaim.REFUSED or names != local.parameter_names):
                problems.append("a refused routing carries a local posterior that is not the refused one it names")
        else:
            if self.coordinates != "natural":
                problems.append("grid coordinates are not 'natural'")
            summary = self.grid_summary or {}
            if set(summary) != _GRID_SUMMARY_KEYS:
                problems.append(f"grid_summary holds {sorted(summary)}, not exactly {sorted(_GRID_SUMMARY_KEYS)}")
            if summary.get("route") != decision.value:
                problems.append("grid_summary names another route")
            points, dataset = summary.get("points"), summary.get("dataset_id")
            if isinstance(points, bool) or not isinstance(points, int) or points < 1 or not isinstance(dataset, str):
                problems.append("grid_summary commits to a positive integer point count and a dataset id")
                points, dataset = None, None
            moments = _grid_moments_digest(decision.value, names, summary.get("grid_digest"), self.mean, self.covariance,
                                           dataset, points)
            if summary.get("moments_digest") != moments:
                problems.append("mean and covariance are not the moments grid_summary commits to for its grid")
            if ident is None:
                problems.append("no identifiability for a route that reports numbers")
            else:
                if ident.approximation_class is not ApproximationClass.POSTERIOR_GRID:
                    problems.append("identifiability was read from another approximation")
                if ident.parameterization_digest != _grid_axes_digest(names):
                    problems.append("identifiability names another parameterization")
                if ident.route_claim is not RouteClaim.SUPPORTED:
                    problems.append("identifiability carries another claim")
                if tuple(ident.report.parameter_names) == names:
                    problems.extend(_grid_report_problems(ident.report, self.mean, self.covariance))
            if decision is RouteDecision.GRID_AS_SUPPLIED and local is not None:
                problems.append("a supplied grid was used, so no local posterior was built")
            if decision is RouteDecision.GRID_REBUILT_FROM_LOCAL_COVARIANCE and (local is None or names != local.parameter_names):
                problems.append("a rebuilt grid carries the local posterior it was designed from, over the same parameters")
            elif decision is RouteDecision.GRID_REBUILT_FROM_LOCAL_COVARIANCE:
                # R-01 (re-audit 2026-09-16): the read rule is the write rule. The router no longer designs a box
                # from a local posterior whose uniqueness search is unresolved, because the box centres are the
                # estimate plus the modes that search found, and an unresolved search found none. A record that
                # says otherwise was not produced by the router, and its SUPPORTED grid claim would be exactly the
                # downgrade the local posterior it carries recorded, laundered away.
                word = str(local.diagnostics.uniqueness)
                if word in UNRESOLVED_UNIQUENESS:
                    problems.append(f"a rebuilt grid was designed from a local posterior whose uniqueness is {word}: "
                                    f"the box it names covers the modes a search found, and that search found none")
            grid = self.grid
            if grid is not None:
                if tuple(grid.parameter_names) != names:
                    problems.append("parameter names differ from the grid's")
                if not np.array_equal(np.asarray(self.mean), np.asarray(grid.mean)):
                    problems.append("mean differs from the grid's")
                if not np.array_equal(np.asarray(self.covariance), np.asarray(grid.covariance)):
                    problems.append("covariance differs from the grid's")
                if summary.get("grid_digest") != grid_digest(grid):
                    problems.append("grid_summary names another grid")
                if summary.get("dataset_id") != grid.dataset_id or summary.get("points") != int(len(grid.weights)):
                    problems.append("grid_summary names another dataset or point count than its grid")
        if ident is not None and tuple(ident.report.parameter_names) != names:
            problems.append("identifiability describes other parameters")
        if problems:
            raise HybridUQError(f"the routed result contradicts itself: {problems}")

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


#: The closed key set of a grid result's summary (audit HUQ-12): nothing uncommitted can ride along in it.
_GRID_SUMMARY_KEYS = frozenset({"route", "dataset_id", "points", "grid_digest", "moments_digest"})


def _grid_moments_digest(route: str, parameter_names, grid_identity, mean, covariance, dataset_id, points) -> str:
    """The commitment binding a grid result's reported moments, dataset and size to the grid its summary names.

    ``from_dict`` cannot restore the grid itself (it is data-plane), so without this a serialized grid record could
    keep its ``grid_digest`` and carry any other mean and valid covariance. The digest is over the canonical route,
    names, grid digest, dataset id, point count, mean and covariance, exactly as the record serializes them. It is
    integrity-only -- anyone can recompute it -- so the record's numbers are also re-derived where they can be.
    """
    return digest_of({"route": str(route), "parameter_names": [str(n) for n in parameter_names],
                      "grid_digest": grid_identity, "dataset_id": dataset_id, "points": points,
                      "mean": encode_vector(float(v) for v in mean),
                      "covariance": encode_matrix(tuple(tuple(float(v) for v in row) for row in covariance))})


def _grid_summary(grid: PosteriorGrid, how: str) -> dict[str, Any]:
    identity = grid_digest(grid)
    points = int(len(grid.weights))
    return {"route": how, "dataset_id": grid.dataset_id, "points": points, "grid_digest": identity,
            "moments_digest": _grid_moments_digest(how, grid.parameter_names, identity, grid.mean, grid.covariance,
                                                   grid.dataset_id, points)}


#: A rebuilt grid must contain its posterior: on every face that is not a declared bound, the largest
#: HOW FAR A GAUSSIAN OF THE FITTED SD REACHES BEFORE IT LEAVES THE ln 1e6 BAND (I-06, R-11).
#:
#: A Gaussian of standard deviation s has a log-density exactly
#: ``EDGE_LOG_LIKELIHOOD_DROP`` below its peak at ``sqrt(2 ln 1e6)`` sd. So if
#: the fitted local Gaussian were the truth, a profile would already have left
#: the band by this distance; one still INSIDE the band further out than this is
#: wider than the local fit claims in that direction. Written as the expression
#: and not as the literal 5.2565, so it cannot drift from the band it is about.
_GAUSSIAN_BAND_SD = math.sqrt(2.0 * EDGE_LOG_LIKELIHOOD_DROP)

#: log-likelihood must sit at least EDGE_LOG_LIKELIHOOD_DROP below the grid's maximum (density below 1e-6 of the
#: peak). The frozen V1 checks verify resolution, not containment, so the router checks containment itself -- on
#: supplied grids too, since CORE-002 (see _grid_evidence).
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


#: Interior rows of a rebuilt table re-evaluated through the forward model, chosen from a digest of the table itself,
#: on top of its two extreme corners, the node nearest the estimate and the table's own best-fitting node.
#:
#: NO LONGER THE COUNT, AND NO LONGER THE SEED (I-07, R-19). The audit says it in one sentence -- "a rebuild
#: `table_builder` can do the same to `_require_table_agrees_with_forward`" -- and the mechanism is the one it
#: measured on the supplied-grid path: the seed is a digest of the table's own values and mask, so a builder
#: keeps the fixed rows honest, answers with a sharpened model everywhere else, and nudges one far-tail value
#: until the drawn rows miss it. Two attempts were enough there. Kept because it is the constant a reader of
#: the old behaviour will look for.
_SPOT_CHECK_INTERIOR_ROWS = 4


def _require_table_agrees_with_forward(table, natural, mesh, z0, observations, forward, *, nonce=None):
    """Refuse a rebuilt table whose values are not the forward model's at the nodes it is spot-checked on (HUQ-05).

    ``_require_requested_grid`` binds a table's coordinates to the request; nothing bound its VALUES, so a builder
    answering with another model's predictions at the requested coordinates was certified. Deterministic nodes are
    re-evaluated through the forward evaluator the route was given: the two extreme corners, the node nearest the
    estimate, the table's best-fitting node, and interior nodes chosen from a digest of the table's own bytes. An
    admitted node must be admitted by the forward evaluator and agree with it to ``SUPPLIED_PREDICTION_AGREEMENT_SD``
    observation sigmas; a node the forward evaluator admits must not be refused by the table.
    """
    if forward is None:
        raise HybridUQError("a rebuilt grid is verified against the forward evaluator; none was supplied")
    predictions, _columns = table.select_observations(observations)
    observed, sigma = observations.numeric_vectors()
    keys = observations.keys
    units = tuple(o.value.units for o in observations.observations)
    references = tuple(o.value for o in observations.observations)
    mask = np.asarray(table.admissible_mask, dtype=bool)
    n = len(natural)
    span = np.where(np.ptp(mesh, axis=0) > 0.0, np.ptp(mesh, axis=0), 1.0)
    rows = {0, n - 1, int(np.argmin(np.sum(((mesh - z0) / span) ** 2, axis=1)))}
    # THE ROWS ARE DRAWN FROM A SEED THE BUILDER DOES NOT CONTROL (I-07, R-19).
    #
    # `SPOT_CHECK_WEIGHTED_ROWS` rows by the posterior weight the table's own chi-square implies -- because
    # a builder who moves a reported moment must move that weight -- and
    # `SPOT_CHECK_INADMISSIBLE_ROWS` uniformly from the rows it refused, which carry no weight at all and
    # are how a builder deletes mass without touching a value.
    weight = np.zeros(n)
    if np.any(mask):
        chi = np.sum(((predictions - observed[None, :]) / sigma[None, :]) ** 2, axis=1)
        rows.add(int(np.argmin(np.where(mask, chi, np.inf))))
        usable = mask & np.isfinite(chi)
        if np.any(usable):
            weight = np.where(usable, np.exp(-0.5 * (chi - np.min(chi[usable]))), 0.0)
    stream = np.random.default_rng(np.frombuffer(
        hashlib.sha256(nonce if nonce is not None else secrets.token_bytes(32)).digest(), dtype=np.uint32))
    total = float(np.sum(weight))
    if total > 0.0:
        pool = np.flatnonzero(weight > 0.0)
        draw = min(int(SPOT_CHECK_WEIGHTED_ROWS), pool.size)
        rows.update(int(r) for r in stream.choice(pool, size=draw, replace=False, p=weight[pool] / total))
    refused = np.flatnonzero(~mask)
    if refused.size:
        draw = min(int(SPOT_CHECK_INADMISSIBLE_ROWS), refused.size)
        rows.update(int(r) for r in stream.choice(refused, size=draw, replace=False))
    for row in sorted(rows):
        value = evaluate(forward, natural[row], keys, units, references)
        if value is None:
            if mask[row]:
                raise HybridUQError(f"the rebuilt table admits row {row} ({list(natural[row])}), which the forward evaluator "
                                    f"refuses: the table is not this forward model's")
            continue
        if not mask[row]:
            raise HybridUQError(f"the rebuilt table refuses row {row} ({list(natural[row])}), which the forward evaluator "
                                f"admits: the table is not this forward model's")
        gap = float(np.max(np.abs(predictions[row] - value) / sigma))
        if not gap <= SUPPLIED_PREDICTION_AGREEMENT_SD:
            raise HybridUQError(f"the rebuilt table's values differ from the forward evaluator's by {gap:.3g} sigma at row {row} "
                                f"({list(natural[row])}; at most {SUPPLIED_PREDICTION_AGREEMENT_SD:g}): a table from another "
                                f"model is not certified as this posterior")


def _build(local, policy, observations, forward, lo, hi, nodes):
    p = len(lo)
    axes = [np.linspace(lo[i], hi[i], int(nodes[i])) for i in range(p)]
    mesh = np.array(np.meshgrid(*axes, indexing="ij")).reshape(p, -1).T
    natural = [tuple(float(v) for v in to_natural(row, local.inference_transforms)) for row in mesh]
    table = policy.table_builder(natural)
    if not isinstance(table, AdmittedForwardTable):
        raise HybridUQError("table_builder must return an AdmittedForwardTable")
    _require_requested_grid(table, local.parameter_names, natural)
    _require_table_agrees_with_forward(table, natural, mesh, np.asarray(local.inference_point), observations, forward)
    rebuilt = gaussian_grid_posterior(table, observations)
    usable = rebuilt.admissible_mask & np.isfinite(rebuilt.log_likelihood)
    ll = np.where(usable, rebuilt.log_likelihood, -np.inf).reshape(tuple(int(n) for n in nodes))
    return rebuilt, ll


def _rebuild_grid(local, policy, observations, forward, refinement=0):
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
        rebuilt, ll = _build(local, policy, observations, forward, lo, hi, nodes)
        peak = float(np.max(ll))
        grew = False
        truncated = []
        # R-17: the forward model's admissible region ending inside the box is the same hard edge as a declared
        # bound. Kept in its own list so the bound-domination rule below never fires on the model's own domain.
        cut = admissibility_cut_axes(ll, ll.shape)
        # The peak's own coordinate on each axis, for the per-side domination
        # test below. Read off the lattice, so it is quantised to the node
        # spacing -- far finer than the 5.2565 sd comparison it feeds.
        peak_index = np.unravel_index(int(np.argmax(ll)), ll.shape)
        one_sided = []
        for i in range(p):
            width = hi[i] - lo[i]
            steps = max(int(nodes[i]) - 1, 1)
            peak_at = lo[i] + float(peak_index[i]) * (hi[i] - lo[i]) / steps
            for side, index, bound in (("low", 0, lower[i]), ("high", -1, upper[i])):
                edge = lo[i] if side == "low" else hi[i]
                face = float(np.max(np.take(ll, index, axis=i)))
                reaches = peak - face < EDGE_LOG_LIKELIHOOD_DROP
                if abs(edge - bound) <= tolerance[i]:
                    if reaches:
                        truncated.append(i)
                        # R-11: ONE reached declared bound is enough, when the
                        # posterior stays inside the band all the way out to it
                        # over more than a Gaussian of the fitted sd could
                        # reach. The both-sides rule below let this through, and
                        # the sd reported then belonged to wherever the bound
                        # was declared: 1.743, 2.037 and 3.473 for the same data
                        # with the bound at 20, 40 and 80.
                        #
                        # A posterior that DECAYS toward its bound -- a peak
                        # sitting at one, say -- has a distance of about zero
                        # here, nowhere near the band distance, so it falls
                        # through to the halving loop exactly as before. That is
                        # what makes this a diagnosis and not a blanket refusal.
                        if math.isfinite(sd[i]) and sd[i] > 0.0:
                            reach = abs(bound - peak_at) / float(sd[i])
                            if reach > _GAUSSIAN_BAND_SD:
                                one_sided.append((local.parameter_names[i], side, reach))
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

    # CORE-002: density within ln 1e6 of the peak on BOTH declared bounds of an axis means the data rule out no part of
    # the declared range there; the moments along it describe the bounds, and no refinement changes that.
    dominated = sorted({local.parameter_names[i] for i in truncated if truncated.count(i) >= 2})
    if dominated:
        return None, (RouteReason.GRID_POSTERIOR_BOUND_DOMINATED,
                      f"the posterior reaches both declared bounds of {dominated} within ln 1e6 of its peak: the width "
                      f"reported there would be the declared range's, not the data's")
    # R-11 (I-06): the same finding one side at a time, named as one side. Kept
    # SEPARATE from the rule above, and reported after it, because the two call
    # for different remedies: both sides dominated means the declared range is
    # too narrow to say anything, one side means the DATA constrain only one
    # direction and a wider box makes it worse. A refusal that did not
    # distinguish them is what produced the 1.743 / 2.037 / 3.473 sequence.
    if one_sided:
        worst = max(one_sided, key=lambda item: item[2])
        named = sorted({(name, side) for name, side, _reach in one_sided})
        return None, (RouteReason.GRID_POSTERIOR_BOUND_DOMINATED,
                      f"the posterior runs to the {worst[1]} declared bound of {worst[0]!r} while staying within "
                      f"ln 1e6 of its peak over {worst[2]:.3g} local sd, more than the {_GAUSSIAN_BAND_SD:.4g} sd a "
                      f"Gaussian of that sd would reach: the width reported there is the bound's, not the data's "
                      f"(dominated side(s): {named})")

    halvings = 0
    truncated = sorted(set(truncated) | set(cut))
    while truncated:
        finer = nodes.copy()
        for i in truncated:
            finer[i] = 2 * (finer[i] - 1) + 1
        if float(np.prod(finer.astype(float))) > budget:
            return None, (RouteReason.GRID_REBUILD_OVER_BUDGET,
                          f"a declared bound truncates the posterior and the moments had not converged within the budget "
                          f"of {budget} points after {halvings} halving(s)")
        candidate, _ = _build(local, policy, observations, forward, lo, hi, finer)
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
                     f"{halvings} truncation halving(s) on axes {truncated} (admissibility cuts {cut}), "
                     f"{int(refinement)} refinement(s)")


def _declared_bounds(calibration) -> list[tuple[float, float]] | None:
    """Each parameter's declared bounds in its own natural unit, or None without a calibration to read them from."""
    if not isinstance(calibration, CalibrationResult):
        return None
    return [(float(q.bounds.lower.magnitude_in(q.unit)), float(q.bounds.upper.magnitude_in(q.unit)))
            for q in calibration.spec.parameters.parameters]


def _grid_spans_the_declared_bounds(grid: PosteriorGrid, calibration) -> bool:
    """Whether the grid's own box IS the declared box on every axis (R-06).

    The declared bounds are the whole parameter space the request admits, so a grid that spans them has no
    outside for a mode to hide in, and the router's containment check has already shown the posterior does not
    reach its faces. Whether a mode INSIDE such a box is resolved is a grid-resolution question, not this one.
    """
    bounds = _declared_bounds(calibration)
    if bounds is None or len(bounds) != len(grid.parameter_names):
        return False
    points = np.asarray(grid.points, dtype=np.float64)
    for i, (lower, upper) in enumerate(bounds):
        tolerance = float(_bound_tolerance(lower, upper))
        axis = points[:, i]
        if not (float(np.min(axis)) <= lower + tolerance and float(np.max(axis)) >= upper - tolerance):
            return False
    return True


def _grid_uniqueness_basis(grid: PosteriorGrid, calibration, local, searched: bool) -> tuple[RouteReason, str] | str:
    """R-06: why a supplied grid may not stand on uniqueness, or the basis on which it may.

    Either the grid spans the declared bounds, or a uniqueness search at or above the minimum ran and every
    separated mode it found lies inside the grid's box. A grid route's claim is SUPPORTED or absent, so a grid
    with neither is passed over rather than downgraded.
    """
    if _grid_spans_the_declared_bounds(grid, calibration):
        return "uniqueness: the grid spans the declared bounds of every axis, so no mode lies outside it"
    if not searched or local is None:
        return (RouteReason.GRID_UNIQUENESS_NOT_ASSESSED,
                "the grid is narrower than the declared bounds and no uniqueness search stands behind it, so nothing "
                "shows the posterior has no mode outside its box; a grid claim cannot be downgraded")
    word = str(local.diagnostics.uniqueness)
    if word in UNRESOLVED_UNIQUENESS:
        return (RouteReason.GRID_UNIQUENESS_NOT_ASSESSED,
                f"the grid is narrower than the declared bounds and the uniqueness search behind it is {word}, so "
                f"nothing shows the posterior has no mode outside its box")
    points = np.asarray(grid.points, dtype=np.float64)
    low, high = np.min(points, axis=0), np.max(points, axis=0)
    tolerance = _bound_tolerance(low, high)
    for mode in getattr(local, "_modes", ()):  # inference coordinates, as the local route records them
        natural = np.asarray(to_natural(np.asarray(mode, dtype=float), local.inference_transforms), dtype=float)
        outside = [i for i in range(len(natural))
                   if natural[i] < low[i] - tolerance[i] or natural[i] > high[i] + tolerance[i]]
        if outside:
            names = [str(grid.parameter_names[i]) for i in outside]
            return (RouteReason.GRID_MISSES_A_FOUND_MODE,
                    f"the uniqueness search found a mode at {[float(v) for v in natural]} which lies outside the grid's "
                    f"box on {names}: the grid describes one mode of a posterior that has more than one")
    return f"uniqueness: {word}, over {len(local.diagnostics.multistart)} start(s), every found mode inside the box"


def _require_grid_bound_to_request(grid: PosteriorGrid, calibration, observations) -> None:
    """Refuse a supplied grid that is not a posterior for the request it is routed with (audit HUQ-06).

    A grid over other parameters, or computed from other data, would otherwise be certified GRID_AS_SUPPLIED for a
    calibration and observations it never saw. Where the request names its parameters (a calibration) or its data
    (observations), the grid must be over exactly those parameters, in that order, and from that dataset.
    """
    if isinstance(calibration, CalibrationResult):
        requested = tuple(calibration.spec.parameters.names)
        if tuple(grid.parameter_names) != requested:
            raise HybridUQError(f"the supplied grid is over parameters {list(grid.parameter_names)}; the request calibrates "
                                f"{list(requested)}: a grid for other parameters is not this request's posterior")
    if isinstance(observations, ObservationSet) and str(grid.dataset_id) != str(observations.dataset_id):
        raise HybridUQError(f"the supplied grid was computed from dataset {grid.dataset_id!r}; the request's observations are "
                            f"{observations.dataset_id!r}: a grid from other data is not this request's posterior")


def route_uncertainty(
    *,
    grid: PosteriorGrid | None = None,
    calibration: CalibrationResult | None = None,
    observations: ObservationSet | None = None,
    forward: ForwardEvaluator | None = None,
    multistart: MultistartPolicy | None = None,
    rebuild: GridRebuildPolicy | None = None,
    maximum_grid_parameters: int = GRID_ROUTE_MAXIMUM_PARAMETERS,
    canonical_uniqueness_search: bool = True,
) -> HybridUQResult:
    """Route an uncertainty request. See docs/CORE_V2_API_DESIGN.md section 3.6 for the rule.

    ``canonical_uniqueness_search`` (R-01, R-06): a grid route's claim is SUPPORTED or absent, so a grid needs
    a basis for the single mode it describes. When a grid route is in play -- a grid is supplied, or a
    ``GridRebuildPolicy`` is given -- and the caller passed no ``multistart``, the router runs the canonical
    :class:`MultistartPolicy` for its local route rather than recording that nobody looked. Pass ``False`` to
    keep the older behaviour, which can only pass a grid over and never accept one. With neither a grid nor a
    rebuild policy, ``multistart=None`` keeps its exact meaning and no search is run: there the DOWNGRADED
    local claim already says what is not known, and a search would only cost evaluations.
    """
    if int(maximum_grid_parameters) > GRID_ROUTE_MAXIMUM_PARAMETERS or int(maximum_grid_parameters) < 1:
        raise HybridUQError(f"maximum_grid_parameters must lie in [1, {GRID_ROUTE_MAXIMUM_PARAMETERS}], the validated grid range")
    if rebuild is not None and not isinstance(rebuild, GridRebuildPolicy):
        raise HybridUQError("rebuild must be a GridRebuildPolicy")
    considered: list[dict[str, str]] = []
    if isinstance(grid, PosteriorGrid):
        _require_grid_bound_to_request(grid, calibration, observations)

    # The search that stands behind whatever grid claim this call may make (R-01, R-06).
    local_inputs = calibration is not None and observations is not None and forward is not None
    a_grid_route_is_in_play = grid is not None or rebuild is not None
    searching = multistart
    if searching is None and bool(canonical_uniqueness_search) and a_grid_route_is_in_play and local_inputs:
        searching = MultistartPolicy()
    # The local route is built at most once, and step 1 may need it before step 2 reports it.
    _local_route: list = []

    def local_route():
        """``(posterior, refusal)``: the local route with ``searching``, computed once. One of the two is None."""
        if not _local_route:
            if not local_inputs:
                _local_route.append((None, None))
            else:
                try:
                    _local_route.append((local_gaussian_posterior(calibration, observations, forward,
                                                                  multistart=searching), None))
                except RouteRefusedError as exc:
                    _local_route.append((None, exc))
        return _local_route[0]

    # 1. the grid as supplied
    if grid is None:
        considered.append({"route": "GRID_AS_SUPPLIED", "outcome": "SKIPPED", "reason": RouteReason.GRID_NOT_SUPPLIED.value})
    elif not isinstance(grid, PosteriorGrid):
        raise HybridUQError("grid must be a PosteriorGrid")
    elif len(grid.parameter_names) > int(maximum_grid_parameters):
        considered.append({"route": "GRID_AS_SUPPLIED", "outcome": "PASSED_OVER",
                           "reason": RouteReason.GRID_BEYOND_VALIDATED_DIMENSION.value})
    else:
        _require_weights_follow_likelihood(grid)
        # CORE-005: a grid is a posterior for a request only when it can be shown to be that request's evidence, and that
        # needs the observations and the forward model its likelihood is re-evaluated from.
        bound = isinstance(observations, ObservationSet) and forward is not None
        # A grid that is not this request's evidence is a fact about the GRID, so it passes the grid route
        # over and the request goes on to the local route. This used to raise from here, outside any try, so
        # a table off by a solver's own convergence aborted a request the local route answers SUPPORTED
        # (I-07, R-30).
        binding = grid_is_this_evidence(grid, calibration, observations, forward) if bound else None
        try:
            identifiability = assess_routed_identifiability(grid)
        except GridResolutionError as exc:
            considered.append({"route": "GRID_AS_SUPPLIED", "outcome": "REFUSED_BY_V1",
                               "reason": RouteReason.GRID_UNRESOLVED.value, "detail": str(exc)[:400]})
        else:
            if not bound:
                problem = (RouteReason.GRID_NOT_BOUND_TO_EVIDENCE,
                           "a supplied grid is used only with the observations and forward model it is checked against")
            else:
                # CORE-010, CORE-001 and CORE-002: equal node mass is the declared prior, the declared noise explains the
                # residuals, and the box holds the posterior
                problem = (binding
                           or grid_prior_uniformity(grid, calibration)
                           or grid_goodness_of_fit(grid, observations, calibration=calibration, forward=forward)
                           or grid_containment(grid, calibration)
                           # R-17 then R-05: a cut inside the box, then every mode in the band on its own nodes
                           or grid_admissibility_truncation(grid)
                           or grid_mode_resolution(grid))
            if problem is None:
                # R-06: last, because it is the only check that may cost a uniqueness search, and a grid that
                # spans its declared bounds needs none. Nothing before this point has run the search the
                # caller handed in, so a grid over one of two equal modes read SUPPORTED.
                basis = _grid_uniqueness_basis(grid, calibration, *local_route()[:1], searched=searching is not None)
                problem = None if isinstance(basis, str) else basis
            else:
                basis = ""
            if problem is not None:
                considered.append({"route": "GRID_AS_SUPPLIED", "outcome": "PASSED_OVER", "reason": problem[0].value,
                                   "detail": problem[1][:400]})
            else:
                considered.append({"route": "GRID_AS_SUPPLIED", "outcome": "USED", "reason": "", "detail": basis[:400]})
                return HybridUQResult(
                    decision=RouteDecision.GRID_AS_SUPPLIED, approximation_class=ApproximationClass.POSTERIOR_GRID,
                    claim=RouteClaim.SUPPORTED, parameter_names=grid.parameter_names, coordinates="natural",
                    mean=tuple(grid.mean), covariance=tuple(map(tuple, grid.covariance)), local_posterior=None,
                    grid_summary=_grid_summary(grid, "GRID_AS_SUPPLIED"), considered=tuple(considered),
                    identifiability=identifiability, grid=grid)

    # 2. the local Gaussian route
    local = None
    if not local_inputs:
        considered.append({"route": "LOCAL_GAUSSIAN", "outcome": "SKIPPED", "reason": RouteReason.LOCAL_INPUTS_NOT_SUPPLIED.value})
    else:
        local, refusal = local_route()
        if refusal is not None:
            # The route refused without a posterior record (a derivative that did not stabilize): recorded, and
            # nothing is rebuilt from it, because there is no covariance to design a grid from.
            considered.append({"route": "LOCAL_GAUSSIAN", "outcome": RouteClaim.REFUSED.value,
                               "reason": "the local route refused before it had a posterior", "detail": str(refusal)[:400]})
        else:
            reasons = ",".join(r.value for r in local.reasons)
            if local.claim is RouteClaim.SUPPORTED:
                considered.append({"route": "LOCAL_GAUSSIAN", "outcome": "USED", "reason": ""})
                return _local_result(local, considered)
            considered.append({"route": "LOCAL_GAUSSIAN", "outcome": local.claim.value, "reason": reasons})

    # 3. a grid rebuilt from the local covariance, then verified by the frozen V1 checks
    if rebuild is not None and local is not None:
        p = len(local.parameter_names)
        misfit = sorted(set(local.reasons) & MISFIT_REASONS, key=lambda r: r.value)
        if misfit:
            # CORE-001: a grid claim is SUPPORTED or absent, so a grid cannot carry a misfit the local route recorded
            considered.append({"route": "GRID_REBUILT_FROM_LOCAL_COVARIANCE", "outcome": "PASSED_OVER",
                               "reason": misfit[0].value,
                               "detail": "the declared noise does not explain the residuals; no grid is built past that"})
        elif p > int(maximum_grid_parameters):
            considered.append({"route": "GRID_REBUILT_FROM_LOCAL_COVARIANCE", "outcome": "PASSED_OVER",
                               "reason": RouteReason.GRID_BEYOND_VALIDATED_DIMENSION.value})
        elif set(local.diagnostics.refusals) & _STRUCTURAL:
            considered.append({"route": "GRID_REBUILT_FROM_LOCAL_COVARIANCE", "outcome": "PASSED_OVER",
                               "reason": "no usable local covariance to design a grid from"})
        elif str(local.diagnostics.uniqueness) in UNRESOLVED_UNIQUENESS:
            # R-01: the same rule as the misfit above, for the same reason. The box is the estimate plus the modes
            # a search found; an unresolved search found none, so the grid covers one basin and says SUPPORTED,
            # which is exactly the DOWNGRADED caveat the local route recorded, laundered away. A found mode is not
            # this case: it becomes a design centre, and the rebuilt box covers it.
            word = str(local.diagnostics.uniqueness)
            considered.append({"route": "GRID_REBUILT_FROM_LOCAL_COVARIANCE", "outcome": "PASSED_OVER",
                               "reason": _UNRESOLVED_REASON[word].value,
                               "detail": f"the uniqueness search behind this local route is {word}, so the box would cover "
                                         f"one basin and report SUPPORTED; a grid claim cannot be downgraded"})
        else:
            for refinement in range(_MAXIMUM_REFINEMENTS + 1):
                rebuilt, detail = _rebuild_grid(local, rebuild, observations, forward, refinement)
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
                # R-05: V1 checks one quadratic about the global argmax, so a second mode in the box is aliased
                # away. The next refinement quadruples the aliasing target, which is the lever that fixes it.
                unresolved = grid_mode_resolution(rebuilt)
                if unresolved is not None:
                    considered.append({"route": "GRID_REBUILT_FROM_LOCAL_COVARIANCE", "outcome": "PASSED_OVER",
                                       "reason": unresolved[0].value,
                                       "detail": f"refinement {refinement}: {unresolved[1][:360]}"})
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
    if local is not None:
        names = local.parameter_names
    elif grid is not None:
        names = grid.parameter_names
    else:
        names = calibration.spec.parameters.names if isinstance(calibration, CalibrationResult) else ()
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
    calibration_observations: ObservationSet | None = None,
    observations: ObservationSet | None = None,
    forward: ForwardEvaluator | None = None,
    calibration: CalibrationResult | None = None,
) -> tuple[RoutedPredictiveUncertainty, ...]:
    """Predictive uncertainty through whichever route the result used. A refused result has none.

    ``calibration_observations`` (CORE-006) are the observations the result was calibrated on; their declared conditions
    bound the range a prediction may claim. Without them every prediction is DOWNGRADED ``PREDICTION_DOMAIN_NOT_DECLARED``.

    ``observations`` and ``forward`` (I-14, R-27 / the audit's finding 24) are the EVIDENCE a grid result's
    grid is held to. This function used to re-apply only the V1 resolution check and say so in a comment --
    "the evidence checks cannot be [re-applied], since the result does not carry the evidence" -- and then
    predict anyway, so a grid computed from other data, which ``grid_predictive_uncertainty`` refuses on the
    same evidence, predicted SUPPORTED once wrapped in a hand-built result: mean 2.4745 against an honest
    1.9745. There are two honest answers and this is both of them. Given the evidence the grid checks are
    re-run; without it every prediction is DOWNGRADED ``GRID_NOT_BOUND_TO_EVIDENCE``, which is the reason
    the supplied-grid route already uses for exactly this. ``calibration`` is passed through to the same
    checks: without it the goodness of fit falls back to the pooled test, which is what the numbers then
    support.
    """
    if not isinstance(result, HybridUQResult):
        raise HybridUQError("routed_predictive_uncertainty takes a HybridUQResult")
    if result.decision is RouteDecision.REFUSED:
        raise RouteRefusedError("the routing was REFUSED; no route established a posterior to predict from")
    if result.decision is RouteDecision.LOCAL_GAUSSIAN:
        if predict is None:
            raise HybridUQError("a LOCAL_GAUSSIAN result predicts through a forward evaluator: pass predict")
        return linearized_predictive_uq(result.local_posterior, predict, specs, confidence_level=confidence_level,
                                        calibration_observations=calibration_observations)
    if result.grid is None:
        raise HybridUQError("this grid result was read back from a record; the grid itself is data-plane and was not serialized")
    if predictive_table is None or twin is None or model is None or source_ref is None:
        raise HybridUQError("a grid result predicts through a table over result.grid.points: pass predictive_table, twin, model, source_ref")
    # The router held this grid to its evidence, its goodness of fit and its containment before it built the result
    # (CORE-001/-002/-005), and _require_one_truth binds result.grid to the grid_summary digest the result carries. The
    # resolution judgement is re-applied; the evidence checks cannot be, since the result does not carry the evidence.
    _grid_route_claim(result.grid)
    # I-14 (R-27, finding 24). The checks are the ones `supplied_grid_problem` applies, run here on the
    # result's own grid: a claim about a posterior is a claim about the evidence it came from, and a record
    # cannot carry that evidence. A finding RAISES, because a caller who handed over the evidence asked for
    # it to be checked; its absence DOWNGRADES, because a claim not bound to evidence is still a number.
    unbound: set[RouteReason] = set()
    if isinstance(observations, ObservationSet) and forward is not None:
        finding = supplied_grid_problem(result.grid, calibration, observations, forward)
        if finding is not None:
            raise RouteRefusedError(
                f"this grid result is not bound to the evidence handed over: {finding[0].value} -- {finding[1]}")
    else:
        unbound.add(RouteReason.GRID_NOT_BOUND_TO_EVIDENCE)
    out = []
    for spec in specs:
        # R-23 (I-13 part B): `predict` was accepted here and used only on the LOCAL path, so a grid result
        # read its numbers out of the table and never compared them with the model passed beside it.
        found = _prediction_domain_reasons(spec, calibration_observations) | _table_reasons(
            result.grid, predictive_table, spec, predict) | unbound
        reasons = tuple(sorted(found, key=lambda r: r.value))
        out.append(_grid_record(result.grid, predictive_table, spec, claim_for(reasons), reasons, twin=twin, model=model,
                                source_ref=source_ref, confidence_level=confidence_level))
    return tuple(out)
