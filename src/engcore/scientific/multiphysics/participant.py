"""Scientific declaration of one independently executable multiphysics participant."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity, dimensionality
from .ports import PortDefinition, PortDirection

PARTICIPANT_SCHEMA = schema_string("multiphysics_participant")
_TIME_DIMENSION = dimensionality("second")


def _positive_time(value: Quantity | None, *, label: str) -> Quantity | None:
    if value is None:
        return None
    if not isinstance(value, Quantity) or value.dimensionality != _TIME_DIMENSION:
        raise InvalidScientificProblem(f"{label} must be a time Quantity")
    seconds = value.magnitude_in("second")
    if seconds <= 0.0:
        raise InvalidScientificProblem(f"{label} must be positive")
    return value.to("second")


@dataclass(frozen=True)
class ParticipantSpec:
    participant_id: str
    model_id: str
    model_version: str
    realization_id: str
    realization_version: str
    solver_id: str
    solver_version: str
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
            "realization_id",
            "realization_version",
            "solver_id",
            "solver_version",
        ):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidScientificProblem(
                    f"participant requires non-empty {label}"
                )
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
        object.__setattr__(
            self, "ports", tuple(sorted(ports, key=lambda port: port.port_id))
        )

        for label in (
            "transient",
            "checkpointable",
            "deterministic_restore",
            "event_capable",
        ):
            if not isinstance(getattr(self, label), bool):
                raise InvalidScientificProblem(f"{label} must be boolean")
        if self.deterministic_restore and not self.checkpointable:
            raise InvalidScientificProblem(
                "deterministic_restore requires checkpointable=True"
            )
        if not self.transient and (
            self.preferred_time_step is not None
            or self.maximum_time_step is not None
        ):
            raise InvalidScientificProblem(
                "steady participant cannot declare a time step"
            )

        preferred = _positive_time(
            self.preferred_time_step, label="preferred_time_step"
        )
        maximum = _positive_time(
            self.maximum_time_step, label="maximum_time_step"
        )
        if (
            preferred is not None
            and maximum is not None
            and preferred.magnitude_in("second") > maximum.magnitude_in("second")
        ):
            raise InvalidScientificProblem(
                "preferred_time_step cannot exceed maximum_time_step"
            )
        object.__setattr__(self, "preferred_time_step", preferred)
        object.__setattr__(self, "maximum_time_step", maximum)
        object.__setattr__(self, "description", str(self.description).strip())

    @property
    def inputs(self) -> tuple[PortDefinition, ...]:
        return tuple(
            port for port in self.ports if port.direction is PortDirection.INPUT
        )

    @property
    def outputs(self) -> tuple[PortDefinition, ...]:
        return tuple(
            port for port in self.ports if port.direction is PortDirection.OUTPUT
        )

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
            "model_version": self.model_version,
            "realization_id": self.realization_id,
            "realization_version": self.realization_version,
            "solver_id": self.solver_id,
            "solver_version": self.solver_version,
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
    def from_dict(cls, payload: Mapping[str, Any]) -> "ParticipantSpec":
        require_schema(payload, PARTICIPANT_SCHEMA)

        def q(name: str) -> Quantity | None:
            raw = payload.get(name)
            return None if raw is None else Quantity.from_dict(raw)

        return cls(
            participant_id=payload["participant_id"],
            model_id=payload["model_id"],
            model_version=payload["model_version"],
            realization_id=payload["realization_id"],
            realization_version=payload["realization_version"],
            solver_id=payload["solver_id"],
            solver_version=payload["solver_version"],
            ports=tuple(PortDefinition.from_dict(port) for port in payload["ports"]),
            transient=payload.get("transient", False),
            checkpointable=payload.get("checkpointable", False),
            deterministic_restore=payload.get("deterministic_restore", False),
            event_capable=payload.get("event_capable", False),
            preferred_time_step=q("preferred_time_step"),
            maximum_time_step=q("maximum_time_step"),
            description=payload.get("description", ""),
        )
