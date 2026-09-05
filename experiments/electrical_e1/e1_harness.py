"""E1 grader + integration harness.

This module holds the two roles the decision path must not: it is the
*instrument* (the executor evaluates the real solver at the grader-only true
parameter and adds the declared benchmark noise), and it is the *wiring* that
connects the Electrical domain to the frozen M1/M3/M4/M5 machinery:

    real solver -> ExecutionRecord -> Evidence -> NumericalCritic-style
    assessment -> Arbiter -> AdmissionAuthority -> Gateway -> belief
    -> posterior reconstructed from admitted observations only

**The smallest adapter (documented, as required).** The public
``solve_circuit`` wrapper runs the full protocol lifecycle but discards
``RawSolverOutput`` — the residual norm, wall-seconds and raw diagnostics never
reach the ``ScientificResult``, and SRIA's ``ExecutionRecord``/assessment
contracts need them. Rather than modify the frozen domain, the executor
re-derives the raw output by running ``prepare``+``solve`` once more on the
same bound solver and circuit: the solve is a deterministic dense LU on an
identical matrix, so the second run is bit-identical to the one inside
``solve_circuit`` (a test asserts raw values equal the result's metrics).
Cost: one extra ~3x3 linear solve per execution.
"""

from __future__ import annotations

import dataclasses
import hashlib
from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np

from src.engcore.domains.electrical.dc import (
    ElectricalDCSolver,
    build_dc_problem,
    solve_circuit,
)
from src.engcore.scientific import Quantity
from src.engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind
from src.engcore.sria import (
    AdmissionAuthority,
    AdmissionAuthorityRegistry,
    BeliefUpdateGateway,
    CampaignCharter,
    ClaimBinding,
    ClaimType,
    DiscrepancyKind,
    Disposition,
    EnvironmentSignature,
    Evidence,
    ExecutorType,
    ModelDiscrepancy,
    ResearchAction,
    RunOutcome,
    SourceClass,
    StructureComponent,
    StructureSignature,
    SubjectModel,
    TerminalDecision,
    UncertaintyChannel,
    UncertaintyDeclaration,
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
    Consumer,
    MemoryKind,
)
from src.engcore.sria.calibration.critic import CalibrationVerdict
from src.engcore.sria.campaign import (
    AssessmentBundle,
    BudgetLedger,
    CampaignRunner,
    ExecutionRecord,
)
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

from . import e1_truth
from .e1_config import (
    ACTIONS,
    CAMPAIGN_ID,
    CHARTER_VERSION,
    COST_UNIT,
    DECISION_ID,
    E1Action,
    MAX_ITERATIONS,
    NOISE_SEED,
    THRESHOLD_OHM,
    TOTAL_BUDGET,
    VMID_METRIC,
    config_hash,
)
from .e1_model import (
    E1Observation,
    best_decision,
    build_divider_circuit,
    evsi,
    observations_digest,
    posterior_weights,
    predictive_summary,
)

SOLVER_IDENTITY = ("electrical.dc.mna", "0.1.0")
ACTION_BY_ID: Mapping[str, E1Action] = {a.action_id: a for a in ACTIONS}

E1_STRUCTURE = StructureSignature(
    structure_kind="electrical_dc_circuit",
    components=(
        StructureComponent(kind="node", multiplicity=3),
        StructureComponent(kind="resistor", multiplicity=2),
        StructureComponent(kind="dc_voltage_source", multiplicity=1),
    ),
    attributes={"formulation": "modified_nodal_analysis"},
)
E1_ENVIRONMENT = EnvironmentSignature(
    hardware_class="local.workstation.x86_64",
    precision="float64",
    solver_build=SOLVER_IDENTITY,
    runtime={"backend": "scipy.linalg.solve"},
)


