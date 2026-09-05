"""Deterministic sequential toy campaign for M5.

Not D5, not a scientific claim, and separate from the frozen M4 benchmark. A
small exact problem whose utilities can be checked by hand, so the *sequential*
machinery is tested against arithmetic rather than against a model's opinion.

The campaign
------------
Two independent unknowns, theta and phi. The campaign must eventually decide
``pick_design``, and it values knowing both:

    u(belief) = PAYOFF * ( max(c_theta, 1 - c_theta) + max(c_phi, 1 - c_phi) )

with ``c`` the campaign's confidence in each unknown, both starting at the prior
0.5. An action that would leave confidence ``r`` in its target raises that
target's term to ``PAYOFF * max(r, 1 - r)`` and leaves the other alone, so

    gain(a) = PAYOFF * ( max(r_a, 1-r_a) - max(c_target(a), 1-c_target(a)) )
    net(a)  = gain(a) - lambda * cost(a)

is exact, closed-form, and — crucially for a *sequential* benchmark — depends on
the current belief. An action that was worth buying at iteration 1 can be worth
nothing at iteration 2 precisely because it already did its job.

Confidence only moves through admitted evidence. A result that is INCONCLUSIVE,
INVALID or never assessed leaves ``c`` exactly where it was, which is what makes
scenario 3 a real test rather than a decorative one.

PREDECLARED EXPECTATIONS
------------------------
Written down before the scenarios were run, and asserted verbatim in
``tests/test_sria_m5_campaign.py``:

  S1 belief adaptation   iter1 -> a_theta (net +3.0),  iter2 -> b_phi (net +1.5)
                         static baseline repeats a_theta for net -1.0
  S2 cost learning       iter1 -> a_theta (predicted cheap by backoff)
                         realized 6.0 completes a_theta's cost cell
                         iter2 -> b_phi, because a_theta2 now prices at ~6.0
  S3 inconclusive        no admission, belief unchanged, iteration 2 still acts
  S4 validation liveness ordinary action scores higher; deferring validation
                         would strand the obligation -> validation scheduled
  S5 stop proposal       every net <= 0 -> STOP_PROPOSAL -> review, no self-cert
  S6 resume              interrupt after execution -> resume -> nothing doubles
  NULL adaptation is irrelevant; adaptive and static agree
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from src.engcore.scientific import Quantity
from src.engcore.scientific.ir.values import IntegerValue
from src.engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind
from src.engcore.sria import (
    AdmissionAuthority,
    AdmissionAuthorityRegistry,
    AssessmentProvenance,
    BeliefUpdateGateway,
    CampaignCharter,
    ClaimBinding,
    ClaimType,
    DiscrepancyKind,
    Disposition,
    AttributedCause,
    Evidence,
    ExecutorType,
    ModelDiscrepancy,
    ResearchAction,
    RunOutcome,
    SourceClass,
    SubjectModel,
    TerminalDecision,
    UncertaintyChannel,
    UncertaintyDeclaration,
)
from src.engcore.sria.assurance.arbiter import Arbiter
from src.engcore.sria.assurance.assessment import (
    CheckRecord,
    CriticAssessment,
    CriticClass,
    CriticVerdict,
    Finding,
    FindingImpact,
    Severity,
)
from src.engcore.sria.assurance.obligations import (
    ObligationKind,
    ObligationSet,
    ValidationObligation,
)
from src.engcore.sria.assurance.uncertainty_budget import (
    ChannelEntry,
    ChannelState,
    UncertaintyBudget,
)
from src.engcore.sria.calibration import (
    CalibrationMemory,
    CalibrationMemoryEntry,
    ComputationalLearningRecord,
    Consumer,
    CostModel,
    MemoryKind,
    structure_for,
)
from src.engcore.sria.calibration.critic import CalibrationVerdict
from src.engcore.sria.calibration.ingest import CAMPAIGN_ENVIRONMENT
from src.engcore.sria.campaign import (
    AssessmentBundle,
    BudgetLedger,
    ExecutionRecord,
)
from src.engcore.sria.decision import (
    ActionFamily,
    ActionProposal,
    AtomicAction,
    BeliefSnapshot,
    CalibrationCostSupplier,
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

class InterruptedCampaign(Exception):
    """Stands in for the process dying mid-iteration."""


PAYOFF = 10.0
PRIOR = 0.5
COST_WEIGHT = 1.0
SOLVER = ("toy.sequential_solver", "1")

#: Distinct structures so the two targets occupy distinct cost-model cells.
STRUCTURE = {
    "theta": structure_for(5, 100),
    "phi": structure_for(7, 100),
}


# =====================================================================
# Campaign, utility, belief
# =====================================================================

def toy_charter(campaign_id: str = "m5-campaign") -> CampaignCharter:
    return CampaignCharter(
        campaign_id=campaign_id,
        terminal_decisions=(
            TerminalDecision(
                decision_id="pick_design",
                statement="Select the better of design_a and design_b",
                options=("design_a", "design_b"),
            ),
        ),
        utility_reference="m5/two-unknown-confidence/1",
    )


def toy_cost_tradeoff() -> CostTradeoff:
    return CostTradeoff(
        rate=COST_WEIGHT,
        cost_unit="hour",
        utility_reference="m5/two-unknown-confidence/1",
        source="m5 toy campaign charter",
        assumptions=("compute time is the only cost the campaign charges for",),
    )


def _term(confidence: float) -> float:
    return PAYOFF * max(float(confidence), 1.0 - float(confidence))


class ToyTerminalUtility:
    """u = PAYOFF * (term(c_theta) + term(c_phi)). Exact, campaign-owned."""

    utility_id = "m5.two_unknown_confidence"
    utility_version = "1"

    def expected_utility(self, snapshot: BeliefSnapshot, decision_id: str) -> float:
        return _term(snapshot.metadata.get("c_theta", PRIOR)) + _term(
            snapshot.metadata.get("c_phi", PRIOR)
        )

    def expected_utility_after(
        self, snapshot: BeliefSnapshot, decision_id: str, outcome: Mapping[str, Any]
    ) -> float:
        target = str(outcome["target"])
        reliability = float(outcome["reliability"])
        confidences = {
            "theta": float(snapshot.metadata.get("c_theta", PRIOR)),
            "phi": float(snapshot.metadata.get("c_phi", PRIOR)),
        }
        # Evidence only ever sharpens; a weaker result does not blunt belief.
        confidences[target] = max(confidences[target], reliability)
        return _term(confidences["theta"]) + _term(confidences["phi"])

    def state_digest(self) -> str:
        """Closed form in two constants — a complete description, not a stand-in."""
        return canonical_digest(
            {"form": "PAYOFF*(term(theta)+term(phi))", "payoff": PAYOFF,
             "prior": PRIOR}
        )


def ground_truth_net(
    *, target: str, reliability: float, cost: float, confidences: Mapping[str, float]
) -> float:
    """Closed-form net value. The tests' independent reference."""
    now = _term(confidences.get("theta", PRIOR)) + _term(
        confidences.get("phi", PRIOR)
    )
    after = dict(confidences)
    after[target] = max(after.get(target, PRIOR), reliability)
    return (
        _term(after.get("theta", PRIOR))
        + _term(after.get("phi", PRIOR))
        - now
        - COST_WEIGHT * cost
    )


