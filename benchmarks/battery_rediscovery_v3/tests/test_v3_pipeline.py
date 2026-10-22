"""Pre-run tests of battery_rediscovery_v3: GEN1 identity, the bundle and its provenance, the firewall, reference B,
the process-blindness guards, and a synthetic end-to-end dry run plus replay dry run through the real sandbox.

No real-data truth is computed here: every reference fit runs on synthetic problems only.
"""

from __future__ import annotations

import json
import math
import pathlib
import subprocess
import sys

import numpy as np
import pytest

from benchmarks.battery_rediscovery_v2.candidate.common import load_pack
from benchmarks.battery_rediscovery_v2.evaluator import reference as ref_a
from benchmarks.battery_rediscovery_v2.evaluator.run_evaluation import replay_summary
from benchmarks.battery_rediscovery_v2.tests import synthetic_pack as v2syn
from benchmarks.battery_rediscovery_v3 import build_pack, gen1_reference, launch, leakage, mutation
from benchmarks.battery_rediscovery_v3.evaluator import conclusion as cr
from benchmarks.battery_rediscovery_v3.evaluator import reference_b, truth
from benchmarks.battery_rediscovery_v3.evaluator.run_evaluation import build_instances
from benchmarks.battery_rediscovery_v3.tests import synthetic_v3

HERE = pathlib.Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
REAL_DATA = pathlib.Path("D:/forge-data/kirkaldy2024/v3_rpt").exists()


# ---- GEN1 and the bundle ----------------------------------------------------------------------------------------------
def test_gen1_reference_is_intact():
    rec = json.loads((ROOT / "docs" / "discovery" / "mind_gen1_reference.json").read_bytes())
    assert gen1_reference.check(rec) == []
    s = rec["generation_status"]
    assert (s["SCIENTIFICALLY_VERIFIED"], s["CERTIFIED"], s["FORMAL"]) == ("NO", "NO", "NO")
    v2 = rec["benchmarks"]["battery_rediscovery_v2"]["standing"]
    assert v2["described_as"] == "REAL_DATA_IMPROVEMENT_CONFIRMED_BY_PREREGISTERED_V2_RULE"
    assert v2["EVIDENCE_STRENGTH"] == "LIMITED_SMALL_N"


def test_bridge_problems_are_the_v2_pack_bytes():
    v2 = ROOT / "benchmarks" / "battery_rediscovery_v2" / "candidate" / "pack"
    for pid in build_pack.BRIDGE:
        assert (HERE / "CandidateBundle" / f"{pid}.json").read_bytes() == (v2 / f"{pid}.json").read_bytes()


def test_primary_units_are_unused_and_unexposed():
    census = json.loads((HERE / "EvaluatorVault" / "CENSUS.json").read_bytes())
    primary = [r for r in census["rows"] if r["primary_class"] == "ELIGIBLE_PRIMARY_V3"]
    assert primary
    for r in primary:
        assert "UNUSED_BY_MIND" in r["classes"]
        assert not set(r["classes"]) & {"USED_IN_V0", "USED_IN_V1", "USED_IN_V2", "HISTORICAL_TRUTH_EXPOSED"}
        assert r["outcome_known_in_evaluator_context"] is False
    ident = json.loads((HERE / "EvaluatorVault" / "IDENTITY_MAP.json").read_bytes())
    units = {r["unit"] for r in primary}
    for pid, e in ident.items():
        d = e["design"]
        name = {"gitt": f"Expt {d.get('expt')} cell {d['cell']}", "chen": d["cell"], "nasa": d["cell"]}[d["kind"]]
        assert name in units, (pid, name)


def test_gitt_ocv_knots_come_from_calibration_rests_only():
    pack = load_pack(HERE / "CandidateBundle")
    for pid, spec in pack.items():
        if spec["declared_family"]["family_id"] != "rc1_measured_ocv/1" or pid in build_pack.BRIDGE:
            continue
        knots = spec["declared_family"]["constants"]["ocv_knots"]
        cal_z0 = {round(t["initial_state"]["soc"], 9) for t in spec["sets"]["calibration"]}
        held_z0 = {round(t["initial_state"]["soc"], 9) for s in ("within_unit_heldout", "cross_unit_heldout")
                   for v in spec["sets"].get(s, {}).values() for t in v}
        for z, _v in knots:
            assert round(z, 9) in cal_z0 or abs(z) < 1e-9, (pid, z)
        assert not {round(z, 9) for z, _ in knots} & (held_z0 - cal_z0), pid


