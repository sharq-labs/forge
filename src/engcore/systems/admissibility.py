"""Physical admissibility: declared physical invariants a computed state must satisfy before it is reported.

Hostile review F6 (HIGH): the coupled drone hover screening reported a state
whose shaft power was a fourteenth of the ideal induced power of momentum
theory (figure of merit 14.55) -- a rotor doing more work on the air than it
absorbs. Every individual model was evaluated "correctly"; nothing asked
whether the combined state could exist.

This module is the generic mechanism, and it knows no physics. A system that
can name a law its states must obey declares a :class:`PhysicalInvariant` --
the law in words, where it comes from, and which way the inequality runs --
and evaluates it on two quantities it computes itself (the value and the
bound). The mechanism only:

* compares the two in the bound's unit (incompatible units are refused, never coerced);
* treats the exact boundary as admissible and anything beyond it, by more than
  floating-point round-off (:data:`ROUND_OFF`), as INADMISSIBLE;
* treats a value or bound the system could not compute (``None``) as UNKNOWN -- and UNKNOWN never admits;
* refuses, through :func:`require_admissible`, any state with an evaluation
  that is not ADMISSIBLE.

An admissible evaluation is a necessary condition, not evidence: it says the
state does not violate the declared law, never that the models are right.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from ..scientific.errors import InvalidScientificProblem, ScientificCoreError
from ..scientific.units.quantity import Quantity

#: Relative slack for floating-point round-off at the exact boundary. Not a physical tolerance.
ROUND_OFF = 1e-12


class InvariantRelation(str, Enum):
    """Which way the declared law runs: ``value <relation> bound``."""

    AT_MOST = "at_most"
    AT_LEAST = "at_least"


class AdmissibilityStatus(str, Enum):
    ADMISSIBLE = "admissible"
    INADMISSIBLE = "inadmissible"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PhysicalInvariant:
    """A law a physical state must obey, declared by the system that computes the state."""

    invariant_id: str
    statement: str
    basis: str
    relation: InvariantRelation

    def __post_init__(self) -> None:
        for name in ("invariant_id", "statement", "basis"):
            if not str(getattr(self, name)).strip():
                raise InvalidScientificProblem(f"a physical invariant needs a non-empty {name}")
        object.__setattr__(self, "relation", InvariantRelation(self.relation))

    def to_dict(self) -> dict[str, Any]:
        return {"invariant_id": self.invariant_id, "statement": self.statement, "basis": self.basis,
                "relation": self.relation.value}


class PhysicallyInadmissible(InvalidScientificProblem):
    """A computed state violates (or cannot be shown to satisfy) a declared physical invariant."""


@dataclass(frozen=True)
class InvariantEvaluation:
    invariant: PhysicalInvariant
    value: Quantity | None
    bound: Quantity | None
    status: AdmissibilityStatus
    #: ``value / bound`` in the bound's unit (the figure the law is about); None when it cannot be formed
    ratio: float | None
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {**self.invariant.to_dict(), "value": None if self.value is None else self.value.to_dict(),
                "bound": None if self.bound is None else self.bound.to_dict(),
                "status": self.status.value, "ratio": self.ratio, "detail": self.detail}


def evaluate_invariant(invariant: PhysicalInvariant, value: Quantity | None, bound: Quantity | None) -> InvariantEvaluation:
    """Evaluate ``value <relation> bound`` for a declared invariant. Never raises for a violation: it reports it.

    ``None`` for either side means the system could not compute it: UNKNOWN, which never admits.
    """
    if value is None or bound is None:
        return InvariantEvaluation(invariant, value, bound, AdmissibilityStatus.UNKNOWN, None,
                                   "the value or the bound was not computed, so the law cannot be shown to hold")
    if not isinstance(value, Quantity) or not isinstance(bound, Quantity):
        raise InvalidScientificProblem(f"invariant {invariant.invariant_id!r} compares quantities with units")
    try:
        v = value.magnitude_in(bound.units)
    except ScientificCoreError as exc:  # the Core's own unit contract refuses incompatible units; never coerced
        raise InvalidScientificProblem(
            f"invariant {invariant.invariant_id!r} compares {value.units} with {bound.units}: incompatible units are "
            f"a declaration error, not a comparison ({exc})") from exc
    b = bound.magnitude  # a Quantity is finite by construction
    ratio = v / b if b != 0 else None
    slack = ROUND_OFF * max(abs(v), abs(b))
    if invariant.relation is InvariantRelation.AT_LEAST:
        holds = v >= b - slack
    else:
        holds = v <= b + slack
    status = AdmissibilityStatus.ADMISSIBLE if holds else AdmissibilityStatus.INADMISSIBLE
    word = "at least" if invariant.relation is InvariantRelation.AT_LEAST else "at most"
    detail = (f"{v:.9g} {bound.units} must be {word} {b:.9g} {bound.units}"
              + ("" if holds else f": violated ({invariant.statement})"))
    return InvariantEvaluation(invariant, value, bound, status, ratio, detail)


def require_admissible(evaluations: Iterable[InvariantEvaluation]) -> tuple[InvariantEvaluation, ...]:
    """Refuse unless every evaluation is ADMISSIBLE. UNKNOWN refuses too: a law not shown to hold is not assumed to."""
    evaluations = tuple(evaluations)
    failing = [e for e in evaluations if e.status is not AdmissibilityStatus.ADMISSIBLE]
    if failing:
        raise PhysicallyInadmissible(
            "physically inadmissible state: " + "; ".join(
                f"{e.invariant.invariant_id} is {e.status.value} ({e.detail})" for e in failing))
    return evaluations


__all__ = [
    "ROUND_OFF",
    "AdmissibilityStatus",
    "InvariantEvaluation",
    "InvariantRelation",
    "PhysicalInvariant",
    "PhysicallyInadmissible",
    "evaluate_invariant",
    "require_admissible",
]
