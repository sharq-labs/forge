"""Reference heater-resistance drift probe: an architectural probe, not a calibrated model.

    t_eq   = sum_i dt_i * exp(-Ea/R * (1/T_i - 1/T_ref))        (domain aggregate)
    d(t+)  = d(t) + k_drift * t_eq
    R_0,eff = R_0 * (1 + d)

``t_eq`` is an Arrhenius-equivalent time at ``T_ref`` computed from the
heater temperature DWELL history of the fast physics.  It needs the
temperature distribution in time: a time-weighted MEAN temperature would
give exp(mean) instead of mean(exp) (Jensen), so the model refuses any
aggregate that does not preserve DWELL.  Parameters are illustrative; the
linear drift law and the single activation energy are the declared
(UNKNOWN) model discrepancy.
"""

from __future__ import annotations

import math
from fractions import Fraction
from typing import Mapping, Sequence

from ...materials import ApplicabilityRange
from ...multiscale.aggregation import DomainAggregator
from ...scenarios.contracts import NamedQuantity
from ...scenarios.lifecycle import (
    AggregateRequirement, DegradationModel, DegradationModelIdentity, HistoryFeature, InputRequirement, InputSource,
)
from ...scientific.multiphysics.state import InitialStateDefinition
from ...scientific.results.uncertainty import Uncertainty
from ...scientific.units.quantity import Quantity

GAS_CONSTANT = 8.314462618  # J/(mol K), CODATA exact definition value
AGGREGATOR_ID = "electrical.arrhenius_equivalent_time"


class ArrheniusEquivalentTime(DomainAggregator):
    required_source_features = frozenset({HistoryFeature.DWELL, HistoryFeature.DISTRIBUTION})
    preserves = frozenset({HistoryFeature.DWELL, HistoryFeature.INTEGRAL})
    extensive = True
    output_unit = "second"

    def __init__(self, *, activation_energy: Quantity, reference_temperature: Quantity, valid_temperature: tuple[Quantity, Quantity]) -> None:
        self.aggregator_id, self.version = AGGREGATOR_ID, "0.2"
        low, high = (q.to("K") for q in valid_temperature)
        if not 0 < low.magnitude < high.magnitude:
            raise ValueError("declared Arrhenius temperature range must be 0 < low < high")
        self.parameters = (
            NamedQuantity("activation_energy", activation_energy.to("J/mol"), Uncertainty.unknown("illustrative activation energy")),
            NamedQuantity("reference_temperature", reference_temperature.to("K"), Uncertainty.unknown("declared reference temperature")),
            NamedQuantity("valid_temperature_low", low, Uncertainty.unknown("declared applicability of the Arrhenius parameters")),
            NamedQuantity("valid_temperature_high", high, Uncertainty.unknown("declared applicability of the Arrhenius parameters")),
        )
        self._ea = activation_energy.to("J/mol").magnitude
        self._tref = reference_temperature.to("K").magnitude
        self._range = (low.magnitude, high.magnitude)

    def compute(self, samples: Sequence[tuple[Fraction, Quantity]]) -> Quantity:
        total = 0.0
        for dt, temperature in samples:
            t = temperature.to("K").magnitude
            if not self._range[0] <= t <= self._range[1]:
                # applicability is checked on the variable the parameters hold
                # for (temperature), sample by sample -- not on the total
                raise ValueError(f"heater temperature {t:.6g} K is outside the declared Arrhenius range "
                                 f"[{self._range[0]:g}, {self._range[1]:g}] K")
            total += float(dt) * math.exp(-self._ea / GAS_CONSTANT * (1.0 / t - 1.0 / self._tref))
        return Quantity(total, "second")


class ArrheniusResistanceDrift(DegradationModel):
    def __init__(self, *, k_drift: Quantity, max_equivalent_time: Quantity | None = None) -> None:
        self.identity = DegradationModelIdentity(
            "electrical.arrhenius_resistance_drift", "0.1",
            (NamedQuantity("k_drift", k_drift.to("1/s"), Uncertainty.unknown("reference probe parameter; not calibrated")),),
            Uncertainty.unknown("linear drift in Arrhenius-equivalent time; single activation energy; not calibrated"),
            applicability=(ApplicabilityRange(
                "equivalent_time", Quantity(0, "s"), max_equivalent_time if max_equivalent_time is not None else None,
                unbounded_reason="" if max_equivalent_time is not None else
                "a sum over the macro window that grows with its length; the Arrhenius parameters' validity is "
                "checked per sample temperature by the aggregator"),),
            state_ranges=(ApplicabilityRange("resistance_drift", Quantity(0, "dimensionless"), Quantity(1, "dimensionless")),),
        )
        self.state_variables = (InitialStateDefinition("resistance_drift", "dimensionless"),)
        self.requirements = (InputRequirement("equivalent_time", InputSource.PHYSICS_AGGREGATE, "heater_temperature"),)
        self.aggregate_requirements = (
            AggregateRequirement("equivalent_time", (f"domain_defined:{AGGREGATOR_ID}",), (HistoryFeature.DWELL,)),
        )

    def advance(self, inputs: Mapping[str, Quantity], state: Mapping[str, Quantity], duration: Quantity) -> Mapping[str, Quantity]:
        k = self.identity.parameter("k_drift").magnitude
        d = state["resistance_drift"].magnitude_in("dimensionless") + k * inputs["equivalent_time"].to("s").magnitude
        return {"resistance_drift": Quantity(d, "dimensionless")}


class MeanTemperatureDrift(ArrheniusResistanceDrift):
    """A deliberately WRONG consumer used by refusal tests: it declares that it
    would accept a time-weighted MEAN temperature, yet the drift law it shares
    needs DWELL.  The requirement is still declared honestly (DWELL), so a
    mean-only aggregate is refused rather than silently used."""

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.requirements = (InputRequirement("equivalent_time", InputSource.PHYSICS_AGGREGATE, "heater_temperature"),)
        self.aggregate_requirements = (
            AggregateRequirement("equivalent_time", ("time_weighted_mean", f"domain_defined:{AGGREGATOR_ID}"), (HistoryFeature.DWELL,)),
        )
