"""Atomic built-in Domain Pack for equivalent-circuit battery science."""

from __future__ import annotations

from ..domains.battery import models
from ..domains.battery.solver import (
    BatteryCellSolver,
    SOLVER_ID,
    SOLVER_VERSION,
)
from .manifest import ArtifactRef, DOMAIN_PACK_API, DomainPackManifest

PACK_ID = "battery.cell"
PACK_VERSION = "1"

MANIFEST = DomainPackManifest(
    pack_id=PACK_ID,
    pack_version=PACK_VERSION,
    domain="battery",
    compatible_core_apis=(DOMAIN_PACK_API,),
    capabilities=(models.CELL_TERMINAL_STATE.identifier,),
    models=tuple(
        ArtifactRef(item.model_id, item.version)
        for item in models.BATTERY_MODELS
    ),
    realizations=tuple(
        ArtifactRef(item.realization_id, item.version)
        for item in models.BATTERY_REALIZATIONS
    ),
    solvers=(ArtifactRef(SOLVER_ID, SOLVER_VERSION),),
)


class BatteryCellDomainPack:
    manifest = MANIFEST

    def models(self):
        return models.BATTERY_MODELS

    def realizations(self):
        return models.BATTERY_REALIZATIONS

    def solver_factories(self):
        return (BatteryCellSolver,)

    def calibration_protocols(self):
        return ()

    def validation_protocols(self):
        return ()

    def uq_producers(self):
        return ()

    def measurement_adapters(self):
        return ()

    def transformations(self):
        return ()

    def benchmarks(self):
        return ()


BUILTIN_BATTERY_CELL_PACK = BatteryCellDomainPack()

__all__ = [
    "BUILTIN_BATTERY_CELL_PACK",
    "BatteryCellDomainPack",
    "MANIFEST",
    "PACK_ID",
    "PACK_VERSION",
]
