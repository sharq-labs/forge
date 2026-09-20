"""Atomic built-in Domain Pack for linear DC circuit analysis."""

from __future__ import annotations

from ..domains.electrical.dc.models import DC_MODELS
from ..domains.electrical.dc.realizations import (
    DC_NETWORK_STATE,
    MNA_NETWORK_REALIZATION,
)
from ..domains.electrical.dc.solver import (
    ElectricalDCSolver,
    SOLVER_ID,
    SOLVER_VERSION,
)
from .manifest import ArtifactRef, DOMAIN_PACK_API, DomainPackManifest

PACK_ID = "electrical.dc"
PACK_VERSION = "1"

MANIFEST = DomainPackManifest(
    pack_id=PACK_ID,
    pack_version=PACK_VERSION,
    domain="electrical",
    compatible_core_apis=(DOMAIN_PACK_API,),
    capabilities=(DC_NETWORK_STATE.identifier,),
    models=tuple(
        ArtifactRef(item.model_id, item.version)
        for item in DC_MODELS
    ),
    realizations=(
        ArtifactRef(
            MNA_NETWORK_REALIZATION.realization_id,
            MNA_NETWORK_REALIZATION.version,
        ),
    ),
    solvers=(ArtifactRef(SOLVER_ID, SOLVER_VERSION),),
)


class ElectricalDCDomainPack:
    manifest = MANIFEST

    def models(self):
        return DC_MODELS

    def realizations(self):
        return (MNA_NETWORK_REALIZATION,)

    def solver_factories(self):
        return (ElectricalDCSolver,)

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


BUILTIN_ELECTRICAL_DC_PACK = ElectricalDCDomainPack()

__all__ = [
    "BUILTIN_ELECTRICAL_DC_PACK",
    "ElectricalDCDomainPack",
    "MANIFEST",
    "PACK_ID",
    "PACK_VERSION",
]
