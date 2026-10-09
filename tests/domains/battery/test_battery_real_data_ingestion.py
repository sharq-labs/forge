"""Hostile tests for canonical battery real-data ingestion, receipts, lineage and splits.

Every test here tries to get a number into the canonical record that the raw
bytes do not support, or to put one experiment on both sides of a split.
"""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest

from engcore.claims.empirical_uq_trust import PRODUCTION_EMPIRICAL_RECORDS
from engcore.claims.measurement_dataset import (
    DatasetSplit as ClaimSplit,
    MeasurementDatasetError,
    require_independent_split,
)
from engcore.domains.battery.real_data import (
    CalibrationHoldoutSplit,
    Channel,
    ColumnDeclaration,
    CurrentSign,
    DerivedChannel,
    LineageKind,
    RawFileDeclaration,
    RealDataError,
    SourceFormat,
    SplitPolicy,
    SplitUnit,
    build_split,
    calibration_series,
    derive_state_of_charge,
    ingest_dataset,
    ingest_raw_file,
)
from engcore.domains.battery.real_data.ingest import BatteryTimeSeries, ChannelLineage
from engcore.scientific.corpus import CorpusError, CorpusLeakageError, ReferenceSource, SourceSnapshot
from engcore.scientific.units.quantity import Quantity

SOURCE = ReferenceSource(
    source_id="test.synthetic.battery",
    authority="pytest",
    domain="battery",
    source_version="1",
    landing_url="https://example.org/data",
    allowed_hosts=("example.org",),
)


def _format(*, current_unit: str = "ampere", voltage_unit: str = "volt", sign=CurrentSign.POSITIVE_IS_CHARGE,
            temperature_unit: str | None = None) -> SourceFormat:
    header = ["t", "Q", "I", "U"]
    columns = [
        ColumnDeclaration("t", Channel.TIME, "second", LineageKind.MEASURED, "test declaration"),
        ColumnDeclaration("Q", Channel.CHARGE_COUNTER, "ampere_hour", LineageKind.SOURCE_COMPUTED, "test declaration"),
        ColumnDeclaration("I", Channel.CURRENT, current_unit, LineageKind.MEASURED, "test declaration"),
        ColumnDeclaration("U", Channel.VOLTAGE, voltage_unit, LineageKind.MEASURED, "test declaration"),
    ]
    if temperature_unit is not None:
        header.append("T")
        columns.append(ColumnDeclaration("T", Channel.TEMPERATURE, temperature_unit, LineageKind.MEASURED, "test"))
    return SourceFormat(
        format_id="test.synthetic.csv",
        format_version=1,
        description="synthetic test layout",
        header=tuple(header),
        columns=tuple(columns),
        current_sign=sign,
        current_sign_basis="test declaration",
        voltage_window_v=(0.5, 5.0),
    )


def _rows(n: int = 40) -> list[list[float]]:
    """A rest -> discharge -> rest record in SOURCE convention (positive = charge)."""
    rows = []
    q = 0.0
    previous = None
    for k in range(n):
        t = 10.0 * k
        i_src = -1.0 if 10 <= k < 30 else 0.0
        if previous is not None:
            q += 0.5 * (i_src + previous[1]) * (t - previous[0]) / 3600.0
        v = 3.3 - (0.05 if i_src else 0.0) - 0.001 * k
        rows.append([t, q, i_src, v])
        previous = (t, i_src)
    return rows


def _bytes(rows, header=("t", "Q", "I", "U"), terminator="\r\n") -> bytes:
    lines = [",".join(header)] + [",".join(repr(float(x)) for x in row) for row in rows]
    return (terminator.join(lines) + terminator).encode("ascii")


def _declaration(raw: bytes, *, group="cellA/seq1", cell="cellA", seq="seq1", fmt=None) -> RawFileDeclaration:
    return RawFileDeclaration(
        group_id=group,
        cell_id=cell,
        test_sequence_id=seq,
        published_filename=f"{seq}.csv",
        snapshot=SourceSnapshot(
            source_id=SOURCE.source_id,
            source_version=SOURCE.source_version,
            snapshot_sha256=hashlib.sha256(raw).hexdigest(),
            snapshot_url=f"https://example.org/{seq}.csv",
            byte_length=len(raw),
            retrieved_at_utc="2026-10-09",
        ),
        source_format=fmt or _format(),
    )


