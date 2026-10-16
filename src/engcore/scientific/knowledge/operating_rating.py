"""Manufacturer operating-rating applicability.

Owner: ``engcore.scientific.knowledge``. A published operating rating is
source-bound knowledge, not a model validity domain and not a solver result.

Reused authority, and nothing beside it:

* :class:`~engcore.scientific.knowledge.source.KnowledgeSource` is the source
  identity. This module does not invent a second source record.
* :class:`~engcore.scientific.results.provenance.ProvenanceRecord` is the run
  identity. Git revision is supplied by the caller. This module does not read
  the git repository, which is the provenance contract: a missing revision is
  refused here rather than stored as null.
* :class:`~engcore.scientific.units.quantity.Quantity` holds duration, current,
  power and voltage. An absent quantity stays absent. It is never zero, and a
  stated duty word never fills it.

``ValidityDomain`` is not used. It answers whether a scientific model applies.
This module answers whether a published rating envelope covers a requested
operating condition. Reading a particular manufacturer packet format or mission
record is not done here: that adapter lives with the product system that owns
the format, outside the Scientific Core. Those are different questions, and collapsing them would
make a duration refusal look like a model failure.

The assessment does not claim physical impossibility, component failure, or a
maximum operating duration. ``OUTSIDE_DURATION_ENVELOPE`` means the requested
duration is outside the published interval.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..results.provenance import ProvenanceRecord
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity
from .source import KnowledgeSource, KnowledgeSourceClass

RATING_SCHEMA = schema_string("manufacturer_operating_rating")
REQUEST_SCHEMA = schema_string("requested_operating_condition")
ASSESSMENT_SCHEMA = schema_string("manufacturer_rating_applicability")
MISSION_SCHEMA = schema_string("manufacturer_rating_mission_assessment")

SOFTWARE_VERSION = "engcore.scientific.knowledge.operating_rating/1.0.0"

_DIGEST_SCOPES = frozenset({"source_document", "frozen_packet_record"})
_NOT_PHYSICAL = (
    "duration refusals are evidence-envelope refusals and are not a "
    "physical-impossibility finding"
)


class RatingApplicability(str, Enum):
    SUPPORTED_WITHIN_RATING = "supported_within_rating"
    OUTSIDE_DURATION_ENVELOPE = "outside_duration_envelope"
    OPERATING_POINT_NOT_ESTABLISHED = "operating_point_not_established"
    CONDITIONAL_APPLICABILITY_UNRESOLVED = "conditional_applicability_unresolved"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    OUTSIDE_STATED_LIMIT = "outside_stated_limit"


class MissionSupportability(str, Enum):
    SUPPORTED = "supported"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


def _text(value: object, label: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise InvalidScientificProblem(f"{label} must be non-empty")
    return text


def _optional_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidScientificProblem(f"{label} must be text or absent")
    text = value.strip()
    if not text:
        raise InvalidScientificProblem(f"{label} is blank; absence is null, not an empty string")
    return text


def _time_quantity(value: Quantity | None, label: str) -> Quantity | None:
    if value is None:
        return None
    if not isinstance(value, Quantity) or not value.is_compatible_with("second"):
        raise InvalidScientificProblem(f"{label} must be a time Quantity or absent")
    if value.magnitude_in("second") < 0:
        raise InvalidScientificProblem(f"{label} duration cannot be negative")
    return value


def _optional_quantity(value: Quantity | None, unit: str, label: str) -> Quantity | None:
    if value is None:
        return None
    if not isinstance(value, Quantity) or not value.is_compatible_with(unit):
        raise InvalidScientificProblem(f"{label} must be a {unit} Quantity or absent")
    if value.magnitude_in(unit) < 0:
        raise InvalidScientificProblem(f"{label} cannot be negative")
    return value


def _quantity_dict(value: Quantity | None) -> dict[str, Any] | None:
    return None if value is None else value.to_dict()


def _quantity_from(payload: object) -> Quantity | None:
    if payload is None:
        return None
    if not isinstance(payload, Mapping):
        raise InvalidScientificProblem("a serialized quantity must be an object or null")
    return Quantity.from_dict(payload)


def _canonical_digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _seconds(value: Quantity) -> float:
    return float(value.magnitude_in("second"))


def _exceeds(stated: Quantity | None, requested: Quantity | None, is_maximum: bool) -> bool:
    if not is_maximum or stated is None or requested is None:
        return False
    if not requested.is_compatible_with(stated):
        raise InvalidScientificProblem(
            "a requested limit is not dimensionally compatible with the published rating"
        )
    return float(requested.magnitude_in(stated.units)) > float(stated.magnitude)


@dataclass(frozen=True)
class ManufacturerOperatingRating:
    """One published operating envelope. Absent fields stay absent."""

    source: KnowledgeSource
    source_digest_scope: str
    component_id: str
    manufacturer: str
    rating_type: str
    rating_id: str
    duration: Quantity | None = None
    current: Quantity | None = None
    power: Quantity | None = None
    voltage: Quantity | None = None
    current_is_maximum: bool = False
    power_is_maximum: bool = False
    cooling_requirement: str | None = None
    temperature_qualifier: str | None = None
    environment_qualifier: str | None = None
    stated_duty: str | None = None
    limit_conflict: bool = False
    undated_magnitude: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.source, KnowledgeSource):
            raise InvalidScientificProblem("a manufacturer rating binds a KnowledgeSource")
        scope = _text(self.source_digest_scope, "source digest scope")
        if scope not in _DIGEST_SCOPES:
            raise InvalidScientificProblem(
                "source digest scope is source_document or frozen_packet_record"
            )
        object.__setattr__(self, "source_digest_scope", scope)
        object.__setattr__(self, "component_id", _text(self.component_id, "component id"))
        manufacturer = _text(self.manufacturer, "manufacturer")
        if manufacturer != self.source.issuer:
            raise InvalidScientificProblem(
                "manufacturer must be the KnowledgeSource issuer; the source record is the identity"
            )
        object.__setattr__(self, "manufacturer", manufacturer)
        object.__setattr__(self, "rating_type", _text(self.rating_type, "rating type"))
        object.__setattr__(self, "rating_id", _text(self.rating_id, "rating id"))
        object.__setattr__(self, "duration", _time_quantity(self.duration, "published duration"))
        object.__setattr__(self, "current", _optional_quantity(self.current, "ampere", "published current"))
        object.__setattr__(self, "power", _optional_quantity(self.power, "watt", "published power"))
        object.__setattr__(self, "voltage", _optional_quantity(self.voltage, "volt", "published voltage"))
        if not isinstance(self.current_is_maximum, bool) or not isinstance(self.power_is_maximum, bool):
            raise InvalidScientificProblem("a maximum-limit flag must be a boolean")
        object.__setattr__(self, "cooling_requirement", _optional_text(self.cooling_requirement, "cooling requirement"))
        object.__setattr__(self, "temperature_qualifier", _optional_text(self.temperature_qualifier, "temperature qualifier"))
        object.__setattr__(self, "environment_qualifier", _optional_text(self.environment_qualifier, "environment qualifier"))
        object.__setattr__(self, "stated_duty", _optional_text(self.stated_duty, "stated duty"))
        if not isinstance(self.limit_conflict, bool) or not isinstance(self.undated_magnitude, bool):
            raise InvalidScientificProblem("limit flags must be booleans")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": RATING_SCHEMA,
            "source": self.source.to_dict(),
            "source_digest_scope": self.source_digest_scope,
            "component_id": self.component_id,
            "manufacturer": self.manufacturer,
            "rating_type": self.rating_type,
            "rating_id": self.rating_id,
            "duration": _quantity_dict(self.duration),
            "current": _quantity_dict(self.current),
            "power": _quantity_dict(self.power),
            "voltage": _quantity_dict(self.voltage),
            "current_is_maximum": self.current_is_maximum,
            "power_is_maximum": self.power_is_maximum,
            "cooling_requirement": self.cooling_requirement,
            "temperature_qualifier": self.temperature_qualifier,
            "environment_qualifier": self.environment_qualifier,
            "stated_duty": self.stated_duty,
            "limit_conflict": self.limit_conflict,
            "undated_magnitude": self.undated_magnitude,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ManufacturerOperatingRating":
        require_schema(payload, RATING_SCHEMA)
        return cls(
            source=KnowledgeSource.from_dict(payload["source"]),
            source_digest_scope=payload["source_digest_scope"],
            component_id=payload["component_id"],
            manufacturer=payload["manufacturer"],
            rating_type=payload["rating_type"],
            rating_id=payload["rating_id"],
            duration=_quantity_from(payload["duration"]),
            current=_quantity_from(payload["current"]),
            power=_quantity_from(payload["power"]),
            voltage=_quantity_from(payload["voltage"]),
            current_is_maximum=payload["current_is_maximum"],
            power_is_maximum=payload["power_is_maximum"],
            cooling_requirement=payload["cooling_requirement"],
            temperature_qualifier=payload["temperature_qualifier"],
            environment_qualifier=payload["environment_qualifier"],
            stated_duty=payload["stated_duty"],
            limit_conflict=payload["limit_conflict"],
            undated_magnitude=payload["undated_magnitude"],
        )


@dataclass(frozen=True)
class RequestedOperatingCondition:
    requirement_id: str
    duration: Quantity | None = None
    current: Quantity | None = None
    power: Quantity | None = None
    voltage: Quantity | None = None
    cooling_condition: str | None = None
    operating_point_admission_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "requirement_id", _text(self.requirement_id, "requirement id"))
        object.__setattr__(
            self,
            "operating_point_admission_id",
            _optional_text(self.operating_point_admission_id, "operating point admission id"),
        )
        object.__setattr__(self, "duration", _time_quantity(self.duration, "required duration"))
        object.__setattr__(self, "current", _optional_quantity(self.current, "ampere", "requested current"))
        object.__setattr__(self, "power", _optional_quantity(self.power, "watt", "requested power"))
        object.__setattr__(self, "voltage", _optional_quantity(self.voltage, "volt", "requested voltage"))
        object.__setattr__(self, "cooling_condition", _optional_text(self.cooling_condition, "cooling condition"))

    @property
    def operating_point_admitted(self) -> bool:
        """A named admission plus at least one point quantity. A flag is not a point."""
        has_quantity = self.current is not None or self.power is not None or self.voltage is not None
        return self.operating_point_admission_id is not None and has_quantity

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": REQUEST_SCHEMA,
            "requirement_id": self.requirement_id,
            "duration": _quantity_dict(self.duration),
            "current": _quantity_dict(self.current),
            "power": _quantity_dict(self.power),
            "voltage": _quantity_dict(self.voltage),
            "cooling_condition": self.cooling_condition,
            "operating_point_admission_id": self.operating_point_admission_id,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RequestedOperatingCondition":
        require_schema(payload, REQUEST_SCHEMA)
        return cls(
            requirement_id=payload["requirement_id"],
            duration=_quantity_from(payload["duration"]),
            current=_quantity_from(payload["current"]),
            power=_quantity_from(payload["power"]),
            voltage=_quantity_from(payload["voltage"]),
            cooling_condition=payload["cooling_condition"],
            operating_point_admission_id=payload["operating_point_admission_id"],
        )


@dataclass(frozen=True)
class DimensionAssessment:
    dimension: str
    status: RatingApplicability
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"dimension": self.dimension, "status": self.status.value, "reason": self.reason}


@dataclass(frozen=True)
class ApplicabilityAssessment:
    rating_id: str
    component_id: str
    requirement_id: str
    source_id: str
    source_document_digest: str
    source_digest_scope: str
    status: RatingApplicability
    reason: str
    dimensions: tuple[DimensionAssessment, ...]
    provenance: ProvenanceRecord
    rating: ManufacturerOperatingRating
    request: RequestedOperatingCondition

    def __post_init__(self) -> None:
        if self.provenance.git_commit is None:
            raise InvalidScientificProblem(
                "a rating assessment requires a caller-supplied git revision; null is not stored"
            )
        if self.rating.rating_id != self.rating_id or self.rating.component_id != self.component_id:
            raise InvalidScientificProblem("assessment identity does not match the rating it binds")
        if self.rating.source.source_id != self.source_id or self.rating.source.document_digest != self.source_document_digest:
            raise InvalidScientificProblem("assessment source identity does not match the rating source")
        if self.rating.source_digest_scope != self.source_digest_scope:
            raise InvalidScientificProblem("assessment digest scope does not match the rating")
        if self.request.requirement_id != self.requirement_id:
            raise InvalidScientificProblem("assessment requirement does not match the request")
        digest = self.provenance.metadata.get("source_document_digest")
        if digest != self.source_document_digest or self.provenance.metadata.get("component_id") != self.component_id:
            raise InvalidScientificProblem("assessment provenance does not bind the same source and component")
        if self.provenance.metadata.get("requirement_id") != self.requirement_id:
            raise InvalidScientificProblem("assessment provenance does not bind the requirement")
        if self.provenance.metadata.get("rating_id") != self.rating_id:
            raise InvalidScientificProblem("assessment provenance does not bind the rating")
        if self.provenance.metadata.get("assessment_reason") != self.reason:
            raise InvalidScientificProblem("assessment provenance reason does not match the assessment")

    def dimension(self, name: str) -> DimensionAssessment:
        found = [item for item in self.dimensions if item.dimension == name]
        if len(found) != 1:
            raise InvalidScientificProblem(f"assessment has no single {name} dimension")
        return found[0]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ASSESSMENT_SCHEMA,
            "rating_id": self.rating_id,
            "component_id": self.component_id,
            "requirement_id": self.requirement_id,
            "source_id": self.source_id,
            "source_document_digest": self.source_document_digest,
            "source_digest_scope": self.source_digest_scope,
            "status": self.status.value,
            "reason": self.reason,
            "dimensions": [item.to_dict() for item in self.dimensions],
            "provenance": self.provenance.to_dict(),
            "rating": self.rating.to_dict(),
            "request": self.request.to_dict(),
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ApplicabilityAssessment":
        require_schema(payload, ASSESSMENT_SCHEMA)
        provenance = ProvenanceRecord.from_dict(payload["provenance"])
        if provenance.git_commit is None:
            raise InvalidScientificProblem("a stored rating assessment has no git revision")
        recomputed = assess_operating_rating(
            ManufacturerOperatingRating.from_dict(payload["rating"]),
            RequestedOperatingCondition.from_dict(payload["request"]),
            run_id=provenance.run_id,
            source_revision=provenance.git_commit,
        )
        stored_dimensions = [
            (item["dimension"], item["status"], item["reason"]) for item in payload["dimensions"]
        ]
        fresh_dimensions = [
            (item.dimension, item.status.value, item.reason) for item in recomputed.dimensions
        ]
        if payload["status"] != recomputed.status.value or stored_dimensions != fresh_dimensions:
            raise InvalidScientificProblem(
                "stored applicability status is not entailed by the bound rating and request"
            )
        if payload["reason"] != recomputed.reason or payload["rating_id"] != recomputed.rating_id:
            raise InvalidScientificProblem("stored applicability identity is not entailed by the bound rating")
        return recomputed


@dataclass(frozen=True)
class ComponentRatingAssessment:
    component_id: str
    status: RatingApplicability
    assessments: tuple[ApplicabilityAssessment, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "status": self.status.value,
            "assessments": [item.to_dict() for item in self.assessments],
        }


@dataclass(frozen=True)
class MissionRatingAssessment:
    requirement_id: str
    status: MissionSupportability
    components: tuple[ComponentRatingAssessment, ...]
    reason: str
    physical_infeasibility_claimed: bool

    def __post_init__(self) -> None:
        if self.physical_infeasibility_claimed is not False:
            raise InvalidScientificProblem(
                "a rating-envelope assessment cannot claim physical infeasibility"
            )

    def component(self, component_id: str) -> ComponentRatingAssessment:
        found = [item for item in self.components if item.component_id == component_id]
        if len(found) != 1:
            raise InvalidScientificProblem(f"mission assessment has no single component {component_id}")
        return found[0]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": MISSION_SCHEMA,
            "requirement_id": self.requirement_id,
            "status": self.status.value,
            "physical_infeasibility_claimed": False,
            "reason": self.reason,
            "components": [item.to_dict() for item in self.components],
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.to_dict())


def _provenance(
    *,
    run_id: str,
    source_revision: str,
    rating: ManufacturerOperatingRating,
    request: RequestedOperatingCondition,
    reason: str,
) -> ProvenanceRecord:
    revision = _text(source_revision, "source revision")
    return ProvenanceRecord(
        run_id=_text(run_id, "run id"),
        software_version=SOFTWARE_VERSION,
        git_commit=revision,
        metadata={
            "component_id": rating.component_id,
            "requirement_id": request.requirement_id,
            "source_id": rating.source.source_id,
            "source_document_digest": rating.source.document_digest,
            "source_digest_scope": rating.source_digest_scope,
            "rating_id": rating.rating_id,
            "assessment_reason": reason,
            "operating_point_admission_id": request.operating_point_admission_id or "",
        },
    )


def _withhold(status: RatingApplicability, reason: str, incoming: RatingApplicability, incoming_reason: str) -> tuple[RatingApplicability, str]:
    """A duration refusal stays a duration refusal. Later gaps withhold support only."""
    if status is not RatingApplicability.SUPPORTED_WITHIN_RATING:
        return status, reason
    return incoming, incoming_reason


def assess_operating_rating(
    rating: ManufacturerOperatingRating,
    request: RequestedOperatingCondition,
    *,
    run_id: str,
    source_revision: str,
) -> ApplicabilityAssessment:
    """Relate one published rating to one requested condition.

    Duration is compared first. A short published interval is
    ``OUTSIDE_DURATION_ENVELOPE`` even when cooling is also unknown. A missing
    duration is ``INSUFFICIENT_EVIDENCE``, including when ``stated_duty``
    contains the word continuous. A duration that contains the request does
    not by itself support the rating: cooling conditions and the operating
    point still have to be established.
    """

    if not isinstance(rating, ManufacturerOperatingRating):
        raise InvalidScientificProblem("rating applicability requires a ManufacturerOperatingRating")
    if not isinstance(request, RequestedOperatingCondition):
        raise InvalidScientificProblem("rating applicability requires a RequestedOperatingCondition")

    dimensions: list[DimensionAssessment] = []
    if rating.duration is None or request.duration is None:
        dimensions.append(DimensionAssessment(
            "duration",
            RatingApplicability.INSUFFICIENT_EVIDENCE,
            "published duration and required duration must both be stated; a missing duration is not unlimited",
        ))
        status = RatingApplicability.INSUFFICIENT_EVIDENCE
        reason = dimensions[0].reason
    elif _seconds(rating.duration) < _seconds(request.duration):
        dimensions.append(DimensionAssessment(
            "duration",
            RatingApplicability.OUTSIDE_DURATION_ENVELOPE,
            "required duration is longer than the published rating interval",
        ))
        status = RatingApplicability.OUTSIDE_DURATION_ENVELOPE
        reason = dimensions[0].reason
    else:
        dimensions.append(DimensionAssessment(
            "duration",
            RatingApplicability.SUPPORTED_WITHIN_RATING,
            "published duration contains the required duration",
        ))
        status = RatingApplicability.SUPPORTED_WITHIN_RATING
        reason = dimensions[0].reason

    def _conditional(name: str, text: str) -> None:
        nonlocal status, reason
        dimensions.append(DimensionAssessment(
            name, RatingApplicability.CONDITIONAL_APPLICABILITY_UNRESOLVED, text
        ))
        status, reason = _withhold(
            status, reason, RatingApplicability.CONDITIONAL_APPLICABILITY_UNRESOLVED, text
        )

    if rating.cooling_requirement is not None:
        if request.cooling_condition is None:
            _conditional(
                "cooling",
                "the published rating states a cooling condition and the mission cooling condition is unknown",
            )
        else:
            _conditional(
                "cooling",
                "a stated mission cooling condition is not evidence that it meets the published cooling requirement",
            )
    if rating.temperature_qualifier is not None:
        _conditional(
            "temperature",
            "the published temperature qualifier has no admissible comparison on the request",
        )
    if rating.environment_qualifier is not None:
        _conditional(
            "environment",
            "the published environment qualifier has no admissible comparison on the request",
        )

    duration_contains = (
        rating.duration is not None
        and request.duration is not None
        and _seconds(rating.duration) >= _seconds(request.duration)
    )
    # Published limits the request was actually compared with and found within. A caller's admission id is a label,
    # not evidence: without one such comparison the operating point is not established (UNKNOWN never improves).
    compared_within: list[str] = []

    if rating.limit_conflict and duration_contains:
        conflict = DimensionAssessment(
            "stated_limit",
            RatingApplicability.INSUFFICIENT_EVIDENCE,
            "published limits of the same kind and duration disagree; neither magnitude is selected",
        )
        dimensions.append(conflict)
        status, reason = _withhold(status, reason, conflict.status, conflict.reason)
    else:
        for label, stated, requested, is_maximum in (
            ("current", rating.current, request.current, rating.current_is_maximum),
            ("power", rating.power, request.power, rating.power_is_maximum),
        ):
            if stated is None:
                if requested is not None and duration_contains:
                    _conditional(
                        label,
                        f"the requested {label} has no published {label} to compare",
                    )
                continue
            if requested is None:
                if duration_contains:
                    _conditional(
                        label,
                        f"the published {label} has no requested {label} to compare",
                    )
                continue
            if not is_maximum:
                _conditional(
                    label,
                    f"both sides state {label} and the published value is not declared a maximum",
                )
            elif _exceeds(stated, requested, True):
                exceeded = DimensionAssessment(
                    label,
                    RatingApplicability.OUTSIDE_STATED_LIMIT,
                    f"requested {label} exceeds the published maximum",
                )
                dimensions.append(exceeded)
                status, reason = _withhold(status, reason, exceeded.status, exceeded.reason)
            else:
                compared_within.append(label)

    if rating.voltage is None and request.voltage is not None and duration_contains:
        _conditional("voltage", "the requested voltage has no published voltage to compare")
    elif rating.voltage is not None and request.voltage is None and duration_contains:
        _conditional("voltage", "the published voltage has no requested voltage to compare")
    elif rating.voltage is not None and request.voltage is not None:
        request.voltage.require_compatible(rating.voltage, context="published voltage")
        if float(request.voltage.magnitude_in(rating.voltage.units)) != float(rating.voltage.magnitude):
            mismatch = DimensionAssessment(
                "voltage",
                RatingApplicability.OUTSIDE_STATED_LIMIT,
                "requested voltage differs from the published voltage",
            )
            dimensions.append(mismatch)
            status, reason = _withhold(status, reason, mismatch.status, mismatch.reason)
        else:
            compared_within.append("voltage")

    if rating.undated_magnitude and duration_contains:
        undated = DimensionAssessment(
            "undated_magnitude",
            RatingApplicability.INSUFFICIENT_EVIDENCE,
            "a stated current, power or voltage has no explicit duration and is not assigned to this envelope",
        )
        dimensions.append(undated)
        status, reason = _withhold(status, reason, undated.status, undated.reason)

    point_established = bool(
        request.operating_point_admitted and compared_within and not rating.limit_conflict
    )
    if duration_contains:
        if point_established:
            dimensions.append(DimensionAssessment(
                "operating_point",
                RatingApplicability.SUPPORTED_WITHIN_RATING,
                "the request names an admission id and its " + ", ".join(compared_within)
                + " lie within the published limits",
            ))
        else:
            dimensions.append(DimensionAssessment(
                "operating_point",
                RatingApplicability.OPERATING_POINT_NOT_ESTABLISHED,
                "duration containment does not establish the requested operating point: no requested quantity was "
                "compared with a published limit of the same kind and found within it",
            ))
    if (
        duration_contains
        and not point_established
        and status is not RatingApplicability.OUTSIDE_DURATION_ENVELOPE
    ):
        status = RatingApplicability.OPERATING_POINT_NOT_ESTABLISHED
        reason = "duration containment does not establish the requested operating point"

    return ApplicabilityAssessment(
        rating_id=rating.rating_id,
        component_id=rating.component_id,
        requirement_id=request.requirement_id,
        source_id=rating.source.source_id,
        source_document_digest=rating.source.document_digest,
        source_digest_scope=rating.source_digest_scope,
        status=status,
        reason=reason,
        dimensions=tuple(dimensions),
        provenance=_provenance(
            run_id=run_id,
            source_revision=source_revision,
            rating=rating,
            request=request,
            reason=reason,
        ),
        rating=rating,
        request=request,
    )


def _component_status(assessments: tuple[ApplicabilityAssessment, ...]) -> RatingApplicability:
    statuses = {item.status for item in assessments}
    if RatingApplicability.SUPPORTED_WITHIN_RATING in statuses:
        return RatingApplicability.SUPPORTED_WITHIN_RATING
    for candidate in (
        RatingApplicability.OPERATING_POINT_NOT_ESTABLISHED,
        RatingApplicability.CONDITIONAL_APPLICABILITY_UNRESOLVED,
        RatingApplicability.INSUFFICIENT_EVIDENCE,
        RatingApplicability.OUTSIDE_STATED_LIMIT,
        RatingApplicability.OUTSIDE_DURATION_ENVELOPE,
    ):
        if candidate in statuses:
            return candidate
    return RatingApplicability.INSUFFICIENT_EVIDENCE


def assess_operating_ratings(
    ratings: tuple[ManufacturerOperatingRating, ...] | list[ManufacturerOperatingRating],
    request: RequestedOperatingCondition,
    *,
    run_id: str,
    source_revision: str,
) -> MissionRatingAssessment:
    """A mission is supported only when one rating establishes every required dimension.

    Composition is any-of: each ``component_id`` is an alternative candidate for the
    same requirement, so one supported candidate supports the mission. This function
    does not express all-of composition (a system that needs every listed part at
    once); a caller with jointly required parts must assess each part's requirement
    separately and must not read this result as support for their combination.

    Ratings that fall outside a published duration do not combine into a
    physical-impossibility claim. A sibling rating whose duration contains the
    mission, but whose operating point is not established, keeps the mission
    at ``INSUFFICIENT_EVIDENCE``.
    """

    grouped: dict[str, list[ApplicabilityAssessment]] = {}
    for rating in ratings:
        assessment = assess_operating_rating(
            rating, request, run_id=run_id, source_revision=source_revision
        )
        grouped.setdefault(rating.component_id, []).append(assessment)
    components = tuple(
        ComponentRatingAssessment(
            component_id,
            _component_status(tuple(grouped[component_id])),
            tuple(grouped[component_id]),
        )
        for component_id in sorted(grouped)
    )
    if any(item.status is RatingApplicability.SUPPORTED_WITHIN_RATING for item in components):
        status = MissionSupportability.SUPPORTED
        reason = "at least one candidate establishes every required rating dimension"
    else:
        status = MissionSupportability.INSUFFICIENT_EVIDENCE
        parts = ", ".join(f"{item.component_id}={item.status.value}" for item in components) or "no ratings"
        reason = f"no supplied rating establishes every required dimension ({parts}); {_NOT_PHYSICAL}"
    return MissionRatingAssessment(
        requirement_id=request.requirement_id,
        status=status,
        components=components,
        reason=reason,
        physical_infeasibility_claimed=False,
    )
