"""Declared liquid phase envelopes for the CSTR domain (audit CAP-01).

The CSTR model claims a single liquid phase and checks it against the boiling
and freezing temperatures the declared fluid states for itself. This module is
where a named fluid's envelope is declared ONCE, with its basis, so a study
can attach it explicitly with :func:`declare_fluid`. Nothing here is applied
implicitly: a ``ReactorChemistry`` that is not handed an envelope declares no
phase boundary, and its liquid-phase conditions stay UNKNOWN.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ....scientific.units.quantity import Quantity
from .errors import ReactorConfigurationError
from .problem import TEMPERATURE_UNIT, ReactorChemistry

__all__ = [
    "FluidPhaseEnvelope",
    "SEBORG_TEXTBOOK_LIQUID",
    "declare_fluid",
]


@dataclass(frozen=True)
class FluidPhaseEnvelope:
    """Where one named liquid is liquid, at one stated pressure, and on what basis."""

    name: str
    pressure: Quantity
    boiling_temperature: Quantity
    freezing_temperature: Quantity
    basis: str

    def __post_init__(self) -> None:
        boil = self.boiling_temperature.magnitude_in(TEMPERATURE_UNIT)
        freeze = self.freezing_temperature.magnitude_in(TEMPERATURE_UNIT)
        if not 0.0 < freeze < boil:
            raise ReactorConfigurationError(
                f"fluid {self.name!r}: freezing temperature {freeze!r} K must be "
                f"positive and below the boiling temperature {boil!r} K"
            )
        self.pressure.magnitude_in("pascal")
        if not str(self.basis).strip():
            raise ReactorConfigurationError(
                f"fluid {self.name!r} declares a liquid range with no basis"
            )


#: The liquid of the Seborg, Edgar, Mellichamp & Doyle CSTR parameterization
#: that the frozen K-series studies use (rho = 1000 kg/m^3, c_p = 0.239 J/(g K)).
#:
#: WHAT THE TEXTBOOK STATES AND WHAT IT DOES NOT. The tabulated example names
#: no fluid and states NO operating pressure. Its density is water's, and the
#: reaction is carried in a dilute liquid solution, so the liquid is taken to
#: be an aqueous solution whose phase boundaries are water's. Its heat capacity
#: (0.239 J/(g K)) is NOT water's (4.18 J/(g K)); that is a property of the
#: textbook parameterization, recorded in experiments/kinetics_k1 as not checked
#: against the printed source, and it does not change where water boils.
#:
#: THE PRESSURE IS AN ASSUMPTION, STATED: atmospheric, 101.325 kPa, because
#: nothing in the source says the tank is pressurised. A study that means a
#: pressurised tank must declare its own envelope; this one does not stretch.
#:
#: VALUES. Boiling: 373.124 K, the saturation temperature of water at
#: 101.325 kPa from the IAPWS-95 formulation (W. Wagner and A. Pruss, J. Phys.
#: Chem. Ref. Data 31, 387 (2002)); dilute solutes raise it by well under 1 K,
#: which is not taken as margin. Freezing: 273.15 K, the ice point of water at
#: 101.325 kPa; dilute solutes lower it, which only widens the true range. These
#: are standard reference values quoted here, not extracted from a document in
#: this repository.
SEBORG_TEXTBOOK_LIQUID = FluidPhaseEnvelope(
    name="seborg_cstr_dilute_aqueous_liquid",
    pressure=Quantity(101325.0, "pascal"),
    boiling_temperature=Quantity(373.124, TEMPERATURE_UNIT),
    freezing_temperature=Quantity(273.15, TEMPERATURE_UNIT),
    basis=(
        "dilute aqueous liquid (textbook density 1000 kg/m^3; fluid unnamed in "
        "the source) at an ASSUMED 101.325 kPa (no operating pressure stated "
        "in the source); water saturation temperature at 101.325 kPa per "
        "IAPWS-95, ice point 273.15 K"
    ),
)


def declare_fluid(
    chemistry: ReactorChemistry, envelope: FluidPhaseEnvelope
) -> ReactorChemistry:
    """``chemistry`` with ``envelope``'s phase boundaries declared on it.

    Refuses a chemistry that already declares different boundaries: two
    statements of where one liquid boils are a contradiction, not a merge.
    """
    for label in ("boiling_temperature", "freezing_temperature"):
        existing = getattr(chemistry, label)
        stated = getattr(envelope, label)
        if existing is not None and existing.compare(stated) != 0.0:
            raise ReactorConfigurationError(
                f"chemistry already declares {label} = {existing}, and fluid "
                f"{envelope.name!r} states {stated}"
            )
    return replace(
        chemistry,
        boiling_temperature=envelope.boiling_temperature,
        freezing_temperature=envelope.freezing_temperature,
    )