def test_heldout_windows_are_disjoint_from_calibration():
    ident = json.loads((HERE / "EvaluatorVault" / "IDENTITY_MAP.json").read_bytes())
    for pid, e in ident.items():
        seen = {}
        for tid, tr in e["trajectories"].items():
            key = (tr["source_file"], tr.get("pulse_start_s", tr.get("start_s", tr.get("discharge_ordinal"))))
            assert key not in seen, (pid, tid, seen.get(key))
            seen[key] = tid


@pytest.mark.expensive
@pytest.mark.skipif(not REAL_DATA, reason="needs the local raw archives")
def test_bundle_rebuilds_byte_identically_and_static_audit_passes():
    assert leakage.provenance_findings() == []
    rep = leakage.audit(mutation.protected_values(), phase="test")
    assert rep["status"] == "PASS", {k: rep[k] for k in ("numeric", "text", "pack_schema", "provenance")}


def test_runtime_negative_controls(tmp_path):
    rows = mutation.runtime_cases(tmp_path)
    assert [r["name"] for r in rows if (r["expected"] == "DETECT") != r["flagged"]] == []
    assert {r["name"] for r in rows if r["expected"] == "DETECT"} >= {"vault_read", "truth_bundle_read", "v2_pack_read",
                                                                       "output_read_during_run", "real_process_vault_read"}


# ---- process blindness -------------------------------------------------------------------------------------------------
def test_launch_refuses_once_a_truth_bundle_exists(tmp_path, monkeypatch):
    tb = tmp_path / "TruthBundle"
    tb.mkdir()
    (tb / "TRUTH.json").write_bytes(b"{}")
    monkeypatch.setattr(launch, "TRUTH", tb)
    assert any("PROCESS BLINDNESS" in p for p in launch.preconditions())


def test_truth_refuses_before_a_committed_seal(tmp_path):
    with pytest.raises(truth.SealNotVerified):
        truth.verify_seal(tmp_path)


# ---- reference B ------------------------------------------------------------------------------------------------------
def test_reference_b_recovers_noise_free_parameters():
    spec = synthetic_v3.s3(0, sigma=0.0, linear_ocv=True)
    b = reference_b.truth_table(spec)
    p = b["diagnostics"]["parameters"]
    assert p["R0"] == pytest.approx(0.020, rel=1e-3)
    assert p["R1"] == pytest.approx(0.012, rel=1e-3)
    assert p["C1"] == pytest.approx(2500.0, rel=1e-3)


@pytest.mark.expensive
@pytest.mark.parametrize("make", [lambda: v2syn.s1(0), lambda: v2syn.s2(0), lambda: synthetic_v3.s3(0)])
def test_reference_b_agrees_with_reference_a_on_synthetic_problems(make):
    spec = make()
    a, b = ref_a.truth_table(spec), reference_b.truth_table(spec)
    for axis in reference_b.AXES:
        assert a[axis]["truth"] == b[axis]["truth"], axis
    assert b["diagnostics"]["sse"] / 2 == pytest.approx(a["diagnostics"]["cost"], rel=1e-6)
    for n in ("R0", "R1", "C1"):
        assert math.log(b["diagnostics"]["parameters"][n]) == pytest.approx(
            math.log(a["diagnostics"]["parameters"][n]), abs=1e-3)


def test_reference_b_uses_no_nonlinear_least_squares_solver():
    import ast  # noqa: PLC0415

    tree = ast.parse((HERE / "evaluator" / "reference_b.py").read_bytes())
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module == "scipy.optimize"
                for a in n.names}
    called = {n.attr if isinstance(n, ast.Attribute) else n.id for n in ast.walk(tree)
              if isinstance(n, (ast.Name, ast.Attribute))}
    assert imported == {"lsq_linear", "minimize_scalar"}
    assert "least_squares" not in called


# ---- synthetic end-to-end dry run and replay dry run --------------------------------------------------------------------
def _sandbox(log: pathlib.Path, *args: str) -> int:
    return subprocess.run([sys.executable, "-m", "benchmarks.battery_rediscovery_v3.sandbox_run", str(log), "--", *args],
                          cwd=ROOT, capture_output=True).returncode


