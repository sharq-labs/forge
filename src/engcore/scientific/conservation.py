"""Domain-neutral conservation/balance verification.

A conservation check asks whether two explicitly declared sides of a balance
close within a dimensional tolerance.  The core does not know whether the
quantity is mass, energy, charge, momentum, species amount or something a
future domain introduces; units decide whether the terms are commensurate.

The framework deliberately does **not** award a validation level by itself.
Conservation is a powerful necessary check, but satisfying a balance does not
prove that the constitutive law, boundary conditions or physics are correct.
It returns an ordinary :class:`ValidationCheck` so domains can include the
result beside their other evidence without turning a necessary condition into
an over-broad scientific claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .errors import ScientificValidationError
from .results.validation import ValidationCheck, ValidationOutcome
from .serialization import require_schema, schema_string
from .units.quantity import Quantity
from .units.validation import require_same_dimension

BALANCE_TERM_SCHEMA = schema_string("balance_term")
CONSERVATION_BALANCE_SCHEMA = schema_string("conservation_balance")


@dataclass(frozen=True)
class BalanceTerm:
    """One named contribution to one side of a conservation equation."""

    name: str
    value: Quantity
    evidence: str = ""

    def __post_init__(self) -> None:
        name = str(self.name).strip()
        if not name:
            raise ScientificValidationError("balance term requires a non-empty name")
        if not isinstance(self.value, Quantity):
            raise ScientificValidationError(
                f"balance term {name!r} value must be a Quantity"
            )
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "evidence", str(self.evidence).strip())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": BALANCE_TERM_SCHEMA,
            "name": self.name,
            "value": self.value.to_dict(),
            "evidence": self.evidence,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BalanceTerm":
        require_schema(payload, BALANCE_TERM_SCHEMA)
        return cls(
            name=payload["name"],
            value=Quantity.from_dict(payload["value"]),
            evidence=payload.get("evidence", ""),
        )


@dataclass(frozen=True)
class ConservationBalance:
    """A checkable equation ``sum(left) == sum(right)`` within tolerance.

    The equation form is more general and less error-prone than embedding a
    sign convention (inflow positive, outflow negative, storage positive, ...)
    in the universal core.  A domain decides which physical terms belong on
    which side, and this record checks only what is universal: dimensions,
    deterministic summation and closure against the declared tolerance.
    """

    balance_id: str
    left: tuple[BalanceTerm, ...]
    right: tuple[BalanceTerm, ...]
    tolerance: Quantity
    description: str = ""
    reference: str = ""

    def __post_init__(self) -> None:
        balance_id = str(self.balance_id).strip()
        if not balance_id:
            raise ScientificValidationError("conservation balance requires balance_id")
        left, right = tuple(self.left), tuple(self.right)
        if not left and not right:
            raise ScientificValidationError(
                f"conservation balance {balance_id!r} has no terms to compare"
            )
        terms = left + right
        if any(not isinstance(term, BalanceTerm) for term in terms):
            raise ScientificValidationError("conservation terms must be BalanceTerm records")
        names = [term.name for term in terms]
        if len(set(names)) != len(names):
            raise ScientificValidationError(
                f"conservation balance {balance_id!r} term names must be unique"
            )
        if not isinstance(self.tolerance, Quantity):
            raise ScientificValidationError("conservation tolerance must be a Quantity")
        exemplar = terms[0].value if terms else self.tolerance
        require_same_dimension(
            exemplar, self.tolerance, context=f"conservation balance {balance_id!r} tolerance"
        )
        for term in terms[1:]:
            require_same_dimension(
                exemplar,
                term.value,
                context=f"conservation balance {balance_id!r} term {term.name!r}",
            )
        tolerance = self.tolerance.magnitude_in(exemplar.units)
        if tolerance < 0.0:
            raise ScientificValidationError(
                f"conservation balance {balance_id!r} tolerance must be non-negative"
            )
        object.__setattr__(self, "balance_id", balance_id)
        object.__setattr__(self, "left", left)
        object.__setattr__(self, "right", right)
        object.__setattr__(self, "description", str(self.description))
        object.__setattr__(self, "reference", str(self.reference).strip())

    @property
    def unit(self) -> str:
        terms = self.left + self.right
        return terms[0].value.units if terms else self.tolerance.units

    @staticmethod
    def _sum(terms: Sequence[BalanceTerm], unit: str) -> float:
        # Stable ordering means the same record has the same floating summation
        # order whatever order a caller's mapping happened to have upstream.
        return sum(term.value.magnitude_in(unit) for term in sorted(terms, key=lambda t: t.name))

    @property
    def left_total(self) -> float:
        return self._sum(self.left, self.unit)

    @property
    def right_total(self) -> float:
        return self._sum(self.right, self.unit)

    @property
    def absolute_residual(self) -> float:
        return abs(self.left_total - self.right_total)

    @property
    def tolerance_magnitude(self) -> float:
        return self.tolerance.magnitude_in(self.unit)

    @property
    def normalized_residual(self) -> float:
        tolerance = self.tolerance_magnitude
        residual = self.absolute_residual
        if tolerance == 0.0:
            return 0.0 if residual == 0.0 else float("inf")
        return residual / tolerance

    @property
    def closed(self) -> bool:
        return self.absolute_residual <= self.tolerance_magnitude

    def to_check(self, *, name: str | None = None) -> ValidationCheck:
        """Return a non-level-awarding check for this balance."""
        ratio = self.normalized_residual
        finite_ratio = ratio if ratio != float("inf") else 2.0
        sources = [
            f"term:{term.name}:{term.evidence}"
            for term in self.left + self.right
            if term.evidence
        ]
        evidence = (
            f"balance:{self.balance_id}",
            f"equation:sum(left)==sum(right)",
            *(f"reference:{self.reference}",) if self.reference else (),
            *sources,
        )
        detail = (
            f"{self.balance_id}: left={self.left_total:g} {self.unit}, "
            f"right={self.right_total:g} {self.unit}, "
            f"absolute residual={self.absolute_residual:g} {self.unit}, "
            f"tolerance={self.tolerance_magnitude:g} {self.unit}"
        )
        return ValidationCheck(
            name=name or f"conservation:{self.balance_id}",
            outcome=ValidationOutcome.PASS if self.closed else ValidationOutcome.FAIL,
            detail=detail,
            establishes=None,
            residual=finite_ratio,
            tolerance=1.0,
            evidence=evidence,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CONSERVATION_BALANCE_SCHEMA,
            "balance_id": self.balance_id,
            "left": [term.to_dict() for term in self.left],
            "right": [term.to_dict() for term in self.right],
            "tolerance": self.tolerance.to_dict(),
            "description": self.description,
            "reference": self.reference,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ConservationBalance":
        require_schema(payload, CONSERVATION_BALANCE_SCHEMA)
        return cls(
            balance_id=payload["balance_id"],
            left=tuple(BalanceTerm.from_dict(v) for v in payload.get("left", ())),
            right=tuple(BalanceTerm.from_dict(v) for v in payload.get("right", ())),
            tolerance=Quantity.from_dict(payload["tolerance"]),
            description=payload.get("description", ""),
            reference=payload.get("reference", ""),
        )


__all__ = ["BalanceTerm", "ConservationBalance"]