def preregistration_hash() -> str:
    """SHA-256 over the decision-visible config AND the grader truth."""
    blob = f"{config_hash()}|{e1_truth.truth_hash()}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class E1MeasurementResult:
    """What one executed measurement produced. No path to belief exists here."""

    result_id: str
    action_id: str
    y_volt: float
    sigma_volt: float
    source_voltage_volt: float
    scientific_result_ref: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class E1Executor:
    """The instrument. Runs the real solver at the grader-only true R2."""

    executor_id = "e1.electrical_executor"
    executor_version = "1"

    def __init__(self, true_r2_ohm: float | None = None) -> None:
        self._true_r2 = (
            e1_truth.TRUE_R2_OHM if true_r2_ohm is None else float(true_r2_ohm)
        )
        self.calls: list[str] = []
        self.completed: dict[str, ExecutionRecord] = {}
        #: (result, raw) pairs kept for the faithfulness test.
        self.raw_by_execution: dict[str, Any] = {}

    def fetch_execution(self, execution_id: str) -> ExecutionRecord | None:
        return self.completed.get(execution_id)

    def _noise(self, execution_id: str, sigma: float) -> float:
        digest = hashlib.sha256(execution_id.encode("utf-8")).digest()
        offset = int.from_bytes(digest[:4], "big")
        rng = np.random.default_rng(NOISE_SEED + offset)
        return float(rng.normal(0.0, sigma))

    def execute(self, action, *, execution_id: str, context: Any = None):
        self.calls.append(action.action_id)
        member = action.members[0]
        spec = ACTION_BY_ID[member.action_id]

        circuit = build_divider_circuit(
            spec.source_voltage_volt, self._true_r2, circuit_id=execution_id
        )
        solver = ElectricalDCSolver()
        problem = build_dc_problem(circuit)
        solver.bind_circuit(circuit, problem.problem_id)

        # The official result through the untouched public wrapper...
        result = solve_circuit(
            circuit, run_id=execution_id, solver=solver, problem=problem
        )
        # ...and the raw output the wrapper discards, re-derived exactly
        # (deterministic direct solve on the identical assembled system).
        prepared = solver.prepare(problem)
        raw = solver.solve(prepared)
        self.raw_by_execution[execution_id] = (result, raw)

        vmid_true = result.values[VMID_METRIC].magnitude_in("volt")
        y = vmid_true + self._noise(execution_id, spec.noise_sigma_volt)

        record = ExecutionRecord(
            execution_id=execution_id,
            action_id=member.action_id,
            run_evaluation_id=f"{execution_id}-eval",
            solver_identity=SOLVER_IDENTITY,
            structure=E1_STRUCTURE,
            environment=E1_ENVIRONMENT,
            realized_cost=spec.cost,
            cost_unit=COST_UNIT,
            outcome=RunOutcome(
                disposition=Disposition.SUCCESS,
                completion_fraction=1.0,
                informative_for_pf=True,
            ),
            result=E1MeasurementResult(
                result_id=f"{execution_id}-measurement",
                action_id=member.action_id,
                y_volt=y,
                sigma_volt=spec.noise_sigma_volt,
                source_voltage_volt=spec.source_voltage_volt,
                scientific_result_ref=result.result_id,
            ),
            result_ref=result.result_id,
            provenance_ref=f"prov:{result.provenance.run_id}",
            diagnostics={
                "wall_seconds": raw.wall_seconds,
                "residual_linear_system": raw.residuals.get(
                    "linear_system", float("nan")
                ),
                "validation_status": result.validation.status.value,
                "convergence": result.convergence.value,
                "residual_atol": solver.settings.residual_atol,
            },
        )
        self.completed[execution_id] = record
        return record


# =====================================================================
# Decision-theoretic suppliers wired to the E1 posterior
# =====================================================================

class E1EvsiOutcomeModel:
    """Supplies the M4 information term as REAL EVSI from the predictive.

    Nothing here is hand-authored: the value handed to the engine is the same
    quadrature EVSI the tests bound against EVPI, computed from the posterior
    over admitted observations at scoring time.
    """

    def __init__(self, harness: "E1Harness") -> None:
        self._harness = harness

    def dependency_identity(self) -> DependencyIdentity:
        return DependencyIdentity(
            dependency_id="e1.evsi_from_predictive",
            kind=DependencyKind.OUTCOME_MODEL,
            version="1",
            state_digest=observations_digest(self._harness.current_observations()),
            detail="EVSI by quadrature over the solver-based predictive",
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
            source="e1.evsi_from_predictive",
            assumptions=(
                "declared Gaussian observation model",
                "posterior over the frozen R2 grid",
            ),
            detail=f"one-step EVSI for {spec.action_id}",
        )

    def conditional_failure_utility_gain(
        self, candidate, snapshot, objective
    ) -> ScoreComponent:
        return ScoreComponent(
            name="conditional_failure_utility_gain",
            value=0.0,
            status=ComponentStatus.AVAILABLE,
            source="e1.declared",
            detail="E1 declares no informative failure value",
        )


