"""Bridge production credibility reports into SRIA candidate evidence.

Layering
--------
The Scientific Core must not import SRIA, and SRIA should remain usable without
the MCP transport.  This module therefore lives above both.  It does not run
physics, reinterpret validation checks, or choose a favourable uncertainty
model.  It derives a candidate SRIA claim from one value already present in a
:class:`CredibilityEvidenceReport`.

The bridge is deliberately conservative:

* the claim value and units are copied from the report, never supplied by the
  caller;
* the evidence provenance is the report's producing run;
* the exact campaign charter + terminal decision are content-addressed into
  `context_ref`, and the same ref is inserted into the claim binding so
  bridged belief keys are context-sensitive without changing the global SRIA
  schema;
* missing model-form discrepancy becomes `UNKNOWN`, never
  `ZERO_DECLARED`;
* a quantified uncertainty with no attributable channel is refused rather than
  guessed into one;
* validation levels are re-read by a registered process critic from the report
  itself.  Evidence metadata is commentary/provenance, not authority.

This is a transport boundary, not a certification shortcut.  Candidate evidence
still has to pass the normal Critics -> Arbiter -> Admission -> Gateway path.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping

from ..mcp.evidence import (
    CredibilityEvidenceReport,
    CredibilityVerdict,
)
from ..scientific.results.uncertainty import (
    UncertaintySource,
)
from ..scientific.results.validation import ValidationLevel
from ..sria.charter import CampaignCharter
from ..sria.evidence import (
    ClaimBinding,
    ClaimType,
    Evidence,
    SourceClass,
)
from ..sria.provenance import AssessmentProvenance
from ..sria.uncertainty import (
    CHANNEL_OF_SOURCE,
    DiscrepancyKind,
    ModelDiscrepancy,
    SubjectModel,
    UncertaintyDeclaration,
)
from ..sria.assurance.assessment import (
    CheckRecord,
    CriticAssessment,
    CriticClass,
    CriticVerdict,
    Finding,
    FindingImpact,
    Severity,
)

CREDIBILITY_REPORT_CRITIC_ID = "sria.credibility_report"
_BRIDGE_VERSION = "decision-evidence/1"
_CONTEXT_VERSION = "decision-context/1"


class DecisionEvidenceBridgeError(ValueError):
    """The report cannot be represented as SRIA evidence without guessing."""


def _canonical_digest(payload: Any, *, tag: str) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    ).encode("utf-8")
    digest = hashlib.sha256()
    digest.update(tag.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(encoded)
    return digest.hexdigest()


def report_digest(report: CredibilityEvidenceReport) -> str:
    """Content identity of the exact credibility report presented to the bridge."""
    if not isinstance(report, CredibilityEvidenceReport):
        raise DecisionEvidenceBridgeError(
            f"report must be CredibilityEvidenceReport, got {type(report).__name__}"
        )
    return _canonical_digest(report.to_dict(), tag="crafty.credibility-report/1")


def _decision_context_payload(
    charter: CampaignCharter,
    decision_id: str,
    operating_context_ref: str,
) -> dict[str, str]:
    if not isinstance(charter, CampaignCharter):
        raise DecisionEvidenceBridgeError(
            f"charter must be CampaignCharter, got {type(charter).__name__}"
        )
    decision_id = str(decision_id).strip()
    known = {decision.decision_id for decision in charter.terminal_decisions}
    if decision_id not in known:
        raise DecisionEvidenceBridgeError(
            f"decision {decision_id!r} is not a terminal decision of campaign "
            f"{charter.campaign_id!r}; known decisions: {sorted(known)}"
        )
    return {
        "campaign_id": charter.campaign_id,
        "charter_digest": charter.digest,
        "charter_version": charter.version,
        "decision_id": decision_id,
        "operating_context_ref": str(operating_context_ref).strip(),
    }


def decision_context_ref(
    charter: CampaignCharter,
    decision_id: str,
    *,
    operating_context_ref: str = "",
) -> str:
    """Stable identity for the exact charter, decision and operating context."""
    payload = _decision_context_payload(charter, decision_id, operating_context_ref)
    digest = _canonical_digest(payload, tag=f"crafty.{_CONTEXT_VERSION}")
    return f"{_CONTEXT_VERSION}:{digest}"


def _uncertainty_declaration(
    report: CredibilityEvidenceReport,
    value_name: str,
    *,
    model_discrepancy: ModelDiscrepancy | None,
) -> UncertaintyDeclaration:
    discrepancy = model_discrepancy or ModelDiscrepancy(
        kind=DiscrepancyKind.UNKNOWN,
        rationale=(
            "the production credibility report does not declare a model-form "
            "discrepancy assumption; the bridge preserves that absence as UNKNOWN"
        ),
    )
    if not isinstance(discrepancy, ModelDiscrepancy):
        raise DecisionEvidenceBridgeError(
            "model_discrepancy must be a ModelDiscrepancy when supplied"
        )

    record = report.uncertainty.get(value_name)
    channels = {}
    notes: list[str] = []

    if record is None:
        notes.append(
            f"report declares no per-value uncertainty for {value_name!r}; "
            "all undeclared SRIA channels remain UNKNOWN"
        )
    else:
        source = UncertaintySource(record.source_kind)
        channel = CHANNEL_OF_SOURCE.get(source)

        if channel is not None:
            # This also preserves a source-attributed UNKNOWN record: the
            # channel is known, while its magnitude is honestly not.
            channels[channel] = record
        elif record.is_quantified:
            if source is UncertaintySource.UNSPECIFIED:
                raise DecisionEvidenceBridgeError(
                    f"report uncertainty for {value_name!r} is quantified but "
                    "declares no source_kind. The bridge cannot decide whether "
                    "it is measurement, parameter, numerical or model-form "
                    "uncertainty."
                )
            if source is UncertaintySource.COMBINED:
                raise DecisionEvidenceBridgeError(
                    f"report uncertainty for {value_name!r} is COMBINED. SRIA "
                    "budgets require per-channel components; filing a combined "
                    "number under one channel would double-count its contents."
                )
            raise DecisionEvidenceBridgeError(
                f"report uncertainty source {source.value!r} maps to no SRIA channel"
            )
        else:
            notes.append(
                f"report uncertainty for {value_name!r} is UNKNOWN with source "
                f"{source.value!r}; no quantified uncertainty is invented"
            )

    return UncertaintyDeclaration(
        subject_model=SubjectModel.PREDICTION_MODEL,
        discrepancy=discrepancy,
        channels=channels,
        notes="; ".join(notes),
    )


def evidence_from_credibility_report(
    report: CredibilityEvidenceReport,
    *,
    evidence_id: str,
    value_name: str,
    domain_pack_ref: str,
    charter: CampaignCharter,
    decision_id: str,
    operating_context_ref: str = "",
    qualifiers: Mapping[str, str] | None = None,
    model_discrepancy: ModelDiscrepancy | None = None,
) -> Evidence:
    """Derive one QOI-value candidate from one report value.

    The caller chooses *which existing value* is relevant and the routing
    identities (campaign/domain); it never supplies the scientific value or its
    units.  This is the central anti-copy invariant of the bridge.
    """
    if not isinstance(report, CredibilityEvidenceReport):
        raise DecisionEvidenceBridgeError(
            f"report must be CredibilityEvidenceReport, got {type(report).__name__}"
        )
    value_name = str(value_name).strip()
    if value_name not in report.values:
        raise DecisionEvidenceBridgeError(
            f"report {report.run_id!r} has no value {value_name!r}; "
            f"available: {sorted(report.values)}"
        )
    evidence_id = str(evidence_id).strip()
    domain_pack_ref = str(domain_pack_ref).strip()
    if not evidence_id:
        raise DecisionEvidenceBridgeError("evidence_id must be non-empty")
    if not domain_pack_ref:
        raise DecisionEvidenceBridgeError("domain_pack_ref must be non-empty")

    context_payload = _decision_context_payload(
        charter, decision_id, operating_context_ref
    )
    context_ref = decision_context_ref(
        charter,
        decision_id,
        operating_context_ref=operating_context_ref,
    )

    qualifiers = {str(k): str(v) for k, v in dict(qualifiers or {}).items()}
    if "context_ref" in qualifiers and qualifiers["context_ref"] != context_ref:
        raise DecisionEvidenceBridgeError(
            "qualifier 'context_ref' is reserved by the bridge and must match "
            "the exact campaign/decision context"
        )
    qualifiers["context_ref"] = context_ref

    quantity = report.values[value_name]
    digest = report_digest(report)
    attained = sorted(level.value for level in report.attained_levels)

    return Evidence(
        evidence_id=evidence_id,
        source_class=SourceClass.SIMULATION,
        claim_type=ClaimType.QOI_VALUE,
        claim_binding=ClaimBinding(
            subject_kind="qoi",
            subject_ref=value_name,
            qualifiers=qualifiers,
        ),
        claim_payload={
            "value": quantity.magnitude,
            "units": str(quantity.units),
        },
        uncertainty=_uncertainty_declaration(
            report,
            value_name,
            model_discrepancy=model_discrepancy,
        ),
        provenance_ref=report.provenance.run_id,
        domain_pack_ref=domain_pack_ref,
        context_ref=context_ref,
        metadata={
            "bridge_version": _BRIDGE_VERSION,
            "source_report_digest": digest,
            "source_report_run_id": report.run_id,
            "source_provenance_run_id": report.provenance.run_id,
            "credibility_verdict": report.verdict.value,
            "evidence_basis": report.evidence_basis,
            "attained_validation_levels": attained,
            "decision_context": context_payload,
        },
    )


def _binding_gaps(
    report: CredibilityEvidenceReport,
    evidence: Evidence,
    charter: CampaignCharter,
) -> tuple[str, ...]:
    gaps: list[str] = []
    if evidence.source_class is not SourceClass.SIMULATION:
        gaps.append("evidence source_class is not simulation")
    if evidence.claim_type is not ClaimType.QOI_VALUE:
        gaps.append("evidence claim_type is not qoi_value")
    if evidence.provenance_ref != report.provenance.run_id:
        gaps.append(
            f"evidence provenance {evidence.provenance_ref!r} != "
            f"report provenance {report.provenance.run_id!r}"
        )

    name = evidence.claim_binding.subject_ref
    quantity = report.values.get(name)
    if quantity is None:
        gaps.append(f"report holds no claimed quantity {name!r}")
    else:
        payload = evidence.claim_payload
        value = payload.get("value")
        units = payload.get("units")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            gaps.append("claim payload does not carry a numeric value")
        elif not isinstance(units, str) or not units.strip():
            gaps.append("claim payload does not carry units")
        else:
            try:
                held = float(quantity.to(units).magnitude)
                stated = float(value)
                if not math.isclose(stated, held, rel_tol=1e-9, abs_tol=0.0):
                    gaps.append(
                        f"claim states {stated} {units}, report holds {held} {units}"
                    )
            except Exception as exc:  # noqa: BLE001 - mismatch is the result
                gaps.append(f"claim units/value cannot be matched to report: {exc}")

    if evidence.context_ref != evidence.claim_binding.qualifiers.get("context_ref", ""):
        gaps.append("claim binding is not scoped to evidence.context_ref")

    context_meta = evidence.metadata.get("decision_context")
    if not isinstance(context_meta, Mapping):
        gaps.append("evidence carries no structured decision_context metadata")
    else:
        decision_id = str(context_meta.get("decision_id", ""))
        operating_context_ref = str(context_meta.get("operating_context_ref", ""))
        try:
            expected_context = _decision_context_payload(
                charter, decision_id, operating_context_ref
            )
            if dict(context_meta) != expected_context:
                gaps.append(
                    "evidence decision_context does not match the governing charter"
                )
            expected_context_ref = decision_context_ref(
                charter,
                decision_id,
                operating_context_ref=operating_context_ref,
            )
            if evidence.context_ref != expected_context_ref:
                gaps.append(
                    "evidence context_ref is not derived from the governing charter"
                )
        except DecisionEvidenceBridgeError as exc:
            gaps.append(f"decision context is not governed by this charter: {exc}")

    expected_digest = report_digest(report)
    if evidence.metadata.get("source_report_digest") != expected_digest:
        gaps.append("evidence does not pin the exact credibility report digest")
    if evidence.metadata.get("source_report_run_id") != report.run_id:
        gaps.append("evidence metadata names a different credibility report run")

    return tuple(gaps)


class CredibilityReportCritic:
    """Trusted process critic for the Core/MCP -> SRIA bridge.

    It does not grant validation levels.  It asks the credibility report which
    levels the core already says were attained, then emits named SRIA checks so
    an existing charter obligation can resolve them.  The Arbiter still decides
    whether those checks satisfy policy.
    """

    critic_id = CREDIBILITY_REPORT_CRITIC_ID
    critic_version = "1"
    critic_class = CriticClass.PROCESS

    def assess(
        self,
        report: CredibilityEvidenceReport,
        evidence: Evidence,
        charter: CampaignCharter,
        *,
        assessment_id: str,
    ) -> CriticAssessment:
        if not isinstance(report, CredibilityEvidenceReport):
            raise TypeError("CredibilityReportCritic requires CredibilityEvidenceReport")
        if not isinstance(evidence, Evidence):
            raise TypeError("CredibilityReportCritic requires Evidence")
        if not isinstance(charter, CampaignCharter):
            raise TypeError("CredibilityReportCritic requires CampaignCharter")

        gaps = _binding_gaps(report, evidence, charter)
        checks: list[CheckRecord] = [
            CheckRecord(
                name="credibility_report_binding",
                outcome=CriticVerdict.PASS if not gaps else CriticVerdict.FAIL,
                mandatory=True,
                detail=(
                    "claim, provenance, context and source-report digest are bound"
                    if not gaps
                    else "; ".join(gaps)
                ),
            )
        ]

        attained = set(report.attained_levels)
        for level in ValidationLevel:
            checks.append(
                CheckRecord(
                    name=f"validation_level:{level.value}",
                    outcome=(
                        CriticVerdict.PASS
                        if level in attained
                        else CriticVerdict.NOT_ASSESSED
                    ),
                    mandatory=False,
                    detail=(
                        "attained by the source credibility report"
                        if level in attained
                        else "not attained by the source credibility report"
                    ),
                )
            )

        checks.append(
            CheckRecord(
                name="credibility_report_supported",
                outcome={
                    CredibilityVerdict.SUPPORTED: CriticVerdict.PASS,
                    CredibilityVerdict.INSUFFICIENT_EVIDENCE: CriticVerdict.INCONCLUSIVE,
                    CredibilityVerdict.NOT_SUPPORTED: CriticVerdict.FAIL,
                }[report.verdict],
                mandatory=True,
                detail=(
                    f"source report verdict={report.verdict.value}; "
                    f"evidence_basis={report.evidence_basis}"
                ),
            )
        )

        if gaps:
            verdict = CriticVerdict.FAIL
        elif report.verdict is CredibilityVerdict.SUPPORTED:
            verdict = CriticVerdict.PASS
        elif report.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE:
            verdict = CriticVerdict.INCONCLUSIVE
        else:
            verdict = CriticVerdict.FAIL

        findings: tuple[Finding, ...] = ()
        if gaps:
            findings = (
                Finding(
                    code="bridge.credibility_report_misbound",
                    severity=Severity.BLOCKING,
                    impact=FindingImpact.ASSURANCE_BLOCKING,
                    category="provenance",
                    message="; ".join(gaps),
                    check_name="credibility_report_binding",
                ),
            )
        elif report.verdict is not CredibilityVerdict.SUPPORTED:
            findings = (
                Finding(
                    code=f"bridge.credibility_{report.verdict.value}",
                    severity=Severity.MAJOR,
                    impact=FindingImpact.ASSURANCE_BLOCKING,
                    category="credibility",
                    message=(
                        "the source credibility report does not support relying "
                        "on this value for a decision-grade claim"
                    ),
                    check_name="credibility_report_supported",
                ),
            )

        digest = report_digest(report)
        return CriticAssessment(
            assessment_id=assessment_id,
            critic_id=self.critic_id,
            critic_version=self.critic_version,
            critic_class=self.critic_class,
            subject_ref=evidence.record_hash,
            verdict=verdict,
            provenance=AssessmentProvenance(
                assessment_id=assessment_id,
                critic_id=self.critic_id,
                critic_version=self.critic_version,
                inputs_ref=(
                    report.run_id,
                    report.provenance.run_id,
                    digest,
                    charter.digest,
                ),
                metadata={
                    "source_report_digest": digest,
                    "source_report_verdict": report.verdict.value,
                    "source_evidence_basis": report.evidence_basis,
                    "charter_digest": charter.digest,
                },
            ),
            checks=tuple(checks),
            findings=findings,
            summary=(
                "credibility report is bound and eligible for policy evaluation"
                if verdict is CriticVerdict.PASS
                else f"credibility report assessment is {verdict.value}"
            ),
        )
