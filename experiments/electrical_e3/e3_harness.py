"""E3 grader + integration harness.

Two roles the decision path must not have: the instrument (E2's executor,
reused unmodified, running the real solver at the grader-only effective
resistance) and the wiring that connects all of it to the frozen M4/M5 stack.

WHAT IS GENUINELY EXERCISED, AND WHAT IS ADAPTED
-------------------------------------------------
This distinction is the point of E3, so it is stated here rather than implied.

**Exercised — frozen code, unmodified:**

    CampaignRunner  snapshot -> candidate generation -> UtilityEngine scoring
                    with REAL E2 EVSI -> RecommendationOutcome.STOP_PROPOSAL
                    -> ArbiterStoppingReview -> AdequacyStoppingEvaluator
                    -> Arbiter.decide -> StopReview

    M1/M3 chain     solve_circuit -> ExecutionRecord -> Evidence -> numerical
                    critic -> Arbiter -> AdmissionAuthority -> Gateway -> belief

Both stop reviews E3 reports — the one before the probes and the one after —
are produced by a real ``CampaignRunner`` over a real ``Arbiter``. Nothing here
constructs a ``StopReview``, and nothing here can: ``STOP_APPROVED`` is
structurally unreachable without a genuine Arbiter decision.

**Adapted — and this is the architecture gap E3 exists to find:**

The runner has no obligation-resolution path. Whatever the stop review says,
``_propose_stop`` pauses the run with ``NO_ACTION_WORTH_BUYING``. There is no
branch that reads a non-approving review, consults an outstanding scientific
obligation, and routes to the evidence that would discharge it. So the probe
acquisition between the two runs is performed by an experiment-local policy
(:class:`AdequacyObligationPolicy`), which executes through the same frozen
M1/M3 chain and then hands control back to a fresh runner.

E3 does not describe that as "the campaign supports obligation-driven
acquisition". It supports refusing to stop; the acquiring is the seam that is
missing.

WHY THE PROBES ARE ALSO ORDINARY CANDIDATES
--------------------------------------------
Every adequacy probe is generated, scored and priced alongside the parameter
action, by the same ``UtilityEngine``, at the same cost. The EVSI-only policy
therefore sees them and declines them on the merits — which is what makes the
comparison a comparison of policies rather than of candidate sets. Their
parameter EVSI is at the floor and is reported unaltered.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

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
from src.engcore.sria.assurance.assessment import CriticClass
from src.engcore.sria.assurance.obligations import (
    ObligationKind,
    ObligationSet,
    ValidationObligation,
)
from src.engcore.sria.calibration import CalibrationMemory, CalibrationMemoryEntry
from src.engcore.sria.calibration import Consumer, MemoryKind
from src.engcore.sria.calibration.critic import CalibrationVerdict
from src.engcore.sria.campaign import (
    AssessmentBundle,
    BudgetLedger,
    CampaignEventLog,
    CampaignRunner,
    ExecutionRecord,
)
from src.engcore.sria.campaign.checkpoint import CampaignCheckpoint
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

from experiments.electrical_e2 import e2_truth
from experiments.electrical_e2.e2_config import VMID_METRIC
from experiments.electrical_e2.e2_harness import (
    E2Executor,
    E2FaultyExecutor,
    E2Harness,
)
from experiments.electrical_e2.e2_model import (
    E2Observation,
    best_decision,
    evsi,
    observations_digest,
    posterior_weights,
    predictive_summary,
)

from .e3_config import (
    ACTION_FAMILY_BY_PHASE,
    ADEQUACY_OBLIGATION,
    CALIBRATION_ACTION,
    CAMPAIGN_ID,
    CANDIDATE_ACTIONS,
    CHARTER_VERSION,
    COST_UNIT,
    DECISION_ID,
    MAX_ITERATIONS,
    TOTAL_BUDGET,
)
from .e3_obligation import (
    AdequacyStoppingEvaluator,
    ObligationState,
    adequacy_stopping_criterion,
)

ACTION_BY_ID = {a.action_id: a for a in CANDIDATE_ACTIONS}


# =====================================================================
# Executor adapter: the runner's calling convention over E2's instrument
# =====================================================================

class E3Executor:
    """Adapts E2's unmodified executor to the CampaignRunner's signature.

    The instrument itself is E2's — same solver, same grader-only effective
    resistance, same seeded noise derivation. Only the call shape differs, so
    the runner can drive it and the obligation policy can drive it and both
    produce identical ``ExecutionRecord``s.
    """

    executor_id = "e3.electrical_executor"
    executor_version = "1"

    def __init__(self, inner: E2Executor) -> None:
        self._inner = inner
        self.calls: list[str] = []

    @property
    def inner(self) -> E2Executor:
        return self._inner

    @property
    def completed(self) -> dict[str, ExecutionRecord]:
        return self._inner.completed

    def fetch_execution(self, execution_id: str) -> ExecutionRecord | None:
        return self._inner.completed.get(execution_id)

    def execute(self, action, *, execution_id: str, context: Any = None):
        member = action.members[0]
        spec = ACTION_BY_ID[member.action_id]
        self.calls.append(spec.action_id)
        return self._inner.execute(spec, repeat=1, execution_id=execution_id)


# =====================================================================
# Decision-theoretic suppliers — REAL E2 EVSI, unmodified
# =====================================================================

class E3EvsiOutcomeModel:
    """Supplies the M4 information term as E2's real parameter EVSI.

    Used identically by the EVSI-only policy and the obligation-aware policy.
    Nothing about an outstanding obligation reaches this class: it has no
    reference to the obligation ledger, and a test asserts the scores are
    bit-identical between the two policies.
    """

    def __init__(self, harness: "E3Harness") -> None:
        self._harness = harness

    def dependency_identity(self) -> DependencyIdentity:
        return DependencyIdentity(
            dependency_id="e3.parameter_evsi_from_predictive",
            kind=DependencyKind.OUTCOME_MODEL,
            version="1",
            state_digest=observations_digest(self._harness.current_observations()),
            detail="E2 quadrature EVSI over the solver-based predictive",
        )

    def conditional_success_utility_gain(
        self, candidate, snapshot, objective
    ) -> ScoreComponent:
        spec = ACTION_BY_ID[candidate.members[0].action_id]
        observations = self._harness.current_observations()
        weights = self._harness.posterior_for(observations)
        value = evsi(weights, spec)
        self._harness.record_decision_quantities(
            snapshot, spec, weights, observations, value
        )
        return ScoreComponent(
            name="conditional_success_utility_gain",
            value=value,
            status=ComponentStatus.AVAILABLE,
            source="e3.parameter_evsi_from_predictive",
            assumptions=(
                "declared Gaussian observation model",
                "posterior over the frozen R2 grid",
                "PARAMETER information value only; carries no adequacy or "
                "certification term of any kind",
            ),
            detail=f"one-step parameter EVSI for {spec.action_id}",
        )

    def conditional_failure_utility_gain(
        self, candidate, snapshot, objective
    ) -> ScoreComponent:
        return ScoreComponent(
            name="conditional_failure_utility_gain",
            value=0.0,
            status=ComponentStatus.AVAILABLE,
            source="e3.declared",
            detail="E3 declares no informative failure value",
        )


class E3CostSupplier:
    def dependency_identity(self) -> DependencyIdentity:
        return DependencyIdentity(
            dependency_id="e3.declared_cost",
            kind=DependencyKind.COST_MODEL,
            version="1",
            state_digest=canonical_digest(
                {a.action_id: a.cost for a in CANDIDATE_ACTIONS}
            ),
            detail="preregistered declared costs; no fitted parameters",
        )

    def expected_cost(self, candidate, snapshot) -> ScoreComponent:
        spec = ACTION_BY_ID[candidate.members[0].action_id]
        return ScoreComponent(
            name="expected_cost",
            value=spec.cost,
            status=ComponentStatus.AVAILABLE,
            source="e3.declared_cost",
            calibration_verdict=CalibrationVerdict.TRUSTED,
            unit=COST_UNIT,
            detail="declared benchmark cost",
        )


class E3FailureSupplier:
    def dependency_identity(self) -> DependencyIdentity:
        return DependencyIdentity(
            dependency_id="e3.declared_failure",
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
            source="e3.declared_failure",
            calibration_verdict=CalibrationVerdict.TRUSTED,
            detail="declared benchmark failure probability",
        )


class E3TerminalUtility:
    utility_id = "e3.decision_loss"
    utility_version = "1"

    def __init__(self, harness: "E3Harness") -> None:
        self._harness = harness

    def _weights(self):
        return self._harness.posterior_for(self._harness.current_observations())

    def expected_utility(self, snapshot: BeliefSnapshot, decision_id: str) -> float:
        _, value = best_decision(self._weights())
        return value

    def expected_utility_after(
        self, snapshot: BeliefSnapshot, decision_id: str, outcome: Mapping[str, Any]
    ) -> float:
        observation = E2Observation(
            action_id=str(outcome["action_id"]),
            source_voltage_volt=float(outcome["source_voltage_volt"]),
            y_volt=float(outcome["y_volt"]),
            sigma_volt=float(outcome["sigma_volt"]),
        )
        updated = posterior_weights(
            tuple(self._harness.current_observations()) + (observation,)
        )
        _, value = best_decision(updated)
        return value

    def state_digest(self) -> str:
        return observations_digest(self._harness.current_observations())


def family_for(spec) -> ActionFamily:
    """VALIDATE for adequacy probes, CHARACTERIZE for parameter learning.

    Not a cosmetic label. The frozen ``BudgetLedger`` fences its validation
    reservation BY FAMILY — ``affordable(cost, family=VALIDATE)`` may draw on
    the reservation and nothing else may — so declaring the probes VALIDATE is
    what makes the repository's existing protection apply to them. It is also
    simply what they are.
    """
    return ActionFamily(ACTION_FAMILY_BY_PHASE[spec.phase])


class E3Generator:
    """Proposes every preregistered candidate — parameter AND adequacy probes.

    The probes are ordinary candidates here on purpose. If they were withheld
    from the EVSI-only policy the comparison would be rigged; they are offered
    at the same price and it declines them, which is the honest result.

    Probe actions carry ``obligation_id`` in their metadata, which is the link
    the frozen ``validation_targets`` router uses to match a VALIDATE candidate
    to the obligation it would discharge. E3 stamps it so the router *could*
    match; whether it actually can is a separate question the experiment
    answers rather than assumes.
    """

    family = ActionFamily.CHARACTERIZE

    def generate(self, context: GenerationContext):
        out = []
        for spec in CANDIDATE_ACTIONS:
            family = family_for(spec)
            metadata = {
                "source_voltage_volt": spec.source_voltage_volt,
                "noise_sigma_volt": spec.noise_sigma_volt,
                "declared_cost": spec.cost,
                "phase": spec.phase,
            }
            if family is ActionFamily.VALIDATE:
                metadata["obligation_id"] = ADEQUACY_OBLIGATION.obligation_id
                metadata["required_by_obligation"] = (
                    spec.action_id in ADEQUACY_OBLIGATION.required_action_ids
                )
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
                        family=family,
                        target_ref="theta.R2",
                        rationale=spec.description,
                        expected_observable=VMID_METRIC,
                        informative_failure_causes=("numerical",),
                    ),
                )
            )
        return tuple(out)


# =====================================================================
# The CampaignHarness
# =====================================================================

@dataclass
class E3Harness:
    """CampaignHarness for E3. Evidence and assessment delegate to E2's."""

    run_id: str
    gateway: BeliefUpdateGateway
    e2: E2Harness
    executor_impl: E3Executor
    obligations: ObligationSet
    memory: CalibrationMemory = field(default_factory=CalibrationMemory)
    decision_log: list[dict[str, Any]] = field(default_factory=list)
    _posterior_cache: dict[str, Any] = field(default_factory=dict)

    # -- posterior plumbing (reads the gateway, nothing else) --------------
    def current_observations(self) -> tuple[E2Observation, ...]:
        return self.e2.current_observations()

    def posterior_for(self, observations) -> Any:
        key = observations_digest(observations)
        if key not in self._posterior_cache:
            self._posterior_cache[key] = posterior_weights(observations)
        return self._posterior_cache[key]

    def record_decision_quantities(
        self, snapshot, spec, weights, observations, evsi_value
    ) -> None:
        entry = {
            "snapshot_id": getattr(snapshot, "snapshot_id", ""),
            "action_id": spec.action_id,
            "phase": spec.phase,
            "observations_digest": observations_digest(observations),
            "n_observations": len(observations),
            "parameter_evsi": evsi_value,
            "cost": spec.cost,
            "net_parameter_value": evsi_value - spec.cost,
            "predictive": predictive_summary(weights, spec),
        }
        if entry not in self.decision_log:
            self.decision_log.append(entry)

    # -- CampaignHarness protocol ------------------------------------------
    def build_snapshot(self, *, snapshot_id, run, obligation_state) -> BeliefSnapshot:
        return BeliefSnapshot(
            snapshot_id=snapshot_id,
            campaign_id=CAMPAIGN_ID,
            charter_version=CHARTER_VERSION,
            active_evidence=tuple(sorted(self.gateway.belief.active_view())),
            belief_snapshot_ref=self.gateway.belief.snapshot_ref(),
            calibration=CalibrationState(
                cost_model_id="e3.declared_cost",
                cost_verdict=CalibrationVerdict.TRUSTED,
                failure_model_id="e3.declared_failure",
                failure_verdict=CalibrationVerdict.TRUSTED,
            ),
            obligation_state=dict(obligation_state),
            metadata={
                "observations_digest": observations_digest(
                    self.current_observations()
                )
            },
        )

    def evaluator(self) -> CandidateEvaluator:
        engine = UtilityEngine(
            policy=UtilityPolicy(
                policy_id="e3.policy",
                cost_tradeoff=CostTradeoff(
                    rate=1.0,
                    cost_unit=COST_UNIT,
                    utility_reference="e3/decision-loss/1",
                    source="e3 preregistered config",
                    assumptions=(
                        "declared benchmark cost units exchange 1:1 with "
                        "terminal loss units",
                    ),
                ),
            ),
            outcome_model=E3EvsiOutcomeModel(self),
            cost_supplier=E3CostSupplier(),
            failure_supplier=E3FailureSupplier(),
        )
        return CandidateEvaluator(engine)

    def objective(self):
        return resolve_terminal_objective(e3_charter(), E3TerminalUtility(self))

    def generation_context(self, snapshot, run) -> GenerationContext:
        return GenerationContext(snapshot=snapshot)

    def generators(self, run):
        return (E3Generator(),)

    def executor(self) -> E3Executor:
        return self.executor_impl

    def build_evidence(self, execution, snapshot, *, evidence_id):
        if execution.result is None:
            return None
        return self.e2.build_evidence(execution, evidence_id=evidence_id)

    def assess(self, execution, evidence, *, assessment_prefix) -> AssessmentBundle:
        assessment, budget, state = self.e2.assess(
            execution, evidence, prefix=assessment_prefix
        )
        # E2's critic reports the numerical obligation; E3 declares the same
        # one, so the campaign-level obligation state maps straight across.
        obligation_state = {
            o.obligation_id: bool(state.get(o.obligation_id, False))
            for o in self.obligations.obligations
            if o.kind is ObligationKind.REQUIRED_CRITIC
        }
        return AssessmentBundle(
            assessments=(assessment,),
            uncertainty_budget=budget,
            obligation_state=obligation_state,
        )

    def update_calibration(self, execution, *, record_id):
        entry = CalibrationMemoryEntry(
            entry_id=record_id,
            kind=MemoryKind.CALIBRATION_DIAGNOSTIC,
            model_version="e3/1",
            dataset_id="e3",
            payload={
                "action_id": execution.action_id,
                "wall_seconds": execution.diagnostics["wall_seconds"],
            },
            consumed_by=(Consumer.CALIBRATION_AUDIT,),
        )
        return self.memory.record(entry)


