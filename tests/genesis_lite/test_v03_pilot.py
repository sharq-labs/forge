"""Genesis-lite v0.3 DEVELOPMENT cost pilot runner (owner-approved 2026-10-28: 30-minute cap, 4 workers).

Measurement only: the summary reports cost and validity per arm and labels any credit as descriptive development output,
never a rate, a lift or a benchmark result.
"""

from __future__ import annotations

import json

import pytest


def test_the_plan_runs_every_arm_on_a_world_set_before_the_next_one():
    from benchmarks.genesis_lite.pilot_v3 import plan
    tasks = plan(["a", "b", "c"], campaigns=2, presentations=("anonymous", "renamed"), seeds=(0,))
    assert len(tasks) == 3 * 2 * 2
    first = tasks[:3]
    assert [t.arm for t in first] == ["a", "b", "c"] and len({(t.campaign, t.presentation, t.seed) for t in first}) == 1


def test_world_sets_are_paired_across_arms_and_never_reused():
    from benchmarks.genesis_lite.pilot_v3 import master_seed
    root = bytes(32)
    assert master_seed(root, 0, "anonymous", 0) == master_seed(root, 0, "anonymous", 0)
    seeds = {master_seed(root, i, p, s) for i in range(3) for p in ("anonymous", "renamed") for s in (0, 1)}
    assert len(seeds) == 12


def test_a_zero_deadline_runs_nothing_and_says_so(tmp_path):
    from benchmarks.genesis_lite.pilot_v3 import run_pilot
    summary = run_pilot(["always_refuse"], out=tmp_path, campaigns=1, presentations=("anonymous",), seeds=(0,),
                        workers=1, deadline_seconds=0.0, root=bytes(32))
    assert summary["arms"]["always_refuse"]["not_run"] == 1 and summary["arms"]["always_refuse"]["runs"] == 0
    assert summary["readiness"] == "DEVELOPMENT_ONLY" and summary["claims"] == "COST_MEASUREMENT_ONLY"


def test_an_unavailable_arm_is_recorded_not_substituted(tmp_path, monkeypatch):
    from benchmarks.genesis_lite import pilot_v3
    monkeypatch.setattr(pilot_v3, "arm_available", lambda name: name != "pysr_symbolic")
    summary = pilot_v3.run_pilot(["pysr_symbolic"], out=tmp_path, campaigns=1, presentations=("anonymous",), seeds=(0,),
                                 workers=1, deadline_seconds=60.0, root=bytes(32))
    assert summary["arms"]["pysr_symbolic"]["status"] == "ARM_UNAVAILABLE"
    assert summary["arms"]["pysr_symbolic"]["runs"] == 0


def test_a_tiny_pilot_writes_runs_summary_and_environment(tmp_path):
    from benchmarks.genesis_lite.pilot_v3 import run_pilot
    summary = run_pilot(["always_refuse", "careful"], out=tmp_path, campaigns=1, presentations=("anonymous",),
                        seeds=(0,), workers=1, deadline_seconds=120.0, root=bytes(32))
    runs = [json.loads(line) for line in (tmp_path / "runs.jsonl").read_text().splitlines()]
    assert len(runs) == 2 and {r["arm"] for r in runs} == {"always_refuse", "careful"}
    assert json.loads((tmp_path / "summary.json").read_text()) == summary
    env = json.loads((tmp_path / "environment.json").read_text())
    assert env["root_commitment_sha256"] and "library_versions" in env and env["workers"] == 1
    for name in ("always_refuse", "careful"):
        arm = summary["arms"][name]
        assert arm["runs"] == 1 and arm["valid"] == 1 and arm["wall_seconds_total"] >= 0
        assert arm["descriptive_credit"]["label"].startswith("DEVELOPMENT_DESCRIPTIVE")
    assert summary["paired_world_sets_complete"] == 1


