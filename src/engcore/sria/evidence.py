"""Source-agnostic evidence envelope and its lifecycle.

The envelope exists so that a simulation result, a datasheet value, a
laboratory measurement and a published benchmark can travel through the same
pipeline without the pipeline pretending they are equally trustworthy. What
they share is *structure*, not authority.

Two rules shape this module.

**Storage is not acceptance.** An ``Evidence`` object existing — in memory, in
a file, in a database — must never mean it affects scientific belief. Belief is
reached only by passing admission and going through the Belief Update Gateway.
The lifecycle status is what separates the two, and it is carried on the
envelope rather than in a side table so it cannot drift.

**The core does not own scientific meaning.** ``claim_payload`` is opaque here:
validated as serializable, never interpreted. A universal ontology of
scientific claims would be wrong within a week and would put every domain in
the business of arguing with the core. Meaning belongs to Domain Packs.

Two identities, deliberately separate:

* ``content_hash`` — **Scientific Content Identity**. What is claimed: claim
  type, binding, payload, uncertainty, domain pack, context. Two records that
  make the same claim share this hash, and that is correct: it is what lets
  the platform recognise corroboration and conflict.
* ``record_hash`` — **Evidence Record Identity**. Which record this is:
  content plus ``evidence_id``, ``source_class`` and ``provenance_ref``. A
  simulation and a measurement asserting the identical value are *two* pieces
  of evidence, and collapsing them would silently double-count one source or
  discard the other.

Nothing treats ``content_hash`` as provenance. Belief entries key on
``evidence_id`` and verify ``record_hash``; admission declarations bind to
``record_hash`` so an admission granted to one record cannot be replayed onto
another that happens to claim the same thing.

Lifecycle events, assessments and admission attempts sit outside both hashes,
so a claim keeps a stable identity while its standing changes. Altering the
content makes the hash stop matching, and the tampering surfaces on reload.

Admission is procedural, not epistemic. A refused, unsigned, unattributable or
mis-bound admission leaves scientific standing untouched and is recorded as an
:class:`~engcore.sria.admission.AdmissionAttempt`. ``INVALID`` is reserved for
an explicit scientific judgement that the claim itself is wrong.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Mapping

from ..scientific.serialization import encode, require_schema, schema_string
from .admission import (
    AdmissionAttempt,
    AdmissionDeclaration,
    AdmissionOutcome,
)
from .errors import AdmissionError, EvidenceError, LifecycleViolation, ReservedNotImplemented
from .provenance import AssessmentProvenance
from .uncertainty import UncertaintyDeclaration

EVIDENCE_SCHEMA = schema_string("sria_evidence", 2)
ASSESSMENT_SCHEMA = schema_string("sria_assessment")
LIFECYCLE_EVENT_SCHEMA = schema_string("sria_lifecycle_event")
CLAIM_BINDING_SCHEMA = schema_string("sria_claim_binding")


class SourceClass(str, Enum):
    """Where evidence came from.

    Only ``SIMULATION`` has an ingestion path in V0.1. The others are reserved
    so that the storage format, the lifecycle and the gateway do not change
    when they arrive.
    """

    SIMULATION = "simulation"
    MEASUREMENT = "measurement"    # reserved
    LITERATURE = "literature"      # reserved
    BENCHMARK = "benchmark"        # reserved


IMPLEMENTED_SOURCE_CLASSES = frozenset({SourceClass.SIMULATION})


class ClaimType(str, Enum):
    """Closed set of claim shapes the platform can route.

    Closed on purpose: routing, admission and belief keying all switch on it.
    Adding a member is a deliberate contract change.
    """

    PARAMETER_VALUE = "parameter_value"
    QOI_VALUE = "qoi_value"
    MODEL_SUPPORT_OR_CONTRADICTION = "model_support_or_contradiction"
    SCOPE_BOUNDARY = "scope_boundary"
    CALIBRATION_REFERENCE = "calibration_reference"


class EvidenceStatus(str, Enum):
    CANDIDATE = "candidate"
    UNBOUND = "unbound"
    ASSESSED = "assessed"
    ACCEPTED = "accepted"
    SUSPENDED = "suspended"
    INVALID = "invalid"
    SUPERSEDED = "superseded"


#: Legal lifecycle moves. Anything absent here is refused, so an implementation
#: cannot quietly promote candidate evidence straight into belief.
ALLOWED_TRANSITIONS: Mapping[EvidenceStatus, frozenset[EvidenceStatus]] = {
    EvidenceStatus.CANDIDATE: frozenset(
        {EvidenceStatus.UNBOUND, EvidenceStatus.ASSESSED, EvidenceStatus.INVALID}
    ),
    EvidenceStatus.UNBOUND: frozenset(
        {EvidenceStatus.ASSESSED, EvidenceStatus.INVALID}
    ),
    EvidenceStatus.ASSESSED: frozenset(
        {EvidenceStatus.ACCEPTED, EvidenceStatus.INVALID}
    ),
    EvidenceStatus.ACCEPTED: frozenset(
        {
            EvidenceStatus.SUSPENDED,
            EvidenceStatus.SUPERSEDED,
            EvidenceStatus.INVALID,
        }
    ),
    EvidenceStatus.SUSPENDED: frozenset(
        {
            EvidenceStatus.ACCEPTED,
            EvidenceStatus.SUPERSEDED,
            EvidenceStatus.INVALID,
        }
    ),
    EvidenceStatus.INVALID: frozenset(),
    EvidenceStatus.SUPERSEDED: frozenset(),
}

#: The only status whose evidence may reach belief through the Gateway.
BELIEF_BEARING_STATUS = EvidenceStatus.ACCEPTED


class AssessmentVerdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class ClaimBinding:
    """What the claim is *about*.

    ``subject_kind`` and ``subject_ref`` are strings the owning Domain Pack
    interprets. The core uses them only for keying and equality.
    """

    subject_kind: str
    subject_ref: str
    qualifiers: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for label in ("subject_kind", "subject_ref"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise EvidenceError(f"claim binding requires {label}")
            object.__setattr__(self, label, value)
        object.__setattr__(
            self,
            "qualifiers",
            {str(k): str(v) for k, v in self.qualifiers.items()},
        )

    @property
    def key(self) -> str:
        """Stable belief key for this subject."""
        extra = "".join(
            f";{k}={self.qualifiers[k]}" for k in sorted(self.qualifiers)
        )
        return f"{self.subject_kind}:{self.subject_ref}{extra}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CLAIM_BINDING_SCHEMA,
            "subject_kind": self.subject_kind,
            "subject_ref": self.subject_ref,
            "qualifiers": dict(sorted(self.qualifiers.items())),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ClaimBinding":
        require_schema(payload, CLAIM_BINDING_SCHEMA)
        return cls(
            subject_kind=payload["subject_kind"],
            subject_ref=payload["subject_ref"],
            qualifiers=payload.get("qualifiers", {}),
        )


@dataclass(frozen=True)
class Assessment:
    """One critic's judgement of one piece of evidence."""

    verdict: AssessmentVerdict
    provenance: AssessmentProvenance
    rationale: str = ""
    score: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "verdict", AssessmentVerdict(self.verdict))
        if not isinstance(self.provenance, AssessmentProvenance):
            raise EvidenceError(
                "assessment requires AssessmentProvenance: an unattributed "
                "judgement cannot be audited"
            )
        if self.score is not None:
            object.__setattr__(self, "score", float(self.score))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ASSESSMENT_SCHEMA,
            "verdict": self.verdict.value,
            "provenance": self.provenance.to_dict(),
            "rationale": self.rationale,
            "score": self.score,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Assessment":
        require_schema(payload, ASSESSMENT_SCHEMA)
        return cls(
            verdict=AssessmentVerdict(payload["verdict"]),
            provenance=AssessmentProvenance.from_dict(payload["provenance"]),
            rationale=payload.get("rationale", ""),
            score=payload.get("score"),
        )


