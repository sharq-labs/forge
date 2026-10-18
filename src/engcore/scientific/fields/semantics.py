"""Declared field measures; no ontology, physical law or normal execution."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..semantics import ConservedQuantity, QuantityRole, QuantitySemantics
from ..serialization import require_schema
from ..units.quantity import Quantity, base_unit, dimensionality, is_ratio_scale


class FieldKind(str, Enum):
    CELL_AVERAGE_DENSITY = "cell_average_density"
    CELL_INTEGRATED = "cell_integrated"
    INTENSIVE = "intensive"
    NORMAL_FLUX = "normal_flux"
    INTERFACE = "interface"


@dataclass(frozen=True)
class InterfaceConvention:
    """Positive normal component means orientation * dot(vector, normal).

    This support-bound convention alone is declarative; execution additionally
    requires an admitted InterfaceTransfer and its qualified geometry.
    It does not declare a face discretization or qualify a physical interface.
    """
    support_id: str
    support_fingerprint: str
    coordinate_frame: str
    orientation: int
    normal: tuple[float, ...]

    def __post_init__(self) -> None:
        if any(not isinstance(v, str) or not v.strip() for v in (self.support_id, self.coordinate_frame)):
            raise InvalidScientificProblem("interface requires explicit support and coordinate frame")
        if (not isinstance(self.support_fingerprint, str) or len(self.support_fingerprint) != 64
                or any(c not in "0123456789abcdef" for c in self.support_fingerprint)):
            raise InvalidScientificProblem("interface requires exact support fingerprint")
        if isinstance(self.orientation, bool) or not isinstance(self.orientation, int) or self.orientation not in (-1, 1):
            raise InvalidScientificProblem("interface orientation must explicitly be -1 or +1")
        normal = tuple(float(x) for x in self.normal)
        if (len(normal) not in (1, 2, 3) or not all(math.isfinite(x) for x in normal)
                or abs(math.fsum(x*x for x in normal) - 1.0) > 1e-12):
            raise InvalidScientificProblem("interface requires a finite unit normal")
        object.__setattr__(self, "normal", normal)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": "interface_convention/1", "support_id": self.support_id,
                "support_fingerprint": self.support_fingerprint, "coordinate_frame": self.coordinate_frame,
                "orientation": self.orientation, "normal": list(self.normal)}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "InterfaceConvention":
        require_schema(payload, "interface_convention/1")
        return cls(payload["support_id"], payload["support_fingerprint"], payload["coordinate_frame"],
                   payload["orientation"], tuple(payload["normal"]))


@dataclass(frozen=True)
class FieldSemantics:
    kind: FieldKind
    quantity: QuantitySemantics
    measure_unit: str = ""
    conserved_quantity: ConservedQuantity | None = None
    interface: InterfaceConvention | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", FieldKind(self.kind))
        if not isinstance(self.quantity, QuantitySemantics):
            raise InvalidScientificProblem("field requires typed quantity semantics")
        required_role = {FieldKind.CELL_AVERAGE_DENSITY: QuantityRole.DENSITY,
                         FieldKind.CELL_INTEGRATED: QuantityRole.INTEGRATED,
                         FieldKind.INTENSIVE: QuantityRole.INTENSIVE}.get(self.kind)
        if required_role is not None and required_role not in self.quantity.roles:
            raise InvalidScientificProblem("field kind requires its corresponding declared quantity role")
        cell = self.kind in (FieldKind.CELL_AVERAGE_DENSITY, FieldKind.CELL_INTEGRATED)
        if cell:
            if not isinstance(self.conserved_quantity, ConservedQuantity) or not self.measure_unit:
                raise InvalidScientificProblem("conserved cells require amount meaning and geometric measure")
            if not is_ratio_scale(self.measure_unit):
                raise InvalidScientificProblem("geometric measure must be ratio scale")
            measure = base_unit(self.measure_unit)
            if not any(dimensionality(measure) == dimensionality(f"m**{d}") for d in (1, 2, 3)):
                raise InvalidScientificProblem("geometric measure must be length, area or volume")
            object.__setattr__(self, "measure_unit", measure)
            amount_unit = (Quantity(1, self.quantity.unit) * Quantity(1, measure)).units if self.kind is FieldKind.CELL_AVERAGE_DENSITY else self.quantity.unit
            if dimensionality(amount_unit) != dimensionality(self.conserved_quantity.unit):
                raise InvalidScientificProblem("field kind/measure and conserved amount units disagree")
            if self.kind is FieldKind.CELL_INTEGRATED and self.quantity.conserved_quantity != self.conserved_quantity:
                raise InvalidScientificProblem("integrated quantity must name the exact conserved amount")
            if self.kind is FieldKind.CELL_AVERAGE_DENSITY and self.quantity.conserved_quantity is not None:
                raise InvalidScientificProblem("density quantity must not substitute a density for the conserved amount")
        elif self.measure_unit or self.conserved_quantity is not None:
            raise InvalidScientificProblem("only conserved cell kinds declare geometric amount measures")
        if self.kind is FieldKind.INTENSIVE and self.quantity.conserved_quantity is not None:
            raise InvalidScientificProblem("intensive mapping cannot claim a conserved amount")
        interface_kind = self.kind in (FieldKind.NORMAL_FLUX, FieldKind.INTERFACE)
        if interface_kind != isinstance(self.interface, InterfaceConvention):
            raise InvalidScientificProblem("flux/interface kinds require explicit normal and support conventions only")
        if not interface_kind and self.interface is not None:
            raise InvalidScientificProblem("cell kinds cannot carry interface conventions")

    def require_cell_mapping(self, other: "FieldSemantics", dimension: int) -> None:
        if self != other:
            raise InvalidScientificProblem("field meanings, kinds or measures differ; explicit transformation required")
        if self.kind in (FieldKind.NORMAL_FLUX, FieldKind.INTERFACE):
            raise InvalidScientificProblem("flux/interface execution requires A-4 normal/sign admission")
        if self.measure_unit and dimensionality(self.measure_unit) != dimensionality(f"m**{dimension}"):
            raise InvalidScientificProblem("declared measure does not match support dimension")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": "field_semantics/1", "kind": self.kind.value, "quantity": self.quantity.to_dict(),
                "measure_unit": self.measure_unit,
                "conserved_quantity": None if self.conserved_quantity is None else self.conserved_quantity.to_dict(),
                "interface": None if self.interface is None else self.interface.to_dict()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FieldSemantics":
        require_schema(payload, "field_semantics/1")
        cq, interface = payload.get("conserved_quantity"), payload.get("interface")
        return cls(payload["kind"], QuantitySemantics.from_dict(payload["quantity"]), payload.get("measure_unit", ""),
                   None if cq is None else ConservedQuantity.from_dict(cq),
                   None if interface is None else InterfaceConvention.from_dict(interface))
