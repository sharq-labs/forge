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
import operator as _operator
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


def dimension_of(unit: str) -> Any:
    """A unit's physical dimensionality as the backend's own comparable object.

    This — not :func:`dimensionality` — is what compatibility is decided by.
    Pint's ``UnitsContainer`` is a mapping from dimension name to exponent and
    compares (and hashes) by content, so ``ampere * ohm`` and ``volt`` are
    equal to it. Its *rendering* is not canonical: the exponents come out in
    the order the composite was built, so ``I * R`` renders as
    ``... / [current] / [time] ** 3`` and ``volt`` as
    ``... / [time] ** 3 / [current]``. Comparing those strings made Ohm's law
    a units error; comparing these objects does not.
    """
    try:
        return registry().Unit(normalize_unit(unit)).dimensionality
    except UnitCompatibilityError:
        raise
    except Exception as exc:
        raise UnitCompatibilityError(
            f"cannot determine dimensionality of {unit!r}: {exc}"
        ) from exc


def dimensionality(unit: str) -> str:
    """Stable string form of a unit's physical dimensionality.

    For messages, display and serialization. The rendering is **canonical**:
    the dimension names are sorted, so two dimensionally identical units
    always produce the same string no matter how each was composed. Equality
    of these strings is therefore a correct compatibility test as well —
    which matters because callers outside this subpackage do compare them.

    Single-dimension and dimensionless units render exactly as the backend
    renders them (``"[temperature]"``, ``"dimensionless"``); only the ordering
    of a multi-dimension rendering is fixed, and only where it was arbitrary.
    """
    dimensions = dimension_of(unit)
    # Rebuilt through the container's own type rather than string-joined by
    # hand, so the rendering stays the backend's and only its order is ours.
    return str(type(dimensions)(dict(sorted(dimensions.items()))))


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
        # Objects, not their renderings. See :func:`dimension_of`.
        return dimension_of(self.units) == dimension_of(target)

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
    def _combine(self, other: "Quantity", operator, *, context: str) -> "Quantity":
        """Addition and subtraction, performed by the backend.

        **This used to be converted-magnitude arithmetic** — convert the right
        operand into the left's unit, apply the operator to the two floats, and
        keep the left's unit. That is correct for every ratio-scale unit and
        wrong for every interval one, and the wrongness is not small:
        ``Q(30, 'degC') - Q(20, 'degC')`` returned ``10 degC``, which converts
        to **283.15 K** rather than to a 10 K difference. On an interval scale
        the difference of two absolute values is not an absolute value; it
        lives on a different unit, and the backend has one. The same rule made
        ``Q(30, 'degC') + Q(20, 'degC')`` return ``50 degC`` — not a wrong
        number but a meaningless one, since adding two absolute temperatures
        has no answer to give.

        So the operation is delegated, which is this module's stated design
        position rather than a new one: *"we do not reimplement dimensional
        analysis. Pint owns the unit algebra; this module owns the contract."*
        Offset-unit and delta-unit semantics come back from the backend intact
        — a Celsius difference lands on ``delta_degree_Celsius``, a delta added
        to an absolute stays absolute, and absolute-plus-absolute raises.

        What this module keeps is the contract around it. The dimensional check
        is made **first**, so an incompatible pair still fails with this
        package's own :class:`UnitCompatibilityError` naming the operation,
        rather than with whatever the backend would have said; and the result
        is rebuilt through :class:`Quantity`, so it is normalised and finite
        like every other value here.

        Ratio-scale behaviour is unchanged, because pint's own rule there is
        already the left operand's unit: ``1 m + 100 cm`` is still ``2 m``.
        """
        self.require_compatible(other, context=context)
        try:
            combined = operator(
                registry().Quantity(self.magnitude, self.units),
                registry().Quantity(other.magnitude, other.units),
            )
        except Exception as exc:  # pint raises several distinct types
            raise UnitCompatibilityError(
                f"cannot perform {context} on {self.units!r} and "
                f"{other.units!r}: {exc}"
            ) from exc
        return Quantity(float(combined.magnitude), str(combined.units))

    def __add__(self, other: "Quantity") -> "Quantity":
        return self._combine(other, _operator.add, context="addition")

    def __sub__(self, other: "Quantity") -> "Quantity":
        return self._combine(other, _operator.sub, context="subtraction")

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
