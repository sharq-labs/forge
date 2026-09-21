"""Domain Pack for the flagship 1-RC electrothermal cell.

Separate from ``battery.cell@1`` on purpose. That pack's docstring says the
1-RC kernel "joins a pack when it passes its own calibration/validation gate,
not before". Sprint 3 built that gate, so the kernel is promoted -- into a pack
of its own, carrying its own model, realization and solver, with the Rint pack
left exactly as it was.

The two are different scientific claims about the same physical cell. Merging
them would give one manifest to two validity domains, which is the failure
``battery.cell@1``'s own consolidation round was about.
"""

from __future__ import annotations

from ..domains.battery import flagship, flagship_v2
from .manifest import ArtifactRef, DOMAIN_PACK_API, DomainPackManifest

PACK_ID = "battery.electrothermal"
PACK_VERSION = "1"

MANIFEST = DomainPackManifest(
    pack_id=PACK_ID,
    pack_version=PACK_VERSION,
    domain="battery",
    compatible_core_apis=(DOMAIN_PACK_API,),
    capabilities=(flagship.ELECTROTHERMAL_CELL_STATE.identifier,),
    models=(
        ArtifactRef(
            flagship.ELECTROTHERMAL_1RC_MODEL.model_id,
            flagship.ELECTROTHERMAL_1RC_MODEL.version,
        ),
        # 0.2.0 joins 0.1.0 rather than replacing it. The older version is what
        # the Sprint 3 flagship's evidence is about, and a record whose model
        # has been silently re-pointed is a record about nothing.
        ArtifactRef(
            flagship_v2.ELECTROTHERMAL_1RC_V2_MODEL.model_id,
            flagship_v2.ELECTROTHERMAL_1RC_V2_MODEL.version,
        ),
    ),
    realizations=(
        ArtifactRef(
            flagship.ELECTROTHERMAL_1RC_REALIZATION.realization_id,
            flagship.ELECTROTHERMAL_1RC_REALIZATION.version,
        ),
        ArtifactRef(
            flagship_v2.ELECTROTHERMAL_1RC_V2_REALIZATION.realization_id,
            flagship_v2.ELECTROTHERMAL_1RC_V2_REALIZATION.version,
        ),
    ),
    solvers=(ArtifactRef(flagship.SOLVER_ID, flagship.SOLVER_VERSION),),
)


class BatteryElectrothermalDomainPack:
    """Atomic provider for the flagship cell's artifacts."""

    manifest = MANIFEST

    def models(self):
        return flagship.ELECTROTHERMAL_MODELS + flagship_v2.ELECTROTHERMAL_V2_MODELS

    def realizations(self):
        return (
            flagship.ELECTROTHERMAL_REALIZATIONS
            + flagship_v2.ELECTROTHERMAL_V2_REALIZATIONS
        )

    def solver_factories(self):
        return (flagship.ElectrothermalCellSolver,)

    def calibration_protocols(self):
        # The flagship's parameters are fitted against measured trajectories by
        # the campaign, and the record that comes out is a
        # CalibratedParameterSet. That is not a domain calibration protocol --
        # it produces no production authority and promotes nothing -- so none is
        # declared here rather than one being invented to fill the slot.
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


BUILTIN_BATTERY_ELECTROTHERMAL_PACK = BatteryElectrothermalDomainPack()


def domain_pack() -> BatteryElectrothermalDomainPack:
    """Zero-argument factory for the ``forge.domainpacks`` entry-point contract."""
    return BUILTIN_BATTERY_ELECTROTHERMAL_PACK


__all__ = [
    "BUILTIN_BATTERY_ELECTROTHERMAL_PACK",
    "BatteryElectrothermalDomainPack",
    "MANIFEST",
    "PACK_ID",
    "PACK_VERSION",
    "domain_pack",
]
