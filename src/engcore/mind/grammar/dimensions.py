"""Buckingham-pi analysis from DECLARED units only (EXC-4, development).

A unit is a product of base dimensions with integer powers, written ``B1^1*B2^-2`` (``"1"`` is dimensionless) -- the
form a Blindfold card states.  From the inputs' units and the output's unit this module derives

* a **scale**: one monomial of the inputs with the output's dimension (rational exponents allowed), and
* **groups**: an integer basis of the dimensionless monomials of the inputs (the null space of the dimension matrix).

Any law that is dimensionally homogeneous can then be written ``scale x F(groups)``.  Nothing is defaulted: a unit that
does not parse, names a base dimension the problem does not declare, or an output dimension that no monomial of the
inputs can carry raises :class:`DimensionRefused` -- it never becomes "dimensionless".

The result depends on the inputs' DIMENSIONS and BOXES, never on their names or their presentation order: inputs are
put in a canonical order (box, then dimension vector) before the elimination, so a renamed or reordered presentation of
one problem gets the same groups up to the renaming.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Mapping, Sequence

_FACTOR = re.compile(r"^([^\^\*\s]+)\^(-?\d+)$")


class DimensionRefused(ValueError):
    """Units that cannot be analysed exactly (unparseable, undeclared base, inconsistent output)."""


@dataclass(frozen=True)
class InputDimension:
    name: str
    unit: str
    low: float
    high: float


@dataclass(frozen=True)
class DimensionalBasis:
    """``scale``: input -> exponent (Fraction); ``groups``: each a mapping input -> nonzero integer exponent."""

    inputs: tuple[str, ...]                       # canonical order
    scale: Mapping[str, Fraction]
    groups: tuple[Mapping[str, int], ...]

    def to_dict(self) -> dict:
        return {"inputs": list(self.inputs), "scale": {k: str(v) for k, v in sorted(self.scale.items())},
                "groups": [dict(sorted(g.items())) for g in self.groups]}


def parse_unit(unit: str, bases: Sequence[str]) -> tuple[int, ...]:
    """The dimension vector of ``unit`` over ``bases``; refuses anything else."""
    if not isinstance(unit, str) or not unit.strip():
        raise DimensionRefused("a unit is a non-empty string")
    vec = [0] * len(bases)
    if unit.strip() == "1":
        return tuple(vec)
    index = {b: i for i, b in enumerate(bases)}
    for part in unit.split("*"):
        m = _FACTOR.match(part.strip())
        if m is None:
            raise DimensionRefused(f"unit factor {part!r} is not of the form BASE^integer")
        if m.group(1) not in index:
            raise DimensionRefused(f"unit names base dimension {m.group(1)!r}, which the problem does not declare")
        vec[index[m.group(1)]] += int(m.group(2))
    return tuple(vec)


def _rref(rows: list[list[Fraction]], ncols: int) -> tuple[list[list[Fraction]], list[int]]:
    m = [r[:] for r in rows]
    pivots: list[int] = []
    r = 0
    for col in range(ncols):
        pick = next((i for i in range(r, len(m)) if m[i][col] != 0), None)
        if pick is None:
            continue
        m[r], m[pick] = m[pick], m[r]
        lead = m[r][col]
        m[r] = [x / lead for x in m[r]]
        for i in range(len(m)):
            if i != r and m[i][col] != 0:
                f = m[i][col]
                m[i] = [a - f * b for a, b in zip(m[i], m[r])]
        pivots.append(col)
        r += 1
        if r == len(m):
            break
    return m, pivots


def _integer(vec: list[Fraction]) -> list[int]:
    den = 1
    for x in vec:
        den = den * x.denominator // math.gcd(den, x.denominator)
    ints = [int(x * den) for x in vec]
    g = 0
    for x in ints:
        g = math.gcd(g, abs(x))
    ints = [x // g for x in ints] if g else ints
    first = next((x for x in ints if x), 0)
    return [-x for x in ints] if first < 0 else ints


def analyse(inputs: Sequence[InputDimension], output_unit: str, bases: Sequence[str]) -> DimensionalBasis:
    if not inputs:
        raise DimensionRefused("no input to analyse")
    if len(set(bases)) != len(bases):
        raise DimensionRefused("base dimensions are distinct")
    if len({x.name for x in inputs}) != len(inputs):
        raise DimensionRefused("input names are distinct")
    dims = {x.name: parse_unit(x.unit, bases) for x in inputs}
    target = parse_unit(output_unit, bases)
    order = sorted(inputs, key=lambda x: (float(x.low), float(x.high), dims[x.name]))
    names = [x.name for x in order]
    n, k = len(names), len(bases)
    # augmented system D s = target, D[k x n] (columns = canonical inputs)
    rows = [[Fraction(dims[name][i]) for name in names] + [Fraction(target[i])] for i in range(k)]
    red, pivots = _rref(rows, n)
    if any(all(x == 0 for x in row[:n]) and row[n] != 0 for row in red):
        raise DimensionRefused("no monomial of the inputs has the output's dimension")
    scale = [Fraction(0)] * n
    for i, col in enumerate(pivots):
        scale[col] = red[i][n]
    groups = []
    for free in (c for c in range(n) if c not in pivots):
        vec = [Fraction(0)] * n
        vec[free] = Fraction(1)
        for i, col in enumerate(pivots):
            vec[col] = -red[i][free]
        ints = _integer(vec)
        groups.append({names[j]: e for j, e in enumerate(ints) if e})
    return DimensionalBasis(tuple(names), {names[j]: e for j, e in enumerate(scale) if e}, tuple(groups))


__all__ = ["DimensionRefused", "DimensionalBasis", "InputDimension", "analyse", "parse_unit"]