def e3_charter() -> CampaignCharter:
    return CampaignCharter(
        campaign_id=CAMPAIGN_ID,
        terminal_decisions=(
            TerminalDecision(
                decision_id=DECISION_ID,
                statement="classify the unknown resistance against 1200 ohm",
                options=("A", "B"),
            ),
        ),
        utility_reference="e3/decision-loss/1",
    )


def e3_obligations() -> ObligationSet:
    """The campaign's PER-EVIDENCE assurance obligations.

    The adequacy obligation is deliberately NOT here. ``ObligationSet`` is
    evaluated by the Arbiter against the critic assessments of ONE evidence
    record, so a campaign-scoped scientific requirement placed in it would be
    looked for among that record's checks, never found, and would make every
    piece of evidence INCONCLUSIVE — blocking all admission. E3 demonstrates
    that failure mode in a test rather than asserting it, and routes the
    adequacy obligation through the stopping-criterion seam instead.
    """
    return ObligationSet(
        campaign_id=CAMPAIGN_ID,
        obligations=(
            ValidationObligation(
                obligation_id="critic:numerical",
                kind=ObligationKind.REQUIRED_CRITIC,
                target=CriticClass.NUMERICAL.value,
                source="e3 preregistered config",
            ),
        ),
    )


# =====================================================================
# Campaign construction
# =====================================================================

