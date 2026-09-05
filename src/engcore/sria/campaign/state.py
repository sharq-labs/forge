"""M5A — campaign execution state.

The lifecycle here describes **what the runner is doing**, never what the
campaign is scientifically *about*. That distinction is the whole reason this
module exists as a separate vocabulary from :class:`ActionFamily`.

``EXECUTING`` means a simulation is running. It does not mean the campaign is
"in optimization mode". There is no ``current_family``, no mode, and no
transition rule that lets one action family follow another. The six families
remain peer generators whose proposals all enter the same M4 ranking, and
:class:`ExecutionState` is structurally incapable of expressing otherwise —
:data:`RESEARCH_MODE_VOCABULARY` records the words that must never appear here,
and a test asserts they do not.

An :class:`IterationRecord` is the per-iteration ledger: which snapshot, which
decision basis, which recommendation, which action, which evidence, which
critic assessments, which arbiter decision, what it cost. It is derived from the
event log rather than maintained beside it, so a resumed run and a run that
never stopped produce the same record.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from ...scientific.serialization import require_schema, schema_string

RUN_SCHEMA = schema_string("sria_campaign_run")
ITERATION_SCHEMA = schema_string("sria_campaign_iteration")


class ExecutionState(str, Enum):
    """Operational lifecycle of the runner. Not a research mode."""

    CREATED = "created"
    READY = "ready"
    DECIDING = "deciding"
    ACTION_SELECTED = "action_selected"
    EXECUTING = "executing"
    ASSESSING = "assessing"
    UPDATING = "updating"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


#: States from which no further work happens without operator intervention.
TERMINAL_STATES = frozenset(
    {ExecutionState.COMPLETED, ExecutionState.FAILED}
)

#: Words that would signal a research-mode state machine had crept in. The
#: lifecycle vocabulary is asserted disjoint from this set.
RESEARCH_MODE_VOCABULARY = frozenset(
    {
        "explore",
        "characterize",
        "discriminate",
        "optimize",
        "reduce_uncertainty",
        "validate",
    }
)


class PauseReason(str, Enum):
    """Why the runner stopped advancing. Never a scientific verdict."""

    #: M4 scored nothing above zero. An economic proposal, not a completion.
    NO_ACTION_WORTH_BUYING = "no_action_worth_buying"
    #: The hard budget cannot fund any further ordinary action.
    BUDGET_EXHAUSTED = "budget_exhausted"
    #: Realized spend passed the declared budget. Recorded, then halted — the
    #: cost was real, so the ledger tells the truth and the campaign stops.
    BUDGET_OVERRUN = "budget_overrun"
    #: The declared iteration ceiling was reached.
    ITERATION_LIMIT_REACHED = "iteration_limit_reached"
    #: No candidate could be scored against a verified decision basis.
    NO_SCORABLE_CANDIDATE = "no_scorable_candidate"
    #: An operator asked for it.
    OPERATOR_REQUESTED = "operator_requested"


@dataclass(frozen=True)
class IterationRecord:
    """Everything one iteration touched, for audit and for resume."""

    iteration: int
    snapshot_digest: str = ""
    decision_basis_digest: str = ""
    recommendation_id: str = ""
    recommendation_outcome: str = ""
    selected_action_id: str = ""
    execution_id: str = ""
    evidence_ids: tuple[str, ...] = ()
    assessment_ids: tuple[str, ...] = ()
    arbiter_decision_id: str = ""
    arbiter_verdict: str = ""
    admitted_evidence_ids: tuple[str, ...] = ()
    calibration_entry_ids: tuple[str, ...] = ()
    predicted_cost: float | None = None
    realized_cost: float | None = None
    stop_proposed: bool = False
    detail: str = ""

    def __post_init__(self) -> None:
        if self.iteration < 0:
            raise ValueError("iteration must be non-negative")
        for label in (
            "evidence_ids",
            "assessment_ids",
            "admitted_evidence_ids",
            "calibration_entry_ids",
        ):
            object.__setattr__(self, label, tuple(getattr(self, label)))

    @property
    def cost_overrun(self) -> float | None:
        """Realized minus predicted, when both are known. Never retroactive."""
        if self.predicted_cost is None or self.realized_cost is None:
            return None
        return self.realized_cost - self.predicted_cost

    @property
    def changed_belief(self) -> bool:
        return bool(self.admitted_evidence_ids)

    @property
    def changed_calibration(self) -> bool:
        return bool(self.calibration_entry_ids)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ITERATION_SCHEMA,
            "iteration": self.iteration,
            "snapshot_digest": self.snapshot_digest,
            "decision_basis_digest": self.decision_basis_digest,
            "recommendation_id": self.recommendation_id,
            "recommendation_outcome": self.recommendation_outcome,
            "selected_action_id": self.selected_action_id,
            "execution_id": self.execution_id,
            "evidence_ids": list(self.evidence_ids),
            "assessment_ids": list(self.assessment_ids),
            "arbiter_decision_id": self.arbiter_decision_id,
            "arbiter_verdict": self.arbiter_verdict,
            "admitted_evidence_ids": list(self.admitted_evidence_ids),
            "calibration_entry_ids": list(self.calibration_entry_ids),
            "predicted_cost": self.predicted_cost,
            "realized_cost": self.realized_cost,
            "stop_proposed": self.stop_proposed,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "IterationRecord":
        require_schema(payload, ITERATION_SCHEMA)
        return cls(
            iteration=int(payload["iteration"]),
            snapshot_digest=payload.get("snapshot_digest", ""),
            decision_basis_digest=payload.get("decision_basis_digest", ""),
            recommendation_id=payload.get("recommendation_id", ""),
            recommendation_outcome=payload.get("recommendation_outcome", ""),
            selected_action_id=payload.get("selected_action_id", ""),
            execution_id=payload.get("execution_id", ""),
            evidence_ids=tuple(payload.get("evidence_ids", ())),
            assessment_ids=tuple(payload.get("assessment_ids", ())),
            arbiter_decision_id=payload.get("arbiter_decision_id", ""),
            arbiter_verdict=payload.get("arbiter_verdict", ""),
            admitted_evidence_ids=tuple(payload.get("admitted_evidence_ids", ())),
            calibration_entry_ids=tuple(payload.get("calibration_entry_ids", ())),
            predicted_cost=payload.get("predicted_cost"),
            realized_cost=payload.get("realized_cost"),
            stop_proposed=bool(payload.get("stop_proposed", False)),
            detail=payload.get("detail", ""),
        )


@dataclass(frozen=True)
class CampaignRun:
    """The durable state of one bounded campaign run."""

    run_id: str
    campaign_id: str
    charter_version: str = ""
    state: ExecutionState = ExecutionState.CREATED
    iteration: int = 0
    max_iterations: int = 1
    iterations: tuple[IterationRecord, ...] = ()
    active_snapshot_digest: str = ""
    active_basis_digest: str = ""
    stop_proposal_recommendation_id: str = ""
    stop_review_outcome: str = ""
    pause_reason: PauseReason | None = None
    failure_reason: str = ""
    event_log_digest: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for label in ("run_id", "campaign_id"):
            if not str(getattr(self, label)).strip():
                raise ValueError(f"campaign run requires {label}")
        object.__setattr__(self, "state", ExecutionState(self.state))
        if self.pause_reason is not None:
            object.__setattr__(self, "pause_reason", PauseReason(self.pause_reason))
        if self.max_iterations < 1:
            raise ValueError(
                "max_iterations must be at least 1; an unbounded campaign loop "
                "is outside V0.1 scope"
            )
        if self.iteration < 0:
            raise ValueError("iteration must be non-negative")
        object.__setattr__(self, "iterations", tuple(self.iterations))
        object.__setattr__(self, "metadata", dict(self.metadata))
        if (
            self.state is ExecutionState.PAUSED
            and self.pause_reason is None
        ):
            raise ValueError(
                "a paused campaign must record why; an unexplained pause cannot "
                "be reviewed"
            )
        if self.state is ExecutionState.FAILED and not self.failure_reason.strip():
            raise ValueError("a failed campaign must record why")

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    @property
    def completed_iterations(self) -> int:
        return len(self.iterations)

    def record(self, iteration: int) -> IterationRecord | None:
        for item in self.iterations:
            if item.iteration == iteration:
                return item
        return None

    @property
    def admitted_evidence_ids(self) -> tuple[str, ...]:
        out: list[str] = []
        for item in self.iterations:
            out.extend(item.admitted_evidence_ids)
        return tuple(out)

    @property
    def is_certification(self) -> bool:
        """Always False. A campaign run never certifies its own completion."""
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": RUN_SCHEMA,
            "run_id": self.run_id,
            "campaign_id": self.campaign_id,
            "charter_version": self.charter_version,
            "state": self.state.value,
            "iteration": self.iteration,
            "max_iterations": self.max_iterations,
            "iterations": [i.to_dict() for i in self.iterations],
            "active_snapshot_digest": self.active_snapshot_digest,
            "active_basis_digest": self.active_basis_digest,
            "stop_proposal_recommendation_id": self.stop_proposal_recommendation_id,
            "stop_review_outcome": self.stop_review_outcome,
            "pause_reason": self.pause_reason.value if self.pause_reason else None,
            "failure_reason": self.failure_reason,
            "event_log_digest": self.event_log_digest,
            "metadata": dict(sorted(self.metadata.items())),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CampaignRun":
        require_schema(payload, RUN_SCHEMA)
        return cls(
            run_id=payload["run_id"],
            campaign_id=payload["campaign_id"],
            charter_version=payload.get("charter_version", ""),
            state=ExecutionState(payload.get("state", "created")),
            iteration=int(payload.get("iteration", 0)),
            max_iterations=int(payload.get("max_iterations", 1)),
            iterations=tuple(
                IterationRecord.from_dict(i) for i in payload.get("iterations", ())
            ),
            active_snapshot_digest=payload.get("active_snapshot_digest", ""),
            active_basis_digest=payload.get("active_basis_digest", ""),
            stop_proposal_recommendation_id=payload.get(
                "stop_proposal_recommendation_id", ""
            ),
            stop_review_outcome=payload.get("stop_review_outcome", ""),
            pause_reason=(
                PauseReason(payload["pause_reason"])
                if payload.get("pause_reason")
                else None
            ),
            failure_reason=payload.get("failure_reason", ""),
            event_log_digest=payload.get("event_log_digest", ""),
            metadata=payload.get("metadata", {}),
        )
