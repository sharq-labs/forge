"""Battery Practical Pass 1 on the vendored A123 HysPowerTest bytes.

These tests read the real raw files under benchmarks/battery_flagship_b3/evidence/raw.
They pin the receipt identity and the gate's DECISION, never a fitted value.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from engcore.domains.battery.real_data import (
    GateDecision,
    assess_thevenin_1rc_identifiability,
    build_split,
    ingest_dataset,
    quality_report,
)
from engcore.domains.battery.real_data import sources

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "benchmarks" / "battery_flagship_b3" / "evidence" / "raw"
PROVENANCE = ROOT / "benchmarks" / "battery_flagship_b3" / "evidence" / "PROVENANCE.json"
PASS1 = ROOT / "benchmarks" / "battery_real_data_identifiability"

#: The dataset identity at this pass's parser, normalization and declaration versions.
RECEIPT_DIGEST = "b22162f1237f6e7cd52873ff2d87f57cef60898233cfb9a165e87fa8aad54d5c"


def _runner():
    spec = importlib.util.spec_from_file_location("battery_pass1_runner", PASS1 / "audit" / "run_pass1.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def dataset():
    raw = {d.group_id: (RAW / d.published_filename).read_bytes() for d in sources.JAHN_2024_HYSPOWERTEST_FILES}
    return ingest_dataset(sources.JAHN_2024_DATASET_ID, sources.JAHN_2024_SOURCE,
                          sources.JAHN_2024_HYSPOWERTEST_FILES, raw,
                          declared_assumptions=sources.JAHN_2024_HYSPOWERTEST_ASSUMPTIONS)


@pytest.fixture(scope="module")
def runner():
    return _runner()


@pytest.fixture(scope="module")
def gate(dataset, runner):
    split = build_split(dataset, runner.SPLIT_POLICY)
    return split, assess_thevenin_1rc_identifiability(dataset, split, runner.NOISE)


def test_the_byte_pins_agree_with_the_acquisition_record() -> None:
    record = json.loads(PROVENANCE.read_bytes())
    by_name = {f["raw_filename"]: f for f in record["files"]}
    for declaration in sources.JAHN_2024_HYSPOWERTEST_FILES:
        entry = by_name[declaration.published_filename]
        assert declaration.snapshot.snapshot_sha256 == entry["sha256"]
        assert declaration.snapshot.byte_length == entry["bytes"]
        assert declaration.snapshot.snapshot_url == entry["acquisition_url"]


def test_the_receipt_identity_is_pinned_and_machine_independent(dataset) -> None:
    assert dataset.receipt.digest == RECEIPT_DIGEST
    text = json.dumps(dataset.receipt.to_dict())
    assert str(ROOT) not in text and "/home/" not in text
    files = {f.group_id: f for f in dataset.receipt.files}
    assert files["A123_01/HysPowerTest_SOC100"].raw_record_count == 723
    assert files["A123_01/HysPowerTest_SOC50"].raw_record_count == 336
    for receipt in files.values():
        assert receipt.dropped_row_count == 0
        assert receipt.line_terminator == "CRLF"
        checks = receipt.consistency_checks
        assert checks["charge_counter_max_abs_error_ah"] < 2e-4
        assert checks["passive_step_test"]["steps"] == checks["passive_step_test"]["voltage_moves_against_canonical_current"] > 0


def test_the_quality_report_classifies_without_cleaning(dataset) -> None:
    report = quality_report(dataset.group("A123_01/HysPowerTest_SOC100"))
    assert [s["kind"] for s in report["segments"]] == ["rest", "charge", "rest", "discharge", "rest", "discharge"]
    assert report["channels_absent"] == {"temperature": "not a source channel of this format"}
    assert report["voltage_quantization_step_v"] == pytest.approx(1.908776803496437e-4, rel=1e-9)
    assert report["dropped_records"] == 0
    onsets = [t for t in report["transitions"] if t["kind"] == "onset"]
    assert [round(t["bracket_s"], 3) for t in onsets] == [0.002, 0.002]
    assert report["constant_voltage_runs"][0]["segment_kind"] == "charge"


def test_the_split_is_within_one_cell_and_says_so(gate) -> None:
    split, _ = gate
    assert split.calibration_groups == ("A123_01/HysPowerTest_SOC100",)
    assert split.holdout_groups == ("A123_01/HysPowerTest_SOC50",)
    assert split.shared_cells == ("A123_01",)
    assert "within-cell only" in split.independence_scope
    assert not set(split.calibration_raw_sha256) & set(split.holdout_raw_sha256)


def test_the_gate_refuses_to_promote_window_dependent_parameters(gate) -> None:
    _, report = gate
    record = report.to_dict()
    cell = record["cells"]["A123_01"]
    assert report.decision is GateDecision.WEAKLY_IDENTIFIABLE
    assert report.action == "REVIEW"
    assert record["holdout_groups_not_read"] == ["A123_01/HysPowerTest_SOC50"]
    assert cell["structural"]["status"] == "PARAMETERS_IDENTIFIABLE"
    assert cell["practical_local"]["frozen_rule_status"] == "PARAMETERS_IDENTIFIABLE"
    assert cell["horizon_stability"]["verdict"] == "UNSTABLE"
    z = {name: max(h["z_score"][name] for h in cell["horizon_stability"]["horizons"] if h["comparable"])
         for name in ("R1", "C1")}
    assert z["C1"] > 3.0 and z["R1"] > 1.96
    assert any("window-unstable" in r for r in report.reasons)
    assert any("resolution-dependent" in r for r in report.reasons)
    assert len(cell["excitation"]["relaxation_windows"]) == 1
    assert cell["diagnostic_fit"]["use"] == "DIAGNOSTIC_ONLY_NOT_CALIBRATED"


def test_the_committed_pass1_artifacts_reproduce(runner) -> None:
    assert runner.main(["--check"]) == 0


def test_a_tampered_gate_record_is_detected(runner) -> None:
    from engcore.domains.battery.real_data.identifiability import gate_record_digest

    committed = json.loads((PASS1 / "IDENTIFIABILITY_GATE.json").read_bytes())
    assert gate_record_digest(committed) == committed["gate_digest"]
    forged = json.loads(json.dumps(committed))
    forged["cells"]["A123_01"]["diagnostic_fit"]["linearization_point"]["R0"]["value"] *= 1.01
    assert gate_record_digest(forged) != committed["gate_digest"]
    assert runner._numeric_differences(forged, committed, "gate")


@pytest.mark.parametrize("millivolt", [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 20.0])
def test_declaring_more_noise_never_buys_calibration_on_the_real_record(dataset, runner, millivolt) -> None:
    from engcore.domains.battery.real_data import VoltageNoiseDeclaration
    from engcore.scientific.units.quantity import Quantity

    split = build_split(dataset, runner.SPLIT_POLICY)
    noise = VoltageNoiseDeclaration(Quantity(millivolt, "millivolt"), source="hostile", basis="inflated")
    report = assess_thevenin_1rc_identifiability(dataset, split, noise)
    assert report.decision is not GateDecision.CAN_CALIBRATE, report.reasons
    cell = report.to_dict()["cells"]["A123_01"]
    rms = cell["noise"]["diagnostic_residual_rms_v"]
    if millivolt * 1e-3 >= rms:
        assert cell["noise"]["check_scale_v"] == pytest.approx(rms)
        assert cell["horizon_stability"]["verdict"] == "UNSTABLE"


def test_a_dataset_whose_series_are_not_its_receipt_cannot_be_built(dataset) -> None:
    from engcore.domains.battery.real_data import BatteryDataset, BatteryTimeSeries, RealDataError

    cal = dataset.group("A123_01/HysPowerTest_SOC100")
    hold = dataset.group("A123_01/HysPowerTest_SOC50")
    ghost = BatteryTimeSeries(cal.group_id, cal.cell_id, cal.test_sequence_id, cal.raw_sha256,
                              hold.row_index, hold.channels, hold.lineage)
    with pytest.raises(RealDataError, match="not the content its receipt names"):
        BatteryDataset(dataset.receipt, (ghost, hold))
    with pytest.raises(RealDataError, match="one to one"):
        BatteryDataset(dataset.receipt, (cal,))


def test_the_holdout_publishes_no_voltage_feature() -> None:
    quality = json.loads((PASS1 / "QUALITY.json").read_bytes())
    held = [r for r in quality["reports"] if r["group_id"] == "A123_01/HysPowerTest_SOC50"][0]
    published = {k: v for k, v in held.items() if k != "segmentation_policy"}  # policy names thresholds only
    text = json.dumps(published)
    assert "voltage" not in text.replace("no voltage-derived feature", "")
    assert "step_resistance" not in text
