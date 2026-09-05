"""SRIA provenance layers.

The Scientific Core already owns *run* provenance
(:class:`~engcore.scientific.results.provenance.ProvenanceRecord`) and it is
reused unchanged — re-implementing it would create two competing answers to
"where did this number come from".

SRIA adds the two layers above it, plus one reserved layer:

* :class:`EvidenceProvenance` — how a raw run became a claim;
* :class:`AssessmentProvenance` — who judged that claim, with which critic;
* :class:`DecisionProvenance` — **reserved**. The fields are defined now so
  that stored records stay forward-compatible, but no Strategist exists in M1
  and nothing constructs one during normal operation.

As in the core, nothing here harvests machine identity on its own: timestamps
and versions are supplied by the caller so that identical work produces
identical records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..scientific.serialization import require_schema, schema_string
from .errors import SRIAError

EVIDENCE_PROVENANCE_SCHEMA = schema_string("sria_evidence_provenance")
ASSESSMENT_PROVENANCE_SCHEMA = schema_string("sria_assessment_provenance")
DECISION_PROVENANCE_SCHEMA = schema_string("sria_decision_provenance")


@dataclass(frozen=True)
class EvidenceProvenance:
    """How a claim came to exist from an underlying run."""

    evidence_id: str
    run_provenance_ref: str          # ProvenanceRecord.run_id of the source run
    producer: str = ""               # component that extracted the claim
    producer_version: str = ""
    created_at: str | None = None
    source_refs: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for label in ("evidence_id", "run_provenance_ref"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise SRIAError(f"evidence provenance requires {label}")
            object.__setattr__(self, label, value)
        object.__setattr__(self, "source_refs", tuple(self.source_refs))
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": EVIDENCE_PROVENANCE_SCHEMA,
            "evidence_id": self.evidence_id,
            "run_provenance_ref": self.run_provenance_ref,
            "producer": self.producer,
            "producer_version": self.producer_version,
            "created_at": self.created_at,
            "source_refs": list(self.source_refs),
            "metadata": dict(sorted(self.metadata.items(), key=lambda kv: kv[0])),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidenceProvenance":
        require_schema(payload, EVIDENCE_PROVENANCE_SCHEMA)
        return cls(
            evidence_id=payload["evidence_id"],
            run_provenance_ref=payload["run_provenance_ref"],
            producer=payload.get("producer", ""),
            producer_version=payload.get("producer_version", ""),
            created_at=payload.get("created_at"),
            source_refs=tuple(payload.get("source_refs", ())),
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass(frozen=True)
class AssessmentProvenance:
    """Who assessed a claim, and with what."""

    assessment_id: str
    critic_id: str
    critic_version: str = ""
    inputs_ref: tuple[str, ...] = ()
    assessed_at: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for label in ("assessment_id", "critic_id"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise SRIAError(f"assessment provenance requires {label}")
            object.__setattr__(self, label, value)
        object.__setattr__(self, "inputs_ref", tuple(self.inputs_ref))
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ASSESSMENT_PROVENANCE_SCHEMA,
            "assessment_id": self.assessment_id,
            "critic_id": self.critic_id,
            "critic_version": self.critic_version,
            "inputs_ref": list(self.inputs_ref),
            "assessed_at": self.assessed_at,
            "metadata": dict(sorted(self.metadata.items(), key=lambda kv: kv[0])),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AssessmentProvenance":
        require_schema(payload, ASSESSMENT_PROVENANCE_SCHEMA)
        return cls(
            assessment_id=payload["assessment_id"],
            critic_id=payload["critic_id"],
            critic_version=payload.get("critic_version", ""),
            inputs_ref=tuple(payload.get("inputs_ref", ())),
            assessed_at=payload.get("assessed_at"),
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass(frozen=True)
class DecisionProvenance:
    """RESERVED for the Strategist — field layout only, no policy in M1.

    Defined now so that a decision journal written later can be replayed
    against records written today. M1 never produces one during normal
    operation; it exists to keep the format stable and to make the eventual
    "why did the system choose this?" question answerable by construction.
    """

    decision_id: str
    belief_snapshot_ref: str = ""
    candidate_actions: tuple[str, ...] = ()
    scores: Mapping[str, float] = field(default_factory=dict)
    chosen_action: str = ""
    reason: str = ""
    policy_id: str = ""
    policy_version: str = ""
    human_override: bool = False
    decided_at: str | None = None

    def __post_init__(self) -> None:
        decision_id = str(self.decision_id).strip()
        if not decision_id:
            raise SRIAError("decision provenance requires a decision_id")
        object.__setattr__(self, "decision_id", decision_id)
        object.__setattr__(self, "candidate_actions", tuple(self.candidate_actions))
        object.__setattr__(
            self, "scores", {str(k): float(v) for k, v in self.scores.items()}
        )
        if not isinstance(self.human_override, bool):
            raise SRIAError("human_override must be an explicit bool")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": DECISION_PROVENANCE_SCHEMA,
            "decision_id": self.decision_id,
            "belief_snapshot_ref": self.belief_snapshot_ref,
            "candidate_actions": list(self.candidate_actions),
            "scores": dict(sorted(self.scores.items())),
            "chosen_action": self.chosen_action,
            "reason": self.reason,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "human_override": self.human_override,
            "decided_at": self.decided_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DecisionProvenance":
        require_schema(payload, DECISION_PROVENANCE_SCHEMA)
        return cls(
            decision_id=payload["decision_id"],
            belief_snapshot_ref=payload.get("belief_snapshot_ref", ""),
            candidate_actions=tuple(payload.get("candidate_actions", ())),
            scores=dict(payload.get("scores", {})),
            chosen_action=payload.get("chosen_action", ""),
            reason=payload.get("reason", ""),
            policy_id=payload.get("policy_id", ""),
            policy_version=payload.get("policy_version", ""),
            human_override=bool(payload.get("human_override", False)),
            decided_at=payload.get("decided_at"),
        )
