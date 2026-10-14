"""Hostile checks for the local-only assurance execution path."""

from __future__ import annotations

import pathlib

import pytest

from tools.certification import branch_policy
from tools.certification.local_assurance import (
    LocalAssuranceError,
    _build_evidence_manifest,
    _require_clean,
    _require_head,
    _resolve_python,
    _verify_evidence_manifest,
)

REPO = pathlib.Path(__file__).resolve().parents[1]


#: Hostile review F8: the CI control plane runs automatically (CLAUDE.md, CI policy) -- every pull request
#: is classified and tested, certificate-sensitive ones are recertified, pushes to main rerun the merged-tree
#: checks and the branch policy. Manual dispatch stays as an explicit fallback; nothing runs on a schedule.
WORKFLOW_TRIGGERS = {
    ".github/workflows/tests.yml": {"pull_request", "push", "workflow_dispatch"},
    ".github/workflows/recertify-hardened-core.yml": {"pull_request", "workflow_dispatch"},
    ".github/workflows/branch-policy.yml": {"push", "workflow_dispatch"},
    ".github/workflows/trust-mutations.yml": {"workflow_dispatch"},
}


@pytest.mark.parametrize("workflow", sorted(WORKFLOW_TRIGGERS))
def test_github_workflows_trigger_as_the_ci_policy_requires(workflow):
    text = (REPO / workflow).read_text(encoding="utf-8")
    block = text.split("\non:\n", 1)[1].split("\n\n", 1)[0]
    triggers = {line.strip().rstrip(":") for line in block.splitlines() if line.startswith("  ") and not line.startswith("    ")}
    assert triggers == WORKFLOW_TRIGGERS[workflow]
    if "push" in triggers:
        assert "branches: [main]" in block  # a push anywhere else is not the merged tree
    assert "paths" not in block  # classification, not a path filter, decides what a change needs


def test_forge_policy_requires_no_github_status_checks():
    assert branch_policy.REQUIRED_STATUS_CHECKS == ()
    required = branch_policy.POLICY["rules"]["required_status_checks"]["required_status_checks"]
    assert required == []


def test_missing_required_python_is_refused(tmp_path):
    with pytest.raises(LocalAssuranceError, match="was not found"):
        _resolve_python("definitely-not-a-python-executable", tmp_path, "3.11")


def test_dirty_tree_is_refused(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "tracked.txt").write_text("clean\n", encoding="utf-8")
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "add", "tracked.txt"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "commit", "-q", "-m", "source"], cwd=root, check=True)
    (root / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(LocalAssuranceError, match="dirty"):
        _require_clean(root, "test")


def test_changed_head_is_refused(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "tracked.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "add", "tracked.txt"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "commit", "-q", "-m", "one"], cwd=root, check=True)
    first = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True,
                           capture_output=True, text=True).stdout.strip()
    (root / "tracked.txt").write_text("two\n", encoding="utf-8")
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "add", "tracked.txt"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "commit", "-q", "-m", "two"], cwd=root, check=True)
    with pytest.raises(LocalAssuranceError, match="HEAD moved"):
        _require_head(root, first, "test")


def test_frozen_evidence_manifest_detects_tampering(tmp_path):
    import subprocess

    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "pyproject.toml").write_text("[project]\nname='x'\nversion='0'\n", encoding="utf-8")
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "add", "pyproject.toml"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "commit", "-q", "-m", "source"], cwd=root, check=True)
    source = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True,
                            capture_output=True, text=True).stdout.strip()

    evidence = tmp_path / "run" / "evidence"
    evidence.mkdir(parents=True)
    artifact = evidence / "gate.json"
    artifact.write_text('{"ok": true}\n', encoding="utf-8")
    manifest, digest, count = _build_evidence_manifest(root, source, evidence)
    assert _verify_evidence_manifest(manifest, evidence) == (digest, count)

    artifact.write_text('{"ok": false}\n', encoding="utf-8")
    with pytest.raises(LocalAssuranceError, match="changed after"):
        _verify_evidence_manifest(manifest, evidence)


