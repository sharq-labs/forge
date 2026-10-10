"""TwinRevision evidence resolved against SRIA evidence records and the gateway's belief.

Lives in the claim layer: SRIA imports only the Scientific Core, so the bridge
between a ``systems`` twin revision and SRIA records sits above both.

A :class:`~engcore.systems.twin_revision.TwinRevision` carries
:class:`~engcore.systems.twin_revision.EvidenceReference` pointers (role +
context digest).  Pointers are not evidence.  This module resolves each
pointer to the SRIA :class:`~engcore.sria.evidence.Evidence` record it names
and refuses the revision unless every pointer is backed:

* the pointer names ONE exact record: ``sria:<evidence_id>@<record_hash>``;
  the record's integrity is re-checked (``record_hash`` re-derives content
  identity), so an edited or swapped record does not resolve;
* the record was produced for the revision's context: ``context_ref`` equals
  the pointer's (and therefore the revision's) context digest;
* the role is one that record can play (:data:`ROLE_RULES`): validation needs a
  MEASUREMENT record making a model support/contradiction claim, calibration a
  CALIBRATION_REFERENCE claim from measurement, and so on.  A simulation record
  never backs validation, calibration or measurement;
* the record's lifecycle standing meets the role's bar: physical-truth roles
  (validation, calibration, measurement) need ACCEPTED AND an active entry
  for exactly this record in the gateway's belief -- a record's own status
  field is not admission; SUSPENDED, INVALID and SUPERSEDED records back
  nothing.

* validation and calibration records must be ABOUT one of the twin's declared
  models (``claim_binding.subject_ref``);
* verification needs at least one PASS critic assessment and no FAIL or
  INCONCLUSIVE one (assessments are not part of the record identity: a
  verification pointer confers no physical authority, only "this numerics
  check was assessed as passing"); a provider-run pointer is "recorded" only.

Withdrawing a record's standing therefore withdraws the support.

What resolution is NOT: a validation verdict.  It checks that each attached
pointer is backed; it does not weigh them.  A support/contradiction record's
polarity is reported as the record states it (``claim_payload["polarity"]``,
else ``"unstated"``), and every ACTIVE belief entry for this context that the
revision does NOT point at is listed in ``unreferenced_active_evidence`` --
omitting a contradicting measurement is visible, never silent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from ..systems.twin_revision import EvidenceReference, EvidenceRole, TwinRevision
from ..sria.errors import EvidenceError
from ..sria.evidence import AssessmentVerdict, ClaimType, Evidence, EvidenceStatus, SourceClass
from ..sria.gateway import ScientificBelief

SRIA_REF_PREFIX = "sria:"

_PHYSICAL = frozenset({EvidenceStatus.ACCEPTED})
_RECORDED = frozenset({EvidenceStatus.CANDIDATE, EvidenceStatus.UNBOUND, EvidenceStatus.ASSESSED, EvidenceStatus.ACCEPTED})
_ASSESSED = frozenset({EvidenceStatus.ASSESSED, EvidenceStatus.ACCEPTED})


@dataclass(frozen=True)
class RoleRule:
    sources: frozenset[SourceClass]
    claims: frozenset[ClaimType]
    statuses: frozenset[EvidenceStatus]
    why: str


#: Which SRIA records may back which twin evidence role, and at what standing.
ROLE_RULES: Mapping[EvidenceRole, RoleRule] = {
    EvidenceRole.VALIDATION: RoleRule(frozenset({SourceClass.MEASUREMENT}), frozenset({ClaimType.MODEL_SUPPORT_OR_CONTRADICTION}),
                                      _PHYSICAL, "validation compares a model with an admitted physical observation"),
    EvidenceRole.CALIBRATION: RoleRule(frozenset({SourceClass.MEASUREMENT}), frozenset({ClaimType.CALIBRATION_REFERENCE}),
                                       _PHYSICAL, "calibration fits parameters to an admitted observation (it is not validation)"),
    EvidenceRole.MEASUREMENT: RoleRule(frozenset({SourceClass.MEASUREMENT}), frozenset({ClaimType.PARAMETER_VALUE, ClaimType.QOI_VALUE}),
                                       _PHYSICAL, "a measurement is an admitted observation record"),
    EvidenceRole.VERIFICATION: RoleRule(frozenset({SourceClass.SIMULATION, SourceClass.BENCHMARK}),
                                        frozenset({ClaimType.QOI_VALUE, ClaimType.MODEL_SUPPORT_OR_CONTRADICTION}),
                                        _ASSESSED, "verification is a numerics/code check assessed as passing, never a physical comparison"),
    EvidenceRole.PROVIDER_RUN: RoleRule(frozenset({SourceClass.SIMULATION}), frozenset({ClaimType.QOI_VALUE, ClaimType.PARAMETER_VALUE}),
                                        _RECORDED, "a provider computation: recorded, not evidence of physical truth"),
}


class TwinEvidenceRefused(EvidenceError):
    """A twin evidence pointer that no admissible SRIA record backs."""


def sria_reference(evidence: Evidence, role: EvidenceRole | str) -> EvidenceReference:
    """The pointer to exactly this record, bound to the context the record was produced for."""
    if not isinstance(evidence, Evidence):
        raise TwinEvidenceRefused("a twin evidence pointer is built from an SRIA Evidence record")
    role = EvidenceRole(role)
    _check_role(evidence, role)
    if len(evidence.context_ref) != 64:
        raise TwinEvidenceRefused(f"evidence {evidence.evidence_id!r} names no 64-hex context; it cannot be bound to a twin context")
    return EvidenceReference(f"{SRIA_REF_PREFIX}{evidence.evidence_id}@{evidence.record_hash}", role, evidence.context_ref)


def _check_role(evidence: Evidence, role: EvidenceRole) -> None:
    rule = ROLE_RULES[role]
    if evidence.source_class not in rule.sources or evidence.claim_type not in rule.claims:
        raise TwinEvidenceRefused(f"evidence {evidence.evidence_id!r} ({evidence.source_class.value} / {evidence.claim_type.value}) "
                                  f"cannot back the {role.value} role: {rule.why}")
    if evidence.status not in rule.statuses:
        raise TwinEvidenceRefused(f"evidence {evidence.evidence_id!r} is {evidence.status.value}; the {role.value} role needs "
                                  f"{sorted(s.value for s in rule.statuses)}")
    if role is EvidenceRole.VERIFICATION:
        verdicts = {a.verdict for a in evidence.assessments}
        if AssessmentVerdict.PASS not in verdicts or verdicts & {AssessmentVerdict.FAIL, AssessmentVerdict.INCONCLUSIVE}:
            raise TwinEvidenceRefused(f"evidence {evidence.evidence_id!r} backs verification only with a PASS assessment and no "
                                      f"FAIL or INCONCLUSIVE one (has {sorted(v.value for v in verdicts) or 'none'})")


def _parse(ref: str) -> tuple[str, str]:
    if not ref.startswith(SRIA_REF_PREFIX) or "@" not in ref:
        raise TwinEvidenceRefused(f"evidence pointer {ref!r} does not name an SRIA record (sria:<evidence_id>@<record_hash>)")
    evidence_id, _, record_hash = ref[len(SRIA_REF_PREFIX):].rpartition("@")
    if not evidence_id or len(record_hash) != 64:
        raise TwinEvidenceRefused(f"evidence pointer {ref!r} is malformed")
    return evidence_id, record_hash


@dataclass(frozen=True)
class ResolvedTwinEvidence:
    """Audit view: which record backs each pointer, at what standing."""

    revision_id: str
    context_digest: str
    entries: tuple[Mapping[str, Any], ...]
    #: active belief entries for this context the revision does not point at (evidence ids); never silently dropped
    unreferenced_active_evidence: tuple[str, ...] = ()
    classification: str = "pointer_resolution_not_a_validation_verdict"

    def to_dict(self) -> dict[str, Any]:
        return {"schema": "engcore.claims.resolved_twin_evidence/1", "classification": self.classification, "revision_id": self.revision_id,
                "context_digest": self.context_digest, "entries": [dict(e) for e in self.entries],
                "unreferenced_active_evidence": list(self.unreferenced_active_evidence)}


#: Roles whose authority comes from admission into belief, not from the record alone.
BELIEF_ROLES = frozenset({EvidenceRole.VALIDATION, EvidenceRole.CALIBRATION, EvidenceRole.MEASUREMENT})


def resolve_twin_evidence(revision: TwinRevision, records: Iterable[Evidence], *, belief: Any = None) -> ResolvedTwinEvidence:
    """Resolve every pointer of ``revision`` against SRIA ``records``; refuse on the first one not backed.

    ``belief`` is the gateway's :class:`~engcore.sria.gateway.ScientificBelief` (``gateway.belief``); it is
    required whenever a pointer plays a validation, calibration or measurement role."""
    if not isinstance(revision, TwinRevision):
        raise TwinEvidenceRefused("resolve_twin_evidence takes a TwinRevision")
    if belief is not None and not isinstance(belief, ScientificBelief):
        raise TwinEvidenceRefused("belief must be the gateway's ScientificBelief; a look-alike mapping is not admission")
    model_ids = {m.model_id for m in revision.twin.models}
    by_id: dict[str, Evidence] = {}
    for rec in records:
        if not isinstance(rec, Evidence):
            raise TwinEvidenceRefused("twin evidence resolves against SRIA Evidence records only")
        if rec.evidence_id in by_id and by_id[rec.evidence_id].record_hash != rec.record_hash:
            raise TwinEvidenceRefused(f"two different records carry evidence id {rec.evidence_id!r}")
        by_id[rec.evidence_id] = rec
    ctx = revision.context_digest
    entries = []
    for pointer in revision.evidence:
        evidence_id, record_hash = _parse(pointer.ref)
        rec = by_id.get(evidence_id)
        if rec is None:
            raise TwinEvidenceRefused(f"evidence {evidence_id!r} is not among the supplied SRIA records; a missing record backs nothing")
        if rec.record_hash != record_hash:  # also re-checks content integrity
            raise TwinEvidenceRefused(f"evidence {evidence_id!r} is another record than the pointer names (record hash differs)")
        if rec.context_ref != pointer.context_digest or pointer.context_digest != ctx:
            raise TwinEvidenceRefused(f"evidence {evidence_id!r} was produced for context {rec.context_ref[:12] or '(none)'}, "
                                      f"not this revision's {ctx[:12]}")
        _check_role(rec, pointer.role)
        if pointer.role in (EvidenceRole.VALIDATION, EvidenceRole.CALIBRATION) and rec.claim_binding.subject_ref not in model_ids:
            raise TwinEvidenceRefused(f"evidence {evidence_id!r} is about {rec.claim_binding.subject_ref!r}, not one of the twin's models "
                                      f"{sorted(model_ids)}")
        if pointer.role in BELIEF_ROLES:
            if belief is None:
                raise TwinEvidenceRefused(f"evidence {evidence_id!r} plays the {pointer.role.value} role, whose authority is "
                                          "admission into belief: the gateway's belief must be supplied")
            entry = belief.active_view().get(evidence_id)
            if entry is None or entry.record_hash != record_hash:
                raise TwinEvidenceRefused(f"evidence {evidence_id!r} is not an active belief entry for this exact record; "
                                          f"its {pointer.role.value} role is not backed")
        standing = "admitted_in_belief" if pointer.role in BELIEF_ROLES else (
            "assessed_pass" if pointer.role is EvidenceRole.VERIFICATION else "recorded")
        entries.append({"ref": pointer.ref, "role": pointer.role.value, "evidence_id": evidence_id, "record_hash": record_hash,
                        "status": rec.status.value, "standing": standing, "source_class": rec.source_class.value,
                        "claim_type": rec.claim_type.value, "subject": rec.claim_binding.key,
                        "polarity": str(rec.claim_payload.get("polarity", "unstated"))})
    unreferenced: tuple[str, ...] = ()
    if belief is not None:
        pointed = {_parse(p.ref)[0] for p in revision.evidence}
        unreferenced = tuple(sorted(eid for eid, entry in belief.active_view().items()
                                    if entry.belief_key.endswith(f"|context:{ctx}") and eid not in pointed))
    return ResolvedTwinEvidence(revision.revision_id, ctx, tuple(entries), unreferenced)


__all__ = ["BELIEF_ROLES", "ROLE_RULES", "ResolvedTwinEvidence", "RoleRule", "SRIA_REF_PREFIX", "TwinEvidenceRefused", "resolve_twin_evidence",
           "sria_reference"]
