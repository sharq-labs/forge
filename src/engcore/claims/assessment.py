"""CORE-10 -- generic claim assessment: from a structured claim to an auditable verdict.

    compile_claim  ->  plan_experiment  ->  execute_plan  ->  assemble_evidence
                   ->  assure  ->  compare  ->  derive_claim_verdict  ->  explain

The caller names **no system, no case, no quantity key, no report index**: the
claim's structured requirements route it (:mod:`.compiler`), the plan fixes
exactly what runs (:mod:`.planning`), and every later step reuses the existing
authority for its part --

* the run's credibility is the :class:`~engcore.mcp.evidence.CredibilityEvidenceReport`
  verdict, derived by the Core's own rules;
* SRIA evidence is made by :func:`~engcore.mcp.sria_bridge.evidence_from_credibility_report`,
  which takes the value from the report and never from the caller, under the
  plan's context reference ``charter:<digest>#decision:<id>``;
* evidentiary levels are awarded only by the issuer-gated
  :class:`~engcore.mcp.sria_bridge.CredibilityReportCritic` through the
  :class:`~engcore.sria.assurance.Arbiter`, against obligations derived from the
  plan's charter -- including one per demanded uncertainty channel;
* a demanded discrepancy is judged by SRIA's own ``model_discrepancy_check``;
* the claim verdict is :func:`~engcore.claims.verdict.derive_claim_verdict`.

The result is a :class:`ClaimAssessment` whose serialized record answers: what
was assessed, how it was modeled, why that model applied or not, what ran,
which checks ran, what evidence was attained, what uncertainty is known and
unknown, whether the evidence supports the claim, what prevents a conclusion,
and what would repair it. :func:`verify_assessment` reads such a record back and
re-derives all of it; a record whose verdict, value, levels, uncertainty or
context was edited is refused.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from ..credibility.evidence import CredibilityEvidenceReport
from ..credibility.sria_bridge import CredibilityReportCritic, evidence_from_credibility_report
from ..scientific.results.validation import VALIDATION_LEVELS, VERIFICATION_LEVELS, ValidationLevel
from ..scientific.serialization import schema_string
from ..sria.assurance import (
    Arbiter,
    CriticClass,
    budget_from_declaration,
    model_discrepancy_check,
    obligations_from_charter,
    trusting_authority,
)
from ..sria.assurance.assessment import CriticVerdict
from ._records import assessment_record_digest, canonical_json, require_mapping, tagged_digest
from .capabilities import CapabilityRegistry
from .compiler import CompilationStatus, CompiledClaim, compile_claim
from .context import context_problems
from .contract import ScientificClaim
from .errors import ClaimLayerError
from .execution import ExecutionOutcome, PlanExecution, binding_problems, execute_plan
from .explanation import ExplanationItem, ExplanationKind, explain
from .planning import ExperimentPlan, PlanningError, plan_experiment, verify_plan
from .repair import RepairAction, RepairKind, merge_repairs
from .external_evidence import (
    PRODUCTION_EXTERNAL_REGISTRY,
    LiteratureRecord,
    MeasurementRecord,
    TrustedExternalRegistry,
    _half_widths,
    assess_benchmark,
    assess_literature,
    assess_measurement,
    read_external_record,
)
from .oracles import discover_oracles
from .measurement_dataset import DatasetObservation
from ..uq.model_form.qualification import ProducerQualification
from .model_form_trust import (
    ModelFormQualificationRegistry,
    PRODUCTION_MODEL_FORM_QUALIFICATIONS,
)
from .empirical_uq_trust import (
    EmpiricalObservationRegistry,
    PRODUCTION_EMPIRICAL_OBSERVATIONS,
)
from .gaps import analyze_gaps
from .next_experiment import recommend_next
from .policy import derive_requirement, policy_findings
from .selection import concrete
from .sources import gather_evidence
from .uncertainty import report_transport
from .uq_studies import (
    StudyOutcome,
    UncertaintyStudyError,
    planned_studies,
    run_uncertainty_studies,
    verify_study_records,
)
from .verdict import ClaimComparison, ClaimVerdict, VerdictBasis, admissible, compare, derive_claim_verdict

ASSESSMENT_SCHEMA = schema_string("claim_assessment_record")
_TAG = "crafty.claims.assessment/1"


class AssessmentForgeryError(ClaimLayerError):
    """A serialized assessment does not re-derive from what it carries."""


@dataclass(frozen=True)
class AssembledEvidence:
    evidence: Any | None
    problem: str | None


@dataclass(frozen=True)
class Assurance:
    decision: Any
    obligations: Any
    discrepancy_check: Any | None

    def to_dict(self, plan: ExperimentPlan) -> dict[str, Any]:
        check = self.discrepancy_check
        return {
            "verdict": self.decision.verdict.value,
            "decision_id": self.decision.decision_id,
            "charter_digest": plan.charter_digest,
            "unmet_obligations": sorted(self.decision.unmet_obligations),
            "reasons": list(self.decision.reasons),
            "refused_assessments": list(self.decision.refused_assessments),
            "obligations": [r.to_dict() for r in self.decision.obligation_results],
            "discrepancy_check": None
            if check is None
            else {"outcome": check.outcome.value, "detail": check.detail},
        }


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


def assemble_evidence(
    plan: ExperimentPlan,
    claim: ScientificClaim,
    report: CredibilityEvidenceReport,
    studies: StudyOutcome | None = None,
) -> AssembledEvidence:
    """SRIA evidence for the claim's quantity, bound to the plan's context. The value is the report's.

    ``studies`` adds the channel records the plan's uncertainty studies
    quantified (never an UNKNOWN one), and names every run they executed.
    """
    channel_records = {} if studies is None else dict(studies.channel_records)
    study_refs = () if studies is None else tuple(
        f"run:{run['run_id']}" for record in studies.records for run in record["runs"]
    )
    try:
        evidence = evidence_from_credibility_report(
            report,
            quantity_name=claim.qoi.name,
            evidence_id=f"claim:{plan.run_id}:{claim.qoi.name}",
            domain_pack_ref=f"capability:{plan.capability_id}@{plan.content['capability']['version']}",
            context_ref=plan.context_ref,
            discrepancy=claim.discrepancy,
            # A quantified record that names no single channel (UNSPECIFIED or
            # COMBINED) is filed under none and every channel stays UNKNOWN --
            # stated in the declaration, never guessed into a channel, never zero.
            unattributable_uncertainty="unknown",
            channel_records=channel_records,
            study_refs=study_refs,
        )
    except ValueError as exc:  # pragma: no cover - the bridge's remaining refusals
        return AssembledEvidence(None, str(exc))
    return AssembledEvidence(evidence, None)


def assure(plan: ExperimentPlan, claim: ScientificClaim, evidence: Any, report: CredibilityEvidenceReport) -> Assurance:
    """The SRIA decision over the evidence, under the plan's own charter."""
    obligations = obligations_from_charter(
        plan.charter,
        required_critics=(CriticClass.PROCESS,),
        required_uncertainty_channels=claim.uncertainty.ordered_channels(),
        context_decision_id=plan.decision_id,
    )
    critic = CredibilityReportCritic()
    authority = trusting_authority(f"claims-authority:{plan.capability_id}", critics=(critic,), policies=(obligations,))
    arbiter = Arbiter(authority, critics=(critic,))
    mandatory = tuple(o.target for o in obligations.obligations if o.target.startswith("validation_level:"))
    assessment = arbiter.run_critic(
        critic.critic_id,
        report,
        subject=evidence,
        assessment_id=f"credibility:{report.run_id}:{claim.qoi.name}",
        mandatory_checks=mandatory,
    )
    budget = budget_from_declaration(evidence.claim_binding.key, evidence.uncertainty)
    decision = arbiter.decide(
        decision_id=f"assess:{plan.decision_id}",
        evidence=evidence,
        assessments=(assessment,),
        obligations=obligations,
        budget=budget if claim.uncertainty.demands_quantification else None,
    )
    discrepancy = None
    if claim.uncertainty.require_supported_discrepancy:
        discrepancy, _findings = model_discrepancy_check(budget, mandatory=True)
    return Assurance(decision, obligations, discrepancy)


