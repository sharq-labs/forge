"""Deterministic simulation orchestration contracts."""

from .attempt import AttemptState, SimulationAttempt
from .backend import BackendOutcome, SimulationBackend
from .budget import ExecutionBudget
from .checkpoint import CheckpointReference
from .plan import SimulationPlan
from .policy import OrchestrationPolicy
from .refinement import RefinementRequest, RefinementStrategy
from .report import OrchestrationReport
from .retry import RetryDecision, decide_retry
from .scheduler import schedule_attempts
from .runner import run_plan

__all__=[
    "ExecutionBudget","SimulationPlan","AttemptState","SimulationAttempt",
    "CheckpointReference","OrchestrationPolicy","RefinementStrategy",
    "RefinementRequest","RetryDecision","decide_retry","schedule_attempts",
    "OrchestrationReport","BackendOutcome","SimulationBackend","run_plan",
]

from .resources import ResourceBudget, ResourceUsage
from .capabilities import (
    ProblemKind, SimulationRequirements, SolverCapability,
    rank_solver_capabilities,
)
from .adaptive import (
    AdaptiveDecision, AdaptiveRefinementPolicy, RefinementDiagnostics,
)
from .advanced_backend import AdvancedBackendOutcome, AdvancedSimulationBackend
from .advanced_report import (
    AdvancedAttemptRecord, AdvancedOrchestrationReport, AdvancedStopReason,
)
from .advanced_runner import run_adaptive_plan

__all__ += [
    "ResourceBudget", "ResourceUsage", "ProblemKind", "SimulationRequirements",
    "SolverCapability", "rank_solver_capabilities", "AdaptiveDecision",
    "AdaptiveRefinementPolicy", "RefinementDiagnostics",
    "AdvancedBackendOutcome", "AdvancedSimulationBackend",
    "AdvancedAttemptRecord", "AdvancedOrchestrationReport",
    "AdvancedStopReason", "run_adaptive_plan",
]
