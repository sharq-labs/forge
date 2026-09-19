"""Scientific declaration of an independently executable multiphysics participant."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity, dimensionality
from .ports import PortDefinition, PortDirection

PARTICIPANT_SCHEMA = schema_string("multiphysics_participant")


def _seconds(value: Quantity | None, *, label: str) -> Quantity | None:
    if value is None:
        return None
    if not isinstance(value, Quantity) or dimensionality(value.units) != dimensionality("second"):
        raise InvalidScientificProblem(f"{label} must be a time Quantity")
    if value.magnitude_in("second") <= 0.0:
        raise InvalidScientificProblem(f"{label} must be positive")
    return value.to("second")


@dataclass(frozen=True)
class ParticipantSpec:
    """Stable scientific/execution identity and the typed ports it exposes."""

    participant_id: str
    model_id: str
    realization_id: str
    solver_id: str
    ports: tuple[PortDefinition, ...]
    transient: bool = False
    checkpointable: bool = False
    deterministic_restore: bool = False
    event_capable: bool = False
    preferred_time_step: Quantity | None = None
    maximum_time_step: Quantity | None = None
    description: str = ""

    def __post_init__(self) -> None:
        for label in ("participant_id", "model_id", "realization_id", "solver_id"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidScientificProblem(f"participant requires non-empty {label}")
            object.__setattr__(self, label, value)

        ports = tuple(self.ports)
        if not ports or any(not isinstance(port, PortDefinition) for port in ports):
            raise InvalidScientificProblem(
                f"participant {self.participant_id!r} requires typed ports"
            )
        ids = [port.port_id for port in ports]
        if len(ids) != len(set(ids)):
            raise InvalidScientificProblem(
                f"participant {self.participant_id!r} has duplicate port ids"
            )
        object.__setattr__(self, "ports", tuple(sorted(ports, key=lambda p: p.port_id)))

        for label in ("transient", "checkpointable", "deterministic_restore", "event_capable"):
            if not isinstance(getattr(self, label), bool):
                raise InvalidScientificProblem(f"{label} must be boolean")
        if self.deterministic_restore and not self.checkpointable:
            raise InvalidScientificProblem(
                "deterministic_restore requires checkpointable=True"
            )
        if not self.transient and (
            self.preferred_time_step is not None or self.maximum_time_step is not None
        ):
            raise InvalidScientificProblem(
                "steady participant cannot declare a time step"
            )
        preferred = _seconds(self.preferred_time_step, label="preferred_time_step")
        maximum = _seconds(self.maximum_time_step, label="maximum_time_step")
        if preferred is not None and maximum is not None:
            if preferred.magnitude_in("second") > maximum.magnitude_in("second"):
                raise InvalidScientificProblem(
                    "preferred_time_step cannot exceed maximum_time_step"
                )
        object.__setattr__(self, "preferred_time_step", preferred)
        object.__setattr__(self, "maximum_time_step", maximum)
        object.__setattr__(self, "description", str(self.description).strip())

    @property
    def inputs(self) -> tuple[PortDefinition, ...]:
        return tuple(p for p in self.ports if p.direction is PortDirection.INPUT)

    @property
    def outputs(self) -> tuple[PortDefinition, ...]:
        return tuple(p for p in self.ports if p.direction is PortDirection.OUTPUT)

    def port(self, port_id: str) -> PortDefinition:
        for port in self.ports:
            if port.port_id == port_id:
                return port
        raise InvalidScientificProblem(
            f"participant {self.participant_id!r} has no port {port_id!r}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PARTICIPANT_SCHEMA,
            "participant_id": self.participant_id,
            "model_id": self.model_id,
            "realization_id": self.realization_id,
            "solver_id": self.solver_id,
            "ports": [p.to_dict() for p in self.ports],
            "transient": self.transient,
            "checkpointable": self.checkpointable,
            "deterministic_restore": self.deterministic_restore,
            "event_capable": self.event_capable,
            "preferred_time_step": None if self.preferred_time_step is None else self.preferred_time_step.to_dict(),
            "maximum_time_step": None if self.maximum_time_step is None else self.maximum_time_step.to_dict(),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ParticipantSpec":
        require_schema(payload, PARTICIPANT_SCHEMA)
        def q(name: str) -> Quantity | None:
            raw = payload.get(name)
            return None if raw is None else Quantity.from_dict(raw)
        return cls(
            participant_id=payload["participant_id"],
            model_id=payload["model_id"],
            realization_id=payload["realization_id"],
            solver_id=payload["solver_id"],
            ports=tuple(PortDefinition.from_dict(p) for p in payload["ports"]),
            transient=payload.get("transient", False),
            checkpointable=payload.get("checkpointable", False),
            deterministic_restore=payload.get("deterministic_restore", False),
            event_capable=payload.get("event_capable", False),
            preferred_time_step=q("preferred_time_step"),
            maximum_time_step=q("maximum_time_step"),
            description=payload.get("description", ""),
        )
