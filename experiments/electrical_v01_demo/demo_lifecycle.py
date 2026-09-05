"""One Electrical V0.1 campaign, wired from frozen parts and traced.

Everything scientific here is imported. The module contributes the wiring a
campaign has to write for itself — a generator, a harness, an evaluator — and
the trace that makes the run legible afterwards.

WHERE THE PREDICTION COMES FROM
-------------------------------
Validation probes must reference a prediction that existed before their
observation. The generator creates those predictions the first time it is asked
for candidates AFTER the parameter phase has produced evidence, commits them to
E2's ledger from the posterior of that moment, and seals it. Generation
precedes selection, which precedes execution, so the commitment is strictly
earlier than every observation it will be scored against — and the frozen event
log records the reference in ACTION_SELECTED, which it orders before
EXECUTION_STARTED.

Committing at the prior instead would have been simpler and worthless: the
predictive would be a metre wide and nothing could fail it.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np

from experiments.electrical_e2 import e2_truth
from experiments.electrical_e2.e2_adequacy import (
    AdequacyState,
    CommitmentLedger,
    ExecutionValidity,
    aggregate_adequacy,
    build_joint_predictive,
    classify_adequacy,
    score_commitments,
)
from experiments.electrical_e2.e2_config import VMID_METRIC
from experiments.electrical_e2.e2_harness import (
    E2Executor,
    E2FaultyExecutor,
    E2Harness,
    e2_obligations,
)
from experiments.electrical_e2.e2_model import (
    E2Observation,
    best_decision,
    evsi,
    observations_digest,
    posterior_summary,
    posterior_weights,
    predictive_mixture,
    prior_weights,
)
from src.engcore.scientific import Quantity
from src.engcore.sria import (
    AdmissionAuthority,
    AdmissionAuthorityRegistry,
    BeliefUpdateGateway,
    CampaignCharter,
    ExecutorType,
    ResearchAction,
    TerminalDecision,
)
from src.engcore.sria.assurance import Arbiter
from src.engcore.sria.assurance.assessment import (
    CheckRecord,
    CriticAssessment,
    CriticClass,
    CriticVerdict,
    Finding,
    FindingImpact,
    Severity,
)
from src.engcore.sria.assurance.obligations import ObligationKind
from src.engcore.sria.calibration.critic import CalibrationVerdict
from src.engcore.sria.campaign import (
    AssessmentBundle,
    BudgetLedger,
    CampaignEventLog,
    CampaignEventType,
    CampaignRunner,
    CertificationRequirement,
)
from src.engcore.sria.campaign.stopping import StoppingCriterion
from src.engcore.sria.decision import (
    ActionFamily,
    ActionProposal,
    AtomicAction,
    BeliefSnapshot,
    CalibrationState,
    CandidateEvaluator,
    ComponentStatus,
    CostTradeoff,
    DependencyIdentity,
    DependencyKind,
    GenerationContext,
    ScoreComponent,
    UtilityEngine,
    UtilityPolicy,
    canonical_digest,
    resolve_terminal_objective,
)
from src.engcore.sria.provenance import AssessmentProvenance

from .demo_config import (
    ACTION_FAMILY_BY_PHASE,
    CAMPAIGN_ID,
    CANDIDATE_ACTIONS,
    CHARTER_VERSION,
    COST_UNIT,
    DECISION_ID,
    MAX_ITERATIONS,
    PARAMETER_ACTION,
    REQUIRED_ACTION_IDS,
    REQUIREMENT_ID,
    REQUIREMENT_SOURCE,
    RESERVED_VALIDATION_BUDGET,
    STOPPING_CRITERION_ID,
    TOTAL_BUDGET,
)

ACTION_BY_ID = {a.action_id: a for a in CANDIDATE_ACTIONS}


def family_for(spec) -> ActionFamily:
    return ActionFamily(ACTION_FAMILY_BY_PHASE[spec.phase])


# =====================================================================
# Executor adapter and decision suppliers
# =====================================================================

class DemoExecutor:
    """E2's instrument, in the shape the CampaignRunner calls."""

    executor_id = "v01demo.electrical_executor"
    executor_version = "1"

    def __init__(self, inner: E2Executor) -> None:
        self._inner = inner
        self.calls: list[str] = []

    @property
    def inner(self) -> E2Executor:
        return self._inner

    def fetch_execution(self, execution_id: str):
        return self._inner.completed.get(execution_id)

    def execute(self, action, *, execution_id: str, context: Any = None):
        spec = ACTION_BY_ID[action.members[0].action_id]
        self.calls.append(spec.action_id)
        return self._inner.execute(spec, repeat=1, execution_id=execution_id)


