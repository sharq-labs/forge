"""Battery 1RC closure pins: identities, the forward model against the FORGE route, and hostile data cases."""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib

import numpy as np
import pytest

from benchmarks.battery_1rc_closure import data as bdata
from benchmarks.battery_1rc_closure import fit as bfit
from benchmarks.battery_1rc_closure import prereg as bprereg
from engcore.domains.battery import context as ctx
from engcore.domains.battery import thevenin_route as tr
from engcore.domains.battery.cell import CellSpecification
from engcore.domains.battery.thevenin import Thevenin1RCParameters
from engcore.scientific.models.curves import DeclaredCurve, TabulatedForm
from engcore.scientific.units.quantity import Quantity as Q

HERE = pathlib.Path(bprereg.__file__).resolve().parent


def test_both_preregistrations_are_pinned_and_v2_amends_v1():
    for name in ("PREREGISTRATION.json", "PREREGISTRATION_v2.json"):
        raw = (HERE / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == (HERE / name).with_suffix(".sha256").read_bytes().split()[0].decode()
    assert hashlib.sha256((HERE / "PREREGISTRATION.json").read_bytes()).hexdigest() == bprereg.V1_SHA256
    assert bprereg.canonical(bprereg.PREREG) == (HERE / "PREREGISTRATION_v2.json").read_bytes()
    assert json.loads((HERE / "PREREGISTRATION_v2.json").read_bytes())["amends"]["preregistration_sha256"] == bprereg.V1_SHA256


def test_the_calibration_trajectories_are_pinned_to_this_preregistration():
    doc = bdata.load("calibration")
    assert doc["role"] == "calibration" and doc["refused"] == [] and len(doc["cycles"]) == 38
    assert {c["cell"] for c in doc["cycles"]} == {"B0005", "B0007"}
    assert all(2 <= c["ordinal"] <= 20 for c in doc["cycles"])


def _route_terminal_voltages(cycle: bfit.Cycle, ocv, r0, r1, c1):
    cell = CellSpecification(
        cell_id=cycle.cell, nominal_capacity=Q(cycle.q_as / 3600.0, "ampere_hour"), internal_resistance=Q(r0, "ohm"),
        coulombic_efficiency=Q(1.0, "dimensionless"),
        open_circuit_voltage_curve=DeclaredCurve(quantity=ctx.OCV_CURVE, against=ctx.STATE_OF_CHARGE,
                                                 against_unit="dimensionless", unit="volt", lower=0.0, upper=1.0,
                                                 form=TabulatedForm(tuple(zip(bfit.KNOTS.tolist(), ocv)))))
    ps = tr.Thevenin1RCParameterSet("pin", cell, Thevenin1RCParameters(Q(r1, "ohm"), Q(c1, "farad")),
                                    Q(-40.0, "degC"), Q(80.0, "degC"), Q(10.0, "ampere"), "test transcription pin")
    segments = tuple(tr.ProfileSegment(Q(float(cycle.t[k] - cycle.t[k - 1]), "second"), Q(float(cycle.i[k]), "ampere"),
                                       Q(float(cycle.temp[k]), "degC")) for k in range(1, len(cycle.t)))
    run = tr.run_thevenin_1rc(ps, tr.Thevenin1RCInitialState(Q(1.0, "dimensionless"), Q(0.0, "volt"), "prereg"),
                              tr.DischargeRestProfile(f"{cycle.cell}-{cycle.ordinal}", segments, tr.POSITIVE_DISCHARGE))
    return np.array([p.terminal_voltage_v for p in run.trajectory])


def test_the_fitting_transcription_equals_the_forge_route_on_real_cycles():
    cycles = [bfit.Cycle(c) for c in bdata.load("calibration")["cycles"][:3]]
    ocv = list(3.0 + 1.2 * bfit.KNOTS ** 0.5)
    for c in cycles:
        fast = bfit.predict(c, np.array(ocv), 0.08, 0.03, 900.0)
        route = _route_terminal_voltages(c, ocv, 0.08, 0.03, 900.0)
        assert np.max(np.abs(fast - route)) < 1e-12


# ---- hostile data cases ----------------------------------------------------------------------------------------------
def _cycle(**over):
    base = {"cycle_index": 1, "ambient_temperature_degC": 24.0,
            "channels": {"Time": [0.0, 10.0, 20.0, 30.0], "Voltage_measured": [4.19, 3.95, 3.90, 3.98],
                         "Current_measured": [-0.001, -2.0, -2.0, 0.002], "Temperature_measured": [24.0] * 4}}
    for key, value in over.items():
        base["channels"][key] = value
    return base


def test_a_well_formed_cycle_builds_with_the_declared_sign_conversion():
    built = bdata.build_cycle(_cycle(), capacity_basis_ah=1.8)
    assert built["current_A"] == [0.0, 2.0, 2.0, 0.0]


@pytest.mark.parametrize("over, match", [
    ({"Current_measured": [-0.001, 2.0, 2.0, 0.0]}, "charge-direction"),          # wrong sign convention in the record
    ({"Voltage_measured": [4.19, 4.25, 4.30, 4.2]}, "sign check"),                 # voltage rose under 'discharge'
    ({"Voltage_measured": [4.05, 3.95, 3.9, 3.98]}, "full-charge screen"),         # not fully charged
    ({"Time": [0.0, 10.0, 10.0, 30.0]}, "strictly increasing"),                    # malformed time
    ({"Current_measured": [-0.5, -2.0, -2.0, 0.0]}, "does not start at rest"),     # missing initial-state evidence
])
def test_malformed_or_misleading_cycles_are_refused_not_repaired(over, match):
    with pytest.raises(bdata.CycleRefused, match=match):
        bdata.build_cycle(_cycle(**over), capacity_basis_ah=1.8)


def test_a_record_that_delivers_more_than_its_capacity_basis_is_refused_not_clipped():
    with pytest.raises(bdata.CycleRefused, match="SOC would leave"):
        bdata.build_cycle(_cycle(), capacity_basis_ah=0.005)


def test_a_changed_trajectory_file_is_refused(tmp_path, monkeypatch):
    for name in ("calibration.json", "calibration.sha256"):
        (tmp_path / name).write_bytes((bdata.DATA_DIR / name).read_bytes())
    raw = bytearray((tmp_path / "calibration.json").read_bytes())
    raw[200] = ord("9") if raw[200] != ord("9") else ord("8")
    (tmp_path / "calibration.json").write_bytes(bytes(raw))
    monkeypatch.setattr(bdata, "DATA_DIR", tmp_path)
    with pytest.raises(ValueError, match="pinned digest"):
        bdata.load("calibration")
