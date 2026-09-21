"""Production assembly for deterministic engineering planning.

Transport layers are deliberately absent from this module. Product capability
declarations come from engcore.product; installed scientific artifacts and
cross-domain authorities come from engcore.assembly.
"""

from __future__ import annotations

from ..claims.capabilities import CapabilityRegistry
from ..design.fidelity import FidelityLadder, FidelityRung
from ..scientific.models.registry import ModelRegistry
from ..scientific.realizations.registry import RealizationRegistry
from ..scientific.solvers.registry import SolverRegistry
from .blueprint import BlueprintRegistry
from .planner import PlanningRegistries
from .verification import VerificationPlanningRegistry


def _production_capabilities() -> CapabilityRegistry:
    from ..product.capabilities import production_registry

    return production_registry()


def _enabled_domain_packs():
    from ..assembly.domainpacks import (
        configure_production_domain_packs_from_env,
    )

    return configure_production_domain_packs_from_env().list(
        enabled_only=True
    )


def _production_models(
    capabilities: CapabilityRegistry,
) -> ModelRegistry:
    by_key = {}
    for declaration in capabilities:
        for use in declaration.models:
            definition = use.definition
            if definition is None:
                continue
            existing = by_key.get(definition.key)
            if existing is not None and existing != definition:
                raise ValueError(
                    "production capabilities attach conflicting definitions "
                    f"for model {definition.model_id}@{definition.version}"
                )
            by_key[definition.key] = definition

    for registration in _enabled_domain_packs():
        for definition in registration.provider.models():
            existing = by_key.get(definition.key)
            if existing is not None and existing != definition:
                raise ValueError(
                    "production Domain Packs declare conflicting model "
                    f"{definition.model_id}@{definition.version}"
                )
            by_key[definition.key] = definition

    return ModelRegistry(by_key[key] for key in sorted(by_key))


def _production_realizations() -> RealizationRegistry:
    by_key = {}
    for registration in _enabled_domain_packs():
        for realization in registration.provider.realizations():
            existing = by_key.get(realization.key)
            if existing is not None and existing != realization:
                raise ValueError(
                    "production Domain Packs declare conflicting realization "
                    f"{realization.realization_id}@{realization.version}"
                )
            by_key[realization.key] = realization

    return RealizationRegistry(by_key[key] for key in sorted(by_key))


def _production_solvers() -> SolverRegistry:
    factories = []
    for registration in _enabled_domain_packs():
        factories.extend(registration.provider.solver_factories())

    by_key = {}
    for factory in factories:
        probe = factory()
        key = probe.identity.key
        existing = by_key.get(key)
        if existing is not None and existing is not factory:
            # Same identity is allowed only when the callable itself is the
            # same frozen implementation.
            raise ValueError(
                "production solver identity collision for "
                f"{key[0]}@{key[1]}"
            )
        by_key[key] = factory

    return SolverRegistry(by_key[key] for key in sorted(by_key))


def _production_fidelity_ladders() -> tuple[FidelityLadder, ...]:
    """Study-scoped ladders backed by executable production capabilities.

    This is deliberately not a universal low/high-fidelity taxonomy.  The
    ordering is meaningful only for an electrothermal coupling study: the
    one-way composition omits electrical/thermal feedback, while the feedback
    composition resolves that interaction through its declared coupling plan.
    """

    return (
        FidelityLadder(
            ladder_id="system.electrothermal.coupling",
            version="1",
            rungs=(
                FidelityRung(
                    rung_id="one_way",
                    rank=0,
                    required_capabilities=frozenset({
                        "system.thermal_resistance_property",
                    }),
                    description=(
                        "One-way thermal-to-resistance composition; electrical "
                        "heating does not feed back into temperature."
                    ),
                ),
                FidelityRung(
                    rung_id="feedback",
                    rank=1,
                    required_capabilities=frozenset({
                        "system.electrothermal_feedback",
                    }),
                    description=(
                        "Closed-loop electrothermal feedback using the pinned "
                        "production coupling and execution packs."
                    ),
                ),
            ),
        ),
    )


def production_planning_registries() -> PlanningRegistries:
    """The exact currently-enabled scientific planning universe."""

    from ..assembly.domainpacks import (
        production_composition_packs,
        production_execution_packs,
    )

    capabilities = _production_capabilities()
    compositions = production_composition_packs()
    executions = production_execution_packs()

    return PlanningRegistries(
        capabilities=capabilities,
        models=_production_models(capabilities),
        realizations=_production_realizations(),
        solvers=_production_solvers(),
        # Legacy single-pack blueprints remain readable but are no longer
        # populated by production Domain Packs.
        blueprints=BlueprintRegistry(),
        composition_packs=compositions,
        participant_factories=executions.participant_factory_registry(
            enabled_only=True
        ),
        execution_packs=executions,
        verification=VerificationPlanningRegistry(),
        fidelity_ladders=_production_fidelity_ladders(),
    )


__all__ = ["production_planning_registries"]
