"""Operator timing must measure isolated startup; diagnostics have no authority."""
from __future__ import annotations

from benchmarks.genesis_lite import harness_v4 as h4, isolated_host as ih
import json
import queue

import pytest


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


def _fake_host(diagnostics):
    host = object.__new__(ih.IsolatedProposerHost)
    host._diagnostics = diagnostics
    host._timeout = 1.0
    host._started = 0.0
    host.timing = {"diagnostic_events_untrusted": []}
    host._lines = queue.Queue()
    host.stderr_tail = lambda: ""
    host.close = lambda: None
    return host


def test_unrequested_diagnostics_are_not_a_new_protocol_channel():
    host = _fake_host(False)
    host._lines.put(json.dumps({"op": "diagnostic"}).encode())
    with pytest.raises(RuntimeError, match="unsolicited"):
        host._recv()


def test_diagnostics_do_not_restart_the_receive_deadline(monkeypatch):
    host = _fake_host(True)
    ticks = iter((0.0, 0.0, 0.6, 1.1))
    monkeypatch.setattr(ih.time, "monotonic", lambda: next(ticks))
    for _ in range(3):
        host._lines.put(json.dumps({"op": "diagnostic"}).encode())
    with pytest.raises(RuntimeError, match="within 1.0"):
        host._recv()
    assert len(host.timing["diagnostic_events_untrusted"]) == 2
