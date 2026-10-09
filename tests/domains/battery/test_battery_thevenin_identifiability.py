"""Hostile tests for the battery.thevenin_1rc identifiability gate.

Synthetic records are generated with the gate's own interval convention and
the kernel's exact update, so a well-excited record is exactly the model and
every refusal below is about information, not about misfit -- except the
two-time-constant record, which is built to be misfit on purpose.
"""

from __future__ import annotations

import hashlib
import inspect
import math

import numpy as np
import pytest

from engcore.domains.battery.cell import CellSpecification
from engcore.domains.battery.real_data import (
    Channel,
    ColumnDeclaration,
    CurrentSign,
    GateDecision,
    IdentifiabilityDesign,
    LineageKind,
    RawFileDeclaration,
    RealDataError,
    SourceFormat,
    SplitPolicy,
    SplitUnit,
    VoltageNoiseDeclaration,
    assess_thevenin_1rc_identifiability,
    build_split,
    ingest_dataset,
    thevenin_1rc_overpotential,
)
from engcore.domains.battery.real_data import identifiability as gate_module
from engcore.domains.battery.thevenin import Thevenin1RCParameters, TheveninState, evaluate_thevenin_step
from engcore.scientific.corpus import ReferenceSource, SourceSnapshot
from engcore.scientific.units.quantity import Quantity

SOURCE = ReferenceSource("test.synthetic.1rc", "pytest", "battery", "1", "https://example.org/d", ("example.org",))
NOISE = VoltageNoiseDeclaration(Quantity(1.0, "millivolt"), source="test", basis="declared for the test")
OCV = 3.3


def _format(current_unit: str = "ampere", voltage_unit: str = "volt") -> SourceFormat:
    return SourceFormat(
        format_id="test.synthetic.1rc.csv",
        format_version=1,
        description="synthetic",
        header=("t", "Q", "I", "U"),
        columns=(
            ColumnDeclaration("t", Channel.TIME, "second", LineageKind.MEASURED, "test"),
            ColumnDeclaration("Q", Channel.CHARGE_COUNTER, "ampere_hour", LineageKind.SOURCE_COMPUTED, "test"),
            ColumnDeclaration("I", Channel.CURRENT, current_unit, LineageKind.MEASURED, "test"),
            ColumnDeclaration("U", Channel.VOLTAGE, voltage_unit, LineageKind.MEASURED, "test"),
        ),
        current_sign=CurrentSign.POSITIVE_IS_DISCHARGE,
        current_sign_basis="test",
        voltage_window_v=(0.5, 5.0),
    )


def _profile(segments, *, bracket: float = 0.002):
    """segments: (duration_s, discharge_current_a, sample_interval_s). One sample `bracket` after each step."""
    t, i = [], []
    start = 0.0
    for n, (duration, current, dt) in enumerate(segments):
        if n:
            t.append(start + bracket)
            i.append(current)
        k = 0 if n == 0 else 1
        while True:
            when = start + k * dt
            if when > start + duration + 1e-9:
                break
            if not t or when > t[-1] + 1e-9:
                t.append(when)
                i.append(current)
            k += 1
        start += duration
    return np.asarray(t), np.asarray(i)


def _voltage(t, i, *, r0=0.02, r1=0.03, c1=40.0 / 0.03, vp0=0.0, second=None, noise=0.0, seed=7):
    eta = thevenin_1rc_overpotential(t, i, r0_ohm=r0, r1_ohm=r1, c1_farad=c1, initial_polarization_v=vp0)
    if second is not None:
        r2, c2 = second
        eta = eta + thevenin_1rc_overpotential(t, i, r0_ohm=0.0, r1_ohm=r2, c1_farad=c2)
    v = OCV - eta
    if noise:
        v = v + np.random.default_rng(seed).normal(0.0, noise, v.size)
    return v


def _csv(t, i, v, *, current_scale: float = 1.0, voltage_scale: float = 1.0) -> bytes:
    q = np.concatenate([[0.0], np.cumsum(0.5 * (i[1:] + i[:-1]) * np.diff(t))]) / 3600.0
    lines = ["t,Q,I,U"] + [
        f"{repr(float(a))},{repr(float(b))},{repr(float(c * current_scale))},{repr(float(d * voltage_scale))}"
        for a, b, c, d in zip(t, q, i, v)
    ]
    return ("\n".join(lines) + "\n").encode("ascii")