# =====================================================================
# Actions
# =====================================================================

def toy_action(
    action_id: str,
    *,
    target: str,
    reliability: float,
    cost: float,
    family: ActionFamily = ActionFamily.EXPLORE,
    obligation_id: str = "",
) -> AtomicAction:
    metadata: dict[str, Any] = {
        "target": target,
        "reliability": reliability,
        "declared_cost": cost,
    }
    if obligation_id:
        metadata["obligation_id"] = obligation_id
    return AtomicAction(
        action=ResearchAction(
            action_id=action_id,
            executor_type=ExecutorType.SIMULATION,
            target_ref=target,
            parameters={"dimension": IntegerValue(5 if target == "theta" else 7)},
            expected_cost={"compute": Quantity(cost, "hour")},
            metadata=metadata,
        ),
        proposal=ActionProposal(
            family=family,
            target_ref=target,
            rationale=f"resolve {target} to reliability {reliability}",
            expected_observable=f"qoi.{target}",
            informative_failure_causes=("numerical",),
        ),
    )


class StaticGenerator:
    """Proposes a predeclared candidate list. No hypothesis generation."""

    def __init__(self, family: ActionFamily, actions):
        self.family = ActionFamily(family)
        self._actions = tuple(actions)

    def generate(self, context: GenerationContext):
        return tuple(a for a in self._actions if a.family is self.family)


def generators_for(actions):
    """One generator per family present. Families stay peers."""
    families = sorted({a.family for a in actions}, key=lambda f: f.value)
    return tuple(StaticGenerator(f, actions) for f in families)


