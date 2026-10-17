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
from .checkpoint import (
    CheckpointConversion,
    CheckpointReference,
    adopt_checkpoint,
    converted_resume_point,
    resume_owner,
    resume_point_for,
    resume_refusal,
)
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
    conversions: tuple[CheckpointConversion, ...] = (),
) -> AdvancedOrchestrationReport:
    """Run the capable declared solvers in rank order until one is accepted.

    Phase 2 BR10 recovery rules: a checkpoint resumes only the solver build and
    problem it was produced for (:func:`resume_refusal`); a fallback solver
    cold-starts from the admitted problem unless a declared, qualified
    :class:`CheckpointConversion` exists and its backend declares
    ``accepts_converted_checkpoints``; a backend whose stated build changes
    between attempts is refused (build drift); every resume, conversion and
    cold start is recorded in ``problems``.
    """
    owner = resume_owner(checkpoint)
    if any(not isinstance(item, CheckpointConversion) for item in conversions):
        raise TypeError("conversions must be CheckpointConversion records")
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
    if owner is not None and owner not in {cap.solver_id for cap in ranked}:
        return AdvancedOrchestrationReport(
            (),
            ResourceUsage(),
            AdvancedStopReason.NO_CAPABLE_SOLVER,
            checkpoint,
            (f"resume_checkpoint_owner_{owner}_not_a_capable_declared_solver",),
        )
    if checkpoint is not None:
        refused = resume_refusal(
            checkpoint,
            solver_build=str(getattr(backends.get(owner), "solver_build", "")),
            problem_digest=plan.problem_digest,
        )
        if refused:
            # the caller asked to CONTINUE this state; continuing it on an
            # incompatible build or problem would not be a continuation
            return AdvancedOrchestrationReport(
                (),
                ResourceUsage(),
                AdvancedStopReason.NO_CAPABLE_SOLVER,
                checkpoint,
                (f"resume_checkpoint_refused: {refused}",),
            )
    builds_seen: dict[str, str] = {}

    attempts: list[AdvancedAttemptRecord] = []
    total = ResourceUsage()
    current_checkpoint = checkpoint
    refinement: RefinementRequest | None = None
    attempt_number = 0
    refinement_level = 0
    problems: list[str] = []

    for capability in ranked:
        if owner is not None and capability.solver_id != owner:
            # a resumed run continues ONE solver's state; another solver
            # cannot continue it and is not run cold in its place
            problems.append(
                f"{capability.solver_id}:resume_checkpoint_belongs_to_{owner}"
            )
            continue
        backend = backends.get(capability.solver_id)
        if backend is None:
            problems.append(f"{capability.solver_id}:backend_missing")
            continue
        if str(getattr(backend, "solver_id", "")) != capability.solver_id:
            problems.append(
                f"{capability.solver_id}:backend_solver_identity_mismatch"
            )
            continue

        # A refinement request answers ONE solver's error indicator; a fallback
        # route starts at its own level 0 (max_refinements counts per route,
        # the total stays bounded by max_attempts).
        refinement = None
        refinement_level = 0

        while attempt_number < plan.budget.max_attempts:
            attempt_number += 1
            attempt_id = (
                f"{plan.plan_id}:{attempt_number}:{capability.solver_id}:"
                f"r{refinement_level}"
            )
            build = str(getattr(backend, "solver_build", "")).strip()
            first = builds_seen.setdefault(capability.solver_id, build)
            if build != first:
                problems.append(f"{capability.solver_id}:build_drift_{first}_to_{build}_refused")
                break
            # a checkpoint is solver state: only the solver build that produced
            # it may resume from it; a fallback solver starts cold unless a
            # qualified conversion is declared for exactly this pair of builds
            resume_from = resume_point_for(
                current_checkpoint, capability.solver_id,
                solver_build=build, problem_digest=plan.problem_digest,
            )
            if resume_from is None and current_checkpoint is not None:
                resume_from, conversion = converted_resume_point(
                    current_checkpoint, solver_id=capability.solver_id, solver_build=build,
                    conversions=conversions,
                    accepts_converted=bool(getattr(backend, "accepts_converted_checkpoints", False)),
                )
                problems.append(
                    f"{capability.solver_id}:resume_via_conversion_{conversion.conversion_id}"
                    if conversion is not None
                    else f"{capability.solver_id}:cold_start_from_admitted_problem"
                )
            try:
                outcome = backend.run_advanced(
                    attempt_id=attempt_id,
                    deterministic_seed=plan.deterministic_seed,
                    checkpoint=resume_from,
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
                        None,
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
            adopted, problem = adopt_checkpoint(
                outcome.checkpoint,
                solver_id=capability.solver_id,
                state=outcome.state,
                solver_build=build,
                problem_digest=plan.problem_digest,
            )
            if problem:
                problems.append(problem)
            # the record carries only a checkpoint that was adopted: a refused
            # one is named in ``problems`` and is never readable as usable
            attempts.append(
                AdvancedAttemptRecord(
                    attempt,
                    capability.solver_id,
                    outcome.usage,
                    refinement,
                    adopted,
                )
            )
            if adopted is not None:
                current_checkpoint = adopted
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
                    # the accepted result's checkpoint is the one the ACCEPTED
                    # attempt returned, never an earlier, rejected refinement's
                    # or another route's
                    return AdvancedOrchestrationReport(
                        tuple(attempts),
                        total,
                        AdvancedStopReason.ERROR_TARGET_SATISFIED,
                        adopted,
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
