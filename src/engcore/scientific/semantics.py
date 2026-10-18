"""Physics-neutral declarations of quantity meaning and scalar transport.

Domain Packs own meaning identifiers and laws. These records check declaration
consistency; they confer no applicability, qualification or scientific evidence.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .composition.conversion import CONSERVATION_TOLERANCE, LossPath
from .errors import InvalidScientificProblem
from .serialization import require_schema, require_schema_any
from .units.quantity import Quantity, base_unit, dimensionality, is_ratio_scale


def _identifier(value: str) -> str:
    if (not isinstance(value, str) or value != value.strip() or ":" not in value
            or any(not part for part in value.split(":")) or any(c.isspace() for c in value)):
        raise InvalidScientificProblem("semantic meaning requires an explicit namespaced identifier")
    return value


def semantic_extension(payload: Mapping[str, Any], legacy: str, key: str) -> Any:
    """Read an exact /1-or-/2 extension without silently discarding meaning."""
    typed = legacy.rsplit("/", 1)[0] + "/2"
    version = require_schema_any(payload, (legacy, typed))
    if version == legacy:
        if key in payload:
            raise InvalidScientificProblem(f"legacy {legacy} cannot carry {key}; explicit /2 required")
        return None
    if key not in payload or payload[key] is None:
        raise InvalidScientificProblem(f"typed {typed} requires {key}")
    return payload[key]


def extend_payload(payload: dict[str, Any], key: str, record: Any) -> dict[str, Any]:
    if record is not None:
        payload["schema"] = payload["schema"].rsplit("/", 1)[0] + "/2"
        payload[key] = record.to_dict() if hasattr(record, "to_dict") else record.value
    return payload


class QuantityRole(str, Enum):
    POTENTIAL = "potential"
    EFFORT = "effort"
    FLOW = "flow"
    INTENSIVE = "intensive"
    EXTENSIVE = "extensive"
    DENSITY = "density"
    INTEGRATED = "integrated"
    OTHER = "other"


@dataclass(frozen=True)
class ConservedQuantity:
    """The exact measure balanced; amount/rate conversion is never inferred."""
    meaning_id: str
    unit: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "meaning_id", _identifier(self.meaning_id))
        if not is_ratio_scale(self.unit):
            raise InvalidScientificProblem("a conserved measure must use a ratio-scale unit")
        object.__setattr__(self, "unit", base_unit(self.unit))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": "conserved_quantity/1", "meaning_id": self.meaning_id, "unit": self.unit}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ConservedQuantity":
        require_schema(payload, "conserved_quantity/1")
        return cls(payload["meaning_id"], payload["unit"])


@dataclass(frozen=True)
class QuantitySemantics:
    meaning_id: str
    unit: str
    roles: tuple[QuantityRole, ...]
    conserved_quantity: ConservedQuantity | None = None
    other_role: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "meaning_id", _identifier(self.meaning_id))
        roles = tuple(QuantityRole(role) for role in self.roles)
        if not roles or len(set(roles)) != len(roles):
            raise InvalidScientificProblem("quantity semantics require distinct explicit roles")
        if ((QuantityRole.INTENSIVE in roles and QuantityRole.EXTENSIVE in roles)
                or (QuantityRole.DENSITY in roles and QuantityRole.INTEGRATED in roles)):
            raise InvalidScientificProblem("quantity roles declare incompatible measures")
        if QuantityRole.OTHER in roles:
            _identifier(self.other_role)
        elif self.other_role:
            raise InvalidScientificProblem("other_role requires the OTHER role")
        object.__setattr__(self, "roles", tuple(sorted(roles, key=lambda x: x.value)))
        object.__setattr__(self, "unit", base_unit(self.unit))
        if self.conserved_quantity is not None:
            if not isinstance(self.conserved_quantity, ConservedQuantity):
                raise InvalidScientificProblem("conserved quantity must be a typed declaration")
            if dimensionality(self.unit) != dimensionality(self.conserved_quantity.unit):
                raise InvalidScientificProblem("semantic quantity and conserved measure dimensions differ")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": "quantity_semantics/1", "meaning_id": self.meaning_id, "unit": self.unit,
                "roles": [role.value for role in self.roles], "other_role": self.other_role,
                "conserved_quantity": None if self.conserved_quantity is None else self.conserved_quantity.to_dict()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "QuantitySemantics":
        require_schema(payload, "quantity_semantics/1")
        raw = payload.get("conserved_quantity")
        return cls(payload["meaning_id"], payload["unit"], tuple(payload["roles"]),
                   None if raw is None else ConservedQuantity.from_dict(raw), payload.get("other_role", ""))


class TransportKind(str, Enum):
    SIGNAL = "signal"
    CONSERVED = "conserved"


@dataclass(frozen=True)
class QuantityTransport:
    """A declared scalar partition; coefficients are not measured evidence.

    LossPath's existing named fractional record is reused without granting it
    an energy interpretation. Full single-sink loss is outside its legacy range.
    """
    kind: TransportKind
    conserved_quantity: ConservedQuantity | None = None
    delivered_fraction: float | None = None
    losses: tuple[LossPath, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", TransportKind(self.kind))
        losses = tuple(self.losses)
        if any(not isinstance(loss, LossPath) for loss in losses):
            raise InvalidScientificProblem("transport losses must be existing typed LossPath records")
        if len({loss.form for loss in losses}) != len(losses):
            raise InvalidScientificProblem("transport loss destinations must be distinct")
        for loss in losses:
            _identifier(loss.form)
        object.__setattr__(self, "losses", tuple(sorted(losses, key=lambda x: x.form)))
        if self.kind is TransportKind.SIGNAL:
            if self.conserved_quantity is not None or self.delivered_fraction is not None or losses:
                raise InvalidScientificProblem("signal transport cannot claim a conserved partition")
            return
        if not isinstance(self.conserved_quantity, ConservedQuantity):
            raise InvalidScientificProblem("conserved transport requires its precise conserved measure")
        fraction = self.delivered_fraction
        if fraction is None:
            if losses:
                raise InvalidScientificProblem("UNKNOWN delivery cannot account for declared losses")
            return
        if isinstance(fraction, bool) or not isinstance(fraction, (int, float)) or not math.isfinite(fraction) or not 0 < fraction <= 1:
            raise InvalidScientificProblem("delivered fraction must be finite in (0, 1], or UNKNOWN")
        object.__setattr__(self, "delivered_fraction", float(fraction))
        if abs(math.fsum([fraction] + [loss.fraction for loss in losses]) - 1.0) > CONSERVATION_TOLERANCE:
            raise InvalidScientificProblem("transport partition does not account for all input")

    def admit(self, source: QuantitySemantics, target: QuantitySemantics) -> None:
        if source != target:
            raise InvalidScientificProblem("different quantity meanings/roles require an explicit qualified transformation participant")
        if self.conserved_quantity != source.conserved_quantity:
            raise InvalidScientificProblem("transport and port conserved meanings disagree")

    def transfer(self, value: Quantity) -> tuple[Quantity, dict[str, Quantity]]:
        if self.kind is TransportKind.SIGNAL:
            return value, {}
        if self.delivered_fraction is None:
            raise InvalidScientificProblem("transport delivery is UNKNOWN; no value is authorized")
        if (not is_ratio_scale(value.units)
                or dimensionality(value.units) != dimensionality(self.conserved_quantity.unit)):
            raise InvalidScientificProblem("transport value does not match its conserved measure")
        return value * self.delivered_fraction, {loss.form: value * loss.fraction for loss in self.losses}

    def to_dict(self) -> dict[str, Any]:
        return {"schema": "quantity_transport/1", "kind": self.kind.value,
                "conserved_quantity": None if self.conserved_quantity is None else self.conserved_quantity.to_dict(),
                "delivered_fraction": self.delivered_fraction, "losses": [loss.to_dict() for loss in self.losses]}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "QuantityTransport":
        require_schema(payload, "quantity_transport/1")
        raw = payload.get("conserved_quantity")
        return cls(payload["kind"], None if raw is None else ConservedQuantity.from_dict(raw),
                   payload.get("delivered_fraction"), tuple(LossPath.from_dict(p) for p in payload.get("losses", ())))
