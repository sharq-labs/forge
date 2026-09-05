"""Dimensional validation helpers.

These exist so that IR objects, model definitions and results all enforce
dimensional agreement the same way, with the same error type and the same
message shape.
"""

from __future__ import annotations

from typing import Iterable, Mapping

from ..errors import UnitCompatibilityError
from .quantity import Quantity, dimensionality, normalize_unit


def require_unit(unit: str, *, context: str) -> str:
    """Validate and normalize a declared unit string."""
    try:
        return normalize_unit(unit)
    except UnitCompatibilityError as exc:
        raise UnitCompatibilityError(f"{context}: {exc}") from exc


def require_same_dimension(
    left: Quantity | str,
    right: Quantity | str,
    *,
    context: str,
) -> None:
    """Raise unless both operands share a physical dimensionality."""
    left_unit = left.units if isinstance(left, Quantity) else left
    right_unit = right.units if isinstance(right, Quantity) else right
    if dimensionality(left_unit) != dimensionality(right_unit):
        raise UnitCompatibilityError(
            f"{context}: {left_unit!r} [{dimensionality(left_unit)}] is not "
            f"compatible with {right_unit!r} [{dimensionality(right_unit)}]"
        )


def require_expected_dimension(
    value: Quantity,
    expected_unit: str,
    *,
    context: str,
) -> None:
    """Raise unless ``value`` has the dimensionality implied by
    ``expected_unit`` (e.g. a temperature metric supplied in volts)."""
    require_same_dimension(value, expected_unit, context=context)


def check_unit_map(
    values: Mapping[str, Quantity],
    expected_units: Mapping[str, str],
    *,
    context: str,
) -> None:
    """Validate a whole ``{name: Quantity}`` map against declared units.

    Names absent from ``expected_units`` are ignored: the core does not
    invent expectations it was never given.
    """
    for name, quantity in values.items():
        expected = expected_units.get(name)
        if expected is None:
            continue
        require_same_dimension(
            quantity, expected, context=f"{context}: metric {name!r}"
        )


def all_dimensionalities(units: Iterable[str]) -> tuple[str, ...]:
    return tuple(dimensionality(u) for u in units)
