"""Atomic built-in Domain Pack for linear-TCR material resistance."""

from __future__ import annotations

from ..domains.electrical import material
from .manifest import ArtifactRef, DOMAIN_PACK_API, DomainPackManifest

PACK_ID = "electrical.material.linear_tcr"
PACK_VERSION = "1"

MANIFEST = DomainPackManifest(
    pack_id=PACK_ID,
    pack_version=PACK_VERSION,
    domain="electrical",
    compatible_core_apis=(DOMAIN_PACK_API,),
    capabilities=(material.TEMPERATURE_DEPENDENT_RESISTANCE.identifier,),
    models=(
        ArtifactRef(
            material.LINEAR_TCR_MODEL.model_id,
            material.LINEAR_TCR_MODEL.version,
        ),
    ),
    realizations=(
        ArtifactRef(
            material.LINEAR_TCR_REALIZATION.realization_id,
            material.LINEAR_TCR_REALIZATION.version,
        ),
    ),
    solvers=(
        ArtifactRef(material.SOLVER_ID, material.SOLVER_VERSION),
    ),
)


class ElectricalMaterialDomainPack:
    manifest = MANIFEST

    def models(self):
        return (material.LINEAR_TCR_MODEL,)

    def realizations(self):
        return (material.LINEAR_TCR_REALIZATION,)

    def solver_factories(self):
        return (material.ResistancePropertySolver,)

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


BUILTIN_ELECTRICAL_MATERIAL_PACK = ElectricalMaterialDomainPack()

__all__ = [
    "BUILTIN_ELECTRICAL_MATERIAL_PACK",
    "ElectricalMaterialDomainPack",
    "MANIFEST",
    "PACK_ID",
    "PACK_VERSION",
]
