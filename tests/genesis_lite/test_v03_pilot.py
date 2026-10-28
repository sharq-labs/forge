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