class DemoOutcomeModel:
    """The M4 information term is E2's parameter EVSI, unmodified.

    It has no reference to the certification requirement, and a test asserts
    the scores are identical whether or not one is declared.
    """

    def __init__(self, harness: "DemoHarness") -> None:
        self._harness = harness

    def dependency_identity(self) -> DependencyIdentity:
        return DependencyIdentity(
            dependency_id="v01demo.parameter_evsi",
            kind=DependencyKind.OUTCOME_MODEL,
            version="1",
            state_digest=observations_digest(self._harness.observations()),
            detail="E2 quadrature EVSI over the solver-based predictive",
        )

    def conditional_success_utility_gain(self, candidate, snapshot, objective):
        spec = ACTION_BY_ID[candidate.members[0].action_id]
        weights = self._harness.posterior()
        value = evsi(weights, spec)
        self._harness.record_score(snapshot, spec, value)
        return ScoreComponent(
            name="conditional_success_utility_gain",
            value=value,
            status=ComponentStatus.AVAILABLE,
            source="v01demo.parameter_evsi",
            assumptions=(
                "PARAMETER information value only; carries no certification, "
                "adequacy or obligation term of any kind",
            ),
            detail=f"one-step parameter EVSI for {spec.action_id}",
        )

    def conditional_failure_utility_gain(self, candidate, snapshot, objective):
        return ScoreComponent(
            name="conditional_failure_utility_gain",
            value=0.0,
            status=ComponentStatus.AVAILABLE,
            source="v01demo.declared",
            detail="no informative failure value is declared",
        )


class DemoCostSupplier:
    def dependency_identity(self) -> DependencyIdentity:
        return DependencyIdentity(
            dependency_id="v01demo.declared_cost",
            kind=DependencyKind.COST_MODEL,
            version="1",
            state_digest=canonical_digest(
                {a.action_id: a.cost for a in CANDIDATE_ACTIONS}
            ),
            detail="declared instrument costs; no fitted model",
        )

    def expected_cost(self, candidate, snapshot):
        spec = ACTION_BY_ID[candidate.members[0].action_id]
        return ScoreComponent(
            name="expected_cost",
            value=spec.cost,
            status=ComponentStatus.AVAILABLE,
            source="v01demo.declared_cost",
            calibration_verdict=CalibrationVerdict.TRUSTED,
            unit=COST_UNIT,
            detail="declared instrument cost",
        )


class DemoFailureSupplier:
    def dependency_identity(self) -> DependencyIdentity:
        return DependencyIdentity(
            dependency_id="v01demo.declared_failure",
            kind=DependencyKind.FAILURE_SOURCE,
            version="1",
            state_digest=canonical_digest({"p_cf": 0.0}),
            detail="declared zero failure probability for a direct linear solve",
        )

    def computational_failure_probability(self, candidate, snapshot):
        return ScoreComponent(
            name="p_computational_failure",
            value=0.0,
            status=ComponentStatus.AVAILABLE,
            source="v01demo.declared_failure",
            calibration_verdict=CalibrationVerdict.TRUSTED,
            detail="declared benchmark failure probability",
        )


class DemoTerminalUtility:
    utility_id = "v01demo.decision_loss"
    utility_version = "1"

    def __init__(self, harness: "DemoHarness") -> None:
        self._harness = harness

    def expected_utility(self, snapshot, decision_id: str) -> float:
        _, value = best_decision(self._harness.posterior())
        return value

    def expected_utility_after(self, snapshot, decision_id, outcome) -> float:
        observation = E2Observation(
            action_id=str(outcome["action_id"]),
            source_voltage_volt=float(outcome["source_voltage_volt"]),
            y_volt=float(outcome["y_volt"]),
            sigma_volt=float(outcome["sigma_volt"]),
        )
        updated = posterior_weights(
            tuple(self._harness.observations()) + (observation,)
        )
        _, value = best_decision(updated)
        return value

    def state_digest(self) -> str:
        return observations_digest(self._harness.observations())


# =====================================================================
# Generator: candidates, and the predictions the probes answer to
# =====================================================================