class E1CostSupplier:
    """Declared benchmark acquisition costs. ASSERTED_FOR_BENCHMARK."""

    def dependency_identity(self) -> DependencyIdentity:
        return DependencyIdentity(
            dependency_id="e1.declared_cost",
            kind=DependencyKind.COST_MODEL,
            version="1",
            state_digest=canonical_digest(
                {a.action_id: a.cost for a in ACTIONS}
            ),
            detail="preregistered declared costs; no fitted parameters",
        )

    def expected_cost(self, candidate, snapshot) -> ScoreComponent:
        spec = ACTION_BY_ID[candidate.members[0].action_id]
        return ScoreComponent(
            name="expected_cost",
            value=spec.cost,
            status=ComponentStatus.AVAILABLE,
            source="e1.declared_cost",
            calibration_verdict=CalibrationVerdict.TRUSTED,
            unit=COST_UNIT,
            detail="declared benchmark cost",
        )


class E1FailureSupplier:
    """p_cf = 0, declared for this deterministic computational benchmark."""

    def dependency_identity(self) -> DependencyIdentity:
        return DependencyIdentity(
            dependency_id="e1.declared_failure",
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
            source="e1.declared_failure",
            calibration_verdict=CalibrationVerdict.TRUSTED,
            detail="declared benchmark failure probability",
        )


class E1TerminalUtility:
    """u = -E[loss] of the Bayes decision under the current posterior."""

    utility_id = "e1.decision_loss"
    utility_version = "1"

    def __init__(self, harness: "E1Harness") -> None:
        self._harness = harness

    def _weights(self):
        return self._harness.posterior_for(self._harness.current_observations())

    def expected_utility(self, snapshot: BeliefSnapshot, decision_id: str) -> float:
        _, value = best_decision(self._weights())
        return value

    def expected_utility_after(
        self, snapshot: BeliefSnapshot, decision_id: str, outcome: Mapping[str, Any]
    ) -> float:
        """Genuine posterior-update semantics for a hypothetical observation."""
        observation = E1Observation(
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


class E1Generator:
    """Proposes the preregistered measurement actions. No hypothesis magic."""

    family = ActionFamily.CHARACTERIZE

    def generate(self, context: GenerationContext):
        out = []
        for spec in ACTIONS:
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
                        metadata={
                            "source_voltage_volt": spec.source_voltage_volt,
                            "noise_sigma_volt": spec.noise_sigma_volt,
                            "declared_cost": spec.cost,
                        },
                    ),
                    proposal=ActionProposal(
                        family=self.family,
                        target_ref="theta.R2",
                        rationale=spec.description,
                        expected_observable=VMID_METRIC,
                        informative_failure_causes=("numerical",),
                    ),
                )
            )
        return tuple(out)


# =====================================================================
# The harness
# =====================================================================

