"""Adapter for NASA Ames Li-ion Battery Aging discharge samples.

The NASA files are measurement data, not Forge claim records. This adapter
keeps that boundary explicit:

* terminal voltage, current and temperature are direct recorded channels;
* current sign convention must be declared by the caller;
* state of charge is never read from voltage or cycle index;
* an optional SOC trace may be *derived* by coulomb counting, but that trace is
  labelled derived and cannot masquerade as measurement evidence;
* measurement uncertainty remains UNKNOWN unless a calibration record is
  supplied separately.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Iterable, Mapping

from ...scientific.errors import InvalidScientificProblem
from ...scientific.results.uncertainty import Uncertainty
from ...scientific.units.quantity import Quantity
from ..capabilities import CapabilityDeclaration
from ..measurement_dataset import (
    DatasetObservation,
    DatasetSplit,
    MeasurementDatasetManifest,
    observation_from_row,
    required_physical_context,
)


class CurrentSignConvention(str, Enum):
    POSITIVE_DISCHARGE = "positive_discharge"
    NEGATIVE_DISCHARGE = "negative_discharge"


@dataclass(frozen=True)
class NasaDischargeSample:
    cell_id: str
    cycle_index: int
    sample_index: int
    ambient_temperature_c: float
    voltage_measured_v: float
    current_measured_a: float
    temperature_measured_c: float
    time_s: float
    capacity_ah: float

    def __post_init__(self) -> None:
        if not str(self.cell_id).strip():
            raise InvalidScientificProblem("NASA sample needs a non-empty cell_id")
        if self.cycle_index < 0 or self.sample_index < 0:
            raise InvalidScientificProblem("cycle_index and sample_index must be non-negative")
        for label in (
            "ambient_temperature_c",
            "voltage_measured_v",
            "current_measured_a",
            "temperature_measured_c",
            "time_s",
            "capacity_ah",
        ):
            value = float(getattr(self, label))
            if not math.isfinite(value):
                raise InvalidScientificProblem(f"{label} must be finite")
            object.__setattr__(self, label, value)
        if self.time_s < 0.0:
            raise InvalidScientificProblem("NASA discharge sample time must be non-negative")
        if self.capacity_ah <= 0.0:
            raise InvalidScientificProblem("NASA discharge capacity must be strictly positive")


@dataclass(frozen=True)
class DerivedSocPoint:
    """A model-derived state coordinate, explicitly not a measurement."""

    cell_id: str
    cycle_index: int
    sample_index: int
    time_s: float
    state_of_charge: Quantity
    source_ref: str

    def to_dict(self) -> dict:
        return {
            "cell_id": self.cell_id,
            "cycle_index": self.cycle_index,
            "sample_index": self.sample_index,
            "time_s": self.time_s,
            "state_of_charge": self.state_of_charge.to_dict(),
            "source_ref": self.source_ref,
            "derivation": "trapezoidal_coulomb_counting_from_measured_current",
            "can_be_measurement_evidence": False,
            "notice": (
                "state of charge is derived from an assumed initial SOC and reference capacity; "
                "it is not a directly measured NASA channel"
            ),
        }


def _discharge_current(sample: NasaDischargeSample, convention: CurrentSignConvention) -> float:
    convention = CurrentSignConvention(convention)
    raw = sample.current_measured_a
    current = raw if convention is CurrentSignConvention.POSITIVE_DISCHARGE else -raw
    if current < 0.0:
        raise InvalidScientificProblem(
            f"sample {sample.sample_index} contradicts the declared current sign convention: "
            f"raw current {raw:g} A maps to {current:g} A discharge"
        )
    return current


def nasa_terminal_voltage_observation(
    manifest: MeasurementDatasetManifest,
    sample: NasaDischargeSample,
    declaration: CapabilityDeclaration,
    *,
    split: DatasetSplit,
    current_convention: CurrentSignConvention,
    context_overrides: Mapping[str, Quantity] | None = None,
    uncertainty: Uncertainty | None = None,
    calibration_ref: str | None = None,
) -> DatasetObservation:
    """Map one NASA discharge sample to a fail-closed terminal-voltage observation."""

    current = _discharge_current(sample, current_convention)
    row = {
        "cycle.type": "discharge",
        "cycle.ambient_temperature": sample.ambient_temperature_c,
        "data.Voltage_measured": sample.voltage_measured_v,
        "data.Current_measured": sample.current_measured_a,
        "data.Temperature_measured": sample.temperature_measured_c,
        "data.Time": sample.time_s,
        "data.Capacity": sample.capacity_ah,
    }

    overrides = dict(context_overrides or {})
    # Sign-normalized current is a transformation with an explicit convention,
    # so it overrides the raw channel mapping rather than silently taking abs().
    overrides["load.discharge_current"] = Quantity(current, "ampere")
    overrides["load.cell_temperature"] = Quantity(sample.temperature_measured_c, "degC")
    overrides["thermal.ambient_temperature"] = Quantity(sample.ambient_temperature_c, "degC")

    ref = (
        f"nasa.li_ion_battery_aging:{sample.cell_id}:"
        f"cycle={sample.cycle_index}:sample={sample.sample_index}"
    )
    return observation_from_row(
        manifest,
        row,
        observation_id=ref,
        independence_group=f"cell:{sample.cell_id}",
        split=split,
        quantity="terminal_voltage",
        required_context=required_physical_context(declaration),
        context_overrides=overrides,
        uncertainty=uncertainty,
        calibration_ref=calibration_ref,
        provenance_ref=ref,
    )


def derive_soc_trace(
    samples: Iterable[NasaDischargeSample],
    *,
    initial_state_of_charge: Quantity,
    reference_capacity: Quantity,
    current_convention: CurrentSignConvention,
) -> tuple[DerivedSocPoint, ...]:
    """Integrate measured current with the trapezoidal rule.

    This is intentionally returned as a derived analysis artifact instead of a
    MeasurementRecord. The initial SOC and capacity are assumptions/parameters,
    and changing either changes the trace.
    """

    initial_state_of_charge.require_compatible(
        Quantity(1.0, "dimensionless"), context="initial_state_of_charge"
    )
    z0 = initial_state_of_charge.magnitude_in("dimensionless")
    if not 0.0 <= z0 <= 1.0:
        raise InvalidScientificProblem("initial_state_of_charge must lie in [0, 1]")

    reference_capacity.require_compatible(
        Quantity(1.0, "ampere_hour"), context="reference_capacity"
    )
    capacity_ah = reference_capacity.magnitude_in("ampere_hour")
    if capacity_ah <= 0.0 or not math.isfinite(capacity_ah):
        raise InvalidScientificProblem("reference_capacity must be strictly positive and finite")

    ordered = tuple(samples)
    if not ordered:
        return ()
    first = ordered[0]
    identity = (first.cell_id, first.cycle_index)
    if any((s.cell_id, s.cycle_index) != identity for s in ordered):
        raise InvalidScientificProblem("one SOC trace may contain only one cell and one discharge cycle")

    previous_time = ordered[0].time_s
    previous_current = _discharge_current(ordered[0], current_convention)
    cumulative_ah = 0.0
    out: list[DerivedSocPoint] = []

    for index, sample in enumerate(ordered):
        current = _discharge_current(sample, current_convention)
        if index:
            dt = sample.time_s - previous_time
            if dt <= 0.0:
                raise InvalidScientificProblem(
                    "NASA discharge sample times must be strictly increasing for SOC integration"
                )
            cumulative_ah += 0.5 * (previous_current + current) * dt / 3600.0
        z = z0 - cumulative_ah / capacity_ah
        if not 0.0 <= z <= 1.0:
            raise InvalidScientificProblem(
                f"derived SOC leaves [0, 1] at sample {sample.sample_index}: {z:g}; "
                "the assumed initial SOC/reference capacity is inconsistent with the trace"
            )
        ref = (
            f"nasa.li_ion_battery_aging:{sample.cell_id}:"
            f"cycle={sample.cycle_index}:sample={sample.sample_index}"
        )
        out.append(
            DerivedSocPoint(
                sample.cell_id,
                sample.cycle_index,
                sample.sample_index,
                sample.time_s,
                Quantity(z, "dimensionless"),
                ref,
            )
        )
        previous_time = sample.time_s
        previous_current = current

    return tuple(out)


__all__ = [
    "CurrentSignConvention",
    "DerivedSocPoint",
    "NasaDischargeSample",
    "derive_soc_trace",
    "nasa_terminal_voltage_observation",
]
