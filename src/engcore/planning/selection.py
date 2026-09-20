"""Deterministic selection rules used by the engineering planner."""

from __future__ import annotations

import math
from typing import Any, Mapping

from ..claims.capabilities import CapabilityDeclaration
from ..design.fidelity import FidelityRung
from ..scientific.multiphysics import CouplingPlan
from ..scientific.realizations.definition import ModelRealizationDefinition
from ..scientific.solvers.registry import SolverRegistry
from .blueprint import (
    BlueprintRegistry,
    ParticipantBinding,
    PhysicsGraphBlueprint,
)
from .intent import EngineeringIntent
from .policy import PlannerPolicy
from .records import (
    FidelityDecision,
    GapKind,
    ModelExecutionChoice,
    PlanningGap,
    PlanningRegistries,
    QOIPlan,
    ResourceEstimate,
)


def _select_by_identity(
    candidates: tuple[Any, ...],
    preferred: str | None,
    *,
    identity,
) -> tuple[Any | None, str]:
    if preferred is not None:
        matches = [
            item for item in candidates
            if identity(item) == preferred
        ]
        if len(matches) == 1:
            return (
                matches[0],
                f"selected explicitly by policy: {preferred}",
            )
        return (
            None,
            f"policy requested {preferred!r}, not a unique eligible candidate",
        )
    if len(candidates) == 1:
        return candidates[0], "only eligible candidate"
    if not candidates:
        return None, "no eligible candidate"
    return (
        None,
        f"{len(candidates)} eligible candidates; explicit policy required",
    )


def _solver_candidates(
    registry: SolverRegistry,
    realization: ModelRealizationDefinition,
    declaration: CapabilityDeclaration,
) -> tuple[Any, ...]:
    required = {
        item.name
        for item in realization.required_solver_capabilities
    }
    declared_ids = {
        item.solver_id for item in declaration.solvers
    }
    found = []
    for solver in registry.list():
        provided = {item.name for item in solver.capabilities}
        if required - provided:
            continue
        served_models = {
            item.key for item in getattr(solver, "served_models", ())
        }
        if (
            served_models
            and realization.model_key not in served_models
        ):
            continue
        if (
            declared_ids
            and solver.identity.solver_id not in declared_ids
        ):
            continue
        found.append(solver)
    return tuple(
        sorted(found, key=lambda item: item.identity.key)
    )