class DemoGenerator:
    """Every instrument, every iteration, at its declared price.

    Validation probes are ordinary candidates scored by the same engine. They
    lose on net value and are declined; that is the honest result and it is
    what makes the certification routing visible as something separate.
    """

    family = ActionFamily.CHARACTERIZE

    def __init__(self, harness: "DemoHarness", commitments: CommitmentLedger) -> None:
        self._harness = harness
        self._commitments = commitments

    def _commit_predictions_once(self) -> None:
        """Create and seal the required predictions, before any probe runs."""
        if self._commitments.is_sealed:
            return
        observations = self._harness.observations()
        if not observations:
            # Nothing has been measured yet, so a prediction now would be the
            # prior and would test nothing. Wait for the parameter phase.
            return
        weights = self._harness.posterior()
        digest = observations_digest(observations)
        for action_id in REQUIRED_ACTION_IDS:
            spec = ACTION_BY_ID[action_id]
            self._commitments.commit(
                action_id=action_id,
                source_voltage_volt=spec.source_voltage_volt,
                noise_sigma_volt=spec.noise_sigma_volt,
                evidence_snapshot_digest=digest,
                n_observations=len(observations),
                mixture=predictive_mixture(weights, spec),
            )
        self._commitments.seal()

    def generate(self, context: GenerationContext):
        self._commit_predictions_once()
        refs = {
            action_id: commitment.artifact_hash
            for action_id, commitment in self._commitments.commitments.items()
        }
        out = []
        for spec in CANDIDATE_ACTIONS:
            metadata: dict[str, Any] = {
                "source_voltage_volt": spec.source_voltage_volt,
                "noise_sigma_volt": spec.noise_sigma_volt,
                "declared_cost": spec.cost,
                "phase": spec.phase,
            }
            if spec.action_id in refs:
                metadata["prediction_ref"] = refs[spec.action_id]
                metadata["requirement_id"] = REQUIREMENT_ID
            out.append(
                AtomicAction(
                    action=ResearchAction(
                        action_id=spec.action_id,
                        executor_type=ExecutorType.SIMULATION,
                        target_ref="theta.R2",
                        parameters={
                            "source_voltage": Quantity(
                                spec.source_voltage_volt, "volt"
                            )
                        },
                        expected_cost={
                            "acquisition": Quantity(spec.cost, COST_UNIT)
                        },
                        metadata=metadata,
                    ),
                    proposal=ActionProposal(
                        family=family_for(spec),
                        target_ref="theta.R2",
                        rationale=spec.description,
                        expected_observable=VMID_METRIC,
                        informative_failure_causes=("numerical",),
                    ),
                )
            )
        return tuple(out)


# =====================================================================
# Harness
# =====================================================================

@dataclass
class DemoHarness:
    """CampaignHarness for the demo. Evidence and assessment are E2's."""

    gateway: BeliefUpdateGateway
    e2: E2Harness
    executor_impl: DemoExecutor
    obligations: Any
    score_log: list[dict[str, Any]] = field(default_factory=list)
    _cache: dict[str, Any] = field(default_factory=dict)

    def observations(self) -> tuple[E2Observation, ...]:
        return self.e2.current_observations()

    def posterior(self):
        observations = self.observations()
        key = observations_digest(observations)
        if key not in self._cache:
            self._cache[key] = (
                posterior_weights(observations) if observations
                else prior_weights()
            )
        return self._cache[key]

    def record_score(self, snapshot, spec, value: float) -> None:
        entry = {
            "snapshot_id": getattr(snapshot, "snapshot_id", ""),
            "action_id": spec.action_id,
            "phase": spec.phase,
            "n_observations": len(self.observations()),
            "parameter_evsi": value,
            "cost": spec.cost,
            "net_value": value - spec.cost,
        }
        if entry not in self.score_log:
            self.score_log.append(entry)

    # -- CampaignHarness protocol -----------------------------------------
    def build_snapshot(self, *, snapshot_id, run, obligation_state):
        return BeliefSnapshot(
            snapshot_id=snapshot_id,
            campaign_id=CAMPAIGN_ID,
            charter_version=CHARTER_VERSION,
            active_evidence=tuple(sorted(self.gateway.belief.active_view())),
            belief_snapshot_ref=self.gateway.belief.snapshot_ref(),
            calibration=CalibrationState(
                cost_model_id="v01demo.declared_cost",
                cost_verdict=CalibrationVerdict.TRUSTED,
                failure_model_id="v01demo.declared_failure",
                failure_verdict=CalibrationVerdict.TRUSTED,
            ),
            obligation_state=dict(obligation_state),
            metadata={"observations_digest": observations_digest(
                self.observations()
            )},
        )

    def evaluator(self) -> CandidateEvaluator:
        return CandidateEvaluator(
            UtilityEngine(
                policy=UtilityPolicy(
                    policy_id="v01demo.policy",
                    cost_tradeoff=CostTradeoff(
                        rate=1.0,
                        cost_unit=COST_UNIT,
                        utility_reference="v01demo/decision-loss/1",
                        source="electrical v0.1 demo charter",
                        assumptions=(
                            "declared cost units exchange 1:1 with terminal "
                            "loss units",
                        ),
                    ),
                ),
                outcome_model=DemoOutcomeModel(self),
                cost_supplier=DemoCostSupplier(),
                failure_supplier=DemoFailureSupplier(),
            )
        )

    def objective(self):
        return resolve_terminal_objective(demo_charter(), DemoTerminalUtility(self))

    def generation_context(self, snapshot, run) -> GenerationContext:
        return GenerationContext(snapshot=snapshot)

    def generators(self, run):
        return self._generators

    def executor(self) -> DemoExecutor:
        return self.executor_impl

    def build_evidence(self, execution, snapshot, *, evidence_id):
        if execution.result is None:
            return None
        return self.e2.build_evidence(execution, evidence_id=evidence_id)

    def assess(self, execution, evidence, *, assessment_prefix) -> AssessmentBundle:
        assessment, budget, state = self.e2.assess(
            execution, evidence, prefix=assessment_prefix
        )
        return AssessmentBundle(
            assessments=(assessment,),
            uncertainty_budget=budget,
            obligation_state={
                o.obligation_id: bool(state.get(o.obligation_id, False))
                for o in self.obligations.obligations
                if o.kind is ObligationKind.REQUIRED_CRITIC
            },
        )

    def update_calibration(self, execution, *, record_id):
        return None


