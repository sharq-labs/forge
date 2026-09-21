"""Serializable identities for participant checkpoints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity, dimensionality
from ..results.uncertainty import Uncertainty
from ..units.quantity import normalize_unit

CHECKPOINT_SCHEMA = schema_string("multiphysics_checkpoint")
INITIAL_STATE_DEFINITION_SCHEMA = schema_string("multiphysics_initial_state_definition")
INITIAL_STATE_VALUE_SCHEMA = schema_string("multiphysics_initial_state_value")
INITIAL_STATE_RECEIPT_SCHEMA = schema_string("multiphysics_initial_state_receipt")
SCHEDULED_EVENT_SCHEMA = schema_string("multiphysics_scheduled_event")
REACHED_EVENT_SCHEMA = schema_string("multiphysics_reached_scheduled_event")


@dataclass(frozen=True, order=True)
class ScheduledEventRecord:
    """Requested synchronization metadata, never a physical observation."""

    event_id: str
    instant: Quantity

    def __post_init__(self) -> None:
        event_id = str(self.event_id).strip()
        if not event_id:
            raise InvalidScientificProblem("scheduled event requires event_id")
        if not isinstance(self.instant, Quantity) or dimensionality(self.instant.units) != dimensionality("second"):
            raise InvalidScientificProblem("scheduled event instant must be time")
        object.__setattr__(self, "event_id", event_id)
        object.__setattr__(self, "instant", self.instant.to("second"))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEDULED_EVENT_SCHEMA, "classification": "scheduled_synchronization_marker", "event_id": self.event_id, "instant": self.instant.to_dict()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ScheduledEventRecord":
        require_schema(payload, SCHEDULED_EVENT_SCHEMA)
        if payload.get("classification") != "scheduled_synchronization_marker":
            raise InvalidScientificProblem("scheduled event classification mismatch")
        return cls(payload["event_id"], Quantity.from_dict(payload["instant"]))


@dataclass(frozen=True, order=True)
class ReachedScheduledEvent:
    """Execution receipt for a synchronization boundary actually reached."""

    event_id: str
    instant: Quantity
    boundary_index: int

    def __post_init__(self) -> None:
        scheduled = ScheduledEventRecord(self.event_id, self.instant)
        if isinstance(self.boundary_index, bool) or int(self.boundary_index) != self.boundary_index or self.boundary_index < 0:
            raise InvalidScientificProblem("reached scheduled event boundary_index must be a non-negative integer")
        object.__setattr__(self, "event_id", scheduled.event_id)
        object.__setattr__(self, "instant", scheduled.instant)
        object.__setattr__(self, "boundary_index", int(self.boundary_index))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": REACHED_EVENT_SCHEMA, "classification": "reached_synchronization_boundary", "event_id": self.event_id, "instant": self.instant.to_dict(), "boundary_index": self.boundary_index}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReachedScheduledEvent":
        require_schema(payload, REACHED_EVENT_SCHEMA)
        if payload.get("classification") != "reached_synchronization_boundary":
            raise InvalidScientificProblem("reached event classification mismatch")
        return cls(payload["event_id"], Quantity.from_dict(payload["instant"]), payload["boundary_index"])


@dataclass(frozen=True, order=True)
class InitialStateDefinition:
    variable_id: str
    unit: str

    def __post_init__(self) -> None:
        variable_id = str(self.variable_id).strip()
        if not variable_id:
            raise InvalidScientificProblem("initial state definition requires variable_id")
        object.__setattr__(self, "variable_id", variable_id)
        object.__setattr__(self, "unit", normalize_unit(self.unit))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": INITIAL_STATE_DEFINITION_SCHEMA, "variable_id": self.variable_id, "unit": self.unit}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "InitialStateDefinition":
        require_schema(payload, INITIAL_STATE_DEFINITION_SCHEMA)
        return cls(payload["variable_id"], payload["unit"])


@dataclass(frozen=True, order=True)
class InitialStateValue:
    variable_id: str
    value: Quantity
    uncertainty: Uncertainty

    def __post_init__(self) -> None:
        variable_id = str(self.variable_id).strip()
        if not variable_id or not isinstance(self.value, Quantity) or not isinstance(self.uncertainty, Uncertainty):
            raise InvalidScientificProblem("initial state value requires id, Quantity and Uncertainty")
        for label in ("standard_uncertainty", "lower", "upper"):
            bound = getattr(self.uncertainty, label)
            if bound is not None:
                bound.require_compatible(
                    self.value.units,
                    context=f"initial state {variable_id!r} {label}",
                )
        object.__setattr__(self, "variable_id", variable_id)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": INITIAL_STATE_VALUE_SCHEMA, "variable_id": self.variable_id, "value": self.value.to_dict(), "uncertainty": self.uncertainty.to_dict()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "InitialStateValue":
        require_schema(payload, INITIAL_STATE_VALUE_SCHEMA)
        return cls(payload["variable_id"], Quantity.from_dict(payload["value"]), Uncertainty.from_dict(payload["uncertainty"]))


@dataclass(frozen=True)
class InitialStateReceipt:
    participant_id: str
    instant: Quantity
    values: tuple[InitialStateValue, ...]
    state_digest: str

    def __post_init__(self) -> None:
        participant_id = str(self.participant_id).strip()
        digest = str(self.state_digest).strip().lower()
        if not participant_id:
            raise InvalidScientificProblem("initial state receipt requires participant_id")
        if not isinstance(self.instant, Quantity) or dimensionality(self.instant.units) != dimensionality("second"):
            raise InvalidScientificProblem("initial state receipt instant must be time")
        values = tuple(self.values)
        if not values or any(not isinstance(item, InitialStateValue) for item in values):
            raise InvalidScientificProblem("initial state receipt requires values")
        if len({item.variable_id for item in values}) != len(values):
            raise InvalidScientificProblem("initial state receipt contains duplicate variables")
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise InvalidScientificProblem("initial state receipt state_digest must be sha256 hex")
        object.__setattr__(self, "participant_id", participant_id)
        object.__setattr__(self, "instant", self.instant.to("second"))
        object.__setattr__(self, "values", tuple(sorted(values)))
        object.__setattr__(self, "state_digest", digest)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": INITIAL_STATE_RECEIPT_SCHEMA, "participant_id": self.participant_id, "instant": self.instant.to_dict(), "values": [item.to_dict() for item in self.values], "state_digest": self.state_digest}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "InitialStateReceipt":
        require_schema(payload, INITIAL_STATE_RECEIPT_SCHEMA)
        return cls(payload["participant_id"], Quantity.from_dict(payload["instant"]), tuple(InitialStateValue.from_dict(item) for item in payload["values"]), payload["state_digest"])


@dataclass(frozen=True)
class CheckpointRecord:
    participant_id: str
    instant: Quantity
    state_digest: str
    deterministic_restore: bool
    provider_state_id: str = ""

    def __post_init__(self) -> None:
        participant = str(self.participant_id).strip()
        digest = str(self.state_digest).strip().lower()
        if not participant:
            raise InvalidScientificProblem("checkpoint requires participant_id")
        if not isinstance(self.instant, Quantity) or dimensionality(self.instant.units) != dimensionality("second"):
            raise InvalidScientificProblem("checkpoint instant must be time")
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise InvalidScientificProblem("checkpoint state_digest must be sha256 hex")
        if not isinstance(self.deterministic_restore, bool):
            raise InvalidScientificProblem("deterministic_restore must be boolean")
        object.__setattr__(self, "participant_id", participant)
        object.__setattr__(self, "instant", self.instant.to("second"))
        object.__setattr__(self, "state_digest", digest)
        object.__setattr__(self, "provider_state_id", str(self.provider_state_id).strip())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CHECKPOINT_SCHEMA,
            "participant_id": self.participant_id,
            "instant": self.instant.to_dict(),
            "state_digest": self.state_digest,
            "deterministic_restore": self.deterministic_restore,
            "provider_state_id": self.provider_state_id,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CheckpointRecord":
        require_schema(payload, CHECKPOINT_SCHEMA)
        return cls(
            participant_id=payload["participant_id"],
            instant=Quantity.from_dict(payload["instant"]),
            state_digest=payload["state_digest"],
            deterministic_restore=payload["deterministic_restore"],
            provider_state_id=payload.get("provider_state_id", ""),
        )
