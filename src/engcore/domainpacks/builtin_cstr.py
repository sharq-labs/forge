"""Built-in production Domain Pack for non-isothermal CSTR kinetics."""

from __future__ import annotations

from ..domains.kinetics.cstr import CSTR_MODEL, CSTRSolver, SOLVER_ID, SOLVER_VERSION
from ..domains.kinetics.cstr.realization import CSTR_REALIZATION, CSTR_TRANSIENT_SCIENCE
from ..domains.kinetics.cstr.independent_solver import (
    IndependentLSODASolver,
    SOLVER_ID as INDEPENDENT_SOLVER_ID,
    SOLVER_VERSION as INDEPENDENT_SOLVER_VERSION,
)
from ..domains.kinetics.cstr.validation import run_verification_gate
from ..mcp.cstr import cstr_capability
from .manifest import ArtifactRef, DOMAIN_PACK_API, DomainPackManifest
from .provider import ProvidedArtifact

PACK_ID = "kinetics.cstr"
PACK_VERSION = "2"

_VALIDATION_REF = ArtifactRef("kinetics.cstr.verification_gate", "0.2.0")

MANIFEST = DomainPackManifest(
    pack_id=PACK_ID,
    pack_version=PACK_VERSION,
    domain="kinetics",
    compatible_core_apis=(DOMAIN_PACK_API,),
    capabilities=(CSTR_TRANSIENT_SCIENCE.identifier,),
    models=(ArtifactRef(CSTR_MODEL.model_id, CSTR_MODEL.version),),
    realizations=(
        ArtifactRef(CSTR_REALIZATION.realization_id, CSTR_REALIZATION.version),
    ),
    solvers=tuple(sorted((
        ArtifactRef(SOLVER_ID, SOLVER_VERSION),
        ArtifactRef(INDEPENDENT_SOLVER_ID, INDEPENDENT_SOLVER_VERSION),
    ))),
    validation_protocols=(_VALIDATION_REF,),
)


class CSTRDomainPack:
    """Atomic built-in pack whose production claim declaration is executable."""

    manifest = MANIFEST

    def models(self):
        return (CSTR_MODEL,)

    def realizations(self):
        return (CSTR_REALIZATION,)

    def solver_factories(self):
        return (CSTRSolver, IndependentLSODASolver)

    def calibration_protocols(self):
        return ()

    def validation_protocols(self):
        return (ProvidedArtifact(_VALIDATION_REF, run_verification_gate),)

    def uq_producers(self):
        return ()

    def measurement_adapters(self):
        return ()

    def transformations(self):
        return ()

    def benchmarks(self):
        return ()

    def claim_capabilities(self):
        return (cstr_capability(),)


BUILTIN_CSTR_PACK = CSTRDomainPack()

__all__ = [
    "BUILTIN_CSTR_PACK",
    "CSTRDomainPack",
    "MANIFEST",
    "PACK_ID",
    "PACK_VERSION",
]
