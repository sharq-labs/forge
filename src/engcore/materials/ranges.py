"""Declared applicability ranges (dependency-light: Core types only).

Shared by material data, material state schemas and degradation-model
identity, so "where is this authorized" has one meaning everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import re
from typing import Any, Mapping

from ..scientific.errors import InvalidScientificProblem
from ..scientific.serialization import require_schema, schema_string
from ..scientific.units.quantity import Quantity

RANGE_SCHEMA = schema_string("applicability_range")
_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]*$")


def _identifier(value: object, label: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text or not _ID.fullmatch(text):
        raise InvalidScientificProblem(f"{label} must be a non-empty typed identifier")
    return text


def _strict_keys(payload: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(payload) != expected:
        raise InvalidScientificProblem(
            f"{label} shape mismatch; missing={sorted(expected - set(payload))}, extra={sorted(set(payload) - expected)}"
        )


def _exact(q: Quantity, unit: str) -> Fraction:
    return Fraction(repr(float(q.magnitude_in(unit))))


@dataclass(frozen=True)
class ApplicabilityRange:
    """A declared range of one named variable.

    ``lower``/``upper`` may be omitted only when ``unbounded_reason`` states why
    the side is deliberately open -- an omitted bound is never "everywhere".
    A point (``lower == upper``, both inclusive) is a valid range: the value a
    tabulated datum was stated at.
    """

    variable_id: str
    lower: Quantity | None
    upper: Quantity | None
    lower_inclusive: bool = True
    upper_inclusive: bool = True
    unbounded_reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "variable_id", _identifier(self.variable_id, "range variable_id"))
        reason = str(self.unbounded_reason or "").strip()
        if (self.lower is None or self.upper is None) and not reason:
            raise InvalidScientificProblem(
                f"range of {self.variable_id!r} omits a bound without stating why; an undeclared "
                f"bound is not applicability everywhere"
            )
        object.__setattr__(self, "unbounded_reason", reason)
        for side in (self.lower, self.upper):
            if side is not None and not isinstance(side, Quantity):
                raise InvalidScientificProblem("range bounds must be Quantity records")
        if self.lower is not None and self.upper is not None:
            self.upper.require_compatible(self.lower.units, context=f"range {self.variable_id!r}")
            if self.upper.magnitude_in(self.lower.units) < self.lower.magnitude:
                raise InvalidScientificProblem(f"range {self.variable_id!r} upper is below lower")
            if self.upper.magnitude_in(self.lower.units) == self.lower.magnitude and not (self.lower_inclusive and self.upper_inclusive):
                raise InvalidScientificProblem(f"range {self.variable_id!r} is empty")

    @property
    def unit(self) -> str:
        return (self.lower or self.upper).units

    @property
    def is_point(self) -> bool:
        return self.lower is not None and self.upper is not None and self.lower.magnitude_in(self.unit) == self.upper.magnitude_in(self.unit)

    def admits(self, value: Quantity) -> bool:
        value.require_compatible(self.unit, context=f"range {self.variable_id!r}")
        v = _exact(value, self.unit)
        if self.lower is not None:
            lo = _exact(self.lower, self.unit)
            if v < lo or (v == lo and not self.lower_inclusive):
                return False
        if self.upper is not None:
            hi = _exact(self.upper, self.unit)
            if v > hi or (v == hi and not self.upper_inclusive):
                return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {"schema": RANGE_SCHEMA, "variable_id": self.variable_id, "lower": None if self.lower is None else self.lower.to_dict(), "upper": None if self.upper is None else self.upper.to_dict(), "lower_inclusive": self.lower_inclusive, "upper_inclusive": self.upper_inclusive, "unbounded_reason": self.unbounded_reason}

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "ApplicabilityRange":
        require_schema(p, RANGE_SCHEMA)
        _strict_keys(p, {"schema", "variable_id", "lower", "upper", "lower_inclusive", "upper_inclusive", "unbounded_reason"}, "applicability range")
        return cls(p["variable_id"], None if p["lower"] is None else Quantity.from_dict(p["lower"]), None if p["upper"] is None else Quantity.from_dict(p["upper"]), p["lower_inclusive"], p["upper_inclusive"], p["unbounded_reason"])


