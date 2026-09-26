"""Declared time-scale hierarchy and fast/slow state ownership.

Generic infrastructure knows only ROLES (fast / operational / slow).  Which
physical phenomena and which state variables sit at which role is declared by
the domain; nothing here names a physical quantity.  The hierarchy is part of
multi-timescale execution identity: changing it changes the run digest.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..scenarios.timeline import canonical_digest
from ..scientific.errors import InvalidScientificProblem
from ..scientific.units.quantity import Quantity
from ._common import identifier, time_seconds

HIERARCHY_SCHEMA = "engcore.multiscale.scale_hierarchy/1"


class ScaleRole(str, Enum):
    #: Resolved by fast physics (e.g. coupled PDE/circuit solves).
    FAST = "fast"
    #: The operating period a representative window resolves.
    OPERATIONAL = "operational"
    #: Evolved only through explicit lifecycle / state-transition authority.
    SLOW = "slow"


_ORDER = {ScaleRole.FAST: 0, ScaleRole.OPERATIONAL: 1, ScaleRole.SLOW: 2}


@dataclass(frozen=True)
class ScaleLevel:
    level_id: str
    role: ScaleRole
    characteristic_time: Quantity
    description: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "level_id", identifier(self.level_id, "scale level_id"))
        object.__setattr__(self, "role", ScaleRole(self.role))
        if time_seconds(self.characteristic_time, "characteristic time") <= 0:
            raise InvalidScientificProblem("a scale's characteristic time must be positive")
        if not str(self.description or "").strip():
            raise InvalidScientificProblem("a scale level must say what it resolves")

    def to_dict(self) -> dict[str, Any]:
        return {"level_id": self.level_id, "role": self.role.value, "characteristic_time": self.characteristic_time.to_dict(),
                "description": self.description}


@dataclass(frozen=True)
class StateOwnership:
    """Which role owns one participant state variable (FAST or SLOW only)."""

    participant_id: str
    variable_id: str
    role: ScaleRole
    unit: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "participant_id", identifier(self.participant_id, "participant_id"))
        object.__setattr__(self, "variable_id", identifier(self.variable_id, "state variable_id"))
        role = ScaleRole(self.role)
        if role is ScaleRole.OPERATIONAL:
            raise InvalidScientificProblem("state is owned by the FAST or the SLOW scale, never by the operational period")
        object.__setattr__(self, "role", role)
        Quantity(1, self.unit)  # unit must parse

    def to_dict(self) -> dict[str, Any]:
        return {"participant_id": self.participant_id, "variable_id": self.variable_id, "role": self.role.value, "unit": self.unit}


@dataclass(frozen=True)
class ScaleHierarchy:
    hierarchy_id: str
    version: str
    levels: tuple[ScaleLevel, ...]
    state: tuple[StateOwnership, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "hierarchy_id", identifier(self.hierarchy_id, "hierarchy_id"))
        if not str(self.version or "").strip():
            raise InvalidScientificProblem("a scale hierarchy requires a version")
        levels = tuple(self.levels)
        if any(not isinstance(x, ScaleLevel) for x in levels) or len({x.level_id for x in levels}) != len(levels):
            raise InvalidScientificProblem("scale levels must be unique ScaleLevel records")
        roles = {x.role for x in levels}
        if ScaleRole.FAST not in roles or ScaleRole.SLOW not in roles:
            raise InvalidScientificProblem("a multi-timescale hierarchy declares at least one FAST and one SLOW scale")
        ordered = sorted(levels, key=lambda x: (_ORDER[x.role], time_seconds(x.characteristic_time)))
        for a, b in zip(ordered, ordered[1:]):
            if _ORDER[a.role] < _ORDER[b.role] and not time_seconds(a.characteristic_time) < time_seconds(b.characteristic_time):
                raise InvalidScientificProblem(
                    f"scale {a.level_id!r} ({a.role.value}) is not faster than {b.level_id!r} ({b.role.value})")
        object.__setattr__(self, "levels", tuple(ordered))
        state = tuple(self.state)
        keys = [(s.participant_id, s.variable_id) for s in state]
        if any(not isinstance(s, StateOwnership) for s in state) or len(set(keys)) != len(keys):
            raise InvalidScientificProblem("state ownership entries must be unique per participant variable")
        object.__setattr__(self, "state", tuple(sorted(state, key=lambda s: (s.participant_id, s.variable_id))))

    def owned(self, role: ScaleRole, participant_id: str | None = None) -> tuple[StateOwnership, ...]:
        return tuple(s for s in self.state if s.role is role and (participant_id is None or s.participant_id == participant_id))

    def role_of(self, participant_id: str, variable_id: str) -> ScaleRole:
        for s in self.state:
            if (s.participant_id, s.variable_id) == (participant_id, variable_id):
                return s.role
        raise InvalidScientificProblem(f"state {participant_id}.{variable_id} has no declared scale owner")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": HIERARCHY_SCHEMA, "hierarchy_id": self.hierarchy_id, "version": self.version,
                "levels": [x.to_dict() for x in self.levels], "state": [s.to_dict() for s in self.state]}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "ScaleHierarchy":
        if p.get("schema") != HIERARCHY_SCHEMA:
            raise InvalidScientificProblem("not a scale hierarchy payload")
        return cls(p["hierarchy_id"], p["version"],
                   tuple(ScaleLevel(x["level_id"], x["role"], Quantity.from_dict(x["characteristic_time"]), x["description"]) for x in p["levels"]),
                   tuple(StateOwnership(s["participant_id"], s["variable_id"], s["role"], s["unit"]) for s in p["state"]))
