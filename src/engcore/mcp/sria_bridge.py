"""Bridge production credibility reports into SRIA candidate evidence.

This module lives under engcore.mcp on purpose. The Scientific Core must not
depend on SRIA, and SRIA must not need to know about one transport's report
shape. The bridge is therefore a consumer-side adapter:

    CredibilityEvidenceReport -> Evidence

It derives the numeric claim from the report itself. A caller chooses which
reported quantity is being claimed and supplies the decision/context identity
and the domain-pack identity, but cannot supply another value.

Uncertainty is carried only when the production record itself names a source
channel that SRIA already understands. UNKNOWN stays unknown. An unattributed
or COMBINED quantified record is refused rather than guessed into a channel.

Validation levels are not copied into Evidence metadata. They are assessed by
CredibilityReportCritic through the Arbiter's trusted-critic path, so a caller
cannot grant itself a level by editing an envelope.
"""

from __future__ import annotations

import hashlib
import json
from typing import Iterable

from ..scientific.results.uncertainty import UncertaintySource
from ..scientific.results.validation import ValidationLevel
from ..sria import (
    ClaimBinding,
    ClaimType,
    Evidence,
    ModelDiscrepancy,
    SourceClass,
    SubjectModel,
    UncertaintyDeclaration,
)
from ..sria.assurance.assessment import (
    CheckRecord,
    CriticAssessment,
    CriticClass,
    CriticVerdict,
)
from ..sria.provenance import AssessmentProvenance
from ..sria.uncertainty import CHANNEL_OF_SOURCE
from .evidence import CredibilityEvidenceReport

__all__ = [
    "CredibilityReportCritic",
    "evidence_from_credibility_report",
]


def _report_digest(report: CredibilityEvidenceReport) -> str:
    blob = json.dumps(report.to_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _uncertainty_declaration(
    report: CredibilityEvidenceReport,
    quantity_name: str,
    *,
    discrepancy: ModelDiscrepancy,
) -> UncertaintyDeclaration:
    """Translate one report value's uncertainty without inventing attribution."""

    record = report.uncertainty.get(quantity_name)
    channels = {}
    if record is not None and record.is_quantified:
        source = UncertaintySource(record.source_kind)
        if source is UncertaintySource.UNSPECIFIED:
            raise ValueError(
                f"quantified uncertainty for {quantity_name!r} declares no "
                "source_kind; the bridge cannot guess an SRIA uncertainty channel"
            )
        if source is UncertaintySource.COMBINED:
            raise ValueError(
                f"quantified uncertainty for {quantity_name!r} is COMBINED; "
                "filing a mixture under one SRIA channel would double-count it"
            )
        channel = CHANNEL_OF_SOURCE.get(source)
        if channel is None:
            raise ValueError(
                f"no SRIA uncertainty channel is defined for source {source.value!r}"
            )
        channels[channel] = record

    return UncertaintyDeclaration(
        subject_model=SubjectModel.PREDICTION_MODEL,
        discrepancy=discrepancy,
        channels=channels,
        notes=(
            f"derived from credibility report {report.run_id!r}; undeclared "
            "channels remain UNKNOWN by UncertaintyDeclaration.channel()"
        ),
    )


def evidence_from_credibility_report(
    report: CredibilityEvidenceReport,
    *,
    quantity_name: str,
    evidence_id: str,
    domain_pack_ref: str,
    context_ref: str,
    discrepancy: ModelDiscrepancy,
) -> Evidence:
    """Derive candidate SRIA evidence for one quantity in a credibility report.

    quantity_name selects an already-produced value; it never supplies the
    value. This is the central trust property of the bridge.
    """

    if not isinstance(report, CredibilityEvidenceReport):
        raise TypeError("report must be a CredibilityEvidenceReport")
    if not isinstance(discrepancy, ModelDiscrepancy):
        raise TypeError(
            "discrepancy must be an explicit ModelDiscrepancy; the bridge "
            "will not assume zero model-form uncertainty"
        )
    name = str(quantity_name).strip()
    if name not in report.values:
        raise KeyError(
            f"credibility report {report.run_id!r} has no quantity {name!r}; "
            f"available: {sorted(report.values)}"
        )
    if not str(context_ref).strip():
        raise ValueError(
            "context_ref is required: decision evidence without an intended "
            "context cannot be distinguished from evidence for another use"
        )

    quantity = report.values[name]
    return Evidence(
        evidence_id=evidence_id,
        source_class=SourceClass.SIMULATION,
        claim_type=ClaimType.QOI_VALUE,
        claim_binding=ClaimBinding(
            subject_kind="qoi",
            subject_ref=name,
            qualifiers={"credibility_report_digest": _report_digest(report)},
        ),
        claim_payload={
            "value": quantity.magnitude,
            "units": str(quantity.units),
        },
        uncertainty=_uncertainty_declaration(
            report, name, discrepancy=discrepancy
        ),
        provenance_ref=report.provenance.run_id,
        domain_pack_ref=domain_pack_ref,
        context_ref=context_ref,
    )


class CredibilityReportCritic:
    """Trusted process critic for levels a credibility report actually attained.

    The critic creates one check per known ValidationLevel. The check name is
    exactly the vocabulary already emitted by obligations_from_charter:
    validation_level:<value>.
    """

    critic_id = "sria.credibility_report"
    critic_version = "critic.credibility_report/1"
    critic_class = CriticClass.PROCESS

    def assess(
        self,
        report: CredibilityEvidenceReport,
        *,
        assessment_id: str,
        mandatory_checks: Iterable[str] = (),
        assessed_at: str | None = None,
    ) -> CriticAssessment:
        if not isinstance(report, CredibilityEvidenceReport):
            raise TypeError("CredibilityReportCritic requires a credibility report")

        mandatory = {str(item) for item in mandatory_checks}
        attained = set(report.attained_levels)
        checks = []
        missing_mandatory = False

        for level in ValidationLevel:
            if level is ValidationLevel.UNVERIFIED:
                continue
            name = f"validation_level:{level.value}"
            ok = level in attained
            is_mandatory = name in mandatory
            missing_mandatory |= is_mandatory and not ok
            checks.append(
                CheckRecord(
                    name=name,
                    outcome=(
                        CriticVerdict.PASS if ok else CriticVerdict.NOT_ASSESSED
                    ),
                    mandatory=is_mandatory,
                    detail=(
                        f"credibility report attained {level.value}"
                        if ok
                        else f"credibility report did not attain {level.value}"
                    ),
                )
            )

        return CriticAssessment(
            assessment_id=assessment_id,
            critic_id=self.critic_id,
            critic_version=self.critic_version,
            critic_class=self.critic_class,
            subject_ref=report.run_id,
            verdict=(
                CriticVerdict.INCONCLUSIVE
                if missing_mandatory
                else CriticVerdict.PASS
            ),
            provenance=AssessmentProvenance(
                assessment_id=assessment_id,
                critic_id=self.critic_id,
                critic_version=self.critic_version,
                inputs_ref=(report.run_id, report.provenance.run_id),
                assessed_at=assessed_at,
                metadata={
                    "evidence_basis": report.evidence_basis,
                    "credibility_verdict": report.verdict.value,
                    "credibility_report_digest": _report_digest(report),
                },
            ),
            checks=tuple(checks),
            summary=(
                f"credibility report exposes {len(attained)} attained "
                "validation/verification level(s)"
            ),
        )
