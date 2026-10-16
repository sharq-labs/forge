"""Which material properties a run states it needs, and how each one resolves.

A :class:`MaterialCoverageReport` is a READ of :meth:`MaterialPropertySet.resolve`
for the properties a model is STATED to require, at one exact
:class:`MaterialState`. It adds no resolution logic and no authority:

* every stated property is resolved afresh at the given state, so a changed
  state is a changed report (nothing is cached across states);
* the requirement list is a caller's statement, recorded with its declared
  source; when the run's own :class:`ResolvedProperty` records are supplied
  (``consumed``), a consumed property that was not stated, or a record that
  does not match a fresh resolution at this state, is refused;
* an UNKNOWN resolution stays UNKNOWN, with the resolver's own reason; a
  conflict between admissible sources is listed as a conflict;
* a value whose uncertainty is UNKNOWN is listed as such -- a value is not an
  uncertainty, and an interpolated value never inherits the tabulated spread;
* properties the set holds data for but that were NOT stated as required are
  named, not resolved and not judged: a missing value nobody needs is not a gap.

The report is ``resolution_report_not_evidence``. Its status says whether every
stated requirement HAS A VALUE; it says nothing about whether those values,
or the run, are valid.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from ..scenarios.timeline import canonical_digest
from ..scientific.errors import InvalidScientificProblem
from ..scientific.results.uncertainty import UncertaintyKind, UncertaintySource
from ..scientific.serialization import schema_string
from .identity import MaterialState, _identifier
from .properties import MaterialPropertySet, PropertyDerivation, ResolvedProperty

COVERAGE_SCHEMA = schema_string("material_property_coverage")
ENTRY_SCHEMA = schema_string("material_property_coverage_entry")

EVERY_STATED_REQUIREMENT_HAS_A_VALUE = "every_stated_requirement_has_a_value"
A_STATED_REQUIREMENT_HAS_NO_VALUE = "a_stated_requirement_has_no_value"


@dataclass(frozen=True)
class PropertyCoverageEntry:
    """One stated property: the resolution record plus what a reader must see first."""

    resolved: ResolvedProperty

    def __post_init__(self) -> None:
        if not isinstance(self.resolved, ResolvedProperty):
            raise InvalidScientificProblem("coverage entry requires a ResolvedProperty")

    @property
    def property_id(self) -> str:
        return self.resolved.property_id

    @property
    def uncertainty_kind(self) -> str:
        """The value's uncertainty kind, or ``""`` when there is no value at all."""
        value = self.resolved.value
        return "" if value is None else UncertaintyKind(value.uncertainty.kind).value

    @property
    def uncertainty_source_kind(self) -> str:
        """What the uncertainty is an uncertainty OF, or ``""`` when there is no value."""
        value = self.resolved.value
        return "" if value is None else UncertaintySource(value.uncertainty.source_kind).value

    @property
    def conflicted(self) -> bool:
        """No value because several admissible data disagree (the resolver names them all)."""
        r = self.resolved
        return r.status == "unknown" and r.rule is None and len(r.claim_digests) > 1

    def to_dict(self) -> dict[str, Any]:
        r = self.resolved
        return {
            "schema": ENTRY_SCHEMA, "property_id": r.property_id, "status": r.status,
            "derivation": r.derivation.value, "value": None if r.value is None else r.value.to_dict(),
            "uncertainty_kind": self.uncertainty_kind, "uncertainty_source_kind": self.uncertainty_source_kind,
            "conflicted": self.conflicted, "origins": list(r.origins), "source_ids": [s.source_id for s in r.sources],
            "claim_digests": list(r.claim_digests), "rule": None if r.rule is None else r.rule.to_dict(),
            "resolved_digest": r.digest, "reason": r.reason,
        }


