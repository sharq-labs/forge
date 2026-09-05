"""The Belief Update Gateway — SRIA's single architectural invariant.

    NO SOURCE WRITES SCIENTIFIC BELIEF DIRECTLY.

Not the solver, not an LLM, not a future Digger, not a Digital Twin, not a raw
measurement stream, not an archive import. The only path is:

    Candidate Evidence -> Critics/Assessments -> Arbiter admission
                       -> Belief Update Gateway -> Scientific Belief

Everything else in SRIA can be replaced. This cannot, because it is what makes
the difference between a research system and a plausible-sounding one: when a
number ends up in belief, there is exactly one code path that put it there and
exactly one record explaining why.

**What the enforcement is.** This is an *architectural capability boundary*,
not security isolation. :class:`ScientificBelief` exposes no public mutator and
its write method demands a token that only this module mints, so belief cannot
be written accidentally, incidentally, or through any supported API — every
write goes through one reviewable path and leaves one record. Python offers no
memory isolation: code that deliberately imports private names, monkey-patches
this module, or manipulates the interpreter can bypass it. The boundary is
designed to make unauthorized writes *impossible by accident and obvious on
purpose*, which is the property an architecture can actually provide.

Admission carries the same caveat and one addition: a declaration must be
attributable to a registered :class:`~engcore.sria.admission.AdmissionAuthority`
and bound to the specific evidence record. A gateway with no registry admits
nothing. That closes the M1 gap where any caller could hand-build an
``AdmissionDeclaration`` and walk it through.

**Rejection is procedural, never epistemic.** A refused, unsigned or mis-bound
admission leaves belief unchanged *and* leaves the evidence's scientific
standing unchanged. Rejections are appended to :attr:`rejection_log` so a
forgery attempt is visible rather than silent.

M1 keeps the belief store deliberately thin — it records which admitted claims
contribute to which key. No fusion, no weighting, no conflict resolution: those
are scientific strategy and belong to later milestones. What M1 fixes is *who
is allowed to write*, which is the part that is expensive to retrofit.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterator, Mapping

from ..scientific.serialization import schema_string
from .admission import (
    AdmissionAttempt,
    AdmissionAuthorityRegistry,
    AdmissionOutcome,
)
from .errors import AdmissionAuthorityError, AdmissionError, BeliefWriteViolation
from .evidence import BELIEF_BEARING_STATUS, Evidence, EvidenceStatus

BELIEF_ENTRY_SCHEMA = schema_string("sria_belief_entry")


class _GatewayToken:
    """Write capability for :class:`ScientificBelief`.

    Exactly one instance may exist; a second construction attempt raises. This
    stops write access being obtained through the supported API — it is a
    capability boundary, not a security control (see the module docstring).
    """

    __slots__ = ()
    _issued = False

    def __init__(self) -> None:
        if type(self)._issued:
            raise BeliefWriteViolation(
                "the belief write capability cannot be forged; route updates "
                "through BeliefUpdateGateway"
            )
        type(self)._issued = True


_TOKEN = _GatewayToken()


@dataclass(frozen=True)
class BeliefEntry:
    """One admitted contribution to one belief key."""

    evidence_id: str
    belief_key: str
    claim_type: str
    content_hash: str       # Scientific Content Identity — shared by like claims
    record_hash: str        # Evidence Record Identity — unique to this record
    status: EvidenceStatus
    admitted_by: str
    claim_payload: Mapping[str, Any]

    @property
    def is_active(self) -> bool:
        return self.status is BELIEF_BEARING_STATUS

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": BELIEF_ENTRY_SCHEMA,
            "evidence_id": self.evidence_id,
            "belief_key": self.belief_key,
            "claim_type": self.claim_type,
            "content_hash": self.content_hash,
            "record_hash": self.record_hash,
            "status": self.status.value,
            "admitted_by": self.admitted_by,
            "claim_payload": dict(self.claim_payload),
        }


class ScientificBelief:
    """What the platform currently holds to be supported, and by what.

    Read-only in public API. The audit trail keeps every contribution ever
    admitted; :meth:`active_view` filters to those still belief-bearing, so
    suspending evidence removes its influence without erasing the record that
    it once had influence.
    """

    def __init__(self) -> None:
        self._entries: dict[str, BeliefEntry] = {}   # evidence_id -> entry
        self._order: list[str] = []

    # ---- write path (gateway only) --------------------------------------
    def _apply(self, token: Any, entry: BeliefEntry) -> None:
        if token is not _TOKEN:
            raise BeliefWriteViolation(
                "scientific belief may only be written by the Belief Update "
                "Gateway; no source writes belief directly"
            )
        if entry.evidence_id not in self._entries:
            self._order.append(entry.evidence_id)
        self._entries[entry.evidence_id] = entry

    # ---- read path ------------------------------------------------------
    def __len__(self) -> int:
        return len(self.active_view())

    def __iter__(self) -> Iterator[BeliefEntry]:
        return iter(self.active_view().values())

    def active_view(self) -> dict[str, BeliefEntry]:
        """Currently belief-bearing contributions, keyed by evidence id."""
        return {
            eid: self._entries[eid]
            for eid in self._order
            if self._entries[eid].is_active
        }

    def audit_log(self) -> tuple[BeliefEntry, ...]:
        """Every contribution ever admitted, active or not."""
        return tuple(self._entries[eid] for eid in self._order)

    def contributions(self, belief_key: str) -> tuple[BeliefEntry, ...]:
        """Active contributions to one belief key."""
        return tuple(
            entry
            for entry in self.active_view().values()
            if entry.belief_key == belief_key
        )

    def keys(self) -> tuple[str, ...]:
        return tuple(sorted({e.belief_key for e in self.active_view().values()}))

    def supports(self, belief_key: str) -> bool:
        return bool(self.contributions(belief_key))

    def snapshot_ref(self) -> str:
        """Digest of the active view, for future Decision Provenance."""
        payload = [
            entry.to_dict() for entry in self.active_view().values()
        ]
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class BeliefUpdateGateway:
    """The only component that may write :class:`ScientificBelief`."""

    def __init__(
        self,
        belief: ScientificBelief | None = None,
        *,
        authorities: AdmissionAuthorityRegistry | None = None,
    ) -> None:
        self._belief = belief if belief is not None else ScientificBelief()
        # An empty registry is the safe default: a gateway that trusts nobody
        # admits nothing, rather than trusting whoever shows up first.
        self._authorities = (
            authorities if authorities is not None else AdmissionAuthorityRegistry()
        )
        self._rejections: list[AdmissionAttempt] = []

    @property
    def belief(self) -> ScientificBelief:
        return self._belief

    @property
    def authorities(self) -> AdmissionAuthorityRegistry:
        return self._authorities

    @property
    def rejection_log(self) -> tuple[AdmissionAttempt, ...]:
        """Append-only record of admission attempts this gateway refused."""
        return tuple(self._rejections)

    @staticmethod
    def _require_evidence(candidate: Any) -> Evidence:
        if not isinstance(candidate, Evidence):
            raise BeliefWriteViolation(
                f"only admitted Evidence may reach belief, got "
                f"{type(candidate).__name__}; a raw solver result is not "
                f"evidence until it has been bound, assessed and admitted"
            )
        return candidate

    def verify_admission(self, evidence: Evidence) -> AdmissionAttempt:
        """Check the admission declaration without writing anything."""
        if evidence.admission is None:
            return AdmissionAttempt(
                outcome=AdmissionOutcome.UNAUTHORIZED,
                reason="evidence carries no admission declaration",
                subject_record_hash=evidence.record_hash,
            )
        return self._authorities.verify(
            evidence.admission, subject_record_hash=evidence.record_hash
        )

    def _reject(self, evidence: Evidence, attempt: AdmissionAttempt) -> None:
        """Record a refusal. Belief and scientific standing both untouched."""
        self._rejections.append(attempt)
        raise AdmissionAuthorityError(
            f"admission for evidence {evidence.evidence_id!r} was not accepted "
            f"({attempt.outcome.value}): {attempt.reason}. Belief is unchanged "
            f"and the evidence keeps its scientific standing "
            f"({evidence.status.value})."
        )

    def submit(self, candidate: Any) -> BeliefEntry:
        """Admit one piece of evidence into belief.

        Refuses anything that is not ``Evidence``, anything not in ACCEPTED
        status, and any declaration that cannot be attributed to a registered
        authority and bound to this exact record.
        """
        evidence = self._require_evidence(candidate)

        if evidence.status is not BELIEF_BEARING_STATUS:
            raise BeliefWriteViolation(
                f"evidence {evidence.evidence_id!r} is {evidence.status.value}; "
                f"only {BELIEF_BEARING_STATUS.value} evidence may update belief. "
                f"Storage is not acceptance."
            )
        if evidence.admission is None:
            raise AdmissionError(
                f"evidence {evidence.evidence_id!r} carries no admitting "
                f"declaration; the Arbiter must admit before belief is written"
            )

        # verify_admission checks issuer signature, subject binding, and (M3.1)
        # that an accepting declaration names a VALID assurance decision.
        attempt = self.verify_admission(evidence)
        if not attempt.succeeded:
            self._reject(evidence, attempt)

        entry = BeliefEntry(
            evidence_id=evidence.evidence_id,
            belief_key=evidence.belief_key,
            claim_type=evidence.claim_type.value,
            content_hash=evidence.content_hash,
            record_hash=evidence.record_hash,
            status=evidence.status,
            admitted_by=evidence.admission.arbiter_id,
            claim_payload=dict(evidence.claim_payload),
        )
        self._belief._apply(_TOKEN, entry)
        # M3.4: retire the authorization. It admitted once; replaying it to
        # re-activate suspended or superseded evidence would let a stale
        # decision override a later scientific judgement.
        self._authorities.consume(
            evidence.admission, subject_record_hash=evidence.record_hash
        )
        return entry

    def update_standing(self, candidate: Any) -> BeliefEntry:
        """Re-record an already-known claim after its standing changed.

        Suspension, supersession and invalidation all flow through here, so a
        withdrawn claim stops influencing the active view without its history
        being deleted.

        **This path only ever lowers standing.** Restoring a withdrawn claim to
        active belief is a fresh scientific judgement — it needs a fresh
        assessment, a fresh Arbiter decision and a fresh authorization — so it
        must go through :meth:`submit`, where all three are checked. Allowing it
        here would mean any caller holding the record could re-activate
        evidence a reviewer had withdrawn, by supplying a sentence of prose.
        """
        evidence = self._require_evidence(candidate)
        known = self._belief.audit_log()
        if all(e.evidence_id != evidence.evidence_id for e in known):
            raise BeliefWriteViolation(
                f"evidence {evidence.evidence_id!r} was never admitted; "
                f"use submit() for new evidence"
            )
        # Record identity, not content identity: two records may legitimately
        # share a content hash, so only the record hash proves this is the
        # same piece of evidence.
        if evidence.record_hash not in {
            e.record_hash for e in known if e.evidence_id == evidence.evidence_id
        }:
            raise BeliefWriteViolation(
                f"evidence {evidence.evidence_id!r} changed content while in "
                f"belief; accepted evidence cannot be silently mutated"
            )

        # Standing may fall here; it may not rise. Reactivating withdrawn
        # evidence is a fresh scientific judgement and belongs to the
        # Critics -> Arbiter -> AdmissionAuthority -> submit() path.
        current = self._belief._entries.get(evidence.evidence_id)
        if (
            evidence.status is BELIEF_BEARING_STATUS
            and current is not None
            and current.status is not BELIEF_BEARING_STATUS
        ):
            raise AdmissionError(
                f"evidence {evidence.evidence_id!r} is recorded as "
                f"{current.status.value} and cannot be returned to "
                f"{BELIEF_BEARING_STATUS.value} through update_standing(). "
                f"Reinstating withdrawn evidence requires a fresh assessment, a "
                f"fresh Arbiter decision and a fresh admission authorization; "
                f"submit() is the only path that verifies all three."
            )

        entry = BeliefEntry(
            evidence_id=evidence.evidence_id,
            belief_key=evidence.belief_key,
            claim_type=evidence.claim_type.value,
            content_hash=evidence.content_hash,
            record_hash=evidence.record_hash,
            status=evidence.status,
            admitted_by=(
                evidence.admission.arbiter_id if evidence.admission else ""
            ),
            claim_payload=dict(evidence.claim_payload),
        )
        self._belief._apply(_TOKEN, entry)
        return entry
