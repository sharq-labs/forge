"""External / analytic reference data with provenance, applicability and pre-declared comparison criteria.

A reference is what an engineer compares a result AGAINST.  It is not evidence by itself and it grants
nothing: validation levels stay owned by ``engcore.scientific.oracles`` and its repository-pinned
declarations.  This module records what the reference is (analytic / numerical benchmark / experimental),
where it came from, what conditions it was produced under, and whether a given flagship is inside them.

Rules kept here on purpose:

* the kind reuses :class:`engcore.scientific.oracles.OracleKind`; a numerical benchmark is never labelled
  experimental (``benchmark_dataset`` is not ``experimental_dataset``);
* a numerical or experimental reference must carry a source digest and an https access URL; only an analytic reference may have
  neither.  ``source_digest`` is the sha256 of the bytes the values were extracted from, or, when several source files were used,
  of the concatenation of THEIR sha256 hex digests in the order the flagship states (the source bytes themselves are not
  stored here when their license does not allow it);
* applicability is ``within`` only when EVERY declared envelope condition is known and inside; a missing
  condition or a missing envelope is ``unknown``, never ``within``;
* a comparison is either PRE-REGISTERED (its criterion is listed in the flagships' pre-registration file; git cannot show that it preceded the first
  run) or it is labelled post hoc; a tolerance edited after seeing a result is a different criterion with a different
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

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReferenceCondition":
        return cls(payload["name"], float(payload["value"]), payload["unit"])


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

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EnvelopeBound":
        return cls(payload["name"], float(payload["low"]), float(payload["high"]), payload["unit"])


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
    #: "implementation_limit": an exact/closed-form relation the implementation must reproduce;
    #: "data_consistency": an analytic relation evaluated with tabulated (evaluated) reference DATA, so it checks the data the
    #: model carries, not just the implementation
    role: str = "implementation_limit"
    #: the names a comparison criterion may bind to (the compared quantity, e.g. a max centerline error); a criterion naming anything
    #: else is refused, so a tolerance cannot be attached to a reference that says nothing about that quantity
    comparable_quantities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.role not in ("implementation_limit", "data_consistency"):
            raise InvalidScientificProblem("reference role is implementation_limit or data_consistency")
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
        object.__setattr__(self, "comparable_quantities", tuple(_text(q, "comparable quantity") for q in self.comparable_quantities))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": REFERENCE_SCHEMA, "reference_id": self.reference_id, "title": self.title, "authors": self.authors,
                "publication": self.publication, "access_url": self.access_url, "license_status": self.license_status,
                "kind": self.kind.value, "conditions": [c.to_dict() for c in self.conditions],
                "quantities": [list(q) for q in self.quantities],
                "data": [[q, [repr(float(v)) for v in values]] for q, values in self.data],
                "source_digest": self.source_digest, "extraction": self.extraction, "envelope": [b.to_dict() for b in self.envelope], "role": self.role,
                "comparable_quantities": list(self.comparable_quantities)}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReferenceRecord":
        """Rebuild a reference from its serialized form (re-running every guard); the result must serialize back to exactly ``payload``."""
        if payload.get("schema") != REFERENCE_SCHEMA:
            raise InvalidScientificProblem("not a Forge reference record")
        record = cls(
            payload["reference_id"], payload["title"], payload["authors"], payload["publication"], payload["access_url"], payload["license_status"],
            OracleKind(payload["kind"]), tuple(ReferenceCondition.from_dict(c) for c in payload["conditions"]),
            tuple((q, u) for q, u in payload["quantities"]), tuple((q, tuple(float(v) for v in values)) for q, values in payload["data"]),
            payload["source_digest"], payload["extraction"], tuple(EnvelopeBound.from_dict(e) for e in payload["envelope"]), payload["role"],
            tuple(payload.get("comparable_quantities", ())))
        if canonical_digest(record.to_dict()) != canonical_digest(payload):
            raise InvalidScientificProblem("the reference record does not serialize back to the payload it was read from")
        return record

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

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PredeclaredCriterion":
        return cls(payload["criterion_id"], payload["quantity"], payload["metric"], Quantity.from_dict(payload["tolerance"]), payload["declared_in"],
                   bool(payload["post_hoc"]))


@dataclass(frozen=True)
class ReferenceComparison:
    """One measured difference between a flagship result and a reference, judged by a criterion.

    Everything a reader relies on is DERIVED from what the caller supplies - the reference, the criterion, the conditions the flagship states
    and the compared difference: the reference's applicability is evaluated here, the tolerance outcome is re-derived as a SPREAD, the
    classification follows the reference's kind and role.  There is no field to set an outcome, an applicability or a kind, so none can be
    forged, and a bundle can rebuild a comparison from its shipped reference and check the record byte for byte (``from_dict``)."""

    reference: ReferenceRecord
    criterion: PredeclaredCriterion
    #: the flagship's own statement of the conditions the reference's envelope is checked against (name, value); missing never means within
    conditions: tuple[tuple[str, Quantity], ...]
    #: the compared difference: a finite non-negative magnitude
    value: Quantity
    #: what was compared with what (the predicted values' own identity, e.g. a provider record digest)
    compared_identity: str
    note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.reference, ReferenceRecord) or not isinstance(self.criterion, PredeclaredCriterion):
            raise InvalidScientificProblem("a comparison names a ReferenceRecord and a PredeclaredCriterion")
        if not math.isfinite(self.value.magnitude) or self.value.magnitude < 0:
            raise InvalidScientificProblem("a compared difference is a finite non-negative magnitude (a signed value would read as met)")
        conditions = tuple(sorted(((str(n), q) for n, q in self.conditions), key=lambda nq: nq[0]))
        if len({n for n, _ in conditions}) != len(conditions):
            raise InvalidScientificProblem("a comparison states each condition once")
        object.__setattr__(self, "conditions", conditions)
        object.__setattr__(self, "compared_identity", _text(self.compared_identity, "compared identity"))
        if self.criterion.quantity not in self.reference.comparable_quantities:
            raise InvalidScientificProblem(f"criterion {self.criterion.criterion_id!r} compares {self.criterion.quantity!r}, which reference "
                                           f"{self.reference.reference_id!r} does not declare as comparable {list(self.reference.comparable_quantities)}")

    @property
    def reference_digest(self) -> str:
        return self.reference.digest

    @property
    def reference_kind(self) -> OracleKind:
        return self.reference.kind

    @property
    def role(self) -> str:
        return self.reference.role

    @property
    def applicability(self) -> ReferenceApplicability:
        return self.reference.applicability(dict(self.conditions))

    @property
    def within_tolerance(self) -> bool | None:
        """None when the reference does not apply: nothing was judged, so neither True nor False is stated."""
        return _within(self.value, self.criterion) if self.applicability.status == "within" else None

    @property
    def outcome(self) -> str:
        """"met" | "not_met" | "not_applicable" - a reference that does not apply is never read as met OR unmet."""
        w = self.within_tolerance
        return "not_applicable" if w is None else ("met" if w else "not_met")

    @property
    def classification(self) -> str:
        base = COMPARISON_CLASSIFICATIONS[self.reference_kind]
        if self.reference_kind is OracleKind.ANALYTIC_REFERENCE and self.role == "data_consistency":
            base = "reference_data_consistency_check_not_validation"
        return f"post_hoc_{base}" if self.criterion.post_hoc else base

    def to_dict(self) -> dict[str, Any]:
        applicability = self.applicability
        return {"classification": self.classification, "reference_digest": self.reference_digest, "reference_kind": self.reference_kind.value,
                "applicability": applicability.to_dict(), "criterion": self.criterion.to_dict(), "criterion_digest": self.criterion.digest,
                "conditions": [[n, q.to_dict()] for n, q in self.conditions], "compared_identity": self.compared_identity,
                "value": self.value.to_dict(), "within_tolerance": self.within_tolerance, "outcome": self.outcome, "note": self.note}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any], reference: ReferenceRecord) -> "ReferenceComparison":
        """Rebuild a comparison from its record and the reference it names; every derived field must come out exactly as recorded."""
        comparison = cls(reference, PredeclaredCriterion.from_dict(payload["criterion"]),
                         tuple((n, Quantity.from_dict(q)) for n, q in payload["conditions"]), Quantity.from_dict(payload["value"]),
                         payload["compared_identity"], payload.get("note", ""))
        if canonical_digest(comparison.to_dict()) != canonical_digest(payload):
            raise InvalidScientificProblem(f"comparison {payload.get('criterion', {}).get('criterion_id')!r} is not what its reference, criterion, "
                                           "conditions and value derive (a stated outcome, applicability, kind or classification was edited)")
        return comparison


def _within(value: Quantity, criterion: PredeclaredCriterion) -> bool:
    """A compared difference is a SPREAD: it converts by the linear part of a unit map only (a 5 K difference is not -268 degC)."""
    return value.magnitude_as_spread_in(criterion.tolerance.units) <= criterion.tolerance.magnitude


def compare_to_reference(reference: ReferenceRecord, criterion: PredeclaredCriterion, conditions: Mapping[str, Quantity], *,
                         value: Quantity, compared_identity: str, note: str = "") -> ReferenceComparison:
    """Judge one already-computed difference ``value`` by a criterion, only if the reference applies to ``conditions``."""
    return ReferenceComparison(reference, criterion, tuple(conditions.items()), value, compared_identity, note)
