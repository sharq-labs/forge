"""M2A — the one canonical bridge from legacy outcomes into SRIA.

The repository carries two failure vocabularies: the Scientific Core's flat
:class:`~engcore.scientific.experiments.evaluation.EvaluationStatus` and SRIA's
orthogonal :class:`~engcore.sria.outcomes.RunOutcome`. M1 deliberately did not
migrate the former, and recorded a standing rule: no learned failure model may
exist while both feed the same learner.

This module discharges that rule. It is the *only* sanctioned conversion, and
after it there is exactly one representation entering learning code.

The hard part is not the mapping — it is refusing to invent.

Legacy ``FAILED`` is a single token covering numerical divergence, a lost
node, a timeout, and a malformed input. Those have opposite meanings for a
failure model: a solver that diverges on stiff problems is signal, a machine
that lost power is noise that would bias every prediction it touched. Nothing
in the legacy record distinguishes them. So a bare ``FAILED`` maps to
:attr:`~engcore.sria.outcomes.AttributedCause.UNATTRIBUTED` and is marked
**ineligible** for supervised failure learning.

It can be *upgraded*, but only by explicit declared provenance evidence — a
recorded ``failure_kind``, never a guess, never a regex over a log message.
Evidence that is absent stays absent.

The alternative — assigning a plausible cause to old rows so the dataset looks
complete — produces a model that is confidently wrong in exactly the cases
that matter, and no downstream diagnostic can recover the damage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from ...scientific.experiments.evaluation import EvaluationStatus
from ...scientific.serialization import require_schema, schema_string
from ..outcomes import (
    AttributedCause,
    BlameAssignment,
    CensoringType,
    DetectedBy,
    Disposition,
    Retryability,
    RunOutcome,
)

BRIDGED_OUTCOME_SCHEMA = schema_string("sria_bridged_outcome")


class MappingConfidence(str, Enum):
    """How much the legacy token actually determined the mapping."""

    EXACT = "exact"        # legacy semantics fully determine the mapping
    PARTIAL = "partial"    # disposition certain, cause inferred from documented semantics
    AMBIGUOUS = "ambiguous"  # legacy token underdetermines the cause


#: Closed vocabulary of provenance evidence that may upgrade a bare FAILED.
#: Only these exact declared values are honoured — no free-text inference.
FAILURE_KIND_EVIDENCE: Mapping[str, tuple[AttributedCause, bool, BlameAssignment]] = {
    "numerical": (AttributedCause.NUMERICAL, True, BlameAssignment.SOLVER),
    "solver": (AttributedCause.NUMERICAL, True, BlameAssignment.SOLVER),
    "scientific": (AttributedCause.SCIENTIFIC, True, BlameAssignment.MODEL),
    "scope": (AttributedCause.SCIENTIFIC, True, BlameAssignment.MODEL),
    "infeasible": (AttributedCause.INFEASIBLE, True, BlameAssignment.PARAMETERS),
    "infrastructure": (AttributedCause.INFRASTRUCTURE, False, BlameAssignment.PLATFORM),
    "timeout": (AttributedCause.INFRASTRUCTURE, False, BlameAssignment.PLATFORM),
}

#: Declared censoring evidence, again closed.
CENSORING_EVIDENCE: Mapping[str, CensoringType] = {
    "budget": CensoringType.RIGHT_CENSORED_BUDGET,
    "wallclock": CensoringType.RIGHT_CENSORED_WALLCLOCK,
    "timeout": CensoringType.RIGHT_CENSORED_WALLCLOCK,
    "manual": CensoringType.RIGHT_CENSORED_MANUAL,
}


@dataclass(frozen=True)
class BridgedOutcome:
    """A legacy outcome converted, with its conversion quality attached.

    ``pf_eligible`` is the gate every failure learner must respect. It is
    carried here rather than recomputed downstream so that one decision, made
    where the ambiguity is visible, governs every consumer.
    """

    outcome: RunOutcome
    mapping_confidence: MappingConfidence
    pf_eligible: bool
    legacy_status: str
    notes: str = ""
    evidence_used: tuple[str, ...] = ()

    @property
    def eligible_for_computational_failure_learning(self) -> bool:
        """Solver-reliability eligibility, narrower than ``pf_eligible``.

        ``INVALID`` legacy rows are feasibility evidence: the design point was
        rejected, but nothing says the numerics misbehaved. They carry signal —
        just not about solver reliability.
        """
        if not self.pf_eligible:
            return False
        return self.outcome.attributed_cause not in (
            AttributedCause.INFEASIBLE,
            AttributedCause.INFRASTRUCTURE,
            AttributedCause.UNATTRIBUTED,
        )

    @property
    def eligible_for_feasibility_learning(self) -> bool:
        """Feasibility-model eligibility. Not implemented in M2; declared here
        so infeasible rows have an honest destination."""
        if not self.pf_eligible:
            return False
        if self.outcome.attributed_cause is AttributedCause.INFEASIBLE:
            return True
        return self.outcome.disposition is Disposition.SUCCESS

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "mapping_confidence", MappingConfidence(self.mapping_confidence)
        )
        if not isinstance(self.outcome, RunOutcome):
            raise TypeError("BridgedOutcome requires a RunOutcome")
        if not isinstance(self.pf_eligible, bool):
            raise TypeError("pf_eligible must be an explicit bool")
        object.__setattr__(self, "evidence_used", tuple(self.evidence_used))

        # The invariant that keeps ambiguity out of training data.
        if (
            self.outcome.attributed_cause is AttributedCause.UNATTRIBUTED
            and self.pf_eligible
        ):
            raise ValueError(
                "an UNATTRIBUTED outcome can never be eligible for supervised "
                "failure learning; its cause is unknown by construction"
            )
        if self.outcome.informative_for_pf != self.pf_eligible:
            raise ValueError(
                "pf_eligible must agree with the outcome's informative_for_pf; "
                "two disagreeing eligibility flags is how bad rows leak in"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": BRIDGED_OUTCOME_SCHEMA,
            "outcome": self.outcome.to_dict(),
            "mapping_confidence": self.mapping_confidence.value,
            "pf_eligible": self.pf_eligible,
            "legacy_status": self.legacy_status,
            "notes": self.notes,
            "evidence_used": list(self.evidence_used),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BridgedOutcome":
        require_schema(payload, BRIDGED_OUTCOME_SCHEMA)
        return cls(
            outcome=RunOutcome.from_dict(payload["outcome"]),
            mapping_confidence=MappingConfidence(payload["mapping_confidence"]),
            pf_eligible=bool(payload["pf_eligible"]),
            legacy_status=payload["legacy_status"],
            notes=payload.get("notes", ""),
            evidence_used=tuple(payload.get("evidence_used", ())),
        )


#: The registered mapping table. Rendered in the M2 report verbatim.
#: (disposition, cause, informative_for_pf, censoring, confidence, note)
LEGACY_MAPPING_TABLE: Mapping[EvaluationStatus, dict[str, Any]] = {
    EvaluationStatus.OK: {
        "disposition": Disposition.SUCCESS,
        "cause": AttributedCause.NONE,
        "pf_eligible": True,
        "censoring": CensoringType.NONE,
        "confidence": MappingConfidence.EXACT,
        "completion_fraction": 1.0,
        "note": "legacy OK means completed with usable values; unambiguous",
    },
    EvaluationStatus.NOT_CONVERGED: {
        "disposition": Disposition.PARTIAL,
        "cause": AttributedCause.NUMERICAL,
        "pf_eligible": True,
        "censoring": CensoringType.NONE,
        "confidence": MappingConfidence.PARTIAL,
        "completion_fraction": 1.0,
        "note": (
            "legacy semantics are 'completed, values present but untrusted' — "
            "the run finished, so it is not censored; NUMERICAL is the only "
            "cause the documented meaning supports"
        ),
    },
    EvaluationStatus.INVALID: {
        "disposition": Disposition.FAILED,
        "cause": AttributedCause.INFEASIBLE,
        "pf_eligible": True,
        "censoring": CensoringType.NONE,
        "confidence": MappingConfidence.PARTIAL,
        "note": (
            "legacy docstring defines INVALID as a scientifically invalid "
            "candidate/point, i.e. an infeasible input rather than a "
            "computational fault. Informative for FEASIBILITY learning only — "
            "it is NOT evidence that the solver is unreliable, and M2.1 routes "
            "it away from the computational-failure target"
        ),
        "completion_fraction": 0.0,
    },
    EvaluationStatus.FAILED: {
        "disposition": Disposition.FAILED,
        "cause": AttributedCause.UNATTRIBUTED,
        "pf_eligible": False,
        "censoring": CensoringType.NONE,
        "confidence": MappingConfidence.AMBIGUOUS,
        "completion_fraction": 0.0,
        "note": (
            "legacy FAILED conflates numerical divergence, infrastructure "
            "loss, timeout and malformed input. Not separable from the record "
            "alone; INELIGIBLE for supervised failure learning unless declared "
            "provenance evidence upgrades it"
        ),
    },
    EvaluationStatus.NOT_RUN: {
        "disposition": Disposition.INDETERMINATE,
        "cause": AttributedCause.NONE,
        "pf_eligible": False,
        "censoring": CensoringType.NONE,
        "confidence": MappingConfidence.EXACT,
        "completion_fraction": 0.0,
        "note": (
            "proposed but never executed: carries no information about "
            "computational behaviour at all"
        ),
    },
}


def bridge_evaluation_status(
    status: EvaluationStatus | str,
    *,
    evidence: Mapping[str, Any] | None = None,
    detail: str = "",
    detected_by: DetectedBy = DetectedBy.UNKNOWN,
) -> BridgedOutcome:
    """Convert one legacy status into the canonical representation.

    ``evidence`` may carry ``failure_kind`` and ``censoring`` keys drawn from
    the closed vocabularies above. Anything else is ignored rather than
    interpreted — an unrecognised value must not become a silent
    classification.
    """
    status = EvaluationStatus(status)
    row = LEGACY_MAPPING_TABLE[status]
    evidence = dict(evidence or {})
    used: list[str] = []

    cause = row["cause"]
    pf_eligible = row["pf_eligible"]
    confidence = row["confidence"]
    censoring = row["censoring"]
    blame = BlameAssignment.UNASSIGNED
    notes = row["note"]

    # Upgrade path: only an explicitly declared, recognised kind may resolve
    # the ambiguity. Absent or unrecognised evidence leaves it unresolved.
    declared_kind = str(evidence.get("failure_kind", "")).strip().lower()
    if cause is AttributedCause.UNATTRIBUTED and declared_kind:
        if declared_kind in FAILURE_KIND_EVIDENCE:
            cause, pf_eligible, blame = FAILURE_KIND_EVIDENCE[declared_kind]
            confidence = MappingConfidence.PARTIAL
            used.append(f"failure_kind={declared_kind}")
            notes = (
                f"legacy FAILED resolved to {cause.value} by declared "
                f"provenance evidence"
            )
        else:
            notes = (
                f"{notes}; unrecognised failure_kind {declared_kind!r} ignored "
                f"rather than interpreted"
            )

    declared_censoring = str(evidence.get("censoring", "")).strip().lower()
    if declared_censoring:
        if declared_censoring in CENSORING_EVIDENCE:
            censoring = CENSORING_EVIDENCE[declared_censoring]
            used.append(f"censoring={declared_censoring}")
            if status is EvaluationStatus.FAILED:
                # A censored run is not an observed failure.
                return BridgedOutcome(
                    outcome=RunOutcome(
                        disposition=Disposition.KILLED_CENSORED,
                        attributed_cause=cause,
                        blame_assignment=blame,
                        censoring_type=censoring,
                        completion_fraction=float(
                            evidence.get("completion_fraction", 0.0)
                        ),
                        retryability=Retryability.UNKNOWN,
                        informative_for_pf=False,
                        detected_by=detected_by,
                        detail=detail,
                    ),
                    mapping_confidence=confidence,
                    pf_eligible=False,
                    legacy_status=status.value,
                    notes=(
                        "censored run: truncation is not an observed failure "
                        "and must not train a failure model as one"
                    ),
                    evidence_used=tuple(used),
                )

    outcome = RunOutcome(
        disposition=row["disposition"],
        attributed_cause=cause,
        blame_assignment=blame,
        censoring_type=censoring,
        completion_fraction=float(
            evidence.get("completion_fraction", row["completion_fraction"])
        ),
        retryability=Retryability.UNKNOWN,
        informative_for_pf=pf_eligible,
        detected_by=detected_by,
        detail=detail,
    )
    return BridgedOutcome(
        outcome=outcome,
        mapping_confidence=confidence,
        pf_eligible=pf_eligible,
        legacy_status=status.value,
        notes=notes,
        evidence_used=tuple(used),
    )


def bridge_evaluation(evaluation: Any, **kwargs: Any) -> BridgedOutcome:
    """Bridge a ``ScientificEvaluation`` without importing its status enum
    anywhere downstream."""
    return bridge_evaluation_status(evaluation.status, **kwargs)


def mapping_table_rows() -> tuple[dict[str, Any], ...]:
    """The audit table, for reports and tests."""
    rows = []
    for status in LEGACY_MAPPING_TABLE:
        row = LEGACY_MAPPING_TABLE[status]
        bridged = bridge_evaluation_status(status)
        rows.append(
            {
                "legacy_status": status.value,
                "disposition": row["disposition"].value,
                "attributed_cause": row["cause"].value,
                "informative_for_pf": row["pf_eligible"],
                "computational_failure_eligible": (
                    bridged.eligible_for_computational_failure_learning
                ),
                "feasibility_eligible": bridged.eligible_for_feasibility_learning,
                "censoring": row["censoring"].value,
                "confidence": row["confidence"].value,
                "note": row["note"],
            }
        )
    return tuple(rows)
