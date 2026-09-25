"""Reference corrosion thickness-loss probe for the lifecycle engine (BIG 4).

An architectural probe, not a calibrated corrosion model.  Thickness loss per
window is linear in two declared environmental doses, in the spirit of
dose-response functions that combine time of wetness and chloride
deposition::

    x(t+dt) = x(t) - (k_wet * TOW + k_cl * D_Cl)

where TOW is the surface-wetness dose (seconds wet) and D_Cl the chloride
deposition dose (mass per area).  Real dose-response functions are power laws
in exposure time and are not additive over windows; the linear form is chosen
so the probe is window-additive, and that choice is the declared (UNKNOWN)
model discrepancy.  Applicability is bounded by the window's chloride dose.
The ``wall_thickness`` state belongs to the wall participant.
"""

from __future__ import annotations

from typing import Mapping

from ...scenarios.contracts import NamedQuantity
from ...materials import ApplicabilityRange, MaterialStateSchema
from ...scenarios.lifecycle import (
    DegradationModel, DegradationModelIdentity, InputRequirement, InputSource,
)
from ...scientific.multiphysics.state import InitialStateDefinition
from ...scientific.results.uncertainty import Uncertainty
from ...scientific.units.quantity import Quantity


#: The wall domain's physical range for thickness: strictly positive.
WALL_STATE_SCHEMA = MaterialStateSchema("corrosion.wall_state", (
    ApplicabilityRange("wall_thickness", Quantity(0, "m"), None, lower_inclusive=False,
                       unbounded_reason="no physical upper limit on thickness is declared by the domain"),
))


class LinearDoseThicknessLoss(DegradationModel):
    def __init__(self, *, k_wet: Quantity, k_chloride: Quantity, max_chloride_dose: Quantity) -> None:
        unstated = Uncertainty.unknown("reference probe parameter; not calibrated")
        self.identity = DegradationModelIdentity(
            "corrosion.linear_dose_thickness_loss", "0.1",
            (
                NamedQuantity("k_wet", k_wet.to("m/s"), unstated),
                NamedQuantity("k_chloride", k_chloride.to("m / (kg/m^2)"), unstated),
            ),
            Uncertainty.unknown("window-additive linear probe of a power-law process; discrepancy not quantified"),
            applicability=(
                ApplicabilityRange("chloride_dose", Quantity(0, "kg/m^2"), max_chloride_dose),
                ApplicabilityRange("wet_time", Quantity(0, "s"), None,
                                   unbounded_reason="a wetness dose cannot exceed the window length by construction"),
            ),
            state_ranges=WALL_STATE_SCHEMA.ranges,
        )
        self.state_variables = (InitialStateDefinition("wall_thickness", "m"),)
        self.requirements = (
            InputRequirement("wet_time", InputSource.EXPOSURE_DOSE, "surface_wetness"),
            InputRequirement("chloride_dose", InputSource.EXPOSURE_DOSE, "chloride_deposition_rate"),
        )

    def advance(self, inputs: Mapping[str, Quantity], state: Mapping[str, Quantity], duration: Quantity) -> Mapping[str, Quantity]:
        p = self.identity.parameter
        loss = p("k_wet").magnitude * inputs["wet_time"].to("s").magnitude + p("k_chloride").magnitude * inputs["chloride_dose"].to("kg/m^2").magnitude
        return {"wall_thickness": Quantity(state["wall_thickness"].to("m").magnitude - loss, "m")}