@pytest.mark.parametrize("workers", [1, 2])
@pytest.mark.parametrize("family,count", [("formal_mutations", 4), ("v4_mutations", 8)])
@pytest.mark.parametrize("fail", [False, True])
def test_shards_are_bounded_isolated_and_fail_closed(tmp_path, monkeypatch, workers, family, count, fail):
    import threading
    import time
    from tools.certification import local_assurance as la
    root = tmp_path / "repo"
    root.mkdir()
    evidence = root / ".forge" / "assurance" / "source" / "evidence"
    active = 0
    peak = 0
    paths = []
    owners = []
    completed = []
    lock = threading.Lock()
    overlap = threading.Barrier(2) if workers == 2 else None

    def job(index):
        nonlocal active, peak
        name = f"{family}_{index}"
        directory = la._gate_dir(evidence, "source", name)
        with la._mutation_scratch(root, name) as scratch:
            with lock:
                active += 1
                peak = max(peak, active)
                paths.append(scratch)
                owners.append(directory)
            try:
                scratch.mkdir()
                (scratch / "mutant").write_text(name)
                if overlap and index < 2:
                    overlap.wait(timeout=5)
                time.sleep(0.01)
                (directory / "owner").write_text(name)
                if fail and index == 0:
                    raise RuntimeError("synthetic shard failure")
                completed.append(index)
            finally:
                with lock:
                    active -= 1

    jobs = [(f"{family}_{i}", lambda i=i: job(i)) for i in range(count)]
    if fail:
        with pytest.raises((la.LocalAssuranceError, RuntimeError), match="synthetic shard failure") as caught:
            la._mutation_group(jobs, workers)
        if workers == 2:
            assert f"{family}_0" in str(caught.value)
            assert isinstance(caught.value.__cause__, RuntimeError)
    else:
        la._mutation_group(jobs, workers)
    assert peak == workers
    assert active == 0
    assert len(paths) == len(set(paths))
    assert len(owners) == len(set(owners))
    for path in paths:
        assert root not in path.parents
        failed_path = fail and (path / "mutant").exists() and (path / "mutant").read_text() == f"{family}_0"
        assert path.parent.exists() == bool(failed_path)
        if failed_path:
            import shutil
            shutil.rmtree(path.parent)
    for directory in owners:
        assert (directory / "owner").read_text().replace("_", "-") in directory.name
    if workers == 1:
        assert completed == ([] if fail else list(range(count)))
    elif fail:
        assert 1 in completed


def test_repository_local_tmpdir_is_refused_and_retained(tmp_path, monkeypatch):
    import tempfile
    from tools.certification import local_assurance as la
    from tools.certification.mutation_workspace import WorkspaceError
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(root))
    with pytest.raises(WorkspaceError, match="must not overlap source"):
        with la._mutation_scratch(root, "v4_mutations_0"):
            pytest.fail("repository-local scratch reached mutation execution")
    retained = list(root.iterdir())
    assert len(retained) == 1 and retained[0].is_dir()
    import shutil
    shutil.rmtree(retained[0])


def test_failure_diagnostics_preserve_late_completed_timings(tmp_path):
    import json
    from tools.certification import local_assurance as la
    path = tmp_path / "failure.json"
    tracker = la._GateTracker(path, "source", "tree", "started")
    tracker.completed("fast311", 1.25)
    tracker.failure("v4_mutations_0", ValueError("broken shard"))
    tracker.completed("v4_mutations_1", 2.5)
    doc = json.loads(path.read_text())
    assert doc["schema"] == la.FAILURE_SCHEMA
    assert doc["status"] == "REFUSED"
    assert doc["certifying"] is False and doc["safe_to_push"] is False
    assert doc["source_commit"] == "source" and doc["source_tree"] == "tree"
    assert doc["started_at"] == "started"
    assert doc["failed_gate"] == "v4_mutations_0"
    assert doc["failure_message"] == "ValueError: broken shard"
    assert doc["gate_seconds"] == {"fast311": 1.25, "v4_mutations_1": 2.5}


@pytest.mark.parametrize("schema,status", [
    ("forge.local_assurance_failure/1", "REFUSED"),
    ("forge.local_assurance_receipt/1", "REFUSED"),
])
def test_verify_refuses_failure_even_at_receipt_path(tmp_path, monkeypatch, schema, status):
    import argparse
    from tools.certification import local_assurance as la
    monkeypatch.setattr(la, "_require_linux", lambda: None)
    from contextlib import nullcontext
    monkeypatch.setattr(la, "_assurance_lock", lambda root: nullcontext())
    monkeypatch.setattr(la.core_certificate, "repo_root", lambda _: tmp_path)
    monkeypatch.setattr(la, "_require_clean", lambda *a: None)
    monkeypatch.setattr(la, "_git", lambda root, *a: "child source" if a[0] == "rev-list" else "child")
    monkeypatch.setattr(la, "_resolve_python", lambda *a: "python")
    monkeypatch.setattr(la, "_version", lambda *a: None)
    monkeypatch.setattr(la, "_run", lambda *a, **kw: pytest.fail("self-check execution authorized"))
    receipt = tmp_path / ".forge/assurance/source/local-assurance-receipt.json"
    la._write_json(receipt, {"schema": schema, "status": status, "source_commit": "source"})
    with pytest.raises(la.LocalAssuranceError, match="receipt does not bind"):
        la.verify(argparse.Namespace(local_root=".forge", python312=None))


