"""Deterministic orchestration for canonical EngineeringIntent records.

The planner is the scientific authority boundary between a typed engineering
intent and executable scientific declarations.  It never parses natural
language and never infers a model, realization, solver or graph from text.

Domains declare capabilities.  Registries expose admissible artifacts.
PlannerPolicy may resolve an otherwise explicit ambiguity.  This module only
combines those declarations into an auditable ScientificPlanningRecord.
"""

from __future__ import annotations

from .clarification import clarification_questions
from .intent import EngineeringIntent
from .policy import PlannerPolicy
from ..scientific.multiphysics import PortRef
from ..scientific.multiphysics.value import validate_port_coupling_value
from ..execution.multiphysics import ParticipantFactoryRegistry
from .records import (
    ExecutionMode,
    FidelityDecision,
    GapKind,
    GraphPlan,
    ModelExecutionChoice,
    PlanningGap,
    PlannedExternalInput,
    PlanningRegistries,
    PlanningStatus,
    QOIPlan,
    ResourceEstimate,
    ScientificPlanningRecord,
)
from .selection import (
    bindings_for_blueprint,
    blueprint_choice,
    execution_choices,
    fidelity_decision,
    resource_estimate,
)
from .validation import IssueKind, validate_intent


def _capability_selection(
    qoi_id: str,
    validation,
    policy: PlannerPolicy,
):
    eligible = validation.eligible_for(qoi_id)
    preferred = policy.capability_by_qoi.get(qoi_id)

    if preferred is not None:
        if "@" in preferred:
            wanted_id, wanted_version = preferred.rsplit("@", 1)
            matches = tuple(
                item
                for item in eligible
                if item.capability_id == wanted_id
                and item.capability_version == wanted_version
            )
        else:
            matches = tuple(
                item for item in eligible if item.capability_id == preferred
            )
        if len(matches) == 1:
            return matches[0], f"selected explicitly by policy: {preferred}"
        return (
            None,
            f"policy requested capability {preferred!r}, not a unique eligible candidate",
        )

    if len(eligible) == 1:
        return eligible[0], "only eligible capability"
    if not eligible:
        return None, "no eligible capability"
    return (
        None,
        f"{len(eligible)} eligible capabilities; explicit policy required",
    )


def _validation_gaps(validation) -> tuple[PlanningGap, ...]:
    gaps: list[PlanningGap] = []
    for issue in validation.issues:
        if issue.kind in {
            IssueKind.EVIDENCE_UNATTAINABLE,
            IssueKind.INDEPENDENT_ROUTE_UNAVAILABLE,
        }:
            gaps.append(
                PlanningGap(
                    GapKind.EVIDENCE_GAP,
                    issue.subject,
                    issue.detail,
                    issue.blocking,
                )
            )
        elif issue.kind is IssueKind.UNCERTAINTY_UNAVAILABLE:
            gaps.append(
                PlanningGap(
                    GapKind.UNCERTAINTY_GAP,
                    issue.subject,
                    issue.detail,
                    issue.blocking,
                )
            )
    return tuple(gaps)


def _build_qoi_plan(
    intent: EngineeringIntent,
    qoi,
    screen,
    selection_reason: str,
    alternatives: tuple[str, ...],
    registries: PlanningRegistries,
    policy: PlannerPolicy,
) -> tuple[QOIPlan, tuple[PlanningGap, ...]]:
    declaration = registries.capabilities.get(screen.capability_id)
    model_choices, selection_gaps = execution_choices(
        declaration,
        registries,
        policy,
    )

    execution_mode = (
        ExecutionMode.CAPABILITY_ROUTE
        if declaration.executable
        else ExecutionMode.MULTIPHYSICS_GRAPH
    )

    plan = QOIPlan(
        qoi_id=qoi.qoi_id,
        capability_id=declaration.capability_id,
        capability_version=declaration.version,
        capability_digest=declaration.digest,
        execution_mode=execution_mode,
        primary_route_id=declaration.primary_route.route_id,
        provided_capabilities=tuple(
            capability.identifier
            for capability in declaration.provided_capabilities
        ),
        model_choices=model_choices,
        required_inputs=tuple(
            item.path for item in declaration.inputs if item.required
        ),
        missing_inputs=screen.missing_inputs,
        required_levels=tuple(
            level.value for level in intent.context.required_levels
        ),
        attainable_levels=tuple(
            level.value for level in declaration.attainable(qoi.name)
        ),
        required_uncertainty=tuple(
            channel.value for channel in intent.context.required_uncertainty
        ),
        quantified_uncertainty=tuple(
            channel.value
            for channel in declaration.uncertainty.channels_for(qoi.name)
        ),
        alternatives=alternatives,
        reasons=(selection_reason,),
    )
    return plan, selection_gaps