def execution_choices(
    declaration: CapabilityDeclaration,
    registries: PlanningRegistries,
    policy: PlannerPolicy,
) -> tuple[
    tuple[ModelExecutionChoice, ...],
    tuple[PlanningGap, ...],
]:
    choices: list[ModelExecutionChoice] = []
    gaps: list[PlanningGap] = []
    graph_required = not declaration.executable

    if registries.models is None:
        gaps.append(
            PlanningGap(
                GapKind.MODEL_REGISTRY_MISSING,
                declaration.capability_id,
                "no ModelRegistry was supplied; model identities can be "
                "reported but not independently resolved",
                graph_required,
            )
        )
    if registries.realizations is None:
        gaps.append(
            PlanningGap(
                GapKind.REALIZATION_REGISTRY_MISSING,
                declaration.capability_id,
                "no RealizationRegistry was supplied; generic participant "
                "realization selection is unavailable, but a declared "
                "capability executor may still run",
                graph_required,
            )
        )

    for model in declaration.models:
        basis = [
            f"capability pins model {model.model_id}@{model.version}"
        ]
        if (
            registries.models is not None
            and not registries.models.contains(
                model.model_id,
                model.version,
            )
        ):
            gaps.append(
                PlanningGap(
                    GapKind.MODEL_NOT_REGISTERED,
                    model.model_id,
                    f"capability declares {model.model_id}@{model.version}, "
                    "absent from supplied ModelRegistry",
                    graph_required,
                )
            )

        realization_candidates: tuple[
            ModelRealizationDefinition, ...
        ] = ()
        selected_realization: (
            ModelRealizationDefinition | None
        ) = None
        if registries.realizations is not None:
            realization_candidates = (
                registries.realizations.for_model(
                    model.model_id,
                    model.version,
                )
            )
            preferred = policy.realization_by_model.get(
                model.model_id
            )
            selected_realization, why = _select_by_identity(
                realization_candidates,
                preferred,
                identity=lambda item: item.realization_id,
            )
            basis.append(why)
            if selected_realization is None:
                gaps.append(
                    PlanningGap(
                        (
                            GapKind.REALIZATION_NOT_FOUND
                            if not realization_candidates
                            else GapKind.REALIZATION_AMBIGUOUS
                        ),
                        model.model_id,
                        why,
                        graph_required,
                    )
                )

        solver_candidates: tuple[Any, ...] = ()
        selected_solver = None
        if selected_realization is not None:
            provided_science = {
                item.capability
                for item in declaration.provides
            }
            missing_science = sorted(
                capability.identifier
                for capability in (
                    selected_realization.required_capabilities
                    - provided_science
                )
            )
            if missing_science:
                gaps.append(
                    PlanningGap(
                        GapKind.REALIZATION_CAPABILITY_UNSATISFIED,
                        selected_realization.realization_id,
                        (
                            "selected realization requires scientific "
                            f"capabilities not provided by the capability "
                            f"declaration: {missing_science}"
                        ),
                        graph_required,
                    )
                )
            if not selected_realization.required_solver_capabilities:
                basis.append(
                    "selected realization declares no external solver "
                    "capability requirement"
                )
            elif registries.solvers is None:
                gaps.append(
                    PlanningGap(
                        GapKind.SOLVER_REGISTRY_MISSING,
                        selected_realization.realization_id,
                        "realization requires solver capabilities but no "
                        "SolverRegistry was supplied; generic participant "
                        "materialization is unavailable",
                        graph_required,
                    )
                )
            else:
                solver_candidates = _solver_candidates(
                    registries.solvers,
                    selected_realization,
                    declaration,
                )
                preferred = (
                    policy.solver_by_realization.get(
                        selected_realization.realization_id
                    )
                )
                selected_solver, why = _select_by_identity(
                    solver_candidates,
                    preferred,
                    identity=lambda item: item.identity.solver_id,
                )
                basis.append(why)
                if selected_solver is None:
                    gaps.append(
                        PlanningGap(
                            (
                                GapKind.SOLVER_NOT_FOUND
                                if not solver_candidates
                                else GapKind.SOLVER_AMBIGUOUS
                            ),
                            selected_realization.realization_id,
                            why,
                            graph_required,
                        )
                    )

        choices.append(
            ModelExecutionChoice(
                model_id=model.model_id,
                model_version=model.version,
                realization_candidates=tuple(
                    f"{item.realization_id}@{item.version}"
                    for item in realization_candidates
                ),
                selected_realization=(
                    None
                    if selected_realization is None
                    else (
                        f"{selected_realization.realization_id}@"
                        f"{selected_realization.version}"
                    )
                ),
                solver_candidates=tuple(
                    f"{item.identity.solver_id}@"
                    f"{item.identity.version}"
                    for item in solver_candidates
                ),
                selected_solver=(
                    None
                    if selected_solver is None
                    else (
                        f"{selected_solver.identity.solver_id}@"
                        f"{selected_solver.identity.version}"
                    )
                ),
                selected_realization_capabilities=(
                    ()
                    if selected_realization is None
                    else tuple(
                        sorted(
                            cap.identifier
                            for cap in (
                                selected_realization
                                .provided_capabilities
                            )
                        )
                    )
                ),
                selected_solver_capabilities=(
                    ()
                    if selected_solver is None
                    else tuple(
                        sorted(
                            cap.name
                            for cap in selected_solver.capabilities
                        )
                    )
                ),
                selection_basis=tuple(basis),
            )
        )

    return tuple(choices), tuple(gaps)


def _available_fidelity_tokens(
    qoi_plans: tuple[QOIPlan, ...],
) -> set[str]:
    tokens: set[str] = set()
    for plan in qoi_plans:
        tokens.add(plan.capability_id)
        tokens.update(plan.provided_capabilities)
        for choice in plan.model_choices:
            if choice.selected_realization:
                tokens.add(
                    choice.selected_realization.split("@", 1)[0]
                )
            if choice.selected_solver:
                tokens.add(
                    choice.selected_solver.split("@", 1)[0]
                )
            tokens.update(
                choice.selected_realization_capabilities
            )
            tokens.update(
                choice.selected_solver_capabilities
            )
    return tokens


