"""Held-out model/data discrepancy estimation.

This is deliberately a *candidate* producer, not an authority that can satisfy a
claim. Calibration residuals constrain a minimum discrepancy magnitude and a
conservative compatible bound after known measurement/prediction intervals are
accounted for. Independent held-out groups must remain compatible with those
predeclared calibration constraints.

Passing this protocol does not prove the model is true and does not grant a
validation level. It produces an auditable candidate for later scientific
review/promotion. Failing or incomplete data remain fail-closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from ...scientific.results.uncertainty import Uncertainty, UncertaintyKind, UncertaintySource
from ...scientific.units.quantity import Quantity, dimensionality
from .._records import tagged_digest
from ..errors import ClaimContractError
from ..measurement_dataset import DatasetSplit

_PROTOCOL_TAG = "crafty.claims.discrepancy_protocol/1"
_ESTIMATE_TAG = "crafty.claims.model_form_discrepancy_estimate/1"


class ModelFormDiscrepancyError(ClaimContractError):
    """The discrepancy study cannot support the statement it is being asked to make."""


class DiscrepancyEstimateStatus(str, Enum):
    INSUFFICIENT_DATA = "insufficient_data"
    INSUFFICIENT_UNCERTAINTY = "insufficient_uncertainty"
    CALIBRATED_UNVALIDATED = "calibrated_unvalidated"
    FAILED_VALIDATION = "failed_validation"
    UNRESOLVED_BELOW_KNOWN_UNCERTAINTY = "unresolved_below_known_uncertainty"
    VALIDATED_CANDIDATE = "validated_candidate"


@dataclass(frozen=True)
class DiscrepancyProtocol:
    """Predeclared acceptance protocol; a method choice, never evidence."""

    protocol_id: str
    minimum_calibration_groups: int
    minimum_validation_groups: int
    require_all_holdout_compatible: bool = True

    def __post_init__(self) -> None:
        if not str(self.protocol_id).strip():
            raise ModelFormDiscrepancyError("discrepancy protocol needs a non-empty protocol_id")
        for label in ("minimum_calibration_groups", "minimum_validation_groups"):
            value = int(getattr(self, label))
            if value < 1:
                raise ModelFormDiscrepancyError(f"{label} must be at least 1")
            object.__setattr__(self, label, value)
        if self.require_all_holdout_compatible is not True:
            raise ModelFormDiscrepancyError(
                "this foundation supports only the fail-closed rule that every held-out group remains compatible with the calibration constraints"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_id": self.protocol_id,
            "minimum_calibration_groups": self.minimum_calibration_groups,
            "minimum_validation_groups": self.minimum_validation_groups,
            "require_all_holdout_compatible": self.require_all_holdout_compatible,
            "method": "interval-constrained residual bounds with independent-group holdout",
            "notice": "the protocol sets an acceptance rule; it is not scientific evidence",
        }

    @property
    def digest(self) -> str:
        return tagged_digest(_PROTOCOL_TAG, self.to_dict())


@dataclass(frozen=True)
class PairedObservation:
    """A prediction and independent observation at one exact bound context."""

    observation_id: str
    independence_group: str
    split: DatasetSplit
    quantity: str
    observed: Quantity
    predicted: Quantity
    measurement_uncertainty: Uncertainty
    prediction_uncertainties: tuple[Uncertainty, ...]
    context_digest: str
    measurement_digest: str

    def __post_init__(self) -> None:
        for label in ("observation_id", "independence_group", "quantity", "context_digest", "measurement_digest"):
            if not str(getattr(self, label)).strip():
                raise ModelFormDiscrepancyError(f"{label} must be non-empty")
        object.__setattr__(self, "split", DatasetSplit(self.split))
        if not isinstance(self.observed, Quantity) or not isinstance(self.predicted, Quantity):
            raise ModelFormDiscrepancyError("observed and predicted must be Quantity records")
        if dimensionality(self.observed.units) != dimensionality(self.predicted.units):
            raise ModelFormDiscrepancyError("observed and predicted quantities have different dimensions")
        if not isinstance(self.measurement_uncertainty, Uncertainty):
            raise ModelFormDiscrepancyError("measurement_uncertainty must be an Uncertainty")
        predictions = tuple(self.prediction_uncertainties)
        if any(not isinstance(item, Uncertainty) for item in predictions):
            raise ModelFormDiscrepancyError("prediction_uncertainties must contain only Uncertainty records")
        object.__setattr__(self, "prediction_uncertainties", predictions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "independence_group": self.independence_group,
            "split": self.split.value,
            "quantity": self.quantity,
            "observed": self.observed.to_dict(),
            "predicted": self.predicted.to_dict(),
            "measurement_uncertainty": self.measurement_uncertainty.to_dict(),
            "prediction_uncertainties": [
                item.to_dict() for item in self.prediction_uncertainties
            ],
            "context_digest": self.context_digest,
            "measurement_digest": self.measurement_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PairedObservation":
        if not isinstance(payload, Mapping):
            raise ModelFormDiscrepancyError("paired observation must be an object")
        expected = {
            "observation_id", "independence_group", "split", "quantity",
            "observed", "predicted", "measurement_uncertainty",
            "prediction_uncertainties", "context_digest", "measurement_digest",
        }
        if set(payload) != expected:
            raise ModelFormDiscrepancyError(
                "paired observation shape mismatch"
            )
        return cls(
            observation_id=payload["observation_id"],
            independence_group=payload["independence_group"],
            split=DatasetSplit(payload["split"]),
            quantity=payload["quantity"],
            observed=Quantity.from_dict(payload["observed"]),
            predicted=Quantity.from_dict(payload["predicted"]),
            measurement_uncertainty=Uncertainty.from_dict(
                payload["measurement_uncertainty"]
            ),
            prediction_uncertainties=tuple(
                Uncertainty.from_dict(item)
                for item in payload["prediction_uncertainties"]
            ),
            context_digest=payload["context_digest"],
            measurement_digest=payload["measurement_digest"],
        )


@dataclass(frozen=True)
class ResidualPoint:
    observation_id: str
    independence_group: str
    split: DatasetSplit
    residual: float
    known_half_width: float | None
    minimum_discrepancy: float | None
    conservative_compatible_bound: float | None
    units: str
    measurement_digest: str
    problem: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "independence_group": self.independence_group,
            "split": self.split.value,
            "residual": self.residual,
            "known_half_width": self.known_half_width,
            "minimum_discrepancy": self.minimum_discrepancy,
            "conservative_compatible_bound": self.conservative_compatible_bound,
            "units": self.units,
            "measurement_digest": self.measurement_digest,
            "problem": self.problem,
        }


@dataclass(frozen=True)
class ModelFormDiscrepancyCandidate:
    """Held-out-tested discrepancy constraints, never an uncertainty record."""

    quantity: str
    units: str
    minimum_required_half_width: float
    conservative_compatible_half_width: float
    protocol_digest: str
    calibration_groups: tuple[str, ...]
    validation_groups: tuple[str, ...]
    measurement_digests: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "quantity": self.quantity,
            "units": self.units,
            "minimum_required_half_width": self.minimum_required_half_width,
            "conservative_compatible_half_width": self.conservative_compatible_half_width,
            "protocol_digest": self.protocol_digest,
            "calibration_groups": list(self.calibration_groups),
            "validation_groups": list(self.validation_groups),
            "measurement_digests": list(self.measurement_digests),
            "status": "candidate",
            "zero_established": False,
            "can_satisfy_claim": False,
            "is_uncertainty_record": False,
            "is_validation_level": False,
            "notice": (
                "held-out empirical discrepancy constraints only; the lower bound is not an uncertainty "
                "estimate and the conservative compatible bound includes known uncertainty. Promotion into "
                "MODEL_FORM requires a separate reviewed statistical or physical producer."
            ),
        }


@dataclass(frozen=True)
class ModelFormDiscrepancyEstimate:
    quantity: str
    units: str
    protocol: DiscrepancyProtocol
    status: DiscrepancyEstimateStatus
    points: tuple[ResidualPoint, ...]
    minimum_required_half_width: float | None
    conservative_compatible_half_width: float | None
    failed_validation_groups: tuple[str, ...]
    reason: str

    @property
    def candidate(self) -> ModelFormDiscrepancyCandidate | None:
        if self.status is not DiscrepancyEstimateStatus.VALIDATED_CANDIDATE:
            return None
        calibration = tuple(sorted({p.independence_group for p in self.points if p.split is DatasetSplit.CALIBRATION}))
        validation = tuple(sorted({p.independence_group for p in self.points if p.split is DatasetSplit.VALIDATION}))
        return ModelFormDiscrepancyCandidate(
            quantity=self.quantity,
            units=self.units,
            minimum_required_half_width=float(self.minimum_required_half_width),
            conservative_compatible_half_width=float(self.conservative_compatible_half_width),
            protocol_digest=self.protocol.digest,
            calibration_groups=calibration,
            validation_groups=validation,
            measurement_digests=tuple(sorted({p.measurement_digest for p in self.points})),
        )

    def to_dict(self) -> dict[str, Any]:
        candidate = self.candidate
        return {
            "quantity": self.quantity,
            "units": self.units,
            "protocol": self.protocol.to_dict(),
            "protocol_digest": self.protocol.digest,
            "status": self.status.value,
            "points": [p.to_dict() for p in self.points],
            "minimum_required_half_width": self.minimum_required_half_width,
            "conservative_compatible_half_width": self.conservative_compatible_half_width,
            "failed_validation_groups": list(self.failed_validation_groups),
            "reason": self.reason,
            "candidate": None if candidate is None else candidate.to_dict(),
            "promotes_model_form_uncertainty": False,
        }

    @property
    def digest(self) -> str:
        return tagged_digest(_ESTIMATE_TAG, self.to_dict())


def _interval_half_width(
    uncertainty: Uncertainty,
    center: Quantity,
    *,
    target_units: str,
    allowed_sources: frozenset[UncertaintySource],
) -> tuple[float | None, str | None]:
    if uncertainty.kind is not UncertaintyKind.INTERVAL:
        return None, "only explicit uncertainty intervals can constrain a residual in this foundation"
    source = UncertaintySource(uncertainty.source_kind)
    if source not in allowed_sources:
        return None, f"uncertainty source {source.value!r} is not admissible for this side of the comparison"
    try:
        lower = uncertainty.lower.to(target_units).magnitude
        upper = uncertainty.upper.to(target_units).magnitude
        value = center.to(target_units).magnitude
    except Exception as exc:
        return None, f"uncertainty interval is not compatible with {target_units}: {exc}"
    if lower > value or upper < value:
        return None, "uncertainty interval does not contain the value it is attached to"
    return max(value - lower, upper - value), None


def _point(pair: PairedObservation) -> ResidualPoint:
    observed = pair.observed.to(pair.predicted.units)
    residual = pair.predicted.magnitude - observed.magnitude

    measurement, problem = _interval_half_width(
        pair.measurement_uncertainty,
        pair.observed,
        target_units=str(pair.predicted.units),
        allowed_sources=frozenset({UncertaintySource.MEASUREMENT}),
    )
    if problem is not None:
        return ResidualPoint(
            pair.observation_id, pair.independence_group, pair.split, residual,
            None, None, None, str(pair.predicted.units), pair.measurement_digest, problem,
        )

    known = float(measurement)
    for item in pair.prediction_uncertainties:
        width, problem = _interval_half_width(
            item,
            pair.predicted,
            target_units=str(pair.predicted.units),
            allowed_sources=frozenset({UncertaintySource.NUMERICAL, UncertaintySource.PARAMETER}),
        )
        if problem is not None:
            return ResidualPoint(
                pair.observation_id, pair.independence_group, pair.split, residual,
                None, None, None, str(pair.predicted.units), pair.measurement_digest, problem,
            )
        known += float(width)

    return ResidualPoint(
        pair.observation_id,
        pair.independence_group,
        pair.split,
        residual,
        known,
        max(0.0, abs(residual) - known),
        abs(residual) + known,
        str(pair.predicted.units),
        pair.measurement_digest,
        None,
    )


def estimate_model_form_discrepancy(
    pairs: Iterable[PairedObservation],
    protocol: DiscrepancyProtocol,
) -> ModelFormDiscrepancyEstimate:
    pairs = tuple(pairs)
    if not pairs:
        raise ModelFormDiscrepancyError("a discrepancy study needs paired model/data observations")
    if len({p.observation_id for p in pairs}) != len(pairs):
        raise ModelFormDiscrepancyError("observation_id values must be unique")

    quantity = pairs[0].quantity
    units = str(pairs[0].predicted.units)
    for pair in pairs:
        if pair.quantity != quantity:
            raise ModelFormDiscrepancyError("one discrepancy study may assess only one quantity")
        if dimensionality(pair.predicted.units) != dimensionality(pairs[0].predicted.units):
            raise ModelFormDiscrepancyError("all paired predictions must have the same dimension")

    calibration_groups = {p.independence_group for p in pairs if p.split is DatasetSplit.CALIBRATION}
    validation_groups = {p.independence_group for p in pairs if p.split is DatasetSplit.VALIDATION}
    leaked = sorted(calibration_groups & validation_groups)
    if leaked:
        raise ModelFormDiscrepancyError(
            f"independence groups appear in both calibration and validation: {leaked}; row-wise leakage is not held-out validation"
        )

    points = tuple(_point(pair) for pair in pairs)
    problems = [p for p in points if p.problem is not None]
    if problems:
        return ModelFormDiscrepancyEstimate(
            quantity, units, protocol, DiscrepancyEstimateStatus.INSUFFICIENT_UNCERTAINTY,
            points, None, None, (), f"{len(problems)} paired observation(s) lack usable separated uncertainty intervals",
        )

    if len(calibration_groups) < protocol.minimum_calibration_groups:
        return ModelFormDiscrepancyEstimate(
            quantity, units, protocol, DiscrepancyEstimateStatus.INSUFFICIENT_DATA,
            points, None, None, (), (
                f"only {len(calibration_groups)} independent calibration group(s); "
                f"protocol requires {protocol.minimum_calibration_groups}"
            ),
        )

    calibration_points = [p for p in points if p.split is DatasetSplit.CALIBRATION]
    minimum_required = max(float(p.minimum_discrepancy) for p in calibration_points)
    conservative_compatible = max(float(p.conservative_compatible_bound) for p in calibration_points)

    if len(validation_groups) < protocol.minimum_validation_groups:
        return ModelFormDiscrepancyEstimate(
            quantity, units, protocol, DiscrepancyEstimateStatus.CALIBRATED_UNVALIDATED,
            points, minimum_required, conservative_compatible, (), (
                f"calibration requires at least {minimum_required:g} {units} discrepancy in the most discrepant "
                f"case and remains compatible up to {conservative_compatible:g} {units}; only "
                f"{len(validation_groups)} independent held-out group(s) are present; "
                f"protocol requires {protocol.minimum_validation_groups}"
            ),
        )

    failed = tuple(sorted({
        p.independence_group
        for p in points
        if p.split is DatasetSplit.VALIDATION
        and float(p.minimum_discrepancy) > conservative_compatible
    }))
    if failed:
        return ModelFormDiscrepancyEstimate(
            quantity, units, protocol, DiscrepancyEstimateStatus.FAILED_VALIDATION,
            points, minimum_required, conservative_compatible, failed,
            "held-out observations require more discrepancy than the conservative calibration bound permits",
        )

    if minimum_required <= 0.0:
        return ModelFormDiscrepancyEstimate(
            quantity, units, protocol,
            DiscrepancyEstimateStatus.UNRESOLVED_BELOW_KNOWN_UNCERTAINTY,
            points, minimum_required, conservative_compatible, (),
            (
                "calibration residuals are fully covered by already-known measurement/prediction uncertainty; "
                "the data may bound discrepancy below current resolution but do not establish zero model-form error"
            ),
        )

    return ModelFormDiscrepancyEstimate(
        quantity, units, protocol, DiscrepancyEstimateStatus.VALIDATED_CANDIDATE,
        points, minimum_required, conservative_compatible, (),
        (
            "the calibration discrepancy constraints survive every independent held-out group; "
            "the result remains a non-authoritative discrepancy candidate, not MODEL_FORM uncertainty"
        ),
    )


__all__ = [
    "DiscrepancyEstimateStatus",
    "DiscrepancyProtocol",
    "ModelFormDiscrepancyError",
    "ModelFormDiscrepancyEstimate",
    "ModelFormDiscrepancyCandidate",
    "PairedObservation",
    "ResidualPoint",
    "estimate_model_form_discrepancy",
]
