"""The shipped records, loaded live from the code that ships them."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

DECLARING_MODULES = (
    "engcore.domains.thermal_models.lumped",
    "engcore.domains.thermal.conduction1d.problem",
    "engcore.domains.battery.models",
    "engcore.domains.electrical.dc.models",
    "engcore.domains.electrical.material",
    "engcore.domains.electrical.dc_applicability",
    "engcore.domains.kinetics.cstr.problem",
    "engcore.domains.kinetics.cstr.alternatives",
)


def system_of(model_id: str) -> str:
    return ".".join(model_id.split(".")[:2])


def shipped_models() -> list[Any]:
    """Every ScientificModelDefinition the tree ships, sorted by identity."""
    from engcore.scientific.models.definition import ScientificModelDefinition

    found: dict[tuple[str, str], Any] = {}
    for module_name in DECLARING_MODULES:
        module = importlib.import_module(module_name)
        for attr in dir(module):
            value = getattr(module, attr)
            if isinstance(value, ScientificModelDefinition):
                found[(value.model_id, value.version)] = value
    return [found[k] for k in sorted(found)]


@dataclass(frozen=True)
class ConditionRef:
    """One condition of one model, with everything a guard needs about it."""

    model_id: str
    system: str
    name: str
    condition: Any
    kind: str            # RangeCondition | CrossLimitCondition | ...
    is_derived: bool     # reads from the assembled namespace rather than declared
    minimum: float | None
    maximum: float | None
    minimum_inclusive: bool
    maximum_inclusive: bool
    units: str | None
    conservative_screen: bool
    description: str

    @property
    def ref(self) -> str:
        return f"{self.model_id}::{self.name}"


def _bound(payload, key):
    entry = payload.get(key)
    if entry is None:
        return None, None
    return float(entry["magnitude"]), str(entry["units"])


def conditions() -> list[ConditionRef]:
    """Every condition instance across every shipped model."""
    out: list[ConditionRef] = []
    for model in shipped_models():
        derived = set(model.validity.derived_quantities)
        for condition in model.validity.conditions:
            payload = condition.to_dict()
            payload.pop("schema", None)
            low, low_units = _bound(payload, "minimum")
            high, high_units = _bound(payload, "maximum")
            out.append(
                ConditionRef(
                    model_id=model.model_id,
                    system=system_of(model.model_id),
                    name=condition.name,
                    condition=condition,
                    kind=type(condition).__name__,
                    is_derived=condition.name in derived,
                    minimum=low,
                    maximum=high,
                    minimum_inclusive=bool(payload.get("minimum_inclusive", True)),
                    maximum_inclusive=bool(payload.get("maximum_inclusive", True)),
                    units=low_units or high_units,
                    conservative_screen=bool(payload.get("conservative_screen")),
                    description=payload.get("description") or "",
                )
            )
    return out


def model_by_id(model_id: str):
    for model in shipped_models():
        if model.model_id == model_id:
            return model
    raise KeyError(model_id)
