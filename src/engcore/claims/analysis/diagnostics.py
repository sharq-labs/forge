"""Derived scientific diagnostics for an assessed claim.

This module does not decide a claim and does not create evidence. It explains
recorded blockers, inventories explicit assumptions, summarizes admissible
model-data comparisons, and turns the existing next-experiment plan into
corrective actions.

The distinction is deliberate:

* a *blocking cause* is directly supported by the assessment record;
* a *repair hypothesis* is a candidate explanation worth testing;
* a *corrective action* may close a named gap, but never guarantees support.

Nothing here mutates the assessment or strengthens its verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

from .._records import tagged_digest
from ..gaps import EvidenceGap, EvidenceGapAnalysis, GapClass, analyze_gaps
from ..next_experiment import ExperimentRecommendation, NextExperimentPlan, recommend_next
from .impact import record_digest

_TAG = "crafty.claims.scientific_diagnostic/1"


class DiagnosticClass(str, Enum):
    CLAIM_DEFINITION = "claim_definition"
    CAPABILITY = "capability"
    EXECUTION = "execution"
    CONTEXT = "context"
    EVIDENCE_ASSEMBLY = "evidence_assembly"
    APPLICABILITY = "applicability"
    VERIFICATION = "verification"
    VALIDATION = "validation"
    NUMERICAL_UNCERTAINTY = "numerical_uncertainty"
    PARAMETER_UNCERTAINTY = "parameter_uncertainty"
    MEASUREMENT_UNCERTAINTY = "measurement_uncertainty"
    MODEL_FORM = "model_form"
    DECISION_MARGIN = "decision_margin"
    EXTERNAL_EVIDENCE = "external_evidence"
    INDEPENDENCE = "independence"
    ASSURANCE = "assurance"
    PROVENANCE = "provenance"
    MODEL_DATA_MISMATCH = "model_data_mismatch"
    UNEXPLAINED = "unexplained"


_GAP_CAUSE = {
    GapClass.MISSING_INPUT: DiagnosticClass.CLAIM_DEFINITION,
    GapClass.INPUT_INVALID: DiagnosticClass.CLAIM_DEFINITION,
    GapClass.CLAIM_AMBIGUOUS: DiagnosticClass.CLAIM_DEFINITION,
    GapClass.CLAIM_REFUSED: DiagnosticClass.CLAIM_DEFINITION,
    GapClass.CAPABILITY_MISSING: DiagnosticClass.CAPABILITY,
    GapClass.EXECUTION_REFUSED: DiagnosticClass.EXECUTION,
    GapClass.BINDING_PROBLEM: DiagnosticClass.EXECUTION,
    GapClass.CONTEXT_MISMATCH: DiagnosticClass.CONTEXT,
    GapClass.EVIDENCE_NOT_ASSEMBLED: DiagnosticClass.EVIDENCE_ASSEMBLY,
    GapClass.MODEL_APPLICABILITY_UNKNOWN: DiagnosticClass.APPLICABILITY,
    GapClass.MODEL_OUTSIDE_DOMAIN: DiagnosticClass.APPLICABILITY,
    GapClass.CHECK_FAILED: DiagnosticClass.VERIFICATION,
    GapClass.CHECK_NOT_RUN: DiagnosticClass.VERIFICATION,
    GapClass.VALIDATION_LEVEL_MISSING: DiagnosticClass.VALIDATION,
    GapClass.NUMERICAL_UQ_MISSING: DiagnosticClass.NUMERICAL_UNCERTAINTY,
    GapClass.PARAMETER_UQ_MISSING: DiagnosticClass.PARAMETER_UNCERTAINTY,
    GapClass.MEASUREMENT_UQ_MISSING: DiagnosticClass.MEASUREMENT_UNCERTAINTY,
    GapClass.MODEL_FORM_UNCERTAINTY_UNKNOWN: DiagnosticClass.MODEL_FORM,
    GapClass.UNCERTAINTY_BAND_STRADDLES: DiagnosticClass.DECISION_MARGIN,
    GapClass.EXTERNAL_EVIDENCE_MISSING: DiagnosticClass.EXTERNAL_EVIDENCE,
    GapClass.INDEPENDENT_ROUTE_MISSING: DiagnosticClass.INDEPENDENCE,
    GapClass.ASSURANCE_OBLIGATION_UNMET: DiagnosticClass.ASSURANCE,
    GapClass.SOURCE_CLOSURE_INCOMPLETE: DiagnosticClass.PROVENANCE,
    GapClass.UNEXPLAINED: DiagnosticClass.UNEXPLAINED,
}


@dataclass(frozen=True)
class RootCauseFinding:
    """A recorded blocker or diagnostic condition, not a physical-causality claim."""

    cause_class: DiagnosticClass
    target: str
    blocking: bool
    reason: str
    source: str
    gap_id: str | None = None
    physical_cause_established: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "cause_class": self.cause_class.value,
            "target": self.target,
            "blocking": self.blocking,
            "reason": self.reason,
            "source": self.source,
            "gap_id": self.gap_id,
            "physical_cause_established": self.physical_cause_established,
        }


class AssumptionKind(str, Enum):
    CALLER = "caller"
    ANALYSIS_METHOD = "analysis_method"


class AssumptionStatus(str, Enum):
    DECLARED_NOT_EVIDENCE = "declared_not_evidence"
    METHOD_LIMITATION = "method_limitation"


@dataclass(frozen=True)
class AssumptionEntry:
    assumption_id: str
    statement: str
    kind: AssumptionKind
    status: AssumptionStatus
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "assumption_id": self.assumption_id,
            "statement": self.statement,
            "kind": self.kind.value,
            "status": self.status.value,
            "source": self.source,
            "can_grant_evidence": False,
        }


@dataclass(frozen=True)
class AssumptionAnalysis:
    assumptions: tuple[AssumptionEntry, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "assumptions": [a.to_dict() for a in self.assumptions],
            "notice": "assumptions are tracked for audit and challenge; an assumption is never evidence merely because it was declared",
        }


def analyze_assumptions(
    record: Mapping[str, Any],
    *,
    robustness: Mapping[str, Any] | None = None,
) -> AssumptionAnalysis:
    entries: list[AssumptionEntry] = []
    for index, item in enumerate((record.get("claim") or {}).get("assumptions") or []):
        entries.append(
            AssumptionEntry(
                assumption_id=str(item["assumption_id"]),
                statement=str(item["statement"]),
                kind=AssumptionKind.CALLER,
                status=AssumptionStatus.DECLARED_NOT_EVIDENCE,
                source=f"/claim/assumptions/{index}",
            )
        )
    if robustness is not None:
        for index, statement in enumerate(robustness.get("assumptions") or []):
            entries.append(
                AssumptionEntry(
                    assumption_id=f"robustness:{index}",
                    statement=str(statement),
                    kind=AssumptionKind.ANALYSIS_METHOD,
                    status=AssumptionStatus.METHOD_LIMITATION,
                    source=f"/robustness/assumptions/{index}",
                )
            )
    return AssumptionAnalysis(tuple(entries))


class DiscrepancyStatus(str, Enum):
    NO_ADMISSIBLE_COMPARISON = "no_admissible_comparison"
    UNDECIDED = "undecided"
    CONSISTENT = "consistent"
    OBSERVED_MISMATCH = "observed_mismatch"


@dataclass(frozen=True)
class DiscrepancyComparison:
    source_class: str
    record_digest: str
    outcome: str
    difference: float | None
    allowed: float | None
    excess: float | None
    units: str | None
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_class": self.source_class,
            "record_digest": self.record_digest,
            "outcome": self.outcome,
            "difference": self.difference,
            "allowed": self.allowed,
            "excess": self.excess,
            "units": self.units,
            "source": self.source,
        }


@dataclass(frozen=True)
class ModelDiscrepancyAnalysis:
    status: DiscrepancyStatus
    comparisons: tuple[DiscrepancyComparison, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "comparisons": [c.to_dict() for c in self.comparisons],
            "quantifies_model_form_uncertainty": False,
            "notice": (
                "this is a model-data discrepancy diagnostic only; even an observed mismatch does not by itself "
                "quantify model-form uncertainty or identify a physical cause"
            ),
        }


def analyze_model_discrepancy(record: Mapping[str, Any]) -> ModelDiscrepancyAnalysis:
    out: list[DiscrepancyComparison] = []
    for index, item in enumerate(record.get("external_evidence_assessments") or []):
        if item.get("standing") != "admissible":
            continue
        comparison = item.get("comparison")
        if not isinstance(comparison, Mapping):
            continue
        outcome = str(comparison.get("outcome", "undecided"))
        difference = comparison.get("difference")
        allowed = comparison.get("allowed")
        difference = float(difference) if isinstance(difference, (int, float)) else None
        allowed = float(allowed) if isinstance(allowed, (int, float)) else None
        excess = None
        if difference is not None and allowed is not None:
            excess = max(0.0, abs(difference) - allowed)
        value = (item.get("record") or {}).get("value")
        units = value.get("units") if isinstance(value, Mapping) else None
        out.append(
            DiscrepancyComparison(
                source_class=str(item.get("source_class")),
                record_digest=str(item.get("record_digest")),
                outcome=outcome,
                difference=difference,
                allowed=allowed,
                excess=excess,
                units=None if units is None else str(units),
                source=f"/external_evidence_assessments/{index}/comparison",
            )
        )
    outcomes = {item.outcome for item in out}
    if "inconsistent" in outcomes:
        status = DiscrepancyStatus.OBSERVED_MISMATCH
    elif "consistent" in outcomes:
        status = DiscrepancyStatus.CONSISTENT
    elif out:
        status = DiscrepancyStatus.UNDECIDED
    else:
        status = DiscrepancyStatus.NO_ADMISSIBLE_COMPARISON
    return ModelDiscrepancyAnalysis(status, tuple(out))


@dataclass(frozen=True)
class CorrectiveAction:
    rank: int
    action: str
    target: str
    addresses_gaps: tuple[str, ...]
    expected_evidence_type: str
    executable_by_forge: bool
    reason: str
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "action": self.action,
            "target": self.target,
            "addresses_gaps": list(self.addresses_gaps),
            "expected_evidence_type": self.expected_evidence_type,
            "executable_by_forge": self.executable_by_forge,
            "reason": self.reason,
            "source": self.source,
            "guarantees_fix": False,
            "requires_reassessment": True,
        }


def _corrective_actions(plan: NextExperimentPlan) -> tuple[CorrectiveAction, ...]:
    return tuple(
        CorrectiveAction(
            rank=index + 1,
            action=rec.action.value,
            target=rec.target,
            addresses_gaps=rec.addresses_gaps,
            expected_evidence_type=rec.expected_evidence_type,
            executable_by_forge=rec.executable_by_forge,
            reason=rec.reason,
            source=rec.source,
        )
        for index, rec in enumerate(plan.recommendations)
    )


class HypothesisKind(str, Enum):
    MODEL_FORM_OR_PARAMETER = "model_form_or_parameter"
    PARAMETER_CONTRIBUTOR = "parameter_contributor"


@dataclass(frozen=True)
class RepairHypothesis:
    rank: int
    kind: HypothesisKind
    target: str
    basis: str
    proposed_test: str
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "kind": self.kind.value,
            "target": self.target,
            "basis": self.basis,
            "proposed_test": self.proposed_test,
            "source": self.source,
            "status": "hypothesis",
            "causal_relationship_established": False,
            "guarantees_fix": False,
        }


def _sensitivity_candidates(
    sensitivity: Mapping[str, Any] | None,
    *,
    qoi: str | None,
) -> list[Mapping[str, Any]]:
    if sensitivity is None or sensitivity.get("quantity") != qoi:
        return []
    usable = [
        item
        for item in sensitivity.get("parameters") or []
        if item.get("problem") is None and isinstance(item.get("derivative"), (int, float))
    ]
    return sorted(
        usable,
        key=lambda item: (
            -abs(
                float(item["normalized"])
                if isinstance(item.get("normalized"), (int, float))
                else float(item["derivative"])
            ),
            str(item.get("path")),
        ),
    )


def _repair_hypotheses(
    record: Mapping[str, Any],
    discrepancy: ModelDiscrepancyAnalysis,
    *,
    sensitivity: Mapping[str, Any] | None,
) -> tuple[RepairHypothesis, ...]:
    if discrepancy.status is not DiscrepancyStatus.OBSERVED_MISMATCH:
        return ()
    qoi = ((record.get("claim") or {}).get("qoi") or {}).get("name")
    candidates = _sensitivity_candidates(sensitivity, qoi=qoi)
    if not candidates:
        return (
            RepairHypothesis(
                rank=1,
                kind=HypothesisKind.MODEL_FORM_OR_PARAMETER,
                target=str(qoi or "qoi"),
                basis="an admissible external comparison is inconsistent with the simulated value",
                proposed_test=(
                    "run declared sensitivity/challenge analysis, independently characterize influential inputs, "
                    "then re-evaluate against held-out validation data"
                ),
                source="/external_evidence_assessments",
            ),
        )
    hypotheses: list[RepairHypothesis] = []
    for index, item in enumerate(candidates[:3]):
        hypotheses.append(
            RepairHypothesis(
                rank=index + 1,
                kind=HypothesisKind.PARAMETER_CONTRIBUTOR,
                target=str(item["path"]),
                basis=(
                    "an admissible model-data mismatch exists and this parameter has high local numerical sensitivity; "
                    "sensitivity is not causality"
                ),
                proposed_test=(
                    "measure or otherwise characterize this input independently, rerun the model, "
                    "and test the corrected prediction on independent validation data"
                ),
                source=f"/sensitivity/parameters/{index}",
            )
        )
    return tuple(hypotheses)


def _root_causes(
    gaps: EvidenceGapAnalysis,
    discrepancy: ModelDiscrepancyAnalysis,
    record: Mapping[str, Any],
) -> tuple[RootCauseFinding, ...]:
    findings = [
        RootCauseFinding(
            cause_class=_GAP_CAUSE[gap.kind],
            target=gap.target,
            blocking=gap.blocking,
            reason=gap.reason,
            source=gap.source,
            gap_id=gap.gap_id,
        )
        for gap in gaps.gaps
    ]
    if discrepancy.status is DiscrepancyStatus.OBSERVED_MISMATCH:
        qoi = ((record.get("claim") or {}).get("qoi") or {}).get("name") or "qoi"
        findings.append(
            RootCauseFinding(
                cause_class=DiagnosticClass.MODEL_DATA_MISMATCH,
                target=str(qoi),
                blocking=False,
                reason="at least one admissible external comparison is inconsistent with the simulated result",
                source="/external_evidence_assessments",
                gap_id=None,
            )
        )
    return tuple(findings)


@dataclass(frozen=True)
class ScientificDiagnosticReport:
    assessment_digest: str
    verdict: str
    root_causes: tuple[RootCauseFinding, ...]
    assumptions: AssumptionAnalysis
    discrepancy: ModelDiscrepancyAnalysis
    corrective_actions: tuple[CorrectiveAction, ...]
    repair_hypotheses: tuple[RepairHypothesis, ...]
    unaddressed_gaps: tuple[str, ...]
    gap_analysis_digest: str
    next_experiment_digest: str

    @property
    def primary_cause(self) -> RootCauseFinding | None:
        return next((item for item in self.root_causes if item.blocking), None) or (
            self.root_causes[0] if self.root_causes else None
        )

    def to_dict(self) -> dict[str, Any]:
        primary = self.primary_cause
        return {
            "assessment_digest": self.assessment_digest,
            "verdict": self.verdict,
            "primary_cause": None if primary is None else primary.to_dict(),
            "root_causes": [item.to_dict() for item in self.root_causes],
            "assumptions": self.assumptions.to_dict(),
            "model_discrepancy": self.discrepancy.to_dict(),
            "corrective_actions": [item.to_dict() for item in self.corrective_actions],
            "repair_hypotheses": [item.to_dict() for item in self.repair_hypotheses],
            "unaddressed_gaps": list(self.unaddressed_gaps),
            "gap_analysis_digest": self.gap_analysis_digest,
            "next_experiment_digest": self.next_experiment_digest,
            "notice": (
                "derived diagnostic only: it cannot alter the recorded verdict; hypotheses are not evidence, "
                "and corrective actions require new evidence plus reassessment before any stronger conclusion"
            ),
        }

    @property
    def digest(self) -> str:
        return tagged_digest(_TAG, self.to_dict())


def diagnose_assessment(
    record: Mapping[str, Any],
    registry: Any,
    *,
    sensitivity: Mapping[str, Any] | None = None,
    robustness: Mapping[str, Any] | None = None,
) -> ScientificDiagnosticReport:
    """Explain blockers and propose testable repairs without changing authority."""

    gaps = analyze_gaps(record)
    next_plan = recommend_next(record, registry, gaps)
    discrepancy = analyze_model_discrepancy(record)
    return ScientificDiagnosticReport(
        assessment_digest=record_digest(record),
        verdict=str(record.get("verdict")),
        root_causes=_root_causes(gaps, discrepancy, record),
        assumptions=analyze_assumptions(record, robustness=robustness),
        discrepancy=discrepancy,
        corrective_actions=_corrective_actions(next_plan),
        repair_hypotheses=_repair_hypotheses(record, discrepancy, sensitivity=sensitivity),
        unaddressed_gaps=next_plan.unaddressed_gaps,
        gap_analysis_digest=gaps.digest,
        next_experiment_digest=next_plan.digest,
    )


__all__ = [
    "AssumptionAnalysis",
    "AssumptionEntry",
    "AssumptionKind",
    "AssumptionStatus",
    "CorrectiveAction",
    "DiagnosticClass",
    "DiscrepancyComparison",
    "DiscrepancyStatus",
    "HypothesisKind",
    "ModelDiscrepancyAnalysis",
    "RepairHypothesis",
    "RootCauseFinding",
    "ScientificDiagnosticReport",
    "analyze_assumptions",
    "analyze_model_discrepancy",
    "diagnose_assessment",
]
