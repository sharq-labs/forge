"""Explicit verification-planning metadata for EngineeringIntent planning.

A second route is not automatically independent.  This module therefore keeps
verification planning separate from a CapabilityDeclaration: a domain/system
pack may register candidate route pairs together with the dependency-derived
independence evidence it can defend before execution.  Runtime/artifact-backed
independence remains a stronger trust gate and is not replaced by this record.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from ..scientific.serialization import require_schema, schema_string
from ..scientific.verification.independence import IndependenceEvidence, IndependenceLevel
from ..scientific.verification.ladder import VerificationLevel, level_for_route
from ..scientific.verification.route import VerificationRouteKind

VERIFICATION_OPTION_SCHEMA = schema_string("engineering_verification_option")

_INDEPENDENCE_RANK = {
    IndependenceLevel.NONE: 0,
    IndependenceLevel.PARTIAL: 1,
    IndependenceLevel.STRONG: 2,
    IndependenceLevel.EXTERNAL: 3,
}


@dataclass(frozen=True)
class VerificationPlanningOption:
    capability_id: str
    primary_route_id: str
    verification_route_id: str
    route_kind: VerificationRouteKind
    independence: IndependenceEvidence
    basis: str

    def __post_init__(self) -> None:
        for label in ("capability_id", "primary_route_id", "verification_route_id", "basis"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise ValueError(f"verification planning option requires {label}")
            object.__setattr__(self, label, value)
        object.__setattr__(self, "route_kind", VerificationRouteKind(self.route_kind))
        if not isinstance(self.independence, IndependenceEvidence):
            raise TypeError("verification planning option requires IndependenceEvidence")
        if self.independence.pair != (self.primary_route_id, self.verification_route_id):
            raise ValueError("independence evidence is for another route pair")

    @property
    def verification_level(self) -> VerificationLevel:
        return level_for_route(self.route_kind)

    def supports_independence(self, minimum: IndependenceLevel = IndependenceLevel.STRONG) -> bool:
        return _INDEPENDENCE_RANK[self.independence.level] >= _INDEPENDENCE_RANK[IndependenceLevel(minimum)]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": VERIFICATION_OPTION_SCHEMA,
            "capability_id": self.capability_id,
            "primary_route_id": self.primary_route_id,
            "verification_route_id": self.verification_route_id,
            "route_kind": self.route_kind.value,
            "verification_level": int(self.verification_level),
            "independence": {
                "primary_route_id": self.independence.primary_route_id,
                "verification_route_id": self.independence.verification_route_id,
                "level": self.independence.level.value,
                "shared_components": list(self.independence.shared_components),
                "rationale": self.independence.rationale,
            },
            "basis": self.basis,
            "notice": (
                "planning-time independence only; runtime/artifact-backed evidence "
                "must still establish any evidentiary level"
            ),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "VerificationPlanningOption":
        require_schema(payload, VERIFICATION_OPTION_SCHEMA)
        raw = payload["independence"]
        option = cls(
            capability_id=payload["capability_id"],
            primary_route_id=payload["primary_route_id"],
            verification_route_id=payload["verification_route_id"],
            route_kind=VerificationRouteKind(payload["route_kind"]),
            independence=IndependenceEvidence(
                primary_route_id=raw["primary_route_id"],
                verification_route_id=raw["verification_route_id"],
                level=IndependenceLevel(raw["level"]),
                shared_components=tuple(raw.get("shared_components", ())),
                rationale=raw.get("rationale", ""),
            ),
            basis=payload["basis"],
        )
        if "verification_level" in payload and int(payload["verification_level"]) != int(option.verification_level):
            raise ValueError("serialized verification level disagrees with route kind")
        return option


class VerificationPlanningRegistry:
    """Deterministic route-pair declarations. No inference from route labels."""

    def __init__(self, options: Iterable[VerificationPlanningOption] = ()) -> None:
        items = tuple(options)
        if any(not isinstance(item, VerificationPlanningOption) for item in items):
            raise TypeError("VerificationPlanningRegistry accepts VerificationPlanningOption only")
        keys = [
            (item.capability_id, item.primary_route_id, item.verification_route_id)
            for item in items
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate verification planning route pair")
        self._items = tuple(
            sorted(items, key=lambda item: (item.capability_id, item.primary_route_id, item.verification_route_id))
        )

    def for_capability(self, capability_id: str, primary_route_id: str | None = None) -> tuple[VerificationPlanningOption, ...]:
        return tuple(
            item
            for item in self._items
            if item.capability_id == capability_id
            and (primary_route_id is None or item.primary_route_id == primary_route_id)
        )

    def independent_options(
        self,
        capability_id: str,
        primary_route_id: str,
        *,
        minimum: IndependenceLevel = IndependenceLevel.STRONG,
    ) -> tuple[VerificationPlanningOption, ...]:
        return tuple(
            item
            for item in self.for_capability(capability_id, primary_route_id)
            if item.supports_independence(minimum)
        )

    def __iter__(self):
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)


__all__ = [
    "VERIFICATION_OPTION_SCHEMA",
    "VerificationPlanningOption",
    "VerificationPlanningRegistry",
]
