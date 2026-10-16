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


# ---- result records: pinned, bound to the preregistration, and honest about what they show ---------------------------
RESULTS = HERE / "results"


def _pinned(name):
    raw = (RESULTS / f"{name}.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (RESULTS / f"{name}.sha256").read_bytes().split()[0].decode()
    return json.loads(raw)


def test_every_result_record_is_pinned_and_bound_to_preregistration_v2():
    v2 = hashlib.sha256((HERE / "PREREGISTRATION_v2.json").read_bytes()).hexdigest()
    cal, val = _pinned("CALIBRATION"), _pinned("VALIDATION")
    unc = _pinned("UNCERTAINTY_REPORT")
    assert cal["preregistration_sha256"] == val["preregistration_sha256"] == v2
    assert val["calibration_sha256"] == unc["calibration_sha256"] == (RESULTS / "CALIBRATION.sha256").read_bytes().split()[0].decode()


def test_no_held_out_cycle_leaks_into_calibration():
    cal = {(c["cell"], c["ordinal"]) for c in bdata.load("calibration")["cycles"]}
    within = {(c["cell"], c["ordinal"]) for c in bdata.load("within_cell_holdout")["cycles"]}
    cross = {(c["cell"], c["ordinal"]) for c in bdata.load("cross_cell_validation")["cycles"]}
    assert not cal & within and not cal & cross and not within & cross
    assert {cell for cell, _ in cross}.isdisjoint({cell for cell, _ in cal})
    assert max(o for _, o in cal) < min(o for _, o in within)          # temporal holdout lies strictly later


def test_the_identifiability_result_is_a_refusal_not_a_quiet_pass():
    ident = _pinned("CALIBRATION")["identifiability"]
    assert ident["decision"] == "NOT_IDENTIFIABLE" and ident["calibration_gate"] == "NOT_PASSED"
    assert not ident["per_parameter"]["C1"]["identified"] and not ident["per_parameter"]["tau"]["identified"]


def test_the_profile_rule_refuses_a_flat_profile_and_accepts_a_rising_one():
    flat = [{"factor": f, "sse_ratio": 1.0 + 0.02 * abs(f - 1)} for f in (1 / 3, 1 / 2, 2, 3)]
    rising = [{"factor": f, "sse_ratio": 1.0 + 0.5 * abs(f - 1)} for f in (1 / 3, 1 / 2, 2, 3)]
    one_sided = [{"factor": f, "sse_ratio": 1.5 if f > 1 else 1.01} for f in (1 / 3, 1 / 2, 2, 3)]
    assert not bfit.profile_identified(flat) and bfit.profile_identified(rising)
    assert not bfit.profile_identified(one_sided)


def test_multistart_catches_a_start_that_converges_to_the_wrong_basin():
    starts = _pinned("CALIBRATION")["models"]["1rc"]["starts"]
    best = min(s["sse"] for s in starts)
    assert max(s["sse"] for s in starts) > 1.2 * best              # a start ended in the R1 -> 0 (Rint-like) basin
    assert _pinned("CALIBRATION")["models"]["1rc"]["sse_V2"] == best


def test_rint_outperforming_1rc_would_be_reported_as_such():
    from benchmarks.battery_1rc_closure.evaluate import comparison_verdict, paired_bootstrap
    small = [np.full(50, 0.01) + 0.001 * k for k in range(8)]
    large = [np.full(50, 0.03) + 0.001 * k for k in range(8)]
    out = paired_bootstrap(small, large, b=400)                    # Rint residuals smaller
    assert out["ci95_mV"][1] < 0 and comparison_verdict(out["ci95_mV"]) == "RINT_BETTER"
    assert comparison_verdict([-1.0, 1.0]) == "NOT_DISTINGUISHED"


def test_validation_claims_stay_inside_what_the_evidence_shows():
    val = _pinned("VALIDATION")
    assert "NOT a validation of parameter values" in val["claim_scope"]
    cross = val["roles"]["cross_cell_validation"]
    assert cross["1rc"]["acceptance"] == cross["rint"]["acceptance"] == "FAIL"
    unc = _pinned("UNCERTAINTY_REPORT")["components"]
    assert unc["measurement"]["status"] == "UNKNOWN" and unc["parameter"]["status"] == "NOT_ADMISSIBLE"
    for role in ("within_cell_holdout", "cross_cell_validation"):
        assert val["roles"][role]["parameter_uncertainty_1rc"]["coverage_of_measurements"] < 0.5   # no false precision


def test_the_ledger_does_not_promote_what_the_evidence_does_not_support():
    ledger = json.loads((HERE.parents[1] / "docs/project/scientific_capability_completion.json").read_bytes())
    gates = next(c for c in ledger["capabilities"] if c["id"] == "battery.thevenin_1rc")["gates"]
    # calibration PASSES since the LG HG2 identifiability experiment (benchmarks/battery_1rc_identifiability); the NASA
    # evidence alone never supported it, and these gates still have no supporting evidence:
    # measurement_uq PASSES since the owner admitted the LG HG2 Type B accuracy (2026-10-15); NASA stays UNKNOWN.
    for gate in ("independent_validation", "parameter_uq", "model_discrepancy",
                 "claims_integration", "domainpack_integration"):
        assert gates[gate]["status"] == "MISSING", gate


# ---- review corrections ---------------------------------------------------------------------------------------------
def test_a_set_with_out_of_domain_cycles_cannot_pass_acceptance():
    from benchmarks.battery_1rc_closure.evaluate import applicable_acceptance
    assert applicable_acceptance("PASS", 0) == "PASS"
    assert applicable_acceptance("PASS", 3).startswith("NOT_ASSESSABLE")
    assert applicable_acceptance("FAIL", 3) == "FAIL"                 # a failure is never excused by the domain
    within = _pinned("VALIDATION")["roles"]["within_cell_holdout"]
    assert within["1rc"]["acceptance"].startswith("NOT_ASSESSABLE")
    assert within["1rc"]["acceptance_thresholds_all_cycles"] == "PASS"


def test_every_held_out_prediction_is_bound_to_a_reproducible_route_replay_record():
    from benchmarks.battery_1rc_closure.evaluate import load_calibration, predict_1rc_route
    cal = load_calibration()
    entry = _pinned("VALIDATION")["roles"]["cross_cell_validation"]
    assert all(len(c["replay_record_sha256"]) == 64 for c in entry["per_cycle"])
    first = bfit.Cycle(bdata.load("cross_cell_validation")["cycles"][0])
    basis = next(iter(entry["per_cycle"]))  # noqa: F841 - the record is checked through the digest below
    import math as _m
    cal_digest = (RESULTS / "CALIBRATION.sha256").read_bytes().split()[0].decode()[:16]
    text = (f"identified on B0005+B0007 (results/CALIBRATION.json, sha256 {cal_digest}); identifiability decision "
            f"{cal['identifiability']['decision']}: NOT a validated parameter set")
    _, _, binding = predict_1rc_route(first, cal["models"]["1rc"]["parameters"], cal["parameter_set"], text)
    assert binding["replay_record_sha256"] == entry["per_cycle"][0]["replay_record_sha256"]
    assert _m.isfinite(entry["per_cycle"][0]["rmse_1rc_mV"])


def test_the_raw_bytes_rebuild_check_refuses_when_the_raw_files_are_absent(tmp_path):
    # The rebuild itself needs the receipted NASA .mat files, which are not shipped: it is the command
    # ``python -m benchmarks.battery_1rc_closure.data --verify-raw <dir>`` (run results in docs/work/PROGRESS.md),
    # not a test that the gates could only ever skip. Here: without the files it must report, never pass silently.
    (tmp_path / "scratch").mkdir()
    problems = bdata.verify_raw(tmp_path / "absent", tmp_path / "scratch")
    assert len(problems) == len(bdata.VERIFIED_ROLES)
    assert all("cannot rebuild" in p for p in problems)