def _select_versioned_record(
    candidates,
    preferred: str | None,
    *,
    identity_attr: str,
    version_attr: str = "version",
):
    candidates = tuple(candidates)
    if preferred is not None:
        if "@" in preferred:
            wanted_id, wanted_version = preferred.rsplit("@", 1)
            matches = tuple(
                item
                for item in candidates
                if getattr(item, identity_attr) == wanted_id
                and getattr(item, version_attr) == wanted_version
            )
        else:
            matches = tuple(
                item
                for item in candidates
                if getattr(item, identity_attr) == preferred
            )
        if len(matches) == 1:
            return matches[0], None
        return None, (
            f"policy requested {preferred!r}, not one exact candidate"
        )
    if len(candidates) == 1:
        return candidates[0], None
    if not candidates:
        return None, "no candidates"
    return None, (
        f"{len(candidates)} candidates require explicit planner policy"
    )


def _composition_graph_plan(
    *,
    capability_id: str,
    intent: EngineeringIntent,
    qoi_plans: tuple[QOIPlan, ...],
    registration,
    registries: PlanningRegistries,
    policy: PlannerPolicy,
    graph_required: bool,
) -> tuple[GraphPlan | None, tuple[PlanningGap, ...]]:
    gaps: list[PlanningGap] = []

    blueprints = tuple(
        item
        for item in registration.blueprints
        if item.capability_id == capability_id
    )
    blueprint, reason = _select_versioned_record(
        blueprints,
        policy.blueprint_by_capability.get(capability_id),
        identity_attr="blueprint_id",
    )
    if blueprint is None:
        gaps.append(
            PlanningGap(
                (
                    GapKind.GRAPH_BLUEPRINT_UNAVAILABLE
                    if not blueprints
                    else GapKind.GRAPH_BLUEPRINT_AMBIGUOUS
                ),
                capability_id,
                reason or "composition blueprint selection failed",
                graph_required,
            )
        )
        return None, tuple(gaps)

    bindings, binding_reason = bindings_for_blueprint(
        blueprint,
        qoi_plans,
    )
    if bindings is None:
        gaps.append(
            PlanningGap(
                GapKind.GRAPH_BLUEPRINT_UNAVAILABLE,
                capability_id,
                binding_reason
                or "composition participant bindings are unavailable",
                graph_required,
            )
        )
        return None, tuple(gaps)

    graph = blueprint.materialize(
        bindings,
        graph_id=f"planning.{capability_id}",
    )

    planned_external_inputs: list[PlannedExternalInput] = []
    for binding in registration.external_input_bindings:
        if binding.blueprint_id != blueprint.blueprint_id:
            continue
        ref = PortRef(binding.participant_id, binding.port_id)
        value = intent.fact_map.get(binding.fact_path)
        if value is None:
            gaps.append(
                PlanningGap(
                    GapKind.GRAPH_EXTERNAL_INPUT_MISSING,
                    ref.key,
                    (
                        f"graph external input {ref.key} requires canonical "
                        f"intent fact {binding.fact_path!r}"
                    ),
                    True,
                )
            )
            continue
        port = graph.participant(ref.participant_id).port(ref.port_id)
        try:
            validate_port_coupling_value(port, value)
        except Exception as exc:
            gaps.append(
                PlanningGap(
                    GapKind.GRAPH_EXTERNAL_INPUT_INVALID,
                    ref.key,
                    (
                        f"intent fact {binding.fact_path!r} cannot feed "
                        f"{ref.key}: {exc}"
                    ),
                    True,
                )
            )
            continue
        planned_external_inputs.append(
            PlannedExternalInput(
                port=ref,
                fact_path=binding.fact_path,
                value=value,
            )
        )

    applicability_rules = tuple(
        item
        for item in registration.applicability_rules
        if item.blueprint_id == blueprint.blueprint_id
    )
    fact_paths = set(intent.fact_map)
    missing_system_evidence = sorted(
        {
            requirement.path
            for rule in applicability_rules
            for requirement in rule.required_evidence
            if requirement.path not in fact_paths
        }
    )
    if missing_system_evidence:
        gaps.append(
            PlanningGap(
                GapKind.SYSTEM_APPLICABILITY_EVIDENCE_MISSING,
                blueprint.blueprint_id,
                (
                    "system-level applicability requires canonical intent "
                    f"facts at {missing_system_evidence}"
                ),
                True,
            )
        )

    uncertainty_rule = next(
        item
        for item in registration.uncertainty_rules
        if item.blueprint_id == blueprint.blueprint_id
    )
    required_uncertainty = set(intent.context.required_uncertainty)
    if required_uncertainty:
        declared_channels = set(uncertainty_rule.channels)
        missing_channels = sorted(
            (
                item.value
                for item in required_uncertainty - declared_channels
            )
        )
        if (
            uncertainty_rule.strategy.value == "unknown"
            or missing_channels
        ):
            detail = (
                "system uncertainty composition strategy is explicitly "
                "UNKNOWN"
                if uncertainty_rule.strategy.value == "unknown"
                else (
                    "system uncertainty composition does not cover "
                    f"required channels {missing_channels}"
                )
            )
            gaps.append(
                PlanningGap(
                    GapKind.SYSTEM_UNCERTAINTY_COMPOSITION_UNAVAILABLE,
                    blueprint.blueprint_id,
                    detail,
                    True,
                )
            )

    policy_candidates = tuple(
        item
        for item in registration.coupling_policy_templates
        if item.blueprint_id == blueprint.blueprint_id
    )
    selected_policy, policy_reason = _select_versioned_record(
        policy_candidates,
        policy.coupling_policy_by_blueprint.get(
            blueprint.blueprint_id
        ),
        identity_attr="template_id",
    )
    if selected_policy is None:
        gaps.append(
            PlanningGap(
                GapKind.COUPLING_POLICY_AMBIGUOUS,
                blueprint.blueprint_id,
                policy_reason or "coupling policy selection failed",
                graph_required,
            )
        )

    coupling_plan = None
    estimate = None
    if selected_policy is not None:
        if intent.simulation_horizon is None:
            gaps.append(
                PlanningGap(
                    GapKind.SIMULATION_HORIZON_REQUIRED,
                    blueprint.blueprint_id,
                    (
                        "cross-domain execution requires a canonical "
                        "simulation_horizon with start/end; Forge does not "
                        "invent an execution horizon"
                    ),
                    graph_required,
                )
            )
        else:
            coupling_plan = selected_policy.materialize(
                start=intent.simulation_horizon.start,
                end=intent.simulation_horizon.end,
                plan_id=(
                    f"planning.{capability_id}."
                    f"{selected_policy.template_id}"
                ),
            )
            coupling_plan.validate_against(graph)
            estimate = resource_estimate(
                coupling_plan,
                len(graph.participants),
                intent,
            )
            if estimate.within_declared_budget is False:
                gaps.append(
                    PlanningGap(
                        GapKind.BUDGET_EXCEEDED,
                        capability_id,
                        (
                            "declared compute budget is below the "
                            "deterministic upper bound for the selected "
                            "coupling policy"
                        ),
                        True,
                    )
                )

    execution_fingerprint = ""
    execution_pack_id = ""
    execution_pack_version = ""
    execution_pack_digest = ""
    execution_registry = None

    if registries.execution_packs is None:
        gaps.append(
            PlanningGap(
                GapKind.EXECUTION_PACK_UNAVAILABLE,
                blueprint.blueprint_id,
                "no ExecutionPackRegistry was supplied for the selected "
                "CompositionPack; exact executable authority is unavailable",
                graph_required,
            )
        )
        execution_registry = registries.participant_factories
    else:
        execution_matches = registries.execution_packs.for_composition(
            registration.manifest.pack_id,
            registration.manifest.pack_version,
            registration.manifest.digest,
            enabled_only=True,
        )
        if len(execution_matches) == 1:
            execution_registration = execution_matches[0]
            execution_pack_id = execution_registration.manifest.pack_id
            execution_pack_version = (
                execution_registration.manifest.pack_version
            )
            execution_pack_digest = execution_registration.authority_digest
            execution_registry = ParticipantFactoryRegistry(
                execution_registration.participant_factories
            )
        elif not execution_matches:
            gaps.append(
                PlanningGap(
                    GapKind.EXECUTION_PACK_UNAVAILABLE,
                    blueprint.blueprint_id,
                    (
                        "no enabled ExecutionPack is bound to exact "
                        f"CompositionPack {registration.manifest.pack_id}@"
                        f"{registration.manifest.pack_version}#"
                        f"{registration.manifest.digest}"
                    ),
                    graph_required,
                )
            )
        else:
            gaps.append(
                PlanningGap(
                    GapKind.EXECUTION_PACK_AMBIGUOUS,
                    blueprint.blueprint_id,
                    (
                        f"{len(execution_matches)} enabled ExecutionPacks bind "
                        "the exact same CompositionPack; product authority must "
                        "enable exactly one"
                    ),
                    graph_required,
                )
            )

    if execution_registry is None:
        gaps.append(
            PlanningGap(
                GapKind.EXECUTION_FACTORY_UNAVAILABLE,
                blueprint.blueprint_id,
                "no exact participant factory registry is available for "
                "the selected execution authority",
                graph_required,
            )
        )
    else:
        execution_fingerprint = execution_registry.fingerprint
        missing = execution_registry.missing(graph)
        if missing:
            gaps.append(
                PlanningGap(
                    GapKind.EXECUTION_FACTORY_UNAVAILABLE,
                    blueprint.blueprint_id,
                    "no exact Model/Realization/Solver/Adapter factory for "
                    f"participants {[item.participant_id for item in missing]}",
                    graph_required,
                )
            )

    return (
        GraphPlan(
            capability_id=capability_id,
            blueprint_id=blueprint.blueprint_id,
            blueprint_version=blueprint.version,
            graph=graph,
            coupling_plan=coupling_plan,
            resource_estimate=estimate,
            authority_pack_id=registration.manifest.pack_id,
            authority_pack_version=registration.manifest.pack_version,
            authority_pack_digest=registration.authority_digest,
            coupling_policy_template_id=(
                ""
                if selected_policy is None
                else selected_policy.template_id
            ),
            coupling_policy_template_version=(
                ""
                if selected_policy is None
                else selected_policy.version
            ),
            execution_registry_fingerprint=execution_fingerprint,
            execution_pack_id=execution_pack_id,
            execution_pack_version=execution_pack_version,
            execution_pack_digest=execution_pack_digest,
            external_inputs=tuple(planned_external_inputs),
        ),
        tuple(gaps),
    )