def test_failed_run_never_builds_certificate(tmp_path, monkeypatch):
    import argparse
    import json
    from tools.certification import local_assurance as la
    monkeypatch.setattr(la, "_require_linux", lambda: None)
    from contextlib import nullcontext
    monkeypatch.setattr(la, "_assurance_lock", lambda root: nullcontext())
    monkeypatch.setattr(la.core_certificate, "repo_root", lambda _: tmp_path)
    monkeypatch.setattr(la, "_require_clean", lambda *a: None)
    monkeypatch.setattr(la, "_git", lambda root, *a: "source")
    monkeypatch.setattr(la, "_repository_slug", lambda *a: "owner/repo")
    monkeypatch.setattr(la, "_resolve_python", lambda *a: "python")
    monkeypatch.setattr(la, "_version", lambda *a: None)
    monkeypatch.setattr(la.shutil, "which", lambda *a: "ngspice")
    def gates(*args, **kwargs):
        tracker = args[-1]
        tracker.completed("fast311", 1.5)
        tracker.failure("formal_mutations_2", RuntimeError("failure"))
        raise RuntimeError("failure")
    monkeypatch.setattr(la, "_run_source_gates", gates)
    monkeypatch.setattr(la.core_certificate, "build_certificate",
                        lambda *a, **k: pytest.fail("certificate generation after failure"))
    args = argparse.Namespace(local_root=".forge", repository=None, python311=None,
                              python312=None, workers=4, mutation_workers=2, reuse=False,
                              formal_pytest_workers=1)
    with pytest.raises(RuntimeError, match="failure"):
        la.run(args)
    run_root = tmp_path / ".forge/assurance/source"
    assert not (run_root / "local-assurance-receipt.json").exists()
    doc = json.loads((run_root / "local-assurance-failure.json").read_text())
    assert doc["failed_gate"] == "formal_mutations_2"
    assert doc["gate_seconds"] == {"fast311": 1.5}


@pytest.mark.parametrize("workers", [1, 2])
@pytest.mark.parametrize("fail", [None, "formal_mutations_1", "v4_mutations_3"])
def test_source_gate_orchestration_preserves_checkout(tmp_path, monkeypatch, workers, fail):
    import subprocess
    import threading
    from tools.certification import local_assurance as la
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".gitignore").write_text(".forge/\n")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", ".gitignore"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "commit", "-qm", "source"], cwd=root, check=True)
    source = la._git(root, "rev-parse", "HEAD")
    evidence = root / ".forge/assurance" / source / "evidence"
    scratch_paths = []
    lock = threading.Lock()
    def fake_run(argv, **kw):
        if "--out" in argv:
            pathlib.Path(argv[argv.index("--out") + 1]).write_text("selected-id\n")
        mutation = "--scratch" in argv or "tests/mutation_guards.py" in argv
        if mutation:
            scratch = pathlib.Path(argv[argv.index("--scratch") + 1] if "--scratch" in argv else argv[4])
            assert root not in scratch.resolve().parents
            with lock:
                scratch_paths.append(scratch)
            scratch.mkdir()
            (scratch / "mutant").write_text("synthetic")
            log = pathlib.Path(argv[argv.index("--log") + 1]) if "--log" in argv else kw["log"]
            log.write_text(log.parent.name)
            if fail and la.EVIDENCE[fail][0] in log.parent.name:
                raise la.LocalAssuranceError("injected shard refusal")
    monkeypatch.setattr(la, "_run", fake_run)
    monkeypatch.setattr(la, "_record_runtime", lambda *a: None)
    monkeypatch.setattr(la, "_clean_record", lambda *a: None)
    monkeypatch.setattr(la, "_deselects", lambda *a: [])
    monkeypatch.setattr(la, "_capture", lambda *a, **k: "runtime")
    if fail:
        with pytest.raises(la.LocalAssuranceError, match="injected shard refusal"):
            la._run_source_gates(root, source, evidence, "py311", "py312", 4, workers)
    else:
        timings = la._run_source_gates(root, source, evidence, "py311", "py312", 4, workers)
        assert set(timings) == set(la.EVIDENCE)
        assert len(scratch_paths) == 12
    assert len(scratch_paths) == len(set(scratch_paths))
    retained = [p.parent for p in scratch_paths if p.parent.exists()]
    assert len(retained) == (1 if fail else 0)
    import shutil
    for parent in retained:
        shutil.rmtree(parent)
    la._require_head(root, source, "test end")
    la._require_clean(root, "test end")
    for log in evidence.rglob("*.log"):
        assert log.read_text() == log.parent.name


