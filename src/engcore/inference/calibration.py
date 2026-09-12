"""Fitting a declared parameter set to declared observations, and saying so.

What this layer is, and what it is not
--------------------------------------
It is the **calibration result** layer of

    inference primitives -> CALIBRATION RESULT -> predictive/adequacy -> workflow

so it depends on ``inference`` primitives and on nothing above it. In
particular it does **not** import ``execution``: the forward evaluations are
supplied by a caller-provided :class:`ForwardEvaluator`, and the orchestration
layer is where that gets backed by the sweep engine. Putting the sweep here
would pull an execution dependency into a certified inference module to serve
one caller, and would invert the direction the round set out to keep.

The distinction this module exists to keep
-------------------------------------------
**A calibration that converged is not a model that is adequate.** Those are
different claims about different things, and the whole apparatus below is
arranged so that one cannot be read as the other:

* :class:`CalibrationStatus` answers *did the optimizer find a minimum*;
* :class:`IdentifiabilityStatus` answers *does the data determine the
  parameters*, which a converged optimizer says nothing about;
* adequacy -- *does the model predict data it was not fitted to* -- is not in
  this module at all, and cannot be, because it is a statement about held-out
  evidence that this layer never sees.

A :class:`CalibrationResult` therefore carries no adequacy field, no "success"
boolean, and no verdict. It reports what the fit did.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from ..scientific.serialization import require_schema, schema_string
from ..scientific.units.quantity import Quantity
from .grid import InferenceProblemError, ObservationSet, PosteriorGrid
from .parameters import (
    CalibrationParameterSet,
    ParameterEstimate,
    ParameterIdentity,
    ParameterIdentityError,
    require_parameter_set,
)

CALIBRATION_SPEC_SCHEMA = schema_string("calibration_spec")
CALIBRATION_RESULT_SCHEMA = schema_string("calibration_result")
NOISE_MODEL_SCHEMA = schema_string("calibration_noise_model")


class CalibrationError(InferenceProblemError):
    """A calibration that cannot be posed or cannot be reported."""


class CalibrationStatus(str, Enum):
    """Did the optimizer find a minimum. NOT whether the model is any good."""

    CONVERGED = "CALIBRATION_CONVERGED"
    FAILED = "CALIBRATION_FAILED"


class IdentifiabilityStatus(str, Enum):
    """Does the data determine the parameters, and how well.

    Separate from :class:`CalibrationStatus` because a converged optimizer says
    nothing about this. A perfectly converged fit of two parameters that the
    design cannot separate reports a point estimate with no more content than
    the ridge it sits on, and reporting a tight interval for it would be false
    precision of exactly the kind Phase 11 forbids.
    """

    IDENTIFIABLE = "PARAMETERS_IDENTIFIABLE"
    WEAKLY_IDENTIFIABLE = "PARAMETERS_WEAKLY_IDENTIFIABLE"
    NOT_IDENTIFIABLE = "PARAMETERS_NOT_IDENTIFIABLE"


@dataclass(frozen=True)
class NoiseModel:
    """How the observations' scatter is represented. Declared, never inferred.

    ``gaussian_independent`` is the only kind this round implements, and it
    reads its sigma from each :class:`GaussianObservation` rather than fitting
    one: a sigma estimated from the same residuals it then weights is a
    different statistical object than a declared measurement uncertainty, and
    conflating them is how an over-fitted model comes to look well-calibrated.
    """

    kind: str = "gaussian_independent"
    sigma_source: str = "declared_per_observation"

    def __post_init__(self) -> None:
        if self.kind != "gaussian_independent":
            raise CalibrationError(
                f"unsupported noise model {self.kind!r}; this round implements "
                f"'gaussian_independent' only, and an unimplemented kind is "
                f"refused rather than silently treated as the one that is"
            )
        if self.sigma_source != "declared_per_observation":
            raise CalibrationError(
                f"unsupported sigma source {self.sigma_source!r}: a sigma "
                f"estimated from the residuals it weights is not a declared "
                f"measurement uncertainty"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": NOISE_MODEL_SCHEMA,
            "kind": self.kind,
            "sigma_source": self.sigma_source,
        }


#: A caller-supplied forward model. Takes the parameter vector in the declared
#: column order and returns one predicted Quantity per observation key, in the
#: observation set's own order. Returning ``None`` means the candidate was not
#: scientifically admissible at that point, which is a refusal rather than a
#: large residual -- the difference matters, and a caller that returns a
#: fabricated number for an inadmissible point has destroyed it.
ForwardEvaluator = Callable[[Sequence[float]], "Sequence[Quantity] | None"]


@dataclass(frozen=True)
class CalibrationSpec:
    """Everything a calibration is, stated before it runs.

    Every field here is a declaration the run is held to. There is deliberately
    no way to express "fit whatever is free": :attr:`parameters` is the
    estimated set, :attr:`fixed` is everything held, and a quantity in neither
    is not part of this calibration.
    """

    parameters: CalibrationParameterSet
    fixed: Mapping[str, Quantity]
    initial_point: Mapping[str, Quantity]
    noise_model: NoiseModel = field(default_factory=NoiseModel)
    objective: str = "gaussian_negative_log_likelihood"
    method: str = "bounded_least_squares_trf"

    def __post_init__(self) -> None:
        require_parameter_set(self.parameters)
        if not isinstance(self.noise_model, NoiseModel):
            raise CalibrationError("a calibration spec requires a NoiseModel")
        for label in ("objective", "method"):
            if not str(getattr(self, label)).strip():
                raise CalibrationError(f"a calibration spec requires {label}")
        fixed = dict(self.fixed)
        initial = dict(self.initial_point)
        for name, value in {**fixed, **initial}.items():
            if not isinstance(value, Quantity):
                raise CalibrationError(
                    f"{name!r} must be a Quantity; a bare number in a "
                    f"calibration declaration carries no unit"
                )
        overlap = sorted(set(fixed) & set(self.parameters.names))
        if overlap:
            raise CalibrationError(
                f"{overlap!r} are declared both estimated and fixed. A "
                f"parameter is one or the other, and a record saying both "
                f"cannot be acted on"
            )
        # The initial point is checked against the declared bounds here rather
        # than at the first iteration, so an impossible starting guess is a
        # refusal to pose the problem rather than an optimizer failure that
        # looks like a scientific finding.
        self.parameters.require_all_in_bounds(initial)
        object.__setattr__(self, "fixed", dict(fixed))
        object.__setattr__(self, "initial_point", dict(initial))

    @property
    def initial_vector(self) -> tuple[float, ...]:
        return self.parameters.require_all_in_bounds(self.initial_point)

    @property
    def lower_vector(self) -> tuple[float, ...]:
        return tuple(
            p.bounds.lower.magnitude_in(p.unit) for p in self.parameters.parameters
        )

    @property
    def upper_vector(self) -> tuple[float, ...]:
        return tuple(
            p.bounds.upper.magnitude_in(p.unit) for p in self.parameters.parameters
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CALIBRATION_SPEC_SCHEMA,
            "parameters": self.parameters.to_dict(),
            "fixed": {k: v.to_dict() for k, v in sorted(self.fixed.items())},
            "initial_point": {
                k: v.to_dict() for k, v in sorted(self.initial_point.items())
            },
            "noise_model": self.noise_model.to_dict(),
            "objective": self.objective,
            "method": self.method,
        }

    @property
    def digest(self) -> str:
        blob = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CalibrationProvenance:
    """What a calibrated result must preserve to be re-derivable.

    Phase 20's list, and the reason each entry is here rather than implied:
    a reader handed only estimates cannot tell which data produced them, which
    parameters they are estimates OF, what range the search was allowed, where
    it started, or how the scatter was represented -- and every one of those
    changes what the numbers mean.

    Bulk arrays are deliberately absent. The posterior's points and weights are
    data-plane objects; what belongs in provenance is the identity of the
    thing, not its contents.
    """

    model_ids: tuple[str, ...]
    parameter_set_digest: str
    calibration_dataset_id: str
    heldout_dataset_id: str
    spec_digest: str
    method: str
    objective: str
    noise_model: NoiseModel
    uncertainty_method: str
    evaluation_count: int
    wall_seconds: float
    seed: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_ids": list(self.model_ids),
            "parameter_set_digest": self.parameter_set_digest,
            "calibration_dataset_id": self.calibration_dataset_id,
            "heldout_dataset_id": self.heldout_dataset_id,
            "spec_digest": self.spec_digest,
            "method": self.method,
            "objective": self.objective,
            "noise_model": self.noise_model.to_dict(),
            "uncertainty_method": self.uncertainty_method,
            "evaluation_count": self.evaluation_count,
            "wall_seconds": self.wall_seconds,
            "seed": self.seed,
        }


@dataclass(frozen=True)
class CalibrationResult:
    """What the fit did. Not whether the model is any good.

    There is no ``adequate`` field and no bare ``success`` boolean, on purpose.
    :attr:`status` is about the optimizer; adequacy is a statement about
    held-out evidence this layer never sees, and a reader who wants it has to
    go and get it.
    """

    spec: CalibrationSpec
    status: CalibrationStatus
    estimates: tuple[ParameterEstimate, ...]
    objective_value: float
    termination_reason: str
    evaluation_count: int
    provenance: CalibrationProvenance
    residuals: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, CalibrationStatus):
            raise CalibrationError("status must be a CalibrationStatus")
        if self.status is CalibrationStatus.CONVERGED:
            if len(self.estimates) != len(self.spec.parameters.parameters):
                raise CalibrationError(
                    "a converged calibration reports one estimate per declared "
                    "parameter"
                )
            for estimate, identity in zip(self.estimates, self.spec.parameters.parameters):
                if not estimate.identity.is_same_parameter(identity):
                    raise CalibrationError(
                        f"estimate {estimate.identity.key!r} is not an estimate "
                        f"of declared parameter {identity.key!r}"
                    )
            if not math.isfinite(self.objective_value):
                raise CalibrationError(
                    "a converged calibration cannot report a non-finite objective"
                )
        if not str(self.termination_reason).strip():
            raise CalibrationError("a calibration must say why it stopped")

    @property
    def estimate_vector(self) -> tuple[float, ...]:
        return tuple(e.magnitude for e in self.estimates)

    def estimate_of(self, name: str) -> ParameterEstimate:
        for estimate in self.estimates:
            if estimate.identity.name == name:
                return estimate
        raise ParameterIdentityError(f"{name!r} was not estimated by this calibration")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CALIBRATION_RESULT_SCHEMA,
            "status": self.status.value,
            "spec": self.spec.to_dict(),
            "estimates": [e.to_dict() for e in self.estimates],
            "objective_value": self.objective_value,
            "termination_reason": self.termination_reason,
            "evaluation_count": self.evaluation_count,
            "provenance": self.provenance.to_dict(),
        }


def calibrate(
    spec: CalibrationSpec,
    observations: ObservationSet,
    forward: ForwardEvaluator,
    *,
    heldout_dataset_id: str,
    max_evaluations: int = 2000,
    uncertainty_method: str = "grid_posterior_covariance",
    seed: int | None = None,
) -> CalibrationResult:
    """Bounded least squares on dimensionally-coherent standardized residuals.

    One method, deliberately. The residual for each observation is

        (predicted - observed) / sigma

    with ``predicted`` converted into the observation's own unit first, so the
    quantity being squared is dimensionless and observations in different units
    combine without an arbitrary scale factor. Phase 7's "no hidden unit-less
    residual" is enforced by :meth:`Quantity.require_compatible` on every term,
    not by convention.

    An inadmissible forward point is not given a large residual: the evaluator
    returns ``None`` and the point is refused, because a fabricated number
    there would be an invented observation.
    """
    from scipy.optimize import least_squares  # local: keeps import cost off the module

    if not isinstance(spec, CalibrationSpec):
        raise CalibrationError("calibrate() takes a CalibrationSpec")
    if not isinstance(observations, ObservationSet):
        raise CalibrationError("calibrate() takes an ObservationSet")

    observed, sigma = observations.numeric_vectors()
    units = [item.value.units for item in observations.observations]
    calls = {"n": 0}

    def residual(vector: np.ndarray) -> np.ndarray:
        calls["n"] += 1
        predicted = forward(tuple(float(v) for v in vector))
        if predicted is None:
            # Refused, not penalised. A large finite residual would let the
            # optimizer trade an inadmissible region against a good fit.
            return np.full(observed.shape, np.inf, dtype=np.float64)
        if len(predicted) != len(observed):
            raise CalibrationError(
                f"forward evaluator returned {len(predicted)} value(s) for "
                f"{len(observed)} observation(s)"
            )
        magnitudes = np.empty(observed.shape, dtype=np.float64)
        for index, (value, unit) in enumerate(zip(predicted, units)):
            if not isinstance(value, Quantity):
                raise CalibrationError(
                    f"forward evaluator returned {type(value).__name__} for "
                    f"observation {observations.observations[index].key!r}; a "
                    f"residual taken against a bare float is the hidden "
                    f"unit-less residual this objective refuses"
                )
            value.require_compatible(
                observations.observations[index].value,
                context=f"forward prediction for {observations.observations[index].key}",
            )
            magnitudes[index] = value.magnitude_in(unit)
        return (magnitudes - observed) / sigma

    started = time.monotonic()
    try:
        outcome = least_squares(
            residual,
            x0=np.asarray(spec.initial_vector, dtype=np.float64),
            bounds=(
                np.asarray(spec.lower_vector, dtype=np.float64),
                np.asarray(spec.upper_vector, dtype=np.float64),
            ),
            method="trf",
            max_nfev=max_evaluations,
        )
    except Exception as exc:  # noqa: BLE001 - reported, not swallowed
        return CalibrationResult(
            spec=spec,
            status=CalibrationStatus.FAILED,
            estimates=(),
            objective_value=float("inf"),
            termination_reason=f"{type(exc).__name__}: {exc}",
            evaluation_count=calls["n"],
            provenance=_provenance(
                spec, observations, heldout_dataset_id, uncertainty_method,
                calls["n"], time.monotonic() - started, seed,
            ),
        )
    wall = time.monotonic() - started

    if not outcome.success:
        return CalibrationResult(
            spec=spec,
            status=CalibrationStatus.FAILED,
            estimates=(),
            objective_value=float(2.0 * outcome.cost),
            termination_reason=str(outcome.message),
            evaluation_count=int(outcome.nfev),
            provenance=_provenance(
                spec, observations, heldout_dataset_id, uncertainty_method,
                int(outcome.nfev), wall, seed,
            ),
        )

    # Built through ParameterEstimate, which re-checks the bounds. An optimizer
    # returning fractionally outside its own box is a documented failure mode,
    # and a record that stored it would hide the violation from here on.
    estimates = tuple(
        ParameterEstimate(identity, float(value))
        for identity, value in zip(spec.parameters.parameters, outcome.x)
    )
    return CalibrationResult(
        spec=spec,
        status=CalibrationStatus.CONVERGED,
        estimates=estimates,
        objective_value=float(2.0 * outcome.cost),
        termination_reason=str(outcome.message),
        evaluation_count=int(outcome.nfev),
        provenance=_provenance(
            spec, observations, heldout_dataset_id, uncertainty_method,
            int(outcome.nfev), wall, seed,
        ),
        residuals=tuple(float(v) for v in outcome.fun),
    )


def _provenance(
    spec: CalibrationSpec,
    observations: ObservationSet,
    heldout_dataset_id: str,
    uncertainty_method: str,
    evaluations: int,
    wall: float,
    seed: int | None,
) -> CalibrationProvenance:
    models = sorted({f"{p.model_id}@{p.model_version}" for p in spec.parameters.parameters})
    return CalibrationProvenance(
        model_ids=tuple(models),
        parameter_set_digest=spec.parameters.digest,
        calibration_dataset_id=observations.dataset_id,
        heldout_dataset_id=str(heldout_dataset_id),
        spec_digest=spec.digest,
        method=spec.method,
        objective=spec.objective,
        noise_model=spec.noise_model,
        uncertainty_method=uncertainty_method,
        evaluation_count=evaluations,
        wall_seconds=round(float(wall), 6),
        seed=seed,
    )


# =====================================================================
# Identifiability -- measured, and classified rather than left as a number
# =====================================================================

@dataclass(frozen=True)
class IdentifiabilityReport:
    """How well the data determines the parameters, with the evidence shown.

    Three measures, because no single one is trustworthy alone:

    ``condition_number``
        of the posterior covariance. Large means the ridge is long relative to
        its width.
    ``max_abs_correlation``
        the largest off-diagonal posterior correlation. This is what catches a
        two-parameter ridge that a determinant can miss when both variances are
        small.
    ``relative_widths``
        each marginal 95% credible width divided by the estimate. A parameter
        whose interval is wider than its own value is not determined, whatever
        the correlation structure says.

    The thresholds are declared here rather than hidden in a comparison, and
    they are properties of the classification, not of the science.
    """

    status: IdentifiabilityStatus
    condition_number: float
    max_abs_correlation: float
    relative_widths: tuple[float, ...]
    parameter_names: tuple[str, ...]
    correlation_threshold: float
    condition_threshold: float
    width_threshold: float
    why: str
    effective_sample_size: float = float("nan")

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "condition_number": self.condition_number,
            "max_abs_correlation": self.max_abs_correlation,
            "relative_widths": list(self.relative_widths),
            "parameter_names": list(self.parameter_names),
            "effective_sample_size": self.effective_sample_size,
            "thresholds": {
                "correlation": self.correlation_threshold,
                "condition_number": self.condition_threshold,
                "relative_width": self.width_threshold,
            },
            "why": self.why,
        }


class GridResolutionError(CalibrationError):
    """The grid cannot answer the question being asked of it.

    Distinct from every :class:`IdentifiabilityStatus`, and that distinction is
    the point. When a likelihood is far sharper than the grid spacing, the
    posterior collapses onto a handful of points and its covariance goes to
    zero -- so a naive reading reports a near-zero variance, a correlation
    numerically indistinguishable from 1, and a credible interval of zero
    width.

    Every one of those is FALSE PRECISION, and the direction of the error is
    the dangerous one: an unresolved grid looks like an exquisitely determined
    parameter. It is not "these parameters are not identifiable" either -- that
    is a statement about the data, and this is a statement about the grid.

    So it is raised rather than classified. The caller's job is to refine the
    grid around the estimate, not to read a number off an instrument that
    cannot resolve it.
    """


def posterior_effective_sample_size(posterior: PosteriorGrid) -> float:
    """Kish's effective sample size, ``1 / sum(w^2)``, over the grid weights.

    1.0 means all the mass sits on one point. It is the cheapest honest answer
    to "did this grid resolve the posterior", and it needs no reference to what
    the parameters mean.
    """
    weights = np.asarray(posterior.weights, dtype=np.float64)
    total = float(np.sum(weights * weights))
    if total <= 0.0:
        return 0.0
    return 1.0 / total


def assess_identifiability(
    posterior: PosteriorGrid,
    *,
    correlation_threshold: float = 0.95,
    condition_threshold: float = 1.0e6,
    width_threshold: float = 1.0,
    minimum_effective_points: float = 8.0,
) -> IdentifiabilityReport:
    """Classify what the posterior says about how determined the parameters are.

    Returns a status rather than a number because Phase 11's requirement is
    that the system "must not report identical confidence for both" an
    identifiable and a weakly identifiable case -- and a bare condition number
    reported without a verdict lets every reader draw their own conclusion,
    which is the same as reporting nothing.

    Raises :class:`GridResolutionError` before classifying anything if the grid
    did not resolve the posterior. See that class for why an unresolved grid
    must not be allowed to return a status.
    """
    if not isinstance(posterior, PosteriorGrid):
        raise CalibrationError("identifiability is assessed from a PosteriorGrid")

    ess = posterior_effective_sample_size(posterior)
    if ess < minimum_effective_points:
        raise GridResolutionError(
            f"the posterior's effective sample size is {ess:.3g} over "
            f"{len(posterior.weights)} grid points, below the required "
            f"{minimum_effective_points:.3g}: the likelihood is sharper than "
            f"the grid spacing, so essentially all the mass is on a handful of "
            f"points. Its covariance would be near zero, its correlation "
            f"numerically 1, and its credible intervals of zero width -- all "
            f"FALSE PRECISION, and in the direction that looks like certainty. "
            f"Refine the grid around the estimate (a few standard errors per "
            f"axis) and ask again. This is a statement about the grid, not "
            f"about whether the parameters are identifiable"
        )

    covariance = posterior.covariance
    correlation = posterior.correlation
    n = covariance.shape[0]

    eigenvalues = np.linalg.eigvalsh(covariance)
    smallest = float(np.min(eigenvalues))
    largest = float(np.max(eigenvalues))
    if smallest <= 0.0:
        condition = float("inf")
    else:
        condition = largest / smallest

    off_diagonal = [
        abs(float(correlation[i, j])) for i in range(n) for j in range(n) if i != j
    ]
    max_correlation = max(off_diagonal) if off_diagonal else 0.0

    widths: list[float] = []
    mean = posterior.mean
    for index in range(n):
        low, high = posterior.marginal_interval(index, 0.95)
        scale = abs(float(mean[index]))
        widths.append((high - low) / scale if scale > 0.0 else float("inf"))

    reasons: list[str] = []
    if not math.isfinite(condition) or condition > condition_threshold:
        reasons.append(
            f"posterior covariance condition number {condition:.3g} exceeds "
            f"{condition_threshold:.3g}"
        )
    if max_correlation > correlation_threshold:
        reasons.append(
            f"parameters are correlated at {max_correlation:.4f}, above "
            f"{correlation_threshold}"
        )
    over_wide = [
        posterior.parameter_names[i]
        for i, w in enumerate(widths)
        if not math.isfinite(w) or w > width_threshold
    ]
    if over_wide:
        reasons.append(
            f"the 95% interval is wider than the estimate itself for "
            f"{over_wide!r}"
        )

    if not reasons:
        status = IdentifiabilityStatus.IDENTIFIABLE
        why = (
            f"condition number {condition:.3g}, max |correlation| "
            f"{max_correlation:.4f}, widest relative interval "
            f"{max(widths):.3g} -- all within the declared thresholds"
        )
    elif len(reasons) >= 2 or over_wide:
        status = IdentifiabilityStatus.NOT_IDENTIFIABLE
        why = "; ".join(reasons)
    else:
        status = IdentifiabilityStatus.WEAKLY_IDENTIFIABLE
        why = "; ".join(reasons)

    return IdentifiabilityReport(
        status=status,
        condition_number=condition,
        max_abs_correlation=max_correlation,
        relative_widths=tuple(widths),
        parameter_names=tuple(posterior.parameter_names),
        correlation_threshold=correlation_threshold,
        condition_threshold=condition_threshold,
        width_threshold=width_threshold,
        why=why,
        effective_sample_size=ess,
    )
