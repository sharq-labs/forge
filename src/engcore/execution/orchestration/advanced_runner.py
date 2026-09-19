from __future__ import annotations

from collections.abc import Mapping

from .adaptive import AdaptiveDecision, AdaptiveRefinementPolicy
from .advanced_backend import AdvancedSimulationBackend, AdvancedBackendOutcome
from .advanced_report import (
    AdvancedAttemptRecord,
    AdvancedOrchestrationReport,
    AdvancedStopReason,
)
from .attempt import AttemptState, SimulationAttempt
from .capabilities import (
    SimulationRequirements,
    SolverCapability,
    rank_solver_capabilities,
)
from .checkpoint import CheckpointReference
from .plan import SimulationPlan
from .refinement import RefinementRequest
from .resources import ResourceBudget, ResourceUsage


def run_adaptive_plan(
    plan: SimulationPlan,
    requirements: SimulationRequirements,
    capabilities: tuple[SolverCapability, ...],
    backends: Mapping[str, AdvancedSimulationBackend],
    refinement_policy: AdaptiveRefinementPolicy,
    *,
    resource_budget: ResourceBudget = ResourceBudget(),
    checkpoint: CheckpointReference | None = None,
) -> AdvancedOrchestrationReport:
    ranked = rank_solver_capabilities(capabilities, requirements)
    declared = set(plan.solver_candidates)
    ranked = tuple(cap for cap in ranked if cap.solver_id in declared)
    if not ranked:
        return AdvancedOrchestrationReport(
            (),
            ResourceUsage(),
            AdvancedStopReason.NO_CAPABLE_SOLVER,
            checkpoint,
            ("no declared solver satisfies the simulation requirements",),
        )

    attempts: list[AdvancedAttemptRecord] = []
    total = ResourceUsage()
    current_checkpoint = checkpoint
    refinement: RefinementRequest | None = None
    attempt_number = 0
    refinement_level = 0
    problems: list[str] = []

    for capability in ranked:
        backend = backends.get(capability.solver_id)
        if backend is None:
            problems.append(f"{capability.solver_id}:backend_missing")
            continue
        if str(getattr(backend, "solver_id", "")) != capability.solver_id:
            problems.append(
                f"{capability.solver_id}:backend_solver_identity_mismatch"
            )
            continue

        while attempt_number < plan.budget.max_attempts:
            attempt_number += 1
            attempt_id = (
                f"{plan.plan_id}:{attempt_number}:{capability.solver_id}:"
                f"r{refinement_level}"
            )
            try:
                outcome = backend.run_advanced(
                    attempt_id=attempt_id,
                    deterministic_seed=plan.deterministic_seed,
                    checkpoint=current_checkpoint,
                    refinement=refinement,
                )
            except Exception as exc:
                problems.append(
                    f"{capability.solver_id}:backend_exception:"
                    f"{type(exc).__name__}"
                )
                attempts.append(
                    AdvancedAttemptRecord(
                        SimulationAttempt(
                            attempt_id,
                            AttemptState.FAILED,
                            refinement_level,
                            f"backend_exception:{type(exc).__name__}",
                        ),
                        capability.solver_id,
                        ResourceUsage(),
                        refinement,
                        current_checkpoint,
                    )
                )
                break

            if not isinstance(outcome, AdvancedBackendOutcome):
                raise TypeError(
                    "advanced simulation backend must return AdvancedBackendOutcome"
                )
            total = total.plus(outcome.usage)
            exceeded = total.exceeded(resource_budget)
            attempt = SimulationAttempt(
                attempt_id,
                outcome.state,
                refinement_level,
                outcome.failure_code,
            )
            attempts.append(
                AdvancedAttemptRecord(
                    attempt,
                    capability.solver_id,
                    outcome.usage,
                    refinement,
                    outcome.checkpoint,
                )
            )
            if outcome.checkpoint is not None:
                current_checkpoint = outcome.checkpoint
            if exceeded:
                return AdvancedOrchestrationReport(
                    tuple(attempts),
                    total,
                    AdvancedStopReason.RESOURCE_BUDGET,
                    current_checkpoint,
                    tuple(problems)
                    + (f"resource budget exceeded: {list(exceeded)}",),
                )
            if outcome.state is AttemptState.CANCELLED:
                return AdvancedOrchestrationReport(
                    tuple(attempts),
                    total,
                    AdvancedStopReason.CANCELLED,
                    current_checkpoint,
                    tuple(problems),
                )
            if outcome.state is AttemptState.CONVERGED:
                decision, next_refinement, reason = refinement_policy.decide(
                    outcome.diagnostics,
                    refinement_level,
                )
                if decision is AdaptiveDecision.ACCEPT:
                    return AdvancedOrchestrationReport(
                        tuple(attempts),
                        total,
                        AdvancedStopReason.ERROR_TARGET_SATISFIED,
                        current_checkpoint,
                        tuple(problems),
                    )
                if decision is AdaptiveDecision.STOP:
                    problems.append(reason)
                    break
                refinement = next_refinement
                refinement_level = next_refinement.level
                if refinement_level > plan.budget.max_refinements:
                    return AdvancedOrchestrationReport(
                        tuple(attempts),
                        total,
                        AdvancedStopReason.REFINEMENT_BUDGET,
                        current_checkpoint,
                        tuple(problems),
                    )
                continue

            # A failed/diverged route moves to the next capable solver.  A
            # non-converged run is never "fixed" by declaring success.
            break

    if attempt_number >= plan.budget.max_attempts:
        stop = AdvancedStopReason.ATTEMPT_BUDGET
    else:
        stop = AdvancedStopReason.BACKEND_FAILURE
    return AdvancedOrchestrationReport(
        tuple(attempts),
        total,
        stop,
        current_checkpoint,
        tuple(problems),
    )