# =====================================================================
# Suppliers
# =====================================================================

class ToyOutcomeModel:
    """Reads declared target and reliability. No inference."""

    def dependency_identity(self) -> DependencyIdentity:
        return DependencyIdentity(
            dependency_id="m5.outcome_model",
            kind=DependencyKind.OUTCOME_MODEL,
            version="1",
            state_digest=canonical_digest({"outcome_model": "m5.declared", "v": 1}),
            detail="stateless reader of declared target and reliability",
        )

    def conditional_success_utility_gain(
        self, candidate, snapshot, objective
    ) -> ScoreComponent:
        member = candidate.members[0]
        target = str(member.action.metadata["target"])
        reliability = max(
            float(m.action.metadata["reliability"]) for m in candidate.members
        )
        after = objective.expected_utility_after(
            snapshot, {"target": target, "reliability": reliability}
        )
        now = objective.current_expected_utility(snapshot)
        return ScoreComponent(
            name="conditional_success_utility_gain",
            value=after - now,
            status=ComponentStatus.AVAILABLE,
            source="m5.outcome_model",
            assumptions=("declared reliability is exact",),
            detail=f"{target} -> {reliability}",
        )

    def conditional_failure_utility_gain(
        self, candidate, snapshot, objective
    ) -> ScoreComponent:
        return ScoreComponent(
            name="conditional_failure_utility_gain",
            value=0.0,
            status=ComponentStatus.AVAILABLE,
            source="m5.outcome_model",
            detail="this toy campaign declares no informative failure value",
        )


class ToyFailureSupplier:
    """p_cf = 0, declared. Mirrors M2's real state honestly elsewhere."""

    def __init__(self, probability: float = 0.0):
        self._probability = probability

    def dependency_identity(self) -> DependencyIdentity:
        return DependencyIdentity(
            dependency_id="m5.failure",
            kind=DependencyKind.FAILURE_SOURCE,
            version="1",
            state_digest=canonical_digest({"p": self._probability}),
            detail="declared failure probability; no fitted parameters",
        )

    def computational_failure_probability(self, candidate, snapshot):
        return ScoreComponent(
            name="p_computational_failure",
            value=float(self._probability),
            status=ComponentStatus.AVAILABLE,
            source="m5.failure",
            calibration_verdict=CalibrationVerdict.TRUSTED,
            detail="declared toy failure probability",
        )


def cost_record(action_id: str, target: str, cost: float | None, index: int):
    return ComputationalLearningRecord(
        record_id=f"{action_id}-{index}",
        structure=STRUCTURE[target],
        environment=CAMPAIGN_ENVIRONMENT,
        solver_identity=SOLVER,
        disposition=Disposition.SUCCESS,
        realized_cost=cost,
        group_key=f"{target}-{index}",
    )


def seed_cost_model(rows: Mapping[str, tuple[float, ...]], *, dataset_id: str):
    """Fit a cost model from declared per-target rows."""
    records = []
    for target, costs in sorted(rows.items()):
        for index, cost in enumerate(costs):
            records.append(cost_record(f"seed-{target}", target, cost, index))
    return CostModel().fit(records, dataset_id=dataset_id)


def record_builder_for(action_target: Mapping[str, str]):
    """Map a candidate member to the cost cell it belongs in."""

    def build(member, snapshot):
        target = str(member.action.metadata.get("target", "theta"))
        return ComputationalLearningRecord(
            record_id=member.action_id,
            structure=STRUCTURE[target],
            environment=CAMPAIGN_ENVIRONMENT,
            solver_identity=SOLVER,
            disposition=Disposition.SUCCESS,
            group_key="query",
        )

    return build


# =====================================================================
# Executor
# =====================================================================

@dataclass
class ToyResult:
    """Stands in for a ScientificResult. Carries no path to belief."""

    result_id: str
    target: str
    reliability: float
    converged: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "target": self.target,
            "reliability": self.reliability,
            "converged": self.converged,
        }


