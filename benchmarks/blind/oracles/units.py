"""Unit handling for the blind challenge oracles. Independent of Forge.

**Why this exists rather than `pint`, and rather than `engcore.scientific.units`.**

The oracle layer's job is to be wrong in different ways from the thing it
measures. Forge canonicalises units through ``pint``; an oracle that did the
same would share every conversion bug pint has, and a challenge case whose unit
handling was wrong in both would score as agreement. So this module parses the
exact unit vocabulary the challenge generator emits, and nothing else, against a
table written out by hand from SI definitions.

**Deliberately not general.** There is no unit algebra here: no multiplication of
units, no dimensional inference, no registry a caller can extend. A unit string
the table does not name is a hard failure rather than a best guess, because the
one thing worse than an oracle that cannot read a case is an oracle that reads it
as something else. The generator and this table are checked against each other
before a freeze (`assert_vocabulary_closed`), so a generator that starts emitting
a new unit cannot silently reach an oracle that does not know it.

Offsets are the reason ``convert`` is not a multiplication. degC and degF are
affine, not linear, so a temperature *difference* and a temperature *point*
convert differently — and conflating them is a classic error that a linear-only
converter cannot even express. Difference units are named separately
(``delta_degC``) and the two never share a code path.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "ORACLE_UNIT_TABLE_VERSION",
    "UnknownUnitError",
    "Q",
    "parse",
    "to_si",
    "assert_vocabulary_closed",
]

ORACLE_UNIT_TABLE_VERSION = "blind-units/1.0.0"


class UnknownUnitError(ValueError):
    """A unit string outside the table. Never defaulted, never guessed."""


#: unit -> (dimension, factor to SI, offset to SI).  value_si = value*factor + offset
#: Factors are written from the SI definitions, not derived from another table.
_UNITS: dict[str, tuple[str, float, float]] = {
    # dimensionless
    "dimensionless": ("1", 1.0, 0.0),
    "": ("1", 1.0, 0.0),
    "percent": ("1", 0.01, 0.0),
    # electrical potential
    "volt": ("V", 1.0, 0.0),
    "millivolt": ("V", 1e-3, 0.0),
    "kilovolt": ("V", 1e3, 0.0),
    # current
    "ampere": ("A", 1.0, 0.0),
    "milliampere": ("A", 1e-3, 0.0),
    # resistance
    "ohm": ("ohm", 1.0, 0.0),
    "milliohm": ("ohm", 1e-3, 0.0),
    "kilohm": ("ohm", 1e3, 0.0),
    "megohm": ("ohm", 1e6, 0.0),
    # power
    "watt": ("W", 1.0, 0.0),
    "milliwatt": ("W", 1e-3, 0.0),
    "kilowatt": ("W", 1e3, 0.0),
    # energy
    "joule": ("J", 1.0, 0.0),
    # absolute temperature (affine)
    "kelvin": ("K", 1.0, 0.0),
    "degC": ("K", 1.0, 273.15),
    "degF": ("K", 5.0 / 9.0, 255.3722222222222),  # (F - 32)*5/9 + 273.15
    # temperature DIFFERENCE (linear) — a separate dimension on purpose
    "delta_degC": ("dK", 1.0, 0.0),
    "delta_degF": ("dK", 5.0 / 9.0, 0.0),
    "kelvin_difference": ("dK", 1.0, 0.0),
    # time
    "second": ("s", 1.0, 0.0),
    "minute": ("s", 60.0, 0.0),
    "hour": ("s", 3600.0, 0.0),
    "millisecond": ("s", 1e-3, 0.0),
    # length
    "meter": ("m", 1.0, 0.0),
    "millimeter": ("m", 1e-3, 0.0),
    "centimeter": ("m", 1e-2, 0.0),
    "micrometer": ("m", 1e-6, 0.0),
    # area / volume
    "meter**2": ("m2", 1.0, 0.0),
    "millimeter**2": ("m2", 1e-6, 0.0),
    "meter**3": ("m3", 1.0, 0.0),
    "centimeter**3": ("m3", 1e-6, 0.0),
    # charge
    "ampere_hour": ("Ah", 1.0, 0.0),
    "milliampere_hour": ("Ah", 1e-3, 0.0),
    "coulomb": ("Ah", 1.0 / 3600.0, 0.0),
    # composite engineering units the challenge emits
    "watt/kelvin": ("W/K", 1.0, 0.0),
    "milliwatt/kelvin": ("W/K", 1e-3, 0.0),
    "joule/kelvin": ("J/K", 1.0, 0.0),
    "watt/meter/kelvin": ("W/m/K", 1.0, 0.0),
    "watt/meter**2/kelvin": ("W/m2/K", 1.0, 0.0),
    "1/kelvin": ("1/K", 1.0, 0.0),
    "1/second": ("1/s", 1.0, 0.0),
    # A C-rate is published as `1/hour` and means "of the nominal capacity per
    # hour". It is normalised to 1/s like every other reciprocal time, and the
    # battery oracle puts it back on the per-hour axis where it compares it to
    # an operating rate, rather than carrying a second time convention here.
    "1/hour": ("1/s", 1.0 / 3600.0, 0.0),
    "1/minute": ("1/s", 1.0 / 60.0, 0.0),
    "meter**2/second": ("m2/s", 1.0, 0.0),
    "meter/second": ("m/s", 1.0, 0.0),
    "mole/meter**3": ("mol/m3", 1.0, 0.0),
    "mole/liter": ("mol/m3", 1000.0, 0.0),
    "joule/mole": ("J/mol", 1.0, 0.0),
    "kilojoule/mole": ("J/mol", 1e3, 0.0),
    "joule/mole/kelvin": ("J/mol/K", 1.0, 0.0),
    "joule/kilogram/kelvin": ("J/kg/K", 1.0, 0.0),
    "kilogram/meter**3": ("kg/m3", 1.0, 0.0),
    "joule/meter**3": ("J/m3", 1.0, 0.0),
}


@dataclass(frozen=True)
class Q:
    """A magnitude in SI, remembering the dimension it was read as.

    Not a general quantity type: it cannot be multiplied or divided by another
    ``Q``. Oracles do their algebra on plain floats in SI, which keeps the
    arithmetic readable and stops this class from growing into the unit library
    it exists to avoid being.
    """

    si: float
    dimension: str

    def in_dim(self, dimension: str) -> float:
        if self.dimension != dimension:
            raise UnknownUnitError(
                f"quantity is {self.dimension!r}, asked for {dimension!r}"
            )
        return self.si


def parse(text: str) -> Q:
    """``"12.5 volt"`` -> ``Q(12.5, 'V')``. The unit is mandatory."""
    if not isinstance(text, str):
        raise UnknownUnitError(f"expected a 'value unit' string, got {text!r}")
    stripped = text.strip()
    if not stripped:
        raise UnknownUnitError("empty quantity string")
    head, _, unit = stripped.partition(" ")
    unit = unit.strip()
    if not unit:
        raise UnknownUnitError(
            f"{text!r} carries no unit; a bare number is not a declaration"
        )
    try:
        magnitude = float(head)
    except ValueError as exc:
        raise UnknownUnitError(f"{head!r} is not a number in {text!r}") from exc
    if unit not in _UNITS:
        raise UnknownUnitError(f"unit {unit!r} is not in the oracle unit table")
    dimension, factor, offset = _UNITS[unit]
    return Q(magnitude * factor + offset, dimension)


def to_si(text: str, dimension: str) -> float:
    """Parse and assert the dimension in one step. The oracles' workhorse."""
    return parse(text).in_dim(dimension)


def assert_vocabulary_closed(used: set[str]) -> None:
    """Every unit the generator emitted is one this table names.

    Called before the freeze. A generator that grows a unit this module cannot
    read would otherwise fail case-by-case at truth time, which is a slower and
    much less obvious way to learn the same thing.
    """
    stray = sorted(u for u in used if u not in _UNITS)
    if stray:
        raise UnknownUnitError(
            f"the generator emitted units the oracle table does not name: "
            f"{stray}. Add them here with their SI definition, or stop "
            f"emitting them; do not let a case reach truth construction "
            f"through a unit nothing checked."
        )
