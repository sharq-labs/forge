"""Battery cell relationships against Plett's statements and limiting cases.

Battery coverage was WEAK -- two relationships of roughly twenty-five. This
adds the ones with a citable form or a derivable limit, and separates what kind
of claim each is:

    PHYSICAL_EQUATION   charge conservation, Joule heating, Ohm's law
    EMPIRICAL_MODEL     Peukert, the affine OCV chord
    APPROXIMATION       Rint (no diffusion, no polarisation dynamics)
    INTERNAL_POLICY     the declared windows a caller supplies

It also reproduces, from the payloads alone, the conclusion the previous round
reached about the 11 battery false rejects -- so that conclusion stops being a
paragraph in a report and becomes something that fails if it stops being true.
"""

from __future__ import annotations

import json
import math
import pathlib

import pytest

from engcore.domains.battery import context as battery
from engcore.mcp.battery import run_battery_case
from engcore.scientific.units.quantity import Quantity

from .oracle_ids import oracle

ORACLE_ID = "ORA-BATTERY-COULOMB"

CASES = pathlib.Path("benchmarks/hard/cases_battery")

#: The 11 cases the battery benchmark scores as false rejects.
FALSE_REJECTS = [
    "B00020", "B00066", "B00106", "B00149", "B00160", "B00184",
    "B00197", "B00305", "B00311", "B00327", "B00393",
]


def q(value, units):
    return Quantity(value, units)


def number(text):
    return float(text.split()[0])


# =====================================================================
# PHYSICAL_EQUATION -- charge conservation
# =====================================================================

@pytest.mark.parametrize(
    "z0,current,duration,eta,capacity_ah",
    [
        (0.9, 1.5, 600.0, 0.99, 2.5),
        (1.0, 0.5, 3600.0, 1.0, 2.0),
        (0.5, 3.0, 120.0, 0.95, 5.0),
    ],
)
def test_coulomb_counting_is_charge_removed_over_charge_stored(
    z0, current, duration, eta, capacity_ah
):
    """SoC(t) = SoC_0 - I t / (eta Q). Plett BMS Vol. I, Ch. 2.

    Efficiency DIVIDES on discharge: a cell that returns only eta of the charge
    put into it must give up more than I t of stored charge to deliver I t at
    the terminals, so the depletion is the larger number. Forge states that
    direction explicitly and this pins it.
    """
    assert oracle(ORACLE_ID).executable
    expected = z0 - current * duration / (eta * capacity_ah * 3600.0)
    got = battery.final_state_of_charge(
        initial_state_of_charge=q(z0, "dimensionless"),
        current=q(current, "ampere"),
        duration=q(duration, "second"),
        coulombic_efficiency=q(eta, "dimensionless"),
        nominal_capacity=q(capacity_ah, "ampere_hour"),
    )
    assert got.magnitude_in("dimensionless") == pytest.approx(expected, rel=1e-13)


def test_a_perfect_cell_depletes_exactly_the_charge_it_delivers():
    """eta = 1 is the limit where the two conventions coincide.

    A test that only ever ran at eta = 1 could not tell multiplication from
    division; this one exists to say that the case above, at eta < 1, is the
    one carrying the claim.
    """
    perfect = battery.final_state_of_charge(
        initial_state_of_charge=q(1.0, "dimensionless"),
        current=q(1.0, "ampere"), duration=q(3600.0, "second"),
        coulombic_efficiency=q(1.0, "dimensionless"),
        nominal_capacity=q(2.0, "ampere_hour"),
    ).magnitude_in("dimensionless")
    assert perfect == pytest.approx(0.5, rel=1e-14)

    lossy = battery.final_state_of_charge(
        initial_state_of_charge=q(1.0, "dimensionless"),
        current=q(1.0, "ampere"), duration=q(3600.0, "second"),
        coulombic_efficiency=q(0.5, "dimensionless"),
        nominal_capacity=q(2.0, "ampere_hour"),
    ).magnitude_in("dimensionless")
    assert lossy < perfect, "a lossier cell must deplete MORE, not less"
    assert lossy == pytest.approx(0.0, abs=1e-14)


def test_zero_current_leaves_the_state_of_charge_where_it_started():
    """The no-forcing limit. Charge conservation with nothing flowing."""
    for z0 in (0.0, 0.35, 1.0):
        got = battery.final_state_of_charge(
            initial_state_of_charge=q(z0, "dimensionless"),
            current=q(0.0, "ampere"), duration=q(1e6, "second"),
            coulombic_efficiency=q(0.97, "dimensionless"),
            nominal_capacity=q(3.0, "ampere_hour"),
        )
        assert got.magnitude_in("dimensionless") == pytest.approx(z0, abs=1e-15)


@pytest.mark.parametrize("current,capacity", [(1.0, 1.0), (3.0, 1.5), (0.25, 5.0)])
def test_c_rate_is_current_over_nominal_capacity(current, capacity):
    """C-rate = I/Q_nom, carrying units of inverse time. Plett Ch. 2."""
    got = battery.c_rate(
        current=q(current, "ampere"), nominal_capacity=q(capacity, "ampere_hour")
    )
    assert got.magnitude_in("1/hour") == pytest.approx(current / capacity, rel=1e-13)