def test_parallel_workers_are_pinned_to_one_thread_and_the_environment_says_so(tmp_path):
    # smoke run 2026-10-28: BoTorch took 318 s per campaign with 4 unpinned workers (1.6 s alone): thread oversubscription
    from benchmarks.genesis_lite.pilot_v3 import THREAD_LIMITS, run_pilot
    assert {"OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "JULIA_NUM_THREADS"} <= set(THREAD_LIMITS)
    assert set(THREAD_LIMITS.values()) == {"1"}
    run_pilot(["always_refuse"], out=tmp_path, campaigns=1, presentations=("anonymous",), seeds=(0,), workers=2,
              deadline_seconds=120.0, root=bytes(32))
    env = json.loads((tmp_path / "environment.json").read_text())
    assert env["worker_thread_limits"] == THREAD_LIMITS


# ---- review round 2 (2026-10-28) ----------------------------------------------------------------------------------------
def _rec(arm, campaign, status="VALID", wall=1.0, credit=1.0, answer="no_law", rss=100, rationale="r", reasons=()):
    return {"arm": arm, "status": status, "reasons": list(reasons), "wall_seconds": wall, "observe_calls": 3,
            "worker_maxrss_kib": rss, "v3_total_credit": credit,
            "universes": [{"kind": "no_solution", "answer": answer, "outcome": answer, "credit": credit,
                           "rationale": rationale}],
            "task": {"arm": arm, "campaign": campaign, "presentation": "anonymous", "seed": 0}}


def test_credit_is_compared_only_on_world_sets_every_arm_completed_validly():
    from benchmarks.genesis_lite.pilot_v3 import _summarize
    recs = [_rec("a", 0, credit=1.0), _rec("b", 0, credit=-1.0),
            _rec("a", 1, credit=1.0), _rec("b", 1, status="INVALID_BENCHMARK", credit=5.0, reasons=["separate v0.3 evaluator"])]
    s = _summarize(["a", "b"], {"a": True, "b": True}, recs, [], [], ("anonymous",), (0,), 2, 1.0, 1, 10.0, planned=4)
    assert s["paired_world_sets_complete"] == 1
    assert s["arms"]["a"]["descriptive_credit"]["paired_mean_total"] == 1.0
    assert s["arms"]["b"]["descriptive_credit"]["paired_mean_total"] == -1.0
    assert s["arms"]["a"]["descriptive_credit"]["paired_world_sets"] == 1
    assert s["excluded_world_sets"] and s["excluded_world_sets"][0]["invalid_arms"] == ["b"]


def test_the_cost_estimate_never_hides_missing_or_failed_measurements():
    from benchmarks.genesis_lite.pilot_v3 import _summarize
    from benchmarks.genesis_lite.pilot_v3 import Task
    recs = [_rec("a", 0, wall=2.0), _rec("a", 1, wall=0.1, answer="inadmissible", rationale="ImportError: no julia")]
    s = _summarize(["a", "slow"], {"a": True, "slow": True}, recs, [], [Task("slow", 0, "anonymous", 0)], ("anonymous",),
                   (0,), 2, 1.0, 1, 10.0, planned=3)
    assert s["arms"]["a"]["cost_basis_runs"] == 1 and s["arms"]["a"]["wall_seconds_mean_clean"] == 2.0
    assert s["arms"]["a"]["library_failure_universes"] == 1
    assert s["formal_tier_estimate"]["status"] == "INCOMPLETE" and s["formal_tier_estimate"]["arms_without_measurement"] == ["slow"]


def test_unmeasured_memory_is_reported_as_unmeasured_not_zero():
    from benchmarks.genesis_lite.pilot_v3 import _summarize
    s = _summarize(["a"], {"a": True}, [_rec("a", 0, rss=None)], [], [], ("anonymous",), (0,), 1, 1.0, 1, 10.0, planned=1)
    assert s["arms"]["a"]["worker_rss_high_water_kib"] == "UNMEASURED"
    assert s["worker_rss_high_water_kib_pool"] == "UNMEASURED"


def test_every_planned_task_is_accounted_for_even_when_the_deadline_cuts_in(tmp_path, monkeypatch):
    import concurrent.futures as cf
    import time
    from benchmarks.genesis_lite import pilot_v3

    def slow_work(task, master_hex):
        time.sleep(0.3)
        return {**_rec(task.arm, task.campaign), "task": {"arm": task.arm, "campaign": task.campaign,
                                                           "presentation": task.presentation, "seed": task.seed}}

    monkeypatch.setattr(pilot_v3, "_work", slow_work)
    monkeypatch.setattr(pilot_v3, "_executor", lambda workers: cf.ThreadPoolExecutor(max_workers=workers))
    monkeypatch.setattr(pilot_v3, "GRACE_SECONDS", 0.05)
    s = pilot_v3.run_pilot(["always_refuse"], out=tmp_path, campaigns=6, presentations=("anonymous",), seeds=(0,),
                           workers=2, deadline_seconds=0.5, root=bytes(32))
    t = s["tasks"]
    assert t["planned"] == 6 and t["completed"] + t["not_run"] + t["interrupted"] == 6


def test_a_worker_failure_is_recorded_not_lost(tmp_path, monkeypatch):
    import concurrent.futures as cf
    from benchmarks.genesis_lite import pilot_v3

    def work(task, master_hex):
        if task.campaign == 1:
            raise RuntimeError("worker died")
        return {**_rec(task.arm, task.campaign), "task": {"arm": task.arm, "campaign": task.campaign,
                                                           "presentation": task.presentation, "seed": task.seed}}

    monkeypatch.setattr(pilot_v3, "_work", work)
    monkeypatch.setattr(pilot_v3, "_executor", lambda workers: cf.ThreadPoolExecutor(max_workers=workers))
    s = pilot_v3.run_pilot(["always_refuse"], out=tmp_path, campaigns=2, presentations=("anonymous",), seeds=(0,),
                           workers=2, deadline_seconds=30.0, root=bytes(32))
    assert s["arms"]["always_refuse"]["worker_failures"] == 1
    assert s["tasks"]["completed"] == 1 and s["tasks"]["worker_failed"] == 1
    assert s["formal_tier_estimate"]["status"] == "LOWER_BOUND"


def test_workers_receive_only_their_campaign_seed_and_report_threads_in_force(tmp_path):
    import inspect
    from benchmarks.genesis_lite import pilot_v3
    assert list(inspect.signature(pilot_v3._work).parameters) == ["task", "master_seed_hex"]
    assert "pilot_v3.py" in __import__("benchmarks.genesis_lite.harness_v3", fromlist=["V3_FILES"]).V3_FILES
    pilot_v3.run_pilot(["always_refuse"], out=tmp_path, campaigns=1, presentations=("anonymous",), seeds=(0,), workers=2,
                       deadline_seconds=120.0, root=bytes(32))
    run = json.loads((tmp_path / "runs.jsonl").read_text().splitlines()[0])
    assert run["threads_in_force"]["blas_max"] in (1, None)


def test_a_duplicated_arm_name_is_refused(tmp_path):
    from benchmarks.genesis_lite.pilot_v3 import run_pilot
    with pytest.raises(ValueError):
        run_pilot(["careful", "careful"], out=tmp_path / "unused", campaigns=1, workers=1, deadline_seconds=1.0, root=bytes(32))


# ---- review round 3 (2026-10-29) ----------------------------------------------------------------------------------------
def _small_run(tmp_path, campaigns=2):
    from benchmarks.genesis_lite.pilot_v3 import run_pilot
    return run_pilot(["always_refuse"], out=tmp_path, campaigns=campaigns, presentations=("anonymous",), seeds=(0,),
                     workers=1, deadline_seconds=120.0, root=bytes(32))


def test_resummarize_takes_design_and_availability_from_the_run_not_this_machine(tmp_path, monkeypatch):
    from benchmarks.genesis_lite import pilot_v3
    _small_run(tmp_path)
    monkeypatch.setattr(pilot_v3, "arm_available", lambda name: False)      # a machine without the arm
    s = pilot_v3.resummarize(tmp_path, ["always_refuse"])                    # CLI defaults would plan 120 tasks
    assert s["tasks"]["planned"] == 2 and s["arms"]["always_refuse"]["status"] == "AVAILABLE"
    assert s["formal_tier_estimate"]["status"] == "ESTIMATE"


def test_resummarize_of_a_run_missing_records_is_a_lower_bound(tmp_path):
    from benchmarks.genesis_lite import pilot_v3
    _small_run(tmp_path)
    runs = (tmp_path / "runs.jsonl").read_text().splitlines()
    (tmp_path / "runs.jsonl").write_text(runs[0] + "\n")
    s = pilot_v3.resummarize(tmp_path, ["always_refuse"])
    assert s["tasks"]["missing_records"] == 1 and s["formal_tier_estimate"]["status"] == "LOWER_BOUND"


def test_resummarize_identifies_the_code_that_summarized_and_the_run_it_read(tmp_path):
    from benchmarks.genesis_lite import pilot_v3
    _small_run(tmp_path)
    src = pilot_v3.resummarize(tmp_path, ["always_refuse"])["resummarized_from"]
    assert len(src["summarizer_sha256"]) == 64 and src["summarizer_git_head"] and src["run_git_head"]


def test_a_failed_worker_contributes_no_observation_count():
    from benchmarks.genesis_lite.pilot_v3 import Task, _failure_record, _summarize
    recs = [_rec("a", 0), _failure_record(Task("a", 1, "anonymous", 0), RuntimeError("x"))]
    s = _summarize(["a"], {"a": True}, recs, [], [], ("anonymous",), (0,), 2, 1.0, 1, 10.0, planned=2)
    assert s["arms"]["a"]["observe_calls_mean"] == 3.0


def test_the_estimate_states_its_scope():
    from benchmarks.genesis_lite.pilot_v3 import _summarize
    est = _summarize(["a"], {"a": True}, [_rec("a", 0)], [], [], ("anonymous",), (0,), 1, 1.0, 4, 10.0,
                     planned=1)["formal_tier_estimate"]
    assert "arms planned here" in est["scope"] and "in_process" in est["scope"] and "Mind arms UNMEASURED" in est["scope"]
    assert "concurrent workers" in est["label"]
    mind = _summarize(["mind_full"], {"mind_full": True}, [_rec("mind_full", 0)], [], [], ("anonymous",), (0,), 1, 1.0,
                      4, 10.0, planned=1)["formal_tier_estimate"]
    assert "Mind arms included (EXC-2)" in mind["scope"]


def test_the_parent_environment_is_restored_and_workers_run_one_blas_thread(tmp_path, monkeypatch):
    import importlib.util
    import os
    from benchmarks.genesis_lite import pilot_v3
    monkeypatch.setenv("OMP_NUM_THREADS", "7")
    pilot_v3.run_pilot(["always_refuse"], out=tmp_path, campaigns=1, presentations=("anonymous",), seeds=(0,), workers=2,
                       deadline_seconds=120.0, root=bytes(32))
    assert os.environ["OMP_NUM_THREADS"] == "7"
    run = json.loads((tmp_path / "runs.jsonl").read_text().splitlines()[0])
    if importlib.util.find_spec("threadpoolctl") is not None:
        assert run["threads_in_force"]["blas_max"] == 1