class ToyExecutor:
    """Runs one action and reports telemetry. Knows nothing about belief."""

    executor_id = "m5.toy_executor"
    executor_version = "1"

    def __init__(self, realized_costs: Mapping[str, float] | None = None,
                 dispositions: Mapping[str, RunOutcome] | None = None,
                 crash_after_run: bool = False):
        self._realized = dict(realized_costs or {})
        self._dispositions = dict(dispositions or {})
        #: The solver finished and wrote its output, then the campaign process
        #: died before recording it — the hardest interruption window.
        self.crash_after_run = crash_after_run
        self.calls: list[str] = []
        #: Completed runs, retrievable by id — the toy stand-in for a solver
        #: that wrote its output somewhere durable.
        self.completed: dict[str, ExecutionRecord] = {}

    def fetch_execution(self, execution_id: str):
        return self.completed.get(execution_id)

    def execute(self, action, *, execution_id: str, context: Any = None):
        self.calls.append(action.action_id)
        member = action.members[0]
        target = str(member.action.metadata["target"])
        reliability = float(member.action.metadata["reliability"])
        declared = float(member.action.metadata["declared_cost"])
        realized = float(self._realized.get(action.action_id, declared))
        outcome = self._dispositions.get(
            action.action_id,
            RunOutcome(
                disposition=Disposition.SUCCESS,
                attributed_cause=AttributedCause.NONE,
                completion_fraction=1.0,
                informative_for_pf=True,
            ),
        )
        record = ExecutionRecord(
            execution_id=execution_id,
            action_id=action.action_id,
            run_evaluation_id=f"{execution_id}-eval",
            solver_identity=SOLVER,
            structure=STRUCTURE[target],
            environment=CAMPAIGN_ENVIRONMENT,
            realized_cost=realized,
            cost_unit="hour",
            outcome=outcome,
            result=ToyResult(
                result_id=f"{execution_id}-res",
                target=target,
                reliability=reliability,
                converged=outcome.disposition is Disposition.SUCCESS,
            ),
            result_ref=f"{execution_id}-res",
            provenance_ref=f"prov:{execution_id}",
            diagnostics={"target": target, "reliability": reliability},
        )
        self.completed[execution_id] = record
        if self.crash_after_run:
            raise InterruptedCampaign(
                f"the solver completed {execution_id!r} and the campaign process "
                f"died before recording it"
            )
        return record


# =====================================================================
# The harness — everything domain-specific the runner needs supplied
# =====================================================================

