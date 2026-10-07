"""Hostile specifications of the persistent mutation workspace (Passes 2–9; executed since Pass 8)."""
from __future__ import annotations

import json
import pathlib
import shutil
import stat
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from tools.certification import mutation_v4_runner as v4
from tools.certification import mutation_workspace as mw
from tools.certification.performance_telemetry import PerformanceTelemetry


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    (root / "src").mkdir(parents=True)
    (root / "src/guard.py").write_text("def guard():\n    return 1\n")
    (root / ".git/objects").mkdir(parents=True)
    (root / ".git/objects/blob").write_bytes(b"synthetic git bytes")
    return root


def populate(root, destination):
    shutil.copytree(root, destination, symlinks=True)


def workspace(source, scratch):
    return mw.PersistentWorkspace(source, scratch, populate)


def test_manifest_is_complete_deterministic_and_includes_git(source, tmp_path):
    with workspace(source, tmp_path / "scratch") as owned:
        owned._verify_seed()
        assert mw.snapshot(owned.work) == owned.baseline
        assert ".git/objects/blob" in owned.baseline
        assert owned.baseline_sha256 == mw.manifest_digest(owned.baseline)
        assert owned.baseline_sha256 == mw.manifest_digest(dict(reversed(list(owned.baseline.items()))))
        with pytest.raises(TypeError):
            owned.baseline["new"] = mw.Entry("file", 0)


def test_mutation_changes_worker_only_and_repairs_exact_bytes(source, tmp_path):
    original = mw.snapshot(source)
    with workspace(source, tmp_path / "scratch") as owned:
        with owned.attempt() as worker:
            (worker / "src/guard.py").write_text("def guard():\n    return 0\n")
            assert (owned.seed / "src/guard.py").read_bytes() == (source / "src/guard.py").read_bytes()
            assert (owned.seed / "src/guard.py").stat().st_ino != (worker / "src/guard.py").stat().st_ino
        assert mw.snapshot(owned.work) == owned.baseline
    assert mw.snapshot(source) == original


@pytest.mark.parametrize("change", ["deleted", "unexpected", "mode", "git", "replaced-directory"])
def test_restore_repairs_all_contamination_types(source, tmp_path, change):
    with workspace(source, tmp_path / "scratch") as owned:
        with owned.attempt() as worker:
            if change == "deleted":
                (worker / "src/guard.py").unlink()
            elif change == "unexpected":
                (worker / "cache/nested").mkdir(parents=True)
                (worker / "cache/nested/junk").write_bytes(b"new")
            elif change == "mode":
                path = worker / "src/guard.py"
                path.chmod(path.stat().st_mode ^ stat.S_IXUSR)
            elif change == "git":
                (worker / ".git/objects/blob").write_bytes(b"contaminated git")
            else:
                shutil.rmtree(worker / "src")
                (worker / "src").write_text("directory replaced with file")
        assert mw.snapshot(owned.work) == owned.baseline


def test_contamination_before_attempt_invalidates_without_entering(source, tmp_path):
    with workspace(source, tmp_path / "scratch") as owned:
        (owned.work / "unexpected").write_bytes(b"bad")
        with pytest.raises(mw.WorkspaceError, match="contaminated"):
            with owned.attempt():
                pytest.fail("contaminated worker executed")
        with pytest.raises(mw.WorkspaceError, match="invalidated"):
            owned.verify()


def test_restore_failure_cannot_issue_a_verdict_or_start_next_attempt(source, tmp_path, monkeypatch):
    with workspace(source, tmp_path / "scratch") as owned:
        def fail(*args, **kwargs):
            raise OSError("repair refused")
        monkeypatch.setattr(owned, "_restore_file", fail)
        with pytest.raises(mw.WorkspaceError, match="restoration failed"):
            with owned.attempt() as worker:
                (worker / "src/guard.py").write_bytes(b"mutated")
        with pytest.raises(mw.WorkspaceError, match="invalidated"):
            with owned.attempt():
                pytest.fail("next mutation ran after failed restore")


def test_seed_tampering_refuses_restore(source, tmp_path):
    with workspace(source, tmp_path / "scratch") as owned:
        with pytest.raises(mw.WorkspaceError, match="restoration failed"):
            with owned.attempt():
                path = owned.seed / "src/guard.py"
                path.chmod(0o600)  # Deliberately defeat accidental-write protection.
                path.write_bytes(b"changed seed")
        assert owned.poisoned


def test_next_mutation_observes_pristine_identity(source, tmp_path):
    with workspace(source, tmp_path / "scratch") as owned:
        for number in range(2):
            with owned.attempt() as worker:
                assert mw.snapshot(worker) == owned.baseline
                (worker / "src/guard.py").write_text(str(number))


@pytest.mark.parametrize("failure", [OSError, KeyboardInterrupt])
def test_failure_restores_then_cleans_owned_workspace(source, tmp_path, failure):
    owned = workspace(source, tmp_path / "scratch")
    with pytest.raises(failure):
        with owned:
            with owned.attempt() as worker:
                (worker / "src/guard.py").write_bytes(b"changed")
                raise failure("injected")
    assert not owned.home.exists()
    assert (source / "src/guard.py").read_text() == "def guard():\n    return 1\n"


def test_initial_population_failure_cleans_partial_copy(source, tmp_path):
    homes = []
    def failed_populate(root, seed):
        seed.mkdir()
        homes.append(seed.parent)
        raise OSError("partial population")
    with pytest.raises(OSError, match="partial population"):
        with mw.PersistentWorkspace(source, tmp_path / "scratch", failed_populate):
            pytest.fail("failed population entered")
    assert not homes[0].exists()


def test_concurrent_shards_have_distinct_mutable_state(source, tmp_path):
    import threading
    barrier = threading.Barrier(2)
    def shard(number):
        with workspace(source, tmp_path / f"scratch-{number}") as owned:
            with owned.attempt() as worker:
                (worker / "src/guard.py").write_text(str(number))
                barrier.wait(timeout=5)
                assert (worker / "src/guard.py").read_text() == str(number)
                return owned.home, owned.seed, worker
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(shard, [1, 2]))
    assert len({p for row in results for p in row}) == 6
    assert all(not row[0].exists() for row in results)


@pytest.mark.parametrize("relative", ["../outside", "/tmp/outside", "src/../guard.py", "src\\guard.py"])
def test_target_traversal_is_refused(source, relative):
    with pytest.raises(mw.WorkspaceError, match="unsafe"):
        mw.mutation_target(source, relative)


def test_worker_symlink_is_removed_without_touching_source(source, tmp_path):
    before = mw.snapshot(source)
    with workspace(source, tmp_path / "scratch") as owned:
        with owned.attempt() as worker:
            target = worker / "src/guard.py"
            target.unlink()
            target.symlink_to(source / "src/guard.py")
            with pytest.raises(mw.WorkspaceError, match="linked"):
                mw.mutation_target(worker, "src/guard.py")
        assert mw.snapshot(owned.work) == owned.baseline
    assert mw.snapshot(source) == before