def test_mutation_workers_cli_default_and_invalid_value(monkeypatch):
    from tools.certification import local_assurance as la
    seen = []
    monkeypatch.setattr(la, "run", lambda args: seen.append(args.mutation_workers) or 0)
    assert la.main(["run"]) == 0
    assert la.main(["run", "--mutation-workers", "1", "--workers", "7"]) == 0
    assert seen == [2, 1]


def test_formal_pytest_workers_is_a_distinct_serial_by_default_option(monkeypatch):
    from tools.certification import local_assurance as la
    seen = []
    monkeypatch.setattr(la, "run", lambda args: seen.append(
        (args.workers, args.mutation_workers, args.formal_pytest_workers)) or 0)
    assert la.main(["run"]) == 0
    assert la.main(["run", "--formal-pytest-workers", "2", "--mutation-workers", "4"]) == 0
    assert seen == [(4, 2, 1), (4, 4, 2)]
    # One Formal pytest worker is the unchanged historical shard command.
    assert la._formal_command("py", "/s", ["G1a"]) == ["py", "-X", "utf8", "tests/mutation_guards.py", "/s", "G1a"]
    assert la._formal_command("py", "/s", ["G1a"], 2) == [
        "py", "-X", "utf8", "tests/mutation_guards.py", "--pytest-workers", "2", "/s", "G1a"]
    for bad in (0, -1, True, 1.5):
        with pytest.raises(la.LocalAssuranceError):
            la._formal_command("py", "/s", [], bad)


@pytest.mark.skipif(__import__("sys").platform != "linux", reason="Linux runner process groups")
def test_stream_failure_reaps_mutation_process_before_scratch_cleanup(tmp_path, monkeypatch):
    import os
    import sys
    import subprocess
    from tools.certification import local_assurance as la
    script = tmp_path / "child.py"
    script.write_text("import time\nprint('STREAM_FAILURE_MARKER', flush=True)\ntime.sleep(60)\n")
    processes = []
    original_popen = subprocess.Popen
    original_stdout = sys.stdout
    def popen(*args, **kwargs):
        child = original_popen(*args, **kwargs)
        processes.append(child)
        return child
    class BrokenStream:
        def write(self, line):
            if "STREAM_FAILURE_MARKER" in line:
                raise OSError("synthetic stream failure")
            return original_stdout.write(line)
        def flush(self):
            return original_stdout.flush()
    monkeypatch.setattr(la.subprocess, "Popen", popen)
    with la._mutation_scratch(tmp_path, "formal_mutations_0") as scratch:
        scratch.mkdir()
        with monkeypatch.context() as context:
            context.setattr(sys, "stdout", BrokenStream())
            with pytest.raises(OSError, match="synthetic stream failure"):
                la._run([sys.executable, str(script)], root=tmp_path, log=tmp_path / "shard.log")
        assert processes[0].poll() is not None
        with pytest.raises(ProcessLookupError):
            os.killpg(processes[0].pid, 0)
        assert scratch.exists()
    assert not scratch.parent.exists()


def test_child_exit_during_forced_kill_preserves_stream_error(tmp_path, monkeypatch):
    import subprocess
    from tools.certification import local_assurance as la
    class BrokenPipe:
        def __iter__(self):
            raise OSError("original stream error")
        def close(self):
            pass
    class Child:
        pid = 123
        stdout = BrokenPipe()
        waits = []
        def terminate(self):
            raise ProcessLookupError("already exited")
        def kill(self):
            raise ProcessLookupError("already exited")
        def wait(self, timeout=None):
            self.waits.append(timeout)
            if timeout is not None:
                raise subprocess.TimeoutExpired("synthetic", timeout)
            return 0
    child = Child()
    monkeypatch.setattr(la.subprocess, "Popen", lambda *a, **k: child)
    monkeypatch.setattr(la.os, "killpg", lambda *a: pytest.fail("numeric group kill is not ownership"))
    with pytest.raises(OSError, match="original stream error"):
        la._run(["synthetic"], root=tmp_path, log=tmp_path / "shard.log")
    assert child.waits == [5, None]


