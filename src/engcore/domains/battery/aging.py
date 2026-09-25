"""Reference battery aging probe for the lifecycle engine (BIG 4).

An architectural probe, not a calibrated or validated aging model: capacity
fades linearly with (a) calendar time, Arrhenius-scaled by the window-mean
ambient temperature, and (b) complete equivalent full cycles::

    Q(t+dt) = Q(t) - Q_nom * (k_cal * exp(-Ea/R * (1/T_mean - 1/T_ref)) * dt + k_cyc * N)

Known limits, stated rather than hidden: Arrhenius of a window mean is not the
mean of the Arrhenius factor (Jensen gap); real calendar fade is usually
sub-linear in time and path dependent; cycle fade depends on depth and rate.
Hence the declared model discrepancy is UNKNOWN and parameters carry UNKNOWN
uncertainty.  The state variable (``capacity``) is owned by the battery
participant; nothing battery-specific enters the generic lifecycle layer.
"""

from __future__ import annotations

import math
from typing import Mapping

from ...scenarios.contracts import NamedQuantity
from ...scenarios.lifecycle import (
    ApplicabilityBound, DegradationModel, DegradationModelIdentity, InputRequirement, InputSource,
)
from ...scientific.multiphysics.state import InitialStateDefinition
from ...scientific.results.uncertainty import Uncertainty
from ...scientific.units.quantity import Quantity

GAS_CONSTANT = 8.314462618  # J/(mol*K), exact SI definition


class CalendarCycleCapacityFade(DegradationModel):
    def __init__(
        self,
        *,
        nominal_capacity: Quantity,
        k_calendar: Quantity,
        activation_energy: Quantity,
        reference_temperature: Quantity,
        k_cycle: Quantity,
        temperature_range: tuple[Quantity, Quantity] = (Quantity(273.15, "K"), Quantity(318.15, "K")),
    ) -> None:
        unstated = Uncertainty.unknown("reference probe parameter; not calibrated")
        self.identity = DegradationModelIdentity(
            "battery.calendar_cycle_linear_fade", "0.1",
            (
                NamedQuantity("nominal_capacity", nominal_capacity.to("A*h"), unstated),
                NamedQuantity("k_calendar", k_calendar.to("1/s"), unstated),
                NamedQuantity("activation_energy", activation_energy.to("J/mol"), unstated),
                NamedQuantity("reference_temperature", reference_temperature.to("K"), unstated),
                NamedQuantity("k_cycle", k_cycle.to("dimensionless"), unstated),
            ),
            Uncertainty.unknown("linear-fade probe; Jensen gap and path dependence not quantified"),
        )
        self.state_variables = (InitialStateDefinition("capacity", "A*h"),)
        self.requirements = (
            InputRequirement("mean_temperature", InputSource.EXPOSURE_MEAN, "ambient_temperature"),
            InputRequirement("full_cycles", InputSource.CYCLE_COUNT, "equivalent_full_cycle"),
        )
        self.applicability = (ApplicabilityBound("mean_temperature", *temperature_range),)

    def advance(self, inputs: Mapping[str, Quantity], state: Mapping[str, Quantity], duration: Quantity) -> Mapping[str, Quantity]:
        p = self.identity.parameter
        t_mean = inputs["mean_temperature"].to("K").magnitude
        arrhenius = math.exp(-p("activation_energy").magnitude / GAS_CONSTANT * (1.0 / t_mean - 1.0 / p("reference_temperature").magnitude))
        fraction = p("k_calendar").magnitude * arrhenius * duration.to("s").magnitude + p("k_cycle").magnitude * inputs["full_cycles"].magnitude
        capacity = state["capacity"].to("A*h").magnitude - p("nominal_capacity").magnitude * fraction
        return {"capacity": Quantity(capacity, "A*h")}
