"""Audit CAP-02: a declared pulse is screened, not merely admitted.

Before this fix a declared ``pulse_current`` entered the Rint model's validity
claim through the pulse-rating conditions and was then never simulated or
screened: the terminal voltage was evaluated only at the continuous current,
polarization only over the continuous step, and the constant-current runtime
model -- whose record excludes "a varying load" -- stayed IN_DOMAIN beside a
declared 25 A pulse on a 1.5 A load. At the pulse the Rint terminal voltage
was 2.646 V against a 3.0 V cutoff, and the pulse was one polarization time
constant long, mid-slew (unmodelled fraction 0.368 against a 0.05 ceiling).

Now:
* the Rint model evaluates polarization at ``pulse_duration`` (a screen: the
  model reports no value at the pulse, so a slewing pulse leaves its claim
  UNKNOWN) and the terminal-voltage admissibility at ``pulse_current``;
* the constant-current runtime model is OUTSIDE when the declared pulse
  reaches the voltage cutoff at a higher state of charge than the cutoff its
  runtime is computed to.
"""

from __future__ import annotations

import copy
import math

import pytest

from engcore.domains.battery import context as bctx
from engcore.mcp.battery import example_battery_payload
from engcore.mcp.server import run_battery
from engcore.scientific.units.quantity import Quantity as Q

RINT = "battery.cell.rint_ocv"
RUNTIME = "battery.cell.constant_current_runtime"


def _validity(out):
    return {v["model_id"]: v["assessment"] for v in out["report"]["validity"]}


def _s6_case(**load):
    case = copy.deepcopy(example_battery_payload())
    case["load"]["state_of_charge"] = "0.35 dimensionless"
    case["load"]["pulse_current"] = "25 ampere"      # 10C on 2.5 Ah == the pulse rating
    case["load"]["pulse_duration"] = "20 second"     # == tau_pol: mid-slew
    case["cell"]["limits"]["pulse_discharge_c_rate"] = "10 1/hour"
    case["cell"]["limits"]["rated_pulse_duration"] = "30 second"
    case["cell"]["limits"]["polarization_time_constant"] = "20 second"
    case["march"]["steps"] = 2
    case["load"].update(load)
    return case


def test_the_reviewer_pulse_is_no_longer_in_domain_on_rint_or_runtime() -> None:
    out = run_battery(_s6_case())
    validity = _validity(out)
    assert validity[RINT]["status"] != "in_domain"
    assert bctx.PULSE_POLARIZATION_UNMODELLED_FRACTION in validity[RINT]["unknown"]
    assert bctx.PULSE_POLARIZATION_UNMODELLED_FRACTION not in validity[RINT]["satisfied"]
    assert validity[RUNTIME]["status"] == "outside_validated_domain"
    assert bctx.PULSE_CUTOFF_STATE_OF_CHARGE_SHIFT in validity[RUNTIME]["violated"]
    assert out["verdict"]["value"] == "not_supported"


def test_a_short_undeveloped_pulse_passes_the_pulse_polarization_condition() -> None:
    # 1 s against tau 20 s: f = 1 - exp(-0.05) = 0.0488 <= 0.05.
    out = run_battery(_s6_case(pulse_duration="1 second"))
    validity = _validity(out)
    assert bctx.PULSE_POLARIZATION_UNMODELLED_FRACTION in validity[RINT]["satisfied"]


