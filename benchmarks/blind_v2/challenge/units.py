"""An independent unit algebra.

Written for this challenge rather than taken from anywhere: the challenge has
to be able to say what a declaration *means* physically without asking the
system under test to convert it, and without sharing a units backend with it.
A shared backend would make every unit-equivalence case a comparison of one
library against itself.

Dimensions are a six-vector over (length, mass, time, current, temperature,
substance). A unit is that vector, a multiplicative factor to the SI base, and
an additive offset. Only three units here carry a non-zero offset -- degC, degF
and their absolute-zero shifts -- and the offset is what makes them *affine*
rather than *ratio* scales, which is a distinction the challenge tests
deliberately: 20 degC is a temperature and 20 degC is not twice 10 degC, so an
affine unit can state a state and cannot state a span or a coefficient.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

BASE = ("length", "mass", "time", "current", "temperature", "substance")


def _d(**kw: float) -> tuple[float, ...]:
    return tuple(float(kw.get(name, 0.0)) for name in BASE)


DIMENSIONLESS = _d()


@dataclass(frozen=True)
class UnitSpec:
    """factor and offset to SI base: ``si = value * factor + offset``."""

    dim: tuple[float, ...]
    factor: float
    offset: float = 0.0

    @property
    def affine(self) -> bool:
        return self.offset != 0.0


# ---- atomic units --------------------------------------------------------
# Values are SI definitions, not conversions read from any library.
_ATOMS: dict[str, UnitSpec] = {
    "dimensionless": UnitSpec(DIMENSIONLESS, 1.0),
    "percent": UnitSpec(DIMENSIONLESS, 0.01),
    "meter": UnitSpec(_d(length=1), 1.0),
    "centimeter": UnitSpec(_d(length=1), 1e-2),
    "millimeter": UnitSpec(_d(length=1), 1e-3),
    "kilometer": UnitSpec(_d(length=1), 1e3),
    "kilogram": UnitSpec(_d(mass=1), 1.0),
    "gram": UnitSpec(_d(mass=1), 1e-3),
    "second": UnitSpec(_d(time=1), 1.0),
    "minute": UnitSpec(_d(time=1), 60.0),
    "hour": UnitSpec(_d(time=1), 3600.0),
    "ampere": UnitSpec(_d(current=1), 1.0),
    "milliampere": UnitSpec(_d(current=1), 1e-3),
    "microampere": UnitSpec(_d(current=1), 1e-6),
    "kelvin": UnitSpec(_d(temperature=1), 1.0),
    "degR": UnitSpec(_d(temperature=1), 5.0 / 9.0),
    "degC": UnitSpec(_d(temperature=1), 1.0, 273.15),
    "degF": UnitSpec(_d(temperature=1), 5.0 / 9.0, 273.15 - 32.0 * 5.0 / 9.0),
    "mole": UnitSpec(_d(substance=1), 1.0),
    "millimole": UnitSpec(_d(substance=1), 1e-3),
    "liter": UnitSpec(_d(length=3), 1e-3),
    # derived, defined from the base units rather than tabulated
    "newton": UnitSpec(_d(mass=1, length=1, time=-2), 1.0),
    "joule": UnitSpec(_d(mass=1, length=2, time=-2), 1.0),
    "kilojoule": UnitSpec(_d(mass=1, length=2, time=-2), 1e3),
    "watt": UnitSpec(_d(mass=1, length=2, time=-3), 1.0),
    "milliwatt": UnitSpec(_d(mass=1, length=2, time=-3), 1e-3),
    "kilowatt": UnitSpec(_d(mass=1, length=2, time=-3), 1e3),
    "kilowatt_hour": UnitSpec(_d(mass=1, length=2, time=-2), 3.6e6),
    "volt": UnitSpec(_d(mass=1, length=2, time=-3, current=-1), 1.0),
    "millivolt": UnitSpec(_d(mass=1, length=2, time=-3, current=-1), 1e-3),
    "kilovolt": UnitSpec(_d(mass=1, length=2, time=-3, current=-1), 1e3),
    "ohm": UnitSpec(_d(mass=1, length=2, time=-3, current=-2), 1.0),
    "milliohm": UnitSpec(_d(mass=1, length=2, time=-3, current=-2), 1e-3),
    "kiloohm": UnitSpec(_d(mass=1, length=2, time=-3, current=-2), 1e3),
    "megaohm": UnitSpec(_d(mass=1, length=2, time=-3, current=-2), 1e6),
    "coulomb": UnitSpec(_d(current=1, time=1), 1.0),
    "ampere_hour": UnitSpec(_d(current=1, time=1), 3600.0),
    "milliampere_hour": UnitSpec(_d(current=1, time=1), 3.6),
}


class UnitError(ValueError):
    """A unit string this challenge cannot read, or cannot legally use."""


_TOKEN = re.compile(r"\s*([A-Za-z_][A-Za-z_0-9]*|\d+(?:\.\d+)?|\*\*|[*/()])")


def _tokens(text: str) -> list[str]:
    out: list[str] = []
    pos = 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            if text[pos].isspace():
                pos += 1
                continue
            raise UnitError(f"unreadable character {text[pos]!r} in unit {text!r}")
        out.append(m.group(1))
        pos = m.end()
    return out


def parse(unit: str) -> UnitSpec:
    """Parse a unit expression into dimension, factor and offset.

    Accepts products, quotients and integer powers -- ``joule / kelvin /
    kilogram``, ``meter ** 2 / second``, ``1 / hour``. An affine atom is only
    legal on its own: ``degC ** 2`` and ``degC / second`` have no meaning this
    challenge is willing to invent, and are refused rather than silently
    treated as kelvin.
    """
    if unit in _ATOMS:
        return _ATOMS[unit]
    toks = _tokens(unit)
    if not toks:
        raise UnitError(f"empty unit {unit!r}")
    pos = 0

    def atom() -> UnitSpec:
        nonlocal pos
        tok = toks[pos]
        pos += 1
        if tok == "(":
            inner = expression()
            if pos >= len(toks) or toks[pos] != ")":
                raise UnitError(f"unbalanced parenthesis in {unit!r}")
            pos += 1
            return inner
        if re.fullmatch(r"\d+(\.\d+)?", tok):
            return UnitSpec(DIMENSIONLESS, float(tok))
        spec = _ATOMS.get(tok)
        if spec is None:
            raise UnitError(f"unknown unit {tok!r} in {unit!r}")
        if spec.affine:
            raise UnitError(
                f"affine unit {tok!r} may not appear inside a compound unit "
                f"({unit!r}): an offset scale has no multiplicative meaning"
            )
        return spec

    def power() -> UnitSpec:
        nonlocal pos
        left = atom()
        while pos < len(toks) and toks[pos] == "**":
            pos += 1
            exponent = float(toks[pos])
            pos += 1
            left = UnitSpec(
                tuple(d * exponent for d in left.dim), left.factor**exponent
            )
        return left

    def expression() -> UnitSpec:
        nonlocal pos
        left = power()
        while pos < len(toks) and toks[pos] in ("*", "/"):
            op = toks[pos]
            pos += 1
            right = power()
            sign = 1.0 if op == "*" else -1.0
            left = UnitSpec(
                tuple(a + sign * b for a, b in zip(left.dim, right.dim)),
                left.factor * (right.factor**sign),
            )
        return left

    result = expression()
    if pos != len(toks):
        raise UnitError(f"trailing tokens in unit {unit!r}")
    return result


def to_si(value: float, unit: str) -> float:
    """The value in SI base units."""
    spec = parse(unit)
    return value * spec.factor + spec.offset


def dimension(unit: str) -> tuple[float, ...]:
    return parse(unit).dim


def is_ratio_scale(unit: str) -> bool:
    """True when the unit has a true zero, so a ratio of two is meaningful."""
    return not parse(unit).affine


def same_dimension(a: str, b: str) -> bool:
    return dimension(a) == dimension(b)


def si_span(value: float, unit: str) -> float:
    """A *difference* in SI base units -- the offset does not apply.

    A span of 10 degC is 10 K. This is separate from :func:`to_si` on purpose:
    conflating the two is precisely the mistake the challenge is probing for,
    and a challenge that made it silently could not detect it.
    """
    spec = parse(unit)
    return value * spec.factor


def known_units() -> tuple[str, ...]:
    return tuple(sorted(_ATOMS))


def format_si(value: float) -> float:
    """Round-trip stable float, so a case digest does not move on reprint."""
    return float(f"{value!r}") if math.isfinite(value) else value
