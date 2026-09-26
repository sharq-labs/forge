"""Small shared helpers for the multi-timescale layer (no authority of their own)."""

from __future__ import annotations

import re
from fractions import Fraction
from typing import Any

from ..scenarios.timeline import TimePoint, TimeWindow, exact_seconds
from ..scientific.errors import InvalidScientificProblem
from ..scientific.units.quantity import Quantity

_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]*$")


def identifier(value: object, label: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text or not _ID.fullmatch(text):
        raise InvalidScientificProblem(f"{label} must be a non-empty typed identifier")
    return text


def time_seconds(value: Any, label: str = "duration") -> Fraction:
    """Exact seconds of a time Quantity (BIG 2 same-instant rule)."""
    return exact_seconds(value, label)


def fraction_text(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


def parse_fraction(text: str, label: str) -> Fraction:
    value = Fraction(text)
    if fraction_text(value) != text:
        raise InvalidScientificProblem(f"{label} must be an exact rational in lowest terms")
    return value


def window_seconds(window: TimeWindow) -> Fraction:
    return window.end.seconds - window.start.seconds


def point(basis_id: str, seconds: Fraction) -> TimePoint:
    return TimePoint(basis_id, seconds)


def quantity_seconds(seconds: Fraction) -> Quantity:
    return Quantity(float(seconds), "second")
