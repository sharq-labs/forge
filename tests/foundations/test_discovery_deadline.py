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
