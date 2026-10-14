"""LG HG2 identifiability experiment: identities, frozen rules, leakage, transcription vs route, and honest outcome."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import pathlib

import numpy as np
import pytest

from benchmarks.battery_1rc_identifiability import data as idata
from benchmarks.battery_1rc_identifiability import fit as ifit
from benchmarks.battery_1rc_identifiability import lghg2
from benchmarks.battery_1rc_identifiability import outcome as ioutcome
from benchmarks.battery_1rc_identifiability import prereg as iprereg

HERE = pathlib.Path(iprereg.__file__).resolve().parent
RESULTS = HERE / "results"
CLOSURE = HERE.parent / "battery_1rc_closure" / "results"


def _pinned(path: pathlib.Path):
    raw = path.with_suffix(".json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == path.with_suffix(".sha256").read_bytes().split()[0].decode()
    return json.loads(raw)


def test_the_nasa_closure_evidence_is_preserved_unchanged():
    expected = {"CALIBRATION": "a302989a9034fb5b169480bf1a1e031bca9706ed3d474bd17ce44a641b685530",
                "SENSITIVITY": "7cf0c9bedc4be7dc8503aacb6cb95b6f8f36d8eb657680f6a835cb19ecb76919",
                "UNCERTAINTY_REPORT": "7bcf51a4dbc80f0fc685a60a10e961d3936bb80dcffeb6b0c83b1c424dddbc61",
                "VALIDATION": "ff6f19568a2e8f2e81133cd2aea907e296f5fc27c90d92657667e4052ae9d65c"}
    for name, digest in expected.items():
        assert hashlib.sha256((CLOSURE / f"{name}.json").read_bytes()).hexdigest() == digest, name


def test_the_preregistration_is_pinned_and_every_record_binds_to_it():
    raw = (HERE / "PREREGISTRATION.json").read_bytes()
    assert iprereg.canonical(iprereg.PREREG) == raw
    digest = hashlib.sha256(raw).hexdigest()
    assert digest == (HERE / "PREREGISTRATION.sha256").read_bytes().split()[0].decode()
    for name in ("ocv", "calibration", "heldout_pulses", "heldout_cc", "descriptive", "exclusions"):
        assert idata.load(name)["preregistration_sha256"] == digest
    assert _pinned(RESULTS / "CALIBRATION")["preregistration_sha256"] == digest
    assert _pinned(RESULTS / "VALIDATION")["preregistration_sha256"] == digest


# ---- the byte reader --------------------------------------------------------------------------------------------------
HEAD = ("Time Stamp,Step,Status,Prog Time,Step Time,Cycle,Cycle Level,Procedure,Voltage,Current,Temperature,Capacity,"
        "WhAccu,Cnt,\n,,,,,,,,[V],[A],[C],[Ah],[Wh],[Cnt],\n")


def _row(t, v, i, cap=0.0, stamp="1/1/2018 1:00:00 AM"):
    return f"{stamp},2,DCH,00:00:{t:06.3f},00:00:00.1,1,1,P,{v},{i},24.0,{cap},0,1,\n"


def _csv(tmp_path, rows):
    p = tmp_path / "x.csv"
    p.write_bytes(("Measurement ID,1\n\n" + HEAD + "".join(rows)).encode() + b"\x00\r\n")
    return p


def test_reader_drops_exact_repeats_and_keeps_the_first_of_a_repeat_within_instrument_accuracy(tmp_path):
    rec = lghg2.read(_csv(tmp_path, [_row(1.0, 4.1, -3.0), _row(1.0, 4.1, -3.0), _row(1.1, 4.0, -3.0),
                                     _row(1.1, 4.0002, -3.002, stamp="1/1/2018 1:00:01 AM"), _row(1.2, 3.99, -3.0)]))
    assert rec.dropped_exact_duplicates == 1 and rec.repeated_stamps == 1 and len(rec.prog_time_s) == 3
    assert rec.voltage_v[1] == 4.0


def test_reader_refuses_a_repeat_that_disagrees_beyond_instrument_accuracy(tmp_path):
    with pytest.raises(lghg2.LgHg2FileRefused, match="instrument accuracy"):
        lghg2.read(_csv(tmp_path, [_row(1.0, 4.1, -3.0), _row(1.0, 4.12, -3.0)]))


def test_reader_refuses_rows_that_go_back_in_time_rather_than_reordering_them(tmp_path):
    with pytest.raises(lghg2.LgHg2FileRefused, match="back in time"):
        lghg2.read(_csv(tmp_path, [_row(1.0, 4.1, -3.0), _row(1.2, 4.0, -3.0), _row(1.1, 4.05, -3.0)]))


def test_reader_refuses_a_file_without_the_digatron_header(tmp_path):
    p = tmp_path / "y.csv"
    p.write_bytes(b"not,a,cycler,export\n1,2,3\n")
    with pytest.raises(lghg2.LgHg2FileRefused, match="header"):
        lghg2.read(p)


# ---- frozen roles and exclusions -------------------------------------------------------------------------------------
def test_calibration_and_held_out_pulses_are_disjoint_by_current_level_and_inside_the_declared_soc():
    cal, held = idata.load("calibration")["windows"], idata.load("heldout_pulses")["windows"]
    assert {w["level_A"] for w in cal} == {3.0, 18.0} and {w["level_A"] for w in held} == {6.0, 12.0}
    assert all(w["z_start"] >= 0.10 for w in cal + held)
    assert len(cal) == 18 and len(held) == 20


def test_the_exclusions_are_recorded_not_repaired():
    exc = idata.load("exclusions")["excluded"]
    assert any(e.get("test") == "549_C20DisCh" and "no preceding rest" in e["reason"] for e in exc)
    assert any("truncated" in e.get("reason", "") for e in exc)
    assert any("below the declared 0.10" in e.get("reason", "") for e in exc)
    assert "drive cycles (UDDS, HWFET, LA92, US06, Mixed)" in idata.load("exclusions")["preregistered_exclusions"]


def test_the_ocv_is_measured_and_never_extrapolated():
    ocv = ifit.Ocv(idata.load("ocv"))
    assert ocv.z[-1] == pytest.approx(1.0) and np.all(np.diff(ocv.v) > 0)
    with pytest.raises(ValueError, match="never extrapolated"):
        ocv(np.array([ocv.z[0] - 0.01]))


def test_the_fit_reads_only_the_calibration_role_and_the_ocv():
    tree = ast.parse((HERE / "fit.py").read_text(encoding="utf-8"))
    loaded = {node.args[0].value for node in ast.walk(tree)
              if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "load"
              and node.args and isinstance(node.args[0], ast.Constant)}
    assert loaded == {"ocv", "calibration"}


# ---- the FORGE route and the fitting transcription -------------------------------------------------------------------
def test_the_route_with_the_re_expressed_charge_axis_equals_the_transcription_on_real_windows():
    from benchmarks.battery_1rc_identifiability.evaluate import Axis, load_calibration, predict_route
    cal = load_calibration()
    p = cal["models"]["1rc"]["parameters"]
    ocv = ifit.Ocv(idata.load("ocv"))
    axis = Axis(ocv)
    for role, key in (("calibration", "windows"), ("heldout_cc", "tests")):
        doc = idata.load(role)
        w = ifit.Window(doc[key][0], doc["q_hppc_Ah"])
        route, status, _ = predict_route(w, axis, doc["q_hppc_Ah"], p, cal["parameter_set"], "test pin", "pin")
        fast = ifit.predict(w, ocv, p["R0"], p["R1"], p["C1"])
        assert np.max(np.abs(route - fast)) < 1e-9 and status == "in_domain"


# ---- the calibration, the evaluation and the outcome -----------------------------------------------------------------
def test_the_calibration_record_is_identifiable_and_rerun_stable():
    cal = _pinned(RESULTS / "CALIBRATION")
    assert cal["identifiability"]["decision"] == "IDENTIFIABLE"
    assert not any(cal["identifiability"]["on_bound"].values())
    assert "elapsed_seconds" not in json.dumps(cal)              # timings live in the unpinned TIMINGS file


def test_acceptance_is_applicability_gated():
    from benchmarks.battery_1rc_identifiability.evaluate import acceptance
    lim = {"RMSE_mV_max": 15.0, "P95_abs_mV_max": 30.0}
    assert acceptance({"rmse_mV": 10.0, "p95_abs_mV": 20.0}, lim, 0) == "PASS"
    assert acceptance({"rmse_mV": 10.0, "p95_abs_mV": 20.0}, lim, 2).startswith("NOT_ASSESSABLE")
    assert acceptance({"rmse_mV": 20.0, "p95_abs_mV": 20.0}, lim, 0) == "FAIL"
    # contradiction requires admissible evidence: an out-of-domain set rejects nothing either
    assert acceptance({"rmse_mV": 20.0, "p95_abs_mV": 20.0}, lim, 2).startswith("NOT_ASSESSABLE")


@pytest.mark.parametrize("ident, acc, expected", [
    ("NOT_IDENTIFIABLE", {"a": "PASS"}, "INSUFFICIENT_MEASUREMENT_EVIDENCE"),
    ("WEAKLY_IDENTIFIABLE", {"a": "PASS"}, "INSUFFICIENT_MEASUREMENT_EVIDENCE"),
    ("IDENTIFIABLE", {"a": "PASS", "b": "FAIL"}, "MODEL_REJECTED"),
    ("IDENTIFIABLE", {"a": "PASS", "b": "NOT_ASSESSABLE (1 outside)"}, "IDENTIFIABILITY_SUPPORTED"),
    ("IDENTIFIABLE", {"a": "PASS", "b": "PASS"}, "MODEL_VALIDATION_SUPPORTED"),
])
def test_the_outcome_mapping_is_the_preregistered_one(ident, acc, expected):
    assert ioutcome.decide(ident, acc) == expected


def test_a_comparison_with_one_unit_carries_no_verdict():
    from benchmarks.battery_1rc_identifiability.evaluate import paired_bootstrap
    one = paired_bootstrap([np.full(5, 0.03)], [np.full(5, 0.01)], b=50)
    assert one["verdict"].startswith("NOT_ASSESSABLE")
    assert _pinned(RESULTS / "VALIDATION")["roles"]["heldout_cc"]["comparison"]["verdict"].startswith("NOT_ASSESSABLE")


def test_the_recorded_outcome_is_model_rejected_and_says_why():
    out = _pinned(RESULTS / "OUTCOME")
    assert out["outcome"] == "MODEL_REJECTED"
    assert out["outcome_without_the_preregistered_temperature_widening"] == "IDENTIFIABILITY_SUPPORTED"
    assert "BUNDLE" in out["reading"]["rejected"] and "marginal" in out["reading"]["rejected"]
    assert "under load alone" in out["reading"]["supported"]
    assert out["held_out_acceptance_1rc"] == {"heldout_pulses": "PASS", "heldout_cc": "FAIL"}
    assert "ONE unit" in out["reading"]["comparison_note"]


@pytest.mark.skipif(not os.environ.get("FORGE_LGHG2_DIR"),
                    reason="needs the five LG HG2 CSV files (set FORGE_LGHG2_DIR); see the README")
def test_every_role_rebuilds_from_the_raw_lg_hg2_bytes():
    docs = idata.build(pathlib.Path(os.environ["FORGE_LGHG2_DIR"]))
    for name, doc in docs.items():
        pinned = idata.load(name)
        assert json.dumps(doc, sort_keys=True) == json.dumps(pinned, sort_keys=True), name


def test_the_measurement_uncertainty_decision_is_owner_admitted_and_scoped():
    rec = _pinned(HERE / "MEASUREMENT_UNCERTAINTY_DECISION")
    assert rec["decision"] == "ADMITTED_TYPE_B" and rec["decided_by"] == "owner"
    assert rec["components"]["voltage"]["half_width_V"] == 0.005
    assert any("NASA" in limit and "UNKNOWN" in limit for limit in rec["limits"])
    nasa = json.loads((CLOSURE / "UNCERTAINTY_REPORT.json").read_bytes())
    assert nasa["components"]["measurement"]["status"] == "UNKNOWN"          # the NASA evidence is not upgraded
