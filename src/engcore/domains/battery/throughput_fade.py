"""Reference throughput-driven capacity-fade probe: an architectural probe, not a calibrated model.

    fade(t+) = fade(t) + k_q * Q_throughput[A h] * exp(-Ea/R * (1/T_mean - 1/T_ref))

Inputs are physics aggregates of a battery provider's resolved operating
periods: charge throughput (time integral of |current|; requires INTEGRAL) and
the time-weighted mean cell temperature (requires MEAN).  Using a MEAN
temperature inside an Arrhenius factor is this model's DECLARED form (the
Jensen gap is part of its UNKNOWN model discrepancy) -- the model accepts
exactly those two aggregate forms and nothing else.
"""

from __future__ import annotations

import math
from typing import Mapping

from ...materials import ApplicabilityRange
from ...scenarios.contracts import NamedQuantity
from ...scenarios.lifecycle import (
    AggregateRequirement, DegradationModel, DegradationModelIdentity, HistoryFeature, InputRequirement, InputSource,
)
from ...scientific.multiphysics.state import InitialStateDefinition
from ...scientific.results.uncertainty import Uncertainty
from ...scientific.units.quantity import Quantity

GAS_CONSTANT = 8.314462618


class ThroughputArrheniusFade(DegradationModel):
    def __init__(self, *, k_per_ampere_hour: Quantity, activation_energy: Quantity, reference_temperature: Quantity) -> None:
        self.identity = DegradationModelIdentity(
            "battery.throughput_arrhenius_fade", "0.1",
            (NamedQuantity("k_q", k_per_ampere_hour.to("1/(A*h)"), Uncertainty.unknown("reference probe parameter; not calibrated")),
             NamedQuantity("activation_energy", activation_energy.to("J/mol"), Uncertainty.unknown("illustrative")),
             NamedQuantity("reference_temperature", reference_temperature.to("K"), Uncertainty.unknown("declared"))),
            Uncertainty.unknown("linear throughput fade with a mean-temperature Arrhenius factor; not calibrated"),
            applicability=(ApplicabilityRange("charge_throughput", Quantity(0, "A*s"), None,
                                              unbounded_reason="a window total; its size follows the window length"),
                           ApplicabilityRange("mean_cell_temperature", Quantity(263.15, "K"), Quantity(333.15, "K"))),
            state_ranges=(ApplicabilityRange("capacity_fade", Quantity(0, "dimensionless"), Quantity(0.5, "dimensionless"),
                                             upper_inclusive=False),),
        )
        self.state_variables = (InitialStateDefinition("capacity_fade", "dimensionless"),)
        self.requirements = (InputRequirement("charge_throughput", InputSource.PHYSICS_AGGREGATE, "abs_current"),
                             InputRequirement("mean_cell_temperature", InputSource.PHYSICS_AGGREGATE, "cell_temperature"))
        self.aggregate_requirements = (
            AggregateRequirement("charge_throughput", ("integral_dose",), (HistoryFeature.INTEGRAL,)),
            AggregateRequirement("mean_cell_temperature", ("time_weighted_mean",), (HistoryFeature.MEAN,)),
        )

    def advance(self, inputs: Mapping[str, Quantity], state: Mapping[str, Quantity], duration: Quantity) -> Mapping[str, Quantity]:
        k = self.identity.parameter("k_q").magnitude
        ea = self.identity.parameter("activation_energy").magnitude
        tref = self.identity.parameter("reference_temperature").magnitude
        q_ah = inputs["charge_throughput"].to("A*h").magnitude
        t = inputs["mean_cell_temperature"].to("K").magnitude
        fade = state["capacity_fade"].magnitude_in("dimensionless") + k * q_ah * math.exp(-ea / GAS_CONSTANT * (1.0 / t - 1.0 / tref))
        return {"capacity_fade": Quantity(fade, "dimensionless")}
