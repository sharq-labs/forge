"""tools/run_observatory as a process: the CLI, interruption, crash recovery, concurrency, the pytest adapter.

These drive ``python -m tools.run_observatory`` the way a developer would, because exit-code
preservation, signal handling and concurrent ledger writes only exist across a process boundary.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time

import pytest

from tools.run_observatory import cli, ledger, receipt

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
WINDOWS = sys.platform == "win32"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=obs", "-c", "user.email=obs@example.invalid",
                           "-c", "init.defaultBranch=main", "-c", "core.autocrlf=false", *args],
                          cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    path.mkdir()
    _git(path, "init", "-q")
    (path / "test_sample.py").write_text(
        "import pytest\n\n"
        "def test_ok():\n    pass\n\n"
        "def test_bad():\n    assert False\n\n"
        "@pytest.mark.skip(reason='no')\ndef test_skip():\n    pass\n\n"
        "@pytest.mark.xfail(reason='known')\ndef test_xfail():\n    assert False\n",
        encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "init")
    return path


@pytest.fixture
def run_root(tmp_path: Path) -> Path:
    return tmp_path / "ledger"


def _cli_args(run_root: Path, repo: Path, *args: str) -> list[str]:
    return [PY, "-m", "tools.run_observatory", "--run-root", str(run_root), *args]


def _child_env() -> dict[str, str]:
    """The outer pytest's options (``--basetemp`` above all) must not reach a pytest the observatory runs."""
    return {k: v for k, v in os.environ.items() if not k.startswith(("PYTEST_", "PYTHONBREAKPOINT"))}


def _cli(run_root: Path, repo: Path, *args: str, **kw) -> subprocess.CompletedProcess:
    kw.setdefault("env", _child_env())
    return subprocess.run(_cli_args(run_root, repo, *args), cwd=ROOT, capture_output=True, text=True,
                          timeout=180, **kw)


def _receipts(run_root: Path) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((run_root / "receipts").glob("*.json"))
            if not p.name.endswith(".pending.json")]


