"""M3B — the critic stack.

Critics are **pure**. Each one reads a result and returns a
:class:`~engcore.sria.assurance.assessment.CriticAssessment`. None of them can
write belief, alter evidence standing, admit anything, or mint an admission
authority. That is not a convention here — critics are given no object capable
of doing any of it, and the tests prove they cannot.

Three critics, deliberately separate rather than one universal one:

* :class:`NumericalCritic` — did the computation compute correctly? Owned by
  SRIA, because convergence, residuals and tolerances are domain-independent.
* :class:`DomainCritic` (protocol) — is the science admissible? Owned by a
  Domain Pack, because only it knows what its models mean.
* :class:`CalibrationCriticAdapter` — are the computational models trustworthy?
  Delegates to the frozen M2 :class:`CalibrationCritic`; it does not
  re-implement any of its logic.

The governing rule across all three: **absence of a diagnostic is never a
pass.** A missing residual gives ``NOT_ASSESSED``, not ``PASS``. This is the
difference between a system that checks things and one that merely fails to
notice problems.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Protocol, runtime_checkable

from ...scientific.results.result import ScientificResult
from ...scientific.results.validation import ValidationOutcome
from ...scientific.solvers.protocol import ConvergenceState
from ..calibration.critic import CalibrationReport, CalibrationVerdict
from ..provenance import AssessmentProvenance
from ..uncertainty import DiscrepancyKind, UncertaintyChannel
from .assessment import (
    CheckRecord,
    FindingImpact,
    CriticAssessment,
    CriticClass,
    CriticVerdict,
    Finding,
    Severity,
    observations_from_budget,
)
from .uncertainty_budget import ChannelState, UncertaintyBudget

NUMERICAL_CRITIC_VERSION = "critic.numerical/1"
CALIBRATION_ADAPTER_VERSION = "critic.calibration_adapter/1"


@runtime_checkable
class Critic(Protocol):
    """Anything that assesses. Returns evidence; changes nothing."""

    critic_id: str
    critic_version: str
    critic_class: CriticClass

    def assess(self, *args: Any, **kwargs: Any) -> CriticAssessment:
        ...


# =====================================================================
# Numerical critic
# =====================================================================

class NumericalCritic:
    """Computational trust: did the numbers come out of a sound computation?

    Mandatory checks are declared by the caller (ultimately by the campaign
    charter), not hard-coded here — a global list of required checks would be
    exactly the "arbitrary universal threshold" the architecture forbids.
    What is fixed is the *semantics*: a mandatory check with no evidence is
    ``NOT_ASSESSED`` and the whole assessment degrades accordingly.
    """

    critic_id = "sria.numerical"
    critic_version = NUMERICAL_CRITIC_VERSION
    critic_class = CriticClass.NUMERICAL

    #: Checks this critic knows how to perform.
    KNOWN_CHECKS = (
        "solver_termination",
        "convergence_state",
        "residual_evidence",
        "validation_report_status",
        "numerical_uncertainty_declared",
        "completion_not_censored",
        "failure_attribution",
    )

    def assess(
        self,
        result: ScientificResult,
        *,
        assessment_id: str,
        budget: UncertaintyBudget | None = None,
        mandatory_checks: Iterable[str] = (),
        run_outcome: Any | None = None,
        assessed_at: str | None = None,
    ) -> CriticAssessment:
        mandatory = {str(c) for c in mandatory_checks}
        unknown_requested = sorted(mandatory - set(self.KNOWN_CHECKS))
        checks: list[CheckRecord] = []
        findings: list[Finding] = []
        skipped: list[str] = []

        def add(name: str, outcome: CriticVerdict, detail: str = "", **kw: Any) -> None:
            checks.append(
                CheckRecord(
                    name=name,
                    outcome=outcome,
                    mandatory=name in mandatory,
                    detail=detail,
                    **kw,
                )
            )

        # A required check this critic cannot perform must not disappear.
        for name in unknown_requested:
            checks.append(
                CheckRecord(
                    name=name,
                    outcome=CriticVerdict.NOT_ASSESSED,
                    mandatory=True,
                    detail="requested check is not implemented by this critic",
                )
            )
            findings.append(
                Finding(
                    code="numerical.check_unavailable",
                    severity=Severity.MAJOR,
                    category="coverage",
                    message=f"mandatory check {name!r} is not implemented",
                    check_name=name,
                )
            )

        # --- convergence ------------------------------------------------
        state = result.convergence
        if state is ConvergenceState.CONVERGED:
            add("convergence_state", CriticVerdict.PASS, "solver reported converged")
        elif state is ConvergenceState.NOT_APPLICABLE:
            add(
                "convergence_state",
                CriticVerdict.PASS,
                "convergence not applicable to this solve",
            )
        elif state is ConvergenceState.FAILED:
            add("convergence_state", CriticVerdict.FAIL, "solver reported FAILED")
            findings.append(
                Finding(
                    code="numerical.solver_failed",
                    severity=Severity.BLOCKING,
                    impact=FindingImpact.EVIDENCE_INVALIDATING,
                    category="convergence",
                    message="solver did not produce a converged solution",
                    check_name="convergence_state",
                )
            )
        else:
            add(
                "convergence_state",
                CriticVerdict.FAIL,
                f"solver reported {state.value}",
            )
            findings.append(
                Finding(
                    code="numerical.not_converged",
                    severity=Severity.BLOCKING,
                    impact=FindingImpact.EVIDENCE_INVALIDATING,
                    category="convergence",
                    message=f"convergence state {state.value}",
                    check_name="convergence_state",
                )
            )

        add(
            "solver_termination",
            CriticVerdict.PASS if result.solver is not None else CriticVerdict.NOT_ASSESSED,
            "solver identity recorded" if result.solver else "no solver identity recorded",
        )
        if result.solver is None:
            skipped.append("solver_termination")

        # --- residual evidence -------------------------------------------
        residual_checks = [
            c for c in result.validation.checks if c.residual is not None
        ]
        if residual_checks:
            worst = max(residual_checks, key=lambda c: c.residual or 0.0)
            passed = all(
                c.outcome is not ValidationOutcome.FAIL for c in residual_checks
            )
            add(
                "residual_evidence",
                CriticVerdict.PASS if passed else CriticVerdict.FAIL,
                f"{len(residual_checks)} residual check(s) recorded",
                observed=worst.residual,
                threshold=worst.tolerance,
                threshold_source="domain validation settings (recorded in provenance)",
            )
            if not passed:
                findings.append(
                    Finding(
                        code="numerical.residual_failed",
                        severity=Severity.BLOCKING,
                        impact=FindingImpact.EVIDENCE_INVALIDATING,
                        category="residual",
                        message="a residual check failed",
                        check_name="residual_evidence",
                    )
                )
        else:
            # The single most important line in this class: no residual is not
            # a pass.
            add(
                "residual_evidence",
                CriticVerdict.NOT_ASSESSED,
                "no residual diagnostic present in the validation report",
            )
            skipped.append("residual_evidence")
            findings.append(
                Finding(
                    code="numerical.residual_missing",
                    severity=(
                        Severity.MAJOR
                        if "residual_evidence" in mandatory
                        else Severity.ADVISORY
                    ),
                    category="residual",
                    message="no residual evidence was recorded",
                    check_name="residual_evidence",
                )
            )

        # --- validation report status -------------------------------------
        status = result.validation.status
        if status is ValidationOutcome.FAIL:
            add("validation_report_status", CriticVerdict.FAIL, "a check failed")
            findings.append(
                Finding(
                    code="numerical.validation_failed",
                    severity=Severity.BLOCKING,
                    impact=FindingImpact.EVIDENCE_INVALIDATING,
                    category="validation",
                    message="validation report contains a failing check",
                    check_name="validation_report_status",
                )
            )
        elif status is ValidationOutcome.NOT_RUN:
            add(
                "validation_report_status",
                CriticVerdict.NOT_ASSESSED,
                "validation was never run",
            )
            skipped.append("validation_report_status")
        else:
            add("validation_report_status", CriticVerdict.PASS, status.value)

        # --- numerical uncertainty ----------------------------------------
        if budget is None:
            add(
                "numerical_uncertainty_declared",
                CriticVerdict.NOT_ASSESSED,
                "no uncertainty budget supplied",
            )
            skipped.append("numerical_uncertainty_declared")
        else:
            entry = budget.entry(UncertaintyChannel.NUMERICAL)
            if entry.is_quantified:
                add(
                    "numerical_uncertainty_declared",
                    CriticVerdict.PASS,
                    f"numerical channel is {entry.state.value}",
                )
            elif entry.state is ChannelState.NOT_APPLICABLE:
                add(
                    "numerical_uncertainty_declared",
                    CriticVerdict.PASS,
                    f"declared not applicable: {entry.rationale}",
                )
            else:
                add(
                    "numerical_uncertainty_declared",
                    CriticVerdict.NOT_ASSESSED,
                    "numerical uncertainty is UNKNOWN",
                )
                findings.append(
                    Finding(
                        code="numerical.uncertainty_unknown",
                        severity=(
                            Severity.MAJOR
                            if "numerical_uncertainty_declared" in mandatory
                            else Severity.ADVISORY
                        ),
                        category="uncertainty",
                        message="numerical uncertainty was not quantified",
                        check_name="numerical_uncertainty_declared",
                    )
                )

        # --- censoring / completion / attribution --------------------------
        if run_outcome is None:
            add(
                "completion_not_censored",
                CriticVerdict.NOT_ASSESSED,
                "no run outcome supplied",
            )
            add("failure_attribution", CriticVerdict.NOT_ASSESSED, "no run outcome")
            skipped.extend(["completion_not_censored", "failure_attribution"])
        else:
            censored = bool(getattr(run_outcome, "is_censored", False))
            fraction = float(getattr(run_outcome, "completion_fraction", 1.0))
            add(
                "completion_not_censored",
                CriticVerdict.FAIL if censored else CriticVerdict.PASS,
                f"censoring={getattr(run_outcome, 'censoring_type', None)} "
                f"completion={fraction}",
                observed=fraction,
            )
            if censored:
                findings.append(
                    Finding(
                        code="numerical.censored_run",
                        severity=Severity.BLOCKING,
                        impact=FindingImpact.ASSURANCE_BLOCKING,
                        category="completion",
                        message="run was truncated; results are partial",
                        check_name="completion_not_censored",
                    )
                )
            cause = getattr(run_outcome, "attributed_cause", None)
            add(
                "failure_attribution",
                CriticVerdict.PASS,
                f"attributed cause {getattr(cause, 'value', cause)}",
            )

        verdict = self._verdict(checks, findings)
        return CriticAssessment(
            assessment_id=assessment_id,
            critic_id=self.critic_id,
            critic_version=self.critic_version,
            critic_class=self.critic_class,
            subject_ref=result.result_id,
            verdict=verdict,
            provenance=AssessmentProvenance(
                assessment_id=assessment_id,
                critic_id=self.critic_id,
                critic_version=self.critic_version,
                inputs_ref=(result.result_id, result.provenance.run_id),
                assessed_at=assessed_at,
            ),
            checks=tuple(checks),
            checks_skipped=tuple(sorted(set(skipped))),
            findings=tuple(findings),
            uncertainty_observations=(
                observations_from_budget(budget) if budget is not None else ()
            ),
            summary=f"numerical assessment: {verdict.value}",
        )

    @staticmethod
    def _verdict(
        checks: list[CheckRecord], findings: list[Finding]
    ) -> CriticVerdict:
        """Severity contract: BLOCKING means something *failed*.

        Absence of evidence is never BLOCKING — it is MAJOR at most, and it
        routes through the mandatory-NOT_ASSESSED rule below. Conflating the
        two would turn "we could not check" into "the check failed", which
        loses exactly the distinction M3 exists to preserve.
        """
        if any(c.outcome is CriticVerdict.FAIL for c in checks):
            return CriticVerdict.FAIL
        if any(f.severity is Severity.BLOCKING for f in findings):
            return CriticVerdict.FAIL
        # A mandatory check that could not be evaluated is NOT_ASSESSED, and
        # that must not round up to PASS.
        if any(
            c.mandatory and c.outcome is CriticVerdict.NOT_ASSESSED for c in checks
        ):
            return CriticVerdict.NOT_ASSESSED
        # Any other mandatory check that did not pass (e.g. INCONCLUSIVE) also
        # prevents PASS — CriticAssessment refuses the inconsistent combination
        # anyway, and silently reporting PASS here would be the bug it catches.
        if any(c.blocks_valid for c in checks):
            return CriticVerdict.INCONCLUSIVE
        if any(c.outcome is CriticVerdict.NOT_ASSESSED for c in checks):
            return CriticVerdict.INCONCLUSIVE
        return CriticVerdict.PASS


# =====================================================================
# Domain critic contract
# =====================================================================

@runtime_checkable
class DomainCritic(Protocol):
    """Scientific validity, owned by a Domain Pack.

    The generic core deliberately cannot implement this. Scope validity,
    physical constraints, conservation bounds, reference obligations and QoI
    semantics all require knowing what the numbers mean, and that knowledge
    belongs to the pack that defined the models.

    A domain critic returns an assessment and nothing else — same purity rule
    as every other critic.
    """

    critic_id: str
    critic_version: str
    domain_pack_ref: str

    def assess_domain(
        self,
        result: ScientificResult,
        *,
        assessment_id: str,
        budget: UncertaintyBudget | None = None,
        mandatory_checks: Iterable[str] = (),
    ) -> CriticAssessment:
        ...


#: Domain-critic concerns the Arbiter may require by name. The *names* are
#: shared vocabulary; the *implementations* and thresholds belong to packs.
DOMAIN_CHECK_VOCABULARY = (
    "scope_validity",
    "assumptions_satisfied",
    "physical_constraints",
    "conservation_bounds",
    "reference_obligation",
    "model_discrepancy_supported",
    "qoi_semantics",
)


def model_discrepancy_check(
    budget: UncertaintyBudget,
    *,
    supported_by: str = "",
    contradicted_by: str = "",
    mandatory: bool = False,
) -> tuple[CheckRecord, tuple[Finding, ...]]:
    """Shared helper: is a ZERO_DECLARED discrepancy actually supported?

    ``ZERO_DECLARED`` never means "the model is known to be exact". It means
    this campaign chose to model discrepancy as zero.

    M3.1 separates two very different situations:

    * **unsupported** — nothing backs the assumption. That blocks
      certification (INCONCLUSIVE); it does not disprove anything. An
      unexamined assumption is not a refuted one.
    * **contradicted** — evidence actually conflicts with zero discrepancy.
      That is evidence-backed and may support INVALID.
    """
    if str(contradicted_by).strip():
        return (
            CheckRecord(
                name="model_discrepancy_supported",
                outcome=CriticVerdict.FAIL,
                mandatory=mandatory,
                detail=f"zero discrepancy contradicted by {contradicted_by}",
            ),
            (
                Finding(
                    code="domain.zero_discrepancy_contradicted",
                    severity=Severity.BLOCKING,
                    impact=FindingImpact.EVIDENCE_INVALIDATING,
                    category="model_form",
                    message=(
                        f"evidence contradicts the zero-discrepancy assumption: "
                        f"{contradicted_by}"
                    ),
                    check_name="model_discrepancy_supported",
                ),
            ),
        )
    discrepancy = budget.model_discrepancy
    if discrepancy.kind is DiscrepancyKind.CONSTRAINED_PRIOR:
        return (
            CheckRecord(
                name="model_discrepancy_supported",
                outcome=CriticVerdict.PASS,
                mandatory=mandatory,
                detail=f"constrained prior: {discrepancy.reference}",
            ),
            (),
        )

    # ZERO_DECLARED
    if str(supported_by).strip():
        return (
            CheckRecord(
                name="model_discrepancy_supported",
                outcome=CriticVerdict.PASS,
                mandatory=mandatory,
                detail=f"zero discrepancy supported by {supported_by}",
            ),
            (
                Finding(
                    code="domain.zero_discrepancy_declared",
                    severity=Severity.INFO,
                    category="model_form",
                    message=(
                        "model-form discrepancy is declared zero; this is a "
                        f"campaign choice supported by {supported_by}, not a "
                        f"proof the model is exact"
                    ),
                    check_name="model_discrepancy_supported",
                ),
            ),
        )

    return (
        CheckRecord(
            name="model_discrepancy_supported",
            outcome=CriticVerdict.INCONCLUSIVE,
            mandatory=mandatory,
            detail="ZERO_DECLARED discrepancy with no supporting evidence",
        ),
        (
            Finding(
                code="domain.zero_discrepancy_unsupported",
                severity=Severity.MAJOR,
                impact=FindingImpact.ASSURANCE_BLOCKING,
                category="model_form",
                message=(
                    "model-form discrepancy is declared zero with nothing "
                    "supporting it; ZERO_DECLARED asserts a modelling choice, "
                    "never that the model is exact"
                ),
                check_name="model_discrepancy_supported",
            ),
        ),
    )


# =====================================================================
# Calibration critic integration (reuse, never duplicate)
# =====================================================================

class CalibrationCriticAdapter:
    """Brings the frozen M2 calibration verdict into scientific assurance.

    It re-implements none of M2's logic — it consumes a
    :class:`~engcore.sria.calibration.critic.CalibrationReport` and translates
    it into the assurance vocabulary.

    The point of this adapter is propagation: a DEGRADED or UNTRUSTED cost or
    failure model must reach the Arbiter *even when the solver succeeded*. A
    perfect solve using an untrustworthy calibration is still a result whose
    predicted cost or risk cannot be relied on, and hiding that behind a green
    solver status is precisely the failure mode M2.1 closed for censoring.
    """

    critic_id = "sria.calibration_adapter"
    critic_version = CALIBRATION_ADAPTER_VERSION
    critic_class = CriticClass.CALIBRATION

    #: Assurance meaning of each frozen M2 verdict. INSUFFICIENT_DATA stays
    #: distinct from UNTRUSTED: "could not judge" is not "judged and bad".
    VERDICT_MAP: Mapping[CalibrationVerdict, CriticVerdict] = {
        CalibrationVerdict.TRUSTED: CriticVerdict.PASS,
        CalibrationVerdict.DEGRADED: CriticVerdict.INCONCLUSIVE,
        CalibrationVerdict.UNTRUSTED: CriticVerdict.FAIL,
        CalibrationVerdict.INSUFFICIENT_DATA: CriticVerdict.NOT_ASSESSED,
    }

    def assess(
        self,
        reports: Iterable[CalibrationReport],
        *,
        assessment_id: str,
        subject_ref: str,
        required_verdicts: Iterable[CalibrationVerdict] = (),
        assessed_at: str | None = None,
    ) -> CriticAssessment:
        reports = tuple(reports)
        required = {CalibrationVerdict(v) for v in required_verdicts}
        checks: list[CheckRecord] = []
        findings: list[Finding] = []

        if not reports:
            checks.append(
                CheckRecord(
                    name="calibration_available",
                    outcome=CriticVerdict.NOT_ASSESSED,
                    mandatory=bool(required),
                    detail="no calibration reports supplied",
                )
            )
            return self._finish(
                assessment_id, subject_ref, checks, findings, (), assessed_at
            )

        for report in reports:
            mapped = self.VERDICT_MAP[report.verdict]
            satisfies = (not required) or (report.verdict in required)
            outcome = mapped if satisfies else CriticVerdict.FAIL
            checks.append(
                CheckRecord(
                    name=f"calibration:{report.model_id}",
                    outcome=outcome,
                    mandatory=bool(required),
                    detail=(
                        f"{report.model_version} -> {report.verdict.value}"
                        + ("" if satisfies else "; charter requires "
                           f"{sorted(v.value for v in required)}")
                    ),
                    threshold_source="campaign charter validation obligation"
                    if required
                    else "",
                )
            )
            if report.verdict is CalibrationVerdict.UNTRUSTED:
                findings.append(
                    Finding(
                        code="calibration.untrusted",
                        severity=Severity.BLOCKING if required else Severity.MAJOR,
                        impact=FindingImpact.ASSURANCE_BLOCKING,
                        category="calibration",
                        message=(
                            f"model {report.model_id} is UNTRUSTED; a successful "
                            f"solve does not make an untrusted calibration usable"
                        ),
                        check_name=f"calibration:{report.model_id}",
                    )
                )
            elif report.verdict is CalibrationVerdict.DEGRADED:
                findings.append(
                    Finding(
                        code="calibration.degraded",
                        severity=Severity.BLOCKING if required else Severity.ADVISORY,
                        impact=FindingImpact.ASSURANCE_BLOCKING,
                        category="calibration",
                        message=f"model {report.model_id} is DEGRADED",
                        check_name=f"calibration:{report.model_id}",
                    )
                )
            elif report.verdict is CalibrationVerdict.INSUFFICIENT_DATA:
                findings.append(
                    Finding(
                        code="calibration.insufficient_data",
                        severity=Severity.BLOCKING if required else Severity.ADVISORY,
                        impact=FindingImpact.ASSURANCE_BLOCKING,
                        category="calibration",
                        message=(
                            f"model {report.model_id} has INSUFFICIENT_DATA — "
                            f"distinct from untrusted: it could not be judged"
                        ),
                        check_name=f"calibration:{report.model_id}",
                    )
                )

        return self._finish(
            assessment_id, subject_ref, checks, findings, reports, assessed_at
        )

    def _finish(
        self,
        assessment_id: str,
        subject_ref: str,
        checks: list[CheckRecord],
        findings: list[Finding],
        reports: tuple[CalibrationReport, ...],
        assessed_at: str | None,
    ) -> CriticAssessment:
        verdict = NumericalCritic._verdict(checks, findings)
        return CriticAssessment(
            assessment_id=assessment_id,
            critic_id=self.critic_id,
            critic_version=self.critic_version,
            critic_class=self.critic_class,
            subject_ref=subject_ref,
            verdict=verdict,
            provenance=AssessmentProvenance(
                assessment_id=assessment_id,
                critic_id=self.critic_id,
                critic_version=self.critic_version,
                inputs_ref=tuple(r.model_id for r in reports),
                assessed_at=assessed_at,
            ),
            checks=tuple(checks),
            checks_skipped=tuple(
                c.name for c in checks if c.outcome is CriticVerdict.NOT_ASSESSED
            ),
            findings=tuple(findings),
            summary=f"calibration assessment: {verdict.value}",
        )