def test_seed_symlink_and_git_external_pointer_are_refused(source, tmp_path):
    (source / "linked").symlink_to(source / "src/guard.py")
    with pytest.raises(mw.WorkspaceError, match="links"):
        with workspace(source, tmp_path / "scratch-one"):
            pass
    (source / "linked").unlink()
    (source / ".git/commondir").write_text("/external/git")
    with pytest.raises(mw.WorkspaceError, match="external Git"):
        with workspace(source, tmp_path / "scratch-two"):
            pass


def test_linked_artifacts_and_repository_local_storage_are_refused(source, tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / "junit").symlink_to(source / "src", target_is_directory=True)
    with pytest.raises(mw.WorkspaceError, match="linked artifact"):
        mw.artifact_path(source, scratch, "junit", "guard.xml")
    with pytest.raises(mw.WorkspaceError, match="overlap"):
        with workspace(source, source / "scratch"):
            pass


def test_telemetry_has_no_authority_and_clock_or_storage_failures_are_diagnostic(tmp_path, monkeypatch):
    import tools.certification.performance_telemetry as telemetry
    record = PerformanceTelemetry(tmp_path / "performance.json")
    record.add_seconds("test_execution", 1.0)
    doc = record.document()
    assert doc["schema"] == "forge.local_assurance_performance/1"
    assert doc["certification_authority"] is False
    assert doc["safe_to_push_authority"] is False
    assert "status" not in doc and "verdict" not in doc
    def failure(*args, **kwargs):
        raise OSError("diagnostic failure")
    monkeypatch.setattr(telemetry.time, "monotonic", failure)
    with record.measure("restore"):
        pass
    monkeypatch.setattr(telemetry.os, "replace", failure)
    record.write()


def _entry(mid="SYNTHETIC"):
    return (mid, "src/guard.py", "return 1", "return 0", "tests/guard.py::test_guard",
            "KILLED", "", (), "synthetic-non-certifying")


@pytest.fixture
def mocked_v4(source, monkeypatch):
    monkeypatch.syspath_prepend(str(pathlib.Path(__file__).resolve().parent))
    monkeypatch.setattr(v4, "populate", populate)
    def fake_pytest(work, arguments, scratch, tag, *, telemetry=None, workspace=None):
        report = mw.artifact_path(source, scratch, "junit", tag + ".xml")
        if tag == "control":
            report.write_text('<testsuites><testsuite><testcase classname="tests.guard" name="test_guard"/></testsuite></testsuites>')
            return subprocess.CompletedProcess([], 0, "control output", "")
        report.write_text('<testsuites><testsuite><testcase classname="tests.guard" name="test_guard"><failure/></testcase></testsuite></testsuites>')
        return subprocess.CompletedProcess([], 1, "mutation output", "")
    monkeypatch.setattr(v4, "_pytest", fake_pytest)


def test_v4_population_once_and_existing_transcript_contract(source, tmp_path, monkeypatch, mocked_v4):
    copies = []
    def counted(root, seed):
        copies.append(seed)
        populate(root, seed)
    monkeypatch.setattr(v4, "populate", counted)
    lines, wrong = v4.round_lines(source, [_entry("ONE"), _entry("TWO")], tmp_path / "scratch", say=lambda _: None)
    assert len(copies) == 1
    assert wrong == 0
    assert lines == ["ONE test_guard -> KILLED | mutation output",
                     "TWO test_guard -> KILLED | mutation output",
                     "CONTROL (unmutated, 1 test(s)) GREEN | control output"]
    assert not copies[0].parent.exists()


@pytest.mark.parametrize("outcome", ["no-report", "timeout", "application-refusal"])
def test_v4_failure_paths_restore_before_next_mutation(source, tmp_path, monkeypatch, mocked_v4, outcome):
    import mutation_guards as mg
    if outcome == "application-refusal":
        monkeypatch.setattr(mg, "_apply", lambda *a: "synthetic refusal")
    else:
        def failure(work, args, scratch, tag, *, telemetry=None, workspace=None):
            if outcome == "timeout":
                raise subprocess.TimeoutExpired("synthetic", 1)
            return subprocess.CompletedProcess([], 1, "no report", "")
        monkeypatch.setattr(v4, "_pytest", failure)
    with workspace(source, tmp_path / "scratch") as owned:
        result, _ = v4.run_one(source, _entry(), tmp_path / "scratch", workspace=owned)
        expected = {"no-report": "NO_REPORT", "timeout": "TIMEOUT", "application-refusal": "NOT_APPLIED"}[outcome]
        assert result.startswith(expected)
        assert mw.snapshot(owned.work) == owned.baseline


def test_v4_restore_failure_never_returns_killed(source, tmp_path, monkeypatch, mocked_v4):
    with workspace(source, tmp_path / "scratch") as owned:
        def failure(*args, **kwargs):
            raise OSError("restore failure")
        monkeypatch.setattr(owned, "_restore_file", failure)
        with pytest.raises(mw.WorkspaceError, match="restoration failed"):
            v4.run_one(source, _entry(), tmp_path / "scratch", workspace=owned)


def test_formal_control_first_single_population_and_guard_transcript(source, tmp_path, monkeypatch, capsys):
    monkeypatch.syspath_prepend(str(pathlib.Path(__file__).resolve().parent))
    import mutation_guards as mg
    monkeypatch.setattr(mg, "__file__", str(source / "tests/mutation_guards.py"))
    monkeypatch.setattr(mg, "_self_test", lambda: None)
    monkeypatch.setattr(mg, "_validate_declarations", lambda: None)
    monkeypatch.setattr(mg, "MUTATIONS", [("ONE", "src/guard.py", "return 1", "return 0", "synthetic guard")])
    monkeypatch.setattr(mg, "EVIDENCE", {"ONE": ("synthetic mechanism", "test_guard")})
    copies, calls = [], []
    def counted(root, seed):
        copies.append(seed)
        populate(root, seed)
    monkeypatch.setattr(mg, "_copy_tree", counted)
    def fake_run(work, scratch, *, telemetry=None, workspace=None):
        text = (work / "src/guard.py").read_text()
        calls.append(text)
        return (0, "control", [], "") if "return 1" in text else (1, "mutant", ["test_guard"], "")
    monkeypatch.setattr(mg, "_run", fake_run)
    assert mg.main([str(tmp_path / "scratch"), "ONE"]) == 0
    assert len(copies) == 1 and len(calls) == 2
    assert "return 1" in calls[0] and "return 0" in calls[1]
    text = capsys.readouterr().out
    assert "CONTROL" in text and "1/1 mutations were killed by the guard they name." in text
    assert not copies[0].parent.exists()


