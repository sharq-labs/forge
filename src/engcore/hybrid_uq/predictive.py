"""Predictive uncertainty from either route, with parameter and measurement uncertainty kept apart.

LINEARIZED_PREDICTIVE_UQ: mean g(z_hat), parameter variance diag(G Sigma G^T), measurement variance sigma^2,
total = the sum. Exact only when g is affine over the posterior; +/-2 sd probes along every principal axis, every
diagonal between two axes and each prediction's Sigma grad g compare g with its linear extrapolation, in units
of the parameter standard uncertainty, and downgrade when they disagree; a probe that was not evaluated --
outside the bounds, refused, or not run at all because ``check_nonlinearity=False`` -- downgrades too.

POSTERIOR_GRID: the frozen ``posterior_predictive_uq``, grid-resolution refusal included, re-expressed in the
same record. Model discrepancy is estimated by neither: every record names MODEL_DISCREPANCY_NOT_MODELLED.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.stats import norm

from ..inference.calibration import ForwardEvaluator, assess_identifiability
from ..inference.grid import AdmittedForwardTable, PosteriorGrid
from ..scientific.ir.problem import ModelReference
from ..scientific.twins import TwinReference
from ..scientific.units.quantity import Quantity
from ..uq.predictive import PredictiveObservableSpec, posterior_predictive_uq
from ._records import decode_float, digest_of, encode_float, require_schema
from .local_gaussian import (
    LocalGaussianPosterior,
    PROBE_SD,
    _calibrated_condition_points,
    _calibrated_conditions,
    _observation_content_digest,
    _probe_directions,
)
from .sensitivity import DEFAULT_RELATIVE_STEP, RouteRefusedError, central_difference, evaluate, to_natural
from .vocabulary import (
    GRID_ROUTE_MAXIMUM_PARAMETERS, MODEL_DISCREPANCY_NOT_MODELLED, UNCERTAINTY_SOURCES, ApproximationClass, HybridUQError, RouteClaim,
    RouteReason, claim_for,
)

ROUTED_PREDICTIVE_UNCERTAINTY_SCHEMA = "hybrid_uq.routed_predictive_uncertainty/1"
PREDICTIVE_NONLINEARITY_DOWNGRADE = 0.10


def grid_digest(posterior: PosteriorGrid) -> str:
    """Identity of a grid posterior: names, dataset, and the bytes of its points, weights, log-likelihood and mask.

    The log-likelihood and the admissible mask are part of the identity (audit HUQ-04): the frozen resolution checks
    read the log-likelihood while the moments read the weights, so a digest over the weights alone let a refused
    grid keep its identity under a laundered likelihood.
    """
    import hashlib

    h = hashlib.sha256()
    h.update("\x00".join(posterior.parameter_names).encode("utf-8"))
    h.update(b"\x00" + str(posterior.dataset_id).encode("utf-8") + b"\x00")
    h.update(np.ascontiguousarray(posterior.points, dtype="<f8").tobytes())
    h.update(np.ascontiguousarray(posterior.weights, dtype="<f8").tobytes())
    h.update(b"\x00log_likelihood\x00" + np.ascontiguousarray(posterior.log_likelihood, dtype="<f8").tobytes())
    h.update(b"\x00admissible_mask\x00" + np.ascontiguousarray(posterior.admissible_mask, dtype=np.uint8).tobytes())
    return h.hexdigest()


#: A grid's weights must be the normalized likelihood over its admissible, finite nodes to this relative tolerance
#: (plus an absolute floor far below any weight that moves a moment). The frozen construction reproduces them to
#: roundoff; anything else is weights and a likelihood that describe two different posteriors.
GRID_WEIGHT_RELATIVE_TOLERANCE = 1.0e-9
GRID_WEIGHT_ABSOLUTE_TOLERANCE = 1.0e-14


def _require_weights_follow_likelihood(posterior: PosteriorGrid) -> None:
    """Refuse a grid whose weights are not softmax(log_likelihood) over its admissible mask (audit HUQ-04).

    Defence in depth: whatever the grid constructor enforces, a grid whose resolution is judged on one array and
    whose moments are read from another is never routed, predicted from or certified here.
    """
    ll = np.asarray(posterior.log_likelihood, dtype=np.float64)
    mask = np.asarray(posterior.admissible_mask, dtype=bool)
    weights = np.asarray(posterior.weights, dtype=np.float64)
    if ll.shape != weights.shape or mask.shape != weights.shape:
        raise HybridUQError("a posterior grid's weights, log-likelihood and mask must have one entry per point")
    usable = mask & np.isfinite(ll)
    if not np.any(usable):
        raise HybridUQError("a posterior grid with no admissible finite log-likelihood has no posterior")
    expected = np.zeros_like(ll)
    expected[usable] = np.exp(ll[usable] - float(np.max(ll[usable])))
    expected /= float(np.sum(expected))
    gap = np.abs(weights - expected)
    if np.any(gap > GRID_WEIGHT_RELATIVE_TOLERANCE * expected + GRID_WEIGHT_ABSOLUTE_TOLERANCE):
        worst = int(np.argmax(gap - GRID_WEIGHT_RELATIVE_TOLERANCE * expected))
        raise HybridUQError(
            f"the grid's weights are not softmax(log_likelihood) over its admissible mask: at point {worst} the weight is "
            f"{float(weights[worst]):.6g} and its likelihood implies {float(expected[worst]):.6g}; a grid whose resolution "
            f"is judged on one array and whose moments come from another is not a posterior")


def _grid_route_claim(posterior: PosteriorGrid) -> RouteClaim:
    """The claim a grid may carry: the router's own judgement, or a refusal raised (audit HUQ-02).

    The same checks, in the same order, as the router's GRID_AS_SUPPLIED route: the validated dimension, weights
    that follow the likelihood, and the frozen ``assess_identifiability`` (which raises GridResolutionError when the
    repaired V1 resolution checks refuse). A grid the router would not route is not predicted from.
    """
    if len(posterior.parameter_names) > GRID_ROUTE_MAXIMUM_PARAMETERS:
        raise HybridUQError(f"a grid of {len(posterior.parameter_names)} parameters is beyond the validated grid route "
                            f"({GRID_ROUTE_MAXIMUM_PARAMETERS}); it is not predicted from")
    _require_weights_follow_likelihood(posterior)
    assess_identifiability(posterior)
    return RouteClaim.SUPPORTED


def _grid_evidence_judgement(posterior: PosteriorGrid, claim: RouteClaim, observations, forward,
                             calibration) -> tuple[RouteClaim, tuple[RouteReason, ...]]:
    """The claim left once the grid is held to the evidence it describes (scientific core audit 2026-09-16).

    Resolution says nothing about whose likelihood a grid carries (CORE-005), whether the declared noise explains it
    (CORE-001) or whether its box holds the posterior (CORE-002). Given the observations and forward model, the router's
    checks run here: binding raises, and a misfit or an uncontained posterior raises too, since a grid claim cannot be
    downgraded past either. Without them nothing shows the grid is this evidence, and the claim is DOWNGRADED with
    GRID_NOT_BOUND_TO_EVIDENCE.
    """
    from ._grid_evidence import (
        grid_admissibility_truncation,
        grid_containment,
        grid_goodness_of_fit,
        grid_mode_resolution,
        grid_prior_uniformity,
        require_grid_is_this_evidence,
    )

    if (observations is None) != (forward is None):
        raise HybridUQError("a grid is held to its evidence with both the observations and the forward model, or neither")
    if observations is None:
        return RouteClaim.DOWNGRADED, (RouteReason.GRID_NOT_BOUND_TO_EVIDENCE,)
    require_grid_is_this_evidence(posterior, calibration, observations, forward)
    problem = (grid_prior_uniformity(posterior, calibration)
               or grid_goodness_of_fit(posterior, observations, calibration=calibration, forward=forward)
               or grid_containment(posterior, calibration)
               or grid_admissibility_truncation(posterior)
               or grid_mode_resolution(posterior))
    if problem is not None:
        raise HybridUQError(f"{problem[0].value}: {problem[1]}; the router would not route this grid, so it is not predicted from")
    return claim, ()


@dataclass(frozen=True)
class RoutedPredictiveUncertainty:
    """One predicted quantity, its parameter and measurement uncertainty separately, and where it came from."""

    observation_key: str
    unit: str
    approximation_class: ApproximationClass
    mean: float
    parameter_standard_uncertainty: float
    measurement_standard_uncertainty: float | None
    total_standard_uncertainty: float
    parameter_interval: tuple[float, float]
    total_interval: tuple[float, float]
    confidence_level: float
    sources: tuple[str, ...]
    model_discrepancy: str
    posterior_digest: str
    route_claim: RouteClaim
    reasons: tuple[RouteReason, ...]
    predictive_nonlinearity: float | None
    #: CORE-012: the total interval treats measurement errors as independent Gaussian, which no data here can establish.
    measurement_errors_assumed_independent: bool = True

    def __post_init__(self) -> None:
        cls = ApproximationClass(self.approximation_class)
        if cls is ApproximationClass.LOCAL_GAUSSIAN_APPROXIMATION:
            raise HybridUQError("a predictive record is LINEARIZED_PREDICTIVE_UQ or POSTERIOR_GRID, not a parameter approximation")
        object.__setattr__(self, "approximation_class", cls)
        claim = RouteClaim(self.route_claim)
        if claim is RouteClaim.REFUSED:
            raise HybridUQError("a refused route emits no predictive uncertainty")
        object.__setattr__(self, "route_claim", claim)
        reasons = tuple(sorted({RouteReason(r) for r in self.reasons}, key=lambda r: r.value))
        if claim_for(reasons) is not claim:
            raise HybridUQError(f"claim {claim.value} does not follow from reasons {[r.value for r in reasons]}")
        object.__setattr__(self, "reasons", reasons)
        if tuple(self.sources) != UNCERTAINTY_SOURCES:
            raise HybridUQError(f"a predictive record names exactly the sources {UNCERTAINTY_SOURCES}")
        object.__setattr__(self, "sources", tuple(self.sources))
        if self.model_discrepancy != MODEL_DISCREPANCY_NOT_MODELLED:
            raise HybridUQError("model discrepancy is not modelled by either route, and the record must say so")
        param = float(self.parameter_standard_uncertainty)
        meas = None if self.measurement_standard_uncertainty is None else float(self.measurement_standard_uncertainty)
        total = float(self.total_standard_uncertainty)
        if not (param >= 0.0 and math.isfinite(param)) or (meas is not None and not (meas > 0.0 and math.isfinite(meas))):
            raise HybridUQError("standard uncertainties must be finite and non-negative (measurement strictly positive)")
        if cls is ApproximationClass.LINEARIZED_PREDICTIVE_UQ:
            expected = math.sqrt(param ** 2 + (meas ** 2 if meas is not None else 0.0))
            if not math.isclose(total, expected, rel_tol=1e-12, abs_tol=0.0):
                raise HybridUQError("a linearized total is the root-sum-square of parameter and measurement uncertainty")
        elif total + 1e-12 * max(1.0, total) < param:
            raise HybridUQError("a total uncertainty cannot be smaller than its parameter part")
        for label in ("parameter_interval", "total_interval"):
            low, high = (float(v) for v in getattr(self, label))
            if not low <= high:
                raise HybridUQError(f"{label} is inverted")
            object.__setattr__(self, label, (low, high))
        if not 0.0 < float(self.confidence_level) < 1.0:
            raise HybridUQError("confidence_level must lie strictly between 0 and 1")
        self._require_numbers_agree(cls, param, total)

    def _require_numbers_agree(self, cls: ApproximationClass, param: float, total: float) -> None:
        """A predictive record's mean, intervals, uncertainties, nonlinearity and claim state one truth (audit HUQ-12).

        LINEARIZED_PREDICTIVE_UQ intervals ARE mean +/- q sd, so they must be, to roundoff; its claim must follow
        from the nonlinearity it records (an unmeasured one is an incomplete probe, one above the threshold is
        PREDICTIVE_NONLINEAR). A POSTERIOR_GRID interval is a central interval of a distribution with the recorded
        mean and standard deviation, which Cantelli's inequality confines to mean +/- sqrt((1 - t) / t) sd for the
        tail mass t; it records no linearization, so no nonlinearity.
        """
        mean = float(self.mean)
        if not math.isfinite(mean) or not math.isfinite(total):
            raise HybridUQError("a predictive mean and total uncertainty must be finite")
        if not all(math.isfinite(v) for v in self.parameter_interval + self.total_interval):
            raise HybridUQError("predictive intervals must be finite")
        level = float(self.confidence_level)
        nonlinearity = self.predictive_nonlinearity
        if cls is ApproximationClass.LINEARIZED_PREDICTIVE_UQ:
            q = float(norm.ppf(0.5 + level / 2.0))
            for label, sd in (("parameter_interval", param), ("total_interval", total)):
                low, high = getattr(self, label)
                tolerance = 8.0 * float(np.finfo(float).eps) * max(abs(mean), q * sd, abs(low), abs(high))
                if abs(low - (mean - q * sd)) > tolerance or abs(high - (mean + q * sd)) > tolerance:
                    raise HybridUQError(f"a linearized {label} is mean +/- {q:.6g} sd; ({low!r}, {high!r}) is not "
                                        f"{mean!r} +/- {q:.6g} x {sd!r}")
            if nonlinearity is None or math.isnan(float(nonlinearity)):
                if RouteReason.NONLINEARITY_PROBE_INCOMPLETE not in self.reasons:
                    raise HybridUQError("a linearized prediction whose nonlinearity was not measured is NONLINEARITY_PROBE_INCOMPLETE")
            else:
                if float(nonlinearity) < 0.0:
                    raise HybridUQError("a negative predictive nonlinearity")
                if not math.isfinite(float(nonlinearity)):
                    # R-37: NaN is "not measured" and is handled above. An infinity is a measured deviation
                    # with no scale to measure it against, which is a refusal and not a record.
                    raise HybridUQError(
                        "a predictive nonlinearity of infinity is a linearization with no parameter "
                        "uncertainty to scale it against, which a record cannot carry")
                if (float(nonlinearity) > PREDICTIVE_NONLINEARITY_DOWNGRADE) != (RouteReason.PREDICTIVE_NONLINEAR in self.reasons):
                    raise HybridUQError(f"a predictive nonlinearity of {float(nonlinearity):.3g} and reasons "
                                        f"{[r.value for r in self.reasons]} disagree about PREDICTIVE_NONLINEAR")
        else:
            if nonlinearity is not None or RouteReason.PREDICTIVE_NONLINEAR in self.reasons:
                raise HybridUQError("a POSTERIOR_GRID prediction is not linearized and records no nonlinearity")
            tail = (1.0 - level) / 2.0
            k = math.sqrt((1.0 - tail) / tail)
            for label, sd in (("parameter_interval", param), ("total_interval", total)):
                low, high = getattr(self, label)
                reach = k * sd * (1.0 + 1e-6) + 1e-12 * max(abs(mean), 1.0)
                if low < mean - reach or high > mean + reach:
                    raise HybridUQError(f"a {label} ({low!r}, {high!r}) cannot be a central {level:g} interval of a distribution "
                                        f"with mean {mean!r} and standard deviation {sd!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ROUTED_PREDICTIVE_UNCERTAINTY_SCHEMA, "observation_key": self.observation_key, "unit": self.unit,
            "approximation_class": self.approximation_class.value, "exact": False, "mean": encode_float(self.mean),
            "parameter_standard_uncertainty": encode_float(self.parameter_standard_uncertainty),
            "measurement_standard_uncertainty": None if self.measurement_standard_uncertainty is None
            else encode_float(self.measurement_standard_uncertainty),
            "total_standard_uncertainty": encode_float(self.total_standard_uncertainty),
            "parameter_interval": [encode_float(v) for v in self.parameter_interval],
            "total_interval": [encode_float(v) for v in self.total_interval],
            "confidence_level": float(self.confidence_level), "sources": list(self.sources),
            "model_discrepancy": self.model_discrepancy, "posterior_digest": self.posterior_digest,
            "route_claim": self.route_claim.value, "reasons": [r.value for r in self.reasons],
            "predictive_nonlinearity": None if self.predictive_nonlinearity is None else encode_float(self.predictive_nonlinearity),
            "measurement_errors_assumed_independent": bool(self.measurement_errors_assumed_independent),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RoutedPredictiveUncertainty":
        require_schema(payload, ROUTED_PREDICTIVE_UNCERTAINTY_SCHEMA)
        if payload.get("exact") is not False:
            raise HybridUQError("a predictive record claiming to be exact is refused")
        meas = payload["measurement_standard_uncertainty"]
        nonlin = payload["predictive_nonlinearity"]
        return cls(
            observation_key=payload["observation_key"], unit=payload["unit"],
            approximation_class=ApproximationClass(payload["approximation_class"]), mean=decode_float(payload["mean"]),
            parameter_standard_uncertainty=decode_float(payload["parameter_standard_uncertainty"]),
            measurement_standard_uncertainty=None if meas is None else decode_float(meas),
            total_standard_uncertainty=decode_float(payload["total_standard_uncertainty"]),
            parameter_interval=tuple(decode_float(v) for v in payload["parameter_interval"]),
            total_interval=tuple(decode_float(v) for v in payload["total_interval"]),
            confidence_level=float(payload["confidence_level"]), sources=tuple(payload["sources"]),
            model_discrepancy=payload["model_discrepancy"], posterior_digest=payload["posterior_digest"],
            route_claim=RouteClaim(payload["route_claim"]), reasons=tuple(RouteReason(r) for r in payload["reasons"]),
            predictive_nonlinearity=None if nonlin is None else decode_float(nonlin),
            measurement_errors_assumed_independent=bool(payload.get("measurement_errors_assumed_independent", True)),
        )

    @property
    def digest(self) -> str:
        return digest_of(self.to_dict())


#: CORE-006: a prediction condition equal to an end of the calibrated range, to this relative tolerance, is inside it.
PREDICTION_RANGE_RELATIVE_TOLERANCE = 1.0e-9


def _condition_support_residual(rows: "np.ndarray", scales: "np.ndarray", point: "np.ndarray") -> float:
    """How far ``point`` is from the convex hull of ``rows``, as the smallest achievable max scaled residual (R-31).

    The prediction is INSIDE the calibrated domain when its condition vector is a convex combination of the
    conditions the calibration observed. This solves

        minimise t  subject to  -t <= (sum_i lambda_i c_i - c)_j / s_j <= t,  sum_i lambda_i = 1,  lambda >= 0

    and returns ``t``. Zero (to the caller's tolerance) means inside the hull; the value is the distance in
    units of each condition's own observed spread.

    WHY THE HULL AND NOT A DISTANCE. A distance needs a metric and a threshold, and neither would be
    derivable. Hull membership is the exact statement "this operating point lies between operating points the
    calibration observed", and it degenerates correctly: a calibration at one point admits only that point, a
    calibration along a line admits that segment, and a calibration that varied k conditions independently
    admits its box. **At k = 1 it IS the [min, max] interval it replaces**, which is why this rule needs no
    new number and changes nothing about a single-condition study.

    The scaling is for the TOLERANCE only. Hull membership is affine-invariant, so dividing each condition by
    its observed spread cannot change the answer; it only makes one tolerance comparable across conditions in
    different units, which is what the per-condition ``max(|low|, |high|, |x|)`` scaling did before.
    """
    from scipy.optimize import linprog

    scaled_rows = np.asarray(rows, dtype=float) / np.asarray(scales, dtype=float)
    scaled_point = np.asarray(point, dtype=float) / np.asarray(scales, dtype=float)
    n, k = scaled_rows.shape
    # variables: (lambda_1..lambda_n, t); minimise t
    cost = np.zeros(n + 1)
    cost[-1] = 1.0
    #  (A^T lambda - c)_j - t <= 0   and   -(A^T lambda - c)_j - t <= 0
    upper = np.hstack([scaled_rows.T, -np.ones((k, 1))])
    lower = np.hstack([-scaled_rows.T, -np.ones((k, 1))])
    inequality = np.vstack([upper, lower])
    bound = np.hstack([scaled_point, -scaled_point])
    equality = np.zeros((1, n + 1))
    equality[0, :n] = 1.0
    # The solver has to be able to CERTIFY the tolerance the rule declares. HiGHS's default feasibility
    # tolerance is 1e-7, a hundred times coarser than PREDICTION_RANGE_RELATIVE_TOLERANCE, so at the default
    # a departure of 1e-8 of the observed spread returned exactly 0.0 and read inside -- the rule would have
    # been silently a hundred times looser than it says. At 1e-10 the same departure returns 1.0e-8 and the
    # one inside it, 1e-10 of the spread, returns 9.4e-11. Found while running batch 22's guard mutations.
    done = linprog(cost, A_ub=inequality, b_ub=bound, A_eq=equality, b_eq=np.array([1.0]),
                   bounds=[(0.0, None)] * n + [(0.0, None)], method="highs",
                   options={"primal_feasibility_tolerance": 1.0e-10, "dual_feasibility_tolerance": 1.0e-10})
    if not done.success:  # pragma: no cover - an infeasible program would mean the equality cannot be met
        return math.inf
    return float(done.x[-1])


def _calibration_design(calibration_observations, posterior):
    """``(names, rows)``: the condition design a prediction's domain is judged against, or ``None``.

    The caller's ``calibration_observations`` when they are supplied -- already verified against the
    posterior's content digest by the caller -- and the posterior's OWN stored design when they are not. That
    second half is what stops R-12's simplest form: before it, supplying nothing left the gate with nothing to
    compare and it answered PREDICTION_DOMAIN_NOT_DECLARED, so an extrapolation could be reported with a
    caveat instead of being measured. The stored design is the posterior's own record of what it was fitted
    to, not a caller's assertion, so using it can only make the statement more definite.
    """
    if getattr(calibration_observations, "observations", None):
        pairs = _calibrated_conditions(calibration_observations)
        rows = _calibrated_condition_points(calibration_observations)
    else:
        pairs = tuple(getattr(posterior, "calibrated_conditions", ()) or ())
        rows = tuple(getattr(posterior, "calibrated_condition_points", ()) or ())
    if not pairs or not rows:
        return None
    return pairs, np.asarray(rows, dtype=float)


def _prediction_domain_reasons(spec: PredictiveObservableSpec, calibration_observations, posterior=None) -> set:
    """CORE-006: where a prediction sits relative to the conditions its calibration covered, as route reasons.

    DOWNGRADED ``PREDICTION_DOMAIN_NOT_DECLARED`` when nothing can show it -- no calibration design at all, no
    conditions on the prediction, or a prediction that does not declare every condition the calibration does --
    and DOWNGRADED ``PREDICTION_OUTSIDE_CALIBRATED_CONDITIONS`` when the prediction's condition vector is not a
    convex combination of the calibration's.

    TWO THINGS CHANGED HERE, both R-31. The loop was over the PREDICTION's conditions, so a prediction that
    simply left one out was compared on the rest and read SUPPORTED: a prediction at T = 900 K against a
    calibration at T = 300 K was DOWNGRADED and the same prediction with T omitted was SUPPORTED. Every
    condition the calibration declares must now be declared, or nothing shows where the prediction sits --
    which is what PREDICTION_DOMAIN_NOT_DECLARED says, and is not the same as taking the value from the
    calibration, which would be inventing the prediction's operating point.

    And the comparison was per condition, so the region checked was the BOX around the calibration rather
    than the calibration: with observations on a line in (T, load) a prediction inside both marginal ranges
    and 0.707 of the scaled spread off that line passed. It is now the joint support -- see
    ``_condition_support_residual``, which at one condition is the same interval on the same tolerance.
    """
    design = _calibration_design(calibration_observations, posterior)
    if design is None or not spec.conditions:
        return {RouteReason.PREDICTION_DOMAIN_NOT_DECLARED}
    pairs, rows = design
    names = [name for name, _unit in pairs]
    if any(name not in spec.conditions for name in names):
        return {RouteReason.PREDICTION_DOMAIN_NOT_DECLARED}
    if any(name not in names for name in spec.conditions):
        return {RouteReason.PREDICTION_DOMAIN_NOT_DECLARED}
    # The names are settled above, so the only thing left that can fail here is a unit conversion. The
    # lookup is done first and separately: a single `try` around both would have caught a MISSING name as
    # well, which made the explicit check above unobservable -- a guard mutation removing it survived.
    values = [spec.conditions[name] for name, _unit in pairs]
    try:
        point = np.asarray([value.magnitude_in(unit) for value, (_name, unit) in zip(values, pairs)],
                           dtype=float)
    except Exception:  # noqa: BLE001 - a condition in another dimension is not a range for this one
        return {RouteReason.PREDICTION_DOMAIN_NOT_DECLARED}
    spread = rows.max(axis=0) - rows.min(axis=0)
    reference = np.maximum(np.abs(rows).max(axis=0), np.abs(point))
    scales = np.where(spread > 0.0, spread, np.where(reference > 0.0, reference, 1.0))
    residual = _condition_support_residual(rows, scales, point)
    if residual > PREDICTION_RANGE_RELATIVE_TOLERANCE:
        return {RouteReason.PREDICTION_OUTSIDE_CALIBRATED_CONDITIONS}
    return set()


def linearized_predictive_uq(
    posterior: LocalGaussianPosterior,
    predict: ForwardEvaluator,
    specs: Sequence[PredictiveObservableSpec],
    *,
    confidence_level: float = 0.95,
    check_nonlinearity: bool = True,
    calibration_observations=None,
) -> tuple[RoutedPredictiveUncertainty, ...]:
    """Linearized predictive uncertainty from a local Gaussian posterior. Refuses a refused posterior.

    ``calibration_observations`` (CORE-006): the observations the posterior was calibrated on, whose declared conditions
    say which range a prediction may claim. Without them, or without conditions, a prediction is DOWNGRADED.
    """
    if not isinstance(posterior, LocalGaussianPosterior):
        raise HybridUQError("linearized_predictive_uq takes a LocalGaussianPosterior")
    # R-12: a caller who supplies `calibration_observations` is ASSERTING that these are the observations the
    # posterior was calibrated on. That assertion is either true or false; it is not evidence to be weighed,
    # so a false one is refused rather than carried as a caveat -- the same shape as CORE-005's refusal for a
    # grid that is not this request's evidence. Before this, another dataset's observations, the same
    # observations with their conditions rescaled, or a predictor evaluated elsewhere all read SUPPORTED at a
    # prediction of x = 1e4 against a calibration over x in [0, 1].
    if getattr(calibration_observations, "observations", None) and posterior.calibration_content_digest:
        supplied = _observation_content_digest(calibration_observations)
        if supplied != posterior.calibration_content_digest:
            raise HybridUQError(
                f"the calibration_observations supplied are not the ones this posterior was calibrated on "
                f"(content digest {supplied[:16]}... against {posterior.calibration_content_digest[:16]}...): "
                f"a prediction's domain can only be stated against the calibration it came from")
    cov = posterior._require_numbers()
    if posterior.parameterization != "declared":
        raise HybridUQError("predict from the declared parameterization: a linearly mapped posterior has no forward model")
    specs = tuple(specs)
    if not specs or not all(isinstance(s, PredictiveObservableSpec) for s in specs):
        raise HybridUQError("linearized_predictive_uq takes one or more PredictiveObservableSpec")
    level = float(confidence_level)
    if not 0.0 < level < 1.0:
        raise HybridUQError("confidence_level must lie strictly between 0 and 1")
    keys = tuple(s.observation_key for s in specs)
    units = tuple(s.unit for s in specs)
    references = tuple(Quantity(0.0, u) for u in units)
    transforms = posterior.inference_transforms
    z0 = np.asarray(posterior.inference_point)
    lower, upper = np.asarray(posterior.lower_bounds), np.asarray(posterior.upper_bounds)

    def g(z):
        return evaluate(predict, to_natural(z, transforms), keys, units, references)

    measurement = [None if s.observation_sigma is None else float(s.observation_sigma.magnitude_in(s.unit)) for s in specs]
    try:
        g0, G, _steps, _one_sided, _count = central_difference(
            g, z0, lower, upper, DEFAULT_RELATIVE_STEP, weights=[math.nan if m is None else m for m in measurement])
    except RouteRefusedError as exc:
        raise RouteRefusedError(f"the predictive derivative could not be established near the estimate: {exc}") from None
    parameter_var = np.einsum("ij,jk,ik->i", G, cov, G)
    # g Sigma g^T of a valid covariance is non-negative up to roundoff, which is bounded by |g| |Sigma| |g|^T. A
    # variance below that bound is a defect in the covariance and raises; it is never turned into zero uncertainty.
    roundoff = 64.0 * float(np.finfo(float).eps) * np.einsum("ij,jk,ik->i", np.abs(G), np.abs(cov), np.abs(G))
    if np.any(parameter_var < -roundoff):
        worst = int(np.argmin(parameter_var + roundoff))
        raise HybridUQError(f"the parameter variance of {keys[worst]!r} is {float(parameter_var[worst]):.3g}, negative beyond "
                            f"roundoff ({float(-roundoff[worst]):.3g}): the posterior covariance is not a covariance")
    parameter_var = np.maximum(parameter_var, 0.0)
    parameter_sd = np.sqrt(parameter_var)
    total_sd = np.asarray([math.sqrt(parameter_var[i] + (m ** 2 if m is not None else 0.0)) for i, m in enumerate(measurement)])

    nonlinearity = None
    skipped = 0
    if check_nonlinearity:
        # The largest deviation over the probes that were evaluated. A probe outside the declared bounds or
        # refused by the predictive model was not evaluated, so it is counted, not read as agreement: the
        # nonlinearity it would have measured is unknown, and 0.0 over no probes is not evidence of linearity.
        #
        # The probes are the local route's unit-Mahalanobis directions -- every principal axis and every diagonal
        # between two of them -- plus, for each prediction, the direction Sigma grad g along which its own
        # parameter variance lies (audit HUQ-07: axes alone read g = c u1 + K u1 u2 as exactly linear).
        #
        # A deviation is measured in units of the PARAMETER standard uncertainty (audit HUQ-11): scaled by the total,
        # a large measurement sigma hid a parameter part curved enough to move the parameter interval off its mass.
        # Since the parameter sd never exceeds the total, this never reads less nonlinearity than the total scale did.
        # R-37: ONE number per SPEC. The deviations below are already a vector over the specs, and the
        # maximum was taken over the whole call -- so an exactly affine prediction in the same call as a
        # quadratic one recorded the quadratic one's number, and its read-back rule then derived
        # PREDICTIVE_NONLINEAR for it from someone else's curvature. A record has to be about the thing it
        # names.
        nonlinearity = np.zeros(len(specs))
        lam, vec = np.linalg.eigh(cov)
        directions = _probe_directions(lam, vec)
        for i in range(len(specs)):
            if parameter_sd[i] > 0.0:
                directions.append((cov @ G[i]) / parameter_sd[i])
        roundoff_factor = 64.0 * float(np.finfo(float).eps)
        for direction in directions:
            delta = PROBE_SD * np.asarray(direction, dtype=np.float64)
            for sign in (1.0, -1.0):
                point = z0 + sign * delta
                if np.any(point < lower) or np.any(point > upper):
                    skipped += 1
                    continue
                value = g(point)
                if value is None:
                    skipped += 1
                    continue
                linear = g0 + sign * G @ delta
                deviation = np.maximum(np.abs(value - linear) - roundoff_factor * np.maximum(np.abs(value), np.abs(linear)), 0.0)
                with np.errstate(divide="ignore", invalid="ignore"):
                    relative = np.where(parameter_sd > 0.0, deviation / np.where(parameter_sd > 0.0, parameter_sd, 1.0),
                                        np.where(deviation > 0.0, math.inf, 0.0))
                nonlinearity = np.maximum(nonlinearity, relative)
    else:
        # A caller who chooses not to measure linearity has not shown it: every probe counts as not evaluated, so
        # the claim is capped at DOWNGRADED. predictive_nonlinearity stays None, which says nothing was measured.
        skipped = 2 * len(z0)
    if nonlinearity is not None and not np.all(np.isfinite(nonlinearity)):
        # R-37: inf is not a large nonlinearity -- it is the absence of a scale to measure one against. The
        # deviation is expressed in units of the PARAMETER standard uncertainty because that is what the
        # reported interval is built from; where that uncertainty is exactly 0 the interval is a point, and a
        # probe that moves the prediction at all says the point is wrong by an amount the interval cannot
        # express. There is no number to downgrade, so the route refuses -- which is what "a refused route
        # emits no predictive uncertainty" already says everywhere else here. It was emitted DOWNGRADED.
        worst = [keys[i] for i in range(len(specs)) if not math.isfinite(float(nonlinearity[i]))]
        raise RouteRefusedError(
            f"the linearization of {worst} has no parameter uncertainty for its own curvature to be measured "
            f"against: the probes move it and its reported interval is a point. A prediction whose "
            f"linearization cannot be scaled is refused, not downgraded")
    reasons = set(posterior.diagnostics.downgrades)
    if skipped:
        reasons.add(RouteReason.NONLINEARITY_PROBE_INCOMPLETE)
    q = float(norm.ppf(0.5 + level / 2.0))
    out = []
    for i, spec in enumerate(specs):
        spec_reasons = reasons | _prediction_domain_reasons(spec, calibration_observations, posterior)
        measured = None if nonlinearity is None else float(nonlinearity[i])
        if measured is not None and measured > PREDICTIVE_NONLINEARITY_DOWNGRADE:
            spec_reasons = spec_reasons | {RouteReason.PREDICTIVE_NONLINEAR}
        claim = claim_for(spec_reasons)
        out.append(RoutedPredictiveUncertainty(
            observation_key=spec.observation_key, unit=spec.unit, approximation_class=ApproximationClass.LINEARIZED_PREDICTIVE_UQ,
            mean=float(g0[i]), parameter_standard_uncertainty=float(parameter_sd[i]),
            measurement_standard_uncertainty=measurement[i], total_standard_uncertainty=float(total_sd[i]),
            parameter_interval=(float(g0[i] - q * parameter_sd[i]), float(g0[i] + q * parameter_sd[i])),
            total_interval=(float(g0[i] - q * total_sd[i]), float(g0[i] + q * total_sd[i])), confidence_level=level,
            sources=UNCERTAINTY_SOURCES, model_discrepancy=MODEL_DISCREPANCY_NOT_MODELLED, posterior_digest=posterior.digest,
            route_claim=claim, reasons=tuple(spec_reasons), predictive_nonlinearity=measured,
        ))
    return tuple(out)


#: R-23: the table is supposed to BE ``predict``'s values on these nodes, and ``predict`` is deterministic, so
#: the only admissible disagreement is floating point. Same form as this module's probe-deviation and
#: variance-roundoff bounds.
TABLE_ROUNDOFF_FACTOR = 64.0


def _spot_check_nodes(posterior: PosteriorGrid, predictive_table: AdmittedForwardTable,
                      spec: PredictiveObservableSpec) -> tuple[int, ...]:
    """The nodes a grid prediction's reported numbers stand on (R-23).

    Three, chosen deterministically among the nodes that are admissible in BOTH the posterior and the table
    and carry non-zero posterior weight: the node of maximum posterior weight, and the nodes attaining the
    table's smallest and largest value for THIS prediction.

    WHY THESE AND NOT A COUNT. A count would be a threshold with nothing behind it. These are the nodes the
    ANSWER is made of: the reported mean is dominated by the highest-weight node, and the reported interval's
    ends cannot lie outside the table's extreme values over the support. A table that is systematically wrong
    -- the audited case is a factor of two -- disagrees at the first of them. A table wrong at one low-weight
    interior node is NOT caught, and the bound on that is explicit: such a node moves the reported mean by at
    most its own weight times its own deviation.
    """
    weights = np.asarray(posterior.weights, dtype=float)
    values = np.asarray(predictive_table.values, dtype=float)
    column = list(predictive_table.observation_keys).index(spec.observation_key)
    usable = (np.asarray(posterior.admissible_mask, dtype=bool)
              & np.asarray(predictive_table.admissible_mask, dtype=bool)
              & (weights > 0.0))
    if not usable.any():
        return ()
    heaviest = int(np.argmax(np.where(usable, weights, -np.inf)))
    lowest = int(np.argmin(np.where(usable, values[:, column], np.inf)))
    highest = int(np.argmax(np.where(usable, values[:, column], -np.inf)))
    return tuple(sorted({heaviest, lowest, highest}))


def _require_table_is_the_model(posterior: PosteriorGrid, predictive_table: AdmittedForwardTable,
                               spec: PredictiveObservableSpec, predict: ForwardEvaluator) -> None:
    """Refuse a predictive table that is not ``predict``'s values at the nodes the numbers stand on (R-23).

    A caller who passes ``predict`` beside a table is asserting that the table IS that model's values on
    these nodes. That assertion is true or false, not evidence to be weighed, so a false one is refused --
    the same shape as CORE-005's refusal for a grid that is not this request's evidence, and as part A's
    refusal of calibration observations the posterior was not fitted to. Before this, the grid path took both
    arguments and used only the table.
    """
    column = list(predictive_table.observation_keys).index(spec.observation_key)
    values = np.asarray(predictive_table.values, dtype=float)
    points = np.asarray(predictive_table.points, dtype=float)
    reference = (Quantity(0.0, spec.unit),)
    for node in _spot_check_nodes(posterior, predictive_table, spec):
        got = evaluate(predict, tuple(points[node]), (spec.observation_key,), (spec.unit,), reference)
        if got is None:
            raise HybridUQError(
                f"the predictive model refuses node {node} of the table it is supposed to be the values of, "
                f"which the table admits: the two do not describe the same model")
        stated, fresh = float(values[node, column]), float(got[0])
        tolerance = TABLE_ROUNDOFF_FACTOR * float(np.finfo(float).eps) * max(abs(stated), abs(fresh), 0.0)
        if not abs(stated - fresh) <= tolerance:
            raise HybridUQError(
                f"the predictive table states {stated!r} for {spec.observation_key!r} at node {node} and the "
                f"predict passed with it gives {fresh!r}: a grid prediction's numbers are the table's, so a "
                f"table that is not this model's values is refused rather than reported")


def grid_predictive_uncertainty(
    posterior: PosteriorGrid,
    predictive_table: AdmittedForwardTable,
    spec: PredictiveObservableSpec,
    *,
    twin: TwinReference,
    model: ModelReference,
    source_ref: str,
    confidence_level: float = 0.95,
    observations=None,
    forward: ForwardEvaluator | None = None,
    calibration=None,
    predict: ForwardEvaluator | None = None,
) -> RoutedPredictiveUncertainty:
    """The frozen grid predictive, in the V2 record, for a grid the router's own judgement accepts.

    The frozen ``posterior_predictive_uq`` deliberately keeps a discrete grid too coarse to carry curvature (its
    exact-mixture meaning). A V2 record says SUPPORTED, which the router only says of a grid the repaired V1
    resolution checks accept, so that judgement is applied first and its refusal raised (audit HUQ-02).

    ``observations`` and ``forward`` (and optionally ``calibration``, whose declared bounds name the faces a posterior may
    reach) hold the grid to the evidence it describes; without them the record is DOWNGRADED, GRID_NOT_BOUND_TO_EVIDENCE.
    """
    if not isinstance(posterior, PosteriorGrid):
        raise HybridUQError("grid_predictive_uncertainty takes a PosteriorGrid")
    claim = _grid_route_claim(posterior)
    claim, reasons = _grid_evidence_judgement(posterior, claim, observations, forward, calibration)
    found = set(reasons) | _prediction_domain_reasons(spec, observations) | _table_reasons(
        posterior, predictive_table, spec, predict)
    reasons = tuple(sorted(found, key=lambda r: r.value))
    claim = claim_for(reasons)
    return _grid_record(posterior, predictive_table, spec, claim, reasons, twin=twin, model=model, source_ref=source_ref,
                        confidence_level=confidence_level)


def _table_reasons(posterior, predictive_table, spec, predict) -> set:
    """R-23: the table checked against ``predict``, or the record saying nobody checked it.

    Without the downgrade the spot-check would be silenced by omitting an optional argument, which is the
    shape of R-12 one layer down -- and R-12 is the problem part A of this same improvement closed. A rule a
    caller turns off by passing nothing is not a rule.
    """
    if predict is None:
        return {RouteReason.PREDICTIVE_TABLE_NOT_CHECKED}
    _require_table_is_the_model(posterior, predictive_table, spec, predict)
    return set()


def _grid_record(posterior, predictive_table, spec, claim, reasons, *, twin, model, source_ref, confidence_level):
    """The V2 record of the frozen grid predictive, under a claim already judged."""
    result = posterior_predictive_uq(posterior, predictive_table, spec, twin=twin, model=model, source_ref=source_ref,
                                     credible_mass=confidence_level)
    unit = result.mean.units
    measurement = None if spec.observation_sigma is None else float(spec.observation_sigma.magnitude_in(unit))
    return RoutedPredictiveUncertainty(
        observation_key=result.observation_key, unit=unit, approximation_class=ApproximationClass.POSTERIOR_GRID,
        mean=float(result.mean.magnitude), parameter_standard_uncertainty=float(result.epistemic_standard_uncertainty.magnitude_in(unit)),
        measurement_standard_uncertainty=measurement,
        total_standard_uncertainty=float(result.total_standard_uncertainty.magnitude_in(unit)),
        parameter_interval=(float(result.epistemic_interval.lower.magnitude_in(unit)), float(result.epistemic_interval.upper.magnitude_in(unit))),
        total_interval=(float(result.total_interval.lower.magnitude_in(unit)), float(result.total_interval.upper.magnitude_in(unit))),
        confidence_level=result.confidence_level, sources=UNCERTAINTY_SOURCES, model_discrepancy=MODEL_DISCREPANCY_NOT_MODELLED,
        posterior_digest=grid_digest(posterior), route_claim=claim, reasons=reasons, predictive_nonlinearity=None,
    )