def _instance_index(plan: ExperimentPlan, claim: ScientificClaim, registry: CapabilityRegistry) -> int | None:
    produced = registry.get(plan.capability_id).produced(claim.qoi.name)
    if produced.instance_path is None:
        return None
    head = produced.instance_path.split("[]")[0]
    for path, value in claim.supplied_inputs.items():
        if path.startswith(head + "[") and path.endswith(produced.instance_path.split("[]")[-1]) and value == plan.instance:
            return int(path[len(head) + 1 : path.index("]")])
    return 0


def _post_execution_repairs(
    plan: ExperimentPlan,
    claim: ScientificClaim,
    registry: CapabilityRegistry,
    report: CredibilityEvidenceReport,
    execution: Mapping[str, Any],
    comparison: ClaimComparison | None,
    assurance: Assurance | None,
) -> list[RepairAction]:
    """What would repair what the run itself revealed -- from declarations and the domain's own hints."""
    declaration = registry.get(plan.capability_id)
    source = f"capability:{declaration.capability_id}"
    supplied = claim.supplied_inputs
    index = _instance_index(plan, claim, registry)
    repairs: list[RepairAction] = []
    for record in report.validity:
        model = declaration.model(record.model_id)
        if model is None:
            continue
        at = index if model.instance_section is not None else None
        for unknown in record.assessment.unknown_reasons:
            if unknown.reason.value != "not_supplied":
                continue
            for item in declaration.inputs:
                if item.model_id != record.model_id:
                    continue
                if unknown.name not in item.unlocks_conditions and item.model_input != unknown.name:
                    continue
                path = concrete(item.path, at if item.array_section == model.instance_section else None)
                if path in supplied:
                    continue
                repairs.append(
                    RepairAction(
                        RepairKind.SUPPLY_VALIDITY_EVIDENCE,
                        path,
                        item.description or f"unlocks {unknown.name}",
                        required_for=(f"model:{record.model_id}#condition:{unknown.name}",),
                        alternatives=tuple(concrete(a, at if "[]" in a else None) for a in item.alternative_to),
                        source=f"{source}#input:{item.path}",
                        detail={"observed_unknown": True, "unit_exemplar": item.unit_exemplar},
                    )
                )
    for instance, hint in execution.get("condition_repairs", ()):
        if instance not in (None, plan.instance):
            continue
        repairs.append(
            RepairAction(
                RepairKind.MOVE_INSIDE_VALIDITY,
                f"{hint.get('model_id')}#{hint.get('condition')}",
                "the domain's exact inversion of the violated condition, holding every other declaration fixed",
                required_for=(f"model:{hint.get('model_id')}",),
                source=f"domain_repair:{hint.get('model_id')}#{hint.get('condition')}",
                detail=dict(hint),
            )
        )
    attained = set(report.attained_levels)
    for level in claim.evidence.required_levels:
        if level not in attained:
            repairs.append(
                RepairAction(
                    RepairKind.PROVIDE_EVIDENCE,
                    level.value,
                    "the decision requires this level and the run did not attain it",
                    required_for=(f"decision:{claim.decision.decision_id}",),
                    source=f"{source}#attainable_levels",
                    detail={"attainable": [a.to_dict() for a in declaration.attainable_levels]},
                )
            )
    if comparison is not None:
        for use in comparison.channels:
            if not use.usable:
                repairs.append(
                    RepairAction(
                        RepairKind.PROVIDE_UNCERTAINTY,
                        use.channel.value,
                        use.reason,
                        required_for=(f"decision:{claim.decision.decision_id}",),
                        source=f"{source}#uncertainty",
                        detail={"basis": declaration.uncertainty.basis},
                    )
                )
    if assurance is not None and assurance.discrepancy_check is not None and assurance.discrepancy_check.outcome is not CriticVerdict.PASS:
        repairs.append(
            RepairAction(
                RepairKind.SUPPORT_DISCREPANCY,
                "discrepancy",
                assurance.discrepancy_check.detail,
                required_for=(f"decision:{claim.decision.decision_id}",),
                source="sria:model_discrepancy_check",
                detail={"declared": claim.discrepancy.to_dict()},
            )
        )
    return repairs


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------