def _dataset(files: dict[str, tuple[bytes, str, str]]):
    declarations = []
    raw = {}
    for group, (data, cell, seq) in files.items():
        declarations.append(_declaration(data, group=group, cell=cell, seq=seq))
        raw[group] = data
    return ingest_dataset("test.dataset", SOURCE, declarations, raw, declared_assumptions=("test assumption",))


# ---------------------------------------------------------------------------
# Receipt identity
# ---------------------------------------------------------------------------

def test_identical_raw_bytes_give_an_identical_receipt_digest() -> None:
    raw = _bytes(_rows())
    first = _dataset({"cellA/seq1": (raw, "cellA", "seq1")})
    second = _dataset({"cellA/seq1": (bytes(bytearray(raw)), "cellA", "seq1")})
    assert first.receipt.digest == second.receipt.digest
    assert first.series[0].normalized_digest == second.series[0].normalized_digest
    payload = json.dumps(first.receipt.to_dict())
    assert "example.org" in payload and "/home/" not in payload and "\\Users\\" not in payload


def test_one_changed_byte_is_refused_against_the_pin_and_changes_identity_when_repinned() -> None:
    raw = _bytes(_rows())
    original = _declaration(raw)
    position = raw.index(b"3.2")
    mutated = raw[:position] + b"3.1" + raw[position + 3:]
    assert len(mutated) == len(raw) and mutated != raw
    with pytest.raises(RealDataError, match="do not match the pinned snapshot"):
        ingest_raw_file(mutated, original)
    receipt_a, _ = ingest_raw_file(raw, original)
    receipt_b, _ = ingest_raw_file(mutated, _declaration(mutated))
    assert receipt_a.snapshot.snapshot_sha256 != receipt_b.snapshot.snapshot_sha256
    assert receipt_a.normalized_digest != receipt_b.normalized_digest


def test_reordered_rows_change_identity_or_are_refused() -> None:
    rows = _rows()
    swapped = list(rows)
    swapped[5], swapped[6] = swapped[6], swapped[5]
    raw = _bytes(swapped)
    with pytest.raises(RealDataError, match="not strictly increasing"):
        ingest_raw_file(raw, _declaration(raw))
    duplicated = list(rows)
    duplicated[6] = [rows[5][0]] + rows[6][1:]
    raw = _bytes(duplicated)
    with pytest.raises(RealDataError, match="not strictly increasing"):
        ingest_raw_file(raw, _declaration(raw))


def test_record_order_is_the_sample_order_and_every_sample_names_its_row() -> None:
    raw = _bytes(_rows())
    receipt, series = ingest_raw_file(raw, _declaration(raw))
    assert series.row_index == tuple(range(len(_rows())))
    assert receipt.raw_record_count == receipt.normalized_record_count == len(_rows())
    assert receipt.dropped_row_count == 0 and dict(receipt.dropped_row_reasons) == {}


# ---------------------------------------------------------------------------
# Columns, units and values
# ---------------------------------------------------------------------------

def test_a_missing_required_source_column_is_refused() -> None:
    rows = [[r[0], r[1], r[2]] for r in _rows()]
    raw = _bytes(rows, header=("t", "Q", "I"))
    with pytest.raises(RealDataError, match="missing required source columns"):
        ingest_raw_file(raw, _declaration(raw))
    with pytest.raises(RealDataError, match="lacks required channels"):
        SourceFormat("x", 1, "x", ("t", "I"), (
            ColumnDeclaration("t", Channel.TIME, "second", LineageKind.MEASURED, "b"),
            ColumnDeclaration("I", Channel.CURRENT, "ampere", LineageKind.MEASURED, "b"),
        ), CurrentSign.POSITIVE_IS_CHARGE, "b", (0.5, 5.0))


def test_an_undeclared_extra_column_is_refused_not_ignored() -> None:
    rows = [r + [1.0] for r in _rows()]
    raw = _bytes(rows, header=("t", "Q", "I", "U", "X"))
    with pytest.raises(RealDataError, match="undeclared columns"):
        ingest_raw_file(raw, _declaration(raw))


@pytest.mark.parametrize("unit, pattern", [
    ("", "no unit declared"),
    ("C", "ambiguous"),
    ("deg", "ambiguous"),
    ("ampere", "dimension"),
    ("furlong_per_fortnight_x", "not a unit"),
])
def test_ambiguous_missing_or_wrong_units_are_refused(unit: str, pattern: str) -> None:
    with pytest.raises(RealDataError, match=pattern):
        ColumnDeclaration("T", Channel.TEMPERATURE, unit, LineageKind.MEASURED, "basis")