# =====================================================================
# APPROXIMATION -- the Rint model's algebra
# =====================================================================

@pytest.mark.parametrize("current,resistance", [(0.0, 0.05), (2.0, 0.03), (-1.0, 0.1)])
def test_terminal_voltage_is_ocv_less_the_ohmic_drop(current, resistance):
    """V = OCV - I R. Ohm's law on the Rint equivalent circuit.

    At I = 0 the terminal voltage must equal the OCV exactly -- that is what
    'open circuit' means, and it is the limit that fixes the sign.
    """
    ocv = q(3.9, "volt")
    got = battery.terminal_voltage(
        open_circuit=ocv, current=q(current, "ampere"),
        internal_resistance=q(resistance, "ohm"),
    )
    assert got.magnitude_in("volt") == pytest.approx(
        3.9 - current * resistance, rel=1e-14
    )
    if current == 0.0:
        assert got.magnitude_in("volt") == pytest.approx(3.9, abs=1e-15)


def test_a_zero_resistance_cell_is_refused_rather_than_answered():
    """R -> 0 is a limit the Rint model declines to take, and that is right.

    The limit is mathematically clean -- with no internal resistance the
    terminal voltage is the OCV at every current -- but `internal_resistance`
    carries a declared `> 0` bound, because a cell with no internal resistance
    is not a cell the Rint model describes: R is the only loss it has, and at
    zero the model has nothing left to say that the OCV curve does not already
    say. Forge refuses instead of returning the degenerate answer, and this
    pins the refusal so a future change cannot quietly start answering.

    The same shape as `alpha > 0` in conduction-1D: a bound that removes a
    model's entire content is enforced rather than evaluated.
    """
    from engcore.scientific.errors import InvalidScientificProblem

    with pytest.raises(InvalidScientificProblem, match="strictly positive"):
        battery.terminal_voltage(
            open_circuit=q(4.0, "volt"), current=q(1.0, "ampere"),
            internal_resistance=q(0.0, "ohm"),
        )

    # Approaching the limit from above is answered, and approaches the OCV.
    approaching = [
        battery.terminal_voltage(
            open_circuit=q(4.0, "volt"), current=q(1.0, "ampere"),
            internal_resistance=q(r, "ohm"),
        ).magnitude_in("volt")
        for r in (1e-3, 1e-6, 1e-9)
    ]
    assert approaching == sorted(approaching)
    assert approaching[-1] == pytest.approx(4.0, abs=1e-8)


