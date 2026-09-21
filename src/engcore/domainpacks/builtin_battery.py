"""The Battery Domain Pack. One production authority, and no second copy.

THERE WERE TWO. ``engcore.domainpacks.builtin_battery`` declared pack
``battery.cell@1`` and was the one production registered and enabled; it
exposed models, realizations and a solver factory and nothing else.
``engcore.domains.battery.pack`` declared pack ``battery@1.0.0``, exposed the
same models and solver *plus* the OCV calibration and empirical-adequacy
validation protocols, and was reachable only from a test. Two manifests over
the same artifacts, free to drift, and the richer one was not the one
production ran. This module is the survivor and the other is gone.

The artifacts below are the ones the battery domain can support today. What is
deliberately NOT here is the one-RC Thevenin kernel in
:mod:`engcore.domains.battery.thevenin`: it is a scientific kernel with no
calibration protocol and no empirical adequacy evidence, and consolidating
pack authority is not an occasion to promote it. It joins a pack when it passes
its own calibration/validation gate, not before.

Dependency direction is unchanged and is why this module lives here rather
than under ``domains``::

    claims -> domain pack -> battery domain -> scientific core
"""

from __future__ import annotations

from ..domains.battery import calibration, empirical, models
from ..domains.battery.solver import (
    BatteryCellSolver,
    SOLVER_ID,
    SOLVER_VERSION,
)
from .manifest import ArtifactRef, DOMAIN_PACK_API, DomainPackManifest
from .provider import ProvidedArtifact

PACK_ID = "battery.cell"
PACK_VERSION = "1"

OCV_CHORD_CALIBRATION = ArtifactRef("battery.calibration.ocv_chord", "1")
OCV_CURVE_CALIBRATION = ArtifactRef("battery.calibration.ocv_curve", "1")
OCV_EMPIRICAL_VALIDATION = ArtifactRef(
    "battery.validation.ocv_empirical_adequacy", "1"
)

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
    calibration_protocols=(OCV_CHORD_CALIBRATION, OCV_CURVE_CALIBRATION),
    validation_protocols=(OCV_EMPIRICAL_VALIDATION,),
)


class BatteryCellDomainPack:
    """Atomic provider for the current authoritative battery artifacts."""

    manifest = MANIFEST

    def models(self):
        return tuple(models.BATTERY_MODELS)

    def realizations(self):
        return tuple(models.BATTERY_REALIZATIONS)

    def solver_factories(self):
        return (BatteryCellSolver,)

    def calibration_protocols(self):
        return (
            ProvidedArtifact(
                OCV_CHORD_CALIBRATION, calibration.build_ocv_chord_parameter_set
            ),
            ProvidedArtifact(
                OCV_CURVE_CALIBRATION, calibration.build_curve_parameter_set
            ),
        )

    def validation_protocols(self):
        return (
            ProvidedArtifact(
                OCV_EMPIRICAL_VALIDATION, empirical.assess_ocv_empirical_adequacy
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


BUILTIN_BATTERY_CELL_PACK = BatteryCellDomainPack()


def domain_pack() -> BatteryCellDomainPack:
    """Zero-argument factory for the ``forge.domainpacks`` entry-point contract."""
    return BUILTIN_BATTERY_CELL_PACK


__all__ = [
    "BUILTIN_BATTERY_CELL_PACK",
    "BatteryCellDomainPack",
    "MANIFEST",
    "OCV_CHORD_CALIBRATION",
    "OCV_CURVE_CALIBRATION",
    "OCV_EMPIRICAL_VALIDATION",
    "PACK_ID",
    "PACK_VERSION",
    "domain_pack",
]
