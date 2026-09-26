"""External / analytic reference data with provenance, applicability and pre-declared comparison criteria.

A reference is what an engineer compares a result AGAINST.  It is not evidence by itself and it grants
nothing: validation levels stay owned by ``engcore.scientific.oracles`` and its repository-pinned
declarations.  This module records what the reference is (analytic / numerical benchmark / experimental),
where it came from, what conditions it was produced under, and whether a given flagship is inside them.

Rules kept here on purpose:

* the kind reuses :class:`engcore.scientific.oracles.OracleKind`; a numerical benchmark is never labelled
  experimental (``benchmark_dataset`` is not ``experimental_dataset``);
* a numerical or experimental reference must carry the digest of the bytes it was extracted from and an
  https access URL; only an analytic reference may have neither;
* applicability is ``within`` only when EVERY declared envelope condition is known and inside; a missing
  condition or a missing envelope is ``unknown``, never ``within``;
* a comparison is either PRE-DECLARED (its criterion carries a digest fixed before the result existed) or it
  is labelled post hoc; a tolerance edited after seeing a result is a different criterion with a different
  digest, and the original outcome stays visible.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

from ..scenarios.timeline import canonical_digest
from ..scientific.errors import InvalidScientificProblem
from ..scientific.oracles import OracleKind
from ..scientific.units.quantity import Quantity

REFERENCE_SCHEMA = "engcore.engineering.reference/1"
COMPARISON_CLASSIFICATIONS = {
    OracleKind.ANALYTIC_REFERENCE: "analytic_limit_comparison_verifies_implementation_only",
    OracleKind.BENCHMARK_DATASET: "numerical_benchmark_comparison_not_validation_grant",
    OracleKind.EXPERIMENTAL_DATASET: "experimental_comparison_within_dataset_scope_not_validation_grant",
}


def _text(value: Any, label: str) -> str:
    text = str(value).strip()
    if not text:
        raise InvalidScientificProblem(f"{label} must be non-empty")
    return text


def _hex64(value: str, label: str) -> str:
    v = str(value).strip().lower()
    if len(v) != 64 or any(c not in "0123456789abcdef" for c in v):
        raise InvalidScientificProblem(f"{label} must be a SHA-256 hex digest")
    return v


@dataclass(frozen=True)
class ReferenceCondition:
    """One condition the reference was produced under (e.g. Reynolds number 100)."""

    name: str
    value: float
    unit: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _text(self.name, "reference condition name"))
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)) or not math.isfinite(self.value):
            raise InvalidScientificProblem("a reference condition value is a finite number")
        object.__setattr__(self, "value", float(self.value))
        object.__setattr__(self, "unit", _text(self.unit, "reference condition unit"))

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "value": repr(self.value), "unit": self.unit}


@dataclass(frozen=True)
class EnvelopeBound:
    """The closed range of one condition inside which the reference applies."""

    name: str
    low: float
    high: float
    unit: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _text(self.name, "envelope condition"))
        if not (math.isfinite(self.low) and math.isfinite(self.high) and self.low <= self.high):
            raise InvalidScientificProblem("an applicability bound is a finite ordered range")
        object.__setattr__(self, "unit", _text(self.unit, "envelope unit"))

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "low": repr(float(self.low)), "high": repr(float(self.high)), "unit": self.unit}


@dataclass(frozen=True)
class ReferenceApplicability:
    #: "within" | "outside" | "unknown"; only "within" lets a comparison be read against the reference
    status: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "reasons": list(self.reasons)}


@dataclass(frozen=True)
class ReferenceRecord:
    reference_id: str
    title: str
    authors: str
    publication: str
    access_url: str
    #: what the source permits, in words; if redistribution is not permitted ``data`` stays empty
    license_status: str
    kind: OracleKind
    conditions: tuple[ReferenceCondition, ...]
    quantities: tuple[tuple[str, str], ...]
    #: the extracted values that may legitimately be stored, as (quantity, values); may be empty
    data: tuple[tuple[str, tuple[float, ...]], ...]
    #: sha256 of the bytes the values were extracted from (the fetched file); "" only for an analytic reference
    source_digest: str
    extraction: str
    envelope: tuple[EnvelopeBound, ...] = ()

    def __post_init__(self) -> None:
        for label in ("reference_id", "title", "authors", "publication", "license_status", "extraction"):
            object.__setattr__(self, label, _text(getattr(self, label), f"reference {label}"))
        object.__setattr__(self, "kind", OracleKind(self.kind))
        names = [c.name for c in self.conditions]
        if len(set(names)) != len(names):
            raise InvalidScientificProblem("a reference states each condition once")
        if self.kind is not OracleKind.ANALYTIC_REFERENCE:
            if not str(self.access_url).startswith("https://"):
                raise InvalidScientificProblem("a numerical or experimental reference names its https source")
            object.__setattr__(self, "source_digest", _hex64(self.source_digest, "reference source digest"))
            if not self.conditions:
                raise InvalidScientificProblem("a numerical or experimental reference states the conditions it was produced under")
        elif self.source_digest:
            object.__setattr__(self, "source_digest", _hex64(self.source_digest, "reference source digest"))
        declared = {q for q, _ in self.quantities}
        for q, values in self.data:
            if q not in declared:
                raise InvalidScientificProblem(f"reference data {q!r} is not a declared quantity")
            if not all(math.isfinite(float(v)) for v in values):
                raise InvalidScientificProblem("reference data are finite")
        if {b.name for b in self.envelope} - set(names):
            raise InvalidScientificProblem("an applicability bound names a condition the reference does not state")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": REFERENCE_SCHEMA, "reference_id": self.reference_id, "title": self.title, "authors": self.authors,
                "publication": self.publication, "access_url": self.access_url, "license_status": self.license_status,
                "kind": self.kind.value, "conditions": [c.to_dict() for c in self.conditions],
                "quantities": [list(q) for q in self.quantities],
                "data": [[q, [repr(float(v)) for v in values]] for q, values in self.data],
                "source_digest": self.source_digest, "extraction": self.extraction, "envelope": [b.to_dict() for b in self.envelope]}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def values(self, quantity: str) -> tuple[float, ...]:
        for q, values in self.data:
            if q == quantity:
                return values
        raise InvalidScientificProblem(f"reference {self.reference_id!r} stores no values for {quantity!r}")

    def unit_of(self, quantity: str) -> str:
        for q, unit in self.quantities:
            if q == quantity:
                return unit
        raise InvalidScientificProblem(f"reference {self.reference_id!r} has no quantity {quantity!r}")

    def applicability(self, conditions: Mapping[str, Quantity]) -> ReferenceApplicability:
        """Whether the flagship's conditions lie inside the reference's stated envelope.  Missing never means within."""
        if not self.envelope:
            return ReferenceApplicability("unknown", ("the reference declares no applicability envelope; it is never assumed to apply",))
        reasons: list[str] = []
        outside = False
        unknown = False
        for bound in self.envelope:
            got = conditions.get(bound.name)
            if got is None:
                unknown = True
                reasons.append(f"condition {bound.name!r} of the flagship is not stated")
                continue
            x = got.magnitude_in(bound.unit)
            if not (bound.low <= x <= bound.high):
                outside = True
                reasons.append(f"{bound.name} = {x:.6g} {bound.unit} is outside the reference range [{bound.low:g}, {bound.high:g}]")
        if outside:
            return ReferenceApplicability("outside", tuple(reasons))
        if unknown:
            return ReferenceApplicability("unknown", tuple(reasons))
        return ReferenceApplicability("within", ("every declared condition is known and inside the reference envelope",))


@dataclass(frozen=True)
class PredeclaredCriterion:
    """A comparison criterion fixed BEFORE the result it judges existed.

    ``declared_in`` names where it was fixed (a source file / commit / preregistration).  Its digest covers the
    tolerance, so changing the tolerance later makes a different criterion; the original is never edited away.
    """

    criterion_id: str
    quantity: str
    metric: str
    tolerance: Quantity
    declared_in: str
    post_hoc: bool = False

    def __post_init__(self) -> None:
        for label in ("criterion_id", "quantity", "metric", "declared_in"):
            object.__setattr__(self, label, _text(getattr(self, label), f"criterion {label}"))
        if not (math.isfinite(self.tolerance.magnitude) and self.tolerance.magnitude >= 0):
            raise InvalidScientificProblem("a comparison tolerance is finite and non-negative, and declared")

    def to_dict(self) -> dict[str, Any]:
        return {"criterion_id": self.criterion_id, "quantity": self.quantity, "metric": self.metric, "tolerance": self.tolerance.to_dict(),
                "declared_in": self.declared_in, "post_hoc": self.post_hoc}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())


@dataclass(frozen=True)
class ReferenceComparison:
    """One measured difference between a flagship result and a reference, judged by a criterion."""

    reference_digest: str
    reference_kind: OracleKind
    applicability: ReferenceApplicability
    criterion: PredeclaredCriterion
    #: what was compared with what (the predicted values' own identity, e.g. a provider record digest)
    compared_identity: str
    value: Quantity
    within_tolerance: bool
    #: "met" | "not_met" | "not_applicable" - a reference that does not apply is never read as met OR unmet
    outcome: str
    note: str = ""

    def __post_init__(self) -> None:
        if self.outcome not in ("met", "not_met", "not_applicable"):
            raise InvalidScientificProblem("comparison outcome is met, not_met or not_applicable")
        if (self.applicability.status != "within") != (self.outcome == "not_applicable"):
            raise InvalidScientificProblem("a comparison is read only when the reference applies; otherwise it is not_applicable")
        if self.outcome != "not_applicable" and (self.outcome == "met") != self.within_tolerance:
            raise InvalidScientificProblem("comparison outcome disagrees with its tolerance check")

    @property
    def classification(self) -> str:
        base = COMPARISON_CLASSIFICATIONS[self.reference_kind]
        return f"post_hoc_{base}" if self.criterion.post_hoc else base

    def to_dict(self) -> dict[str, Any]:
        return {"classification": self.classification, "reference_digest": self.reference_digest, "reference_kind": self.reference_kind.value,
                "applicability": self.applicability.to_dict(), "criterion": self.criterion.to_dict(), "criterion_digest": self.criterion.digest,
                "compared_identity": self.compared_identity, "value": self.value.to_dict(), "within_tolerance": self.within_tolerance,
                "outcome": self.outcome, "note": self.note}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())


def compare_to_reference(reference: ReferenceRecord, criterion: PredeclaredCriterion, conditions: Mapping[str, Quantity], *,
                         value: Quantity, compared_identity: str, note: str = "") -> ReferenceComparison:
    """Judge one already-computed difference ``value`` by a criterion, only if the reference applies to ``conditions``."""
    applicability = reference.applicability(conditions)
    if applicability.status != "within":
        return ReferenceComparison(reference.digest, reference.kind, applicability, criterion, compared_identity, value, False, "not_applicable", note)
    ok = value.magnitude_in(criterion.tolerance.units) <= criterion.tolerance.magnitude
    return ReferenceComparison(reference.digest, reference.kind, applicability, criterion, compared_identity, value, ok, "met" if ok else "not_met", note)