def test_a_wrong_but_well_formed_unit_is_refused_by_the_data() -> None:
    raw = _bytes(_rows())
    with pytest.raises(RealDataError, match="contradicted by the data"):
        ingest_raw_file(raw, _declaration(raw, fmt=_format(current_unit="milliampere")))
    with pytest.raises(RealDataError, match="outside the declared window"):
        ingest_raw_file(raw, _declaration(raw, fmt=_format(voltage_unit="millivolt")))


def test_a_misdeclared_current_sign_is_refused_by_the_passive_step_test() -> None:
    raw = _bytes(_rows())
    with pytest.raises(RealDataError, match="current sign"):
        ingest_raw_file(raw, _declaration(raw, fmt=_format(sign=CurrentSign.POSITIVE_IS_DISCHARGE)))


def test_sign_conversion_is_explicit_in_the_lineage() -> None:
    raw = _bytes(_rows())
    _, series = ingest_raw_file(raw, _declaration(raw))
    current = {item.channel: item for item in series.lineage}["current"]
    assert "negated" in current.transformation
    assert series.array(Channel.CURRENT)[15] == pytest.approx(1.0)


@pytest.mark.parametrize("token", ["nan", "NaN", "inf", "-inf", "", " ", "1e999", "0x10", "1,5"])
def test_nan_infinite_empty_or_malformed_measurements_are_refused(token: str) -> None:
    raw = _bytes(_rows()).decode("ascii")
    lines = raw.split("\r\n")
    cells = lines[12].split(",")
    cells[3] = token
    lines[12] = ",".join(cells)
    data = "\r\n".join(lines).encode("ascii")
    with pytest.raises(RealDataError):
        ingest_raw_file(data, _declaration(data))


def test_mixed_line_terminators_are_refused() -> None:
    raw = _bytes(_rows())
    position = raw.index(b"\r\n", 50)
    mixed = raw[:position] + b"\n" + raw[position + 2:]
    with pytest.raises(RealDataError, match="mixed line terminators"):
        ingest_raw_file(mixed, _declaration(mixed))


def test_temperature_in_celsius_is_converted_point_by_point_to_kelvin() -> None:
    rows = [r + [25.0 + 0.1 * k] for k, r in enumerate(_rows())]
    raw = _bytes(rows, header=("t", "Q", "I", "U", "T"))
    _, series = ingest_raw_file(raw, _declaration(raw, fmt=_format(temperature_unit="degC")))
    assert series.array(Channel.TEMPERATURE)[0] == pytest.approx(298.15)
    assert series.array(Channel.TEMPERATURE)[10] == pytest.approx(299.15)


# ---------------------------------------------------------------------------
# Derived state of charge never masquerades as source data
# ---------------------------------------------------------------------------

def test_state_of_charge_cannot_be_declared_as_a_source_column() -> None:
    for name in ("state_of_charge", "SOC", "soc"):
        with pytest.raises(RealDataError, match="state of charge is not measured"):
            ColumnDeclaration("Z", name, "dimensionless", LineageKind.MEASURED, "tester export")
    with pytest.raises(RealDataError, match="DERIVED"):
        ColumnDeclaration("U", Channel.VOLTAGE, "volt", LineageKind.DERIVED, "computed")


def test_a_derived_lineage_cannot_sit_among_source_channels() -> None:
    raw = _bytes(_rows())
    _, series = ingest_raw_file(raw, _declaration(raw))
    forged = [
        ChannelLineage(l.channel, LineageKind.DERIVED if l.channel == "voltage" else l.kind, l.source_column,
                       l.source_unit, l.normalized_unit, l.transformation, l.basis)
        for l in series.lineage
    ]
    with pytest.raises(RealDataError, match="DERIVED channel cannot be stored"):
        BatteryTimeSeries(series.group_id, series.cell_id, series.test_sequence_id, series.raw_sha256,
                          series.row_index, series.channels, tuple(forged))
    with pytest.raises(RealDataError, match="state of charge is not measured"):
        BatteryTimeSeries(series.group_id, series.cell_id, series.test_sequence_id, series.raw_sha256,
                          series.row_index, {**series.channels, "state_of_charge": series.channels["voltage"]},
                          series.lineage)


