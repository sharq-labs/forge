"""Tests for deterministic NASA PCoE battery-aging ingestion."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest
from scipy.io import savemat

from tools.nasa_battery_aging import (
    NasaBatteryIngestionError,
    SourceReceipt,
    canonicalize_loaded_mat,
    ingest_mat_file,
    source_receipt,
)


def _loaded() -> dict:
    return {
        "B0005": {
            "cycle": [
                {
                    "type": "discharge",
                    "ambient_temperature": 24.0,
                    "time": [2008, 4, 2, 15, 25, 41.0],
                    "data": {
                        "Voltage_measured": [4.10, 4.00, 3.90],
                        "Current_measured": [2.0, 2.0, 2.0],
                        "Temperature_measured": [24.1, 24.2, 24.3],
                        "Time": [0.0, 1.0, 2.0],
                        "Capacity": 1.90,
                    },
                },
                {
                    "type": "impedance",
                    "ambient_temperature": 24.0,
                    "time": [2008, 4, 2, 16, 0, 0.0],
                    "data": {
                        "Sense_current": [1.0 + 0.0j, 1.0 + 0.0j],
                        "Battery_impedance": [0.10 + 0.01j, 0.20 + 0.02j],
                    },
                },
            ]
        }
    }


def _receipt() -> SourceReceipt:
    return SourceReceipt("B0005.mat", 123, "a" * 64)


def test_same_parsed_content_has_same_canonical_digest() -> None:
    first = canonicalize_loaded_mat(_loaded(), receipt=_receipt())
    second = canonicalize_loaded_mat(deepcopy(_loaded()), receipt=_receipt())

    assert first["canonical_sha256"] == second["canonical_sha256"]
    assert first["cycle_types"] == {"charge": 0, "discharge": 1, "impedance": 1}


def test_operational_channels_are_preserved_without_current_sign_normalization() -> None:
    record = canonicalize_loaded_mat(_loaded(), receipt=_receipt())
    cycle = record["cycles"][0]

    assert cycle["channels"]["Current_measured"] == [2.0, 2.0, 2.0]
    assert "preserved exactly as recorded" in cycle["current_sign_convention"]
    assert cycle["delivered_capacity_Ah"] == pytest.approx(1.90)


def test_importer_does_not_invent_soc_pulse_rest_or_sensor_uncertainty() -> None:
    record = canonicalize_loaded_mat(_loaded(), receipt=_receipt())

    assert record["scientific_limits"] == {
        "soc": "NOT_INFERRED",
        "pulse_rest_segments": "NOT_INFERRED",
        "sensor_uncertainty": "UNKNOWN",
        "one_rc_parameters": "NOT_IDENTIFIED",
    }
    assert all(
        cycle["measurement_uncertainty"] == "UNKNOWN"
        for cycle in record["cycles"]
    )


def test_complex_impedance_is_preserved_as_real_imaginary_pairs() -> None:
    record = canonicalize_loaded_mat(_loaded(), receipt=_receipt())
    impedance = record["cycles"][1]["channels"]["Battery_impedance"]

    assert impedance == [
        {"real": 0.10, "imag": 0.01},
        {"real": 0.20, "imag": 0.02},
    ]


def test_misaligned_operational_channels_are_refused() -> None:
    loaded = _loaded()
    loaded["B0005"]["cycle"][0]["data"]["Current_measured"] = [2.0, 2.0]

    with pytest.raises(NasaBatteryIngestionError, match="not aligned"):
        canonicalize_loaded_mat(loaded, receipt=_receipt())


def test_unknown_cycle_type_is_refused_not_guessed() -> None:
    loaded = _loaded()
    loaded["B0005"]["cycle"][0]["type"] = "pulse"

    with pytest.raises(NasaBatteryIngestionError, match="unsupported cycle type"):
        canonicalize_loaded_mat(loaded, receipt=_receipt())


def test_source_receipt_binds_exact_raw_bytes(tmp_path: Path) -> None:
    path = tmp_path / "B0005.mat"
    path.write_bytes(b"first")
    first = source_receipt(path)

    path.write_bytes(b"second")
    second = source_receipt(path)

    assert first.sha256 != second.sha256
    assert first.byte_count == 5
    assert second.byte_count == 6


def test_real_matlab_file_round_trip_uses_the_documented_cycle_shape(
    tmp_path: Path,
) -> None:
    path = tmp_path / "B0005.mat"
    savemat(
        path,
        {
            "B0005": {
                "cycle": np.array(
                    [
                        {
                            "type": "discharge",
                            "ambient_temperature": 24.0,
                            "time": np.array([2008, 4, 2, 15, 25, 41.0]),
                            "data": {
                                "Voltage_measured": np.array([4.1, 4.0, 3.9]),
                                "Current_measured": np.array([2.0, 2.0, 2.0]),
                                "Temperature_measured": np.array([24.1, 24.2, 24.3]),
                                "Time": np.array([0.0, 1.0, 2.0]),
                                "Capacity": 1.9,
                            },
                        }
                    ],
                    dtype=object,
                )
            }
        },
    )

    record = ingest_mat_file(path)

    assert record["cell_id"] == "B0005"
    assert record["cycle_count"] == 1
    assert record["cycles"][0]["cycle_type"] == "discharge"
    assert record["cycles"][0]["sample_count"] == 3
    assert record["source"]["sha256"] == source_receipt(path).sha256


@pytest.mark.parametrize("channel", ["Voltage_measured", "Current_measured", "Temperature_measured", "Time"])
@pytest.mark.parametrize("bad", [[1+2j, 2+0j, 3+0j], ["1", "2", "3"], [True, False, True], np.ones((2, 2))])
def test_malformed_operational_values_are_refused(channel, bad):
    loaded = _loaded()
    loaded["B0005"]["cycle"][0]["data"][channel] = bad
    with pytest.raises(NasaBatteryIngestionError):
        canonicalize_loaded_mat(loaded, receipt=_receipt())


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), "24", True])
def test_malformed_ambient_is_refused(bad):
    loaded = _loaded()
    loaded["B0005"]["cycle"][0]["ambient_temperature"] = bad
    with pytest.raises(NasaBatteryIngestionError):
        canonicalize_loaded_mat(loaded, receipt=_receipt())


@pytest.mark.parametrize("data", [{}, {"Battery_impedance": []}])
def test_empty_impedance_is_refused(data):
    loaded = _loaded()
    loaded["B0005"]["cycle"][1]["data"] = data
    with pytest.raises(NasaBatteryIngestionError, match="no impedance samples"):
        canonicalize_loaded_mat(loaded, receipt=_receipt())


def test_single_sample_matlab_cycle_survives_scipy_squeezing(tmp_path):
    loaded = _loaded()
    cycle = loaded["B0005"]["cycle"][0]
    for name in ("Voltage_measured", "Current_measured", "Temperature_measured", "Time"):
        cycle["data"][name] = np.array([cycle["data"][name][0]])
    path = tmp_path / "singleton.mat"
    savemat(path, {"B0005": {"cycle": cycle}})
    record = ingest_mat_file(path)
    assert record["cycles"][0]["sample_count"] == 1
    assert record["cycles"][0]["channels"]["Time"] == [0.0]


def test_receipt_and_parser_use_same_snapshot_despite_path_replacement(tmp_path, monkeypatch):
    import hashlib
    import tools.nasa_battery_aging as ingestion
    path = tmp_path / "B0005.mat"
    savemat(path, {"B0005": {"cycle": _loaded()["B0005"]["cycle"][0]}})
    original = path.read_bytes()
    real_loadmat = ingestion.loadmat
    def replacing_loadmat(source, **kwargs):
        path.write_bytes(b"changed during ingestion")
        return real_loadmat(source, **kwargs)
    monkeypatch.setattr(ingestion, "loadmat", replacing_loadmat)
    record = ingest_mat_file(path)
    assert record["source"]["sha256"] == hashlib.sha256(original).hexdigest()
    assert record["source"]["byte_count"] == len(original)
    assert record["cycles"][0]["channels"]["Voltage_measured"] == [4.1, 4.0, 3.9]


def test_digest_binds_values_receipt_cell_and_cycle_order():
    baseline = canonicalize_loaded_mat(_loaded(), receipt=_receipt())["canonical_sha256"]
    changed = _loaded()
    changed["B0005"]["cycle"][0]["data"]["Voltage_measured"][0] = 4.2
    reordered = _loaded()
    reordered["B0005"]["cycle"].reverse()
    renamed = {"B0006": _loaded()["B0005"]}
    for loaded, receipt in [(changed, _receipt()), (reordered, _receipt()), (renamed, _receipt()),
                            (_loaded(), SourceReceipt("B0005.mat", 123, "b"*64))]:
        assert canonicalize_loaded_mat(loaded, receipt=receipt)["canonical_sha256"] != baseline


@pytest.mark.parametrize("field", ["type", "ambient_temperature", "time", "data"])
def test_missing_cycle_metadata_is_refused(field):
    loaded = _loaded()
    del loaded["B0005"]["cycle"][0][field]
    with pytest.raises(NasaBatteryIngestionError, match="missing required field"):
        canonicalize_loaded_mat(loaded, receipt=_receipt())


@pytest.mark.parametrize("channel", ["Voltage_measured", "Current_measured", "Temperature_measured", "Time", "Capacity"])
def test_missing_operational_channel_is_refused(channel):
    loaded = _loaded()
    del loaded["B0005"]["cycle"][0]["data"][channel]
    with pytest.raises(NasaBatteryIngestionError):
        canonicalize_loaded_mat(loaded, receipt=_receipt())


@pytest.mark.parametrize("capacity", [0, -1, float("nan"), float("inf"), "1.9", True, [1, 2]])
def test_malformed_capacity_is_refused(capacity):
    loaded = _loaded()
    loaded["B0005"]["cycle"][0]["data"]["Capacity"] = capacity
    with pytest.raises(NasaBatteryIngestionError):
        canonicalize_loaded_mat(loaded, receipt=_receipt())


@pytest.mark.parametrize("channel", ["Voltage_measured", "Current_measured", "Temperature_measured", "Time"])
@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_nonfinite_operational_sample_is_refused(channel, bad):
    loaded = _loaded()
    loaded["B0005"]["cycle"][0]["data"][channel][1] = bad
    with pytest.raises(NasaBatteryIngestionError, match="non-finite"):
        canonicalize_loaded_mat(loaded, receipt=_receipt())


def test_decreasing_time_is_refused():
    loaded = _loaded()
    loaded["B0005"]["cycle"][0]["data"]["Time"] = [0, 2, 1]
    with pytest.raises(NasaBatteryIngestionError, match="non-decreasing"):
        canonicalize_loaded_mat(loaded, receipt=_receipt())


def test_empty_operational_samples_are_refused():
    loaded = _loaded()
    for name in ("Voltage_measured", "Current_measured", "Temperature_measured", "Time"):
        loaded["B0005"]["cycle"][0]["data"][name] = []
    with pytest.raises(NasaBatteryIngestionError, match="no operational samples"):
        canonicalize_loaded_mat(loaded, receipt=_receipt())


def test_nonfinite_complex_impedance_is_refused():
    loaded = _loaded()
    loaded["B0005"]["cycle"][1]["data"]["Battery_impedance"] = [complex(1, float("nan"))]
    with pytest.raises(NasaBatteryIngestionError, match="non-finite complex"):
        canonicalize_loaded_mat(loaded, receipt=_receipt())


def test_genuine_matlab_struct_array_preserves_cycle_order_and_channels(tmp_path):
    cycles = _loaded()["B0005"]["cycle"]
    structured = np.empty((1, 2), dtype=[(name, object) for name in cycles[0]])
    for index, cycle in enumerate(cycles):
        for name, value in cycle.items():
            structured[name][0, index] = value
    path = tmp_path / "B0005.mat"
    savemat(path, {"B0005": {"cycle": structured}})
    first = ingest_mat_file(path)
    assert first == ingest_mat_file(path)
    assert [cycle["cycle_type"] for cycle in first["cycles"]] == ["discharge", "impedance"]
    assert first["cycles"][1]["channels"]["Battery_impedance"] == [
        {"real": 0.1, "imag": 0.01}, {"real": 0.2, "imag": 0.02}]


@pytest.mark.parametrize("shape", [(1, 3), (3, 1)])
def test_matlab_row_and_column_operational_vectors_are_accepted(shape):
    loaded = _loaded()
    for name in ("Voltage_measured", "Current_measured", "Temperature_measured", "Time"):
        loaded["B0005"]["cycle"][0]["data"][name] = np.asarray(loaded["B0005"]["cycle"][0]["data"][name]).reshape(shape)
    assert canonicalize_loaded_mat(loaded, receipt=_receipt())["cycles"][0]["sample_count"] == 3
