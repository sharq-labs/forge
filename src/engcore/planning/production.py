"""Production assembly for deterministic engineering planning.

Transport layers are deliberately absent from this module. Product capability
declarations come from engcore.product; installed scientific artifacts and
cross-domain authorities come from engcore.assembly.
"""

from __future__ import annotations

from ..claims.capabilities import CapabilityRegistry
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
    from ..domains.battery.models import battery_realizations
    from ..domains.electrical.material import resistance_realizations
    from ..domains.thermal_models.lumped import lumped_realizations

    by_key = {}
    for registry in (
        battery_realizations(),
        resistance_realizations(),
        lumped_realizations(),
    ):
        for realization in registry:
            existing = by_key.get(realization.key)
            if existing is not None and existing != realization:
                raise ValueError(
                    "built-in domains declare conflicting realization "
                    f"{realization.realization_id}@{realization.version}"
                )
            by_key[realization.key] = realization

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
    from ..domains.battery.solver import BatteryCellSolver
    from ..domains.electrical.dc.solver import ElectricalDCSolver
    from ..domains.electrical.material import ResistancePropertySolver
    from ..domains.thermal_models.lumped import LumpedThermalSolver

    factories = [
        BatteryCellSolver,
        ElectricalDCSolver,
        ResistancePropertySolver,
        LumpedThermalSolver,
    ]
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
        verification=VerificationPlanningRegistry(),
        fidelity_ladders=(),
    )


__all__ = ["production_planning_registries"]