@dataclass
class E3Stack:
    """Everything one E3 world needs, sharing one belief and one Arbiter."""

    gateway: BeliefUpdateGateway
    arbiter: Arbiter
    e2: E2Harness
    harness: E3Harness
    obligation_state: ObligationState
    label: str

    def budget_ledger(
        self, *, total: float = TOTAL_BUDGET, reserved: float = 0.0
    ) -> BudgetLedger:
        """The frozen ledger, with E3's reservation policy expressed in ITS terms."""
        return BudgetLedger(
            total_budget=total,
            reserved_validation_budget=reserved,
            cost_unit=COST_UNIT,
        )

    def build_runner(
        self,
        *,
        run_id: str,
        with_adequacy_criterion: bool,
        budget: BudgetLedger | None = None,
        seed_obligation_state: bool = True,
    ) -> CampaignRunner:
        """A real CampaignRunner over the current belief state.

        ``with_adequacy_criterion=False`` is Control 1 — the EVSI-only policy,
        which is this same runner with no stopping criterion registered.

        ``seed_obligation_state`` hands the runner the assurance record that
        actually exists. E3's evidence was admitted through the M1/M3 chain in
        a different run object, so without this the runner would believe
        nothing had ever been assessed and the stop review would short-circuit
        at "obligations were never assessed" before ever reaching the
        registered criterion. The seeding uses the supported resume structure
        (``CampaignCheckpoint.obligation_state``, whose own documentation calls
        it durable scientific state that feeds the Arbiter's stopping review)
        and the value is DERIVED from the real admission outcomes, never
        asserted. That there is no other way to start a campaign from
        previously admitted evidence is one of E3's findings, not a workaround
        it is quiet about.
        """
        criteria = ()
        evaluators: dict[str, Any] = {}
        if with_adequacy_criterion:
            criterion = adequacy_stopping_criterion()
            criteria = (criterion,)
            evaluators = {
                criterion.criterion_id: AdequacyStoppingEvaluator(
                    self.obligation_state
                )
            }
        runner = CampaignRunner(
            run_id=run_id,
            charter=e3_charter(),
            harness=self.harness,
            gateway=self.gateway,
            arbiter=self.arbiter,
            obligations=self.harness.obligations,
            budget=budget if budget is not None else self.budget_ledger(),
            max_iterations=MAX_ITERATIONS,
            generators=(E3Generator(),),
            charter_version=CHARTER_VERSION,
            stopping_criteria=criteria,
            stopping_evaluators=evaluators,
        )
        if seed_obligation_state:
            runner.restore(
                CampaignCheckpoint(
                    run=runner.run,
                    events=runner.events,
                    budget=runner.budget,
                    effects=runner.effects,
                    plan=None,
                    obligation_state=self.assurance_record(),
                )
            )
        return runner

    def assurance_record(self) -> dict[str, bool]:
        """The campaign obligation state the M1/M3 chain actually established.

        Derived from the real admission outcomes: the numerical critic assessed
        every executed record and the Arbiter admitted the ones that passed.
        """
        admissions = self.e2.admissions
        return {
            "critic:numerical": bool(admissions)
            and all(r.critic_verdict == "pass" for r in admissions)
        }