def _levels(levels, family) -> list[str]:
    return sorted((l.value for l in levels if l in family), key=lambda v: list(ValidationLevel).index(ValidationLevel(v)))


def _reasons(basis: VerdictBasis, verdict: ClaimVerdict, record: Mapping[str, Any]) -> list[dict[str, str]]:
    """Why this verdict: the admissibility conditions that failed, or the comparison that decided."""
    out: list[dict[str, str]] = []
    if not basis.ready:
        out.append({"reason": f"the claim is {record['compilation']['status']}, not ready to execute", "source": "/compilation/status"})
    elif not basis.executed:
        out.append({"reason": "the system refused the planned case", "source": "/execution/failure"})
    elif not basis.bound:
        out.append({"reason": "the report is not bound to the plan", "source": "/execution/binding_problems"})
    else:
        if basis.credibility != "supported":
            out.append({"reason": f"the run's credibility report is {basis.credibility}", "source": "/credibility/verdict"})
        if basis.assurance is None:
            out.append({"reason": "no SRIA evidence could be made from the report", "source": "/uncertainty/evidence_problem"})
        elif basis.assurance != "valid":
            out.append({"reason": f"the assurance decision is {basis.assurance}", "source": "/assurance/verdict"})
        if basis.discrepancy_supported is False:
            out.append({"reason": "the demanded model-form discrepancy is not supported", "source": "/assurance/discrepancy_check"})
        if basis.policy_satisfied is False:
            out.append({"reason": "the decision's evidence policy is not met", "source": "/policy/findings"})
    if admissible(basis):
        out.append({"reason": f"admissible evidence: the comparison is {basis.comparison.value}", "source": "/comparison/outcome"})
    return out