def test_local_telemetry_is_outside_manifest_and_cannot_verify_as_receipt(source, tmp_path, monkeypatch):
    import argparse
    from tools.certification import local_assurance as la
    run = source / ".forge/assurance/source"
    evidence = run / "evidence"
    evidence.mkdir(parents=True)
    (evidence / "gate.json").write_text('{}')
    performance = PerformanceTelemetry(run / "performance/shard.json")
    performance.add_seconds("gate_total", 3.0)
    performance.write()
    monkeypatch.setattr(la, "_git", lambda *a: "source")
    manifest, _, _ = la._build_evidence_manifest(source, "source", evidence)
    assert json.loads(manifest.read_text())["files"][0]["path"] == "gate.json"
    receipt = run / "local-assurance-receipt.json"
    receipt.write_text(json.dumps({**performance.document(), "source_commit": "source"}))
    monkeypatch.setattr(la, "_require_linux", lambda: None)
    monkeypatch.setattr(la.core_certificate, "repo_root", lambda *a: source)
    monkeypatch.setattr(la, "_require_clean", lambda *a: None)
    monkeypatch.setattr(la, "_git", lambda root, *args: "child source" if args[0] == "rev-list" else "child")
    monkeypatch.setattr(la, "_resolve_python", lambda *a: "python")
    monkeypatch.setattr(la, "_version", lambda *a: None)
    with pytest.raises(la.LocalAssuranceError, match="receipt does not bind"):
        la.verify(argparse.Namespace(local_root=".forge", python312=None))


@pytest.mark.parametrize("outcome", ["normal", "timeout", "interrupted"])
def test_target_cleanup_confirms_drain_before_return(tmp_path, monkeypatch, outcome):
    import io
    events = []
    state = [0]
    class Child:
        pid = 123
        returncode = 1
        stdout, stderr = io.StringIO(), io.StringIO()
        def communicate(self, timeout):
            events.append("communicate")
            if outcome == "timeout":
                raise subprocess.TimeoutExpired("synthetic", timeout)
            if outcome == "interrupted":
                raise KeyboardInterrupt("synthetic")
            return "out", "err"
        def wait(self, timeout):
            events.append("wait")
            return 1
    def subreaper(value=None):
        if value is not None:
            state[0] = value
        return state[0]
    monkeypatch.setattr(mw, "_children", lambda *a: set())
    monkeypatch.setattr(mw, "_subreaper", subreaper)
    monkeypatch.setattr(mw, "_drain_children", lambda: events.append("drained"))
    monkeypatch.setattr(mw, "_check_process_owner", lambda: None)
    monkeypatch.setattr(mw.subprocess, "Popen", lambda *a, **k: Child())
    if outcome == "normal":
        assert mw.run_captured(["synthetic"], cwd=tmp_path, timeout=1).returncode == 1
    else:
        expected = subprocess.TimeoutExpired if outcome == "timeout" else KeyboardInterrupt
        with pytest.raises(expected):
            mw.run_captured(["synthetic"], cwd=tmp_path, timeout=1)
    assert events == ["communicate", "drained", "wait"]
    assert state[0] == 0


def test_detached_children_are_drained_after_adoption(monkeypatch):
    import signal
    monkeypatch.setattr(mw, "_check_reaper_state", lambda **kwargs: None)
    snapshots = iter([{10}, {20}, {20}, set()])
    killed = []
    monkeypatch.setattr(mw, "_children", lambda *a: next(snapshots))
    monkeypatch.setattr(mw.os, "kill", lambda pid, sig: killed.append((pid, sig)))
    monkeypatch.setattr(mw.os, "waitpid", lambda *a: (0, 0))
    monkeypatch.setattr(mw.time, "sleep", lambda *a: None)
    mw._drain_children()
    assert killed == [(10, signal.SIGKILL), (20, signal.SIGKILL)]


def test_undrained_descendant_refuses_without_restoration_or_cleanup(source, tmp_path, monkeypatch):
    owned = workspace(source, tmp_path / "scratch")
    with pytest.raises(mw.UndrainedProcessError, match="retained"):
        with owned:
            with owned.attempt() as worker:
                (worker / "src/guard.py").write_bytes(b"possibly still owned by descendant")
                raise mw.UndrainedProcessError("synthetic child could not be drained")
    assert owned.poisoned and owned.undrained
    assert owned.home.exists()
    assert (owned.work / "src/guard.py").read_bytes() == b"possibly still owned by descendant"
    mw._unlock_directories(owned.seed)
    shutil.rmtree(owned.home)  # Synthetic test has no live descendant.