@pytest.mark.parametrize("relative", ["../outside", "/absolute", "a/../b", "", "C:/outside", "a\\b"])
def test_manifest_refuses_unsafe_paths(tmp_path, relative):
    from tools.certification import local_assurance as la
    with pytest.raises(la.LocalAssuranceError, match="unsafe evidence path"):
        la._evidence_file(tmp_path, relative)


@pytest.mark.skipif(__import__("sys").platform != "linux", reason="Linux authoritative lock")
def test_repository_invocation_lock_refuses_concurrent_owner(tmp_path, monkeypatch):
    from tools.certification import local_assurance as la
    for key in list(__import__("os").environ):
        if key.startswith("GIT_"):
            monkeypatch.delenv(key)
    with la._assurance_lock(tmp_path):
        with pytest.raises(la.LocalAssuranceError, match="another local assurance"):
            with la._assurance_lock(tmp_path):
                pytest.fail("second owner admitted")
    with la._assurance_lock(tmp_path):
        pass


def test_failure_persistence_error_preserves_refusal(tmp_path, monkeypatch):
    from tools.certification import local_assurance as la
    monkeypatch.setattr(la, "_write_json", lambda *args: (_ for _ in ()).throw(OSError("disk full")))
    tracker = la._GateTracker(tmp_path / "failure.json", "source", "tree", "execution")
    tracker.failure("gate", RuntimeError("original refusal"))
    assert "original refusal" in tracker.failures["gate"]


@pytest.mark.parametrize("problem", ["extra", "duplicate", "source"])
def test_manifest_closure_and_identity_refusals(tmp_path, monkeypatch, problem):
    import json
    from tools.certification import local_assurance as la
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "gate.json").write_text("{}")
    monkeypatch.setattr(la, "_git", lambda *args: "tree")
    path, _, _ = la._build_evidence_manifest(tmp_path, "source", evidence)
    document = json.loads(path.read_text())
    if problem == "extra":
        (evidence / "performance.json").write_text("{}")
    elif problem == "duplicate":
        document["files"] *= 2
        document["file_count"] = 2
    else:
        document["source_commit"] = "another"
    la._write_json(path, document)
    with pytest.raises(la.LocalAssuranceError):
        la._verify_evidence_manifest(path, evidence, source="source", source_tree="tree")


def test_atomic_json_replace_failure_preserves_previous_document(tmp_path, monkeypatch):
    from tools.certification import local_assurance as la
    path = tmp_path / "receipt.json"
    la._write_json(path, {"status": "REFUSED"})
    previous = path.read_bytes()
    def fail(*args):
        raise OSError("replace failed")
    monkeypatch.setattr(la.os, "replace", fail)
    with pytest.raises(OSError, match="replace failed"):
        la._write_json(path, {"status": "PASS"})
    assert path.read_bytes() == previous
    assert list(tmp_path.iterdir()) == [path]


def test_source_identity_guard_refuses_clean_head_movement(tmp_path, monkeypatch):
    from tools.certification import local_assurance as la
    monkeypatch.setattr(la, "_git", lambda *args: "new-source")
    with pytest.raises(la.LocalAssuranceError, match="HEAD moved"):
        la._require_head(tmp_path, "original-source", "after gates")


@pytest.mark.skipif(__import__("sys").platform != "linux", reason="Linux authoritative lock")
def test_lock_refuses_linked_forge_before_outside_creation(tmp_path, monkeypatch):
    from tools.certification import local_assurance as la
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".forge").symlink_to(outside, target_is_directory=True)
    for key in list(__import__("os").environ):
        if key.startswith("GIT_"):
            monkeypatch.delenv(key)
    with pytest.raises(la.LocalAssuranceError, match="linked assurance"):
        with la._assurance_lock(root):
            pytest.fail("linked root admitted")
    assert list(outside.iterdir()) == []


@pytest.mark.skipif(__import__("sys").platform != "linux", reason="Linux authoritative lock")
def test_assurance_admission_refuses_inherited_git_identity(tmp_path, monkeypatch):
    from tools.certification import local_assurance as la
    monkeypatch.setenv("GIT_DIR", "/another/repository")
    with pytest.raises(la.LocalAssuranceError, match="inherited Git overrides"):
        with la._assurance_lock(tmp_path):
            pytest.fail("redirected source admitted")
    assert not (tmp_path / ".forge").exists()