def fidelity_decision(
    intent: EngineeringIntent,
    qoi_plans: tuple[QOIPlan, ...],
    registries: PlanningRegistries,
    policy: PlannerPolicy,
) -> tuple[
    FidelityDecision | None,
    tuple[PlanningGap, ...],
]:
    request = intent.fidelity
    if request is None:
        return None, ()

    ladder = registries.fidelity(
        request.ladder_id,
        request.ladder_version,
    )
    if ladder is None:
        return (
            FidelityDecision(
                request.ladder_id,
                request.ladder_version,
                request.minimum_rung,
                request.preferred_rung,
                None,
                (),
                "requested study-specific fidelity ladder is not registered",
            ),
            (
                PlanningGap(
                    GapKind.FIDELITY_LADDER_MISSING,
                    request.ladder_id,
                    f"no fidelity ladder {request.ladder_id}@"
                    f"{request.ladder_version}",
                    True,
                ),
            ),
        )

    minimum = (
        ladder.rung(request.minimum_rung)
        if request.minimum_rung
        else ladder.rungs[0]
    )
    preferred = (
        ladder.rung(request.preferred_rung)
        if request.preferred_rung
        else minimum
    )
    if preferred.rank < minimum.rank:
        raise ValueError(
            "preferred fidelity rung cannot be below minimum rung"
        )

    tokens = _available_fidelity_tokens(qoi_plans)
    available = tuple(
        rung
        for rung in ladder.rungs
        if not set(rung.required_capabilities) - tokens
    )
    candidates = tuple(
        rung
        for rung in available
        if minimum.rank <= rung.rank <= preferred.rank
    )

    selected: FidelityRung | None = None
    if preferred in candidates:
        selected = preferred
        reason = "preferred rung requirements are satisfied"
    elif policy.allow_fidelity_downgrade and candidates:
        selected = max(
            candidates,
            key=lambda rung: rung.rank,
        )
        reason = (
            "preferred rung is unavailable; policy allows "
            f"downgrade to {selected.rung_id}"
        )
    else:
        reason = (
            "requested fidelity requirements are not all available"
        )

    gaps: tuple[PlanningGap, ...] = ()
    if selected is None:
        gaps = (
            PlanningGap(
                GapKind.FIDELITY_UNAVAILABLE,
                request.ladder_id,
                reason,
                True,
            ),
        )

    return (
        FidelityDecision(
            ladder_id=ladder.ladder_id,
            ladder_version=ladder.version,
            minimum_rung=minimum.rung_id,
            preferred_rung=preferred.rung_id,
            selected_rung=(
                None
                if selected is None
                else selected.rung_id
            ),
            available_rungs=tuple(
                rung.rung_id for rung in available
            ),
            reason=reason,
        ),
        gaps,
    )


def resource_estimate(
    plan: CouplingPlan,
    participant_count: int,
    intent: EngineeringIntent,
) -> ResourceEstimate:
    start = plan.time.start.magnitude_in("second")
    end = plan.time.end.magnitude_in("second")
    window = plan.time.coupling_window.magnitude_in(
        "second"
    )
    windows = int(math.ceil((end - start) / window))
    lower = windows * participant_count
    upper = lower * plan.max_iterations
    budget = intent.compute_budget.max_solver_calls
    within = None if budget is None else upper <= budget

    return ResourceEstimate(
        solver_calls_lower_bound=lower,
        solver_calls_upper_bound=upper,
        within_declared_budget=within,
        basis=(
            "bound from coupling windows × participants × coupling "
            "iterations; wall-time is not estimated because no "
            "calibrated performance model was declared"
        ),
    )