def test_descendant_drain_timeout_is_not_a_mutation_verdict(monkeypatch):
    monkeypatch.setattr(mw, "_check_reaper_state", lambda **kwargs: None)
    clock = iter([0.0, 4.0])
    monkeypatch.setattr(mw.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(mw, "_children", lambda *a: {10})
    monkeypatch.setattr(mw.os, "kill", lambda *a: None)
    monkeypatch.setattr(mw.os, "waitpid", lambda *a: (0, 0))
    with pytest.raises(mw.UndrainedProcessError, match="could not be drained"):
        mw._drain_children()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux child ownership")
@pytest.mark.parametrize("detached", [False, True])
def test_real_future_detached_and_sigterm_resistant_descendants_are_owned(tmp_path, detached):
    # Specification only: NOT RUN in passes 2–4; ownership needs a dedicated interpreter.
    script = tmp_path / "descendant.py"
    script.write_text(
        "import os, signal, time\n"
        "child = os.fork()\n"
        "if child == 0:\n"
        + ("    os.setsid()\n" if detached else "")
        + "    signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "    fd = os.open(os.devnull, os.O_WRONLY)\n"
        "    os.dup2(fd, 1); os.dup2(fd, 2)\n"
        "    time.sleep(60)\n"
        "else:\n"
        "    print(child, flush=True)\n"
    )
    driver = (
        "from tools.certification.mutation_workspace import run_captured\n"
        "import sys\n"
        "result = run_captured([sys.executable, sys.argv[1]], cwd=sys.argv[2], timeout=5)\n"
        "print(result.stdout.strip(), flush=True)\n"
    )
    result = subprocess.run([sys.executable, "-c", driver, str(script), str(tmp_path)],
                            cwd=pathlib.Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, timeout=10, check=True)
    pid = int(result.stdout.strip())
    with pytest.raises(ProcessLookupError):
        __import__("os").kill(pid, 0)
    assert mw._children(__import__("os").getpid()) == set()


@pytest.mark.parametrize("failure", [False, True])
def test_parent_retains_unreleased_worker_storage(source, tmp_path, failure):
    from tools.certification import local_assurance as la
    retained = None
    expected = RuntimeError if failure else la.LocalAssuranceError
    with pytest.raises(expected):
        with la._mutation_scratch(source, "v4_mutations_0") as scratch:
            retained = scratch / "workspace-unreleased"
            retained.mkdir(parents=True)
            if failure:
                raise RuntimeError("shard refused")
    assert retained.exists()
    shutil.rmtree(retained.parents[1])  # No live process in this synthetic specification.


@pytest.mark.parametrize("config", [
    "[core]\nworktree = /external/source\n",
    "[Core]\nworktree = /external/source\n",
    "[cOrE]\nWorkTree = /external/source\n",
    "[include]\npath = /external/config\n",
])
def test_external_git_configuration_is_refused(source, tmp_path, config):
    (source / ".git/config").write_text(config)
    with pytest.raises(mw.WorkspaceError, match="config"):
        with workspace(source, tmp_path / "scratch"):
            pytest.fail("external git configuration admitted")


@pytest.mark.parametrize("missing", [False, True])
def test_unavailable_proc_child_listing_does_not_mean_empty(tmp_path, monkeypatch, missing):
    tasks = tmp_path / "task"
    thread = tasks / "owner-thread"
    thread.mkdir(parents=True)
    from types import SimpleNamespace
    monkeypatch.setattr(mw, "pathlib", SimpleNamespace(Path=lambda *a: tmp_path / "absent" if missing else tasks))
    with pytest.raises(mw.WorkspaceError, match="ownership is unavailable|listing is unavailable"):
        mw._children(123)



def test_pristine_index_is_reused_without_retaining_file_bytes(source, tmp_path, monkeypatch):
    calls = []
    original = mw._digest
    def counted(path, **kwargs):
        calls.append(path)
        return original(path, **kwargs)
    monkeypatch.setattr(mw, "_digest", counted)
    with workspace(source, tmp_path / "scratch") as owned:
        index = owned.index
        digest = index.sha256
        for number in range(2):
            with owned.attempt(mutation_id=str(number), intended=["src/guard.py"]):
                (owned.work / "src/guard.py").write_text("def guard():\n    return 0\n")
        assert owned.index is index and owned.index.sha256 == digest
        assert any(owned.seed in path.parents for path in calls)
        assert not hasattr(index, "contents")  # Full content hashes replace the RAM byte cache.
        assert not hasattr(index, "files") and not hasattr(index, "directories")
        with pytest.raises(TypeError):
            index.entries["src/guard.py"] = mw.Entry("file", 0)


def test_dirty_hints_do_not_hide_unrelated_same_size_and_restored_timestamp_bytes(source, tmp_path):
    import os
    (source / "src/unrelated.py").write_text("return_value = 1\n")
    with workspace(source, tmp_path / "scratch") as owned:
        path = owned.work / "src/unrelated.py"
        before = path.stat()
        with owned.attempt(mutation_id="ONE", intended=["src/guard.py"]):
            path.write_text("return_value = 0\n")
            os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        assert owned.last_deltas.content_changed == frozenset({"src/unrelated.py"})
        assert mw.snapshot(owned.work) == owned.baseline


def test_known_target_restore_is_sparse_but_worker_sha_remains_complete(source, tmp_path, monkeypatch):
    (source / "src/untouched.py").write_text("unchanged = 1\n")
    with workspace(source, tmp_path / "scratch") as owned:
        repaired = []
        original = owned._restore_file
        def record(name):
            repaired.append(name)
            original(name)
        monkeypatch.setattr(owned, "_restore_file", record)
        with owned.attempt(intended=["src/guard.py"]):
            (owned.work / "src/guard.py").write_text("def guard():\n    return 0\n")
        assert repaired == ["src/guard.py"]
        assert owned.last_deltas.intended == frozenset({"src/guard.py"})
        assert mw.snapshot(owned.work) == owned.baseline


@pytest.mark.parametrize("change", ["same-size-seed", "hardlink", "file-directory"])
def test_new_index_cannot_mask_seed_link_or_type_contamination(source, tmp_path, change):
    import os
    with workspace(source, tmp_path / "scratch") as owned:
        if change == "same-size-seed":
            path = owned.seed / "src/guard.py"
            expected_mode = stat.S_IMODE(path.stat().st_mode)
            path.chmod(0o600)
            path.write_text("def guard():\n    return 0\n")
            path.chmod(expected_mode)
            with pytest.raises(mw.WorkspaceError, match="seed changed"):
                with owned.attempt():
                    pytest.fail("seed contamination was hidden by cached hashes")
        else:
            with owned.attempt(intended=["src/guard.py"]):
                path = owned.work / "src/guard.py"
                if change == "hardlink":
                    os.link(path, owned.work / "unexpected-hardlink")
                else:
                    path.unlink()
                    path.mkdir()
                    (path / "extra").write_text("new")
            assert mw.snapshot(owned.work) == owned.baseline


def test_seed_permissions_are_read_only_and_cleanup_never_follows_substituted_directory(source, tmp_path):
    (source / "src/nested").mkdir()
    (source / "src/nested/a").write_bytes(b"safe")
    original = mw.snapshot(source)
    owned = workspace(source, tmp_path / "scratch")
    with pytest.raises(mw.WorkspaceError, match="seed changed"):
        with owned:
            assert all(not (e.mode & 0o222) for e in mw.snapshot(owned.seed).values())
            owned.seed.chmod(0o700)
            (owned.seed / "src").chmod(0o700)
            (owned.seed / "src/nested").chmod(0o700)
            (owned.seed / "src/nested/a").unlink()
            (owned.seed / "src/nested").rmdir()
            (owned.seed / "src/guard.py").unlink()
            (owned.seed / "src").rmdir()
            (owned.seed / "src").symlink_to(source / "src", target_is_directory=True)
            owned.verify()
    assert mw.snapshot(source) == original
    assert not owned.home.exists()


def test_lifecycle_failure_diagnostics_preserve_exact_mutation_and_stage(source, tmp_path):
    record = PerformanceTelemetry(tmp_path / "performance.json", shard="v4_mutations_3")
    owned = mw.PersistentWorkspace(source, tmp_path / "scratch", populate, telemetry=record)
    with pytest.raises(RuntimeError, match="application interrupted"):
        with owned:
            with owned.attempt(mutation_id="ONE", intended=["src/guard.py"]):
                record.stage("mutation_application_started")
                raise RuntimeError("application interrupted")
    doc = json.loads(record.path.read_text())
    failure = next(row for row in doc["failures"] if row["category"] == "RuntimeError")
    assert failure["shard"] == "v4_mutations_3"
    assert failure["mutation_id"] == "ONE"
    assert failure["stage"] == "mutation_application_started"
    assert doc["lifecycle_stage"] == "cleanup_finished"
    assert doc["certification_authority"] is False and doc["safe_to_push_authority"] is False


def test_subprocess_construction_failure_still_confirms_descendant_drain(tmp_path, monkeypatch):
    events = []
    state = [0]
    def subreaper(value=None):
        if value is not None:
            state[0] = value
        return state[0]
    def failed_popen(*args, **kwargs):
        raise OSError("construction interrupted")
    monkeypatch.setattr(mw, "_children", lambda *a: set())
    monkeypatch.setattr(mw, "_subreaper", subreaper)
    monkeypatch.setattr(mw, "_drain_children", lambda: events.append("drained"))
    monkeypatch.setattr(mw, "_check_process_owner", lambda: None)
    monkeypatch.setattr(mw.subprocess, "Popen", failed_popen)
    with pytest.raises(OSError, match="construction interrupted"):
        mw.run_captured(["synthetic"], cwd=tmp_path, timeout=1)
    assert events == ["drained"]
    assert state[0] == 0


def test_drain_failure_stage_retains_worker_and_cannot_authorize_reuse(source, tmp_path, monkeypatch):
    import io
    state = [0]
    class Child:
        stdout, stderr = io.StringIO(), io.StringIO()
        returncode = 0
        def communicate(self, timeout):
            return "", ""
        def wait(self, timeout):
            return 0
    def subreaper(value=None):
        if value is not None:
            state[0] = value
        return state[0]
    def refused():
        raise mw.UndrainedProcessError("descendants remain")
    monkeypatch.setattr(mw, "_PROCESS_POISONED", False)
    monkeypatch.setattr(mw, "_children", lambda *a: set())
    monkeypatch.setattr(mw, "_subreaper", subreaper)
    monkeypatch.setattr(mw, "_drain_children", refused)
    monkeypatch.setattr(mw, "_check_process_owner", lambda: None)
    monkeypatch.setattr(mw.subprocess, "Popen", lambda *a, **k: Child())
    owned = workspace(source, tmp_path / "scratch")
    with pytest.raises(mw.UndrainedProcessError, match="retained"):
        with owned:
            with owned.attempt(mutation_id="ONE"):
                mw.run_captured(["synthetic"], cwd=owned.work, timeout=1, telemetry=owned.telemetry)
    doc = json.loads(owned.telemetry.path.read_text())
    failure = next(row for row in doc["failures"] if row["category"] == "descendant_quiescence_unproven")
    assert failure["stage"] == "descendant_drain_started"
    assert failure["mutation_id"] == "ONE"
    assert failure["worker_retained"] and failure["descendant_quiescence"] is False
    assert owned.home.exists()
    mw._unlock_directories(owned.seed)
    shutil.rmtree(owned.home)  # Mock ownership failure has no live children.


def test_sparse_repair_does_not_chmod_through_symlink_ancestor(source, tmp_path):
    (source / "src/nested").mkdir()
    (source / "src/nested/a").write_text("baseline")
    outside = tmp_path / "outside"
    (outside / "nested").mkdir(parents=True)
    (outside / "nested" / "untouched").write_text("outside")
    (outside / "nested").chmod(0o500)
    before = mw.snapshot(outside)
    with workspace(source, tmp_path / "scratch") as owned:
        with owned.attempt(mutation_id="ANCESTOR", intended=["src/guard.py"]):
            shutil.rmtree(owned.work / "src")
            (owned.work / "src").symlink_to(outside, target_is_directory=True)
        assert mw.snapshot(owned.work) == owned.baseline
        assert mw.snapshot(outside) == before


def test_invalid_dirty_hint_poisoning_refuses_next_attempt(source, tmp_path):
    with workspace(source, tmp_path / "scratch") as owned:
        with pytest.raises(mw.WorkspaceError, match="outside pristine index"):
            with owned.attempt(mutation_id="INVALID", intended=["../outside"]):
                pytest.fail("unsafe hint admitted")
        with pytest.raises(mw.WorkspaceError, match="invalidated"):
            with owned.attempt(mutation_id="NEXT"):
                pytest.fail("poisoned workspace reused")


@pytest.mark.parametrize("change", ["bytes", "deleted", "unexpected", "mode", "symlink", "hardlink", "directory"])
def test_seed_mismatch_stops_before_first_restore_and_next_attempt(source, tmp_path, monkeypatch, change):
    import os
    with workspace(source, tmp_path / "scratch") as owned:
        path = owned.seed / "src/guard.py"
        restored = []
        monkeypatch.setattr(owned, "_restore_file", lambda name: restored.append(name))
        with pytest.raises(mw.WorkspaceError, match="restoration failed"):
            with owned.attempt(intended=["src/guard.py"]):
                owned.seed.chmod(0o700)
                (owned.seed / "src").chmod(0o700)
                path.chmod(0o600)
                if change == "bytes":
                    path.write_bytes(b"corrupt")
                elif change == "unexpected":
                    (owned.seed / "extra").write_bytes(b"extra")
                elif change == "hardlink":
                    os.link(path, owned.seed / "extra-link")
                elif change in {"deleted", "symlink", "directory"}:
                    path.unlink()
                    if change == "symlink":
                        path.symlink_to(source / "src/guard.py")
                    elif change == "directory":
                        path.mkdir()
        assert owned.poisoned and not restored
        with pytest.raises(mw.WorkspaceError, match="invalidated"):
            with owned.attempt():
                pytest.fail("failed seed authorized reuse")


def test_restore_streams_seed_without_content_cache(source, tmp_path):
    with workspace(source, tmp_path / "scratch") as owned:
        assert not hasattr(owned.index, "contents")
        with owned.attempt(intended=["src/guard.py"]):
            (owned.work / "src/guard.py").write_bytes(b"changed")
        assert mw.snapshot(owned.work) == owned.baseline
        assert owned.telemetry.counters["restoration_bytes_copied"] == owned.baseline["src/guard.py"].size
        assert owned.telemetry.counters["files_restored"] == 1
        assert owned.telemetry.counters.get("seed_bytes_from_cache", 0) == 0


def test_git_and_host_injection_environment_is_neutralized_without_binding_repo(tmp_path):
    inherited = {"GIT_DIR": "/outside/git", "GIT_WORK_TREE": "/outside/work",
                 "GIT_COMMON_DIR": "/outside/common", "GIT_INDEX_FILE": "/outside/index",
                 "GIT_OBJECT_DIRECTORY": "/outside/objects",
                 "GIT_ALTERNATE_OBJECT_DIRECTORIES": "/outside/alternates",
                 "GIT_CEILING_DIRECTORIES": "/outside", "GIT_CONFIG_GLOBAL": "/outside/global",
                 "GIT_CONFIG_SYSTEM": "/outside/system", "GIT_CONFIG_COUNT": "9",
                 "GIT_CONFIG_KEY_7": "core.worktree", "GIT_CONFIG_VALUE_7": "/outside",
                 "GIT_TRACE": "/outside/trace", "PYTHONPATH": "/outside/imports",
                 "PYTHONHOME": "/outside/python", "PYTEST_PLUGINS": "host_plugin",
                 "PYTEST_ADDOPTS": "--override-ini=pythonpath=/outside", "TMPDIR": "/outside/tmp",
                 "PATH": "/certified/tools", "FORGE_PROVIDER_SETTING": "preserved"}
    env = mw.mutation_environment(tmp_path, inherited)
    assert "GIT_DIR" not in env and "GIT_WORK_TREE" not in env
    assert "GIT_OBJECT_DIRECTORY" not in env and "GIT_ALTERNATE_OBJECT_DIRECTORIES" not in env
    assert "GIT_CONFIG_KEY_7" not in env and "GIT_CONFIG_VALUE_7" not in env
    assert env["GIT_CONFIG_GLOBAL"] == env["GIT_CONFIG_SYSTEM"] == __import__("os").devnull
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert env["GIT_CONFIG_KEY_0"] == "core.hooksPath"
    assert env["TMPDIR"] == env["TMP"] == env["TEMP"] == str(tmp_path)
    assert "PYTHONPATH" not in env and "PYTEST_PLUGINS" not in env and "PYTEST_ADDOPTS" not in env
    assert env["PATH"] == inherited["PATH"]
    assert env["FORGE_PROVIDER_SETTING"] == "preserved"
    assert list(pathlib.Path(env["GIT_TEMPLATE_DIR"]).iterdir()) == []


@pytest.mark.parametrize("config", [
    '[core]\nhooksPath=/outside/hooks\n', '[Core]\nfsmonitor=/outside/monitor\n',
    '[extensions]\nworktreeConfig=true\n', '[includeIf "gitdir:/"]\npath=/outside/config\n',
    '[core ]\nworktree=/outside/work\n', '[core\t]\nworktree=/outside/work\n',
    '[extensions ]\nworktreeConfig=true\n',
    '[filter.driver]\nclean=/outside/helper\n', '[diff.driver]\ncommand=/outside/helper\n',
    '[filter "driver"]\nclean=/outside/helper\n', '[core]\nattributesFile=/outside/attrs\n',
])
def test_git_external_helpers_and_worktree_config_are_refused(source, tmp_path, config):
    (source / ".git/config").write_text(config)
    with pytest.raises(mw.WorkspaceError, match="config"):
        with workspace(source, tmp_path / "scratch"):
            pytest.fail("external Git behavior admitted")


@pytest.mark.parametrize("pointer", ["objects/info/alternates", "objects/info/http-alternates", "info/grafts", "refs/replace/name", "config.worktree"])
def test_git_alternates_and_rewritten_history_are_refused(source, tmp_path, pointer):
    path = source / ".git" / pointer
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("/outside/storage")
    with pytest.raises(mw.WorkspaceError, match="external Git"):
        with workspace(source, tmp_path / "scratch"):
            pytest.fail("external storage or rewritten history admitted")


def test_ambiguous_owner_retains_worker_and_blocks_next_attempt(source, tmp_path, monkeypatch):
    def ambiguous():
        raise mw.UndrainedProcessError("competing reaper")
    monkeypatch.setattr(mw, "_PROCESS_POISONED", False)
    monkeypatch.setattr(mw, "_check_process_owner", ambiguous)
    owned = workspace(source, tmp_path / "scratch")
    with pytest.raises(mw.UndrainedProcessError, match="retained"):
        with owned:
            with owned.attempt(mutation_id="ONE"):
                mw.run_captured(["synthetic"], cwd=owned.work, timeout=1, telemetry=owned.telemetry)
    assert owned.home.exists() and owned.poisoned and owned.undrained
    with pytest.raises(mw.WorkspaceError, match="invalidated"):
        with owned.attempt(mutation_id="TWO"):
            pytest.fail("uncertain ownership authorized another mutation")
    assert owned.telemetry.counters["workers_retained_ownership_uncertain"] == 1
    mw._unlock_directories(owned.seed)
    shutil.rmtree(owned.home)  # No target was launched in this mock specification.


def test_child_descriptors_and_runtime_storage_have_explicit_lifetimes(tmp_path, monkeypatch):
    import io
    calls = []
    class Child:
        stdout, stderr = io.StringIO(), io.StringIO()
        returncode = 0
        def communicate(self, timeout):
            return "", ""
        def wait(self, timeout):
            return 0
    child = Child()
    def popen(*args, **kwargs):
        calls.append(kwargs)
        assert pathlib.Path(kwargs["env"]["TMPDIR"]).is_dir()
        return child
    monkeypatch.setattr(mw, "_check_process_owner", lambda: None)
    monkeypatch.setattr(mw, "_subreaper", lambda *a: 0 if not a else None)
    state = [0]
    def subreaper(value=None):
        if value is not None:
            state[0] = value
        return state[0]
    monkeypatch.setattr(mw, "_subreaper", subreaper)
    monkeypatch.setattr(mw, "_drain_children", lambda: None)
    monkeypatch.setattr(mw.subprocess, "Popen", popen)
    mw.run_captured(["synthetic"], cwd=tmp_path, timeout=1)
    assert calls[0]["close_fds"] is True and calls[0]["pass_fds"] == ()
    assert child.stdout.closed and child.stderr.closed
    assert not pathlib.Path(calls[0]["env"]["TMPDIR"]).exists()


def test_diagnostic_counters_never_grant_authority(tmp_path):
    record = PerformanceTelemetry(tmp_path / "performance.json")
    record.increment("seed_bytes_read", 10)
    record.increment("files_restored", 1)
    record.increment("workers_retained_ownership_uncertain", 1)
    doc = record.document()
    assert doc["counters"]["seed_bytes_read"] == 10
    assert doc["certification_authority"] is False and doc["safe_to_push_authority"] is False
    assert "verdict" not in doc and "status" not in doc


@pytest.mark.parametrize("ambiguity", ["kernel-threads", "sigchld-handler", "sigchld-mask", "children", "subreaper"])
def test_dedicated_process_contract_refuses_detectable_competing_owners(monkeypatch, ambiguity):
    import signal
    from types import SimpleNamespace
    fake_tasks = SimpleNamespace(iterdir=lambda: iter(range(2 if ambiguity == "kernel-threads" else 1)))
    monkeypatch.setattr(mw, "pathlib", SimpleNamespace(Path=lambda *a: fake_tasks))
    monkeypatch.setattr(mw.signal, "getsignal", lambda *a: signal.SIG_IGN if ambiguity == "sigchld-handler" else signal.SIG_DFL)
    monkeypatch.setattr(mw.signal, "pthread_sigmask", lambda *a: {signal.SIGCHLD} if ambiguity == "sigchld-mask" else set())
    monkeypatch.setattr(mw, "_children", lambda *a: {123} if ambiguity == "children" else set())
    monkeypatch.setattr(mw, "_subreaper", lambda *a: 1 if ambiguity == "subreaper" else 0)
    with pytest.raises(mw.UndrainedProcessError):
        mw._check_process_owner()


def test_telemetry_counter_accounting_failure_cannot_change_workspace_identity(source, tmp_path, monkeypatch):
    with workspace(source, tmp_path / "scratch") as owned:
        class BrokenCounters(dict):
            def get(self, *args):
                raise OSError("accounting unavailable")
        owned.telemetry.counters = BrokenCounters()
        with owned.attempt(intended=["src/guard.py"]):
            (owned.work / "src/guard.py").write_bytes(b"changed")
        assert mw.snapshot(owned.work) == owned.baseline
        assert owned.telemetry.document()["certification_authority"] is False


def test_seed_restore_open_descriptor_is_closed_on_write_failure(source, tmp_path, monkeypatch):
    import builtins
    opened = []
    original = builtins.open
    with workspace(source, tmp_path / "scratch") as owned:
        def recording(file, *args, **kwargs):
            handle = original(file, *args, **kwargs)
            if pathlib.Path(file) == owned.seed / "src/guard.py":
                opened.append(handle)
            return handle
        monkeypatch.setattr(builtins, "open", recording)
        original_path_open = pathlib.Path.open
        def failed_target(path, mode="r", *args, **kwargs):
            if path == owned.work / "src/guard.py" and mode == "xb":
                raise OSError("write refused")
            return original_path_open(path, mode, *args, **kwargs)
        monkeypatch.setattr(pathlib.Path, "open", failed_target)
        with pytest.raises(mw.WorkspaceError, match="restoration failed"):
            with owned.attempt(intended=["src/guard.py"]):
                (owned.work / "src/guard.py").write_bytes(b"changed")
        assert opened and all(handle.closed for handle in opened)


@pytest.mark.parametrize("case", ["unchanged-hint", "mode-only"])
def test_authenticated_clean_dirty_candidates_are_not_recopied(source, tmp_path, monkeypatch, case):
    with workspace(source, tmp_path / "scratch") as owned:
        writes = []
        monkeypatch.setattr(owned, "_restore_file", lambda name: writes.append(name))
        with owned.attempt(intended=["src/guard.py"]):
            if case == "mode-only":
                (owned.work / "src/guard.py").chmod(0o600)
        assert writes == []
        assert mw.snapshot(owned.work) == owned.baseline


def test_cli_scratch_existing_user_artifacts_are_never_cleared(source, tmp_path, mocked_v4):
    scratch = tmp_path / "user-scratch"
    (scratch / "basetemp/mut_SYNTHETIC").mkdir(parents=True)
    sentinel = scratch / "basetemp/mut_SYNTHETIC/user-data"
    sentinel.write_bytes(b"keep")
    (scratch / "junit").mkdir()
    report = scratch / "junit/mut_SYNTHETIC.xml"
    report.write_bytes(b"keep report")
    v4.run_one(source, _entry(), scratch)
    assert sentinel.read_bytes() == b"keep"
    assert report.read_bytes() == b"keep report"


def test_owned_root_substitution_refuses_recursive_cleanup(tmp_path):
    owner = mw.OwnedRoot.create(prefix="owned-", parent=tmp_path)
    original = owner.path.with_name(owner.path.name + "-original")
    owner.path.rename(original)
    owner.path.mkdir()
    sentinel = owner.path / "user-data"
    sentinel.write_bytes(b"keep")
    with pytest.raises(mw.WorkspaceError, match="identity changed"):
        owner.remove()
    assert sentinel.read_bytes() == b"keep"
    shutil.rmtree(original)


def test_formal_population_refuses_preexisting_arbitrary_directory(source, tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(pathlib.Path(__file__).resolve().parent))
    import mutation_guards as mg
    destination = tmp_path / "user-data"
    destination.mkdir()
    sentinel = destination / "sentinel"
    sentinel.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        mg._copy_tree(source, destination)
    assert sentinel.read_bytes() == b"keep"


@pytest.mark.parametrize("link", ["symlink", "hardlink"])
def test_diagnostic_atomic_replacement_cannot_overwrite_link_target(tmp_path, link):
    import os
    outside = tmp_path / "user-data"
    outside.write_bytes(b"keep")
    record = PerformanceTelemetry(tmp_path / "performance.json")
    if link == "symlink":
        record.path.symlink_to(outside)
    else:
        os.link(outside, record.path)
    record.write()
    assert outside.read_bytes() == b"keep"
    assert json.loads(record.path.read_text())["certification_authority"] is False


def test_diagnostic_parent_substitution_is_ignorable_without_outside_write(tmp_path):
    parent = tmp_path / "diagnostics"
    parent.mkdir()
    record = PerformanceTelemetry(parent / "performance.json")
    parent.rename(tmp_path / "old-diagnostics")
    outside = tmp_path / "user-area"
    outside.mkdir()
    parent.symlink_to(outside, target_is_directory=True)
    record.write()
    assert not (outside / "performance.json").exists()


@pytest.mark.parametrize("config", [
    '[extensions]\npartialClone=origin\n', '[EXTENSIONS]\nobjectformat=sha256\n',
    '[remote "origin"]\npromisor=true\nurl=/outside/repo\n',
    '[extensions]\nunknownextension=true\n',
])
def test_git_lazy_fetch_and_unknown_formats_are_refused(source, tmp_path, config):
    (source / ".git/config").write_text(config)
    with pytest.raises(mw.WorkspaceError, match="config|object format"):
        with workspace(source, tmp_path / "scratch"):
            pytest.fail("external lazy fetch admitted")


def test_promisor_pack_marker_is_refused(source, tmp_path):
    (source / ".git/objects/pack").mkdir()
    (source / ".git/objects/pack/pack-marker.promisor").write_bytes(b"")
    with pytest.raises(mw.WorkspaceError, match="promisor"):
        with workspace(source, tmp_path / "scratch"):
            pytest.fail("promisor objects admitted")


def test_git_ceiling_prevents_ancestor_discovery_without_binding_fixture_repositories(tmp_path):
    work = tmp_path / "workspace/worker"
    work.mkdir(parents=True)
    runtime = tmp_path / "workspace/runtime"
    runtime.mkdir()
    env = mw.mutation_environment(runtime, {}, work=work)
    assert env["GIT_CEILING_DIRECTORIES"] == str(work.parent)
    assert env["GIT_DISCOVERY_ACROSS_FILESYSTEM"] == "0"
    assert "GIT_DIR" not in env and "GIT_WORK_TREE" not in env


def test_abnormal_parent_retains_entire_scratch_without_workspace_marker(source):
    from tools.certification import local_assurance as la
    with pytest.raises(OSError, match="abrupt shard"):
        with la._mutation_scratch(source, "v4_mutations_0") as scratch:
            scratch.mkdir()
            retained = scratch.parent
            (scratch / "possibly-owned").write_bytes(b"keep")
            raise OSError("abrupt shard")
    assert retained.exists()
    shutil.rmtree(retained)  # Synthetic exception launched no descendants.


def test_changed_sigchld_during_drain_retains_and_refuses(monkeypatch):
    import signal
    monkeypatch.setattr(mw.signal, "getsignal", lambda *a: signal.SIG_IGN)
    with pytest.raises(mw.UndrainedProcessError, match="SIGCHLD"):
        mw._drain_children()


def test_duplicate_shard_jobs_are_refused_before_submission():
    from tools.certification import local_assurance as la
    calls = []
    with pytest.raises(la.LocalAssuranceError, match="duplicate"):
        la._mutation_group([("same", lambda: calls.append(1)), ("same", lambda: calls.append(2))], 2)
    assert not calls


def test_reuse_quarantines_prior_data_instead_of_recursively_deleting(tmp_path):
    from tools.certification import local_assurance as la
    run_root = tmp_path / "assurance/source"
    run_root.mkdir(parents=True)
    (run_root / "user-data").write_bytes(b"keep")
    quarantine = la._quarantine_prior_run(run_root)
    assert not run_root.exists()
    assert (quarantine / "previous-run/user-data").read_bytes() == b"keep"


def test_substituted_artifact_root_cannot_clear_user_basetemp(source, tmp_path):
    outside = tmp_path / "user-area"
    outside.mkdir()
    (outside / "keep").write_bytes(b"keep")
    with workspace(source, tmp_path / "scratch") as owned:
        owned.artifacts.rmdir()
        owned.artifacts.symlink_to(outside, target_is_directory=True)
        with pytest.raises(mw.WorkspaceError, match="linked|substituted"):
            owned.artifact_path("basetemp", "target")
    assert (outside / "keep").read_bytes() == b"keep"


def test_private_target_helpers_refuse_unowned_deletion_roots(source, tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(pathlib.Path(__file__).resolve().parent))
    import mutation_guards as mg
    with pytest.raises(mw.WorkspaceError, match="owned"):
        v4._pytest(source, [], tmp_path, "target")
    with pytest.raises(mw.WorkspaceError, match="owned"):
        mg._run(source, tmp_path)


@pytest.mark.parametrize("code", [2, 3, 4, 5, -9])
def test_v4_infrastructure_exit_cannot_earn_named_junit_kill(source, tmp_path, monkeypatch, mocked_v4, code):
    def infrastructure(work, args, scratch, tag, *, telemetry=None, workspace=None):
        report = workspace.artifact_path("junit", tag + ".xml")
        report.write_text('<testsuites><testsuite><testcase classname="tests.guard" name="test_guard"><failure/></testcase></testsuite></testsuites>')
        return subprocess.CompletedProcess([], code, "named failure", "")
    monkeypatch.setattr(v4, "_pytest", infrastructure)
    with workspace(source, tmp_path / "scratch") as owned:
        with pytest.raises(mw.WorkspaceError, match="infrastructure exit"):
            v4.run_one(source, _entry(), tmp_path / "scratch", workspace=owned)
        assert owned.poisoned


@pytest.mark.parametrize("code", [3, 4, 5, -9])
def test_formal_infrastructure_exit_cannot_earn_transcript_credit(source, tmp_path, monkeypatch, code):
    monkeypatch.syspath_prepend(str(pathlib.Path(__file__).resolve().parent))
    import mutation_guards as mg
    monkeypatch.setattr(mw, "run_captured", lambda *a, **kw:
                        subprocess.CompletedProcess([], code, "E   ValueError: core refusal\nFAILED test_guard", ""))
    with workspace(source, tmp_path / "scratch") as owned:
        with pytest.raises(mw.WorkspaceError, match="infrastructure exit"):
            mg._run(owned.work, owned.artifacts, workspace=owned)



def _reference_snapshot(tree):
    """The Pass 2-8 pathlib formulation, kept here as an independent oracle."""
    import os
    tree = pathlib.Path(tree)
    rows = {"": mw.Entry("directory", stat.S_IMODE(tree.lstat().st_mode))}
    counts = {}

    def walk(directory):
        with os.scandir(directory) as handle:
            children = sorted(handle, key=lambda e: os.fsencode(e.name))
        for child in children:
            path = pathlib.Path(child.path)
            relative = path.relative_to(tree).as_posix()
            info = child.stat(follow_symlinks=False)
            mode = stat.S_IMODE(info.st_mode)
            counts["entries_structurally_scanned"] = counts.get("entries_structurally_scanned", 0) + 1
            if stat.S_ISDIR(info.st_mode):
                rows[relative] = mw.Entry("directory", mode)
                walk(path)
            elif stat.S_ISREG(info.st_mode):
                counts["files_structurally_scanned"] = counts.get("files_structurally_scanned", 0) + 1
                if relative.startswith(".git/"):
                    counts["git_files_processed"] = counts.get("git_files_processed", 0) + 1
                import hashlib
                rows[relative] = mw.Entry("file", mode, hashlib.sha256(path.read_bytes()).hexdigest(),
                                          links=info.st_nlink, size=info.st_size)
            elif stat.S_ISLNK(info.st_mode):
                rows[relative] = mw.Entry("symlink", mode, target=os.readlink(path))
            else:
                rows[relative] = mw.Entry("special", mode)
    walk(tree)
    return dict(sorted(rows.items())), counts


def test_string_path_snapshot_equals_the_pathlib_manifest_and_counters(source, tmp_path, monkeypatch):
    import os
    (source / ".gitignore").write_text("x")
    (source / ".github").mkdir()
    (source / ".github/w.yml").write_text("w")
    (source / "back\\slash").write_text("b")
    with open(os.fsencode(str(source)) + b"/bad-\xff-name", "wb") as handle:
        handle.write(b"bytes")
    (source / "src/link").symlink_to(source / "src", target_is_directory=True)
    os.link(source / "src/guard.py", source / "src/hard")
    os.mkfifo(source / "fifo")
    expected, counts = _reference_snapshot(source)
    record = PerformanceTelemetry(None)
    assert mw.snapshot(source, telemetry=record, area="worker") == expected
    assert {k: record.counters[k] for k in counts} == counts
    monkeypatch.chdir(source.parent)
    assert mw.snapshot(source.name) == expected  # Relative tree spelling: same relative names.


def test_mid_walk_failure_still_reports_entries_already_scanned(source, tmp_path):
    (source / "z-locked").mkdir()
    (source / "z-locked").chmod(0)
    record = PerformanceTelemetry(None)
    try:
        with pytest.raises(PermissionError):
            mw.snapshot(source, telemetry=record, area="worker")
    finally:
        (source / "z-locked").chmod(0o700)
    assert record.counters["entries_structurally_scanned"] >= 4
    assert record.counters["git_files_processed"] == 1