@dataclass(frozen=True)
class LifecycleEvent:
    """One append-only entry in an evidence audit trail."""

    status: EvidenceStatus
    reason: str = ""
    actor: str = ""
    at: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", EvidenceStatus(self.status))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": LIFECYCLE_EVENT_SCHEMA,
            "status": self.status.value,
            "reason": self.reason,
            "actor": self.actor,
            "at": self.at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LifecycleEvent":
        require_schema(payload, LIFECYCLE_EVENT_SCHEMA)
        return cls(
            status=EvidenceStatus(payload["status"]),
            reason=payload.get("reason", ""),
            actor=payload.get("actor", ""),
            at=payload.get("at"),
        )


@dataclass(frozen=True)
class Evidence:
    """A source-agnostic scientific claim with its standing attached."""

    evidence_id: str
    source_class: SourceClass
    claim_type: ClaimType
    claim_binding: ClaimBinding
    claim_payload: Mapping[str, Any]
    uncertainty: UncertaintyDeclaration
    provenance_ref: str
    domain_pack_ref: str
    context_ref: str = ""
    content_hash: str = ""
    status: EvidenceStatus = EvidenceStatus.CANDIDATE
    assessments: tuple[Assessment, ...] = ()
    admission: AdmissionDeclaration | None = None
    admission_attempts: tuple[AdmissionAttempt, ...] = ()
    lifecycle_log: tuple[LifecycleEvent, ...] = ()
    supersedes: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for label in ("evidence_id", "provenance_ref", "domain_pack_ref"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise EvidenceError(f"evidence requires a non-empty {label}")
            object.__setattr__(self, label, value)

        object.__setattr__(self, "source_class", SourceClass(self.source_class))
        object.__setattr__(self, "claim_type", ClaimType(self.claim_type))
        object.__setattr__(self, "status", EvidenceStatus(self.status))

        if not isinstance(self.claim_binding, ClaimBinding):
            raise EvidenceError("evidence requires a ClaimBinding")
        if not isinstance(self.uncertainty, UncertaintyDeclaration):
            raise EvidenceError(
                "evidence requires an UncertaintyDeclaration: a claim without "
                "a declared uncertainty channel is not admissible evidence"
            )

        try:
            payload = encode(dict(self.claim_payload))
        except Exception as exc:
            raise EvidenceError(
                f"claim_payload must be serializable: {exc}"
            ) from exc
        object.__setattr__(self, "claim_payload", payload)

        object.__setattr__(self, "assessments", tuple(self.assessments))
        object.__setattr__(
            self, "admission_attempts", tuple(self.admission_attempts)
        )
        object.__setattr__(self, "lifecycle_log", tuple(self.lifecycle_log))
        object.__setattr__(self, "metadata", dict(self.metadata))

        computed = self._compute_content_hash()
        declared = str(self.content_hash).strip()
        if not declared:
            object.__setattr__(self, "content_hash", computed)
        elif declared != computed:
            raise EvidenceError(
                f"evidence {self.evidence_id!r} content_hash does not match its "
                f"content; the claim was altered after it was recorded"
            )

        if not self.lifecycle_log:
            object.__setattr__(
                self,
                "lifecycle_log",
                (LifecycleEvent(status=self.status, reason="created"),),
            )

    # ---- identity -------------------------------------------------------
    def _scientific_content(self) -> dict[str, Any]:
        """What is claimed. Excludes which record claimed it, and standing.

        Two records asserting the same thing from different sources share this
        — that is what makes corroboration and conflict recognisable.
        """
        return {
            "claim_type": self.claim_type.value,
            "claim_binding": self.claim_binding.to_dict(),
            "claim_payload": self.claim_payload,
            "uncertainty": self.uncertainty.to_dict(),
            "domain_pack_ref": self.domain_pack_ref,
            "context_ref": self.context_ref,
        }

    def _content(self) -> dict[str, Any]:
        """Serialization view: scientific content plus record identity."""
        payload = self._scientific_content()
        payload.update(
            {
                "evidence_id": self.evidence_id,
                "source_class": self.source_class.value,
                "provenance_ref": self.provenance_ref,
            }
        )
        return payload

    def _compute_content_hash(self) -> str:
        blob = json.dumps(
            self._scientific_content(), sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    @property
    def record_hash(self) -> str:
        """Evidence Record Identity — never interchangeable with content_hash.

        Distinguishes two records that make the identical claim but come from
        different sources or runs.
        """
        blob = json.dumps(
            {
                "evidence_id": self.evidence_id,
                "source_class": self.source_class.value,
                "provenance_ref": self.provenance_ref,
                "content_hash": self.content_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    @property
    def belief_key(self) -> str:
        return f"{self.claim_type.value}|{self.claim_binding.key}"

    @property
    def is_belief_bearing(self) -> bool:
        """Whether this evidence may currently contribute to belief."""
        return self.status is BELIEF_BEARING_STATUS

    # ---- lifecycle (append-only) ----------------------------------------
    def _transition(
        self,
        new_status: EvidenceStatus,
        *,
        reason: str,
        actor: str = "",
        at: str | None = None,
        **changes: Any,
    ) -> "Evidence":
        allowed = ALLOWED_TRANSITIONS[self.status]
        if new_status not in allowed:
            raise LifecycleViolation(
                f"evidence {self.evidence_id!r} cannot move "
                f"{self.status.value} -> {new_status.value}; allowed: "
                f"{sorted(s.value for s in allowed) or 'none (terminal)'}"
            )
        event = LifecycleEvent(
            status=new_status, reason=reason, actor=actor, at=at
        )
        return replace(
            self,
            status=new_status,
            lifecycle_log=self.lifecycle_log + (event,),
            **changes,
        )

    def with_assessment(
        self,
        assessment: Assessment,
        *,
        reason: str = "assessed",
        actor: str = "",
        at: str | None = None,
    ) -> "Evidence":
        """Append a critic assessment, moving to ASSESSED the first time."""
        if not isinstance(assessment, Assessment):
            raise EvidenceError("with_assessment requires an Assessment")
        assessments = self.assessments + (assessment,)
        if self.status is EvidenceStatus.ASSESSED:
            return replace(self, assessments=assessments)
        return self._transition(
            EvidenceStatus.ASSESSED,
            reason=reason,
            actor=actor,
            at=at,
            assessments=assessments,
        )

    def mark_unbound(self, reason: str, *, actor: str = "", at: str | None = None) -> "Evidence":
        return self._transition(
            EvidenceStatus.UNBOUND, reason=reason, actor=actor, at=at
        )

    def record_admission_attempt(self, attempt: AdmissionAttempt) -> "Evidence":
        """Append an admission attempt without touching scientific standing.

        Used for refusals and for gateway-side rejections. Failing to get
        admitted is a procedural fact about the admission process; it is not a
        finding that the claim is wrong.
        """
        if not isinstance(attempt, AdmissionAttempt):
            raise AdmissionError(
                "record_admission_attempt requires an AdmissionAttempt"
            )
        return replace(self, admission_attempts=self.admission_attempts + (attempt,))

    def admit(
        self,
        declaration: AdmissionDeclaration,
        *,
        actor: str = "",
        at: str | None = None,
    ) -> "Evidence":
        """Apply an Arbiter admission.

        An admitting declaration moves the evidence to ACCEPTED. A declining
        one records the attempt and **leaves the status unchanged** — it does
        not mark the evidence INVALID, because "no authority admitted this"
        and "this claim is scientifically wrong" are different statements. Use
        :meth:`invalidate` for the latter, which is an epistemic decision made
        by a scientific authority.
        """
        if not isinstance(declaration, AdmissionDeclaration):
            raise AdmissionError("admit requires an AdmissionDeclaration")
        if declaration.subject_record_hash and (
            declaration.subject_record_hash != self.record_hash
        ):
            raise AdmissionError(
                f"admission declaration was issued for a different evidence "
                f"record; it cannot be applied to {self.evidence_id!r}"
            )

        if not declaration.admitted:
            return self.record_admission_attempt(
                AdmissionAttempt(
                    outcome=AdmissionOutcome.REFUSED,
                    reason=declaration.rationale or "admission declined",
                    arbiter_id=declaration.arbiter_id,
                    issuer_id=declaration.issuer_id,
                    subject_record_hash=declaration.subject_record_hash,
                    at=at or declaration.decided_at,
                )
            )

        admitted_attempt = AdmissionAttempt(
            outcome=AdmissionOutcome.ADMITTED,
            reason=declaration.rationale or "admitted",
            arbiter_id=declaration.arbiter_id,
            issuer_id=declaration.issuer_id,
            subject_record_hash=declaration.subject_record_hash,
            at=at or declaration.decided_at,
        )
        return self._transition(
            EvidenceStatus.ACCEPTED,
            reason=declaration.rationale or "admitted",
            actor=actor or declaration.arbiter_id,
            at=at,
            admission=declaration,
            admission_attempts=self.admission_attempts + (admitted_attempt,),
        )

    def suspend(self, reason: str, *, actor: str = "", at: str | None = None) -> "Evidence":
        return self._transition(
            EvidenceStatus.SUSPENDED, reason=reason, actor=actor, at=at
        )

    def reinstate(self, reason: str, *, actor: str = "", at: str | None = None) -> "Evidence":
        return self._transition(
            EvidenceStatus.ACCEPTED, reason=reason, actor=actor, at=at
        )

    def invalidate(self, reason: str, *, actor: str = "", at: str | None = None) -> "Evidence":
        """Epistemic invalidation: the claim itself is judged wrong.

        Reserved for an explicit scientific decision — a refuted measurement, a
        model applied outside its validity domain, a discovered extraction bug.
        Never reached as a side effect of an admission failure.
        """
        if not str(reason).strip():
            raise LifecycleViolation(
                "invalidating evidence requires a scientific reason; INVALID is "
                "an epistemic verdict, not a procedural outcome"
            )
        return self._transition(
            EvidenceStatus.INVALID, reason=reason, actor=actor, at=at
        )

    def supersede(
        self, by_evidence_id: str, reason: str = "", *, actor: str = "", at: str | None = None
    ) -> "Evidence":
        successor = str(by_evidence_id).strip()
        if not successor:
            raise LifecycleViolation("supersede requires the successor evidence id")
        return self._transition(
            EvidenceStatus.SUPERSEDED,
            reason=reason or f"superseded by {successor}",
            actor=actor,
            at=at,
            supersedes=successor,
        )

    # ---- serialization --------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        payload = self._content()
        payload.update(
            {
                "schema": EVIDENCE_SCHEMA,
                "content_hash": self.content_hash,
                "record_hash": self.record_hash,
                "status": self.status.value,
                "assessments": [a.to_dict() for a in self.assessments],
                "admission": self.admission.to_dict() if self.admission else None,
                "admission_attempts": [
                    a.to_dict() for a in self.admission_attempts
                ],
                "lifecycle_log": [e.to_dict() for e in self.lifecycle_log],
                "supersedes": self.supersedes,
                "metadata": dict(
                    sorted(self.metadata.items(), key=lambda kv: kv[0])
                ),
            }
        )
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Evidence":
        require_schema(payload, EVIDENCE_SCHEMA)
        admission = payload.get("admission")
        return cls(
            evidence_id=payload["evidence_id"],
            source_class=SourceClass(payload["source_class"]),
            claim_type=ClaimType(payload["claim_type"]),
            claim_binding=ClaimBinding.from_dict(payload["claim_binding"]),
            claim_payload=payload.get("claim_payload", {}),
            uncertainty=UncertaintyDeclaration.from_dict(payload["uncertainty"]),
            provenance_ref=payload["provenance_ref"],
            domain_pack_ref=payload["domain_pack_ref"],
            context_ref=payload.get("context_ref", ""),
            content_hash=payload.get("content_hash", ""),
            status=EvidenceStatus(payload.get("status", "candidate")),
            assessments=tuple(
                Assessment.from_dict(a) for a in payload.get("assessments", ())
            ),
            admission=(
                AdmissionDeclaration.from_dict(admission) if admission else None
            ),
            admission_attempts=tuple(
                AdmissionAttempt.from_dict(a)
                for a in payload.get("admission_attempts", ())
            ),
            lifecycle_log=tuple(
                LifecycleEvent.from_dict(e) for e in payload.get("lifecycle_log", ())
            ),
            supersedes=payload.get("supersedes", ""),
            metadata=dict(payload.get("metadata", {})),
        )


def require_implemented_source(source_class: SourceClass) -> None:
    """Guard for ingestion paths that must actually exist.

    Representing reserved source classes is fine and intended — an archive
    written today must round-trip a LITERATURE claim tomorrow. *Ingesting* one
    is not implemented in V0.1.
    """
    source_class = SourceClass(source_class)
    if source_class not in IMPLEMENTED_SOURCE_CLASSES:
        raise ReservedNotImplemented(
            f"source class {source_class.value!r} is reserved in SRIA V0.1; "
            f"implemented ingestion: "
            f"{sorted(s.value for s in IMPLEMENTED_SOURCE_CLASSES)}"
        )
