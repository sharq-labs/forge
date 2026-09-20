"""Production assembly for the engineering planner.

This module is deliberately the place that knows which built-in domain packs
are installed.  The generic planner never imports battery/thermal/electrical
modules or branches on their names; product assembly supplies their registries.
Enabled external Domain Packs can add capability declarations today and can add
planning registries/blueprints through the same explicit dependencies later.
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
    # Import lazily: planning is a core/product concern and importing it must
    # not initialize MCP or production domains unless a product asks for them.
    from ..mcp.capabilities import production_registry

    return production_registry()


def _models_from_capabilities(capabilities: CapabilityRegistry) -> ModelRegistry:
    by_key = {}
    for declaration in capabilities:
        for use in declaration.models:
            definition = use.definition
            if definition is None:
                continue
            existing = by_key.get(definition.key)
            if existing is not None and existing != definition:
                raise ValueError(
                    f"production capabilities attach conflicting definitions "
                    f"for model {definition.model_id}@{definition.version}"
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
                    f"built-in domains declare conflicting realization "
                    f"{realization.realization_id}@{realization.version}"
                )
            by_key[realization.key] = realization

    from ..mcp.production_packs import (
        configure_production_domain_packs_from_env,
    )

    packs = configure_production_domain_packs_from_env()
    for registered in packs.list(enabled_only=True):
        for realization in registered.provider.realizations():
            existing = by_key.get(realization.key)
            if existing is not None and existing != realization:
                raise ValueError(
                    "production domain packs declare conflicting realization "
                    f"{realization.realization_id}@{realization.version}"
                )
            by_key[realization.key] = realization

    return RealizationRegistry(by_key[key] for key in sorted(by_key))


def _production_solvers() -> SolverRegistry:
    from ..domains.battery.solver import BatteryCellSolver
    from ..domains.electrical.dc.solver import ElectricalDCSolver
    from ..domains.electrical.material import ResistancePropertySolver
    from ..domains.thermal_models.lumped import LumpedThermalSolver

    # SolverRegistry requires factories and proves every issued session is
    # fresh. Merge built-ins and enabled pack factories by exact identity.
    factories = [
        BatteryCellSolver,
        ElectricalDCSolver,
        ResistancePropertySolver,
        LumpedThermalSolver,
    ]

    from ..mcp.production_packs import (
        configure_production_domain_packs_from_env,
    )

    packs = configure_production_domain_packs_from_env()
    for registered in packs.list(enabled_only=True):
        factories.extend(registered.provider.solver_factories())

    by_key = {}
    for factory in factories:
        probe = factory()
        key = probe.identity.key
        existing = by_key.get(key)
        if existing is not None and existing is not factory:
            raise ValueError(
                "production solver identity collision for "
                f"{key[0]}@{key[1]}"
            )
        by_key[key] = factory

    return SolverRegistry(by_key[key] for key in sorted(by_key))


def production_planning_registries() -> PlanningRegistries:
    """The currently installed product planning universe.

    No blueprint or verification-independence metadata is invented here.
    Enabled packs may explicitly contribute validated PhysicsGraph blueprints,
    realizations and solver factories. Generic graph synthesis still refuses
    to guess missing scientific wiring; only declared stronger contracts enter
    the planning universe.
    """
    capabilities = _production_capabilities()

    from ..mcp.production_packs import production_pack_blueprints

    return PlanningRegistries(
        capabilities=capabilities,
        models=_models_from_capabilities(capabilities),
        realizations=_production_realizations(),
        solvers=_production_solvers(),
        blueprints=BlueprintRegistry(production_pack_blueprints()),
        verification=VerificationPlanningRegistry(),
        fidelity_ladders=(),
    )


__all__ = ["production_planning_registries"]