def _simulated_interval(report: Any, evidence: Any, qoi: str) -> tuple[Any, tuple[float, float] | None] | None:
    """The claim's value with the linear sum of its quantified INTERVAL channels (None when any is not one)."""
    if report is None or qoi not in report.values:
        return None
    value = report.values[qoi]
    if evidence is None or not evidence.uncertainty.channels:
        return value, None
    lo = hi = 0.0
    for record in evidence.uncertainty.channels.values():
        halves = _half_widths(record, value)
        if halves is None:
            return value, None
        lo, hi = lo + halves[0], hi + halves[1]
    return value, (lo, hi)


def _external_assessments(claim, plan, report, evidence, oracles, offered, trust) -> tuple[Any, ...]:
    """Benchmark evidence from every discovered oracle, and every offered record, each given its standing."""
    if claim is None or plan is None:
        return ()
    simulated = _simulated_interval(report, evidence, claim.qoi.name)
    out = [assess_benchmark(m, claim, context_ref=plan.context_ref, simulated=simulated) for m in oracles]
    for item in offered:
        if isinstance(item, MeasurementRecord):
            out.append(assess_measurement(item, claim, context_ref=plan.context_ref, trust=trust, simulated=simulated))
        elif isinstance(item, LiteratureRecord):
            out.append(assess_literature(item, claim, context_ref=plan.context_ref, trust=trust, simulated=simulated))
        else:
            raise TypeError(f"external evidence must be a MeasurementRecord or LiteratureRecord, got {type(item).__name__}")
    return tuple(out)