def test_derived_state_of_charge_is_labelled_and_bound_to_its_inputs() -> None:
    raw = _bytes(_rows())
    _, series = ingest_raw_file(raw, _declaration(raw))
    soc = derive_state_of_charge(series, initial_state_of_charge=Quantity(0.9, "dimensionless"),
                                 reference_capacity=Quantity(1.0, "ampere_hour"))
    assert isinstance(soc, DerivedChannel) and soc.kind is LineageKind.DERIVED
    record = soc.to_dict()
    assert record["is_source_data"] is False and record["can_be_measurement_evidence"] is False
    assert record["input_series_digest"] == series.normalized_digest
    assert set(record["assumptions"]) == {"initial_state_of_charge", "reference_capacity"}
    assert "state_of_charge" not in series.channels
    other = derive_state_of_charge(series, initial_state_of_charge=Quantity(0.8, "dimensionless"),
                                   reference_capacity=Quantity(1.0, "ampere_hour"))
    assert other.digest != soc.digest
    with pytest.raises(RealDataError, match="leaves"):
        derive_state_of_charge(series, initial_state_of_charge=Quantity(0.01, "dimensionless"),
                               reference_capacity=Quantity(0.01, "ampere_hour"))


# ---------------------------------------------------------------------------
# Split: whole groups, receipt-bound, disjoint
# ---------------------------------------------------------------------------

def _three_groups():
    a = _bytes(_rows(40))
    b = _bytes(_rows(41))
    c = _bytes(_rows(42))
    return _dataset({
        "cellA/seq1": (a, "cellA", "seq1"),
        "cellA/seq2": (b, "cellA", "seq2"),
        "cellB/seq1b": (c, "cellB", "seq1b"),
    })


def test_overlapping_calibration_and_holdout_keys_are_refused() -> None:
    with pytest.raises(CorpusLeakageError, match="calibration AND holdout"):
        SplitPolicy("p", SplitUnit.CELL, ("cellA",), ("cellA", "cellB"), "hostile")
    with pytest.raises(CorpusError, match="no holdout"):
        SplitPolicy("p", SplitUnit.CELL, ("cellA",), (), "hostile")


def test_a_cell_level_split_never_puts_one_cell_on_both_sides() -> None:
    dataset = _three_groups()
    split = build_split(dataset, SplitPolicy("p", SplitUnit.CELL, ("cellA",), ("cellB",), "cell split"))
    assert split.calibration_groups == ("cellA/seq1", "cellA/seq2")
    assert split.holdout_groups == ("cellB/seq1b",)
    assert split.shared_cells == ()
    assert not set(split.calibration_raw_sha256) & set(split.holdout_raw_sha256)


def test_a_sequence_split_on_one_cell_records_the_shared_cell_and_narrows_its_scope() -> None:
    dataset = _three_groups()
    split = build_split(dataset, SplitPolicy("p", SplitUnit.TEST_SEQUENCE, ("seq1",), ("seq2", "seq1b"), "seq"))
    assert split.shared_cells == ("cellA",)
    assert "within-cell only" in split.independence_scope


def test_rows_of_one_physical_group_leaking_into_calibration_are_refused() -> None:
    dataset = _three_groups()
    split = build_split(dataset, SplitPolicy("p", SplitUnit.CELL, ("cellA",), ("cellB",), "cell split"))
    # Hand-assembled leak: the held-out group also listed as calibration.
    with pytest.raises(CorpusLeakageError):
        CalibrationHoldoutSplit(
            split.receipt_digest, split.dataset_id, split.policy,
            split.calibration_groups + ("cellB/seq1b",), split.holdout_groups,
            split.calibration_raw_sha256, split.holdout_raw_sha256, (), split.independence_scope,
        )
    # Same raw bytes filed as two groups -- one experiment cannot be two.
    raw = _bytes(_rows())
    with pytest.raises(RealDataError, match="same raw bytes"):
        _dataset({"cellA/seq1": (raw, "cellA", "seq1"), "cellB/seq9": (raw, "cellB", "seq9")})


def test_an_unassigned_group_is_a_refusal_not_a_silent_exclusion() -> None:
    dataset = _three_groups()
    with pytest.raises(RealDataError, match="assigned to neither side"):
        build_split(dataset, SplitPolicy("p", SplitUnit.TEST_SEQUENCE, ("seq1",), ("seq2",), "gap"))
    with pytest.raises(RealDataError, match="does not hold"):
        build_split(dataset, SplitPolicy("p", SplitUnit.CELL, ("cellA",), ("cellZ",), "unknown"))