@dataclass
class E1Harness:
    """CampaignHarness implementation for E1."""

    gateway: BeliefUpdateGateway
    executor_impl: E1Executor
    obligations: ObligationSet
    memory: CalibrationMemory = field(default_factory=CalibrationMemory)
    #: Every EVSI/predictive computation, recorded at scoring time with the
    #: observation-set digest it was computed from. Together with the event
    #: log's hash-chained ordering (DECISION_RECOMMENDED precedes
    #: EXECUTION_STARTED) this is the proof that predictions preceded
    #: observations.
    decision_log: list[dict[str, Any]] = field(default_factory=list)
    _posterior_cache: dict[str, Any] = field(default_factory=dict)
    last_evidence: Any = None

    # -- posterior plumbing (reads the gateway, nothing else) --------------
    def current_observations(self) -> tuple[E1Observation, ...]:
        """Admitted observations ONLY. The sole entrance to the posterior."""
        out = []
        for entry in self.gateway.belief.active_view().values():
            payload = entry.claim_payload
            out.append(
                E1Observation(
                    action_id=str(payload["action_id"]),
                    source_voltage_volt=float(payload["source_voltage_volt"]),
                    y_volt=float(payload["y_volt"]),
                    sigma_volt=float(payload["sigma_volt"]),
                )
            )
        out.sort(key=lambda o: (o.action_id, o.y_volt))
        return tuple(out)

    def posterior_for(self, observations) -> Any:
        key = observations_digest(observations)
        if key not in self._posterior_cache:
            self._posterior_cache[key] = posterior_weights(observations)
        return self._posterior_cache[key]

    def record_decision_quantities(
        self, snapshot, spec, weights, observations, evsi_value
    ) -> None:
        entry = {
            "snapshot_id": snapshot.snapshot_id,
            "action_id": spec.action_id,
            "observations_digest": observations_digest(observations),
            "n_observations": len(observations),
            "evsi": evsi_value,
            "cost": spec.cost,
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
                cost_model_id="e1.declared_cost",
                cost_verdict=CalibrationVerdict.TRUSTED,
                failure_model_id="e1.declared_failure",
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
                policy_id="e1.policy",
                cost_tradeoff=CostTradeoff(
                    rate=1.0,
                    cost_unit=COST_UNIT,
                    utility_reference="e1/decision-loss/1",
                    source="e1 preregistered config",
                    assumptions=(
                        "declared benchmark cost units exchange 1:1 with "
                        "terminal loss units",
                    ),
                ),
            ),
            outcome_model=E1EvsiOutcomeModel(self),
            cost_supplier=E1CostSupplier(),
            failure_supplier=E1FailureSupplier(),
        )
        return CandidateEvaluator(engine)

    def objective(self):
        return resolve_terminal_objective(e1_charter(), E1TerminalUtility(self))

    def generation_context(self, snapshot, run) -> GenerationContext:
        return GenerationContext(snapshot=snapshot)

    def generators(self, run):
        return (E1Generator(),)

    def executor(self) -> E1Executor:
        return self.executor_impl

    # -- result -> evidence -------------------------------------------------
    def build_evidence(self, execution, snapshot, *, evidence_id) -> Evidence | None:
        measurement: E1MeasurementResult = execution.result
        if measurement is None:
            return None
        evidence = Evidence(
            evidence_id=evidence_id,
            source_class=SourceClass.SIMULATION,
            claim_type=ClaimType.QOI_VALUE,
            claim_binding=ClaimBinding(
                subject_kind="qoi",
                subject_ref=VMID_METRIC,
                qualifiers={"action_id": measurement.action_id},
            ),
            claim_payload={
                "action_id": measurement.action_id,
                "source_voltage_volt": measurement.source_voltage_volt,
                "y_volt": measurement.y_volt,
                "sigma_volt": measurement.sigma_volt,
                "result_ref": measurement.scientific_result_ref,
            },
            uncertainty=UncertaintyDeclaration(
                subject_model=SubjectModel.OBSERVATION_MODEL,
                discrepancy=ModelDiscrepancy(
                    kind=DiscrepancyKind.ZERO_DECLARED,
                    rationale=(
                        "E1 declares the linear DC model exact for this "
                        "computational verification (ASSERTED_FOR_BENCHMARK)"
                    ),
                ),
            ),
            provenance_ref=execution.provenance_ref,
            domain_pack_ref="electrical.dc.v0",
        )
        self.last_evidence = evidence
        return evidence

    def _uncertainty_budget(self, evidence, execution) -> UncertaintyBudget:
        sigma = float(evidence.claim_payload["sigma_volt"])
        atol = float(execution.diagnostics["residual_atol"])
        return UncertaintyBudget(
            value_name=evidence.belief_key,
            entries=(
                ChannelEntry(
                    channel=UncertaintyChannel.ALEATORIC,
                    state=ChannelState.KNOWN,
                    uncertainty=Uncertainty(
                        kind=UncertaintyKind.STANDARD,
                        standard_uncertainty=Quantity(sigma, "volt"),
                        source="declared benchmark observation noise",
                        method="preregistered E1 config",
                    ),
                    source="e1 observation model",
                ),
                ChannelEntry(
                    channel=UncertaintyChannel.NUMERICAL,
                    state=ChannelState.BOUNDED,
                    uncertainty=Uncertainty(
                        kind=UncertaintyKind.INTERVAL,
                        lower=Quantity(-atol, "volt"),
                        upper=Quantity(atol, "volt"),
                        source="DCValidationSettings.residual_atol",
                        method="linear-system residual check",
                    ),
                    source="electrical dc solver validation",
                ),
                ChannelEntry(
                    channel=UncertaintyChannel.MODEL_FORM,
                    state=ChannelState.NOT_APPLICABLE,
                    rationale=(
                        "zero model discrepancy is declared by the E1 charter "
                        "for this computational verification"
                    ),
                ),
            ),
            declaration=evidence.uncertainty,
        )

    def assess(self, execution, evidence, *, assessment_prefix) -> AssessmentBundle:
        residual = float(execution.diagnostics["residual_linear_system"])
        atol = float(execution.diagnostics["residual_atol"])
        termination = (
            CriticVerdict.PASS
            if execution.outcome.disposition is Disposition.SUCCESS
            else CriticVerdict.FAIL
        )
        validation_ok = (
            CriticVerdict.PASS
            if execution.diagnostics["validation_status"] == "pass"
            else CriticVerdict.FAIL
        )
        residual_ok = (
            CriticVerdict.PASS if residual <= atol else CriticVerdict.FAIL
        )
        checks = (
            CheckRecord(
                name="solver_termination",
                outcome=termination,
                mandatory=True,
                detail=f"disposition {execution.outcome.disposition.value}",
            ),
            CheckRecord(
                name="residual_evidence",
                outcome=residual_ok,
                mandatory=True,
                observed=residual,
                threshold=atol,
                threshold_source="DCValidationSettings.residual_atol",
                detail="||A x - z|| for the assembled MNA system",
            ),
            CheckRecord(
                name="validation_report_status",
                outcome=validation_ok,
                mandatory=True,
                detail=(
                    f"domain validation report: "
                    f"{execution.diagnostics['validation_status']}"
                ),
            ),
        )
        failed = any(c.outcome is CriticVerdict.FAIL for c in checks)
        verdict = CriticVerdict.FAIL if failed else CriticVerdict.PASS
        findings = ()
        if failed:
            findings = (
                Finding(
                    code="e1.solver_check_failed",
                    severity=Severity.BLOCKING,
                    category="numerical",
                    message="a mandatory solver check did not pass",
                    impact=FindingImpact.EVIDENCE_INVALIDATING,
                ),
            )
        assessment = CriticAssessment(
            assessment_id=f"{assessment_prefix}-numerical",
            critic_id="e1.numerical",
            critic_version="1",
            critic_class=CriticClass.NUMERICAL,
            subject_ref=evidence.evidence_id,
            verdict=verdict,
            provenance=AssessmentProvenance(
                assessment_id=f"{assessment_prefix}-numerical",
                critic_id="e1.numerical",
                critic_version="1",
                inputs_ref=(execution.execution_id,),
            ),
            checks=checks,
            findings=findings,
            summary=(
                f"solver termination/residual/validation checks -> "
                f"{verdict.value}"
            ),
        )
        satisfied = verdict is CriticVerdict.PASS
        state = {
            o.obligation_id: satisfied
            for o in self.obligations.obligations
            if o.kind is ObligationKind.REQUIRED_CRITIC
        }
        return AssessmentBundle(
            assessments=(assessment,),
            uncertainty_budget=self._uncertainty_budget(evidence, execution),
            obligation_state=state,
        )

    def update_calibration(self, execution, *, record_id):
        """Computational telemetry only. Never touches the posterior."""
        entry = CalibrationMemoryEntry(
            entry_id=record_id,
            kind=MemoryKind.CALIBRATION_DIAGNOSTIC,
            model_version="e1/1",
            dataset_id="e1",
            payload={
                "action_id": execution.action_id,
                "wall_seconds": execution.diagnostics["wall_seconds"],
                "residual_linear_system": execution.diagnostics[
                    "residual_linear_system"
                ],
            },
            consumed_by=(Consumer.CALIBRATION_AUDIT,),
        )
        return self.memory.record(entry)


