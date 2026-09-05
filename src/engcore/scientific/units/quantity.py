"""Scientific quantity contract.

Design position: we do not reimplement dimensional analysis. Pint owns the
unit algebra; this module owns the *contract* — an immutable, serializable
quantity type that the rest of the Scientific Core depends on, so that the
units backend stays replaceable and never leaks into scientific records.

Invariants:

* a Quantity always carries a unit (``"dimensionless"`` is a unit, not an
  absence of one);
* unit strings are normalized on construction, so serialization is
  deterministic;
* incompatible operations raise :class:`UnitCompatibilityError` — the core
  never silently strips or coerces units;
* **a magnitude is always finite.** NaN and ±Inf are refused here, which is
  what keeps them out of parameters, bounds, tolerances, results,
  uncertainties and provenance without a check in each of those types.

  The one sanctioned home for non-finite numbers is
  :class:`~engcore.scientific.solvers.protocol.RawSolverOutput`: a diverged
  backend must be able to report NaN honestly. The boundary is therefore
  *raw backend output may be non-finite; interpreted science may not*.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

import pint

from ..errors import UnitCompatibilityError
from ..serialization import require_schema, schema_string

QUANTITY_SCHEMA = schema_string("quantity")

_REGISTRY: pint.UnitRegistry | None = None


def registry() -> pint.UnitRegistry:
    """The single unit registry owned by the Scientific Core.

    Deliberately *not* pint's application registry: that is process-global and
    mutable by any co-resident library, which would make our dimensional
    guarantees depend on unrelated code.
    """
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = pint.UnitRegistry()
    return _REGISTRY


def normalize_unit(unit: str) -> str:
    """Canonical string form of a unit expression.

    Raises :class:`UnitCompatibilityError` for unparsable input.
    """
    text = str(unit).strip()
    if not text:
        raise UnitCompatibilityError(
            "unit must be a non-empty string; use 'dimensionless' explicitly"
        )
    try:
        return str(registry().Unit(text))
    except Exception as exc:  # pint raises several distinct types
        raise UnitCompatibilityError(f"unparsable unit {unit!r}: {exc}") from exc


def dimensionality(unit: str) -> str:
    """Stable string form of a unit's physical dimensionality."""
    try:
        return str(registry().Unit(normalize_unit(unit)).dimensionality)
    except UnitCompatibilityError:
        raise
    except Exception as exc:
        raise UnitCompatibilityError(
            f"cannot determine dimensionality of {unit!r}: {exc}"
        ) from exc


@dataclass(frozen=True)
class Quantity:
    """A scientific value: magnitude plus unit, never one without the other."""

    magnitude: float
    units: str

    def __post_init__(self) -> None:
        magnitude = float(self.magnitude)
        if not math.isfinite(magnitude):
            raise UnitCompatibilityError(
                f"scientific magnitude must be finite, got {magnitude!r}; "
                f"non-finite values belong in RawSolverOutput diagnostics, "
                f"not in an interpreted scientific quantity"
            )
        object.__setattr__(self, "magnitude", magnitude)
        object.__setattr__(self, "units", normalize_unit(self.units))

    # ---- construction -------------------------------------------------
    @classmethod
    def dimensionless(cls, magnitude: float) -> "Quantity":
        return cls(magnitude, "dimensionless")

    @classmethod
    def parse(cls, text: str) -> "Quantity":
        """Parse ``"12 V"`` style input. Bare numbers are rejected: a
        scientific value without a unit is a contract violation, not a
        dimensionless default."""
        raw = str(text).strip()
        try:
            # A bare numeric literal parses as dimensionless in every units
            # backend; accepting it would silently invent a unit.
            float(raw)
        except ValueError:
            pass
        else:
            raise UnitCompatibilityError(
                f"{raw!r} carries no unit; state one explicitly "
                f"(e.g. '{raw} dimensionless')"
            )
        try:
            parsed = registry().Quantity(raw)
        except Exception as exc:
            raise UnitCompatibilityError(
                f"cannot parse quantity {text!r}: {exc}"
            ) from exc
        return cls(float(parsed.magnitude), str(parsed.units))

    # ---- dimensional interface ----------------------------------------
    @property
    def dimensionality(self) -> str:
        return dimensionality(self.units)

    def is_compatible_with(self, other: "Quantity | str") -> bool:
        target = other.units if isinstance(other, Quantity) else other
        return dimensionality(self.units) == dimensionality(target)

    def require_compatible(self, other: "Quantity | str", *, context: str = "") -> None:
        if not self.is_compatible_with(other):
            target = other.units if isinstance(other, Quantity) else other
            where = f" ({context})" if context else ""
            raise UnitCompatibilityError(
                f"incompatible units{where}: {self.units!r} "
                f"[{self.dimensionality}] vs {target!r} [{dimensionality(target)}]"
            )

    def to(self, unit: str) -> "Quantity":
        """Convert to ``unit``. Raises if dimensionally incompatible."""
        target = normalize_unit(unit)
        self.require_compatible(target, context="conversion")
        converted = registry().Quantity(self.magnitude, self.units).to(target)
        return Quantity(float(converted.magnitude), str(converted.units))

    def magnitude_in(self, unit: str) -> float:
        """Numeric magnitude expressed in ``unit`` — the single sanctioned way
        to hand a scientific value to a numeric kernel."""
        return self.to(unit).magnitude

    # ---- minimal arithmetic -------------------------------------------
    # Enough for constraint checks and adapters; full quantity algebra stays
    # in the backend and is not part of this contract.
    def __add__(self, other: "Quantity") -> "Quantity":
        self.require_compatible(other, context="addition")
        return Quantity(self.magnitude + other.to(self.units).magnitude, self.units)

    def __sub__(self, other: "Quantity") -> "Quantity":
        self.require_compatible(other, context="subtraction")
        return Quantity(self.magnitude - other.to(self.units).magnitude, self.units)

    def __mul__(self, other: "Quantity | float") -> "Quantity":
        if isinstance(other, Quantity):
            product = (
                registry().Quantity(self.magnitude, self.units)
                * registry().Quantity(other.magnitude, other.units)
            )
            return Quantity(float(product.magnitude), str(product.units))
        return Quantity(self.magnitude * float(other), self.units)

    def __truediv__(self, other: "Quantity | float") -> "Quantity":
        if isinstance(other, Quantity):
            ratio = (
                registry().Quantity(self.magnitude, self.units)
                / registry().Quantity(other.magnitude, other.units)
            )
            return Quantity(float(ratio.magnitude), str(ratio.units))
        return Quantity(self.magnitude / float(other), self.units)

    def compare(self, other: "Quantity") -> float:
        """Signed difference in *this* quantity's units (>0 if self larger)."""
        self.require_compatible(other, context="comparison")
        return self.magnitude - other.to(self.units).magnitude

    # ---- serialization -------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": QUANTITY_SCHEMA,
            "magnitude": self.magnitude,
            "units": self.units,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Quantity":
        require_schema(payload, QUANTITY_SCHEMA)
        return cls(float(payload["magnitude"]), str(payload["units"]))

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"{self.magnitude} {self.units}"


def coerce_quantity(value: Quantity | float | int | str, unit: str) -> Quantity:
    """Interpret ``value`` in the declared context ``unit``.

    A bare number is accepted only because ``unit`` supplies the missing
    context explicitly; a Quantity is converted and dimension-checked. This is
    the one sanctioned entry point for numeric input, and it never guesses.
    """
    if isinstance(value, Quantity):
        return value.to(unit)
    if isinstance(value, str):
        return Quantity.parse(value).to(unit)
    return Quantity(float(value), unit)
