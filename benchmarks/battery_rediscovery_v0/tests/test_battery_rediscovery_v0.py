"""BR-BATT-REDISC-01 pins: Mind identity, the forward model, the arms on synthetic worlds, leakage, seal and scoring.

Every arm here runs on synthetic problems with known parameters (``synthetic.py``); no test runs an arm on the real
pack, and no test reads a historical result record.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import pathlib
import subprocess

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from benchmarks.battery_rediscovery_v0 import build_pack, leakage
from benchmarks.battery_rediscovery_v0.candidate import baselines, mind_arm
from benchmarks.battery_rediscovery_v0.candidate import model as m
from benchmarks.battery_rediscovery_v0.candidate.common import (
    NOT_ASSESSABLE, NOT_SUPPORTED, REFUSED, REVIEW, SUPPORTED, Trajectory, combine, load_pack,
)
from benchmarks.battery_rediscovery_v0.evaluator import score, truth
from benchmarks.battery_rediscovery_v0.tests import synthetic as syn
from engcore.mind.minimal import ObservationRefused

HERE = pathlib.Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
MIND_COMMIT = "e2b8037c881847a497c32f7ca56f82b95b493727"


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def test_mind_source_is_byte_identical_to_its_source_commit():
    files = sorted((ROOT / "src" / "engcore" / "mind" / "minimal").glob("*.py"))
    assert len(files) == 10
    for p in files:
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        committed = subprocess.run(["git", "show", f"{MIND_COMMIT}:{rel}"], cwd=ROOT, capture_output=True, check=True).stdout
        assert p.read_bytes() == committed, rel


def _one(t, cur, z0=0.9, cap=3.0):
    return Trajectory("x", "A", "k", np.asarray(t, float), np.asarray(cur, float), np.zeros(len(t)), np.zeros(len(t)), z0, cap)


def test_forward_model_matches_an_independent_ode_integration():
    t = np.concatenate([np.arange(0, 10, 0.5), np.arange(10, 40, 1.7), np.arange(40, 90, 3.1)])
    cur = np.where((t > 9.9) & (t < 39), 5.0, 0.0)
    cur[(t > 20) & (t < 30)] = 12.0
    R0, R1, C1, cap = 0.02, 0.015, 1500.0, 3.0
    tr = _one(t, cur, cap=cap)
    b = m.Batch.build([tr], "backward")
    knots = np.array([[0.0, 3.0], [1.0, 4.2]])
    spec = m.ModelSpec(True, {"R0": (1e-3, 1), "R1": (1e-4, 1), "C1": (1, 1e6)}, fixed_knots=knots)
    v, _ = m.Evaluator(spec, b).predict(np.log([R0, R1, C1]))
    ref, z, v1 = [3.0 + 1.2 * 0.9 - cur[0] * R0], 0.9, 0.0
    for k in range(1, len(t)):
        i = cur[k]
        sol = solve_ivp(lambda _t, y: [-i / (3600 * cap), i / C1 - y[1] / (R1 * C1)], (t[k - 1], t[k]), [z, v1],
                        method="DOP853", rtol=1e-12, atol=1e-14)
        z, v1 = sol.y[0, -1], sol.y[1, -1]
        ref.append(3.0 + 1.2 * z - i * R0 - v1)
    assert np.max(np.abs(v[0, :len(t)] - np.array(ref))) < 1e-9


def test_analytic_jacobian_matches_finite_differences():
    p = syn.cc_problem()
    spec = m.ModelSpec.from_declared(p.model)
    ev = m.Evaluator(spec, m.Batch.build(p.calibration()[:2], "backward"))
    theta = np.concatenate([np.log([0.05, 0.03, 900.0]), np.linspace(3.2, 4.2, 13)])
    J = ev.jacobian(theta)
    for j in (0, 1, 2, 5, 15):
        h = 1e-6
        e = np.zeros_like(theta); e[j] = h
        fd = (ev.residuals(theta + e) - ev.residuals(theta - e)) / (2 * h)
        assert np.max(np.abs(fd - J[:, j])) < 1e-6 * max(1.0, np.max(np.abs(fd)))


def test_svd_covariance_never_manufactures_identifiability():
    rng = np.random.RandomState(0)
    col = rng.standard_normal(50)
    jac = np.column_stack([col, col, rng.standard_normal(50)])   # two parameters enter only through their sum
    f = m.Fit(None, np.zeros(3), 1.0, 50, [], np.zeros(50), jac)
    cov = m.covariance(f, rho=0.0)
    assert math.isinf(cov[0, 0]) and math.isinf(cov[1, 1]) and math.isfinite(cov[2, 2])


@pytest.mark.expensive
def test_careful_identifies_synthetic_pulses_and_recovers_the_parameters():
    p = syn.pulse_problem()
    rec = baselines.careful(p)
    est = rec["fit"]["parameters"]
    for k, v in syn.TRUE.items():
        assert abs(est[k] / v - 1) < 0.01
    assert rec["answers"]["IDENTIFIABILITY"]["disposition"] == SUPPORTED
    assert rec["answers"]["WITHIN_CELL_GENERALIZATION"]["disposition"] == SUPPORTED
    assert rec["answers"]["CROSS_CELL_TRANSFER"]["disposition"] == NOT_ASSESSABLE


@pytest.mark.expensive
def test_no_arm_supports_identifiability_when_tau_is_far_outside_the_window():
    saved = dict(syn.TRUE)
    try:
        syn.TRUE.update({"C1": 1e5})                               # tau = 3000 s against a 40 s rest
        p = syn.pulse_problem(seed=3)
        assert baselines.careful(p)["answers"]["IDENTIFIABILITY"]["disposition"] != SUPPORTED
        assert mind_arm.mind(p, seeds=(0,))["answers"]["IDENTIFIABILITY"]["disposition"] != SUPPORTED
    finally:
        syn.TRUE.clear(); syn.TRUE.update(saved)


@pytest.mark.expensive
def test_mind_runs_end_to_end_on_synthetic_pulses_and_its_traces_replay():
    p = syn.pulse_problem()
    traces: dict = {}
    rec = mind_arm.mind(p, seeds=(0,), traces=traces)
    assert rec["answers"]["IDENTIFIABILITY"]["disposition"] == SUPPORTED
    assert rec["answers"]["WITHIN_CELL_GENERALIZATION"]["disposition"] == SUPPORTED
    assert rec["answers"]["MODEL_ADEQUACY"]["disposition"] == NOT_ASSESSABLE      # not representable, never filled in
    assert rec["parameters"]["R0"] is None
    run = rec["detail"]["prediction"]["within_cell_heldout/pulses"]["per_seed"]["0"]
    assert run["sealed_pre_result_predictions"] > 0
    rep = mind_arm.replay_traces(p, json.loads(json.dumps(traces)))
    assert rep and all(v["status"] == "VERIFIED" and v["problem_digest_matches"] for v in rep.values())


def test_world_serves_only_recorded_samples_within_tolerance_and_enforces_the_budget():
    pool = mind_arm.Pool(("t_off_s",), ("T_K",), np.array([[1.0], [2.0], [4.0]]), np.array([[300.0]] * 3),
                         np.array([0.1, 0.2, 0.3]), ["a", "b", "c"], 1.0, np.ones(3), "ohm")
    w = mind_arm.PoolWorld(pool, budget=2)
    assert w({"t_off_s": 2.05}, "q0")["y"] == 0.2
    with pytest.raises(ObservationRefused):
        w({"t_off_s": 3.0}, "q1")                                  # 0.288 ln from the nearest unused sample
    assert w({"t_off_s": 1.0}, "q2")["t_off_s"] == 1.0
    with pytest.raises(ObservationRefused) as exc:
        w({"t_off_s": 4.0}, "q3")
    assert exc.value.budget


def test_combine_lets_a_decisive_failure_win_and_never_turns_refusal_into_support():
    assert combine([SUPPORTED, NOT_SUPPORTED, REFUSED]) == NOT_SUPPORTED
    assert combine([SUPPORTED, REFUSED]) == REFUSED
    assert combine([SUPPORTED, NOT_ASSESSABLE]) == NOT_ASSESSABLE
    assert combine([SUPPORTED, REVIEW]) == REVIEW
    assert combine([]) == NOT_ASSESSABLE


def test_pack_matches_its_manifest_and_rebuilds_byte_identically_from_the_pinned_splits():
    problems = load_pack()
    assert sorted(problems) == ["P1", "P2"]
    manifest = json.loads((HERE / "candidate" / "pack" / "MANIFEST.json").read_bytes())
    for pid, builder in (("P1", build_pack.build_p1), ("P2", build_pack.build_p2)):
        problem, _, _ = builder()
        raw = (json.dumps(problem, sort_keys=True, indent=1, allow_nan=False) + "\n").encode()
        assert hashlib.sha256(raw).hexdigest() == manifest["problems"][pid]["sha256"]
    assert problems["P2"].heldout("cross_cell_heldout") is None


def test_static_leakage_audit_passes_on_the_candidate_and_catches_planted_leaks(tmp_path):
    assert leakage.static_findings(leakage.candidate_files()) == []
    assert leakage.schema_findings() == []
    planted = tmp_path / "planted.py"
    src = (HERE / "candidate" / "baselines.py").read_bytes().decode()
    for token in ("B0006", "NOT_IDENTIFIABLE", "battery_1rc_closure", "70ffb357511d"):
        planted.write_bytes((src + f"\n# {token}\n").encode())
        assert leakage.static_findings([planted]) and token in leakage.static_findings([planted])[0]["tokens"]
    planted.write_bytes(b"R0 = 0.132\n")
    assert leakage.static_findings([planted], extra=[r"(?<![\d.])0\.132(?![\d])"])
    pack = tmp_path / "pack"
    pack.mkdir()
    p1 = json.loads((HERE / "candidate" / "pack" / "P1.json").read_bytes())
    p1["sets"]["calibration"]["trajectories"][0]["verdict"] = "FAIL"
    (pack / "P1.json").write_bytes(json.dumps(p1).encode())
    assert leakage.schema_findings(pack) == [{"file": "P1.json", "unexpected_key": "verdict"}]


def test_runtime_leakage_audit_refuses_history_paths_and_evaluator_modules(tmp_path):
    clean = {"opened": [[str(HERE / "candidate" / "pack" / "P1.json"), "rb"]], "modules": ["numpy"]}
    r = leakage.runtime_findings(clean, tmp_path)
    assert not r["paths_outside_roots"] and not r["forbidden_modules"]
    dirty = {"opened": [[str(ROOT / "benchmarks" / "battery_1rc_closure" / "results" / "CALIBRATION.json"), "rb"],
                        [str(HERE / "evaluator" / "IDENTITY_MAP.json"), "rb"]],
             "modules": ["benchmarks.battery_rediscovery_v0.evaluator.truth", "benchmarks.battery_1rc_closure.fit"]}
    r = leakage.runtime_findings(dirty, tmp_path)
    assert len(r["paths_outside_roots"]) == 2 and len(r["forbidden_modules"]) == 2


def test_evaluator_refuses_to_read_history_without_a_committed_seal(tmp_path):
    with pytest.raises(truth.SealNotVerified):
        truth.extract(tmp_path)
    (tmp_path / "SEAL.json").write_bytes(b'{"status": "PASS"}\n')
    with pytest.raises((truth.SealNotVerified, ValueError)):
        truth.extract(tmp_path)


def test_outcome_classes():
    assert score.outcome(SUPPORTED, SUPPORTED) == "CORRECT"
    assert score.outcome(NOT_SUPPORTED, NOT_SUPPORTED) == "CORRECT"
    assert score.outcome(REFUSED, NOT_ASSESSABLE) == "CORRECT_REFUSAL"
    assert score.outcome(NOT_ASSESSABLE, NOT_ASSESSABLE) == "CORRECT_REFUSAL"
    assert score.outcome(SUPPORTED, NOT_ASSESSABLE) == "FALSE_SUPPORT"
    assert score.outcome(SUPPORTED, NOT_SUPPORTED) == "FALSE_SUPPORT"
    assert score.outcome(NOT_SUPPORTED, SUPPORTED) == "FALSE_REJECT"
    assert score.outcome(NOT_SUPPORTED, NOT_ASSESSABLE) == "UNSUPPORTED_DECISION"
    assert score.outcome(REVIEW, NOT_SUPPORTED) == "FALSE_REFUSE"
    assert score.outcome(SUPPORTED, None) == "UNSCORED"


def _scores(totals: dict[str, tuple[int, int]]) -> dict:
    out = {}
    for arm, (correct, false_support) in totals.items():
        counts = {k: 0 for k in score.OUTCOMES}
        counts["CORRECT"], counts["FALSE_SUPPORT"] = correct, false_support
        out[arm] = {"counts": counts, "correct_total": correct, "scored": 10}
    return out


def test_conclusion_rule_order():
    mind = {}                                                     # no non-committal answers to attribute
    t = {"table": {}}
    base = {"MIND": (5, 0), "FIXED_FIT": (3, 3), "CAREFUL_BASELINE": (4, 0), "ALWAYS_FIT": (1, 8), "ALWAYS_REFUSE": (2, 0)}
    kw = dict(mind=mind, truth=t)
    assert score.conclusion(leakage_ok=False, mind_end_to_end=True, mind_replay_ok=True, scores=_scores(base),
                            **kw)["conclusion"] == "LEAKAGE_INVALIDATED"
    assert score.conclusion(leakage_ok=True, mind_end_to_end=True, mind_replay_ok=False, scores=_scores(base),
                            **kw)["conclusion"] == "INCONCLUSIVE"
    assert score.conclusion(leakage_ok=True, mind_end_to_end=True, mind_replay_ok=True, scores=_scores(base),
                            **kw)["conclusion"] == "PROMISING_SIGNAL"
    worse = dict(base, MIND=(5, 1))
    assert score.conclusion(leakage_ok=True, mind_end_to_end=True, mind_replay_ok=True, scores=_scores(worse),
                            **kw)["conclusion"] == "NO_MEASURED_ADVANTAGE"
    easy = dict(base, MIND=(2, 0), ALWAYS_REFUSE=(5, 0))
    assert score.conclusion(leakage_ok=True, mind_end_to_end=True, mind_replay_ok=True, scores=_scores(easy),
                            **kw)["conclusion"] == "BENCHMARK_TOO_EASY"


def test_candidate_code_imports_nothing_from_the_evaluator_or_history():
    for p in (HERE / "candidate").glob("*.py"):
        text = p.read_bytes().decode()
        for bad in ("evaluator", "leakage", "build_pack", "battery_1rc", "nasa_battery", "IDENTITY_MAP"):
            assert f"import {bad}" not in text and f"from .{bad}" not in text and f".{bad} import" not in text, (p.name, bad)


def test_plan_is_frozen_and_pins_every_file():
    plan_raw = (HERE / "PLAN.json").read_bytes()
    assert hashlib.sha256(plan_raw).hexdigest() == (HERE / "PLAN.sha256").read_bytes().split()[0].decode()
    plan = json.loads(plan_raw)
    from benchmarks.battery_rediscovery_v0 import freeze
    assert plan["frozen_files"] == freeze.frozen_digests()
    assert plan["mind"]["source_commit"] == MIND_COMMIT