def _declaration(raw: bytes, group: str, seq: str, fmt: SourceFormat) -> RawFileDeclaration:
    return RawFileDeclaration(
        group, "cellA", seq, f"{seq}.csv",
        SourceSnapshot(SOURCE.source_id, SOURCE.source_version, hashlib.sha256(raw).hexdigest(),
                       f"https://example.org/{seq}.csv", len(raw), "2026-10-09"),
        fmt,
    )


def _holdout_bytes() -> bytes:
    t, i = _profile([(300, 0.0, 10), (600, 2.0, 10), (600, 0.0, 10)])
    return _csv(t, i, _voltage(t, i, noise=3e-4, seed=99))


def _run(calibration: bytes, *, holdout: bytes | None = None, design: IdentifiabilityDesign | None = None,
         fmt: SourceFormat | None = None, noise: VoltageNoiseDeclaration = NOISE):
    fmt = fmt or _format()
    holdout = holdout if holdout is not None else _holdout_bytes()
    declarations = [_declaration(calibration, "cellA/cal", "cal", fmt),
                    _declaration(holdout, "cellA/hold", "hold", _format())]
    dataset = ingest_dataset("test", SOURCE, declarations, {"cellA/cal": calibration, "cellA/hold": holdout},
                             declared_assumptions=("synthetic",))
    split = build_split(dataset, SplitPolicy("p", SplitUnit.TEST_SEQUENCE, ("cal",), ("hold",), "test"))
    report = assess_thevenin_1rc_identifiability(dataset, split, noise, design or IdentifiabilityDesign())
    return report, report.to_dict()["cells"]["cellA"]


def _well_excited(**kwargs) -> bytes:
    t, i = _profile([(300, 0.0, 10), (1200, 1.0, 10), (900, 0.0, 5)])
    return _csv(t, i, _voltage(t, i, noise=3e-4, **kwargs))


# ---------------------------------------------------------------------------
# The gate's forward model IS the kernel
# ---------------------------------------------------------------------------

def test_the_gate_recursion_equals_chained_kernel_steps() -> None:
    cell = CellSpecification(
        cell_id="equivalence", nominal_capacity=Quantity(500.0, "ampere_hour"),
        internal_resistance=Quantity(0.02, "ohm"), open_circuit_voltage_at_full=Quantity(3.4, "volt"),
        open_circuit_voltage_at_empty=Quantity(3.0, "volt"), coulombic_efficiency=Quantity(1.0, "dimensionless"),
    )
    rc = Thevenin1RCParameters(Quantity(0.03, "ohm"), Quantity(1000.0, "farad"))
    t, i = _profile([(50, 0.0, 5), (200, 1.5, 7), (100, 0.0, 3), (60, 0.7, 11)])
    state = TheveninState(Quantity(0.9, "dimensionless"), Quantity(0.0, "volt"))
    kernel = []
    for k in range(1, t.size):
        step = evaluate_thevenin_step(cell, rc, state, current=Quantity(float(i[k]), "ampere"),
                                      duration=Quantity(float(t[k] - t[k - 1]), "second"))
        kernel.append((step.open_circuit_voltage - step.terminal_voltage).magnitude_in("volt"))
        state = step.final_state
    gate = thevenin_1rc_overpotential(t, i, r0_ohm=0.02, r1_ohm=0.03, c1_farad=1000.0)
    assert np.allclose(gate[1:], kernel, rtol=0.0, atol=1e-12)


# ---------------------------------------------------------------------------
# Refusals for missing information
# ---------------------------------------------------------------------------

def test_steady_constant_current_is_insufficient_excitation() -> None:
    t, i = _profile([(3600, 1.0, 10)])
    report, cell = _run(_csv(t, i, _voltage(t, i, vp0=0.03)))
    assert report.decision is GateDecision.INSUFFICIENT_EXCITATION
    assert report.action == "REFUSE"
    assert "steady or zero current" in cell["reasons"][0]
    assert "diagnostic_fit" not in cell


def test_zero_current_is_insufficient_excitation() -> None:
    t, i = _profile([(3600, 0.0, 10)])
    report, _ = _run(_csv(t, i, _voltage(t, i)))
    assert report.decision is GateDecision.INSUFFICIENT_EXCITATION