def test_a_split_bound_to_another_receipt_cannot_feed_a_fit() -> None:
    dataset = _three_groups()
    split = build_split(dataset, SplitPolicy("p", SplitUnit.CELL, ("cellA",), ("cellB",), "cell split"))
    other = _dataset({
        "cellA/seq1": (_bytes(_rows(43)), "cellA", "seq1"),
        "cellA/seq2": (_bytes(_rows(41)), "cellA", "seq2"),
        "cellB/seq1b": (_bytes(_rows(42)), "cellB", "seq1b"),
    })
    with pytest.raises(RealDataError, match="another dataset receipt"):
        calibration_series(other, split)
    assert [s.group_id for s in calibration_series(dataset, split)] == ["cellA/seq1", "cellA/seq2"]


def test_a_hand_built_split_cannot_route_a_held_out_cell_into_a_fit() -> None:
    dataset = _three_groups()
    honest = build_split(dataset, SplitPolicy("p", SplitUnit.CELL, ("cellA",), ("cellB",), "cell split"))
    by = {s.group_id: s.raw_sha256 for s in dataset.series}
    forged = CalibrationHoldoutSplit(
        honest.receipt_digest, honest.dataset_id, honest.policy,
        ("cellA/seq1", "cellB/seq1b"), ("cellA/seq2",),
        tuple(sorted((by["cellA/seq1"], by["cellB/seq1b"]))), (by["cellA/seq2"],), (), honest.independence_scope,
    )
    with pytest.raises(RealDataError, match="not the one its own policy derives"):
        calibration_series(dataset, forged)
    ghost = CalibrationHoldoutSplit(
        honest.receipt_digest, honest.dataset_id, honest.policy,
        tuple(sorted(by)), ("ghost",), tuple(sorted(by.values())), ("0" * 64,), (), honest.independence_scope,
    )
    with pytest.raises(RealDataError, match="not the one its own policy derives"):
        calibration_series(dataset, ghost)


def test_the_split_digest_is_bound_to_the_receipt() -> None:
    a = _three_groups()
    b = _three_groups()
    policy = SplitPolicy("p", SplitUnit.CELL, ("cellA",), ("cellB",), "cell split")
    assert build_split(a, policy).digest == build_split(b, policy).digest
    assert build_split(a, policy).receipt_digest == a.receipt.digest


# ---------------------------------------------------------------------------
# Review 3: the S-OCV production catalog
# ---------------------------------------------------------------------------

def test_the_production_s_ocv_catalog_is_split_by_cell() -> None:
    calibration = {o.independence_group for o in PRODUCTION_EMPIRICAL_RECORDS if o.split is ClaimSplit.CALIBRATION}
    validation = {o.independence_group for o in PRODUCTION_EMPIRICAL_RECORDS if o.split is ClaimSplit.VALIDATION}
    assert calibration == {"cell:BATT_001"}
    assert validation == {"cell:BATT_002"}
    assert not calibration & validation


def test_a_catalog_with_one_cell_on_both_sides_is_refused() -> None:
    first = PRODUCTION_EMPIRICAL_RECORDS[0]
    from dataclasses import replace

    leaked = (first, replace(first, observation_id=first.observation_id + ":copy", split=ClaimSplit.VALIDATION))
    with pytest.raises(MeasurementDatasetError, match="row-wise leakage"):
        require_independent_split(leaked)
    require_independent_split(PRODUCTION_EMPIRICAL_RECORDS)


def test_normalized_values_survive_a_unit_restatement() -> None:
    rows = _rows()
    milli = [[r[0], r[1], r[2] * 1000.0, r[3] * 1000.0] for r in rows]
    raw_a, raw_b = _bytes(rows), _bytes(milli)
    _, a = ingest_raw_file(raw_a, _declaration(raw_a))
    _, b = ingest_raw_file(raw_b, _declaration(raw_b, fmt=_format(current_unit="milliampere", voltage_unit="millivolt")))
    for channel in (Channel.CURRENT, Channel.VOLTAGE, Channel.TIME):
        assert np.allclose(a.array(channel), b.array(channel), rtol=1e-12, atol=1e-15)
