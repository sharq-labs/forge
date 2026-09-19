"""Built-in Battery Domain Pack.

This adapter wraps the existing battery domain without moving its modules.
Only artifacts owned by the battery domain are exposed here. Outer claim
adapters are deliberately excluded so the dependency direction remains:

    claims -> domain pack -> battery domain -> scientific core

and never battery domain -> claims.
"""

from __future__ import annotations

from ...domainpacks.manifest import (
    ArtifactRef,
    DOMAIN_PACK_API,
    DomainPackManifest,
)
from ...domainpacks.provider import ProvidedArtifact
from . import calibration
from . import empirical
from . import models
from .solver import BatteryCellSolver


PACK_VERSION = "1.0.0"

BATTERY_PACK_MANIFEST = DomainPackManifest(
    pack_id="battery",
    pack_version=PACK_VERSION,
    domain="battery",
    compatible_core_apis=(DOMAIN_PACK_API,),
    capabilities=("battery:cell_terminal_state",),
    models=(
        ArtifactRef("battery.cell.rint_ocv", "0.1.0"),
        ArtifactRef("battery.cell.coulomb_counting", "0.1.0"),
        ArtifactRef("battery.cell.constant_current_runtime", "0.1.0"),
        ArtifactRef("battery.cell.peukert_capacity_derating", "0.1.0"),
    ),
    realizations=(
        ArtifactRef("battery.cell.rint_ocv.closed_form", "0.1.0"),
        ArtifactRef("battery.cell.coulomb_counting.exact_constant_current", "0.1.0"),
        ArtifactRef("battery.cell.constant_current_runtime.closed_form", "0.1.0"),
        ArtifactRef("battery.cell.peukert_capacity_derating.closed_form", "0.1.0"),
    ),
    solvers=(
        ArtifactRef("engcore.battery.cell_closed_form", "0.1.0"),
    ),
    calibration_protocols=(
        ArtifactRef("battery.calibration.ocv_chord", "1"),
        ArtifactRef("battery.calibration.ocv_curve", "1"),
    ),
    validation_protocols=(
        ArtifactRef("battery.validation.ocv_empirical_adequacy", "1"),
    ),
    uq_producers=(),
    measurement_adapters=(),
    transformations=(),
    benchmarks=(),
)


class BatteryDomainPack:
    """Atomic provider for the current authoritative battery artifacts."""

    @property
    def manifest(self) -> DomainPackManifest:
        return BATTERY_PACK_MANIFEST

    def models(self):
        return tuple(models.BATTERY_MODELS)

    def realizations(self):
        return tuple(models.BATTERY_REALIZATIONS)

    def solver_factories(self):
        return (BatteryCellSolver,)

    def calibration_protocols(self):
        return (
            ProvidedArtifact(
                ArtifactRef("battery.calibration.ocv_chord", "1"),
                calibration.build_ocv_chord_parameter_set,
            ),
            ProvidedArtifact(
                ArtifactRef("battery.calibration.ocv_curve", "1"),
                calibration.build_curve_parameter_set,
            ),
        )

    def validation_protocols(self):
        return (
            ProvidedArtifact(
                ArtifactRef("battery.validation.ocv_empirical_adequacy", "1"),
                empirical.assess_ocv_empirical_adequacy,
            ),
        )

    def uq_producers(self):
        return ()

    def measurement_adapters(self):
        return ()

    def transformations(self):
        return ()

    def benchmarks(self):
        return ()


def domain_pack() -> BatteryDomainPack:
    """Zero-argument factory suitable for the forge.domainpacks entry-point contract."""
    return BatteryDomainPack()


__all__ = [
    "BATTERY_PACK_MANIFEST",
    "BatteryDomainPack",
    "PACK_VERSION",
    "domain_pack",
]