def build_e3_stack(
    spec: e2_truth.TruthSpec,
    *,
    label: str,
    executor_class: type[E2Executor] = E2Executor,
) -> E3Stack:
    """Wire one world: authority, gateway, arbiter, E2 harness, E3 harness."""
    from experiments.electrical_e2.e2_harness import e2_obligations

    authority = AdmissionAuthority(f"e3.authority.{label}")
    registry = AdmissionAuthorityRegistry([authority])
    gateway = BeliefUpdateGateway(authorities=registry)
    arbiter = Arbiter(authority)
    e2 = E2Harness(
        run_id=f"{label}-chain",
        gateway=gateway,
        arbiter=arbiter,
        executor=executor_class(spec),
        obligations=e2_obligations(),
        events=CampaignEventLog(f"{label}-chain"),
    )
    harness = E3Harness(
        run_id=label,
        gateway=gateway,
        e2=e2,
        executor_impl=E3Executor(e2.executor),
        obligations=e3_obligations(),
    )
    from .e3_obligation import ObligationLedger

    return E3Stack(
        gateway=gateway,
        arbiter=arbiter,
        e2=e2,
        harness=harness,
        obligation_state=ObligationState(ledger=ObligationLedger()),
        label=label,
    )


def run_calibration(stack: E3Stack) -> tuple[Any, ...]:
    """Phase 0 — E2's calibration, through the real M1/M3 admission chain."""
    rows = []
    for repeat in range(1, CALIBRATION_ACTION.repeats + 1):
        rows.append(stack.e2.run_measurement(CALIBRATION_ACTION, repeat=repeat))
    return tuple(rows)


def swap_to_faulty_executor(stack: E3Stack) -> None:
    """CONTROL 5 — make the next execution computationally untrustworthy."""
    faulty = E2FaultyExecutor(stack.e2.executor.spec)
    stack.e2.executor = faulty
    stack.harness.executor_impl = E3Executor(faulty)
