"""Participant roles owned by a cross-domain Composition Pack.

These records describe a participant role without selecting realization or
solver. They intentionally do not import the planning package: composition
authority is input to the planner, never a child of planner initialization.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..scientific.errors import InvalidScientificProblem
from ..scientific.multiphysics import ParticipantSpec, PortDefinition
from ..scientific.serialization import require_schema, schema_string
from ..scientific.units.quantity import Quantity

PARTICIPANT_ROLE_SCHEMA = schema_string(
    "composition_participant_role"
)
PARTICIPANT_BINDING_SCHEMA = schema_string(
    "composition_participant_binding"
)


@dataclass(frozen=True)
class ParticipantBinding:
    participant_id: str
    realization_id: str
    realization_version: str
    solver_id: str
    solver_version: str

    def __post_init__(self) -> None:
        for label in (
            "participant_id",
            "realization_id",
            "realization_version",
            "solver_id",
            "solver_version",
        ):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidScientificProblem(
                    f"participant binding requires {label}"
                )
            object.__setattr__(self, label, value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PARTICIPANT_BINDING_SCHEMA,
            "participant_id": self.participant_id,
            "realization_id": self.realization_id,
            "realization_version": self.realization_version,
            "solver_id": self.solver_id,
            "solver_version": self.solver_version,
        }

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "ParticipantBinding":
        require_schema(payload, PARTICIPANT_BINDING_SCHEMA)
        return cls(
            participant_id=payload["participant_id"],
            realization_id=payload["realization_id"],
            realization_version=payload["realization_version"],
            solver_id=payload["solver_id"],
            solver_version=payload["solver_version"],
        )


@dataclass(frozen=True)
class ParticipantBlueprint:
    participant_id: str
    model_id: str
    model_version: str
    adapter_id: str
    adapter_version: str
    ports: tuple[PortDefinition, ...]
    transient: bool = False
    checkpointable: bool = False
    deterministic_restore: bool = False
    event_capable: bool = False
    preferred_time_step: Quantity | None = None
    maximum_time_step: Quantity | None = None
    description: str = ""

    def __post_init__(self) -> None:
        for label in (
            "participant_id",
            "model_id",
            "model_version",
            "adapter_id",
            "adapter_version",
        ):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidScientificProblem(
                    f"participant blueprint requires {label}"
                )
            object.__setattr__(self, label, value)

        ports = tuple(self.ports)
        if not ports or any(
            not isinstance(port, PortDefinition) for port in ports
        ):
            raise InvalidScientificProblem(
                f"participant blueprint {self.participant_id!r} "
                "requires PortDefinition records"
            )
        ids = [port.port_id for port in ports]
        if len(ids) != len(set(ids)):
            raise InvalidScientificProblem(
                f"participant blueprint {self.participant_id!r} "
                "has duplicate ports"
            )
        object.__setattr__(
            self,
            "ports",
            tuple(sorted(ports, key=lambda port: port.port_id)),
        )
        object.__setattr__(
            self,
            "description",
            str(self.description).strip(),
        )

    def materialize(self, binding: Any) -> ParticipantSpec:
        if binding.participant_id != self.participant_id:
            raise InvalidScientificProblem(
                f"binding {binding.participant_id!r} cannot materialize "
                f"participant {self.participant_id!r}"
            )
        return ParticipantSpec(
            participant_id=self.participant_id,
            model_id=self.model_id,
            model_version=self.model_version,
            realization_id=binding.realization_id,
            realization_version=binding.realization_version,
            solver_id=binding.solver_id,
            solver_version=binding.solver_version,
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            ports=self.ports,
            transient=self.transient,
            checkpointable=self.checkpointable,
            deterministic_restore=self.deterministic_restore,
            event_capable=self.event_capable,
            preferred_time_step=self.preferred_time_step,
            maximum_time_step=self.maximum_time_step,
            description=self.description,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PARTICIPANT_ROLE_SCHEMA,
            "participant_id": self.participant_id,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "ports": [port.to_dict() for port in self.ports],
            "transient": self.transient,
            "checkpointable": self.checkpointable,
            "deterministic_restore": self.deterministic_restore,
            "event_capable": self.event_capable,
            "preferred_time_step": (
                None
                if self.preferred_time_step is None
                else self.preferred_time_step.to_dict()
            ),
            "maximum_time_step": (
                None
                if self.maximum_time_step is None
                else self.maximum_time_step.to_dict()
            ),
            "description": self.description,
        }

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "ParticipantBlueprint":
        require_schema(payload, PARTICIPANT_ROLE_SCHEMA)
        preferred = payload.get("preferred_time_step")
        maximum = payload.get("maximum_time_step")
        return cls(
            participant_id=payload["participant_id"],
            model_id=payload["model_id"],
            model_version=payload["model_version"],
            adapter_id=payload["adapter_id"],
            adapter_version=payload["adapter_version"],
            ports=tuple(
                PortDefinition.from_dict(item)
                for item in payload["ports"]
            ),
            transient=payload.get("transient", False),
            checkpointable=payload.get("checkpointable", False),
            deterministic_restore=payload.get(
                "deterministic_restore",
                False,
            ),
            event_capable=payload.get("event_capable", False),
            preferred_time_step=(
                None
                if preferred is None
                else Quantity.from_dict(preferred)
            ),
            maximum_time_step=(
                None
                if maximum is None
                else Quantity.from_dict(maximum)
            ),
            description=payload.get("description", ""),
        )


__all__ = [
    "PARTICIPANT_BINDING_SCHEMA",
    "PARTICIPANT_ROLE_SCHEMA",
    "ParticipantBinding",
    "ParticipantBlueprint",
]
