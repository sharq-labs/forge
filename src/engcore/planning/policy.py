"""Explicit planner preferences. Nothing is selected from registry order."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..scientific.results.immutable import freeze
from ..scientific.serialization import require_schema, schema_string

PLANNER_POLICY_SCHEMA = schema_string("scientific_planner_policy")


@dataclass(frozen=True)
class PlannerPolicy:
    capability_by_qoi: Mapping[str, str] = field(default_factory=dict)
    realization_by_model: Mapping[str, str] = field(default_factory=dict)
    solver_by_realization: Mapping[str, str] = field(default_factory=dict)
    blueprint_by_capability: Mapping[str, str] = field(default_factory=dict)
    allow_fidelity_downgrade: bool = False

    def __post_init__(self) -> None:
        for label in (
            "capability_by_qoi",
            "realization_by_model",
            "solver_by_realization",
            "blueprint_by_capability",
        ):
            raw = dict(getattr(self, label))
            clean = {}
            for key, value in raw.items():
                key = str(key).strip()
                value = str(value).strip()
                if not key or not value:
                    raise ValueError(f"{label} keys and values must be non-empty")
                clean[key] = value
            object.__setattr__(self, label, freeze(clean))
        if not isinstance(self.allow_fidelity_downgrade, bool):
            raise ValueError("allow_fidelity_downgrade must be boolean")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PLANNER_POLICY_SCHEMA,
            "capability_by_qoi": dict(sorted(self.capability_by_qoi.items())),
            "realization_by_model": dict(sorted(self.realization_by_model.items())),
            "solver_by_realization": dict(sorted(self.solver_by_realization.items())),
            "blueprint_by_capability": dict(sorted(self.blueprint_by_capability.items())),
            "allow_fidelity_downgrade": self.allow_fidelity_downgrade,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PlannerPolicy":
        require_schema(payload, PLANNER_POLICY_SCHEMA)
        return cls(
            capability_by_qoi=dict(payload.get("capability_by_qoi", {})),
            realization_by_model=dict(payload.get("realization_by_model", {})),
            solver_by_realization=dict(payload.get("solver_by_realization", {})),
            blueprint_by_capability=dict(payload.get("blueprint_by_capability", {})),
            allow_fidelity_downgrade=payload.get("allow_fidelity_downgrade", False),
        )


__all__ = ["PLANNER_POLICY_SCHEMA", "PlannerPolicy"]
