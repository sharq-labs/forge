"""Real pipes and child processes: the deadline includes handshake, output and descendants."""

import os
import socket
import subprocess
import sys
import time

import pytest

from engcore.blindfold import isolation

pytestmark = pytest.mark.skipif(os.name != "posix", reason="isolated Discovery uses POSIX pipes and process sessions")


def _launcher(monkeypatch, tmp_path, script):
    original = subprocess.Popen
    launched = []

    def launch(_cmd, **kwargs):
        proc = original([sys.executable, "-u", "-c", script], **kwargs)
        launched.append(proc)
        return proc

    monkeypatch.setattr(isolation.subprocess, "Popen", launch)
    monkeypatch.setattr(isolation, "_leaf", lambda pid: pid)
    monkeypatch.setattr(isolation, "_inspect", lambda pid, store: {"inspected": True, "pid": pid})
    escrow = object.__new__(isolation.IsolatedEscrow)
    escrow.storage_dir = tmp_path
    left, right = socket.socketpair()
    escrow._discovery_end = left
    return escrow, launched, (left, right)


@pytest.mark.parametrize("script", [
    "import time; time.sleep(30)",  # no readiness line
    "import sys,time; sys.stdin.readline(); print('{\"ready\":true}'); sys.stdin.readline(); time.sleep(30)",
    "import sys,subprocess; sys.stdin.readline(); print('{\"ready\":true}'); sys.stdin.readline(); "
    "subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])",  # leader exits, inherited pipes remain
])
def test_timeout_covers_handshake_output_and_inherited_pipes(monkeypatch, tmp_path, script):
    escrow, launched, sockets = _launcher(monkeypatch, tmp_path, script)
    started = time.monotonic()
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            escrow.run_discovery({}, timeout=0.5)
        assert time.monotonic() - started < 4
        assert launched[0].poll() is not None
        assert all(s.closed for s in (launched[0].stdin, launched[0].stdout, launched[0].stderr))
        # An orphan may remain a zombie until init reaps it; it must not be running.
        from pathlib import Path
        for stat in Path("/proc").glob("[0-9]*/stat"):
            try:
                fields = stat.read_text().rsplit(")", 1)[1].split()
            except (FileNotFoundError, ProcessLookupError):
                continue
            if int(fields[2]) == launched[0].pid:  # state, ppid, process group
                assert fields[0] == "Z"
    finally:
        for sock in sockets:
            sock.close()


def test_stderr_is_drained_while_waiting_for_readiness_and_permission(monkeypatch, tmp_path):
    script = ("import sys,json; task=json.loads(sys.stdin.readline()); "
              "sys.stderr.write('x'*200000); sys.stderr.flush(); print('{\"ready\":true}'); "
              "assert sys.stdin.readline()=='go\\n'; print(json.dumps({'task':task['number']}))")
    escrow, launched, sockets = _launcher(monkeypatch, tmp_path, script)
    try:
        result, outside = escrow.run_discovery({"number": 7}, timeout=4)
        assert result == {"task": 7}
        assert outside == {"inspected": True, "pid": launched[0].pid}
    finally:
        for sock in sockets:
            sock.close()


@pytest.mark.parametrize("script, task", [
    ("import time; time.sleep(30)", {"large": "x" * 2000000}),
    ("import sys,os,time; sys.stdin.readline(); print('{\"ready\":true}'); "
     "sys.stdin.readline(); os.close(1); os.close(2); time.sleep(30)", {}),
])
def test_deadline_also_bounds_task_writes_and_exit_after_output_eof(monkeypatch, tmp_path, script, task):
    escrow, launched, sockets = _launcher(monkeypatch, tmp_path, script)
    started = time.monotonic()
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            escrow.run_discovery(task, timeout=0.5)
        assert time.monotonic() - started < 4
        assert launched[0].poll() is not None
    finally:
        for sock in sockets:
            sock.close()


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), True])
def test_invalid_deadline_is_refused_before_launch(timeout):
    with pytest.raises(ValueError, match="finite and positive"):
        object.__new__(isolation.IsolatedEscrow).run_discovery({}, timeout=timeout)


def test_process_group_wait_reports_survivor_pid(monkeypatch):
    from pathlib import Path
    from engcore.blindfold import isolation

    original_glob = Path.glob
    original_read = Path.read_text
    stat_path = Path("/proc/4242/stat")
    monkeypatch.setattr(Path, "glob", lambda self, pattern: [stat_path] if self == Path("/proc") else original_glob(self, pattern))
    monkeypatch.setattr(Path, "read_text", lambda self, *a, **k: "4242 (hostile child) R 1 99 77 0" if self == stat_path else original_read(self, *a, **k))
    ticks = [0.0]
    def advance_clock():
        ticks[0] += 6.0
        return ticks[0]
    monkeypatch.setattr(isolation.time, "monotonic", advance_clock)
    with pytest.raises(RuntimeError, match=r"live members \['4242'\]"):
        isolation._wait_process_group_stopped(99, timeout=5)


def test_process_group_wait_fails_closed_on_malformed_proc_observation(monkeypatch):
    from pathlib import Path
    from engcore.blindfold import isolation

    original_glob = Path.glob
    original_read = Path.read_text
    stat_path = Path("/proc/4242/stat")
    monkeypatch.setattr(Path, "glob", lambda self, pattern: [stat_path] if self == Path("/proc") else original_glob(self, pattern))
    monkeypatch.setattr(Path, "read_text", lambda self, *a, **k: "malformed" if self == stat_path else original_read(self, *a, **k))
    with pytest.raises(RuntimeError, match="cannot parse process-group observation"):
        isolation._wait_process_group_stopped(77, timeout=5)


def test_process_group_cleanup_reaps_leader_even_when_observation_fails(monkeypatch):
    from engcore.blindfold import isolation

    waited = []
    class Process:
        pid = 4242
        def wait(self, *, timeout):
            waited.append(timeout)
            return -9

    monkeypatch.setattr(isolation.os, "killpg", lambda pid, sig: None)
    def fail_observation(*args, **kwargs):
        raise RuntimeError("synthetic observation failure")
    monkeypatch.setattr(isolation, "_wait_process_group_stopped", fail_observation)
    with pytest.raises(RuntimeError, match="group observation failed"):
        isolation._stop_discovery_process_group(Process())
    assert waited == [5]
