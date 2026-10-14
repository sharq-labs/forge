"""Kirkaldy 2024 cross-cell experiment: identities, frozen roles, leakage, transcription vs route, honest outcome."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import pathlib

import numpy as np
import pytest

from benchmarks.battery_1rc_crosscell import data as xdata
from benchmarks.battery_1rc_crosscell import fit as xfit
from benchmarks.battery_1rc_crosscell import outcome as xoutcome
from benchmarks.battery_1rc_crosscell import prereg as xprereg

HERE = pathlib.Path(xprereg.__file__).resolve().parent
RESULTS = HERE / "results"
SMALL_ROLES = ("ocv_cal", "heldout_own_ocv", "exclusions")
WINDOW_ROLES = ("calibration", "heldout_gitt25", "heldout_gitt5")
RAW = os.environ.get("FORGE_KIRKALDY_DIR")
have_windows = all((HERE / "data" / f"{n}.json").exists() for n in WINDOW_ROLES)
needs_windows = pytest.mark.skipif(not have_windows, reason="window roles are rebuilt from the raw files: "
                                                            "python -m benchmarks.battery_1rc_crosscell.data --raw-dir ...")


def _pinned(path: pathlib.Path):
    raw = path.with_suffix(".json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == path.with_suffix(".sha256").read_bytes().split()[0].decode()
    return json.loads(raw)


def test_the_earlier_battery_evidence_is_preserved_unchanged():
    closure = HERE.parent / "battery_1rc_closure" / "results"
    assert hashlib.sha256((closure / "VALIDATION.json").read_bytes()).hexdigest() == \
        "ff6f19568a2e8f2e81133cd2aea907e296f5fc27c90d92657667e4052ae9d65c"
    lghg2 = HERE.parent / "battery_1rc_identifiability"
    expected = {"PREREGISTRATION.json": "d8acfb2697589b034fdacc38cba92be93770beac840ef2864689f6d03a30a300",
                "results/CALIBRATION.json": "0bcec32d774ec3465bb86a9dc2254424c5a0524c9fbbd9fc74d2d3cab7b8bf9e",
                "results/VALIDATION.json": "90eb67f7897aad05fbe31a4fdfa77067d017555ce9e5375329eaf45b4335ff4a",
                "results/OUTCOME.json": "bfe1b6f39d31d284dfd4cc93b3c4f4658638336730c2e05de0f50e486d7a865c"}
    for name, digest in expected.items():
        assert hashlib.sha256((lghg2 / name).read_bytes()).hexdigest() == digest, name
    assert _pinned(lghg2 / "results" / "OUTCOME")["outcome"] == "MODEL_REJECTED"


def test_the_preregistration_is_pinned_and_every_record_binds_to_it():
    raw = (HERE / "PREREGISTRATION.json").read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    assert digest == (HERE / "PREREGISTRATION.sha256").read_bytes().split()[0].decode()
    assert xprereg.canonical(json.loads(raw)) == raw
    for name in SMALL_ROLES:
        assert xdata.load(name)["preregistration_sha256"] == digest
    for name in ("CALIBRATION", "VALIDATION"):
        doc = _pinned(RESULTS / name)
        assert doc["preregistration_sha256"] == digest


def test_the_split_is_by_cell_and_experiment_and_disjoint():
    cal, held = set(xprereg.CAL_CELLS), set(xprereg.HELD_CELLS)
    assert not cal & held
    assert {c.split("/")[0] for c in cal} == {"Expt 3", "Expt 4", "Expt 5"}
    assert {c.split("/")[0] for c in held} == {"Expt 1", "Expt 2,2"}
    assert set(_pinned(RESULTS / "CALIBRATION")["cells"]) == cal


def test_the_large_window_roles_are_pinned_but_not_committed():
    ignored = (HERE / "data" / ".gitignore").read_bytes().decode().split()
    for name in WINDOW_ROLES:
        assert f"{name}.json" in ignored
        assert len((HERE / "data" / f"{name}.sha256").read_bytes().split()[0]) == 64


def test_load_refuses_a_role_that_does_not_reproduce_its_pin(tmp_path, monkeypatch):
    (tmp_path / "ocv_cal.json").write_bytes(b'{"preregistration_sha256": "x"}\n')
    (tmp_path / "ocv_cal.sha256").write_bytes(b"0" * 64 + b"\n")
    monkeypatch.setattr(xdata, "DATA", tmp_path)
    with pytest.raises(ValueError, match="pinned digest"):
        xdata.load("ocv_cal")


def test_both_construction_deviations_are_recorded_with_their_discovery():
    exc = xdata.load("exclusions")
    text = " ".join(exc["deviations"])
    assert "temperature dropout" in text and "inventing a temperature" in text
    assert "transition record" in text and "no model had been run" in text
    dropped = exc["transition_records_dropped"]
    assert {k for k, v in dropped.items() if v} == {f"Expt 2,2/{c} {t}" for c in "CD"
                                                    for t in ("25-pulse GITT", "5-pulse GITT")}
    reasons = {e["reason"] for e in exc["excluded"]}
    assert "temperature dropout inside the pulse" in reasons
    # what deviation 1 itself removed (beyond the preregistered in-pulse rule): nothing, on these files
    assert sum(e["reason"] == "temperature dropout only in the rest (deviation 1)" for e in exc["excluded"]) == 0
    assert sum(exc["dropout_samples_per_file"].values()) > 0


def test_the_transition_rule_drops_only_an_on_load_sample_logged_at_zero_current(tmp_path, monkeypatch):
    rows = ["Time (s),Voltage (V),Current (mA),Charge (mA.h),Temperature (degC)",
            "0.0,4.10,0,0,25", "1.0,4.10,0,0,25", "1.998,4.03,0,0,25", "2.0,4.03,-2500,0,25", "3.0,4.02,-2500,0,25",
            "3.001,4.02,-2500,0,25", "3.05,4.09,0,0,25", "4.0,4.095,0,0,25"]
    p = tmp_path / "f.csv"
    p.write_bytes(("\n".join(rows) + "\n").encode())
    monkeypatch.setitem(xdata.PREREG["data"]["files_sha256"], "f.csv", hashlib.sha256(p.read_bytes()).hexdigest())
    d = xdata.read(tmp_path, "f.csv")
    assert d["transition_records_dropped"] == 1
    assert list(d["t"]) == [0.0, 1.0, 2.0, 3.0, 3.001, 3.05, 4.0]       # the pulse-END record is genuine and kept
    assert list(d["i"]) == [0.0, 0.0, 2.5, 2.5, 2.5, 0.0, 0.0]


def test_read_refuses_a_file_that_is_not_the_preregistered_one(tmp_path):
    p = tmp_path / "Expt 1 - cell D - RPT0 - 25-pulse GITT 0.5C discharge data.csv"
    p.write_bytes(b"Time (s),Voltage (V),Current (mA),Charge (mA.h),Temperature (degC)\n0,4,0,0,25\n")
    with pytest.raises(ValueError, match="not the preregistered file"):
        xdata.read(tmp_path, p.name)


def test_the_ocv_is_the_calibration_mean_and_never_extrapolated():
    doc = xdata.load("ocv_cal")
    ocv = xfit.Ocv(doc)
    assert ocv.z[-1] == pytest.approx(1.0) and np.all(np.diff(ocv.v) > 0)
    assert all(k[2] == len(xprereg.CAL_CELLS) for k in doc["knots_z_V_cells"])
    assert set(doc["per_cell_q_Ah"]) == set(xprereg.CAL_CELLS)
    assert doc["q_cal_Ah"] == pytest.approx(np.mean(list(doc["per_cell_q_Ah"].values())))
    with pytest.raises(ValueError, match="never extrapolated"):
        ocv(np.array([ocv.z[0] - 0.01]))


def test_the_fit_reads_only_the_calibration_role_and_the_calibration_ocv():
    tree = ast.parse((HERE / "fit.py").read_text(encoding="utf-8"))
    loaded = {node.args[0].value for node in ast.walk(tree)
              if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "load"
              and node.args and isinstance(node.args[0], ast.Constant)}
    assert loaded == {"ocv_cal", "calibration"}


def test_the_calibration_record_is_rerun_stable_and_its_temperature_range_is_not_widened():
    cal = _pinned(RESULTS / "CALIBRATION")
    assert "elapsed_seconds" not in json.dumps(cal)
    assert cal["identifiability"]["bootstrap_unit"] == "calibration cell"
    assert "NOT widened" in cal["parameter_set"]["temperature_basis"]


@needs_windows
def test_the_vectorised_transcription_equals_the_route_on_real_windows():
    from benchmarks.battery_1rc_crosscell.evaluate import Axis, load_calibration, predict_route
    cal = load_calibration()
    p = cal["models"]["1rc"]["parameters"]
    ocv = xfit.Ocv(xdata.load("ocv_cal"))
    for role in ("calibration", "heldout_gitt25", "heldout_gitt5"):
        doc = xdata.load(role)
        w = doc["windows"][0]
        route, status, _ = predict_route(w, Axis(ocv), doc["q_Ah"], p, cal["parameter_set"], "test pin", "pin")
        b = xfit.Batch([w], doc["q_Ah"])
        fast = xfit.predict(b, ocv, p["R0"], p["R1"], p["C1"])[0][b.mask[0]]
        assert np.max(np.abs(route - fast)) < 1e-9


def test_acceptance_is_applicability_gated_and_needs_the_load_only_samples_too():
    from benchmarks.battery_1rc_crosscell.evaluate import acceptance
    lim = {"RMSE_mV_max": 15.0, "P95_abs_mV_max": 30.0, "also_load_only": True}
    good = {"rmse_mV": 10.0, "p95_abs_mV": 20.0, "load_only": {"rmse_mV": 12.0, "p95_abs_mV": 25.0}}
    hidden = {"rmse_mV": 10.0, "p95_abs_mV": 20.0, "load_only": {"rmse_mV": 19.0, "p95_abs_mV": 25.0}}
    bad = {"rmse_mV": 20.0, "p95_abs_mV": 20.0, "load_only": {"rmse_mV": 12.0, "p95_abs_mV": 25.0}}
    assert acceptance(good, lim, 0) == "PASS"
    assert acceptance(hidden, lim, 0) == "FAIL"          # pooled rest samples cannot hide a load miss
    assert acceptance(bad, lim, 0) == "FAIL"
    assert acceptance(bad, lim, 3).startswith("NOT_ASSESSABLE")
    assert acceptance(good, lim, 3).startswith("NOT_ASSESSABLE")


def test_an_out_of_domain_set_yields_no_comparison_verdict_and_no_verdict_token():
    from benchmarks.battery_1rc_crosscell.evaluate import gate_comparison
    cmp = {"rmse_rint_minus_1rc_mV": 5.0, "ci95_mV": [4.0, 6.0], "verdict": "1RC_BETTER"}
    assert gate_comparison(cmp, 0) == cmp
    gated = gate_comparison(cmp, 3)
    assert gated["verdict"] == "NOT_ASSESSABLE (3 windows outside the validated domain)"
    assert "1RC_BETTER" not in gated["verdict"] and gated["ci95_mV"] == [4.0, 6.0]
    val = _pinned(RESULTS / "VALIDATION")
    assert val["roles"]["calibration"]["comparison"]["verdict"].startswith("IN_SAMPLE")
    for role in ("heldout_gitt25", "heldout_gitt5"):
        assert "BETTER" not in val["roles"][role]["comparison"]["verdict"]


def test_post_opening_changes_are_disclosed_and_the_superseded_runs_kept():
    val = _pinned(RESULTS / "VALIDATION")
    poc = val["post_opening_changes"]
    for n, key in ((1, "first"), (2, "second"), (3, "third")):
        raw = (RESULTS / "superseded" / f"VALIDATION_run{n}.json").read_bytes()
        assert hashlib.sha256(raw).hexdigest() == poc[f"{key}_run_validation_sha256"]
    first = json.loads((RESULTS / "superseded" / "VALIDATION_run1.json").read_bytes())
    for role in ("heldout_gitt25", "heldout_gitt5"):
        for m in ("1rc", "rint"):
            # every metric and the acceptance of run 1 (opened once) are unchanged
            assert {k: val["roles"][role][m][k] for k in first["roles"][role][m]} == first["roles"][role][m]


def _synthetic_window(n_rest_before=60, n_pulse=288, n_rest_after=600, z0=0.8):
    t = np.arange(n_rest_before + n_pulse + n_rest_after + 1, dtype=float)
    i = np.where((t > n_rest_before) & (t <= n_rest_before + n_pulse), 2.5, 0.0)
    return {"cell": "S", "pulse_start_s": 0.0, "z0": z0, "time_s": t.tolist(), "current_A": i.tolist(),
            "voltage_V": (3.7 - 0.03 * i).tolist(), "temperature_C": [25.0] * len(t)}


def test_the_vectorised_transcription_equals_the_route_on_a_synthetic_window():
    from benchmarks.battery_1rc_crosscell.evaluate import Axis, predict_route
    ocv = xfit.Ocv({"knots_z_V_cells": [[0.05, 3.3, 7], [0.5, 3.7, 7], [1.0, 4.2, 7]]})
    pset = {"temperature_range_C": [20.0, 30.0], "max_current_A": 2.6}
    p = {"R0": 0.033, "R1": 0.02, "C1": 5000.0}
    for z0 in (0.95, 0.4):
        w = _synthetic_window(z0=z0)
        route, status, _ = predict_route(w, Axis(ocv), 4.8, p, pset, "synthetic pin", "pin")
        b = xfit.Batch([w], 4.8)
        fast = xfit.predict(b, ocv, p["R0"], p["R1"], p["C1"])[0][b.mask[0]]
        assert status == "in_domain" and np.max(np.abs(route - fast)) < 1e-9


def _synthetic_files(perturb_held=0.0, extra_pulse_cell=None):
    """name -> read() output for a GITT-like protocol: 4000 s rest, then pulses each followed by a 3700 s rest."""
    files = {}
    for cell in xprereg.CAL_CELLS + xprereg.HELD_CELLS:
        for test, n, dur in (("25-pulse GITT", 6, 290), ("5-pulse GITT", 3, 1450)):
            n += cell == extra_pulse_cell and test == "25-pulse GITT"
            seg_i = [np.zeros(4000)]
            for _ in range(n):
                seg_i += [np.full(dur, 2.5), np.zeros(3700)]
            i = np.concatenate(seg_i)
            t = np.arange(len(i), dtype=float)
            q = np.concatenate([[0.0], np.cumsum(i[1:] * np.diff(t))]) / 3600.0
            v = 3.2 + 0.9 * (1.0 - q / (q[-1] + 1e-9)) - 0.03 * i
            if cell in xprereg.HELD_CELLS:
                v = v + perturb_held
            files[xdata.fname(cell, test)] = {"t": t, "v": v, "i": i, "temp": np.full(len(t), 25.0),
                                              "transition_records_dropped": 0, "dropout_samples": 0}
    return files


def test_held_out_bytes_cannot_reach_the_calibration_ocv_or_q(monkeypatch, tmp_path):
    def build(files):
        monkeypatch.setattr(xdata, "read", lambda raw_dir, name: files[name])
        return xdata.build(tmp_path)
    a, b = build(_synthetic_files()), build(_synthetic_files(perturb_held=0.05))
    assert a["ocv_cal"] == b["ocv_cal"] and a["calibration"] == b["calibration"]
    assert a["calibration"]["windows"] and a["heldout_gitt25"] != b["heldout_gitt25"]


def test_knot_by_knot_averaging_refuses_cells_with_different_knot_structures(monkeypatch, tmp_path):
    files = _synthetic_files(extra_pulse_cell=xprereg.CAL_CELLS[0])
    monkeypatch.setattr(xdata, "read", lambda raw_dir, name: files[name])
    with pytest.raises(ValueError, match="averaging refused"):
        xdata.build(tmp_path)


def test_a_comparison_with_one_cell_carries_no_verdict():
    from benchmarks.battery_1rc_crosscell.evaluate import cell_block_bootstrap
    one = cell_block_bootstrap([np.full(5, 0.03)] * 3, [np.full(5, 0.01)] * 3, ["A"] * 3, b=50)
    assert one["verdict"].startswith("NOT_ASSESSABLE") and one["unit"] == "held-out cell"


@pytest.mark.parametrize("ident, acc, expected", [
    ("NOT_IDENTIFIABLE", {"a": "PASS"}, "INSUFFICIENT_MEASUREMENT_EVIDENCE"),
    ("WEAKLY_IDENTIFIABLE", {"a": "PASS"}, "INSUFFICIENT_MEASUREMENT_EVIDENCE"),
    ("IDENTIFIABLE", {"a": "PASS", "b": "FAIL"}, "MODEL_REJECTED"),
    ("IDENTIFIABLE", {"a": "PASS", "b": "NOT_ASSESSABLE (1 outside)"}, "IDENTIFIABILITY_SUPPORTED"),
    ("IDENTIFIABLE", {"a": "PASS", "b": "PASS"}, "MODEL_VALIDATION_SUPPORTED"),
])
def test_the_outcome_mapping_is_the_preregistered_one(ident, acc, expected):
    assert xoutcome.decide(ident, acc) == expected


def test_the_ledger_gate_stays_missing_without_an_admitted_measurement_uncertainty():
    assert xoutcome.ledger_independent_validation("MODEL_VALIDATION_SUPPORTED", False) == "MISSING"
    assert xoutcome.ledger_independent_validation("MODEL_REJECTED", True) == "MISSING"
    assert xoutcome.ledger_independent_validation("MODEL_VALIDATION_SUPPORTED", True) == "PASS"
    assert _pinned(RESULTS / "OUTCOME")["ledger_independent_validation"] == "MISSING"


@pytest.mark.skipif(not RAW, reason="needs the 36 Kirkaldy RPT0 CSV files (set FORGE_KIRKALDY_DIR); see the README")
def test_every_role_rebuilds_from_the_raw_bytes_and_matches_its_pin():
    docs = xdata.build(pathlib.Path(RAW))
    for name, doc in docs.items():
        data = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        assert hashlib.sha256(data).hexdigest() == (HERE / "data" / f"{name}.sha256").read_bytes().split()[0].decode()


def test_the_calibration_is_identifiable_from_cells_of_three_experiments():
    cal = _pinned(RESULTS / "CALIBRATION")
    assert cal["identifiability"]["decision"] == "IDENTIFIABLE"
    assert not any(cal["identifiability"]["on_bound"].values())


def test_out_of_domain_windows_make_both_sets_and_their_comparisons_not_assessable():
    val = _pinned(RESULTS / "VALIDATION")
    for role in ("heldout_gitt25", "heldout_gitt5"):
        e = val["roles"][role]
        outside = sum(v for k, v in e["out_of_domain_attribution"].items() if k != "in_domain")
        assert outside == sum(v for k, v in e["route_validity"].items() if k != "in_domain") > 0
        for m in ("1rc", "rint"):
            assert e[m]["acceptance"].startswith("NOT_ASSESSABLE")
        for k in ("comparison", "comparison_load"):
            assert e[k]["verdict"].startswith("NOT_ASSESSABLE")
        sub = e["in_domain_windows_only"]
        assert sub["not_preregistered"] is True and sub["carries_no_verdict"] is True
        assert "acceptance" not in sub["1rc"] and "acceptance" not in sub["rint"]


def test_the_recorded_outcome_is_identifiability_supported_and_does_not_promote_the_ledger():
    out = _pinned(RESULTS / "OUTCOME")
    assert out["outcome"] == "IDENTIFIABILITY_SUPPORTED"
    assert all(v.startswith("NOT_ASSESSABLE") for v in out["held_out_acceptance_1rc"].values())
    assert out["ledger_independent_validation"] == "MISSING"
    assert "NO verdict" in out["reading"]["descriptive_only"]
    assert "not widened after the fact" in out["reading"]["not_assessable"]
    assert "not be blind" in out["reading"]["blindness_spent"]