@pytest.mark.expensive
def test_synthetic_end_to_end_and_replay_dry_run(tmp_path):
    pack = synthetic_v3.write_pack(tmp_path / "bundle", with_s1=False)
    out, rep = tmp_path / "out", tmp_path / "replay"
    assert _sandbox(tmp_path / "log.json", "--pack", str(pack), "--out", str(out)) == 0
    r = leakage.runtime_findings(json.loads((tmp_path / "log.json").read_bytes()), [out], pack_dir=pack)
    assert not leakage.runtime_failed(r), r
    assert _sandbox(tmp_path / "log_replay.json", "--pack", str(pack), "--replay", str(out), "--out", str(rep)) == 0
    r = leakage.runtime_findings(json.loads((tmp_path / "log_replay.json").read_bytes()), [rep], readable=[out],
                                 pack_dir=pack)
    assert not leakage.runtime_failed(r), r
    assert replay_summary(json.loads((rep / "REPLAY.json").read_bytes()))["exact"]
    specs = load_pack(pack)
    table = {pid: truth.problem_truth(spec) for pid, spec in specs.items()}
    from benchmarks.battery_rediscovery_v2.candidate import arms  # noqa: PLC0415
    outputs = {a: {pid: json.loads((out / f"{a}__{pid}.json").read_bytes()) for pid in specs} for a in arms.ALL_ARMS}
    rows = [{"key": f"{pid}/{ax}", "problem": pid, "axis": ax, "heldout": ax.endswith(("GENERALIZATION", "TRANSFER"))}
            for pid in specs for ax in reference_b.AXES]
    inst = build_instances(rows, table, outputs, arms.ALL_ARMS)
    c = cr.conclude(instances=inst, seal_ok=True, leakage_ok=True, replay_exact=True, reference_disagreement_fraction=0.0)
    assert c["verdict"] in cr.VERDICTS
    assert c["verdict"] == "TRUTH_INSUFFICIENT"   # two synthetic problems cannot reach the decided-instance minimum
    for pid in specs:
        assert set(table[pid]["dimensions"]) == {"FIT_OK", "PARAMETER_DEGENERACY", "IDENTIFIABILITY_LIMIT",
                                                 "MODEL_DISCREPANCY"}
        assert table[pid]["dimensions"]["FIT_OK"]["value"] == "YES"
    assert np.isfinite(c["statistics"][cr.COMB]["decided_n"])
    # the report assembly runs on the same synthetic outputs, so no evaluator code needs touching after the seal
    from benchmarks.battery_rediscovery_v3.evaluator.run_evaluation import assemble  # noqa: PLC0415
    plan = {"instances": {"primary": rows, "bridge": []},
            "eligibility": {"primary_problems": sorted(specs), "bridge_problems": []}}
    ident = {"S2": {"design": {"kind": "nasa", "cell": "s2"}, "trajectories": {}},
             "S3": {"design": {"kind": "gitt", "expt": 4, "cell": "A", "rpt": 0}, "trajectories": {}}}
    mut = {"status": "PASS", "leak_mutations": 1, "leaks_caught": 1, "benign_controls": 1, "benign_triggered": 0}
    ev, md = assemble(plan=plan, table=table, specs=specs, outputs=outputs,
                      rs=replay_summary(json.loads((rep / "REPLAY.json").read_bytes())), ident=ident,
                      timings=json.loads((out / "TIMINGS.json").read_bytes()), audit_status="PASS", mut=mut,
                      v2_truth={}, v2_outputs={}, seal={})
    assert ev["conclusion"]["verdict"] == c["verdict"] and "V3_CONCLUSION" in md
    assert set(ev["evidence_strength"]) >= {"TOTAL_DECIDED_INSTANCES", "HELD_OUT_DECIDED_INSTANCES", "INDEPENDENT_CELLS",
                                            "OPERATING_CONDITIONS", "SINGLE_INSTANCE_ROBUST",
                                            "IMPLEMENTATION_CORRELATED_INSTANCES", "LEAKAGE", "REPLAY"}
    assert len(ev["table"]) == 10 and ev["table"][0][-1] == "Decided N"
    json.dumps(ev, allow_nan=False)
