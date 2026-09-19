"""Real measurement dataset admission stays fail-closed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engcore.claims import (
    DatasetSplit,
    MeasurementDatasetError,
    MeasurementDatasetManifest,
    observation_from_row,
    required_physical_context,
)
from engcore.mcp.capabilities import production_registry
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind, UncertaintySource
from engcore.scientific.units.quantity import Quantity


MANIFEST_PATH = (
    Path(__file__).resolve().parents[2]
    / "benchmarks"
    / "measurements"
    / "nasa_battery_alt"
    / "manifest.json"
)


def _manifest() -> MeasurementDatasetManifest:
    return MeasurementDatasetManifest.from_dict(json.loads(MANIFEST_PATH.read_text(encoding="utf-8")))


def _shape_fixture_row() -> dict[str, str]:
    # Shape-only fixture matching the published CSV columns. These numbers are
    # not asserted to be rows from the NASA archive.
    return {
        "start time": "01:01:2023 00:00:00",
        "relative time": "10",
        "mode": "-1",
        "voltage charger": "7.4",
        "temperature battery": "25.0",
        "voltage load": "7.2",
        "current load": "9.3",
        "temperature mosfet": "30.0",
        "temperature resistor": "31.0",
        "mission type": "1",
    }


def test_nasa_manifest_is_round_trip_identified_and_not_pretrusted() -> None:
    manifest = _manifest()
    assert manifest.dataset_id == "nasa.randomized_recommissioned_battery_alt"
    assert manifest.independence_unit == "battery_pack"
    assert manifest.measurement_uncertainty_declared is False
    assert manifest.value_columns["terminal_voltage"] == ("voltage load", "volt")
    assert MeasurementDatasetManifest.from_dict(manifest.to_dict()).digest == manifest.digest


def test_raw_nasa_row_cannot_masquerade_as_complete_battery_evidence() -> None:
    manifest = _manifest()
    battery = production_registry().get("system.battery")
    required = required_physical_context(battery)
    observation = observation_from_row(
        manifest,
        _shape_fixture_row(),
        observation_id="shape:0.1:row0",
        independence_group="battery-pack:0.1",
        split=DatasetSplit.CALIBRATION,
        quantity="terminal_voltage",
        required_context=required,
        provenance_ref="nasa-ntrs:20230014884#shape-fixture",
    )

    assert observation.conditions["load.current"].to("ampere").magnitude == pytest.approx(9.3)
    assert observation.conditions["load.cell_temperature"].to("degC").magnitude == pytest.approx(25.0)
    assert observation.missing_context
    assert not observation.uncertainty.is_quantified
    assert observation.ready_for_measurement_evidence is False
    with pytest.raises(MeasurementDatasetError, match="missing exact operating context"):
        observation.to_measurement_record()


def test_complete_context_and_calibration_are_required_before_promotion() -> None:
    manifest = _manifest()
    uncertainty = Uncertainty(
        kind=UncertaintyKind.INTERVAL,
        lower=Quantity(7.19, "volt"),
        upper=Quantity(7.21, "volt"),
        method="independent calibration interval",
        source_kind=UncertaintySource.MEASUREMENT,
    )
    observation = observation_from_row(
        manifest,
        _shape_fixture_row(),
        observation_id="fixture:complete",
        independence_group="fixture-pack:a",
        split=DatasetSplit.VALIDATION,
        quantity="terminal_voltage",
        required_context=("load.current", "load.cell_temperature"),
        uncertainty=uncertainty,
        calibration_ref="calibration:fixture-voltmeter",
        provenance_ref="fixture:measurement-run",
    )

    assert observation.missing_context == ()
    assert observation.ready_for_measurement_evidence
    record = observation.to_measurement_record()
    assert record.quantity == "terminal_voltage"
    assert record.uncertainty.source_kind is UncertaintySource.MEASUREMENT
    assert set(record.independence_roots) == {"fixture-pack:a", "fixture:measurement-run"}


def test_dataset_row_shape_is_strict() -> None:
    row = _shape_fixture_row()
    del row["voltage load"]
    with pytest.raises(MeasurementDatasetError, match="missing dataset columns"):
        observation_from_row(
            _manifest(),
            row,
            observation_id="bad",
            independence_group="pack:x",
            split=DatasetSplit.CALIBRATION,
            quantity="terminal_voltage",
            required_context=(),
            provenance_ref="fixture",
        )
