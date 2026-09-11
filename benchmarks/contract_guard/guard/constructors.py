"""Public constructors, and what they refuse.

The Contract Integrity round built omit-one-field builders for five of the six
shipped systems. ``electrical.dc`` had none, because a DC analysis is not
constructed from a flat field list: it is assembled from a netlist, and most of
what its records call an input is either a solved unknown or a declaration read
through the validity context rather than a constructor argument.

This adds the part that *is* constructor-borne -- the element values -- so the
one promise those records make at construction time ("strictly positive
resistance", "the voltage may be positive, zero or negative") is checked by
something rather than assumed.
"""

from __future__ import annotations

from engcore.scientific.units.quantity import Quantity as Q

#: Element values a DC record names that the circuit constructor carries.
DC_ELEMENT_FIELDS = ("resistance", "source_voltage", "source_current")

#: Ratings a DC record names that ``ComponentRating`` carries. Every one is
#: optional in the record, so the obligation runs the other way: the rating
#: must still construct with any of them withheld.
DC_RATING_FIELDS = (
    "rated_power",
    "rated_power_temperature",
    "zero_power_temperature",
    "maximum_working_voltage",
    "maximum_current",
    "derating_factor",
)

#: The derating line is a group, not three independent fields. The record says
#: the two temperatures are "declared together or not at all" and that both
#: "require a rated_power for the line to pass through". Withholding one member
#: alone therefore tests that coupling rule rather than the optionality of the
#: member, so the whole line is dropped when any member is the field under
#: test. (Probing them singly was an audit defect on the first pass: it read
#: the documented coupling as the record calling rated_power optional while the
#: runtime required it.)
DC_RATING_LINE = (
    "rated_power",
    "rated_power_temperature",
    "zero_power_temperature",
)

DC_FIELDS = DC_ELEMENT_FIELDS + DC_RATING_FIELDS


def dc_builder(omit: str | None) -> str:
    """Build the smallest complete DC analysis, optionally omitting one value."""
    from engcore.domains.electrical.dc.circuit import DCCircuit
    from engcore.domains.electrical.dc.components import (
        DCCurrentSource,
        DCVoltageSource,
        ElectricalNode,
        Resistor,
    )
    from engcore.domains.electrical.dc.problem import build_dc_problem

    if omit is not None and omit not in DC_FIELDS:
        return "NOT_A_CONSTRUCTOR_FIELD"

    _rating(omit)
    resistance = None if omit == "resistance" else Q(100.0, "ohm")
    voltage = None if omit == "source_voltage" else Q(5.0, "volt")
    current = None if omit == "source_current" else Q(0.01, "ampere")

    circuit = DCCircuit(
        circuit_id="guard",
        nodes=(
            ElectricalNode(node_id="gnd", is_reference=True),
            ElectricalNode(node_id="a"),
            ElectricalNode(node_id="b"),
        ),
        resistors=(
            Resistor(
                component_id="R1", node_a="a", node_b="gnd", resistance=resistance
            ),
        ),
        voltage_sources=(
            DCVoltageSource(
                component_id="V1",
                positive_node="a",
                negative_node="gnd",
                voltage=voltage,
            ),
        ),
        current_sources=(
            DCCurrentSource(
                component_id="I1", from_node="gnd", to_node="b", current=current
            ),
        ),
    )
    build_dc_problem(circuit)
    return "ACCEPTED"


def _rating(omit: str | None):
    """Build a fully declared ComponentRating, optionally withholding one field."""
    from engcore.domains.electrical.dc.models import ComponentRating

    fields = {
        "rated_power": Q(0.4, "watt"),
        "rated_power_temperature": Q(343.15, "kelvin"),
        "zero_power_temperature": Q(428.15, "kelvin"),
        "maximum_working_voltage": Q(250.0, "volt"),
        "maximum_current": Q(1.0, "ampere"),
        "derating_factor": 1.0,
    }
    if omit in DC_RATING_LINE:
        for name in DC_RATING_LINE:
            fields.pop(name)
    elif omit in fields:
        fields.pop(omit)
    return ComponentRating(**fields)


def probe(system: str, field: str | None) -> str:
    """Build ``system`` with ``field`` withheld; report what the runtime did."""
    from . import prerequisites

    if system == "electrical.dc":
        try:
            return dc_builder(field)
        except Exception as exc:
            return f"REFUSED:{type(exc).__name__}"
    return prerequisites._audit_module("required_inputs").probe(system, field)
