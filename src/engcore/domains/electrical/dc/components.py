"""Typed components of a linear resistive DC circuit.

Every electrical value is a Scientific Core :class:`Quantity`, so dimensional
errors are rejected here rather than surfacing as nonsense volts deep inside
a matrix. Values are validated by *dimensionality*, never by unit string:
``1 kohm`` and ``1000 ohm`` are the same resistance, and both are accepted.

Scope: linear, steady-state, lumped, ideal independent sources. Capacitors,
inductors, nonlinear devices and dependent sources are out of V0 scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ....scientific.errors import InvalidScientificProblem
from ....scientific.serialization import require_schema, schema_string
from ....scientific.units.quantity import Quantity
from ....scientific.units.validation import require_same_dimension

NODE_SCHEMA = schema_string("electrical_dc_node")
RESISTOR_SCHEMA = schema_string("electrical_dc_resistor")
VSOURCE_SCHEMA = schema_string("electrical_dc_voltage_source")
ISOURCE_SCHEMA = schema_string("electrical_dc_current_source")

# Unit exemplars: these name a *dimension*, not a required unit string.
RESISTANCE_UNIT = "ohm"
VOLTAGE_UNIT = "volt"
CURRENT_UNIT = "ampere"
POWER_UNIT = "watt"


def _require_id(value: str, *, what: str) -> str:
    text = str(value).strip()
    if not text:
        raise InvalidScientificProblem(f"{what} requires a non-empty id")
    return text


@dataclass(frozen=True)
class ElectricalNode:
    """A circuit node.

    ``is_reference`` is explicit: the domain never promotes a node named
    ``"0"`` or ``"gnd"`` to ground by convention. A hidden datum choice is
    exactly the kind of silent assumption that makes results unauditable.
    """

    node_id: str
    label: str = ""
    is_reference: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "node_id", _require_id(self.node_id, what="node")
        )
        object.__setattr__(self, "is_reference", bool(self.is_reference))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": NODE_SCHEMA,
            "node_id": self.node_id,
            "label": self.label,
            "is_reference": self.is_reference,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ElectricalNode":
        require_schema(payload, NODE_SCHEMA)
        return cls(
            node_id=payload["node_id"],
            label=payload.get("label", ""),
            is_reference=bool(payload.get("is_reference", False)),
        )


@dataclass(frozen=True)
class Resistor:
    """An ideal linear resistor between two distinct nodes.

    Sign convention (fixed for the whole domain):

    * ``V_ab = V(node_a) - V(node_b)``
    * ``I_ab = V_ab / R``, positive when current flows ``node_a -> node_b``
    * ``P = V_ab * I_ab = I_ab**2 * R``, always non-negative (absorbed)
    """

    component_id: str
    node_a: str
    node_b: str
    resistance: Quantity

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "component_id",
            _require_id(self.component_id, what="resistor"),
        )
        object.__setattr__(self, "node_a", _require_id(self.node_a, what="node_a"))
        object.__setattr__(self, "node_b", _require_id(self.node_b, what="node_b"))

        if self.node_a == self.node_b:
            raise InvalidScientificProblem(
                f"resistor {self.component_id!r} connects node "
                f"{self.node_a!r} to itself"
            )
        if not isinstance(self.resistance, Quantity):
            raise InvalidScientificProblem(
                f"resistor {self.component_id!r} resistance must be a Quantity"
            )
        require_same_dimension(
            self.resistance, RESISTANCE_UNIT,
            context=f"resistor {self.component_id!r} resistance",
        )
        ohms = self.resistance.magnitude_in(RESISTANCE_UNIT)
        if ohms <= 0.0:
            # A zero resistance is a short (an ideal 0 V source) and a
            # negative resistance is an active device; both need a different
            # formulation than the conductance stamp used here.
            raise InvalidScientificProblem(
                f"resistor {self.component_id!r} requires resistance > 0, "
                f"got {self.resistance} (zero/negative resistance is outside "
                f"Electrical DC V0 scope)"
            )

    @property
    def resistance_ohm(self) -> float:
        return self.resistance.magnitude_in(RESISTANCE_UNIT)

    @property
    def conductance_siemens(self) -> float:
        return 1.0 / self.resistance_ohm

    @property
    def nodes(self) -> tuple[str, str]:
        return (self.node_a, self.node_b)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": RESISTOR_SCHEMA,
            "component_id": self.component_id,
            "node_a": self.node_a,
            "node_b": self.node_b,
            "resistance": self.resistance.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Resistor":
        require_schema(payload, RESISTOR_SCHEMA)
        return cls(
            component_id=payload["component_id"],
            node_a=payload["node_a"],
            node_b=payload["node_b"],
            resistance=Quantity.from_dict(payload["resistance"]),
        )


@dataclass(frozen=True)
class DCVoltageSource:
    """An ideal independent DC voltage source.

    Constraint imposed: ``V(positive_node) - V(negative_node) = voltage``.

    Branch-current convention: the MNA unknown ``I`` for this source is the
    current *leaving* ``positive_node`` through the source. A source
    delivering power to the circuit therefore reports a negative ``I``.
    Absorbed power is ``P = (V_p - V_n) * I``, negative when delivering.

    The voltage may be positive, zero or negative.
    """

    component_id: str
    positive_node: str
    negative_node: str
    voltage: Quantity

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "component_id",
            _require_id(self.component_id, what="voltage source"),
        )
        object.__setattr__(
            self, "positive_node",
            _require_id(self.positive_node, what="positive_node"),
        )
        object.__setattr__(
            self, "negative_node",
            _require_id(self.negative_node, what="negative_node"),
        )
        if self.positive_node == self.negative_node:
            raise InvalidScientificProblem(
                f"voltage source {self.component_id!r} connects node "
                f"{self.positive_node!r} to itself"
            )
        if not isinstance(self.voltage, Quantity):
            raise InvalidScientificProblem(
                f"voltage source {self.component_id!r} voltage must be a "
                f"Quantity"
            )
        require_same_dimension(
            self.voltage, VOLTAGE_UNIT,
            context=f"voltage source {self.component_id!r} voltage",
        )

    @property
    def voltage_volt(self) -> float:
        return self.voltage.magnitude_in(VOLTAGE_UNIT)

    @property
    def nodes(self) -> tuple[str, str]:
        return (self.positive_node, self.negative_node)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": VSOURCE_SCHEMA,
            "component_id": self.component_id,
            "positive_node": self.positive_node,
            "negative_node": self.negative_node,
            "voltage": self.voltage.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DCVoltageSource":
        require_schema(payload, VSOURCE_SCHEMA)
        return cls(
            component_id=payload["component_id"],
            positive_node=payload["positive_node"],
            negative_node=payload["negative_node"],
            voltage=Quantity.from_dict(payload["voltage"]),
        )


@dataclass(frozen=True)
class DCCurrentSource:
    """An ideal independent DC current source.

    Convention: positive ``current`` flows **from_node -> to_node inside the
    source**, so externally it is extracted at ``from_node`` and injected at
    ``to_node``.

    Absorbed power is ``P = (V_from - V_to) * current`` (passive sign
    convention: current enters the element at ``from_node``), negative when
    the source delivers power.

    The current may be positive, zero or negative.
    """

    component_id: str
    from_node: str
    to_node: str
    current: Quantity

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "component_id",
            _require_id(self.component_id, what="current source"),
        )
        object.__setattr__(
            self, "from_node", _require_id(self.from_node, what="from_node")
        )
        object.__setattr__(
            self, "to_node", _require_id(self.to_node, what="to_node")
        )
        if self.from_node == self.to_node:
            raise InvalidScientificProblem(
                f"current source {self.component_id!r} connects node "
                f"{self.from_node!r} to itself"
            )
        if not isinstance(self.current, Quantity):
            raise InvalidScientificProblem(
                f"current source {self.component_id!r} current must be a "
                f"Quantity"
            )
        require_same_dimension(
            self.current, CURRENT_UNIT,
            context=f"current source {self.component_id!r} current",
        )

    @property
    def current_ampere(self) -> float:
        return self.current.magnitude_in(CURRENT_UNIT)

    @property
    def nodes(self) -> tuple[str, str]:
        return (self.from_node, self.to_node)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ISOURCE_SCHEMA,
            "component_id": self.component_id,
            "from_node": self.from_node,
            "to_node": self.to_node,
            "current": self.current.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DCCurrentSource":
        require_schema(payload, ISOURCE_SCHEMA)
        return cls(
            component_id=payload["component_id"],
            from_node=payload["from_node"],
            to_node=payload["to_node"],
            current=Quantity.from_dict(payload["current"]),
        )