def demo_charter() -> CampaignCharter:
    return CampaignCharter(
        campaign_id=CAMPAIGN_ID,
        terminal_decisions=(
            TerminalDecision(
                decision_id=DECISION_ID,
                statement="classify the unknown resistance against 1200 ohm",
                options=("A", "B"),
            ),
        ),
        utility_reference="v01demo/decision-loss/1",
    )


# =====================================================================
# Stopping criterion: was the test done, and did the model survive it?
# =====================================================================

class DemoCertificationEvaluator:
    """Reads the belief store and the sealed commitments. Nothing else.

    No grader truth, no posterior width, no EVPI, no EVSI, no budget. It mints
    no stopping verdict — it produces an assessment and the Arbiter decides.
    """

    criterion_id = STOPPING_CRITERION_ID
    critic_id = "v01demo.certification"
    critic_version = "1"

    def __init__(self, gateway: BeliefUpdateGateway, commitments: CommitmentLedger):
        self._gateway = gateway
        self._commitments = commitments
        self.last_state: AdequacyState | None = None

    def admitted_action_ids(self) -> set[str]:
        return {
            str(entry.claim_payload["action_id"])
            for entry in self._gateway.belief.active_view().values()
        }

    def adequacy_state(self) -> AdequacyState | None:
        admitted = self.admitted_action_ids()
        if not set(REQUIRED_ACTION_IDS) <= admitted:
            return None
        for action_id in REQUIRED_ACTION_IDS:
            if action_id in self._commitments.observations:
                continue
            y = next(
                float(e.claim_payload["y_volt"])
                for e in self._gateway.belief.active_view().values()
                if str(e.claim_payload["action_id"]) == action_id
            )
            self._commitments.record_observation(
                action_id=action_id,
                y_volt=y,
                execution_id=f"v01demo-{action_id}",
                execution_valid=True,
            )
        surprises = score_commitments(self._commitments)
        joint = build_joint_predictive(
            self._commitments, [s.action_id for s in surprises]
        )
        state = classify_adequacy(
            surprises, aggregate_adequacy(surprises, joint)
        ).state
        self.last_state = state
        return state

    def evaluate(self, context, *, assessment_id: str) -> CriticAssessment:
        state = self.adequacy_state()
        if state is None:
            verdict = CriticVerdict.FAIL
            findings = (
                Finding(
                    code="v01demo.certification_outstanding",
                    severity=Severity.BLOCKING,
                    category="process",
                    message="required certification evidence is outstanding",
                    impact=FindingImpact.ASSURANCE_BLOCKING,
                ),
            )
            summary = "the declared certification test has not been performed"
        elif state is AdequacyState.MODEL_ADEQUACY_ACCEPTABLE:
            verdict, findings = CriticVerdict.PASS, ()
            summary = (
                "required evidence obtained; the assumed family survived its "
                "own precommitted predictions at the tested conditions"
            )
        else:
            verdict = CriticVerdict.FAIL
            findings = (
                Finding(
                    code="v01demo.model_space_inadequate",
                    severity=Severity.BLOCKING,
                    category="model_adequacy",
                    message=(
                        "the required evidence was obtained and refuted the "
                        "assumed family; stopping here would certify a model "
                        "this campaign's own predictions have failed"
                    ),
                    impact=FindingImpact.EVIDENCE_INVALIDATING,
                ),
            )
            summary = f"required evidence obtained; adequacy is {state.value}"
        return CriticAssessment(
            assessment_id=assessment_id,
            critic_id=self.critic_id,
            critic_version=self.critic_version,
            critic_class=CriticClass.PROCESS,
            subject_ref=assessment_id,
            verdict=verdict,
            provenance=AssessmentProvenance(
                assessment_id=assessment_id,
                critic_id=self.critic_id,
                critic_version=self.critic_version,
                inputs_ref=(REQUIREMENT_ID,),
            ),
            checks=(
                CheckRecord(
                    name=self.criterion_id,
                    outcome=verdict,
                    mandatory=True,
                    detail=summary,
                ),
            ),
            findings=findings,
            summary=summary,
        )