@dataclass(frozen=True)
class MaterialCoverageReport:
    """Coverage of the STATED requirements at one state of one property set."""

    requirement_source: str
    set_digest: str
    material_digest: str
    state_digest: str
    entries: tuple[PropertyCoverageEntry, ...]
    unrequired_with_data: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "requirement_source", _identifier(self.requirement_source, "requirement_source"))
        entries = tuple(self.entries)
        if not entries or any(not isinstance(e, PropertyCoverageEntry) for e in entries):
            raise InvalidScientificProblem("a coverage report covers at least one stated requirement")
        ids = [e.property_id for e in entries]
        if ids != sorted(set(ids)):
            raise InvalidScientificProblem("coverage entries must be unique and sorted by property id")
        for e in entries:
            if e.resolved.state_digest != self.state_digest or e.resolved.set_digest != self.set_digest:
                raise InvalidScientificProblem(
                    f"{e.property_id!r} was resolved at another state or from another property set"
                )
        unrequired = tuple(self.unrequired_with_data)
        if list(unrequired) != sorted(set(unrequired)) or set(unrequired) & set(ids):
            raise InvalidScientificProblem("unrequired properties must be unique, sorted and disjoint from the stated ones")
        object.__setattr__(self, "entries", entries)
        object.__setattr__(self, "unrequired_with_data", unrequired)

    def _ids(self, keep) -> tuple[str, ...]:
        return tuple(e.property_id for e in self.entries if keep(e))

    @property
    def without_value(self) -> tuple[str, ...]:
        return self._ids(lambda e: e.resolved.status == "unknown")

    @property
    def conflicted(self) -> tuple[str, ...]:
        return self._ids(lambda e: e.conflicted)

    @property
    def uncertainty_unknown(self) -> tuple[str, ...]:
        return self._ids(lambda e: e.resolved.status == "known" and e.uncertainty_kind == UncertaintyKind.UNKNOWN.value)

    @property
    def assumed(self) -> tuple[str, ...]:
        return self._ids(lambda e: e.resolved.derivation is PropertyDerivation.ASSUMED)

    @property
    def interpolated(self) -> tuple[str, ...]:
        return self._ids(lambda e: e.resolved.derivation is PropertyDerivation.INTERPOLATED)

    @property
    def status(self) -> str:
        return A_STATED_REQUIREMENT_HAS_NO_VALUE if self.without_value else EVERY_STATED_REQUIREMENT_HAS_A_VALUE

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": COVERAGE_SCHEMA, "classification": "resolution_report_not_evidence",
            "status": self.status, "requirement_source": self.requirement_source,
            "set_digest": self.set_digest, "material_digest": self.material_digest, "state_digest": self.state_digest,
            "stated_requirements": [e.to_dict() for e in self.entries],
            "without_value": list(self.without_value), "conflicted": list(self.conflicted),
            "uncertainty_unknown": list(self.uncertainty_unknown),
            "assumed": list(self.assumed), "interpolated": list(self.interpolated),
            "unrequired_with_data": list(self.unrequired_with_data),
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())


def material_coverage_report(
    property_set: MaterialPropertySet, state: MaterialState, required: Iterable[str], *,
    requirement_source: str, consumed: Iterable[ResolvedProperty] = (),
) -> MaterialCoverageReport:
    """Resolve each STATED requirement at ``state`` and report how it resolved.

    ``required`` is what the model is stated to consume and ``requirement_source``
    names who stated it (e.g. a model/realization id); an empty requirement would
    report full coverage of nothing and is refused. ``consumed``, when given, are
    the run's own resolution records: each must be stated as required and must be
    exactly what a fresh resolution at ``state`` produces.
    """
    if not isinstance(property_set, MaterialPropertySet):
        raise InvalidScientificProblem("coverage requires a MaterialPropertySet")
    if not isinstance(state, MaterialState):
        raise InvalidScientificProblem("coverage requires a MaterialState")
    if isinstance(required, str):
        raise InvalidScientificProblem("required properties are a collection of identifiers, not one string")
    ids = [_identifier(p, "required property_id") for p in required]
    if not ids:
        raise InvalidScientificProblem("coverage requires the properties the model consumes; none were stated")
    if len(set(ids)) != len(ids):
        raise InvalidScientificProblem("a required property is listed twice")
    ids.sort()
    entries = tuple(PropertyCoverageEntry(property_set.resolve(pid, state)) for pid in ids)
    fresh = {e.property_id: e.resolved.digest for e in entries}
    for record in consumed:
        if not isinstance(record, ResolvedProperty):
            raise InvalidScientificProblem("consumed records must be ResolvedProperty records")
        if record.property_id not in fresh:
            raise InvalidScientificProblem(f"the run consumed {record.property_id!r}, which was not stated as required")
        if record.digest != fresh[record.property_id]:
            raise InvalidScientificProblem(
                f"the run's {record.property_id!r} record is not what this set resolves at this state"
            )
    held = {d.applicability.property_id for d in property_set.data}
    return MaterialCoverageReport(
        requirement_source, property_set.digest, property_set.material.digest, state.digest, entries,
        tuple(sorted(held - set(ids))),
    )
