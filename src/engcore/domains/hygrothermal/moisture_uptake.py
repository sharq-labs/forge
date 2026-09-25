"""Reference moisture-uptake probe: an architectural probe, not a calibrated model.

    m(t+dt) = m(t) + k_uptake * TOW

TOW is the surface-wetness dose (seconds wet).  Real uptake saturates and
depends on the material's sorption isotherm; the linear window-additive form
is the declared (UNKNOWN) model discrepancy.  The ``moisture_content`` state
(mass fraction) belongs to the insulation participant and is range-checked by
the domain schema below.
"""

from __future__ import annotations

from typing import Mapping

from ...materials import ApplicabilityRange, MaterialStateSchema
from ...scenarios.contracts import NamedQuantity
from ...scenarios.lifecycle import DegradationModel, DegradationModelIdentity, InputRequirement, InputSource
from ...scientific.multiphysics.state import InitialStateDefinition
from ...scientific.results.uncertainty import Uncertainty
from ...scientific.units.quantity import Quantity

INSULATION_STATE_SCHEMA = MaterialStateSchema("hygrothermal.insulation_state", (
    ApplicabilityRange("moisture_content", Quantity(0, "dimensionless"), Quantity(1, "dimensionless")),
    ApplicabilityRange("temperature", Quantity(0, "K"), None, lower_inclusive=False,
                       unbounded_reason="absolute temperature has no domain upper limit here"),
))


class LinearWetnessMoistureUptake(DegradationModel):
    def __init__(self, *, k_uptake: Quantity, max_wet_time: Quantity) -> None:
        self.identity = DegradationModelIdentity(
            "hygrothermal.linear_wetness_uptake", "0.1",
            (NamedQuantity("k_uptake", k_uptake.to("1/s"), Uncertainty.unknown("reference probe parameter; not calibrated")),),
            Uncertainty.unknown("linear uptake probe; saturation and sorption isotherm not modelled"),
            applicability=(ApplicabilityRange("wet_time", Quantity(0, "s"), max_wet_time),),
            state_ranges=tuple(r for r in INSULATION_STATE_SCHEMA.ranges if r.variable_id == "moisture_content"),
        )
        self.state_variables = (InitialStateDefinition("moisture_content", "dimensionless"),)
        self.requirements = (InputRequirement("wet_time", InputSource.EXPOSURE_DOSE, "surface_wetness"),)

    def advance(self, inputs: Mapping[str, Quantity], state: Mapping[str, Quantity], duration: Quantity) -> Mapping[str, Quantity]:
        k = self.identity.parameter("k_uptake").magnitude
        m = state["moisture_content"].magnitude_in("dimensionless") + k * inputs["wet_time"].to("s").magnitude
        return {"moisture_content": Quantity(m, "dimensionless")}
