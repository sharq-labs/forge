"""Generic structured scientific-claim assessment over registered MCP systems.

This is orchestration, not a planner.  The caller must name:

- the registered system to execute;
- the complete case payload that system accepts;
- which reported quantity is the claim;
- the terminal decision the evidence is for;
- the ValidationLevel(s) required before that decision may be supported;
- an explicit model-discrepancy declaration.

Nothing here selects a model, guesses a context, invents a confidence target or
turns natural language into scientific structure.  It reuses the existing
execution, credibility, SRIA evidence and assurance paths.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..scientific.results.validation import ValidationLevel
from ..scientific.serialization import schema_string
from ..sria import (
    CampaignCharter,
    ConfidenceRequirement,
    DiscrepancyKind,
    ModelDiscrepancy,
    TerminalDecision,
)
from ..sria.assurance import (
    Arbiter,
    CriticClass,
    charter_context_ref,
    obligations_from_charter,
    trusting_authority,
)
from .evidence import CredibilityEvidenceReport
from .sria_bridge import CredibilityReportCritic, evidence_from_credibility_report
from .systems import system

CLAIM_ASSESSMENT_SCHEMA = schema_string("mcp_claim_assessment")
CLAIM_ASSESSMENT_ERROR_SCHEMA = schema_string("mcp_claim_assessment_error")


class ClaimAssessmentError(ValueError):
    """A structured assessment request is incomplete or ambiguous."""


def _mapping(payload: Any, *, name: str) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise ClaimAssessmentError(f"{name} must be an object")
    return payload


def _text(payload: Mapping[str, Any], key: str, *, where: str = "request") -> str:
    value = str(payload.get(key, "")).strip()
    if not value:
        raise ClaimAssessmentError(f"{where}.{key} is required and must be non-empty")
    return value


def _required_levels(payload: Any) -> tuple[ValidationLevel, ...]:
    if isinstance(payload, (str, bytes)) or not isinstance(payload, Sequence):
        raise ClaimAssessmentError("required_levels must be a non-empty array")
    if not payload:
        raise ClaimAssessmentError(
            "required_levels must name at least one evidentiary level; "
            "a decision standard cannot be inferred"
        )
    try:
        levels = tuple(ValidationLevel(item) for item in payload)
    except (TypeError, ValueError) as exc:
        raise ClaimAssessmentError(
            f"required_levels contains an unknown ValidationLevel: {exc}"
        ) from exc
    if ValidationLevel.UNVERIFIED in levels:
        raise ClaimAssessmentError(
            "UNVERIFIED is absence of a level and cannot be a requirement"
        )
    if len(set(levels)) != len(levels):
        raise ClaimAssessmentError("required_levels contains a duplicate level")
    return levels


def _discrepancy(payload: Any) -> ModelDiscrepancy:
    raw = _mapping(payload, name="discrepancy")
    try:
        kind = DiscrepancyKind(_text(raw, "kind", where="discrepancy"))
    except ValueError as exc:
        raise ClaimAssessmentError(f"discrepancy.kind is invalid: {exc}") from exc
    rationale = _text(raw, "rationale", where="discrepancy")
    reference = str(raw.get("reference", "")).strip()
    try:
        return ModelDiscrepancy(
            kind=kind,
            reference=reference,
            rationale=rationale,
        )
    except Exception as exc:
        raise ClaimAssessmentError(f"invalid discrepancy declaration: {exc}") from exc


def _reports(outcome: Any) -> tuple[CredibilityEvidenceReport, ...]:
    many = getattr(outcome, "reports", None)
    if many is not None:
        reports = tuple(many)
    else:
        one = getattr(outcome, "report", None)
        reports = () if one is None else (one,)
    if not reports or any(not isinstance(r, CredibilityEvidenceReport) for r in reports):
        raise ClaimAssessmentError(
            "the selected system did not return credibility evidence reports"
        )
    return reports


def _select_report(
    reports: tuple[CredibilityEvidenceReport, ...],
    request: Mapping[str, Any],
) -> tuple[int, CredibilityEvidenceReport]:
    raw_index = request.get("report_index")
    if raw_index is None:
        if len(reports) != 1:
            raise ClaimAssessmentError(
                f"system produced {len(reports)} reports; report_index is "
                "required because the assessment boundary will not guess "
                "which stage the claim refers to"
            )
        return 0, reports[0]
    if isinstance(raw_index, bool) or not isinstance(raw_index, int):
        raise ClaimAssessmentError("report_index must be an integer")
    if raw_index < 0 or raw_index >= len(reports):
        raise ClaimAssessmentError(
            f"report_index {raw_index} is out of range for {len(reports)} report(s)"
        )
    return raw_index, reports[raw_index]


def assess_claim_request(request: Mapping[str, Any]) -> dict[str, Any]:
    """Execute one registered system and assess one structured QOI claim."""

    request = _mapping(request, name="request")
    system_name = _text(request, "system")
    try:
        boundary = system(system_name)
    except KeyError as exc:
        raise ClaimAssessmentError(str(exc)) from exc

    case = _mapping(request.get("case"), name="case")
    quantity_name = _text(request, "quantity_name")
    decision_raw = _mapping(request.get("decision"), name="decision")
    decision_id = _text(decision_raw, "id", where="decision")
    decision_statement = _text(decision_raw, "statement", where="decision")
    required_levels = _required_levels(request.get("required_levels"))
    discrepancy = _discrepancy(request.get("discrepancy"))

    outcome = boundary.run(case)
    report_index, report = _select_report(_reports(outcome), request)
    if quantity_name not in report.values:
        raise ClaimAssessmentError(
            f"report {report_index} has no quantity {quantity_name!r}; "
            f"available: {sorted(report.values)}"
        )

    campaign_id = f"claim-assessment:{system_name}:{decision_id}"
    charter = CampaignCharter(
        campaign_id=campaign_id,
        terminal_decisions=(
            TerminalDecision(
                decision_id=decision_id,
                statement=decision_statement,
            ),
        ),
        confidence_requirements=(
            ConfidenceRequirement(
                requirement_id="claim_evidence_level",
                required_levels=required_levels,
                description=(
                    "the structured claim assessment requires these declared "
                    "evidentiary levels before the decision may be VALID"
                ),
            ),
        ),
    )
    obligations = obligations_from_charter(
        charter,
        required_critics=(CriticClass.PROCESS,),
        context_decision_id=decision_id,
    )
    context_ref = charter_context_ref(charter.digest, decision_id)

    evidence = evidence_from_credibility_report(
        report,
        quantity_name=quantity_name,
        evidence_id=f"claim:{report.run_id}:{quantity_name}",
        domain_pack_ref=f"system:{system_name}",
        context_ref=context_ref,
        discrepancy=discrepancy,
    )

    critic = CredibilityReportCritic()
    authority = trusting_authority(
        f"claim-assessment-authority:{system_name}",
        critics=(critic,),
        policies=(obligations,),
    )
    arbiter = Arbiter(authority, critics=(critic,))
    mandatory = tuple(
        obligation.target
        for obligation in obligations.obligations
        if obligation.target.startswith("validation_level:")
    )
    assessment = arbiter.run_critic(
        critic.critic_id,
        report,
        subject=evidence,
        assessment_id=f"credibility:{report.run_id}:{quantity_name}",
        mandatory_checks=mandatory,
    )
    decision = arbiter.decide(
        decision_id=f"assess:{decision_id}",
        evidence=evidence,
        assessments=(assessment,),
        obligations=obligations,
    )

    quantity = report.values[quantity_name]
    return {
        "schema": CLAIM_ASSESSMENT_SCHEMA,
        "status": "assessed",
        "system": system_name,
        "report_index": report_index,
        "report_run_id": report.run_id,
        "claim": {
            "quantity_name": quantity_name,
            "value": quantity.to_dict(),
            "evidence_record_hash": evidence.record_hash,
            "context_ref": evidence.context_ref,
            "source_closure_complete": evidence.source_closure_complete,
            "source_roots": list(evidence.independence_roots),
        },
        "credibility": {
            "verdict": report.verdict.value,
            "evidence_basis": report.evidence_basis,
            "attained_levels": sorted(level.value for level in report.attained_levels),
            "required_levels": [level.value for level in required_levels],
            "missing_required_levels": sorted(
                level.value
                for level in set(required_levels) - set(report.attained_levels)
            ),
        },
        "assurance": {
            "verdict": decision.verdict.value,
            "unmet_obligations": list(decision.unmet_obligations),
            "reasons": list(decision.reasons),
            "refused_assessments": list(decision.refused_assessments),
            "obligations": [
                result.to_dict() for result in decision.obligation_results
            ],
        },
        "decision": {
            "decision_id": decision_id,
            "statement": decision_statement,
            "charter_digest": charter.digest,
        },
        "discrepancy": discrepancy.to_dict(),
        "notice": (
            "This is a structured scientific assurance assessment, not a "
            "safety certification and not an automatic real-world decision."
        ),
    }


def refused_claim_assessment(exc: Exception) -> dict[str, Any]:
    """Stable error payload for the public MCP tool."""
    return {
        "schema": CLAIM_ASSESSMENT_ERROR_SCHEMA,
        "status": "refused",
        "error": str(exc),
    }


__all__ = [
    "CLAIM_ASSESSMENT_ERROR_SCHEMA",
    "CLAIM_ASSESSMENT_SCHEMA",
    "ClaimAssessmentError",
    "assess_claim_request",
    "refused_claim_assessment",
]
