"""Operator timing must measure isolated startup; diagnostics have no authority."""
from __future__ import annotations

from benchmarks.genesis_lite import harness_v4 as h4, isolated_host as ih


def test_profile_is_opt_in_and_the_pinned_host_is_unchanged():
    plain = ih.command([], {})[-1]
    profiled = ih.command([], {"FORGE_PERF_DIAGNOSTICS": "1"})[-1]
    assert "proposer_profile_v4.py" not in plain
    assert "proposer_profile_v4.py" in profiled
    assert "proposer_profile_v4.py" in h4.V4_FILES
    assert "telemetry_v4.py" in h4.V4_FILES


def test_isolated_startup_replaces_inherited_zero_and_keeps_checks_separate(monkeypatch):
    class Record:
        def to_dict(self):
            return {"status": "INVALID_BENCHMARK", "host_start_seconds": 0.0}

    def arm(spec, hidden, checks, *, timings, **kwargs):
        timings.extend([{"launch_to_hello_seconds": 1.25}, {"launch_to_hello_seconds": 2.5}])
        return lambda *a, **kw: {}

    monkeypatch.setattr(h4, "per_universe_arm", arm)
    monkeypatch.setattr(h4.h3, "run_one_v3", lambda *a, **kw: Record())
    monkeypatch.setattr(h4, "development_identity_v4", lambda: ("id", []))
    rec = h4.run_one_v4("careful", "careful", master_seed=b"public", campaign_id="public", presentation="anonymous", hidden=[])
    assert rec["host_start_seconds"] == 3.75
    assert rec["campaign_total_seconds"] >= 0
    assert not rec["isolation_checks"]
    assert rec["status"] == "INVALID_BENCHMARK"
