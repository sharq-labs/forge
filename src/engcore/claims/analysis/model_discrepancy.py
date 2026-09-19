"""Held-out model/data discrepancy estimation.

This is deliberately a *candidate* producer, not an authority that can satisfy a
claim. Calibration residuals define a deterministic max-excess envelope only
after known measurement/prediction intervals are removed conservatively.
Independent held-out groups must then fit inside that envelope.

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
    require_all_holdout_within_envelope: bool = True

    def __post_init__(self) -> None:
        if not str(self.protocol_id).strip():
            raise ModelFormDiscrepancyError("discrepancy protocol needs a non-empty protocol_id")
        for label in ("minimum_calibration_groups", "minimum_validation_groups"):
            value = int(getattr(self, label))
            if value < 1:
                raise ModelFormDiscrepancyError(f"{label} must be at least 1")
            object.__setattr__(self, label, value)
        if self.require_all_holdout_within_envelope is not True:
            raise ModelFormDiscrepancyError(
                "this foundation supports only the fail-closed rule that every held-out group fits the calibrated envelope"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_id": self.protocol_id,
            "minimum_calibration_groups": self.minimum_calibration_groups,
            "minimum_validation_groups": self.minimum_validation_groups,
            "require_all_holdout_within_envelope": self.require_all_holdout_within_envelope,
            "method": "max absolute residual excess after conservative interval subtraction",
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


@dataclass(frozen=True)
class ResidualPoint:
    observation_id: str
    independence_group: str
    split: DatasetSplit
    residual: float
    known_half_width: float | None
    unexplained_excess: float | None
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
            "unexplained_excess": self.unexplained_excess,
            "units": self.units,
            "measurement_digest": self.measurement_digest,
            "problem": self.problem,
        }


@dataclass(frozen=True)
class ModelFormUncertaintyCandidate:
    """A held-out-tested empirical envelope that still requires promotion."""

    quantity: str
    units: str
    half_width: float
    protocol_digest: str
    calibration_groups: tuple[str, ...]
    validation_groups: tuple[str, ...]
    measurement_digests: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "quantity": self.quantity,
            "units": self.units,
            "half_width": self.half_width,
            "protocol_digest": self.protocol_digest,
            "calibration_groups": list(self.calibration_groups),
            "validation_groups": list(self.validation_groups),
            "measurement_digests": list(self.measurement_digests),
            "source_kind": UncertaintySource.MODEL_FORM.value,
            "status": "candidate",
            "can_satisfy_claim": False,
            "is_validation_level": False,
            "notice": (
                "held-out empirical discrepancy candidate only; promotion into an authoritative MODEL_FORM "
                "uncertainty channel requires an explicit reviewed producer and is not performed here"
            ),
        }


@dataclass(frozen=True)
class ModelFormDiscrepancyEstimate:
    quantity: str
    units: str
    protocol: DiscrepancyProtocol
    status: DiscrepancyEstimateStatus
    points: tuple[ResidualPoint, ...]
    calibrated_half_width: float | None
    failed_validation_groups: tuple[str, ...]
    reason: str

    @property
    def candidate(self) -> ModelFormUncertaintyCandidate | None:
        if self.status is not DiscrepancyEstimateStatus.VALIDATED_CANDIDATE:
            return None
        calibration = tuple(sorted({p.independence_group for p in self.points if p.split is DatasetSplit.CALIBRATION}))
        validation = tuple(sorted({p.independence_group for p in self.points if p.split is DatasetSplit.VALIDATION}))
        return ModelFormUncertaintyCandidate(
            quantity=self.quantity,
            units=self.units,
            half_width=float(self.calibrated_half_width),
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
            "calibrated_half_width": self.calibrated_half_width,
            "failed_validation_groups": list(self.failed_validation_groups),
            "reason": self.reason,
            "candidate": None if candidate is None else candidate.to_dict(),
            "promotes_model_form_uncertainty": False,
        }

    @property
    def digest(self) -> str:
        return tagged_digest(_ESTIMATE_TAG, self.to_dict())


def _interval_half_width(uncertainty: Uncertainty, center: Quantity, *, allowed_sources: frozenset[UncertaintySource]) -> tuple[float | None, str | None]:
    if uncertainty.kind is not UncertaintyKind.INTERVAL:
        return None, "only explicit uncertainty intervals can be subtracted from a residual in this foundation"
    source = UncertaintySource(uncertainty.source_kind)
    if source not in allowed_sources:
        return None, f"uncertainty source {source.value!r} is not admissible for this side of the comparison"
    try:
        lower = uncertainty.lower.to(center.units).magnitude
        upper = uncertainty.upper.to(center.units).magnitude
    except Exception as exc:
        return None, f"uncertainty interval is not compatible with {center.units}: {exc}"
    value = center.magnitude
    if lower > value or upper < value:
        return None, "uncertainty interval does not contain the value it is attached to"
    return max(value - lower, upper - value), None


def _point(pair: PairedObservation) -> ResidualPoint:
    observed = pair.observed.to(pair.predicted.units)
    residual = pair.predicted.magnitude - observed.magnitude

    measurement, problem = _interval_half_width(
        pair.measurement_uncertainty,
        pair.observed,
        allowed_sources=frozenset({UncertaintySource.MEASUREMENT}),
    )
    if problem is not None:
        return ResidualPoint(
            pair.observation_id, pair.independence_group, pair.split, residual,
            None, None, str(pair.predicted.units), pair.measurement_digest, problem,
        )

    known = float(measurement)
    for item in pair.prediction_uncertainties:
        width, problem = _interval_half_width(
            item,
            pair.predicted,
            allowed_sources=frozenset({UncertaintySource.NUMERICAL, UncertaintySource.PARAMETER}),
        )
        if problem is not None:
            return ResidualPoint(
                pair.observation_id, pair.independence_group, pair.split, residual,
                None, None, str(pair.predicted.units), pair.measurement_digest, problem,
            )
        known += float(width)

    return ResidualPoint(
        pair.observation_id,
        pair.independence_group,
        pair.split,
        residual,
        known,
        max(0.0, abs(residual) - known),
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
            points, None, (), f"{len(problems)} paired observation(s) lack usable separated uncertainty intervals",
        )

    if len(calibration_groups) < protocol.minimum_calibration_groups:
        return ModelFormDiscrepancyEstimate(
            quantity, units, protocol, DiscrepancyEstimateStatus.INSUFFICIENT_DATA,
            points, None, (), (
                f"only {len(calibration_groups)} independent calibration group(s); "
                f"protocol requires {protocol.minimum_calibration_groups}"
            ),
        )

    calibration_points = [p for p in points if p.split is DatasetSplit.CALIBRATION]
    envelope = max(float(p.unexplained_excess) for p in calibration_points)

    if len(validation_groups) < protocol.minimum_validation_groups:
        return ModelFormDiscrepancyEstimate(
            quantity, units, protocol, DiscrepancyEstimateStatus.CALIBRATED_UNVALIDATED,
            points, envelope, (), (
                f"calibration envelope is {envelope:g} {units}, but only {len(validation_groups)} independent "
                f"held-out group(s) are present; protocol requires {protocol.minimum_validation_groups}"
            ),
        )

    failed = tuple(sorted({
        p.independence_group
        for p in points
        if p.split is DatasetSplit.VALIDATION and float(p.unexplained_excess) > envelope
    }))
    if failed:
        return ModelFormDiscrepancyEstimate(
            quantity, units, protocol, DiscrepancyEstimateStatus.FAILED_VALIDATION,
            points, envelope, failed,
            "held-out observations exceed the envelope calibrated on independent groups",
        )

    if envelope <= 0.0:
        return ModelFormDiscrepancyEstimate(
            quantity, units, protocol,
            DiscrepancyEstimateStatus.UNRESOLVED_BELOW_KNOWN_UNCERTAINTY,
            points, envelope, (),
            (
                "all observed residuals are covered by already-known measurement/prediction uncertainty; "
                "that bounds unresolved model discrepancy below the current resolution but does not establish zero"
            ),
        )

    return ModelFormDiscrepancyEstimate(
        quantity, units, protocol, DiscrepancyEstimateStatus.VALIDATED_CANDIDATE,
        points, envelope, (),
        "every held-out independence group stays within the predeclared calibration envelope",
    )


__all__ = [
    "DiscrepancyEstimateStatus",
    "DiscrepancyProtocol",
    "ModelFormDiscrepancyError",
    "ModelFormDiscrepancyEstimate",
    "ModelFormUncertaintyCandidate",
    "PairedObservation",
    "ResidualPoint",
    "estimate_model_form_discrepancy",
]
