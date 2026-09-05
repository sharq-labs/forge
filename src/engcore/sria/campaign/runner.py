"""M5 — the bounded sequential campaign runner.

One iteration is: build a fresh coherent snapshot, generate candidates from all
six families, score them through M4, select exactly one action, execute it,
turn the result into candidate evidence, assess it, ask the Arbiter, admit only
what is authorized, update computational calibration, and record everything.
Then do it again against a *new* snapshot.

Three properties this module is built around.

**It orchestrates; it does not adjudicate.** The runner never writes belief,
never decides validity, never certifies completion. It calls the frozen
components in order and records what they said. Every refusal they can make —
``INVALID``, ``INCONCLUSIVE``, ``NOT_ASSESSED``, an unverified decision basis, a
budget it cannot afford — is a legal outcome the loop carries forward rather
than an exception it swallows.

**No research mode.** There is no ``current_family`` and no branch anywhere in
this file that reads an action family to decide what to do next. Families are
generator labels; every candidate they produce enters the same ranking. The one
place family membership matters is budget: VALIDATE may draw on the reservation,
which is M4's frozen rule, not a mode.

**Every side effect happens at most once.** Execution, budget settlement,
evidence creation, admission and calibration all pass through the effect ledger,
so an interrupted run resumes without re-executing a simulation, double-charging
a budget, or admitting one experiment as two pieces of evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol, Sequence, runtime_checkable

from ..assurance.arbiter import Arbiter, AssuranceVerdict
from ..assurance.assessment import CriticAssessment
from ..assurance.obligations import ObligationSet
from ..charter import CampaignCharter
from ..decision.actions import ActionFamily, CandidateAction
from ..decision.belief_snapshot import BeliefSnapshot
from ..decision.coherence import pin_decision_basis
from ..decision.families import (
    ActionFamilyGenerator,
    DEFAULT_GENERATORS,
    GenerationContext,
    generate_candidates,
)
from ..decision.recommendation import (
    CandidateEvaluator,
    DecisionRecommendation,
    RecommendationOutcome,
)
from ..decision.terminal import TerminalObjective
from ..errors import ReservedNotImplemented
from ..evidence import Evidence
from ..gateway import BeliefUpdateGateway
from .budget import BudgetExhausted, BudgetLedger
from ..decision.replay import candidate_decision_identity, canonical_digest
from .certification import CertificationRequirement
from .checkpoint import (
    CampaignCheckpoint,
    CheckpointStore,
    EffectLedger,
    IterationPlan,
)
from .events import CampaignEventLog, CampaignEventType
from .executor import ExecutionRecord, SimulationExecutor, require_simulation
from .liveness import (
    LivenessRuling,
    LivenessStatus,
    ValidationLivenessPolicy,
    validation_targets,
)
from .state import CampaignRun, ExecutionState, IterationRecord, PauseReason
from .stopping import (
    ArbiterStoppingReview,
    StopProposal,
    StopReview,
    StoppingCriterion,
)

#: Outcomes from which no action can be selected. Each is a legal answer.
_NON_SELECTING = frozenset(
    {
        RecommendationOutcome.STOP_PROPOSAL,
        RecommendationOutcome.DECISION_INCOMPLETE,
        RecommendationOutcome.NO_SCORABLE_CANDIDATE,
        RecommendationOutcome.TERMINAL_OBJECTIVE_UNAVAILABLE,
        RecommendationOutcome.STATE_INCOHERENT,
        RecommendationOutcome.DECISION_BASIS_UNVERIFIED,
    }
)


@dataclass(frozen=True)
class AssessmentBundle:
    """What the critics produced, plus the uncertainty budget they saw."""

    assessments: tuple[CriticAssessment, ...] = ()
    uncertainty_budget: Any | None = None
    obligation_state: Mapping[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "assessments", tuple(self.assessments))
        object.__setattr__(self, "obligation_state", dict(self.obligation_state))


@runtime_checkable
class CampaignHarness(Protocol):
    """Everything domain- or solver-specific the loop needs supplied.

    The runner knows none of this. It does not know what a solver is, what the
    campaign is studying, or how a result becomes a claim — it knows only that
    something must supply each step and that each step may refuse.
    """

    def build_snapshot(
        self,
        *,
        snapshot_id: str,
        run: CampaignRun,
        obligation_state: Mapping[str, bool],
    ) -> BeliefSnapshot:
        ...

    def evaluator(self) -> CandidateEvaluator:
        ...

    def objective(self) -> TerminalObjective:
        ...

    def generation_context(
        self, snapshot: BeliefSnapshot, run: CampaignRun
    ) -> GenerationContext:
        ...

    def executor(self) -> SimulationExecutor:
        ...

    def build_evidence(
        self,
        execution: ExecutionRecord,
        snapshot: BeliefSnapshot,
        *,
        evidence_id: str,
    ) -> Evidence | None:
        ...

    def assess(
        self,
        execution: ExecutionRecord,
        evidence: Evidence,
        *,
        assessment_prefix: str,
    ) -> AssessmentBundle:
        ...

    def update_calibration(
        self, execution: ExecutionRecord, *, record_id: str
    ) -> Any | None:
        ...


def deterministic_clock(run_id: str) -> Callable[[], str]:
    """A monotone label generator. No wall clock, so runs are reproducible."""
    counter = {"n": 0}

    def tick() -> str:
        counter["n"] += 1
        return f"{run_id}/t{counter['n']:04d}"

    return tick


class CampaignRunner:
    """Drives one bounded campaign run. Composition, not a god object."""

    def __init__(
        self,
        *,
        run_id: str,
        charter: CampaignCharter,
        harness: CampaignHarness,
        gateway: BeliefUpdateGateway,
        arbiter: Arbiter,
        obligations: ObligationSet,
        budget: BudgetLedger,
        max_iterations: int = 3,
        generators: Sequence[ActionFamilyGenerator] = DEFAULT_GENERATORS,
        liveness: ValidationLivenessPolicy | None = None,
        stopping: ArbiterStoppingReview | None = None,
        stopping_criteria: Sequence[StoppingCriterion] = (),
        stopping_evaluators: Mapping[str, Any] | None = None,
        certification_requirements: Sequence[CertificationRequirement] = (),
        checkpoints: CheckpointStore | None = None,
        clock: Callable[[], str] | None = None,
        charter_version: str = "1",
    ) -> None:
        self._charter = charter
        self._harness = harness
        self._gateway = gateway
        self._arbiter = arbiter
        self._obligations = obligations
        self._budget = budget
        self._generators = tuple(generators)
        self._liveness = liveness or ValidationLivenessPolicy()
        # Stopping review is Arbiter-owned. The runner cannot construct a
        # reviewer without one, and the reviewer cannot approve without a
        # genuine ArbiterDecision.
        self._stopping = stopping or ArbiterStoppingReview(arbiter)
        self._stopping_criteria = tuple(stopping_criteria)
        self._stopping_evaluators = dict(stopping_evaluators or {})
        # V0.1 — finite, declared certification evidence. An economic stop does
        # not discharge it, and it carries no status of its own: see
        # _satisfied_certification_actions.
        self._certification_requirements = tuple(certification_requirements)
        self._checkpoints = checkpoints or CheckpointStore()
        self._clock = clock or deterministic_clock(run_id)
        self._charter_version = charter_version

        self._events = CampaignEventLog(run_id)
        self._effects = EffectLedger()
        self._run = CampaignRun(
            run_id=run_id,
            campaign_id=charter.campaign_id,
            charter_version=charter_version,
            state=ExecutionState.CREATED,
            max_iterations=max_iterations,
        )
        self._plan: IterationPlan | None = None
        self._obligation_state: dict[str, bool] = {}
        self._rulings: list[LivenessRuling] = []
        self._reviews: list[StopReview] = []
        self._recommendations: dict[str, DecisionRecommendation] = {}
        self._snapshots: dict[int, BeliefSnapshot] = {}

        self._events.append(
            CampaignEventType.CAMPAIGN_CREATED,
            iteration=0,
            payload={
                "campaign_id": charter.campaign_id,
                "charter_version": charter_version,
                "max_iterations": max_iterations,
                "total_budget": budget.total_budget,
                "reserved_validation_budget": budget.reserved_validation_budget,
            },
            at=self._clock(),
        )
        self._advance(ExecutionState.READY)

    # -- accessors ---------------------------------------------------------
    @property
    def run(self) -> CampaignRun:
        return self._run

    @property
    def events(self) -> CampaignEventLog:
        return self._events

    @property
    def budget(self) -> BudgetLedger:
        return self._budget

    @property
    def effects(self) -> EffectLedger:
        return self._effects

    @property
    def checkpoints(self) -> CheckpointStore:
        return self._checkpoints

    @property
    def liveness_rulings(self) -> tuple[LivenessRuling, ...]:
        return tuple(self._rulings)

    @property
    def stop_reviews(self) -> tuple[StopReview, ...]:
        return tuple(self._reviews)

    def recommendation(self, recommendation_id: str) -> DecisionRecommendation | None:
        return self._recommendations.get(recommendation_id)

    def snapshot(self, iteration: int) -> BeliefSnapshot | None:
        return self._snapshots.get(iteration)

    # -- internals ---------------------------------------------------------
    def _advance(self, state: ExecutionState, **changes: Any) -> CampaignRun:
        import dataclasses

        self._run = dataclasses.replace(
            self._run,
            state=state,
            event_log_digest=self._events.head_digest,
            **changes,
        )
        return self._run

    def _checkpoint(self) -> CampaignCheckpoint:
        return self._checkpoints.save(
            CampaignCheckpoint(
                run=self._run,
                events=CampaignEventLog(self._run.run_id, self._events.events),
                budget=BudgetLedger(
                    total_budget=self._budget.total_budget,
                    reserved_validation_budget=self._budget.reserved_validation_budget,
                    charges=self._budget.charges,
                    cost_unit=self._budget.cost_unit,
                ),
                effects=EffectLedger(applied=dict(self._effects.applied)),
                plan=self._plan,
                obligation_state=dict(self._obligation_state),
            )
        )

    @property
    def plan(self) -> IterationPlan | None:
        """The in-flight iteration's stored decision artifacts, if any."""
        return self._plan

    def _pause(self, reason: PauseReason, detail: str, iteration: int) -> CampaignRun:
        self._events.append(
            CampaignEventType.CAMPAIGN_PAUSED,
            iteration=iteration,
            payload={"reason": reason.value, "detail": detail},
            at=self._clock(),
        )
        run = self._advance(ExecutionState.PAUSED, pause_reason=reason)
        self._checkpoint()
        return run

    # -- the loop ----------------------------------------------------------
    def run_campaign(self) -> CampaignRun:
        """Iterate until paused, completed, or the declared ceiling is hit."""
        while not self._run.is_terminal and self._run.state is not ExecutionState.PAUSED:
            if self._run.iteration >= self._run.max_iterations:
                self._events.append(
                    CampaignEventType.CAMPAIGN_COMPLETED,
                    iteration=self._run.iteration,
                    payload={"reason": "iteration ceiling reached"},
                    at=self._clock(),
                )
                self._advance(ExecutionState.COMPLETED)
                self._checkpoint()
                break
            self.step()
        return self._run

    def step(self) -> CampaignRun:
        """Execute exactly one iteration, or finish an interrupted one.

        Whether this advances or resumes is read from the event log rather than
        from a flag: an iteration that never logged ``ITERATION_COMPLETED`` is
        still in progress, and re-entering it is the resume path. Every side
        effect inside is guarded, so re-entry costs nothing and repeats nothing.
        """
        current = self._run.iteration
        interrupted = current > 0 and not self._events.has(
            CampaignEventType.ITERATION_COMPLETED, iteration=current
        )
        iteration = current if interrupted else current + 1

        # The ceiling is enforced here, not only in the loop, so that a resume
        # on an already-finished campaign cannot quietly buy one more action.
        if iteration > self._run.max_iterations:
            self._events.append(
                CampaignEventType.CAMPAIGN_COMPLETED,
                iteration=current,
                payload={
                    "reason": "iteration ceiling reached",
                    "max_iterations": self._run.max_iterations,
                },
                at=self._clock(),
            )
            self._advance(ExecutionState.COMPLETED)
            self._checkpoint()
            return self._run

        self._advance(ExecutionState.DECIDING, iteration=iteration)

        # A resume continues the stored plan. It does not rebuild the snapshot,
        # regenerate candidates, re-rank, or replace the selected action — all
        # four would be a new decision wearing the old iteration's number.
        if interrupted and self._plan is not None and self._plan.iteration == iteration:
            return self._execute_and_assess(
                iteration=iteration,
                action=self._plan.action,
                snapshot=self._plan.snapshot,
                recommendation=self._plan.recommendation,
                predicted_cost=self._plan.predicted_cost,
                liveness=None,
                resumed=True,
            )
        if interrupted and self._events.has(
            CampaignEventType.ACTION_SELECTED, iteration=iteration
        ):
            # Selected, but the plan is missing. Refuse rather than re-decide.
            self._events.append(
                CampaignEventType.CAMPAIGN_PAUSED,
                iteration=iteration,
                payload={
                    "reason": PauseReason.OPERATOR_REQUESTED.value,
                    "detail": (
                        "an action was selected but its decision artifacts were "
                        "not persisted; resuming would require re-deciding, "
                        "which is not a resume"
                    ),
                },
                at=self._clock(),
            )
            run = self._advance(
                ExecutionState.PAUSED, pause_reason=PauseReason.OPERATOR_REQUESTED
            )
            self._checkpoint()
            return run

        # ---- 1. a fresh, coherent snapshot -------------------------------
        snapshot = self._fresh_snapshot(iteration)
        self._snapshots[iteration] = snapshot

        # ---- 2. candidates from every applicable family ------------------
        context = self._harness.generation_context(snapshot, self._run)
        candidates = generate_candidates(context, self._active_generators())
        self._events.append(
            CampaignEventType.CANDIDATES_GENERATED,
            iteration=iteration,
            payload={
                "count": len(candidates),
                "action_ids": [c.action_id for c in candidates],
                "families": sorted({c.family.value for c in candidates}),
            },
            at=self._clock(),
        )
        if not candidates:
            return self._pause(
                PauseReason.NO_SCORABLE_CANDIDATE,
                "no generator proposed a candidate",
                iteration,
            )

        # ---- 3. score through the frozen M4 engine -----------------------
        evaluator = self._harness.evaluator()
        recommendation = evaluator.evaluate(
            recommendation_id=f"{self._run.run_id}-rec-{iteration}",
            candidates=candidates,
            snapshot=snapshot,
            objective=self._harness.objective(),
            budget=self._budget.to_plan(),
            charter_version=self._charter_version,
        )
        self._recommendations[recommendation.recommendation_id] = recommendation
        self._events.append(
            CampaignEventType.DECISION_RECOMMENDED,
            iteration=iteration,
            payload={
                "recommendation_id": recommendation.recommendation_id,
                "outcome": recommendation.outcome.value,
                "chosen_action_id": recommendation.chosen_action_id,
                "coherence": (
                    recommendation.coherence.status.value
                    if recommendation.coherence
                    else ""
                ),
                "snapshot_digest": recommendation.snapshot_digest,
            },
            at=self._clock(),
        )

        # ---- 4. validation liveness, then selection ----------------------
        selected, ruling = self._select(
            iteration, candidates, recommendation, snapshot
        )
        if ruling is not None:
            self._rulings.append(ruling)

        if selected is None:
            return self._handle_no_selection(
                iteration, recommendation, snapshot, candidates
            )

        self._events.append(
            CampaignEventType.ACTION_SELECTED,
            iteration=iteration,
            payload={
                "action_id": selected.action_id,
                "family": selected.family.value,
                "is_composite": selected.is_composite,
                "liveness_override": bool(ruling and ruling.overrides),
                "liveness_reason": ruling.reason if ruling else "",
                "displaced_action_id": (
                    ruling.displaced_action_id if ruling and ruling.overrides else ""
                ),
                # Why this action is being executed, recorded as what it is. A
                # certification requirement is not positive information value
                # and is not written down as though it were.
                "execution_reason": self._execution_reason(
                    selected, recommendation, ruling
                ),
                # The prediction this action is answerable to, captured here
                # because the log orders ACTION_SELECTED strictly before
                # EXECUTION_STARTED. Empty for actions that carry none.
                "prediction_ref": self._prediction_ref(selected),
            },
            at=self._clock(),
        )
        self._advance(ExecutionState.ACTION_SELECTED)

        predicted = self._predicted_cost(recommendation, selected.action_id)
        # M5.1 — persist the exact artifacts BEFORE anything executes, so a
        # resume continues this decision rather than making another one.
        self._plan = IterationPlan(
            iteration=iteration,
            snapshot=snapshot,
            manifest=recommendation.dependency_manifest,
            recommendation=recommendation,
            action=selected,
            charter_version=self._charter_version,
            campaign_id=self._charter.campaign_id,
            predicted_cost=predicted,
            liveness_reason=ruling.reason if ruling and ruling.overrides else "",
        )
        self._checkpoint()

        return self._execute_and_assess(
            iteration=iteration,
            action=selected,
            snapshot=snapshot,
            recommendation=recommendation,
            predicted_cost=predicted,
            liveness=ruling,
        )

    # -- step helpers ------------------------------------------------------
    @staticmethod
    def _prediction_ref(action: CandidateAction) -> str:
        """The prediction reference a candidate declares, if any.

        Recorded, never validated. V0.1 checks that a reference exists before
        execution and nothing about what it points at — see
        :mod:`~engcore.sria.campaign.certification` for what that does and does
        not guarantee.
        """
        for member in action.members:
            reference = str(member.action.metadata.get("prediction_ref", ""))
            if reference:
                return reference
        return ""

    def _execution_reason(
        self,
        action: CandidateAction,
        recommendation: DecisionRecommendation,
        ruling: LivenessRuling | None,
    ) -> str:
        """Why this action reached execution.

        Three routes exist and they are recorded apart. Pretending a mandatory
        probe was bought for its information value would put a false statement
        in the audit trail and hide the one thing the record is for.
        """
        if ruling is not None and ruling.overrides and (
            ruling.forced_action_id == action.action_id
        ):
            return "VALIDATION_LIVENESS"
        if recommendation.outcome in _NON_SELECTING:
            return "CERTIFICATION_REQUIREMENT"
        return "POSITIVE_NET_VALUE"

    def _effect_subject(self, action: CandidateAction) -> str:
        """Bind an effect key to the action's *content*, not just its label.

        A human-readable ``action_id`` may legitimately recur across iterations,
        and two different actions could carry the same id. The iteration is
        already in the key; adding the decision-identity digest means a reused
        id with different content is a different effect, so one can never be
        mistaken for the other's completion.
        """
        return (
            f"{action.action_id}@"
            f"{canonical_digest(candidate_decision_identity(action))[:16]}"
        )

    def _active_generators(self) -> tuple[ActionFamilyGenerator, ...]:
        """Generators for this iteration, from the harness if it supplies them.

        A campaign whose candidate pool legitimately changes between iterations
        (a new fidelity rung became available, an obligation was discharged)
        says so here. The runner still treats every family as a peer — this
        chooses *what may be proposed*, never *what wins*.
        """
        supplier = getattr(self._harness, "generators", None)
        if callable(supplier):
            return tuple(supplier(self._run))
        return self._generators

    def _fresh_snapshot(self, iteration: int) -> BeliefSnapshot:
        """A NEW snapshot every iteration, pinned to what will score it.

        Pinning happens here rather than in the harness so that M4.4 coherence
        is a property of the loop, not something each campaign must remember.
        """
        base = self._harness.build_snapshot(
            snapshot_id=f"{self._run.run_id}-snap-{iteration}",
            run=self._run,
            obligation_state=dict(self._obligation_state),
        )
        evaluator = self._harness.evaluator()
        context = self._harness.generation_context(base, self._run)
        candidates = generate_candidates(context, self._active_generators())
        manifest = evaluator.build_manifest(
            candidates=candidates,
            snapshot=base,
            objective=self._harness.objective(),
            charter_version=self._charter_version,
        )
        snapshot = pin_decision_basis(base, manifest)
        self._events.append(
            CampaignEventType.SNAPSHOT_CREATED,
            iteration=iteration,
            payload={
                "snapshot_id": snapshot.snapshot_id,
                "digest": snapshot.digest,
                "active_evidence": list(snapshot.active_evidence),
                "basis_kinds": sorted(
                    d.kind.value for d in snapshot.decision_basis
                ),
                "cost_state_digest": snapshot.calibration.cost_model_state_digest,
            },
            at=self._clock(),
        )
        self._advance(
            ExecutionState.DECIDING,
            active_snapshot_digest=snapshot.digest,
            active_basis_digest=manifest.manifest_digest,
        )
        return snapshot

    def _predicted_cost(
        self, recommendation: DecisionRecommendation, action_id: str
    ) -> float | None:
        for score in recommendation.scores:
            if score.action_id != action_id:
                continue
            component = score.component("expected_cost")
            if component is not None and component.value is not None:
                return float(component.value)
        return None

    def _select(
        self,
        iteration: int,
        candidates: Sequence[CandidateAction],
        recommendation: DecisionRecommendation,
        snapshot: BeliefSnapshot,
    ) -> tuple[CandidateAction | None, LivenessRuling | None]:
        by_id = {c.action_id: c for c in candidates}
        recommended = by_id.get(recommendation.chosen_action_id)

        costs = {
            s.action_id: (
                s.component("expected_cost").value
                if s.component("expected_cost") is not None
                else None
            )
            for s in recommendation.scores
        }
        unsatisfied = tuple(
            sorted(
                o.obligation_id
                for o in self._obligations.obligations
                if not self._obligation_state.get(o.obligation_id, False)
            )
        )
        targets = validation_targets(
            candidates, unsatisfied_obligation_ids=unsatisfied, costs=costs
        )
        ruling = self._liveness.assess(
            targets=targets,
            budget=self._budget,
            remaining_iterations=self._run.max_iterations - iteration + 1,
            competing_action_id=recommendation.chosen_action_id,
            competing_cost=costs.get(recommendation.chosen_action_id),
            unsatisfied_obligation_ids=unsatisfied,
        )

        if ruling.overrides and ruling.forced_action_id in by_id:
            return by_id[ruling.forced_action_id], ruling
        # V0.1 — a declared certification requirement outranks an economic
        # stop. This is the whole of the routing fix: the loop already refuses
        # to APPROVE a stop while the requirement is outstanding, and now it
        # also knows what to do about it instead of pausing.
        required = self._certification_route(by_id, costs, recommendation)
        if required is not None:
            return required, ruling
        if recommendation.outcome in _NON_SELECTING:
            return None, ruling
        return recommended, ruling

    def _satisfied_certification_actions(self) -> frozenset[str]:
        """Which required actions have been discharged, read from the log.

        Derived rather than stored, for the same reason :meth:`step` reads
        interruption from the log: a stored flag is a second source of truth a
        resume can contradict.

        An action counts only if BOTH hold. Its evidence was admitted — an
        execution that produced nothing belief-bearing has discharged nothing.
        And its selection carried a prediction reference, which the log orders
        strictly before ``EXECUTION_STARTED``; a validation action whose
        prediction was written after its observation tests nothing, and a
        requirement discharged by one would certify a check that never happened.
        """
        selected: dict[int, tuple[str, str]] = {}
        admitted: set[int] = set()
        for event in self._events:
            if event.event_type is CampaignEventType.ACTION_SELECTED:
                selected[event.iteration] = (
                    str(event.payload.get("action_id", "")),
                    str(event.payload.get("prediction_ref", "")),
                )
            elif event.event_type is CampaignEventType.EVIDENCE_ADMITTED:
                admitted.add(event.iteration)
        return frozenset(
            action_id
            for iteration, (action_id, prediction_ref) in selected.items()
            if action_id and prediction_ref and iteration in admitted
        )

    def _certification_route(
        self,
        by_id: Mapping[str, CandidateAction],
        costs: Mapping[str, float | None],
        recommendation: DecisionRecommendation,
    ) -> CandidateAction | None:
        """The cheapest affordable outstanding required candidate.

        Only consulted when the scoring engine declined to select, so this
        never displaces an action that was worth buying on its own terms. It
        ranks a fixed declared set by price — it is not a planner, it proposes
        nothing, and it computes no value of information. The action it returns
        keeps whatever score the engine gave it, which is typically negative.

        Nothing here branches on action family, and it must not: every family
        is an eligible peer scored by the same engine, and a runner that read a
        family to decide what happens next would be a mode machine wearing a
        different name. Affordability is asked of the ledger using each
        candidate's OWN family, so a VALIDATE requirement draws on the
        validation reservation and anything else draws on the general pool —
        the ledger's existing rule, applied without the runner restating it.
        """
        if not self._certification_requirements:
            return None
        if recommendation.outcome not in _NON_SELECTING:
            return None
        satisfied = self._satisfied_certification_actions()
        eligible: list[tuple[float, int, str]] = []
        for requirement in self._certification_requirements:
            for order, action_id in enumerate(requirement.outstanding(satisfied)):
                candidate = by_id.get(action_id)
                if candidate is None:
                    continue
                cost = costs.get(action_id)
                if cost is None:
                    continue
                if not self._budget.affordable(cost, family=candidate.family):
                    continue
                eligible.append((float(cost), order, action_id))
        if not eligible:
            return None
        eligible.sort()
        return by_id[eligible[0][2]]

    def certification_status(
        self, candidates: Sequence[CandidateAction] = ()
    ) -> dict[str, str]:
        """Per-requirement status, derived. Read-only."""
        satisfied = self._satisfied_certification_actions()
        reachable = [c.action_id for c in candidates] if candidates else None
        return {
            requirement.requirement_id: requirement.status(
                satisfied, reachable_action_ids=reachable
            ).value
            for requirement in self._certification_requirements
        }

    def adopt_prior_assurance(
        self, obligation_state: Mapping[str, bool]
    ) -> CampaignRun:
        """Begin from evidence admitted before this run object existed.

        The smallest supported entry point for a campaign that continues work
        already assessed elsewhere. Without it the stopping review short-
        circuits at "obligations were never assessed" and never reaches the
        registered criterion — the state in which a certification question
        actually arises is the one the runner could not be started in.

        This is the existing checkpoint/restore seam with the boilerplate
        removed; it adds no persistence, no discovery and no replay.
        """
        return self.restore(
            CampaignCheckpoint(
                run=self._run,
                events=self._events,
                budget=self._budget,
                effects=self._effects,
                plan=self._plan,
                obligation_state=dict(obligation_state),
            )
        )

    def _handle_no_selection(
        self,
        iteration: int,
        recommendation: DecisionRecommendation,
        snapshot: BeliefSnapshot,
        candidates: Sequence[CandidateAction] = (),
    ) -> CampaignRun:
        """Every non-selecting outcome is legal. None of them is a crash."""
        outcome = recommendation.outcome
        if outcome is RecommendationOutcome.STOP_PROPOSAL:
            return self._propose_stop(iteration, recommendation, snapshot)
        if outcome in (
            RecommendationOutcome.STATE_INCOHERENT,
            RecommendationOutcome.DECISION_BASIS_UNVERIFIED,
        ):
            self._events.append(
                CampaignEventType.CAMPAIGN_FAILED,
                iteration=iteration,
                payload={
                    "outcome": outcome.value,
                    "reason": recommendation.reason,
                },
                at=self._clock(),
            )
            run = self._advance(
                ExecutionState.FAILED,
                failure_reason=(
                    f"{outcome.value}: the decision basis could not be verified, "
                    f"so no candidate was scored"
                ),
            )
            self._checkpoint()
            return run
        # "Nothing was selectable" has two very different causes, and calling
        # them both NO_SCORABLE_CANDIDATE would hide the one an operator can
        # act on. If every scored candidate was priced above what its pool can
        # fund, the campaign ran out of money, not out of ideas.
        by_id = {c.action_id: c for c in candidates}
        priced = [
            (component.value, by_id[score.action_id].family)
            for score in recommendation.scores
            if score.action_id in by_id
            and (component := score.component("expected_cost")) is not None
            and component.value is not None
        ]
        if priced and all(
            not self._budget.affordable(cost, family=family)
            for cost, family in priced
        ):
            return self._pause(
                PauseReason.BUDGET_EXHAUSTED,
                (
                    f"every scored candidate costs more than the "
                    f"{self._budget.general_pool} remaining in the general pool "
                    f"(cheapest {min(c for c, _f in priced)}); no action may "
                    f"execute"
                ),
                iteration,
            )
        return self._pause(
            PauseReason.NO_SCORABLE_CANDIDATE,
            f"{outcome.value}: {recommendation.reason}",
            iteration,
        )

    def _propose_stop(
        self,
        iteration: int,
        recommendation: DecisionRecommendation,
        snapshot: BeliefSnapshot,
    ) -> CampaignRun:
        proposal = StopProposal(
            proposal_id=f"{self._run.run_id}-stop-{iteration}",
            campaign_id=self._charter.campaign_id,
            run_id=self._run.run_id,
            iteration=iteration,
            recommendation_id=recommendation.recommendation_id,
            snapshot_digest=snapshot.digest,
            scored_action_ids=tuple(s.action_id for s in recommendation.scores),
            economic_reason=recommendation.reason,
        )
        self._events.append(
            CampaignEventType.STOP_PROPOSED,
            iteration=iteration,
            payload=proposal.to_dict(),
            at=self._clock(),
        )
        review = self._stopping.review(
            proposal,
            review_id=f"{self._run.run_id}-stopreview-{iteration}",
            obligations=self._obligations,
            obligation_state=dict(self._obligation_state),
            terminal_objective_available=self._harness.objective().is_available,
            criteria=self._stopping_criteria,
            evaluators=self._stopping_evaluators,
            evaluation_context=self._run,
            reviewed_at=self._clock(),
        )
        self._reviews.append(review)
        self._events.append(
            CampaignEventType.STOP_REVIEWED,
            iteration=iteration,
            payload=review.to_dict(),
            at=self._clock(),
        )
        # The loop pauses either way. Only the Arbiter's review may say the
        # campaign's declared obligations are discharged, and even that is not
        # a certificate of scientific completeness.
        record = IterationRecord(
            iteration=iteration,
            snapshot_digest=snapshot.digest,
            decision_basis_digest=(
                recommendation.dependency_manifest.manifest_digest
                if recommendation.dependency_manifest
                else ""
            ),
            recommendation_id=recommendation.recommendation_id,
            recommendation_outcome=recommendation.outcome.value,
            stop_proposed=True,
            detail=review.outcome.value,
        )
        self._advance(
            ExecutionState.DECIDING,
            iterations=self._run.iterations + (record,),
            stop_proposal_recommendation_id=recommendation.recommendation_id,
            stop_review_outcome=review.outcome.value,
        )
        return self._pause(
            PauseReason.NO_ACTION_WORTH_BUYING,
            (
                f"no evaluated candidate scored above zero; stopping review "
                f"returned {review.outcome.value}"
            ),
            iteration,
        )

    # -- execution and the evidence pipeline -------------------------------
    def _execute_and_assess(
        self,
        *,
        iteration: int,
        action: CandidateAction,
        snapshot: BeliefSnapshot,
        recommendation: DecisionRecommendation,
        predicted_cost: float | None,
        liveness: LivenessRuling | None,
        resumed: bool = False,
    ) -> CampaignRun:
        run_id = self._run.run_id
        require_simulation(action)
        subject = self._effect_subject(action)

        if predicted_cost is not None and not self._budget.affordable(
            predicted_cost, family=action.family
        ):
            return self._pause(
                PauseReason.BUDGET_EXHAUSTED,
                (
                    f"action {action.action_id!r} is predicted to cost "
                    f"{predicted_cost} but the pool it may draw on cannot fund it"
                ),
                iteration,
            )

        # ---- execute exactly once ----------------------------------------
        self._advance(ExecutionState.EXECUTING)
        exec_key = self._effects.key(run_id, iteration, "execute", subject)
        executor = self._harness.executor()
        #: Stable operation id, derived from run and iteration rather than
        #: generated per attempt, so a restarted process asks about the *same*
        #: operation the previous one launched.
        operation_id = f"{run_id}-exec-{iteration}"

        # A previous attempt may have launched this run and died before the
        # ledger recorded it. Exactly-once cannot be invented locally for an
        # external executor, so the campaign asks whether the operation
        # completed and refuses to guess.
        already_started = self._events.has(
            CampaignEventType.EXECUTION_STARTED, iteration=iteration
        )
        if already_started and not self._effects.is_applied(exec_key):
            recovered = self._recover_execution(iteration, action, operation_id)
            if recovered is None:
                return self._pause(
                    PauseReason.OPERATOR_REQUESTED,
                    (
                        f"operation {operation_id!r} for action "
                        f"{action.action_id!r} was started by an earlier attempt "
                        f"and its completion cannot be determined. Re-running it "
                        f"could spend the budget twice and admit one experiment "
                        f"as two, so the campaign stops for an operator instead "
                        f"of guessing"
                    ),
                    iteration,
                )
            self._effects.mark(exec_key, recovered.execution_id)

        if not already_started:
            self._events.append(
                CampaignEventType.EXECUTION_STARTED,
                iteration=iteration,
                payload={"action_id": action.action_id,
                         "operation_id": operation_id},
                at=self._clock(),
            )
            # Durable *before* the solver is invoked. If the process dies during
            # the run, a restart must know an operation was launched — otherwise
            # it would cheerfully launch a second one.
            self._checkpoint()
        execution, performed = self._effects.once(
            exec_key,
            lambda: executor.execute(action, execution_id=operation_id),
            reference=lambda e: e.execution_id,
        )
        if not performed:
            # Already executed before an interruption. Retrieve the record;
            # never re-run the solver to obtain it again.
            execution = self._recover_execution(
                iteration, action, self._effects.reference(exec_key)
            )
            if execution is None:
                return self._pause(
                    PauseReason.OPERATOR_REQUESTED,
                    (
                        f"action {action.action_id!r} already executed as "
                        f"{self._effects.reference(exec_key)!r}, but the executor "
                        f"cannot retrieve that record. Re-running it would spend "
                        f"the budget twice, so the campaign stops for an operator "
                        f"rather than guessing"
                    ),
                    iteration,
                )

        else:
            self._events.append(
                CampaignEventType.EXECUTION_COMPLETED,
                iteration=iteration,
                payload={
                    "execution_id": execution.execution_id,
                    "realized_cost": execution.realized_cost,
                    "disposition": execution.outcome.disposition.value,
                    "attributed_cause": execution.outcome.attributed_cause.value,
                    "informative_for_pf": execution.outcome.informative_for_pf,
                },
                at=self._clock(),
            )

        # ---- charge realized cost exactly once ---------------------------
        charge_key = self._effects.key(run_id, iteration, "charge", subject)
        charge, charged = self._effects.once(
            charge_key,
            lambda: self._budget.settle(
                charge_id=charge_key,
                action_id=action.action_id,
                iteration=iteration,
                family=action.family,
                realized=execution.realized_cost,
                predicted=predicted_cost,
            ),
            reference=lambda c: c.charge_id,
        )
        if charge is None:
            charge = next(
                c for c in self._budget.charges if c.charge_id == charge_key
            )

        if charged:
            self._events.append(
                CampaignEventType.BUDGET_UPDATED,
                iteration=iteration,
                payload={
                    "predicted": predicted_cost,
                    "realized": execution.realized_cost,
                    "overrun": charge.overrun,
                    "remaining": self._budget.remaining,
                    "validation_pool": self._budget.validation_pool,
                    "budget_overrun": self._budget.overrun,
                },
                at=self._clock(),
            )
        # A completed state transition, so a durable point to come back to.
        # An interruption after this must not re-execute or re-charge.
        self._checkpoint()

        # ---- result -> candidate evidence --------------------------------
        self._advance(ExecutionState.ASSESSING)
        evidence_ids: list[str] = []
        assessment_ids: list[str] = []
        admitted_ids: list[str] = []
        arbiter_decision_id = ""
        arbiter_verdict = ""

        evidence_key = self._effects.key(
            run_id, iteration, "evidence", f"{subject}:{execution.execution_id}"
        )
        evidence, built = self._effects.once(
            evidence_key,
            lambda: self._harness.build_evidence(
                execution,
                snapshot,
                evidence_id=f"{run_id}-ev-{iteration}",
            ),
            reference=lambda e: e.evidence_id if e is not None else "",
        )
        if built and evidence is not None:
            evidence_ids.append(evidence.evidence_id)
            self._events.append(
                CampaignEventType.EVIDENCE_CREATED,
                iteration=iteration,
                payload={
                    "evidence_id": evidence.evidence_id,
                    "belief_key": evidence.belief_key,
                    "status": evidence.status.value,
                },
                at=self._clock(),
            )
            (
                assessment_ids,
                admitted_ids,
                arbiter_decision_id,
                arbiter_verdict,
            ) = self._assure(iteration, execution, evidence)
            self._checkpoint()

        # ---- computational calibration -----------------------------------
        self._advance(ExecutionState.UPDATING)
        calibration_ids: list[str] = []
        calib_key = self._effects.key(
            run_id, iteration, "calibrate", execution.execution_id
        )
        entry, updated = self._effects.once(
            calib_key,
            lambda: self._harness.update_calibration(
                execution, record_id=f"{run_id}-calib-{iteration}"
            ),
            reference=lambda e: getattr(e, "entry_id", "") if e is not None else "",
        )
        if updated and entry is not None:
            calibration_ids.append(getattr(entry, "entry_id", ""))
            self._events.append(
                CampaignEventType.CALIBRATION_UPDATED,
                iteration=iteration,
                payload={
                    "entry_id": getattr(entry, "entry_id", ""),
                    "kind": getattr(getattr(entry, "kind", None), "value", ""),
                    "realized_cost": execution.realized_cost,
                },
                at=self._clock(),
            )

        # ---- record and close the iteration ------------------------------
        record = IterationRecord(
            iteration=iteration,
            snapshot_digest=snapshot.digest,
            decision_basis_digest=(
                recommendation.dependency_manifest.manifest_digest
                if recommendation.dependency_manifest
                else ""
            ),
            recommendation_id=recommendation.recommendation_id,
            recommendation_outcome=recommendation.outcome.value,
            selected_action_id=action.action_id,
            execution_id=execution.execution_id,
            evidence_ids=tuple(evidence_ids),
            assessment_ids=tuple(assessment_ids),
            arbiter_decision_id=arbiter_decision_id,
            arbiter_verdict=arbiter_verdict,
            admitted_evidence_ids=tuple(admitted_ids),
            calibration_entry_ids=tuple(calibration_ids),
            predicted_cost=predicted_cost,
            realized_cost=execution.realized_cost,
            detail=(
                liveness.reason if liveness and liveness.overrides else ""
            ),
        )
        self._events.append(
            CampaignEventType.ITERATION_COMPLETED,
            iteration=iteration,
            payload=record.to_dict(),
            at=self._clock(),
        )
        self._plan = None                      # the iteration is no longer in flight
        self._advance(
            ExecutionState.READY,
            iterations=self._run.iterations + (record,),
        )

        # M5.1 — a realized overrun is recorded, then halts the campaign. The
        # cost was genuinely incurred; refusing to write it down would leave the
        # ledger claiming money reality has already spent.
        if self._budget.is_overrun:
            self._checkpoint()
            return self._pause(
                PauseReason.BUDGET_OVERRUN,
                (
                    f"realized spend {self._budget.spent_total} exceeded the "
                    f"declared budget {self._budget.total_budget} by "
                    f"{self._budget.overrun} {self._budget.cost_unit}. "
                    f"{self._budget.guarantee_statement}"
                ),
                iteration,
            )
        self._checkpoint()
        return self._run

    def _resume_iteration(self, iteration: int) -> CampaignRun:
        """Finish an iteration that was already decided. Do not decide again.

        Re-deciding on resume looks harmless and is not: the belief may have
        moved *because of this very iteration* (its evidence was admitted just
        before the interruption), so a fresh ranking can prefer a different
        action and the campaign would execute two actions for one decision.
        The selection is a recorded fact; resume reads it.

        The snapshot is rebuilt rather than stored, which is safe precisely
        where it is used. Only this loop admits evidence, so belief can have
        changed mid-iteration only by this iteration's own admission — and if
        that already happened, the evidence exists and is not rebuilt. Whenever
        ``build_evidence`` actually runs on resume, the rebuilt snapshot is the
        one the decision was made against.
        """
        selection = self._events.last(
            CampaignEventType.ACTION_SELECTED, iteration=iteration
        )
        action_id = str(selection.payload.get("action_id", ""))
        snapshot = self._fresh_snapshot(iteration)
        context = self._harness.generation_context(snapshot, self._run)
        candidates = generate_candidates(context, self._active_generators())
        action = next(
            (c for c in candidates if c.action_id == action_id), None
        )
        if action is None:
            self._events.append(
                CampaignEventType.CAMPAIGN_FAILED,
                iteration=iteration,
                payload={
                    "reason": (
                        f"resume cannot find the recorded action {action_id!r} "
                        f"among the candidates; the campaign will not substitute "
                        f"a different one"
                    )
                },
                at=self._clock(),
            )
            run = self._advance(
                ExecutionState.FAILED,
                failure_reason=f"resumed action {action_id!r} is unavailable",
            )
            self._checkpoint()
            return run

        recommendation_event = self._events.last(
            CampaignEventType.DECISION_RECOMMENDED, iteration=iteration
        )
        recommendation_id = (
            str(recommendation_event.payload.get("recommendation_id", ""))
            if recommendation_event
            else ""
        )
        recommendation = self._recommendations.get(recommendation_id)
        if recommendation is None:
            # A different process made the decision. Rebuild the record from the
            # log rather than re-scoring, so the resumed iteration reports the
            # decision that was actually made.
            recommendation = DecisionRecommendation(
                recommendation_id=recommendation_id or f"{self._run.run_id}-rec-{iteration}",
                outcome=RecommendationOutcome.RECOMMEND_ACTION,
                snapshot_digest=str(
                    recommendation_event.payload.get("snapshot_digest", "")
                    if recommendation_event
                    else ""
                ),
                campaign_id=self._charter.campaign_id,
                charter_version=self._charter_version,
                chosen_action_id=action_id,
                chosen_family=action.family,
                reason="reconstructed from the campaign event log on resume",
            )

        charge = next(
            (
                c for c in self._budget.charges
                if c.iteration == iteration and c.action_id == action_id
            ),
            None,
        )
        predicted = (
            charge.predicted
            if charge is not None
            else self._predicted_cost(recommendation, action_id)
        )
        return self._execute_and_assess(
            iteration=iteration,
            action=action,
            snapshot=snapshot,
            recommendation=recommendation,
            predicted_cost=predicted,
            liveness=None,
        )

    def _recover_execution(
        self, iteration: int, action: CandidateAction, execution_id: str
    ) -> ExecutionRecord | None:
        """Retrieve a completed execution rather than repeating it.

        A solver that has already run wrote its result somewhere; asking for it
        back is a read. Re-invoking the solver would spend the budget a second
        time for a number that already exists, so the executor is asked and, if
        it cannot answer, the campaign stops instead of improvising.
        """
        executor = self._harness.executor()
        fetch = getattr(executor, "fetch_execution", None)
        record = fetch(execution_id) if callable(fetch) else None
        if record is None:
            return None
        self._events.append(
            CampaignEventType.EXECUTION_COMPLETED,
            iteration=iteration,
            payload={
                "execution_id": record.execution_id,
                "realized_cost": record.realized_cost,
                "disposition": record.outcome.disposition.value,
                "recovered": True,
                "detail": "retrieved after an interruption; the solver did not re-run",
            },
            at=self._clock(),
        )
        return record

    def _assure(
        self, iteration: int, execution: ExecutionRecord, evidence: Evidence
    ) -> tuple[list[str], list[str], str, str]:
        """Critics -> Arbiter -> AdmissionAuthority -> Gateway. No shortcut."""
        run_id = self._run.run_id
        bundle = self._harness.assess(
            execution, evidence, assessment_prefix=f"{run_id}-assess-{iteration}"
        )
        assessment_ids = [a.assessment_id for a in bundle.assessments]
        self._events.append(
            CampaignEventType.CRITICS_COMPLETED,
            iteration=iteration,
            payload={
                "assessment_ids": assessment_ids,
                "verdicts": [a.verdict.value for a in bundle.assessments],
            },
            at=self._clock(),
        )
        self._obligation_state.update(bundle.obligation_state)

        decision = self._arbiter.decide(
            decision_id=f"{run_id}-arb-{iteration}",
            subject_ref=evidence.evidence_id,
            assessments=bundle.assessments,
            obligations=self._obligations,
            budget=bundle.uncertainty_budget,
            decided_at=self._clock(),
        )
        self._events.append(
            CampaignEventType.ARBITER_DECIDED,
            iteration=iteration,
            payload={
                "decision_id": decision.decision_id,
                "verdict": decision.verdict.value,
                "unmet_obligations": list(decision.unmet_obligations),
            },
            at=self._clock(),
        )

        assessed = evidence
        for assessment in bundle.assessments:
            assessed = assessed.with_assessment(
                assessment.to_evidence_assessment(),
                reason=f"critic {assessment.critic_id}",
                actor=assessment.critic_id,
                at=self._clock(),
            )

        admitted: list[str] = []
        if decision.verdict is AssuranceVerdict.VALID:
            admit_key = self._effects.key(
                run_id, iteration, "admit", evidence.evidence_id
            )

            def _admit() -> Any:
                declaration = self._arbiter.authorize_admission(
                    decision,
                    assessed,
                    rationale=f"campaign {run_id} iteration {iteration}",
                )
                accepted = assessed.admit(declaration, actor=run_id, at=self._clock())
                return self._gateway.submit(accepted)

            entry, performed = self._effects.once(
                admit_key,
                _admit,
                reference=lambda e: getattr(e, "evidence_id", ""),
            )
            if performed and entry is not None:
                admitted.append(evidence.evidence_id)
                self._events.append(
                    CampaignEventType.EVIDENCE_ADMITTED,
                    iteration=iteration,
                    payload={
                        "evidence_id": evidence.evidence_id,
                        "belief_key": getattr(entry, "belief_key", ""),
                        "belief_size": len(self._gateway.belief),
                    },
                    at=self._clock(),
                )
        else:
            # INVALID / INCONCLUSIVE / NOT_ASSESSED are all legal. The record
            # stays assessed and auditable; it simply does not become belief.
            self._events.append(
                CampaignEventType.EVIDENCE_NOT_ADMITTED,
                iteration=iteration,
                payload={
                    "evidence_id": evidence.evidence_id,
                    "verdict": decision.verdict.value,
                    "reason": (
                        "assessed but not admitted; only a VALID arbiter "
                        "decision authorizes belief"
                    ),
                },
                at=self._clock(),
            )

        return assessment_ids, admitted, decision.decision_id, decision.verdict.value

    # -- resume ------------------------------------------------------------
    def restore(self, checkpoint: CampaignCheckpoint) -> CampaignRun:
        """Adopt a checkpoint's state. Replays nothing and re-derives nothing."""
        self._run = checkpoint.run
        self._events = CampaignEventLog(
            checkpoint.run.run_id, checkpoint.events.events
        )
        self._budget = BudgetLedger(
            total_budget=checkpoint.budget.total_budget,
            reserved_validation_budget=checkpoint.budget.reserved_validation_budget,
            charges=checkpoint.budget.charges,
            cost_unit=checkpoint.budget.cost_unit,
        )
        self._effects = EffectLedger(applied=dict(checkpoint.effects.applied))
        self._plan = checkpoint.plan
        # Assurance state is scientific state. Without it the next snapshot
        # would claim nothing had ever been assessed, which changes its digest,
        # re-opens satisfied obligations to the liveness policy, and would have
        # the Arbiter review a stop against a rewound record.
        self._obligation_state = dict(checkpoint.obligation_state)
        if self._plan is not None:
            # Re-register the stored recommendation so the resumed iteration
            # reports the decision that was actually made, not a fresh one.
            self._recommendations[self._plan.recommendation.recommendation_id] = (
                self._plan.recommendation
            )
            self._snapshots[self._plan.iteration] = self._plan.snapshot
        return self._run