# =====================================================================
# Building and running one world
# =====================================================================

@dataclass
class DemoStack:
    gateway: BeliefUpdateGateway
    arbiter: Arbiter
    e2: E2Harness
    harness: DemoHarness
    commitments: CommitmentLedger
    evaluator: DemoCertificationEvaluator
    runner: CampaignRunner
    budget: BudgetLedger


def build_stack(
    spec: e2_truth.TruthSpec,
    *,
    label: str,
    with_requirement: bool = True,
    executor_class: type[E2Executor] = E2Executor,
) -> DemoStack:
    """One campaign. ``with_requirement=False`` is the counterfactual used to
    prove the certification requirement changed no parameter-learning score."""
    authority = AdmissionAuthority(f"v01demo.authority.{label}")
    gateway = BeliefUpdateGateway(
        authorities=AdmissionAuthorityRegistry([authority])
    )
    arbiter = Arbiter(authority)
    e2 = E2Harness(
        run_id=f"{label}-chain",
        gateway=gateway,
        arbiter=arbiter,
        executor=executor_class(spec),
        obligations=e2_obligations(),
        events=CampaignEventLog(f"{label}-chain"),
    )
    harness = DemoHarness(
        gateway=gateway,
        e2=e2,
        executor_impl=DemoExecutor(e2.executor),
        obligations=e2_obligations(),
    )
    commitments = CommitmentLedger(f"{label}-commitments")
    harness._generators = (DemoGenerator(harness, commitments),)
    evaluator = DemoCertificationEvaluator(gateway, commitments)
    budget = BudgetLedger(
        total_budget=TOTAL_BUDGET,
        reserved_validation_budget=RESERVED_VALIDATION_BUDGET,
        cost_unit=COST_UNIT,
    )
    runner = CampaignRunner(
        run_id=label,
        charter=demo_charter(),
        harness=harness,
        gateway=gateway,
        arbiter=arbiter,
        obligations=harness.obligations,
        budget=budget,
        max_iterations=MAX_ITERATIONS,
        generators=harness._generators,
        charter_version=CHARTER_VERSION,
        stopping_criteria=(
            StoppingCriterion(
                criterion_id=STOPPING_CRITERION_ID,
                statement=(
                    "the campaign may stop only once the declared "
                    "certification evidence has been obtained AND it left the "
                    "assumed model family adequate for the declared scope"
                ),
                source=REQUIREMENT_SOURCE,
                evaluator_id=evaluator.critic_id,
                evaluator_version=evaluator.critic_version,
            ),
        ),
        stopping_evaluators={STOPPING_CRITERION_ID: evaluator},
        certification_requirements=(
            (
                CertificationRequirement(
                    requirement_id=REQUIREMENT_ID,
                    required_action_ids=REQUIRED_ACTION_IDS,
                    source=REQUIREMENT_SOURCE,
                ),
            )
            if with_requirement
            else ()
        ),
    )
    return DemoStack(
        gateway=gateway,
        arbiter=arbiter,
        e2=e2,
        harness=harness,
        commitments=commitments,
        evaluator=evaluator,
        runner=runner,
        budget=runner.budget,
    )
