"""NASA battery aging adapter tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engcore.claims.adapters.nasa_battery_aging import (
    CurrentSignConvention,
    NasaDischargeSample,
    derive_soc_trace,
    nasa_terminal_voltage_observation,
)
from engcore.claims.measurement_dataset import DatasetSplit, MeasurementDatasetManifest
from engcore.mcp.capabilities import production_registry
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.units.quantity import Quantity


MANIFEST = (
    Path(__file__).resolve().parents[2]
    / "benchmarks"
    / "measurements"
    / "nasa_battery_aging"
    / "manifest.json"
)


def _manifest() -> MeasurementDatasetManifest:
    return MeasurementDatasetManifest.from_dict(json.loads(MANIFEST.read_text(encoding="utf-8")))


def _sample(index: int, time_s: float, current_a: float = 2.0) -> NasaDischargeSample:
    return NasaDischargeSample(
        cell_id="B0005",
        cycle_index=12,
        sample_index=index,
        ambient_temperature_c=24.0,
        voltage_measured_v=3.8 - 0.01 * index,
        current_measured_a=current_a,
        temperature_measured_c=25.0 + 0.1 * index,
        time_s=time_s,
        capacity_ah=1.85,
    )


def test_manifest_is_single_cell_and_sensor_uncertainty_is_not_invented() -> None:
    manifest = _manifest()
    assert manifest.independence_unit == "cell_id"
    assert manifest.measurement_uncertainty_declared is False
    assert manifest.value_columns["terminal_voltage"] == ("data.Voltage_measured", "volt")
    assert "State of charge is not a direct measurement" in manifest.notes


def test_direct_voltage_observation_remains_nonadmissible_without_calibration_uq() -> None:
    declaration = production_registry().get("system.battery")
    observation = nasa_terminal_voltage_observation(
        _manifest(),
        _sample(0, 0.0),
        declaration,
        split=DatasetSplit.CALIBRATION,
        current_convention=CurrentSignConvention.POSITIVE_DISCHARGE,
    )

    assert observation.value.magnitude_in("volt") == pytest.approx(3.8)
    assert observation.conditions["load.current"].magnitude_in("ampere") == pytest.approx(2.0)
    assert observation.conditions["load.cell_temperature"].magnitude_in("degC") == pytest.approx(25.0)
    assert not observation.uncertainty.is_quantified
    assert observation.ready_for_measurement_evidence is False
    assert observation.missing_context


def test_current_sign_convention_is_declared_not_hidden_by_abs() -> None:
    negative = _sample(0, 0.0, current_a=-2.0)
    declaration = production_registry().get("system.battery")

    with pytest.raises(InvalidScientificProblem, match="contradicts the declared current sign convention"):
        nasa_terminal_voltage_observation(
            _manifest(),
            negative,
            declaration,
            split=DatasetSplit.CALIBRATION,
            current_convention=CurrentSignConvention.POSITIVE_DISCHARGE,
        )

    observation = nasa_terminal_voltage_observation(
        _manifest(),
        negative,
        declaration,
        split=DatasetSplit.CALIBRATION,
        current_convention=CurrentSignConvention.NEGATIVE_DISCHARGE,
    )
    assert observation.conditions["load.current"].magnitude_in("ampere") == pytest.approx(2.0)


def test_soc_trace_is_explicitly_derived_not_measurement_evidence() -> None:
    trace = derive_soc_trace(
        (_sample(0, 0.0), _sample(1, 10.0), _sample(2, 20.0)),
        initial_state_of_charge=Quantity(1.0, "dimensionless"),
        reference_capacity=Quantity(2.0, "ampere_hour"),
        current_convention=CurrentSignConvention.POSITIVE_DISCHARGE,
    )

    assert trace[0].state_of_charge.magnitude_in("dimensionless") == pytest.approx(1.0)
    assert trace[-1].state_of_charge.magnitude_in("dimensionless") == pytest.approx(
        1.0 - 2.0 * 20.0 / 3600.0 / 2.0
    )
    assert trace[-1].to_dict()["can_be_measurement_evidence"] is False
    assert "assumed initial SOC" in trace[-1].to_dict()["notice"]


def test_soc_derivation_refuses_nonmonotonic_time() -> None:
    with pytest.raises(InvalidScientificProblem, match="strictly increasing"):
        derive_soc_trace(
            (_sample(0, 0.0), _sample(1, 0.0)),
            initial_state_of_charge=Quantity(1.0, "dimensionless"),
            reference_capacity=Quantity(2.0, "ampere_hour"),
            current_convention=CurrentSignConvention.POSITIVE_DISCHARGE,
        )


def test_soc_derivation_refuses_mixed_cells_or_cycles() -> None:
    other = NasaDischargeSample(
        cell_id="B0006",
        cycle_index=12,
        sample_index=1,
        ambient_temperature_c=24.0,
        voltage_measured_v=3.79,
        current_measured_a=2.0,
        temperature_measured_c=25.1,
        time_s=10.0,
        capacity_ah=1.85,
    )
    with pytest.raises(InvalidScientificProblem, match="one cell and one discharge cycle"):
        derive_soc_trace(
            (_sample(0, 0.0), other),
            initial_state_of_charge=Quantity(1.0, "dimensionless"),
            reference_capacity=Quantity(2.0, "ampere_hour"),
            current_convention=CurrentSignConvention.POSITIVE_DISCHARGE,
        )
