"""E2 grader + integration harness.

This module holds the two roles the decision path must not: it is the
*instrument* (it evaluates the real solver at the grader-only effective
resistance and adds the declared benchmark noise), and it is the *wiring* that
connects the Electrical domain to the frozen M1/M3 machinery:

    real solver -> ExecutionRecord -> Evidence -> numerical critic
                -> Arbiter -> AdmissionAuthority -> Gateway -> belief
                -> posterior reconstructed from admitted observations only

DELIBERATE DEVIATION FROM E1, STATED RATHER THAN HIDDEN
--------------------------------------------------------
E1 let the M5 ``CampaignRunner`` choose actions by net EVSI. E2 does not,
because E2's experimental design requires the challenge conditions to be
*preregistered*: a condition selected by the system after the calibration
posterior existed would be a condition chosen partly by the model under test,
and the predictive commitment would no longer be a commitment about an
independently fixed question. So E2 executes a frozen schedule and keeps the
part that matters for its claims — the M1 evidence/admission boundary and the
M3 critic/arbiter path — completely intact. EVSI is still computed and
reported; it just does not steer.

THE CRITIC LOOKS AT THE COMPUTATION, NOT AT THE PREDICTION
-----------------------------------------------------------
:meth:`E2Harness.assess` runs exactly three checks: solver termination, the
linear-system residual against the solver's own tolerance, and the domain
validation report. It has no access to the commitment ledger, the predictive
distribution, or the surprise statistic, and it must not acquire one. A critic
that failed evidence for being improbable under the current model would make
the model unfalsifiable — every observation capable of refuting it would be
discarded on the grounds that it refutes it.

THE SMALLEST ADAPTER (inherited from E1, documented)
-----------------------------------------------------
``solve_circuit`` discards ``RawSolverOutput``, so the residual norm and
wall-seconds never reach the ``ScientificResult`` that SRIA's contracts need.
The executor re-derives them with one extra prepare+solve on the same bound
solver — a deterministic dense LU on an identical matrix — and a test asserts
the raw values equal the wrapper's metrics exactly. The domain is not modified.
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
    ClaimBinding,
    ClaimType,
    DiscrepancyKind,
    Disposition,
    Evidence,
    EnvironmentSignature,
    ModelDiscrepancy,
    RunOutcome,
    SourceClass,
    StructureComponent,
    StructureSignature,
    SubjectModel,
    UncertaintyChannel,
    UncertaintyDeclaration,
)
from src.engcore.sria.assurance import Arbiter
from src.engcore.sria.assurance.arbiter import AssuranceVerdict
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
from src.engcore.sria.campaign import (
    CampaignEventLog,
    CampaignEventType,
    ExecutionRecord,
    deterministic_clock,
)
from src.engcore.sria.provenance import AssessmentProvenance

from . import e2_truth
from .e2_adequacy import ExecutionValidity
from .e2_config import (
    ACTIONS,
    CALIBRATION_ACTIONS,
    CHALLENGE_ACTIONS,
    COST_UNIT,
    E2Action,
    NOISE_SEED,
    VMID_METRIC,
    config_hash,
)
from .e2_model import E2Observation, build_divider_circuit, observations_digest

SOLVER_IDENTITY = ("electrical.dc.mna", "0.1.0")
ACTION_BY_ID: Mapping[str, E2Action] = {a.action_id: a for a in ACTIONS}

E2_STRUCTURE = StructureSignature(
    structure_kind="electrical_dc_circuit",
    components=(
        StructureComponent(kind="node", multiplicity=3),
        StructureComponent(kind="resistor", multiplicity=2),
        StructureComponent(kind="dc_voltage_source", multiplicity=1),
    ),
    attributes={"formulation": "modified_nodal_analysis"},
)
E2_ENVIRONMENT = EnvironmentSignature(
    hardware_class="local.workstation.x86_64",
    precision="float64",
    solver_build=SOLVER_IDENTITY,
    runtime={"backend": "scipy.linalg.solve"},
)


def preregistration_hash() -> str:
    """SHA-256 over the decision-visible config AND the grader truth."""
    blob = f"{config_hash()}|{e2_truth.truth_hash()}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def benchmark_noise(action_id: str, repeat: int, sigma: float) -> float:
    """The declared benchmark noise draw for one measurement.

    Depends on (action_id, repeat) and nothing else — in particular NOT on
    which control is running. Control A and the scored misspecified run
    therefore receive bit-identical noise and differ only through the hidden
    law, which is what makes the comparison between them a comparison of models
    rather than of luck.
    """
    digest = hashlib.sha256(f"{action_id}|{repeat}".encode("utf-8")).digest()
    offset = int.from_bytes(digest[:4], "big")
    rng = np.random.default_rng(NOISE_SEED + offset)
    return float(rng.normal(0.0, sigma))


@dataclass(frozen=True)
class E2MeasurementResult:
    """What one executed measurement produced. No path to belief exists here."""

    result_id: str
    action_id: str
    repeat: int
    y_volt: float
    sigma_volt: float
    source_voltage_volt: float
    scientific_result_ref: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class E2Executor:
    """The instrument. Runs the real solver at the grader-only R_eff(Vs)."""

    executor_id = "e2.electrical_executor"
    executor_version = "1"

    def __init__(self, spec: e2_truth.TruthSpec) -> None:
        self._spec = spec
        self.completed: dict[str, ExecutionRecord] = {}
        self.raw_by_execution: dict[str, Any] = {}
        self.effective_resistance_by_execution: dict[str, float] = {}

    @property
    def spec(self) -> e2_truth.TruthSpec:
        return self._spec

    def execute(
        self, spec_action: E2Action, *, repeat: int, execution_id: str
    ) -> ExecutionRecord:
        r_eff = self._spec.effective_resistance(spec_action.source_voltage_volt)
        circuit = build_divider_circuit(
            spec_action.source_voltage_volt, r_eff, circuit_id=execution_id
        )
        solver = ElectricalDCSolver()
        problem = build_dc_problem(circuit)
        solver.bind_circuit(circuit, problem.problem_id)

        # The official result through the untouched public wrapper...
        result = solve_circuit(
            circuit, run_id=execution_id, solver=solver, problem=problem
        )
        # ...and the raw output the wrapper discards, re-derived exactly.
        prepared = solver.prepare(problem)
        raw = solver.solve(prepared)
        self.raw_by_execution[execution_id] = (result, raw)
        self.effective_resistance_by_execution[execution_id] = r_eff

        vmid_true = result.values[VMID_METRIC].magnitude_in("volt")
        y = (
            vmid_true
            + benchmark_noise(
                spec_action.action_id, repeat, spec_action.noise_sigma_volt
            )
            + self._spec.outlier_for(spec_action.action_id)
        )

        record = ExecutionRecord(
            execution_id=execution_id,
            action_id=spec_action.action_id,
            run_evaluation_id=f"{execution_id}-eval",
            solver_identity=SOLVER_IDENTITY,
            structure=E2_STRUCTURE,
            environment=E2_ENVIRONMENT,
            realized_cost=spec_action.cost,
            cost_unit=COST_UNIT,
            outcome=RunOutcome(
                disposition=Disposition.SUCCESS,
                completion_fraction=1.0,
                informative_for_pf=True,
            ),
            result=E2MeasurementResult(
                result_id=f"{execution_id}-measurement",
                action_id=spec_action.action_id,
                repeat=repeat,
                y_volt=y,
                sigma_volt=spec_action.noise_sigma_volt,
                source_voltage_volt=spec_action.source_voltage_volt,
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


class E2FaultyExecutor(E2Executor):
    """CONTROL D — a genuinely broken computation.

    A test double, not a dangerous physical case: it returns an execution whose
    linear-system residual is far above the solver's own tolerance and whose
    validation report failed. The resulting number may be numerically close to
    the truth, and that is the point — the reason it is rejected is that the
    computation did not check out, not that anyone disliked its value.
    """

    executor_id = "e2.faulty_executor"

    def execute(
        self, spec_action: E2Action, *, repeat: int, execution_id: str
    ) -> ExecutionRecord:
        record = super().execute(
            spec_action, repeat=repeat, execution_id=execution_id
        )
        diagnostics = dict(record.diagnostics)
        atol = float(diagnostics["residual_atol"])
        diagnostics["residual_linear_system"] = atol * 1.0e6
        diagnostics["validation_status"] = "fail"
        diagnostics["convergence"] = "failed"
        broken = dataclasses.replace(
            record,
            outcome=RunOutcome(
                disposition=Disposition.FAILED,
                completion_fraction=0.4,
                informative_for_pf=True,
            ),
            diagnostics=diagnostics,
        )
        self.completed[execution_id] = broken
        return broken


# =====================================================================
# Evidence, assessment and the admission chain
# =====================================================================

@dataclass
class AdmissionOutcomeRecord:
    """What happened to one executed measurement, end to end."""

    action_id: str
    repeat: int
    execution_id: str
    evidence_id: str
    y_volt: float
    critic_verdict: str
    arbiter_verdict: str
    admitted: bool
    execution_validity: ExecutionValidity
    checks: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        payload = dataclasses.asdict(self)
        payload["execution_validity"] = self.execution_validity.value
        payload["checks"] = [dict(c) for c in self.checks]
        return payload


@dataclass
class E2Harness:
    """Executor + critic + arbiter + gateway, driven by a frozen schedule."""

    run_id: str
    gateway: BeliefUpdateGateway
    arbiter: Arbiter
    executor: E2Executor
    obligations: ObligationSet
    events: CampaignEventLog
    admissions: list[AdmissionOutcomeRecord] = field(default_factory=list)
    _step: int = 0

    # -- posterior plumbing (reads the gateway, nothing else) --------------
    def current_observations(self) -> tuple[E2Observation, ...]:
        """Admitted observations ONLY. The sole entrance to the posterior."""
        out = []
        for entry in self.gateway.belief.active_view().values():
            payload = entry.claim_payload
            out.append(
                E2Observation(
                    action_id=str(payload["action_id"]),
                    source_voltage_volt=float(payload["source_voltage_volt"]),
                    y_volt=float(payload["y_volt"]),
                    sigma_volt=float(payload["sigma_volt"]),
                )
            )
        out.sort(key=lambda o: (o.action_id, o.y_volt))
        return tuple(out)

    def evidence_snapshot_digest(self) -> str:
        return observations_digest(self.current_observations())

    # -- result -> evidence -------------------------------------------------
    def build_evidence(
        self, execution: ExecutionRecord, *, evidence_id: str
    ) -> Evidence:
        measurement: E2MeasurementResult = execution.result
        return Evidence(
            evidence_id=evidence_id,
            source_class=SourceClass.SIMULATION,
            claim_type=ClaimType.QOI_VALUE,
            claim_binding=ClaimBinding(
                subject_kind="qoi",
                subject_ref=VMID_METRIC,
                qualifiers={
                    "action_id": measurement.action_id,
                    "repeat": str(measurement.repeat),
                },
            ),
            claim_payload={
                "action_id": measurement.action_id,
                "repeat": measurement.repeat,
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
                        "SCOPE: this declares zero discrepancy for the "
                        "OBSERVATION model only — y measures node_voltage:mid "
                        "with the declared Gaussian noise, which is exactly "
                        "true of this benchmark. It says NOTHING about the "
                        "assumed constant-R inference family, whose adequacy "
                        "is what E2 is testing. The frozen DiscrepancyKind "
                        "enum offers only ZERO_DECLARED and CONSTRAINED_PRIOR, "
                        "so 'under test, not established' cannot be expressed "
                        "here; E2 records that as an architecture gap rather "
                        "than overstating the declaration or editing src/"
                    ),
                ),
            ),
            provenance_ref=execution.provenance_ref,
            domain_pack_ref="electrical.dc.v0",
        )

    def _uncertainty_budget(
        self, evidence: Evidence, execution: ExecutionRecord
    ) -> UncertaintyBudget:
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
                        method="preregistered E2 config",
                    ),
                    source="e2 observation model",
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
                    state=ChannelState.UNKNOWN,
                    rationale=(
                        "the adequacy of the assumed constant-R family is "
                        "exactly what E2 is testing; declaring this channel "
                        "NOT_APPLICABLE — as E1 legitimately could for its own "
                        "well-specified problem — would assume the answer. "
                        "UNKNOWN does not block admission here because E2's "
                        "charter requires no uncertainty channel to be "
                        "quantified, which is correct for execution validity "
                        "and is precisely why nothing in the frozen stack "
                        "notices that the family is on trial"
                    ),
                ),
            ),
            declaration=evidence.uncertainty,
        )

    def assess(
        self, execution: ExecutionRecord, evidence: Evidence, *, prefix: str
    ) -> tuple[CriticAssessment, UncertaintyBudget, dict[str, bool]]:
        """Numerical critic. Computation only — never the predictive.

        There is no ledger, no posterior and no surprise statistic in scope
        here, and that is a design constraint rather than an oversight.
        """
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
        residual_ok = CriticVerdict.PASS if residual <= atol else CriticVerdict.FAIL
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
                    code="e2.solver_check_failed",
                    severity=Severity.BLOCKING,
                    category="numerical",
                    message="a mandatory solver check did not pass",
                    impact=FindingImpact.EVIDENCE_INVALIDATING,
                ),
            )
        assessment = CriticAssessment(
            assessment_id=f"{prefix}-numerical",
            critic_id="e2.numerical",
            critic_version="1",
            critic_class=CriticClass.NUMERICAL,
            subject_ref=evidence.evidence_id,
            verdict=verdict,
            provenance=AssessmentProvenance(
                assessment_id=f"{prefix}-numerical",
                critic_id="e2.numerical",
                critic_version="1",
                inputs_ref=(execution.execution_id,),
            ),
            checks=checks,
            findings=findings,
            summary=(
                f"solver termination/residual/validation checks -> "
                f"{verdict.value} (computation only; predictive surprise is "
                f"not an input to this critic)"
            ),
        )
        state = {
            o.obligation_id: verdict is CriticVerdict.PASS
            for o in self.obligations.obligations
            if o.kind is ObligationKind.REQUIRED_CRITIC
        }
        return assessment, self._uncertainty_budget(evidence, execution), state

    # -- the full chain -----------------------------------------------------
    def run_measurement(
        self, spec_action: E2Action, *, repeat: int
    ) -> AdmissionOutcomeRecord:
        """execute -> evidence -> critic -> arbiter -> authority -> gateway."""
        self._step += 1
        step = self._step
        clock = deterministic_clock(f"{self.run_id}-{step}")
        execution_id = f"{self.run_id}-exec-{step:03d}-{spec_action.action_id}"

        self.events.append(
            CampaignEventType.EXECUTION_STARTED,
            iteration=step,
            payload={"action_id": spec_action.action_id, "repeat": repeat},
            at=clock(),
        )
        execution = self.executor.execute(
            spec_action, repeat=repeat, execution_id=execution_id
        )
        self.events.append(
            CampaignEventType.EXECUTION_COMPLETED,
            iteration=step,
            payload={"execution_id": execution_id},
            at=clock(),
        )

        evidence_id = f"{self.run_id}-ev-{step:03d}"
        evidence = self.build_evidence(execution, evidence_id=evidence_id)
        self.events.append(
            CampaignEventType.EVIDENCE_CREATED,
            iteration=step,
            payload={"evidence_id": evidence_id},
            at=clock(),
        )

        assessment, budget, obligation_state = self.assess(
            execution, evidence, prefix=f"{self.run_id}-assess-{step:03d}"
        )
        self.events.append(
            CampaignEventType.CRITICS_COMPLETED,
            iteration=step,
            payload={"verdict": assessment.verdict.value},
            at=clock(),
        )

        decision = self.arbiter.decide(
            decision_id=f"{self.run_id}-arb-{step:03d}",
            subject_ref=evidence.evidence_id,
            assessments=(assessment,),
            obligations=self.obligations,
            budget=budget,
            decided_at=clock(),
        )
        self.events.append(
            CampaignEventType.ARBITER_DECIDED,
            iteration=step,
            payload={"verdict": decision.verdict.value},
            at=clock(),
        )

        assessed = evidence.with_assessment(
            assessment.to_evidence_assessment(),
            reason=f"critic {assessment.critic_id}",
            actor=assessment.critic_id,
            at=clock(),
        )

        admitted = False
        if decision.verdict is AssuranceVerdict.VALID:
            declaration = self.arbiter.authorize_admission(
                decision,
                assessed,
                rationale=f"{self.run_id} step {step}",
            )
            accepted = assessed.admit(declaration, actor=self.run_id, at=clock())
            self.gateway.submit(accepted)
            admitted = True
            self.events.append(
                CampaignEventType.EVIDENCE_ADMITTED,
                iteration=step,
                payload={
                    "evidence_id": evidence_id,
                    "belief_size": len(self.gateway.belief),
                },
                at=clock(),
            )
        else:
            self.events.append(
                CampaignEventType.EVIDENCE_NOT_ADMITTED,
                iteration=step,
                payload={
                    "evidence_id": evidence_id,
                    "verdict": decision.verdict.value,
                },
                at=clock(),
            )

        validity = (
            ExecutionValidity.VALID
            if decision.verdict is AssuranceVerdict.VALID
            else ExecutionValidity.INVALID
        )
        record = AdmissionOutcomeRecord(
            action_id=spec_action.action_id,
            repeat=repeat,
            execution_id=execution_id,
            evidence_id=evidence_id,
            y_volt=float(execution.result.y_volt),
            critic_verdict=assessment.verdict.value,
            arbiter_verdict=decision.verdict.value,
            admitted=admitted,
            execution_validity=validity,
            checks=tuple(
                {
                    "name": c.name,
                    "outcome": c.outcome.value,
                    "observed": c.observed,
                    "threshold": c.threshold,
                }
                for c in assessment.checks
            ),
        )
        self.admissions.append(record)
        return record

    def run_phase(
        self, actions: tuple[E2Action, ...]
    ) -> tuple[AdmissionOutcomeRecord, ...]:
        out: list[AdmissionOutcomeRecord] = []
        for spec_action in actions:
            for repeat in range(1, spec_action.repeats + 1):
                out.append(self.run_measurement(spec_action, repeat=repeat))
        return tuple(out)

    def run_calibration_phase(self) -> tuple[AdmissionOutcomeRecord, ...]:
        return self.run_phase(CALIBRATION_ACTIONS)

    def run_challenge_phase(self) -> tuple[AdmissionOutcomeRecord, ...]:
        return self.run_phase(CHALLENGE_ACTIONS)


def e2_obligations() -> ObligationSet:
    return ObligationSet(
        campaign_id="e2-electrical",
        obligations=(
            ValidationObligation(
                obligation_id="critic:numerical",
                kind=ObligationKind.REQUIRED_CRITIC,
                target=CriticClass.NUMERICAL.value,
                source="e2 preregistered config",
            ),
        ),
    )


def build_e2_harness(
    spec: e2_truth.TruthSpec,
    *,
    run_id: str = "e2-run",
    executor_class: type[E2Executor] = E2Executor,
) -> E2Harness:
    """Wire a fresh, independent stack: authority, gateway, arbiter, harness."""
    authority = AdmissionAuthority(f"e2.authority.{run_id}")
    registry = AdmissionAuthorityRegistry([authority])
    gateway = BeliefUpdateGateway(authorities=registry)
    return E2Harness(
        run_id=run_id,
        gateway=gateway,
        arbiter=Arbiter(authority),
        executor=executor_class(spec),
        obligations=e2_obligations(),
        events=CampaignEventLog(run_id),
    )
