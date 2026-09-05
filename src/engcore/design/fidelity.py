"""D0 — generic fidelity declarations.

A fidelity rung says only that one execution class is ordered relative to
another and may require declared capabilities. Scientific meaning belongs to
the domain/system layer that binds a rung to concrete models and solvers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..scientific.errors import InvalidScientificProblem
from ..scientific.serialization import require_schema, schema_string

FIDELITY_RUNG_SCHEMA = schema_string("fidelity_rung")
FIDELITY_LADDER_SCHEMA = schema_string("fidelity_ladder")


@dataclass(frozen=True)
class FidelityRung:
    rung_id: str
    rank: int
    required_capabilities: frozenset[str] = frozenset()
    description: str = ""

    def __post_init__(self) -> None:
        rung_id = str(self.rung_id).strip()
        if not rung_id:
            raise InvalidScientificProblem("fidelity rung requires rung_id")
        if isinstance(self.rank, bool) or not isinstance(self.rank, int):
            raise InvalidScientificProblem("fidelity rung rank must be an integer")
        if self.rank < 0:
            raise InvalidScientificProblem("fidelity rung rank cannot be negative")
        capabilities = frozenset(str(item).strip() for item in self.required_capabilities)
        if any(not item for item in capabilities):
            raise InvalidScientificProblem(
                "fidelity capability identifiers must be non-empty"
            )
        object.__setattr__(self, "rung_id", rung_id)
        object.__setattr__(self, "required_capabilities", capabilities)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FIDELITY_RUNG_SCHEMA,
            "rung_id": self.rung_id,
            "rank": self.rank,
            "required_capabilities": sorted(self.required_capabilities),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FidelityRung":
        require_schema(payload, FIDELITY_RUNG_SCHEMA)
        return cls(
            rung_id=payload["rung_id"],
            rank=payload["rank"],
            required_capabilities=frozenset(payload.get("required_capabilities", ())),
            description=payload.get("description", ""),
        )


@dataclass(frozen=True)
class FidelityLadder:
    ladder_id: str
    version: str
    rungs: tuple[FidelityRung, ...]

    def __post_init__(self) -> None:
        ladder_id = str(self.ladder_id).strip()
        version = str(self.version).strip()
        if not ladder_id:
            raise InvalidScientificProblem("fidelity ladder requires ladder_id")
        if not version:
            raise InvalidScientificProblem("fidelity ladder requires version")
        rungs = tuple(self.rungs)
        if not rungs:
            raise InvalidScientificProblem("fidelity ladder requires at least one rung")
        if any(not isinstance(rung, FidelityRung) for rung in rungs):
            raise InvalidScientificProblem(
                "fidelity ladder rungs must be FidelityRung records"
            )
        ids = [rung.rung_id for rung in rungs]
        ranks = [rung.rank for rung in rungs]
        if len(ids) != len(set(ids)):
            raise InvalidScientificProblem("fidelity rung ids must be unique")
        if len(ranks) != len(set(ranks)):
            raise InvalidScientificProblem("fidelity rung ranks must be unique")

        object.__setattr__(self, "ladder_id", ladder_id)
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "rungs", tuple(sorted(rungs, key=lambda rung: rung.rank)))

    def rung(self, rung_id: str) -> FidelityRung:
        for rung in self.rungs:
            if rung.rung_id == rung_id:
                return rung
        raise InvalidScientificProblem(
            f"fidelity ladder {self.ladder_id!r} has no rung {rung_id!r}"
        )

    def next_after(self, rung_id: str) -> FidelityRung | None:
        current = self.rung(rung_id)
        for rung in self.rungs:
            if rung.rank > current.rank:
                return rung
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FIDELITY_LADDER_SCHEMA,
            "ladder_id": self.ladder_id,
            "version": self.version,
            "rungs": [rung.to_dict() for rung in self.rungs],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FidelityLadder":
        require_schema(payload, FIDELITY_LADDER_SCHEMA)
        return cls(
            ladder_id=payload["ladder_id"],
            version=payload["version"],
            rungs=tuple(
                FidelityRung.from_dict(item) for item in payload.get("rungs", ())
            ),
        )