def test_a_discharge_without_a_following_rest_cannot_separate_r1_from_c1() -> None:
    t, i = _profile([(300, 0.0, 10), (1200, 1.0, 10)])
    report, cell = _run(_csv(t, i, _voltage(t, i)))
    assert report.decision is GateDecision.INSUFFICIENT_EXCITATION
    assert "relaxation" in cell["reasons"][0]


def test_charge_only_calibration_data_are_insufficient_data() -> None:
    t, i = _profile([(3600, -1.0, 10)])
    report, _ = _run(_csv(t, i, _voltage(t, -i) * 0 + 3.4))
    assert report.decision is GateDecision.INSUFFICIENT_DATA


def test_an_undeclared_or_zero_noise_is_refused() -> None:
    with pytest.raises(RealDataError):
        VoltageNoiseDeclaration(Quantity(0.0, "volt"), source="x", basis="y")
    with pytest.raises(RealDataError):
        VoltageNoiseDeclaration(Quantity(1.0, "ampere"), source="x", basis="y")
    with pytest.raises(RealDataError):
        VoltageNoiseDeclaration(Quantity(1e-3, "volt"), source="", basis="y")
    t, i = _profile([(300, 0.0, 10), (1200, 1.0, 10), (900, 0.0, 5)])
    with pytest.raises(RealDataError, match="never zero"):
        _run(_csv(t, i, _voltage(t, i)), noise=None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# A well-excited record, and what can break it
# ---------------------------------------------------------------------------

def test_a_well_excited_1rc_record_can_be_calibrated() -> None:
    report, cell = _run(_well_excited())
    assert report.decision is GateDecision.CAN_CALIBRATE, report.reasons
    assert report.action == "CAN_CALIBRATE"
    assert cell["structural"]["status"] == "PARAMETERS_IDENTIFIABLE"
    assert cell["practical_local"]["frozen_rule_status"] == "PARAMETERS_IDENTIFIABLE"
    assert cell["horizon_stability"]["verdict"] == "STABLE"
    for name in ("R0", "R1", "C1"):
        assert cell["parameters"][name]["practical_profile"] == "PARAMETERS_IDENTIFIABLE"
    assert cell["finite_difference_check"]["agrees"] is True
    point = cell["diagnostic_fit"]["linearization_point"]
    assert point["R1*C1"]["value"] == pytest.approx(40.0, rel=0.1)
    assert cell["diagnostic_fit"]["use"] == "DIAGNOSTIC_ONLY_NOT_CALIBRATED"


def test_only_tau_is_observable_when_the_polarization_before_the_rest_is_unknown() -> None:
    # The record starts with one loaded sample, so the polarization at the interruption is a free nuisance.
    t = np.concatenate([[0.0, 0.002], 0.002 + np.arange(5.0, 905.0, 5.0)])
    i = np.concatenate([[1.0], np.zeros(t.size - 1)])
    v = _voltage(t, i, vp0=0.03, noise=2e-4)
    report, cell = _run(_csv(t, i, v))
    assert report.decision is GateDecision.NON_IDENTIFIABLE
    per = cell["structural"]["per_parameter"]
    assert per["R1"] == per["C1"] == "PARAMETERS_NOT_IDENTIFIABLE"
    assert per["R1*C1"] == "PARAMETERS_IDENTIFIABLE"
    assert per["R0"] == "PARAMETERS_IDENTIFIABLE"
    assert "only tau = R1*C1" in cell["structural"]["coupling"]
    direction = cell["structural"]["null_directions"][0]
    assert abs(direction["d_ln_R1"]) == pytest.approx(abs(direction["d_ln_C1"]), rel=1e-6)
    assert abs(direction["d_ln_R0"]) < 1e-6


def test_a_transient_window_shorter_than_tau_is_refused() -> None:
    # tau = 2000 s against a 600 s rest: the relaxation's shape is not in the record.
    t, i = _profile([(300, 0.0, 10), (20000, 1.0, 50), (600, 0.0, 5)])
    v = _voltage(t, i, c1=2000.0 / 0.03, noise=2e-4)
    report, cell = _run(_csv(t, i, v))
    assert report.decision in (GateDecision.INSUFFICIENT_EXCITATION, GateDecision.NON_IDENTIFIABLE)
    assert report.decision is not GateDecision.CAN_CALIBRATE
    text = " ".join(cell["reasons"])
    assert "too short" in text or "bound" in text or "not bounded" in text


def test_steps_sampled_slower_than_tau_cannot_separate_r0_from_r1() -> None:
    # 30 s brackets against tau = 4 s: every sample sees the steady state.
    t, i = _profile([(300, 0.0, 30), (1200, 1.0, 30), (900, 0.0, 30)], bracket=30.0)
    v = _voltage(t, i, c1=4.0 / 0.03, noise=2e-4)
    report, _ = _run(_csv(t, i, v))
    assert report.decision is not GateDecision.CAN_CALIBRATE
    assert report.action == "REFUSE"


def test_inflated_noise_never_hides_a_second_time_constant() -> None:
    t, i = _profile([(300, 0.0, 10), (1800, 1.0, 10), (1200, 0.0, 5)])
    v = _voltage(t, i, r1=0.02, c1=10.0 / 0.02, second=(0.02, 400.0 / 0.02), noise=2e-4)
    entered = []
    for millivolt in (1.0, 2.0, 5.0, 10.0, 30.0):
        noise = VoltageNoiseDeclaration(Quantity(millivolt, "millivolt"), source="hostile", basis="inflated")
        report, cell = _run(_csv(t, i, v), noise=noise)
        assert report.decision is not GateDecision.CAN_CALIBRATE, (millivolt, report.reasons)
        rms = cell["noise"]["diagnostic_residual_rms_v"]
        if millivolt * 1e-3 >= rms:
            entered.append(millivolt)
            # Declaring more noise than the fit leaves must not move the check scale, nor hide the instability.
            assert cell["noise"]["check_scale_v"] == pytest.approx(rms)
            assert cell["horizon_stability"]["verdict"] == "UNSTABLE"
    assert entered, "no declared noise reached the residual RMS; the strict branch was never exercised"


def test_declaring_less_noise_than_the_fit_leaves_is_a_misfit() -> None:
    t, i = _profile([(300, 0.0, 10), (1200, 1.0, 10), (900, 0.0, 5)])
    v = _voltage(t, i, noise=1e-3)
    noise = VoltageNoiseDeclaration(Quantity(0.2, "millivolt"), source="hostile", basis="understated")
    report, cell = _run(_csv(t, i, v), noise=noise)
    assert report.decision is not GateDecision.CAN_CALIBRATE
    assert any(r.startswith("misfit:") for r in cell["reasons"])


def test_correlated_residuals_are_capped_and_widen_the_intervals() -> None:
    t, i = _profile([(300, 0.0, 10), (1200, 1.0, 10), (900, 0.0, 5)])
    clean = _voltage(t, i)
    # Small enough that the inflated widths still pass, so it is the whiteness cap that must catch it. At 1 mV
    # the inflation alone pushes R0 and C1 past their own values and the gate refuses outright.
    white = np.random.default_rng(3).normal(0.0, 2e-4, clean.size + 15)
    coloured = np.convolve(white, np.ones(16) / 4.0, mode="valid")[: clean.size]
    noise = VoltageNoiseDeclaration(Quantity(0.25, "millivolt"), source="test", basis="matches the amplitude")
    report, cell = _run(_csv(t, i, clean + coloured), noise=noise)
    assert report.decision is not GateDecision.CAN_CALIBRATE
    assert any("structured residuals" in r for r in cell["reasons"]), cell["reasons"]
    assert cell["noise"]["autocorrelation_width_inflation"] > 2.0


def test_an_ocv_drift_inside_the_look_back_is_capped() -> None:
    t, i = _profile([(300, 0.0, 10), (1200, 1.0, 5), (900, 0.0, 5)])
    v = _voltage(t, i, noise=2e-4)
    loaded = i > 0.0
    v = v - np.where(loaded, 5e-4 * (t - 300.0), 5e-4 * 1200.0 * (t > 1500.0))
    report, cell = _run(_csv(t, i, v))
    assert report.decision is not GateDecision.CAN_CALIBRATE
    assert any("OCV may not be constant" in r for r in cell["reasons"])


def test_a_horizon_that_cannot_be_compared_is_partial_and_capped() -> None:
    # tau = 200 s, rest sampled every 60 s: the 0.25 horizon holds fewer than five rest samples.
    t, i = _profile([(300, 0.0, 10), (3000, 1.0, 10), (900, 0.0, 60)])
    report, cell = _run(_csv(t, i, _voltage(t, i, c1=200.0 / 0.03, noise=2e-4)))
    assert cell["horizon_stability"]["verdict"] == "PARTIAL"
    assert report.decision is GateDecision.WEAKLY_IDENTIFIABLE
    assert any("PARTIAL" in r for r in cell["reasons"])


def test_the_profile_interval_agrees_with_the_local_interval_on_an_exact_model() -> None:
    _, cell = _run(_well_excited())
    for name in ("R0", "R1", "C1"):
        profile = cell["profile_likelihood"]["per_parameter"][name]["relative_width_95"]
        local = cell["practical_local"]["relative_width_95"][name]
        assert profile == pytest.approx(local, rel=0.1), name


def test_a_loosened_design_cannot_buy_calibration() -> None:
    weak = IdentifiabilityDesign(horizon_fractions=(0.95,), history_factor=1e-3)
    report, cell = _run(_well_excited(), design=weak)
    assert report.decision is GateDecision.WEAKLY_IDENTIFIABLE
    assert any("non-default design" in r for r in cell["reasons"])


def test_a_sign_the_data_cannot_test_cannot_be_calibrated_on() -> None:
    # Steps of 0.08 A never reach the gate's 0.1 A clear-step threshold, so the sign is untestable from data.
    t, i = _profile([(300, 0.0, 10), (1200, 0.08, 10), (900, 0.0, 5)])
    report, cell = _run(_csv(t, i, _voltage(t, i, r0=0.5, r1=0.4, c1=40.0 / 0.4, noise=1e-4)))
    assert report.to_dict()["current_sign_retest"]["cellA/cal"]["clear_steps"] == 0
    assert report.decision is GateDecision.WEAKLY_IDENTIFIABLE
    assert any("cannot be tested from the record" in r for r in cell["reasons"])


def test_a_forged_receipt_string_cannot_verify_the_sign_or_be_duplicated() -> None:
    import dataclasses

    from engcore.domains.battery.real_data import BatteryDataset

    calibration, holdout = _well_excited(), _holdout_bytes()
    fmt = _format()
    declarations = [_declaration(calibration, "cellA/cal", "cal", fmt), _declaration(holdout, "cellA/hold", "hold", fmt)]
    dataset = ingest_dataset("test", SOURCE, declarations, {"cellA/cal": calibration, "cellA/hold": holdout},
                             declared_assumptions=("synthetic",))
    first = dataset.receipt.files[0]
    forged = dataclasses.replace(first, consistency_checks={**first.consistency_checks, "current_sign": "verified: forged"})
    doubled = dataclasses.replace(dataset.receipt, files=(first, forged, *dataset.receipt.files[1:]))
    with pytest.raises(RealDataError, match="twice"):
        BatteryDataset(doubled, dataset.series)
    foreign = dataclasses.replace(first, snapshot=dataclasses.replace(first.snapshot, source_id="another.source"))
    with pytest.raises(RealDataError, match="does not belong"):
        BatteryDataset(dataclasses.replace(dataset.receipt, files=(foreign, *dataset.receipt.files[1:])),
                       dataset.series)
    # A forged text field changes nothing the gate relies on: the sign is re-tested from the series.
    rewritten = BatteryDataset(dataclasses.replace(dataset.receipt, files=(forged, *dataset.receipt.files[1:])),
                               dataset.series)
    policy = SplitPolicy("p", SplitUnit.TEST_SEQUENCE, ("cal",), ("hold",), "test")
    a = assess_thevenin_1rc_identifiability(dataset, build_split(dataset, policy), NOISE).to_dict()
    b = assess_thevenin_1rc_identifiability(rewritten, build_split(rewritten, policy), NOISE).to_dict()
    assert a["current_sign_retest"] == b["current_sign_retest"]
    assert a["cells"] == b["cells"]


def test_a_single_loaded_sample_in_the_look_back_is_untested_not_passed() -> None:
    # The discharge is sampled every 30 s, so the 10 s look-back holds one loaded sample.
    t, i = _profile([(300, 0.0, 10), (1200, 1.0, 30), (900, 0.0, 5)])
    report, cell = _run(_csv(t, i, _voltage(t, i, noise=3e-4)))
    assert report.decision is not GateDecision.CAN_CALIBRATE
    assert any("OCV constancy over the window is untested" in r for r in cell["reasons"])


def test_polarization_left_by_an_earlier_pulse_is_capped() -> None:
    # 10 A for 300 s, a 5 s rest, then 0.5 A for 250 s: the big pulse still biases the small discharge.
    t, i = _profile([(300, 0.0, 10), (300, 10.0, 5), (5, 0.0, 1), (250, 0.5, 5), (900, 0.0, 5)])
    report, cell = _run(_csv(t, i, _voltage(t, i, noise=1e-4)))
    assert report.decision is GateDecision.WEAKLY_IDENTIFIABLE
    assert len(cell["reasons"]) == 1 and "earlier recorded current" in cell["reasons"][0]
    check = cell["initial_polarization_check"][0]
    assert check["max_prior_recorded_current_a"] == pytest.approx(10.0)
    assert check["recorded_history_factor"] > check["limit"]


def test_a_long_rest_after_the_earlier_pulse_clears_the_cap() -> None:
    # Negative control: 400 s (10 tau) of rest between the pulse and the window lets the pulse decay.
    t, i = _profile([(300, 0.0, 10), (300, 10.0, 5), (400, 0.0, 5), (250, 0.5, 5), (900, 0.0, 5)])
    report, cell = _run(_csv(t, i, _voltage(t, i, noise=1e-4)))
    check = cell["initial_polarization_check"][0]
    assert check["recorded_history_factor"] < check["limit"]
    assert not any("earlier recorded current" in r for r in cell["reasons"])


def test_polarization_from_before_the_record_is_never_assumed_zero() -> None:
    # The reviewer's counterexample: the same window, but the record starts 5 s before it with 0.3 V already
    # on the polarization branch -- the earlier 10 A pulse happened before the file began.
    t, i = _profile([(5, 0.0, 1), (250, 0.5, 5), (900, 0.0, 5)])
    report, cell = _run(_csv(t, i, _voltage(t, i, vp0=0.3, noise=1e-4)))
    assert report.decision is not GateDecision.CAN_CALIBRATE
    assert any("polarization at the record's start is unknown" in r for r in cell["reasons"])


def test_the_two_polarization_bounds_are_capped_on_their_sum() -> None:
    # Tuned so that each part alone sits below the limit and only their sum exceeds it.
    t, i = _profile([(100, 0.0, 5), (100, 2.0, 5), (40, 0.0, 5), (375, 0.5, 5), (900, 0.0, 5)])
    report, cell = _run(_csv(t, i, _voltage(t, i, noise=1e-4)))
    check = cell["initial_polarization_check"][0]
    assert check["recorded_history_factor"] <= check["limit"]
    assert check["pre_record_factor"] <= check["limit"]
    assert check["combined_factor"] > check["limit"]
    assert report.decision is GateDecision.WEAKLY_IDENTIFIABLE
    assert any("though neither does alone" in r for r in cell["reasons"])


def test_each_calibration_group_reads_its_own_clock_for_pre_record_polarization() -> None:
    # Two calibration sequences of one cell. The second restarts at t = 1e5 s and begins 5 s before its window,
    # with polarization already on the branch. Its pre-record bound must decay over ITS OWN record only.
    first = _well_excited()
    t, i = _profile([(5, 0.0, 1), (250, 0.5, 5), (900, 0.0, 5)])
    second = _csv(t + 1.0e5, i, _voltage(t, i, vp0=0.3, noise=1e-4))
    holdout = _holdout_bytes()
    fmt = _format()
    declarations = [_declaration(first, "cellA/cal1", "cal1", fmt), _declaration(second, "cellA/cal2", "cal2", fmt),
                    _declaration(holdout, "cellA/hold", "hold", fmt)]
    dataset = ingest_dataset("test", SOURCE, declarations,
                             {"cellA/cal1": first, "cellA/cal2": second, "cellA/hold": holdout},
                             declared_assumptions=("synthetic",))
    split = build_split(dataset, SplitPolicy("p", SplitUnit.TEST_SEQUENCE, ("cal1", "cal2"), ("hold",), "test"))
    report = assess_thevenin_1rc_identifiability(dataset, split, NOISE)
    cell = report.to_dict()["cells"]["cellA"]
    assert report.decision is GateDecision.WEAKLY_IDENTIFIABLE
    assert len(cell["excitation"]["relaxation_windows"]) == 2
    rows = {row["window"]: row for row in cell["initial_polarization_check"]}
    assert rows[1]["pre_record_factor"] > rows[1]["limit"]
    assert rows[0]["pre_record_factor"] < rows[0]["limit"]
    assert cell["reasons"] == [r for r in cell["reasons"] if r.startswith("window 1: polarization at the record")]
    assert len(cell["reasons"]) == 1


def test_a_record_above_five_volts_raises_the_pre_record_bound() -> None:
    # A two-cell-string-like record at about 7 V: 5 V would no longer bound its polarization. (The fit bounds
    # OCV_w to 0-10 V, a single-cell range, so a far higher record never reaches this check.)
    fmt = SourceFormat(
        format_id="test.synthetic.1rc.csv", format_version=1, description="synthetic", header=("t", "Q", "I", "U"),
        columns=_format().columns, current_sign=CurrentSign.POSITIVE_IS_DISCHARGE, current_sign_basis="test",
        voltage_window_v=(0.5, 60.0),
    )
    t, i = _profile([(300, 0.0, 10), (1200, 1.0, 10), (900, 0.0, 5)])
    v = _voltage(t, i, noise=3e-4) + 4.0
    _, cell = _run(_csv(t, i, v), fmt=fmt)
    check = cell["initial_polarization_check"][0]
    assert check["pre_record_bound_v"] == pytest.approx(float(np.max(np.abs(v))))
    assert check["pre_record_bound_v"] > 5.0


def test_declaring_more_noise_does_not_loosen_the_polarization_check() -> None:
    t, i = _profile([(300, 0.0, 10), (300, 10.0, 5), (5, 0.0, 1), (250, 0.5, 5), (900, 0.0, 5)])
    data = _csv(t, i, _voltage(t, i, noise=1e-4))
    limits = set()
    for millivolt in (1.0, 3.0, 10.0, 30.0):
        noise = VoltageNoiseDeclaration(Quantity(millivolt, "millivolt"), source="hostile", basis="inflated")
        report, cell = _run(data, noise=noise)
        assert report.decision is not GateDecision.CAN_CALIBRATE, millivolt
        check = cell["initial_polarization_check"][0]
        # The limit sits on the check scale, so declaring more noise cannot raise it; the cap stays tripped.
        limits.add(round(check["limit"], 12))
        assert check["recorded_history_factor"] > check["limit"], millivolt
    assert len(limits) == 1


def test_a_sign_the_data_contradict_is_refused() -> None:
    # The format declares the wrong sign and an ingest threshold no step reaches; the gate's own retest refuses.
    fmt = SourceFormat(
        format_id="test.synthetic.1rc.csv", format_version=1, description="synthetic", header=("t", "Q", "I", "U"),
        columns=_format().columns, current_sign=CurrentSign.POSITIVE_IS_CHARGE, current_sign_basis="wrong on purpose",
        voltage_window_v=(0.5, 5.0), sign_test_current_step_a=100.0,
    )
    report, cell = _run(_well_excited(), fmt=fmt)
    assert report.decision is GateDecision.INSUFFICIENT_DATA
    assert "contradicted by the record's passive step response" in cell["reasons"][0]


def test_a_short_discharge_history_caps_the_zero_polarization_assumption() -> None:
    # 100 s of discharge against tau = 40 s: the polarization at the interruption is not at steady state.
    t, i = _profile([(300, 0.0, 5), (100, 1.0, 5), (900, 0.0, 5)])
    report, cell = _run(_csv(t, i, _voltage(t, i, noise=2e-4)))
    assert report.decision is not GateDecision.CAN_CALIBRATE
    assert any("zero-initial-polarization" in r for r in cell["reasons"])


def test_two_time_constants_make_the_1rc_parameters_window_dependent() -> None:
    t, i = _profile([(300, 0.0, 10), (1800, 1.0, 10), (1200, 0.0, 5)])
    v = _voltage(t, i, r1=0.02, c1=10.0 / 0.02, second=(0.02, 400.0 / 0.02), noise=2e-4)
    report, cell = _run(_csv(t, i, v))
    assert report.decision is GateDecision.WEAKLY_IDENTIFIABLE
    assert report.action == "REVIEW"
    assert cell["horizon_stability"]["verdict"] == "UNSTABLE"
    assert any("window-unstable" in r for r in cell["reasons"])


# ---------------------------------------------------------------------------
# Scale and numerics
# ---------------------------------------------------------------------------

def test_normalized_sensitivity_is_invariant_under_impedance_scaling() -> None:
    t, i = _profile([(300, 0.0, 10), (1200, 1.0, 10), (900, 0.0, 5)])
    v = _voltage(t, i, noise=3e-4)
    scale = 100.0
    i_big = i * scale
    v_big = _voltage(t, i_big, r0=0.02 / scale, r1=0.03 / scale, c1=(40.0 / 0.03) * scale, noise=3e-4)
    assert np.allclose(v, v_big, atol=1e-12)
    a_report, a = _run(_csv(t, i, v))
    b_report, b = _run(_csv(t, i_big, v_big))
    assert a_report.decision is b_report.decision is GateDecision.CAN_CALIBRATE
    assert np.allclose(a["practical_local"]["projected_singular_values"],
                       b["practical_local"]["projected_singular_values"], rtol=1e-5)
    assert np.allclose(a["practical_local"]["correlation"], b["practical_local"]["correlation"], atol=1e-5)
    for name in ("R0", "R1", "C1", "R1*C1"):
        assert a["practical_local"]["relative_width_95"][name] == pytest.approx(
            b["practical_local"]["relative_width_95"][name], rel=1e-5)


def test_a_unit_restatement_of_the_source_does_not_move_the_gate() -> None:
    t, i = _profile([(300, 0.0, 10), (1200, 1.0, 10), (900, 0.0, 5)])
    v = _voltage(t, i, noise=3e-4)
    a_report, a = _run(_csv(t, i, v))
    b_report, b = _run(_csv(t, i, v, current_scale=1000.0, voltage_scale=1000.0),
                       fmt=_format("milliampere", "millivolt"))
    assert a_report.decision is b_report.decision
    assert np.allclose(a["practical_local"]["projected_singular_values"],
                       b["practical_local"]["projected_singular_values"], rtol=1e-6)


def test_a_perturbation_dominated_by_rounding_is_numerically_unresolved() -> None:
    report, cell = _run(_well_excited(), design=IdentifiabilityDesign(fd_relative_step=1e-14))
    assert report.decision is GateDecision.NUMERICALLY_UNRESOLVED
    assert cell["finite_difference_check"]["below_resolution"]
    assert "rounding" in cell["reasons"][0]


def test_a_perturbation_dominated_by_truncation_is_numerically_unresolved() -> None:
    report, cell = _run(_well_excited(), design=IdentifiabilityDesign(fd_relative_step=0.5))
    assert report.decision is GateDecision.NUMERICALLY_UNRESOLVED
    assert cell["finite_difference_check"]["max_relative_disagreement"] > 1e-4


# ---------------------------------------------------------------------------
# Authority and the holdout
# ---------------------------------------------------------------------------

def test_the_gate_never_reads_the_holdout() -> None:
    calibration = _well_excited()
    t, i = _profile([(100, 0.0, 10), (100, 3.0, 10), (100, 0.0, 10)])
    other_holdout = _csv(t, i, _voltage(t, i, r0=0.2, noise=1e-3, seed=5))
    a_report, a = _run(calibration)
    b_report, b = _run(calibration, holdout=other_holdout)
    assert a == b
    assert a_report.to_dict()["holdout_groups_not_read"] == ["cellA/hold"]


def test_the_gate_grants_no_authority_and_builds_no_parameter_record() -> None:
    report, _ = _run(_well_excited())
    record = report.to_dict()
    assert "not a calibration" in record["authority"] and "grants no ValidationLevel" in record["authority"]
    source = inspect.getsource(gate_module)
    assert "Thevenin1RCParameters(" not in source
    assert "ValidationLevel" not in source.replace("grants no ValidationLevel", "")
    assert record["decision"] in {d.value for d in GateDecision}


def test_the_gate_record_is_deterministic() -> None:
    first, _ = _run(_well_excited())
    second, _ = _run(_well_excited())
    assert first.digest == second.digest


def test_decision_actions_are_exactly_calibrate_review_or_refuse() -> None:
    assert GateDecision.CAN_CALIBRATE.action == "CAN_CALIBRATE"
    assert GateDecision.WEAKLY_IDENTIFIABLE.action == "REVIEW"
    for decision in (GateDecision.NON_IDENTIFIABLE, GateDecision.INSUFFICIENT_EXCITATION,
                     GateDecision.INSUFFICIENT_DATA, GateDecision.NUMERICALLY_UNRESOLVED):
        assert decision.action == "REFUSE"
    assert math.isfinite(gate_module.CHI2_95_1DOF)