def _wait_for_pending(run_root: Path, timeout: float = 60.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for path in (run_root / "receipts").glob("*.pending.json") if (run_root / "receipts").exists() else ():
            try:
                pending = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if pending.get("child_pid"):
                return pending
        time.sleep(0.05)
    raise AssertionError("no pending receipt with a child pid appeared")


def _kill_quietly(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass


# --------------------------------------------------------------------------------------------
# CLI basics


def test_the_module_entry_point_only_delegates_to_the_cli() -> None:
    main_py = ROOT / "tools/run_observatory/__main__.py"
    assert "from tools.run_observatory.cli import main" in main_py.read_text(encoding="utf-8")
    run = subprocess.run([PY, "-m", "tools.run_observatory", "--help"], cwd=ROOT, capture_output=True, text=True,
                         timeout=60)
    assert run.returncode == 0 and "not scientific evidence" in " ".join(run.stdout.split())


def test_cli_refuses_an_empty_command_and_a_malformed_counter_before_running(tmp_path, capsys) -> None:
    root = tmp_path / "ledger"
    assert cli.main(["--run-root", str(root), "run", "--quiet"]) == 2
    with pytest.raises(SystemExit):
        cli.main(["--run-root", str(root), "run", "--counter", "cases", "--", PY, "-c", "pass"])
    assert cli.main(["--run-root", str(root), "run", "--counter", "speedups=3", "--", PY, "-c", "pass"]) == 2
    assert not (root / "receipts").exists() or not list((root / "receipts").glob("*.json"))


def test_cli_run_preserves_exit_codes_and_prints_the_run(repo, run_root) -> None:
    ok = _cli(run_root, repo, "run", "--cwd", str(repo), "--quiet", "--", PY, "-c", "print('hi')")
    assert ok.returncode == 0, ok.stderr
    fail = _cli(run_root, repo, "run", "--cwd", str(repo), "--quiet", "--", PY, "-c", "import sys; sys.exit(7)")
    assert fail.returncode == 7
    assert "RUN_FAIL" in fail.stderr and "RUN_ID" in fail.stderr
    records = _receipts(run_root)
    assert [r["result"]["status"] for r in records].count("RUN_PASS") == 1
    assert all(receipt.verify(r) for r in records)


def test_cli_passes_child_output_through_unless_quiet(repo, run_root) -> None:
    loud = _cli(run_root, repo, "run", "--cwd", str(repo), "--", PY, "-c", "print('through-the-wrapper')")
    assert "through-the-wrapper" in loud.stdout


def test_cli_does_not_reconstruct_a_shell_string(repo, run_root) -> None:
    marker = repo / "should-not-exist.txt"
    hostile = f"x & echo pwned > {marker}" if WINDOWS else f"x; touch {marker}"
    run = _cli(run_root, repo, "run", "--cwd", str(repo), "--quiet", "--", PY, "-c",
               "import sys; print(sys.argv[1])", hostile)
    assert run.returncode == 0 and not marker.exists()


def test_cli_query_verify_show_and_compare(repo, run_root) -> None:
    for _ in range(2):
        assert _cli(run_root, repo, "run", "--cwd", str(repo), "--quiet", "--name", "q", "--",
                    PY, "-c", "pass").returncode == 0
    ids = [r["run_id"] for r in _receipts(run_root)]
    listed = _cli(run_root, repo, "list", "--json")
    assert {r["run_id"] for r in json.loads(listed.stdout)} == set(ids)
    assert _cli(run_root, repo, "verify", "--all").returncode == 0
    shown = json.loads(_cli(run_root, repo, "show", ids[0]).stdout)
    assert shown["run_id"] == ids[0]
    compared = json.loads(_cli(run_root, repo, "compare", ids[1], ids[0], "--json").stdout)
    assert compared["comparability"] == "EXACT_COMPARABLE"


def test_cli_refuses_a_run_root_inside_the_repository(repo) -> None:
    run = _cli(repo / "ledger", repo, "run", "--cwd", str(repo), "--", PY, "-c", "pass")
    assert run.returncode == 2 and "inside" in run.stderr
    assert not (repo / "ledger").exists()


# --------------------------------------------------------------------------------------------
# Crash safety


def test_l_an_interrupted_run_seals_a_valid_partial_receipt(repo, run_root) -> None:
    kw = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if WINDOWS else {"start_new_session": True}
    wrapper = subprocess.Popen(_cli_args(run_root, repo, "run", "--cwd", str(repo), "--quiet", "--grace-seconds", "5",
                                         "--", PY, "-c", "import time; time.sleep(60)"),
                               cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw)
    pending = _wait_for_pending(run_root)
    try:
        if WINDOWS:
            try:
                os.kill(wrapper.pid, signal.CTRL_BREAK_EVENT)
            except OSError as exc:  # no shared console: Windows cannot deliver a console control event
                pytest.skip(f"cannot deliver CTRL_BREAK_EVENT here: {exc}")
        else:
            os.killpg(wrapper.pid, signal.SIGINT)
        _, err = wrapper.communicate(timeout=60)
    finally:
        _kill_quietly(pending["child_pid"])
        if wrapper.poll() is None:
            wrapper.kill()
    assert wrapper.returncode != 0
    [sealed] = _receipts(run_root)
    assert sealed["run_id"] == pending["run_id"]
    assert sealed["result"]["status"] == "RUN_INTERRUPTED" and sealed["partial"] is True
    assert sealed["integrity"]["sealed_by"] == "RUNNER"
    assert receipt.verify(sealed)
    assert not list((run_root / "receipts").glob("*.pending.json"))
    assert ledger.Ledger(run_root).verify_receipt(sealed) == "VALID"


def test_l_a_hard_killed_wrapper_is_recovered_as_a_partial_receipt(repo, run_root) -> None:
    wrapper = subprocess.Popen(_cli_args(run_root, repo, "run", "--cwd", str(repo), "--quiet", "--",
                                         PY, "-c", "import time; time.sleep(60)"),
                               cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    pending = _wait_for_pending(run_root)
    wrapper.kill()
    wrapper.communicate(timeout=30)
    _kill_quietly(pending["child_pid"])
    assert _receipts(run_root) == []
    recovered = _cli(run_root, repo, "recover", "--json")
    assert recovered.returncode == 0, recovered.stderr
    report = json.loads(recovered.stdout)
    assert report["recovered"] == [pending["run_id"]] and report["quarantined"] == []
    [sealed] = _receipts(run_root)
    assert sealed["result"]["status"] == "RUN_INTERRUPTED" and sealed["partial"] is True
    assert sealed["integrity"]["sealed_by"] == "RECOVERY"
    assert sealed["timing"]["wall_seconds"] is None and sealed["timing"]["ended_utc"] is None
    assert receipt.verify(sealed)
    assert ledger.Ledger(run_root).verify_receipt(sealed) == "VALID"


def test_21_a_corrupted_temporary_receipt_is_quarantined_not_indexed(repo, run_root) -> None:
    assert _cli(run_root, repo, "run", "--cwd", str(repo), "--quiet", "--", PY, "-c", "pass").returncode == 0
    broken = run_root / "receipts" / "20261022T000000Z-deadbeefdead.pending.json"
    broken.write_text('{"run_id": "20261022T000000Z-dead', encoding="utf-8")
    report = json.loads(_cli(run_root, repo, "recover", "--json").stdout)
    assert report["recovered"] == [] and len(report["quarantined"]) == 1
    assert not broken.exists() and (run_root / "receipts" / "quarantine" / broken.name).exists()
    assert len(ledger.Ledger(run_root).latest()) == 1


def test_21_a_corrupted_sealed_receipt_fails_verification(repo, run_root) -> None:
    assert _cli(run_root, repo, "run", "--cwd", str(repo), "--quiet", "--", PY, "-c", "pass").returncode == 0
    [path] = [p for p in (run_root / "receipts").glob("*.json")]
    os.chmod(path, 0o644)
    path.write_text(path.read_text(encoding="utf-8").replace('"RUN_PASS"', '"RUN_FAIL"'), encoding="utf-8")
    verified = _cli(run_root, repo, "verify", "--all", "--json")
    assert verified.returncode == 1
    assert json.loads(verified.stdout)[0]["verdict"] == "INTEGRITY_FAILED"


def test_21_a_killed_child_still_leaves_a_receipt(repo, run_root) -> None:
    wrapper = subprocess.Popen(_cli_args(run_root, repo, "run", "--cwd", str(repo), "--quiet", "--",
                                         PY, "-c", "import time; time.sleep(60)"),
                               cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    pending = _wait_for_pending(run_root)
    if WINDOWS:
        os.kill(pending["child_pid"], signal.SIGTERM)  # TerminateProcess(handle, 15)
    else:
        os.kill(pending["child_pid"], signal.SIGKILL)
    wrapper.communicate(timeout=60)
    [sealed] = _receipts(run_root)
    assert sealed["partial"] is False and receipt.verify(sealed)
    if WINDOWS:
        assert wrapper.returncode == 15 and sealed["result"]["exit_code"] == 15
        assert sealed["result"]["status"] == "RUN_FAIL"
    else:
        assert wrapper.returncode == 128 + signal.SIGKILL
        assert sealed["result"]["terminated_by_signal"] == "SIGKILL"
        assert sealed["result"]["status"] == "RUN_ERROR"


def test_h_simultaneous_runs_do_not_corrupt_the_ledger(repo, run_root) -> None:
    procs = [subprocess.Popen(_cli_args(run_root, repo, "run", "--cwd", str(repo), "--quiet", "--name", f"c{i}", "--",
                                        PY, "-c", "pass"),
                              cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for i in range(6)]
    for proc in procs:
        _, err = proc.communicate(timeout=180)
        assert proc.returncode == 0, err
    records = _receipts(run_root)
    assert len(records) == 6 and len({r["run_id"] for r in records}) == 6
    assert all(receipt.verify(r) for r in records)
    book = ledger.Ledger(run_root)
    assert len(book.latest(limit=100)) == 6
    assert all(book.verify_receipt(r) == "VALID" for r in records)
    con = sqlite3.connect(run_root / "ledger.sqlite")
    try:
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        con.close()


# --------------------------------------------------------------------------------------------
# PYTEST adapter


def test_16_the_pytest_adapter_records_outcomes_and_never_calls_a_failing_tier_green(repo, run_root) -> None:
    run = _cli(run_root, repo, "run", "--cwd", str(repo), "--quiet", "--adapter", "pytest", "--kind", "TEST", "--",
               PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "test_sample.py")
    assert run.returncode == 1, run.stderr
    [rec] = _receipts(run_root)
    outcomes = rec["result"]["adapter_outcomes"]
    assert rec["result"]["status"] == "RUN_FAIL"
    assert outcomes["passed"] == 1 and outcomes["failed"] == 1 and outcomes["skipped"] == 1
    assert outcomes["xfailed"] == 1 and outcomes["errors"] == 0
    assert outcomes["support"]["xpassed"] == "UNSUPPORTED" and outcomes["xpassed"] is None
    assert outcomes["failure_set"] == ["test_sample::test_bad"]
    assert rec["counters"]["values"]["tests"] == {"value": 4, "source": "ADAPTER:PYTEST", "category": "throughput"}
    assert "tests_per_second" in rec["counters"]["derived"]
    assert "GREEN" not in json.dumps(rec)
    assert "--junitxml" not in json.dumps(rec["workload"])  # the adapter's report path is not workload


def test_16_a_rerun_with_the_same_failures_reads_no_new_failures(repo, run_root) -> None:
    args = ("run", "--cwd", str(repo), "--quiet", "--adapter", "pytest", "--kind", "TEST", "--",
            PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "test_sample.py")
    _cli(run_root, repo, *args)
    _cli(run_root, repo, *args)
    second = [r for r in _receipts(run_root) if r["comparison"]["baseline_run_id"]]
    assert len(second) == 1
    assert second[0]["comparison"]["comparability"] == "EXACT_COMPARABLE"
    assert second[0]["comparison"]["failure_set"] == "NO_NEW_FAILURES"


# --------------------------------------------------------------------------------------------
# 24. dogfood shape: a pair, then a changed workload


def test_24_an_identical_pair_is_exact_and_a_changed_workload_is_a_variant(repo, run_root) -> None:
    def run(n: int) -> dict:
        done = _cli(run_root, repo, "run", "--cwd", str(repo), "--quiet", "--name", "dogfood", "--group", "dogfood",
                    "--counter", f"cases={n}", "--", PY, "-c", f"print(sum(i * i for i in range({n})))")
        assert done.returncode == 0, done.stderr
        return max(_receipts(run_root), key=lambda r: r["timing"]["started_utc"])

    first, second, changed = run(200_000), run(200_000), run(300_000)
    assert first["run_id"] != second["run_id"]
    assert first["workload"]["workload_id"] == second["workload"]["workload_id"]
    assert first["environment"]["environment_id"] == second["environment"]["environment_id"]
    assert second["comparison"]["comparability"] == "EXACT_COMPARABLE"
    assert second["comparison"]["baseline_run_id"] == first["run_id"]
    assert changed["comparison"]["comparability"] == "WORKLOAD_VARIANT"
    assert changed["comparison"]["deltas"] is None and changed["comparison"]["performance"] == "NOT_COMPARABLE"