@pytest.mark.parametrize("z", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_the_affine_ocv_chord_hits_both_declared_endpoints(z):
    """OCV(z) = V_empty + z (V_full - V_empty).

    An EMPIRICAL_MODEL, and a crude one -- Plett Ch. 3 treats OCV as tabulated
    data precisely because the real curve has a knee near empty and a plateau
    near full. What is checked here is the chord's algebra and that it is
    exact at the two points the caller declared.
    """
    got = battery.open_circuit_voltage(
        state_of_charge=q(z, "dimensionless"),
        ocv_at_empty=q(3.0, "volt"), ocv_at_full=q(4.2, "volt"),
    ).magnitude_in("volt")
    assert got == pytest.approx(3.0 + z * (4.2 - 3.0), rel=1e-14)
    if z == 0.0:
        assert got == pytest.approx(3.0, abs=1e-15)
    if z == 1.0:
        assert got == pytest.approx(4.2, abs=1e-15)


def test_self_heating_rise_is_the_heat_over_the_conductance():
    """dT = Q/(hA), the steady lumped rise. Same relation the thermal domain
    uses, reached here from the battery side."""
    got = battery.self_heating_rise(
        heat=q(2.0, "watt"), thermal_conductance=q(0.4, "watt/kelvin")
    )
    assert got.magnitude_in("kelvin") == pytest.approx(5.0, rel=1e-14)


# =====================================================================
# The definitions the 11 false rejects turn on
# =====================================================================

def test_soc_window_margin_is_the_closer_approach_to_either_wall():
    """min(z_min - w_lo, w_hi - z_max) / (w_hi - w_lo).

    Normalised by the window width, so it is the FRACTION of the window still
    in hand -- negative exactly when the trajectory leaves it.
    """
    got = battery.soc_window_margin(
        initial_state_of_charge=q(0.90, "dimensionless"),
        final_soc=q(0.80, "dimensionless"),
        window_minimum=q(0.70, "dimensionless"),
        window_maximum=q(0.95, "dimensionless"),
    ).magnitude_in("dimensionless")
    assert got == pytest.approx(min(0.80 - 0.70, 0.95 - 0.90) / 0.25, rel=1e-13)


def test_a_trajectory_leaving_the_window_gives_a_negative_margin():
    """The sign is the whole content of the condition."""
    got = battery.soc_window_margin(
        initial_state_of_charge=q(0.90, "dimensionless"),
        final_soc=q(0.69, "dimensionless"),
        window_minimum=q(0.70, "dimensionless"),
        window_maximum=q(0.95, "dimensionless"),
    ).magnitude_in("dimensionless")
    assert got < 0.0


def test_soc_step_resolution_ratio_is_the_excursion_over_the_step():
    """|z_0 - z_end| / declared step. Above 1 means one step outran the
    resolution the caller said a step may have."""
    got = battery.soc_step_resolution_ratio(
        initial_state_of_charge=q(0.9, "dimensionless"),
        final_soc=q(0.8, "dimensionless"),
        resolution=q(0.05, "dimensionless"),
    ).magnitude_in("dimensionless")
    assert got == pytest.approx(0.1 / 0.05, rel=1e-14)


# =====================================================================
# ORA-BATTERY-COULOMB applied to the 11 false rejects
# =====================================================================

def _independent_final_soc(payload):
    """Coulomb counting from the payload, under Forge's DECLARED contract.

    `load.duration` is the STEP duration and `march.steps` is the number of
    intervals, so the discharge lasts their product. Forge's MCP boundary
    states this twice and warns about the misreading. Nothing here reads a
    Forge-computed value.
    """
    cell, load = payload["cell"], payload["load"]
    steps = payload.get("march", {}).get("steps", 1)
    capacity_as = number(cell["nominal_capacity"]) * 3600.0
    eta = number(cell.get("coulombic_efficiency", "1 dimensionless"))
    total_seconds = number(load["duration"]) * steps
    return number(load["state_of_charge"]) - (
        number(load["discharge_current"]) * total_seconds / (eta * capacity_as)
    )


@pytest.mark.parametrize("case_id", FALSE_REJECTS)
def test_every_battery_false_reject_is_a_truth_defect_not_a_runtime_one(case_id):
    """The previous round's conclusion, re-derived here rather than quoted.

    For each of the 11: coulomb counting done in this file, under the contract
    Forge's boundary declares, reproduces Forge's reported final state of
    charge. The truth says these cases are SUPPORTED; the condition their own
    payload places them against is violated at that state of charge. Forge is
    right and the answer key is wrong.

    If a future change makes Forge disagree with an independent coulomb count,
    this fails -- which is the point of writing it down as a test.
    """
    case = json.loads((CASES / f"{case_id}.json").read_text(encoding="utf-8"))
    payload = case["payload"]
    assert case["ground_truth"]["expected_verdict"] == "SUPPORTED"

    expected_z = _independent_final_soc(payload)
    report = run_battery_case(payload, run_id=case_id).report
    forge_z = report.values["final_state_of_charge"].magnitude_in("dimensionless")

    assert forge_z == pytest.approx(expected_z, rel=1e-12), (
        f"{case_id}: independent coulomb count {expected_z!r} vs Forge "
        f"{forge_z!r} -- if these disagree the root cause is NOT the generator"
    )

    # ...and at that state of charge the declared condition really is broken.
    limits = payload["cell"]["limits"]
    z0 = number(payload["load"]["state_of_charge"])
    defect = case["ground_truth"]["defect"]
    if defect.startswith("soc_window_margin"):
        w_lo = number(limits["usable_soc_minimum"])
        w_hi = number(limits["usable_soc_maximum"])
        margin = min(expected_z - w_lo, w_hi - z0) / (w_hi - w_lo)
        assert margin < 0.0, f"{case_id}: margin {margin!r} is not negative"
    else:
        ratio = abs(z0 - expected_z) / number(limits["soc_step_resolution"])
        assert ratio > 1.0, f"{case_id}: ratio {ratio!r} does not exceed 1"


def test_the_generators_reading_of_duration_is_what_produced_the_11():
    """Name the root cause concretely, on one case, so it cannot be mislaid.

    Reading `load.duration` as the total horizon instead of the step duration
    changes the depletion by exactly the step count -- and moves the case from
    outside its bound to inside it, which is how the answer key came to say
    SUPPORTED.
    """
    case = json.loads((CASES / "B00106.json").read_text(encoding="utf-8"))
    payload = case["payload"]
    steps = payload["march"]["steps"]

    contract_z = _independent_final_soc(payload)
    misread_payload = json.loads(json.dumps(payload))
    misread_payload["march"]["steps"] = 1
    misread_z = _independent_final_soc(misread_payload)

    z0 = number(payload["load"]["state_of_charge"])
    assert (z0 - contract_z) == pytest.approx(steps * (z0 - misread_z), rel=1e-12)

    limits = payload["cell"]["limits"]
    w_lo = number(limits["usable_soc_minimum"])
    w_hi = number(limits["usable_soc_maximum"])
    contract_margin = min(contract_z - w_lo, w_hi - z0) / (w_hi - w_lo)
    misread_margin = min(misread_z - w_lo, w_hi - z0) / (w_hi - w_lo)

    assert contract_margin < 0.0 < misread_margin, (
        "the two readings must land on opposite sides of the bound, or this "
        "is not the root cause"
    )