def blueprint_choice(
    capability_id: str,
    registry: BlueprintRegistry | None,
    policy: PlannerPolicy,
    *,
    graph_required: bool,
) -> tuple[
    PhysicsGraphBlueprint | None,
    PlanningGap | None,
]:
    if registry is None:
        return (
            None,
            PlanningGap(
                GapKind.GRAPH_BLUEPRINT_UNAVAILABLE,
                capability_id,
                "no BlueprintRegistry was supplied; generic "
                "PhysicsGraph synthesis is unavailable",
                graph_required,
            ),
        )

    candidates = registry.for_capability(capability_id)
    preferred = policy.blueprint_by_capability.get(
        capability_id
    )
    if preferred:
        if "@" in preferred:
            wanted_id, wanted_version = preferred.rsplit(
                "@",
                1,
            )
            matches = [
                item
                for item in candidates
                if item.blueprint_id == wanted_id
                and item.version == wanted_version
            ]
        else:
            matches = [
                item
                for item in candidates
                if item.blueprint_id == preferred
            ]
        if len(matches) == 1:
            return matches[0], None
        return (
            None,
            PlanningGap(
                GapKind.GRAPH_BLUEPRINT_AMBIGUOUS,
                capability_id,
                f"policy requested blueprint {preferred!r}, "
                "not a unique candidate",
                graph_required,
            ),
        )

    if len(candidates) == 1:
        return candidates[0], None
    if not candidates:
        return (
            None,
            PlanningGap(
                GapKind.GRAPH_BLUEPRINT_UNAVAILABLE,
                capability_id,
                "capability has no registered generic PhysicsGraph "
                "blueprint; declared capability executor remains "
                "the only execution route",
                graph_required,
            ),
        )

    return (
        None,
        PlanningGap(
            GapKind.GRAPH_BLUEPRINT_AMBIGUOUS,
            capability_id,
            "multiple graph blueprints are registered: "
            f"{[item.blueprint_id+'@'+item.version for item in candidates]}",
            graph_required,
        ),
    )


def bindings_for_blueprint(
    blueprint: Any,
    qoi_plans: tuple[QOIPlan, ...],
    *,
    execution_factories: tuple[Any, ...] = (),
) -> tuple[
    Mapping[str, ParticipantBinding] | None,
    str | None,
]:
    choices = {
        choice.model_id: choice
        for plan in qoi_plans
        if plan.capability_id == blueprint.capability_id
        for choice in plan.model_choices
    }
    bindings: dict[str, ParticipantBinding] = {}

    for participant in blueprint.participants:
        factory_candidates = tuple(
            item
            for item in execution_factories
            if (
                getattr(item, "model_keys", ()) == participant.model_keys
                and item.adapter_id == participant.adapter_id
                and item.adapter_version == participant.adapter_version
            )
        )

        primary_choice = choices.get(participant.model_id)
        if factory_candidates:
            narrowed = factory_candidates
            if (
                primary_choice is not None
                and primary_choice.selected_realization is not None
                and primary_choice.selected_solver is not None
            ):
                realization_id, realization_version = (
                    primary_choice.selected_realization.rsplit("@", 1)
                )
                solver_id, solver_version = (
                    primary_choice.selected_solver.rsplit("@", 1)
                )
                narrowed = tuple(
                    item
                    for item in factory_candidates
                    if (
                        item.realization_id == realization_id
                        and item.realization_version == realization_version
                        and item.solver_id == solver_id
                        and item.solver_version == solver_version
                    )
                )

            if len(narrowed) == 1:
                item = narrowed[0]
                bindings[participant.participant_id] = ParticipantBinding(
                    participant_id=participant.participant_id,
                    realization_id=item.realization_id,
                    realization_version=item.realization_version,
                    solver_id=item.solver_id,
                    solver_version=item.solver_version,
                )
                continue
            if not narrowed:
                return (
                    None,
                    f"participant {participant.participant_id} has no "
                    "ExecutionPack factory matching its selected execution "
                    "stack and complete model assembly",
                )
            return (
                None,
                f"participant {participant.participant_id} has "
                f"{len(narrowed)} execution factories; select an exact "
                "ExecutionPack or execution policy",
            )

        choice = primary_choice
        if (
            choice is None
            or choice.selected_realization is None
            or choice.selected_solver is None
        ):
            return (
                None,
                f"participant {participant.participant_id} needs either one "
                "exact ExecutionPack factory or selected realization and "
                f"solver for primary model {participant.model_id}",
            )

        realization_id, realization_version = (
            choice.selected_realization.rsplit("@", 1)
        )
        solver_id, solver_version = (
            choice.selected_solver.rsplit("@", 1)
        )
        bindings[participant.participant_id] = ParticipantBinding(
            participant_id=participant.participant_id,
            realization_id=realization_id,
            realization_version=realization_version,
            solver_id=solver_id,
            solver_version=solver_version,
        )

    return bindings, None


__all__ = [
    "bindings_for_blueprint",
    "blueprint_choice",
    "execution_choices",
    "fidelity_decision",
    "resource_estimate",
]