@dataclass
class ToyHarness:
    """Implements :class:`CampaignHarness` for the sequential toy campaign."""

    actions_by_iteration: Mapping[int, tuple]
    executor_impl: ToyExecutor
    cost_model: CostModel
    gateway: BeliefUpdateGateway
    memory: CalibrationMemory = field(default_factory=CalibrationMemory)
    critic_verdict: CriticVerdict = CriticVerdict.PASS
    obligations: ObligationSet = field(
        default_factory=lambda: ObligationSet(campaign_id="m5-campaign")
    )
    frozen_snapshot: BeliefSnapshot | None = None
    calibration_rows: list[ComputationalLearningRecord] = field(default_factory=list)
    seed_rows: list[ComputationalLearningRecord] = field(default_factory=list)
    dataset_id: str = "m5-seed"
    #: Simulates a process dying at a named step, so resume is tested against a
    #: genuine interruption rather than a rewound ledger.
    crash_at: str = ""
    #: The last candidate Evidence this harness built, for trust probes.
    last_evidence: Any = None
    _current_actions: tuple = ()

    def _maybe_crash(self, step: str) -> None:
        if self.crash_at == step:
            raise InterruptedCampaign(f"simulated interruption at {step!r}")

    # -- decision inputs ---------------------------------------------------
    def actions_for(self, run) -> tuple:
        iteration = run.iteration if run.iteration > 0 else 1
        return self.actions_by_iteration.get(
            iteration, self.actions_by_iteration[max(self.actions_by_iteration)]
        )

    @property
    def confidences(self) -> dict[str, float]:
        """Derived from the Gateway's active belief. There is no other source.

        Not a field the harness may set: if a result was not admitted, it is
        not in the active view, and it therefore cannot move confidence. That
        is what makes the INCONCLUSIVE scenario a real test.
        """
        current = {"theta": PRIOR, "phi": PRIOR}
        for entry in self.gateway.belief.active_view().values():
            payload = entry.claim_payload or {}
            target = str(payload.get("target", ""))
            reliability = payload.get("reliability")
            if target in current and reliability is not None:
                current[target] = max(current[target], float(reliability))
        return current

    def build_snapshot(self, *, snapshot_id, run, obligation_state) -> BeliefSnapshot:
        if self.frozen_snapshot is not None:
            # The static baseline: keep scoring against the first snapshot.
            return self.frozen_snapshot
        confidences = self.confidences
        return BeliefSnapshot(
            snapshot_id=snapshot_id,
            campaign_id="m5-campaign",
            charter_version="1",
            active_evidence=tuple(sorted(self.gateway.belief.active_view())),
            belief_snapshot_ref=self.gateway.belief.snapshot_ref(),
            calibration=CalibrationState(
                cost_model_id="cost.hierarchical",
                cost_verdict=CalibrationVerdict.TRUSTED,
                failure_model_id="m5.failure",
                failure_verdict=CalibrationVerdict.TRUSTED,
            ),
            obligation_state=dict(obligation_state),
            metadata={
                "c_theta": confidences["theta"],
                "c_phi": confidences["phi"],
            },
        )

    def evaluator(self) -> CandidateEvaluator:
        supplier = CalibrationCostSupplier(
            self.cost_model,
            record_builder=record_builder_for({}),
            verdict=CalibrationVerdict.TRUSTED,
            cost_unit="hour",
        )
        engine = UtilityEngine(
            policy=UtilityPolicy(
                policy_id="m5.policy", cost_tradeoff=toy_cost_tradeoff()
            ),
            outcome_model=ToyOutcomeModel(),
            cost_supplier=supplier,
            failure_supplier=ToyFailureSupplier(),
        )
        return CandidateEvaluator(engine)

    def objective(self):
        return resolve_terminal_objective(toy_charter(), ToyTerminalUtility())

    def generation_context(self, snapshot, run) -> GenerationContext:
        self._current_actions = self.actions_for(run)
        return GenerationContext(snapshot=snapshot)

    def generators(self, run):
        return generators_for(self.actions_for(run))

    def executor(self):
        return self.executor_impl

    # -- result -> evidence ------------------------------------------------
    def build_evidence(self, execution, snapshot, *, evidence_id) -> Evidence | None:
        result = execution.result
        if result is None:
            return None
        evidence = Evidence(
            evidence_id=evidence_id,
            source_class=SourceClass.SIMULATION,
            claim_type=ClaimType.QOI_VALUE,
            claim_binding=ClaimBinding(
                subject_kind="qoi", subject_ref=f"qoi.{result.target}"
            ),
            claim_payload={
                "target": result.target,
                "reliability": result.reliability,
                "result_ref": execution.result_ref,
            },
            uncertainty=UncertaintyDeclaration(
                subject_model=SubjectModel.PREDICTION_MODEL,
                discrepancy=ModelDiscrepancy(
                    kind=DiscrepancyKind.ZERO_DECLARED,
                    rationale="toy campaign declares no model discrepancy",
                ),
            ),
            provenance_ref=execution.provenance_ref,
            domain_pack_ref="m5.toy_pack",
        )
        # Kept so trust probes can reach the record the loop actually built.
        self.last_evidence = evidence
        return evidence

    def uncertainty_budget(self, evidence) -> UncertaintyBudget:
        return UncertaintyBudget(
            value_name=evidence.belief_key,
            entries=(
                ChannelEntry(
                    channel=UncertaintyChannel.NUMERICAL,
                    state=ChannelState.BOUNDED,
                    uncertainty=Uncertainty(
                        kind=UncertaintyKind.INTERVAL,
                        lower=Quantity(-0.01, "dimensionless"),
                        upper=Quantity(0.01, "dimensionless"),
                        source="toy solver residual bound",
                        method="declared by the toy executor",
                    ),
                    source="toy solver residual",
                ),
                ChannelEntry(
                    channel=UncertaintyChannel.MODEL_FORM,
                    state=ChannelState.NOT_APPLICABLE,
                    rationale="zero model discrepancy is declared by the charter",
                ),
            ),
            declaration=evidence.uncertainty,
        )

    def assess(self, execution, evidence, *, assessment_prefix) -> AssessmentBundle:
        self._maybe_crash("assess")
        termination = (
            CriticVerdict.PASS
            if execution.outcome.disposition is Disposition.SUCCESS
            else CriticVerdict.FAIL
        )
        checks = (
            CheckRecord(
                name="solver_termination",
                outcome=termination,
                mandatory=True,
                detail=f"disposition {execution.outcome.disposition.value}",
            ),
            CheckRecord(
                name="convergence_state",
                outcome=self.critic_verdict,
                mandatory=True,
                detail="declared by the toy solver",
            ),
        )
        # The verdict follows the checks; a critic may not claim PASS over a
        # mandatory check that did not pass.
        outcomes = {c.outcome for c in checks}
        if CriticVerdict.FAIL in outcomes:
            verdict = CriticVerdict.FAIL
        elif CriticVerdict.INCONCLUSIVE in outcomes:
            verdict = CriticVerdict.INCONCLUSIVE
        elif CriticVerdict.NOT_ASSESSED in outcomes:
            verdict = CriticVerdict.NOT_ASSESSED
        else:
            verdict = CriticVerdict.PASS
        # A failed mandatory check on its own is inconclusive; declaring the
        # evidence *invalid* is a stronger claim and needs an explicit
        # invalidating finding, exactly as M3 requires.
        findings = ()
        if verdict is CriticVerdict.FAIL:
            findings = (
                Finding(
                    code="toy.solver_failed",
                    severity=Severity.BLOCKING,
                    category="numerical",
                    message="the toy solver did not produce a usable result",
                    check_name="convergence_state",
                    impact=FindingImpact.EVIDENCE_INVALIDATING,
                ),
            )
        assessment = CriticAssessment(
            assessment_id=f"{assessment_prefix}-numerical",
            critic_id="m5.toy_numerical",
            critic_version="1",
            critic_class=CriticClass.NUMERICAL,
            subject_ref=evidence.evidence_id,
            verdict=verdict,
            findings=findings,
            provenance=AssessmentProvenance(
                assessment_id=f"{assessment_prefix}-numerical",
                critic_id="m5.toy_numerical",
                critic_version="1",
                inputs_ref=(execution.execution_id,),
            ),
            checks=checks,
            summary=f"toy numerical critic returned {verdict.value}",
        )
        satisfied = verdict is CriticVerdict.PASS
        state = {
            o.obligation_id: satisfied for o in self.obligations.obligations
            if o.kind is ObligationKind.REQUIRED_CRITIC
        }
        return AssessmentBundle(
            assessments=(assessment,),
            uncertainty_budget=self.uncertainty_budget(evidence),
            obligation_state=state,
        )

    # -- calibration -------------------------------------------------------
    def update_calibration(self, execution, *, record_id):
        """Computational telemetry only. It never touches scientific belief."""
        self._maybe_crash("calibrate")
        target = str(execution.diagnostics.get("target", "theta"))
        row = ComputationalLearningRecord(
            record_id=record_id,
            structure=execution.structure,
            environment=execution.environment,
            solver_identity=execution.solver_identity,
            disposition=execution.outcome.disposition,
            attributed_cause=execution.outcome.attributed_cause,
            informative_for_pf=execution.outcome.informative_for_pf,
            realized_cost=execution.realized_cost,
            cost_unit=execution.cost_unit,
            completion_fraction=execution.outcome.completion_fraction,
            group_key=f"run-{record_id}",
            provenance_ref=execution.provenance_ref,
        )
        self.calibration_rows.append(row)
        self.cost_model.fit(
            self.seed_rows + self.calibration_rows,
            dataset_id=f"{self.dataset_id}+{len(self.calibration_rows)}",
        )
        entry = CalibrationMemoryEntry(
            entry_id=record_id,
            kind=MemoryKind.COST_MODEL,
            model_version=self.cost_model.model_version,
            dataset_id=self.cost_model.training_provenance.get("dataset_id", ""),
            payload={"realized_cost": execution.realized_cost, "target": target},
            consumed_by=(Consumer.COST_PREDICTION,),
        )
        return self.memory.record(entry)



# =====================================================================
# Assurance wiring
# =====================================================================

def build_assurance(campaign_id: str = "m5-campaign"):
    authority = AdmissionAuthority("m5.authority")
    registry = AdmissionAuthorityRegistry([authority])
    gateway = BeliefUpdateGateway(authorities=registry)
    arbiter = Arbiter(authority)
    return gateway, arbiter, authority


def critic_obligation(campaign_id: str = "m5-campaign") -> ObligationSet:
    return ObligationSet(
        campaign_id=campaign_id,
        obligations=(
            ValidationObligation(
                obligation_id="critic:numerical",
                kind=ObligationKind.REQUIRED_CRITIC,
                target=CriticClass.NUMERICAL.value,
                source="m5 toy charter",
            ),
        ),
    )


def toy_budget(total: float = 20.0, reserved: float = 0.0) -> BudgetLedger:
    return BudgetLedger(
        total_budget=total, reserved_validation_budget=reserved, cost_unit="hour"
    )