def e1_charter() -> CampaignCharter:
    return CampaignCharter(
        campaign_id=CAMPAIGN_ID,
        terminal_decisions=(
            TerminalDecision(
                decision_id=DECISION_ID,
                statement=(
                    f"classify the unknown resistance against "
                    f"{THRESHOLD_OHM:g} ohm"
                ),
                options=("A", "B"),
            ),
        ),
        utility_reference="e1/decision-loss/1",
    )


def e1_obligations() -> ObligationSet:
    return ObligationSet(
        campaign_id=CAMPAIGN_ID,
        obligations=(
            ValidationObligation(
                obligation_id="critic:numerical",
                kind=ObligationKind.REQUIRED_CRITIC,
                target=CriticClass.NUMERICAL.value,
                source="e1 preregistered config",
            ),
        ),
    )


def build_e1_campaign(
    *, true_r2_ohm: float | None = None, run_id: str = "e1-run"
):
    """Wire the full stack: gateway, arbiter, harness, CampaignRunner."""
    authority = AdmissionAuthority("e1.authority")
    registry = AdmissionAuthorityRegistry([authority])
    gateway = BeliefUpdateGateway(authorities=registry)
    arbiter = Arbiter(authority)
    obligations = e1_obligations()
    harness = E1Harness(
        gateway=gateway,
        executor_impl=E1Executor(true_r2_ohm),
        obligations=obligations,
    )
    runner = CampaignRunner(
        run_id=run_id,
        charter=e1_charter(),
        harness=harness,
        gateway=gateway,
        arbiter=arbiter,
        obligations=obligations,
        budget=BudgetLedger(total_budget=TOTAL_BUDGET, cost_unit=COST_UNIT),
        max_iterations=MAX_ITERATIONS,
        generators=(E1Generator(),),
        charter_version=CHARTER_VERSION,
    )
    return runner, harness, gateway, arbiter