def _graph_plans(
    intent: EngineeringIntent,
    qoi_plans: tuple[QOIPlan, ...],
    registries: PlanningRegistries,
    policy: PlannerPolicy,
) -> tuple[tuple[GraphPlan, ...], tuple[PlanningGap, ...]]:
    graph_plans: list[GraphPlan] = []
    gaps: list[PlanningGap] = []
    by_capability = {
        item.capability_id: item for item in qoi_plans
    }

    for capability_id in sorted(by_capability):
        declaration = registries.capabilities.get(capability_id)
        graph_required = not declaration.executable

        composition_matches = ()
        if registries.composition_packs is not None:
            composition_matches = (
                registries.composition_packs.providing(
                    capability_id,
                    enabled_only=True,
                )
            )

        if len(composition_matches) > 1:
            gaps.append(
                PlanningGap(
                    GapKind.COMPOSITION_PACK_AMBIGUOUS,
                    capability_id,
                    (
                        f"{len(composition_matches)} enabled CompositionPacks "
                        "provide this capability; explicit product authority "
                        "must enable/select exactly one"
                    ),
                    graph_required,
                )
            )
            continue

        if len(composition_matches) == 1:
            graph_plan, local_gaps = _composition_graph_plan(
                capability_id=capability_id,
                intent=intent,
                qoi_plans=qoi_plans,
                registration=composition_matches[0],
                registries=registries,
                policy=policy,
                graph_required=graph_required,
            )
            gaps.extend(local_gaps)
            if graph_plan is not None:
                graph_plans.append(graph_plan)
            continue

        # Backward-compatible path for pre-CompositionPack blueprints.
        blueprint, gap = blueprint_choice(
            capability_id,
            registries.blueprints,
            policy,
            graph_required=graph_required,
        )
        if gap is not None:
            gaps.append(gap)
        if blueprint is None:
            continue

        bindings, reason = bindings_for_blueprint(
            blueprint,
            qoi_plans,
        )
        if bindings is None:
            gaps.append(
                PlanningGap(
                    GapKind.GRAPH_BLUEPRINT_UNAVAILABLE,
                    capability_id,
                    reason or "graph participant bindings are unavailable",
                    graph_required,
                )
            )
            continue

        graph, coupling_plan = blueprint.materialize(
            bindings,
            graph_id=f"planning.{capability_id}",
        )
        estimate = resource_estimate(
            coupling_plan,
            len(graph.participants),
            intent,
        )
        graph_plans.append(
            GraphPlan(
                capability_id=capability_id,
                blueprint_id=blueprint.blueprint_id,
                blueprint_version=blueprint.version,
                graph=graph,
                coupling_plan=coupling_plan,
                resource_estimate=estimate,
            )
        )
        if estimate.within_declared_budget is False:
            gaps.append(
                PlanningGap(
                    GapKind.BUDGET_EXCEEDED,
                    capability_id,
                    (
                        "declared compute budget is below the deterministic "
                        "upper bound for the selected coupling plan"
                    ),
                    True,
                )
            )

    return tuple(graph_plans), tuple(gaps)


