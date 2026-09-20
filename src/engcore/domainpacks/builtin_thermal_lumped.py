"""Atomic built-in Domain Pack for the lumped thermal model."""

from __future__ import annotations

from ..domains.thermal_models import lumped
from .manifest import ArtifactRef, DOMAIN_PACK_API, DomainPackManifest

PACK_ID = "thermal.lumped"
PACK_VERSION = "1"

MANIFEST = DomainPackManifest(
    pack_id=PACK_ID,
    pack_version=PACK_VERSION,
    domain="thermal",
    compatible_core_apis=(DOMAIN_PACK_API,),
    capabilities=(lumped.BODY_TEMPERATURE.identifier,),
    models=(
        ArtifactRef(
            lumped.LUMPED_CAPACITY_MODEL.model_id,
            lumped.LUMPED_CAPACITY_MODEL.version,
        ),
    ),
    realizations=(
        ArtifactRef(
            lumped.LUMPED_CLOSED_FORM_REALIZATION.realization_id,
            lumped.LUMPED_CLOSED_FORM_REALIZATION.version,
        ),
    ),
    solvers=(
        ArtifactRef(lumped.SOLVER_ID, lumped.SOLVER_VERSION),
    ),
)


class ThermalLumpedDomainPack:
    manifest = MANIFEST

    def models(self):
        return (lumped.LUMPED_CAPACITY_MODEL,)

    def realizations(self):
        return (lumped.LUMPED_CLOSED_FORM_REALIZATION,)

    def solver_factories(self):
        return (lumped.LumpedThermalSolver,)

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


BUILTIN_THERMAL_LUMPED_PACK = ThermalLumpedDomainPack()

__all__ = [
    "BUILTIN_THERMAL_LUMPED_PACK",
    "MANIFEST",
    "PACK_ID",
    "PACK_VERSION",
    "ThermalLumpedDomainPack",
]
