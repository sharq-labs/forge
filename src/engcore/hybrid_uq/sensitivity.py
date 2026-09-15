"""Local sensitivity: the Jacobian ``calibrate`` computes internally and does not return.

``calibrate``'s return contract is frozen, so V2 does not add a field to it. The sensitivity gets its own
record instead. It is RECONSTRUCTED from the calibrated estimate with the caller's own forward evaluator
(finite differences shown to converge under step halving, at least 4p + 1 evaluations), or PRESERVED by
constructing the record directly from a Jacobian a domain already has.

Derivatives are taken in INFERENCE coordinates: log space for a parameter declared
``ParameterTransform.LOG``, the declared unit otherwise. The transform is part of the parameter's identity,
and a covariance in log space is a different object from one in the natural unit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from ..inference.calibration import CalibrationResult, CalibrationStatus, ForwardEvaluator
from ..inference.admissibility import InferenceAdmissibilityError
from ..inference.grid import ObservationSet
from ..inference.parameters import CalibrationParameterSet, ParameterTransform
from ..scientific.units.quantity import Quantity
from ._records import decode_matrix, decode_vector, digest_of, encode_matrix, encode_vector, material, require_schema
from .vocabulary import HybridUQError, RouteReason, RouteRefusedError

LOCAL_SENSITIVITY_SCHEMA = "hybrid_uq.local_sensitivity/1"
DEFAULT_RELATIVE_STEP = 1.0e-5


# ---------------------------------------------------------------------------
# coordinates (private)
# ---------------------------------------------------------------------------
def transforms_of(parameter_set: CalibrationParameterSet) -> tuple[str, ...]:
    return tuple(p.transform.value for p in parameter_set.parameters)


def to_inference(values: Sequence[float], transforms: Sequence[str]) -> np.ndarray:
    return np.asarray([ParameterTransform(t).forward(float(v)) for v, t in zip(values, transforms)], dtype=np.float64)


def to_natural(values: Sequence[float], transforms: Sequence[str]) -> np.ndarray:
    return np.asarray([ParameterTransform(t).inverse(float(v)) for v, t in zip(values, transforms)], dtype=np.float64)


def inference_bounds(parameter_set: CalibrationParameterSet) -> tuple[np.ndarray, np.ndarray]:
    lower, upper = [], []
    for p in parameter_set.parameters:
        lo, hi = p.bounds.lower.magnitude_in(p.unit), p.bounds.upper.magnitude_in(p.unit)
        lower.append(p.transform.forward(lo))
        upper.append(p.transform.forward(hi))
    return np.asarray(lower, dtype=np.float64), np.asarray(upper, dtype=np.float64)


def evaluate(forward: ForwardEvaluator, natural: Sequence[float], keys: Sequence[str],
             units: Sequence[str], references: Sequence[Quantity]) -> np.ndarray | None:
    """One forward call, held to the same rules as ``calibrate``: Quantities, compatible units, or a refusal."""
    try:
        predicted = forward(tuple(float(v) for v in natural))
    except InferenceAdmissibilityError:
        # The admission boundary's own refusal is a refusal of the point, the same as returning None. Any
        # other exception is a defect and propagates.
        return None
    if predicted is None:
        return None
    if len(predicted) != len(keys):
        raise HybridUQError(f"forward evaluator returned {len(predicted)} value(s) for {len(keys)} key(s)")
    out = np.empty(len(keys), dtype=np.float64)
    for i, (value, unit, reference) in enumerate(zip(predicted, units, references)):
        if not isinstance(value, Quantity):
            raise HybridUQError(f"forward evaluator returned {type(value).__name__} for {keys[i]!r}; a bare float carries no unit")
        value.require_compatible(reference, context=f"forward prediction for {keys[i]}")
        out[i] = value.magnitude_in(unit)
    if not np.all(np.isfinite(out)):
        return None
    return out


#: A finite-difference column is accepted only when its estimate at one step and at half that step agree: the
#: estimated error of the accepted column, in the weighted 2-norm, is at most this fraction of the column. A
#: 1e-3 relative error in a Jacobian column moves the standard deviations it implies by about 1e-3 of themselves.
DERIVATIVE_RELATIVE_TOLERANCE = 1.0e-3
#: The evaluation error a difference quotient is assumed unable to resolve below, in units of machine epsilon
#: times the size of the values differenced. A model noisier than that at the tolerance is refused, not trusted.
DERIVATIVE_ROUNDOFF_FACTOR = 64.0
_MAXIMUM_STEP_HALVINGS = 40


class _DerivativeNotConverged(RouteRefusedError):
    """A finite-difference derivative that did not stabilize under step refinement.

    A refusal, not a defect: there is no established curvature to build a covariance from. It is a distinct
    class so that a caller never reports it as an inadmissible forward point, which is a different fact.
    """


def central_difference(fun, z0: np.ndarray, lower: np.ndarray, upper: np.ndarray, relative_step: float,
                       weights: np.ndarray | None = None):
    """Jacobian of ``fun`` in inference coordinates, shown to be stable under step refinement.

    Each column starts at ``relative_step`` times the declared inference range: central where both points stay
    inside the bounds, one-sided toward the interior otherwise. It is recomputed at half the step, nested, until
    two successive estimates agree. Agreement means their weighted difference, scaled to an error estimate for the
    coarser of the two (4/3 when both are central, 2 when either is one-sided), is within
    ``DERIVATIVE_RELATIVE_TOLERANCE`` of the column plus the roundoff the two steps can resolve. The coarser
    estimate of the agreeing pair is accepted, so a column that was already accurate at the starting step is
    unchanged, byte for byte, at the cost of one more pair of evaluations.

    Refinement never leaves the bounds. The derivative is refused with :class:`RouteRefusedError` when roundoff
    alone would exceed the tolerance, when the step is no longer resolvable against the coordinate's magnitude,
    or after ``_MAXIMUM_STEP_HALVINGS``. A derivative that did not stabilize is no basis for a curvature.

    ``weights`` divides each output before a norm is taken, so outputs in different units are compared in a common
    scale: the observation sigmas for a Jacobian of observations. An entry that is NaN, or ``weights=None``,
    means no declared scale; that output is scaled by the magnitude of its value at ``z0``, or by 1 where that is
    zero. Returns ``(base, jacobian, steps, one_sided, evaluations)``, where ``steps`` and ``one_sided``
    describe the accepted estimates. Raises :class:`RouteRefusedError` when a point is inadmissible.
    """
    base = fun(z0)
    evaluations = 1
    if base is None:
        raise RouteRefusedError(f"{RouteReason.FORWARD_INADMISSIBLE_NEAR_ESTIMATE.value}: the forward evaluator refused the estimate itself")
    w = np.full(base.shape, np.nan) if weights is None else np.array(weights, dtype=np.float64)
    if w.shape != base.shape or np.any(np.isinf(w)) or np.any(w <= 0.0):
        raise HybridUQError("finite-difference weights must be positive or NaN, one per output")
    undeclared = np.isnan(w)
    w[undeclared] = np.where(np.abs(base[undeclared]) > 0.0, np.abs(base[undeclared]), 1.0)
    eps = float(np.finfo(float).eps)
    columns, steps, one_sided = [], [], []
    for i in range(len(z0)):
        h = relative_step * float(upper[i] - lower[i])
        if not (h > 0.0 and math.isfinite(h)):
            raise HybridUQError(f"parameter {i} has a degenerate inference range; no finite-difference step exists")

        def quotient(step, i=i):
            up, dn = z0.copy(), z0.copy()
            up[i] += step
            dn[i] -= step
            if up[i] > upper[i]:
                f_up, f_dn, denominator, side, calls = base, fun(dn), step, True, 1
            elif dn[i] < lower[i]:
                f_up, f_dn, denominator, side, calls = fun(up), base, step, True, 1
            else:
                f_up, f_dn, denominator, side, calls = fun(up), fun(dn), 2.0 * step, False, 2
            if f_up is None or f_dn is None:
                raise RouteRefusedError(
                    f"{RouteReason.FORWARD_INADMISSIBLE_NEAR_ESTIMATE.value}: the forward evaluator refused a "
                    f"finite-difference point for parameter {i}")
            magnitude = np.maximum(np.abs(f_up), np.abs(f_dn))
            roundoff = float(np.linalg.norm(DERIVATIVE_ROUNDOFF_FACTOR * eps * magnitude / denominator / w))
            return (f_up - f_dn) / denominator, side, calls, roundoff

        coarse, coarse_side, calls, coarse_roundoff = quotient(h)
        evaluations += calls
        resolvable = DERIVATIVE_ROUNDOFF_FACTOR * eps * abs(float(z0[i]))
        for halving in range(1, _MAXIMUM_STEP_HALVINGS + 1):
            fine_step = 0.5 * h
            if not fine_step > resolvable:
                raise _DerivativeNotConverged(
                    f"the derivative for parameter {i} did not stabilize before the step ({fine_step:.3g}) stopped "
                    f"being resolvable against the coordinate ({float(z0[i]):.6g}), after {halving - 1} halving(s)")
            fine, fine_side, calls, fine_roundoff = quotient(fine_step)
            evaluations += calls
            size = max(float(np.linalg.norm(coarse / w)), float(np.linalg.norm(fine / w)))
            factor = 2.0 if (coarse_side or fine_side) else 4.0 / 3.0
            error = factor * float(np.linalg.norm((coarse - fine) / w))
            floor = coarse_roundoff + fine_roundoff
            if error == 0.0:
                break
            if floor > DERIVATIVE_RELATIVE_TOLERANCE * size:
                raise _DerivativeNotConverged(
                    f"the derivative for parameter {i} did not stabilize before evaluation roundoff reached the "
                    f"tolerance: estimates at steps {h:.3g} and {fine_step:.3g} differ by {error:.3g} (weighted) "
                    f"for a column of {size:.3g}, after {halving - 1} halving(s)")
            if error <= DERIVATIVE_RELATIVE_TOLERANCE * size + floor:
                break
            coarse, coarse_side, coarse_roundoff, h = fine, fine_side, fine_roundoff, fine_step
        else:
            raise _DerivativeNotConverged(
                f"the derivative for parameter {i} did not stabilize within {_MAXIMUM_STEP_HALVINGS} step halvings")
        columns.append(coarse)
        steps.append(h)
        one_sided.append(coarse_side)
    return base, np.column_stack(columns), tuple(steps), tuple(one_sided), evaluations


# ---------------------------------------------------------------------------
# the record
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LocalSensitivity:
    """The sigma-free Jacobian of predicted observations with respect to inference coordinates, at one point."""

    parameter_set_digest: str
    parameter_names: tuple[str, ...]
    inference_transforms: tuple[str, ...]
    estimate: tuple[float, ...]
    observation_keys: tuple[str, ...]
    observation_units: tuple[str, ...]
    observed: tuple[float, ...]
    sigma: tuple[float, ...]
    predicted: tuple[float, ...]
    jacobian: tuple[tuple[float, ...], ...]
    steps: tuple[float, ...]
    one_sided: tuple[bool, ...]
    dataset_id: str
    evaluation_count: int
    method: str = "central_difference"

    def __post_init__(self) -> None:
        p, n = len(self.parameter_names), len(self.observation_keys)
        for label in ("parameter_names", "inference_transforms", "observation_keys", "observation_units"):
            object.__setattr__(self, label, tuple(str(v) for v in getattr(self, label)))
        for label in ("estimate", "observed", "sigma", "predicted", "steps"):
            object.__setattr__(self, label, tuple(float(v) for v in getattr(self, label)))
        object.__setattr__(self, "one_sided", tuple(bool(v) for v in self.one_sided))
        object.__setattr__(self, "jacobian", tuple(tuple(float(v) for v in row) for row in self.jacobian))
        if p == 0 or n == 0:
            raise HybridUQError("a local sensitivity needs at least one parameter and one observation")
        for t in self.inference_transforms:
            ParameterTransform(t)
        lengths = {"inference_transforms": len(self.inference_transforms), "estimate": len(self.estimate),
                   "steps": len(self.steps), "one_sided": len(self.one_sided)}
        if any(v != p for v in lengths.values()):
            raise HybridUQError(f"per-parameter fields disagree with {p} parameter(s): {lengths}")
        for label in ("observation_units", "observed", "sigma", "predicted"):
            if len(getattr(self, label)) != n:
                raise HybridUQError(f"{label} has {len(getattr(self, label))} entries for {n} observation(s)")
        if len(self.jacobian) != n or any(len(row) != p for row in self.jacobian):
            raise HybridUQError(f"the jacobian must be {n} x {p}")
        if not all(math.isfinite(v) for row in self.jacobian for v in row):
            raise HybridUQError("the jacobian must be finite")
        if not all(s > 0.0 and math.isfinite(s) for s in self.sigma):
            raise HybridUQError("observation sigmas must be finite and positive")
        if self.method not in ("central_difference", "supplied"):
            raise HybridUQError(f"unknown sensitivity method {self.method!r}")
        if not str(self.dataset_id).strip() or not str(self.parameter_set_digest).strip():
            raise HybridUQError("a local sensitivity names its dataset and its parameter set")

    @property
    def weighted_jacobian(self) -> np.ndarray:
        return np.asarray(self.jacobian, dtype=np.float64) / np.asarray(self.sigma)[:, None]

    @property
    def standardized_residuals(self) -> np.ndarray:
        return (np.asarray(self.predicted) - np.asarray(self.observed)) / np.asarray(self.sigma)

    @property
    def chi_square(self) -> float:
        return float(np.sum(self.standardized_residuals ** 2))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": LOCAL_SENSITIVITY_SCHEMA,
            "parameter_set_digest": self.parameter_set_digest,
            "parameter_names": list(self.parameter_names),
            "inference_transforms": list(self.inference_transforms),
            "estimate": encode_vector(self.estimate),
            "observation_keys": list(self.observation_keys),
            "observation_units": list(self.observation_units),
            "observed": encode_vector(self.observed),
            "sigma": encode_vector(self.sigma),
            "predicted": encode_vector(self.predicted),
            "jacobian": encode_matrix(self.jacobian),
            "steps": encode_vector(self.steps),
            "one_sided": list(self.one_sided),
            "dataset_id": self.dataset_id,
            "evaluation_count": int(self.evaluation_count),
            "method": self.method,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LocalSensitivity":
        require_schema(payload, LOCAL_SENSITIVITY_SCHEMA)
        return cls(
            parameter_set_digest=payload["parameter_set_digest"], parameter_names=tuple(payload["parameter_names"]),
            inference_transforms=tuple(payload["inference_transforms"]), estimate=decode_vector(payload["estimate"]),
            observation_keys=tuple(payload["observation_keys"]), observation_units=tuple(payload["observation_units"]),
            observed=decode_vector(payload["observed"]), sigma=decode_vector(payload["sigma"]),
            predicted=decode_vector(payload["predicted"]), jacobian=decode_matrix(payload["jacobian"]),
            steps=decode_vector(payload["steps"]), one_sided=tuple(payload["one_sided"]),
            dataset_id=payload["dataset_id"], evaluation_count=int(payload["evaluation_count"]), method=payload["method"],
        )

    @property
    def digest(self) -> str:
        return digest_of(material(self.to_dict(), ("evaluation_count",)))


def reconstruct_local_sensitivity(
    calibration: CalibrationResult,
    observations: ObservationSet,
    forward: ForwardEvaluator,
    *,
    relative_step: float = DEFAULT_RELATIVE_STEP,
) -> LocalSensitivity:
    """Finite-difference Jacobian at the calibrated estimate, in inference coordinates, shown to be stable.

    Each column starts at ``relative_step`` times the declared bound range in inference coordinates, one-sided
    where a central step would leave the bounds, and is refined by nested halving until two successive estimates
    agree in the sigma-weighted norm (see :func:`central_difference`). At least 4p + 1 evaluations: a column
    needs a second step before it can be shown to have converged. Raises :class:`RouteRefusedError` if the
    forward evaluator refuses a point or a derivative does not stabilize, and :class:`HybridUQError` if the
    calibration did not converge.
    """
    if not isinstance(calibration, CalibrationResult):
        raise HybridUQError("reconstruct_local_sensitivity takes a CalibrationResult")
    if not isinstance(observations, ObservationSet):
        raise HybridUQError("reconstruct_local_sensitivity takes an ObservationSet")
    if calibration.status is not CalibrationStatus.CONVERGED:
        raise HybridUQError(f"{RouteReason.CALIBRATION_NOT_CONVERGED.value}: there is no estimate to differentiate at")
    if calibration.provenance.calibration_dataset_id != observations.dataset_id:
        raise HybridUQError(
            f"the calibration was fitted to {calibration.provenance.calibration_dataset_id!r}, not to "
            f"{observations.dataset_id!r}; a sensitivity at its estimate against other data is not its sensitivity")
    if not (0.0 < float(relative_step) < 0.1):
        raise HybridUQError("relative_step must lie in (0, 0.1)")
    parameters = calibration.spec.parameters
    transforms = transforms_of(parameters)
    lower, upper = inference_bounds(parameters)
    observed, sigma = observations.numeric_vectors()
    keys = observations.keys
    units = tuple(o.value.units for o in observations.observations)
    references = tuple(o.value for o in observations.observations)
    estimate = np.asarray(calibration.estimate_vector, dtype=np.float64)

    def fun(z):
        return evaluate(forward, to_natural(z, transforms), keys, units, references)

    base, jac, steps, one_sided, evaluations = central_difference(
        fun, to_inference(estimate, transforms), lower, upper, float(relative_step), weights=sigma)
    return LocalSensitivity(
        parameter_set_digest=parameters.digest, parameter_names=parameters.names, inference_transforms=transforms,
        estimate=tuple(estimate), observation_keys=tuple(keys), observation_units=units, observed=tuple(observed),
        sigma=tuple(sigma), predicted=tuple(base), jacobian=tuple(map(tuple, jac)), steps=steps, one_sided=one_sided,
        dataset_id=observations.dataset_id, evaluation_count=evaluations, method="central_difference",
    )
