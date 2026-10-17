from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .attempt import SimulationAttempt
from .checkpoint import CheckpointReference
from .refinement import RefinementRequest
from .resources import ResourceUsage


class AdvancedStopReason(str, Enum):
    CONVERGED = "converged"
    ERROR_TARGET_SATISFIED = "error_target_satisfied"
    ATTEMPT_BUDGET = "attempt_budget"
    REFINEMENT_BUDGET = "refinement_budget"
    RESOURCE_BUDGET = "resource_budget"
    NO_CAPABLE_SOLVER = "no_capable_solver"
    BACKEND_FAILURE = "backend_failure"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class AdvancedAttemptRecord:
    attempt: SimulationAttempt
    solver_id: str
    usage: ResourceUsage
    refinement: RefinementRequest | None = None
    checkpoint: CheckpointReference | None = None

    def __post_init__(self) -> None:
        solver = str(self.solver_id).strip()
        if not solver:
            raise ValueError("advanced attempt record requires solver_id")
        object.__setattr__(self, "solver_id", solver)


@dataclass(frozen=True)
class AdvancedOrchestrationReport:
    """Outcome of an adaptive plan.

    ``final_checkpoint``: on a successful stop, the checkpoint the ACCEPTED
    attempt returned (or None); on any other stop, the last adopted resume
    point, bound to the solver that produced it, or the caller's input when
    none was adopted.  It is a resume point, never the result state of an
    unsuccessful run and never evidence.
    """

    attempts: tuple[AdvancedAttemptRecord, ...]
    total_usage: ResourceUsage
    stop_reason: AdvancedStopReason
    final_checkpoint: CheckpointReference | None = None
    problems: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "attempts", tuple(self.attempts))
        object.__setattr__(self, "stop_reason", AdvancedStopReason(self.stop_reason))
        object.__setattr__(self, "problems", tuple(str(x) for x in self.problems))
        if not isinstance(self.total_usage, ResourceUsage):
            raise TypeError("advanced orchestration total_usage must be ResourceUsage")

    @property
    def successful(self) -> bool:
        return self.stop_reason in {
            AdvancedStopReason.CONVERGED,
            AdvancedStopReason.ERROR_TARGET_SATISFIED,
        }