def _build_record(
    claim: ScientificClaim | None,
    compiled: CompiledClaim,
    plan: ExperimentPlan | None,
    execution: Mapping[str, Any] | None,
    report: CredibilityEvidenceReport | None,
    registry: CapabilityRegistry,
    studies: StudyOutcome | None = None,
    external: tuple[Any, ...] = (),
    trust: TrustedExternalRegistry = PRODUCTION_EXTERNAL_REGISTRY,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The assessment record, and the live objects it was built from."""
    live: dict[str, Any] = {}
    ready = compiled.status is CompilationStatus.READY
    executed = execution is not None and execution["outcome"] == ExecutionOutcome.COMPLETED.value
    bound = executed and report is not None and not execution["binding_problems"]
    evidence = assurance = comparison = None
    evidence_problem = None
    context = ()
    if bound:
        assembled = assemble_evidence(plan, claim, report, studies)
        evidence, evidence_problem = assembled.evidence, assembled.problem
        if evidence is not None:
            # CORE-9: evidence counts only for the context it was made for.
            context = context_problems(evidence, plan, report)
            if context:
                evidence_problem = "; ".join(context)
                evidence = None
        if evidence is not None:
            assurance = assure(plan, claim, evidence, report)
            channels = dict(evidence.uncertainty.channels)
        else:
            channels = {}
        comparison = compare(claim, report.values[claim.qoi.name], compiled.target, channels)
    bound = bound and not context
    live.update(evidence=evidence, assurance=assurance, comparison=comparison)
    oracles = () if claim is None else discover_oracles(registry, qoi=claim.qoi.name, context=claim.supplied_inputs)
    external_assessments = _external_assessments(claim, plan, report, evidence, oracles, external, trust)
    live["external"] = external_assessments
    sources = gather_evidence({
        "simulation_evidence": evidence,
        "simulation_problem": evidence_problem,
        "external_assessments": external_assessments,
    })

    # Phase 3: the requirements the decision's policy adds that a claim cannot state are read off the
    # run's own records. The policy grants nothing: it can only withhold admissibility.
    policy_record = None
    policy_satisfied = None
    if claim is not None and claim.decision_context is not None:
        requirement = derive_requirement(claim.decision_context)
        findings = policy_findings(requirement, plan, report) if bound and report is not None else []
        policy_satisfied = (not findings) if bound else None
        policy_record = {
            "requirement": requirement.to_dict(),
            "requirement_digest": requirement.digest,
            "evaluated": bound,
            "findings": findings,
            "satisfied": policy_satisfied,
        }
    basis = VerdictBasis(
        policy_satisfied=policy_satisfied,
        ready=ready,
        executed=executed,
        bound=bound,
        credibility=None if report is None else report.verdict.value,
        assurance=None if assurance is None else assurance.decision.verdict.value,
        discrepancy_supported=None
        if claim is None or not claim.uncertainty.require_supported_discrepancy
        else (assurance is not None and assurance.discrepancy_check is not None and assurance.discrepancy_check.outcome is CriticVerdict.PASS),
        comparison=None if comparison is None else comparison.outcome,
    )
    verdict = derive_claim_verdict(basis)

    repairs = list(compiled.repairs)
    for finding in policy_record["findings"] if policy_record is not None else ():
        repairs.append(
            RepairAction(
                RepairKind.PROVIDE_EVIDENCE,
                finding["requirement"],
                finding["reason"],
                required_for=(f"decision:{claim.decision.decision_id}",),
                source=f"policy:{policy_record['requirement']['profile_id']}@{policy_record['requirement']['profile_version']}",
                detail={"risk_class": policy_record["requirement"]["risk_class"]},
            )
        )
    if report is not None and claim is not None and plan is not None:
        # An advisory "may be needed" is moot once the run has assessed the
        # condition; the run's own UNKNOWNs produce the repairs that remain.
        repairs = [r for r in repairs if not r.detail.get("advisory")]
        repairs += _post_execution_repairs(plan, claim, registry, report, execution or {}, comparison, assurance)
    repairs = merge_repairs(repairs)

    qoi = None if claim is None else claim.qoi.name
    record: dict[str, Any] = {
        "schema": ASSESSMENT_SCHEMA,
        "status": "assessed" if executed else "not_executed",
        "verdict": verdict.value,
        "claim": None if claim is None else claim.to_dict(),
        "compilation": compiled.to_dict(),
        "plan": None if plan is None else plan.to_dict(),
        "execution": None if execution is None else dict(execution),
        "result": None
        if report is None or qoi not in report.values
        else {
            "quantity": qoi,
            "instance": None if plan is None else plan.instance,
            "value": report.values[qoi].to_dict(),
            "report_run_id": report.run_id,
        },
        "validity": []
        if report is None
        else [
            {
                "model_id": r.model_id,
                "version": r.version,
                "status": r.assessment.status.value,
                "satisfied": sorted(r.assessment.satisfied),
                "violated": sorted(r.assessment.violated),
                "unknown": [{"condition": u.name, "reason": u.reason.value} for u in sorted(r.assessment.unknown_reasons, key=lambda u: u.name)],
                "assumptions": list(registry.get(plan.capability_id).model(r.model_id).assumptions)
                if plan is not None and registry.get(plan.capability_id).model(r.model_id) is not None
                else [],
            }
            for r in report.validity
        ],
        "verification": None
        if report is None
        else {
            "attained": _levels(report.attained_levels, VERIFICATION_LEVELS),
            "checks": [
                {"name": c.name, "outcome": c.outcome.value, "establishes": None if c.establishes is None else c.establishes.value}
                for c in report.validation
            ],
        },
        "validation": None
        if report is None
        else {
            "attained": _levels(report.attained_levels, VALIDATION_LEVELS),
            "evidence_basis": report.evidence_basis,
            "required": [l.value for l in claim.evidence.required_levels],
            "missing_required": [l.value for l in claim.evidence.required_levels if l not in set(report.attained_levels)],
        },
        "uncertainty": None
        if report is None
        else {
            "reported": None if qoi not in report.uncertainty else report.uncertainty[qoi].to_dict(),
            "demanded": [c.value for c in claim.uncertainty.ordered_channels()],
            "coverage_factor": claim.uncertainty.coverage_factor,
            "channels": None
            if evidence is None
            else {c.value: evidence.uncertainty.channel(c).is_quantified for c in claim.uncertainty.ordered_channels()},
            "discrepancy": claim.discrepancy.to_dict(),
            "evidence_problem": evidence_problem,
            "transport": report_transport(report, qoi).to_dict() if qoi in report.values else None,
        },
        "uncertainty_studies": [] if studies is None else studies.to_list(),
        "evidence": None
        if evidence is None
        else {
            "evidence_id": evidence.evidence_id,
            "record_hash": evidence.record_hash,
            "content_hash": evidence.content_hash,
            "source_class": evidence.source_class.value,
            "claim_binding": evidence.claim_binding.key,
            "context_ref": evidence.context_ref,
            "domain_pack_ref": evidence.domain_pack_ref,
            "provenance_ref": evidence.provenance_ref,
            "source_closure_complete": evidence.source_closure_complete,
        },
        "evidence_sources": [o.to_dict() for o in sources],
        "external_evidence": [m.to_dict() for m in oracles],
        "external_evidence_assessments": [a.to_dict() for a in external_assessments],
        "external_trust_registry": trust.digest,
        "context_problems": list(context),
        "assurance": None if assurance is None else assurance.to_dict(plan),
        "credibility": None
        if report is None
        else {"verdict": report.verdict.value, "evidence_basis": report.evidence_basis, "report": report.to_dict()},
        "comparison": None if comparison is None else comparison.to_dict(),
        "basis": {**basis.to_dict(), "admissible": admissible(basis)},
        **({"policy": policy_record} if policy_record is not None else {}),
        "repair_actions": [r.to_dict() for r in repairs],
    }
    items = explain(record)
    record["reasons"] = _reasons(basis, verdict, record)
    record["limitations"] = [i.to_dict() for i in items if i.kind in (ExplanationKind.MODEL_LIMITATION, ExplanationKind.ASSUMPTION)]
    record["missing_evidence"] = [
        i.to_dict()
        for i in items
        if i.kind in (ExplanationKind.MISSING_EVIDENCE, ExplanationKind.VALIDATION_GAP, ExplanationKind.UNCERTAINTY_GAP)
    ]
    record["explanation"] = [i.to_dict() for i in items]
    record["notice"] = (
        "A structured scientific assessment derived from the registered models' own validity, "
        "verification, validation and uncertainty records. Not a safety certification and not an "
        "automatic real-world decision."
    )
    # Phase 5/6: why the claim is (not) decided, and what could close each gap -- both pure functions of
    # this record and the registry's declarations, so read-back re-derives them.
    analysis = analyze_gaps(record)
    record["evidence_gaps"] = analysis.to_dict()
    record["next_experiments"] = recommend_next(record, registry, analysis).to_dict()
    canonical_json(record)  # the record is JSON, all the way down
    live["verdict"] = verdict
    live["basis"] = basis
    live["items"] = items
    return record, live


@dataclass(frozen=True)
class ClaimAssessment:
    """One claim, assessed. ``record`` is the public, serializable answer."""

    claim: ScientificClaim | None
    compiled: CompiledClaim
    plan: ExperimentPlan | None
    execution: PlanExecution | None
    report: CredibilityEvidenceReport | None
    verdict: ClaimVerdict
    basis: VerdictBasis
    evidence: Any = None
    assurance: Assurance | None = None
    comparison: ClaimComparison | None = None
    explanation: tuple[ExplanationItem, ...] = ()
    #: The public record, as canonical JSON: immutable, and a fresh copy per read.
    record_json: str = "{}"

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self.record_json)

    @property
    def digest(self) -> str:
        return assessment_record_digest(self.to_dict())


def _execution_view(execution: PlanExecution) -> dict[str, Any]:
    return {
        "outcome": execution.outcome.value,
        "run_id": execution.run_id,
        "plan_digest": execution.plan_digest,
        "capability_id": execution.capability_id,
        "instance": execution.instance,
        "report_run_id": None if execution.report is None else execution.report.run_id,
        "failure": execution.failure,
        "binding_problems": list(execution.binding_problems),
        "condition_repairs": [[i, dict(r)] for i, r in execution.condition_repairs],
    }


def assess_claim(
    claim: ScientificClaim | Mapping[str, Any],
    registry: CapabilityRegistry,
    *,
    external: tuple[Any, ...] = (),
    empirical_observations: tuple[DatasetObservation, ...] = (),
    model_form_qualification: ProducerQualification | None = None,
    model_form_qualification_trust: ModelFormQualificationRegistry = (
        PRODUCTION_MODEL_FORM_QUALIFICATIONS
    ),
    empirical_observation_trust: EmpiricalObservationRegistry = (
        PRODUCTION_EMPIRICAL_OBSERVATIONS
    ),
    trust: TrustedExternalRegistry = PRODUCTION_EXTERNAL_REGISTRY,
) -> ClaimAssessment:
    """Assess one structured claim end to end. Expected outcomes are records, never exceptions.

    ``external`` are measurement or literature records the caller offers; each is ingested and given a
    standing under ``trust`` (the repository's pins by default). Offering one never grants a level.
    """
    compiled = compile_claim(claim, registry)
    parsed = compiled.claim
    plan = execution = report = None
    view = None
    if compiled.status is CompilationStatus.READY:
        plan = plan_experiment(compiled, registry)
        execution = execute_plan(plan, registry, dict(parsed.supplied_inputs))
        report = execution.report
        view = _execution_view(execution)
    studies = None
    if execution is not None and execution.bound and planned_studies(plan):
        studies = run_uncertainty_studies(
            plan,
            registry,
            parsed,
            report,
            empirical_observations=empirical_observations,
            model_form_qualification=model_form_qualification,
            model_form_qualification_trust=model_form_qualification_trust,
            empirical_observation_trust=empirical_observation_trust,
        )
    offered = tuple(read_external_record(r) if isinstance(r, Mapping) else r for r in external)
    record, live = _build_record(parsed, compiled, plan, view, report, registry, studies, offered, trust)
    return ClaimAssessment(
        claim=parsed,
        compiled=compiled,
        plan=plan,
        execution=execution,
        report=report,
        verdict=live["verdict"],
        basis=live["basis"],
        evidence=live["evidence"],
        assurance=live["assurance"],
        comparison=live["comparison"],
        explanation=live["items"],
        record_json=canonical_json(record),
    )


def verify_assessment(
    record: Mapping[str, Any],
    registry: CapabilityRegistry,
    *,
    trust: TrustedExternalRegistry = PRODUCTION_EXTERNAL_REGISTRY,
    model_form_qualification_trust: ModelFormQualificationRegistry = (
        PRODUCTION_MODEL_FORM_QUALIFICATIONS
    ),
    empirical_observation_trust: EmpiricalObservationRegistry = (
        PRODUCTION_EMPIRICAL_OBSERVATIONS
    ),
) -> ClaimAssessment:
    """Read an assessment record back by re-deriving every part of it.

    The claim is re-read strictly and recompiled; the plan is re-read and must
    be the plan the claim produces; the credibility report is re-read by its own
    strict reader (which re-derives its verdict); the report must still be bound
    to the plan; then evidence, assurance, comparison, verdict, repairs and the
    explanation are rebuilt and the whole record must match. Execution is not
    repeated: what the system ran is the report, and the report re-derives.
    """
    record = require_mapping(record, field="assessment", error=AssessmentForgeryError)
    if record.get("schema") != ASSESSMENT_SCHEMA:
        raise AssessmentForgeryError(f"expected schema {ASSESSMENT_SCHEMA!r}, found {record.get('schema')!r}")
    raw_claim = record.get("claim")
    compiled = compile_claim(raw_claim if raw_claim is not None else {}, registry)
    claim = compiled.claim
    plan = report = None
    view = record.get("execution")
    if compiled.status is CompilationStatus.READY:
        if record.get("plan") is None:
            raise AssessmentForgeryError("a READY claim's record carries no plan")
        try:
            plan = ExperimentPlan.from_dict(record["plan"])
            verify_plan(plan, compiled, registry)
        except PlanningError as exc:
            raise AssessmentForgeryError(f"plan: {exc}") from exc
        if view is None:
            raise AssessmentForgeryError("a READY claim's record carries no execution")
        credibility = record.get("credibility")
        if view.get("outcome") == ExecutionOutcome.COMPLETED.value:
            if credibility is None:
                raise AssessmentForgeryError("a completed execution's record carries no credibility report")
            try:
                report = CredibilityEvidenceReport.from_dict(credibility["report"])
            except Exception as exc:
                raise AssessmentForgeryError(f"credibility report: {exc}") from exc
            problems = binding_problems(plan, registry, report, dict(claim.supplied_inputs))
            if list(problems) != list(view.get("binding_problems", [])):
                raise AssessmentForgeryError("the report's binding to the plan does not re-derive")
        elif credibility is not None:
            raise AssessmentForgeryError("a refused execution carries a credibility report")
    elif view is not None or record.get("plan") is not None:
        raise AssessmentForgeryError("a claim that is not READY cannot carry a plan or an execution")

    studies = None
    recorded_studies = record.get("uncertainty_studies")
    bound_run = plan is not None and report is not None and view is not None and not view.get("binding_problems")
    if bound_run and planned_studies(plan) and not recorded_studies:
        raise AssessmentForgeryError("the plan names uncertainty studies and the record carries none")
    if recorded_studies:
        if plan is None or report is None:
            raise AssessmentForgeryError("uncertainty studies are recorded for a run that produced no bound report")
        try:
            studies = verify_study_records(
                _plain(recorded_studies),
                plan,
                report,
                registry=registry,
                claim=claim,
                model_form_qualification_trust=model_form_qualification_trust,
                empirical_observation_trust=empirical_observation_trust,
            )
        except UncertaintyStudyError as exc:
            raise AssessmentForgeryError(f"uncertainty studies: {exc}") from exc
    try:
        offered = tuple(
            read_external_record(a["record"])
            for a in record.get("external_evidence_assessments", [])
            if a.get("source_class") in ("measurement", "literature")
        )
    except (ClaimLayerError, KeyError, TypeError) as exc:
        raise AssessmentForgeryError(f"external evidence: {exc}") from exc
    rebuilt, live = _build_record(claim, compiled, plan, view, report, registry, studies, offered, trust)
    if canonical_json(rebuilt) != canonical_json(_plain(record)):
        differing = sorted(k for k in set(rebuilt) | set(record) if canonical_json(_plain(rebuilt.get(k))) != canonical_json(_plain(record.get(k))))
        raise AssessmentForgeryError(
            f"the record does not re-derive from the claim, plan and report it carries; differing: {differing}"
        )
    return ClaimAssessment(
        claim=claim,
        compiled=compiled,
        plan=plan,
        execution=None,
        report=report,
        verdict=live["verdict"],
        basis=live["basis"],
        evidence=live["evidence"],
        assurance=live["assurance"],
        comparison=live["comparison"],
        explanation=live["items"],
        record_json=canonical_json(rebuilt),
    )


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


__all__ = [
    "ASSESSMENT_SCHEMA",
    "AssembledEvidence",
    "AssessmentForgeryError",
    "Assurance",
    "ClaimAssessment",
    "assemble_evidence",
    "assess_claim",
    "assure",
    "verify_assessment",
]