def plan_engineering_intent(
    intent: EngineeringIntent,
    registries: PlanningRegistries,
    policy: PlannerPolicy | None = None,
) -> ScientificPlanningRecord:
    """Plan one canonical intent without natural-language interpretation."""

    if not isinstance(intent, EngineeringIntent):
        raise TypeError("plan_engineering_intent requires EngineeringIntent")
    if not isinstance(registries, PlanningRegistries):
        raise TypeError("plan_engineering_intent requires PlanningRegistries")
    policy = PlannerPolicy() if policy is None else policy
    if not isinstance(policy, PlannerPolicy):
        raise TypeError("policy must be PlannerPolicy")

    validation = validate_intent(
        intent,
        registries.capabilities,
        verification_registry=registries.verification,
    )

    qoi_plans: list[QOIPlan] = []
    gaps: list[PlanningGap] = list(_validation_gaps(validation))
    selected_by_qoi: dict[str, str] = {}
    unresolved: dict[str, str] = {}

    for qoi in intent.qois:
        screen, reason = _capability_selection(
            qoi.qoi_id,
            validation,
            policy,
        )
        if screen is None:
            unresolved[qoi.qoi_id] = reason
            continue

        selected_by_qoi[qoi.qoi_id] = screen.capability_id
        alternatives = tuple(
            item.capability_id
            for item in validation.eligible_for(qoi.qoi_id)
            if item.capability_id != screen.capability_id
        )
        qoi_plan, qoi_gaps = _build_qoi_plan(
            intent,
            qoi,
            screen,
            reason,
            alternatives,
            registries,
            policy,
        )
        qoi_plans.append(qoi_plan)
        gaps.extend(qoi_gaps)

    clarifications = clarification_questions(
        intent,
        validation,
        registries.capabilities,
        selected_capabilities=selected_by_qoi,
    )

    graph_plans, graph_gaps = _graph_plans(
        intent,
        tuple(qoi_plans),
        registries,
        policy,
    )
    gaps.extend(graph_gaps)

    fidelity, fidelity_gaps = fidelity_decision(
        intent,
        tuple(qoi_plans),
        registries,
        policy,
    )
    gaps.extend(fidelity_gaps)

    if any(
        issue.kind is IssueKind.NO_CAPABILITY
        for issue in validation.issues
    ):
        status = PlanningStatus.UNSUPPORTED
    elif unresolved:
        status = PlanningStatus.AMBIGUOUS
    elif clarifications or any(gap.blocking for gap in gaps):
        status = PlanningStatus.NEEDS_CLARIFICATION
    else:
        status = PlanningStatus.READY

    return ScientificPlanningRecord(
        intent_identity=intent.identity_digest,
        intent_record=intent.record_digest,
        capability_registry_digest=registries.capabilities.digest,
        status=status,
        qoi_plans=tuple(qoi_plans),
        clarifications=clarifications,
        gaps=tuple(gaps),
        graph_plans=graph_plans,
        fidelity=fidelity,
    )


__all__ = [
    "ExecutionMode",
    "FidelityDecision",
    "GapKind",
    "GraphPlan",
    "ModelExecutionChoice",
    "PlanningGap",
    "PlanningRegistries",
    "PlanningStatus",
    "QOIPlan",
    "ResourceEstimate",
    "ScientificPlanningRecord",
    "plan_engineering_intent",
]