def test_the_pulse_polarization_reads_pulse_duration_not_the_step() -> None:
    derived = bctx.derived_cell_quantities(
        {
            bctx.NOMINAL_CAPACITY: Q(2.5, "ampere_hour"),
            bctx.INTERNAL_RESISTANCE: Q(0.03, "ohm"),
            bctx.OCV_AT_EMPTY: Q(3.0, "volt"),
            bctx.OCV_AT_FULL: Q(4.2, "volt"),
            bctx.DURATION: Q(600.0, "second"),
            bctx.COULOMBIC_EFFICIENCY: Q(0.99, "dimensionless"),
            bctx.POLARIZATION_TIME_CONSTANT: Q(20.0, "second"),
            bctx.PULSE_CURRENT: Q(25.0, "ampere"),
            bctx.PULSE_DURATION: Q(20.0, "second"),
        },
        state_of_charge=Q(0.35, "dimensionless"),
        discharge_current=Q(1.5, "ampere"),
        cell_temperature=Q(298.15, "kelvin"),
    )
    developed = 1.0 - math.exp(-1.0)
    assert derived[bctx.PULSE_POLARIZATION_UNMODELLED_FRACTION].magnitude == pytest.approx(
        min(developed, 1.0 - developed)
    )
    # The continuous step is 30 tau long and settled; the pulse is not.
    assert derived[bctx.POLARIZATION_UNMODELLED_FRACTION].magnitude < 0.05
    # Terminal voltage at the pulse, at the end-of-interval state of charge.
    final_soc = derived[bctx.FINAL_STATE_OF_CHARGE].magnitude
    ocv = 3.0 + 1.2 * final_soc
    assert derived[bctx.PULSE_TERMINAL_VOLTAGE_RATIO].magnitude == pytest.approx(
        (ocv - 25.0 * 0.03) / ocv
    )
    # No cutoff declared in this mapping: the pulse's shift cannot be asked.
    assert bctx.PULSE_CUTOFF_STATE_OF_CHARGE_SHIFT not in derived


def test_a_pulse_driving_the_rint_terminal_voltage_negative_is_outside() -> None:
    # 200 A * 0.03 ohm = 6 V, more than any OCV on the chord.
    out = run_battery(_s6_case(pulse_current="200 ampere", pulse_duration="1 second"))
    validity = _validity(out)
    assert bctx.PULSE_TERMINAL_VOLTAGE_RATIO in validity[RINT]["violated"]


def test_without_a_declared_pulse_the_runtime_departure_is_zero_and_satisfied() -> None:
    case = copy.deepcopy(example_battery_payload())
    case["load"].pop("pulse_current", None)
    case["load"].pop("pulse_duration", None)
    out = run_battery(case)
    validity = _validity(out)
    assert bctx.PULSE_CUTOFF_STATE_OF_CHARGE_SHIFT in validity[RUNTIME]["satisfied"]
    # And the pulse screens on Rint are unanswered, never satisfied, without a pulse.
    assert bctx.PULSE_POLARIZATION_UNMODELLED_FRACTION in validity[RINT]["unknown"]
    assert bctx.PULSE_TERMINAL_VOLTAGE_RATIO in validity[RINT]["unknown"]


def test_a_pulse_equal_to_the_continuous_current_does_not_move_the_cutoff() -> None:
    out = run_battery(_s6_case(pulse_current="1.5 ampere", pulse_duration="1 second"))
    validity = _validity(out)
    assert bctx.PULSE_CUTOFF_STATE_OF_CHARGE_SHIFT in validity[RUNTIME]["satisfied"]


def test_the_reviewer_shift_is_the_voltage_inversion_at_the_pulse() -> None:
    # z_cut(25 A) = (3.0 + 0.75 - 3.0) / 1.2 = 0.625; z_stop(1.5 A) = max(0.15, 0.0375).
    base = {
        bctx.INTERNAL_RESISTANCE: Q(0.03, "ohm"),
        bctx.OCV_AT_EMPTY: Q(3.0, "volt"),
        bctx.OCV_AT_FULL: Q(4.2, "volt"),
        bctx.CUTOFF_VOLTAGE: Q(3.0, "volt"),
        bctx.CUTOFF_STATE_OF_CHARGE: Q(0.15, "dimensionless"),
        bctx.PULSE_CURRENT: Q(25.0, "ampere"),
    }
    derived = bctx.derived_cell_quantities(base, discharge_current=Q(1.5, "ampere"))
    assert derived[bctx.PULSE_CUTOFF_STATE_OF_CHARGE_SHIFT].magnitude == pytest.approx(0.475)


def test_a_pulse_without_a_voltage_cutoff_leaves_the_shift_unanswered() -> None:
    case = _s6_case()
    case["load"].pop("cutoff_voltage")
    out = run_battery(case)
    validity = _validity(out)
    assert bctx.PULSE_CUTOFF_STATE_OF_CHARGE_SHIFT in validity[RUNTIME]["unknown"]
