"""tools/run_observatory -- the universal run ledger (BR-RUN-OBS-01): identity, receipts, comparison.

Developer telemetry, never evidence. A receipt records what ran, on which code and machine, and what
it cost. It never issues a scientific verdict, and nothing in it is read to decide one.
"""

from __future__ import annotations

import ast
import copy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys

import pytest

from tools import run_observatory as obs
from tools.run_observatory import compare, identity, ledger, metrics, receipt, redaction, runner

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=obs", "-c", "user.email=obs@example.invalid",
                           "-c", "init.defaultBranch=main", "-c", "core.autocrlf=false", *args],
                          cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    path.mkdir()
    _git(path, "init", "-q")
    (path / "work.py").write_text("print('work')\n", encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "init")
    return path


@pytest.fixture
def run_root(tmp_path: Path) -> Path:
    return tmp_path / "ledger"


def _request(run_root: Path, cwd: Path, argv: list[str], **kw) -> runner.RunRequest:
    kw.setdefault("kind", "UTILITY")
    kw.setdefault("name", "unit")
    return runner.RunRequest(argv=argv, run_root=run_root, cwd=cwd, quiet=True, **kw)


# --------------------------------------------------------------------------------------------
# A. timing


class _JumpingClock:
    """Monotonic time advances 2.5 s while the wall clock is set back an hour."""

    def __init__(self) -> None:
        self._mono = iter([7_000_000_000, 9_500_000_000])
        self._utc = iter([datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc),
                          datetime(2026, 10, 22, 11, 0, tzinfo=timezone.utc)])

    def monotonic_ns(self) -> int:
        return next(self._mono)

    def utc_now(self) -> datetime:
        return next(self._utc)


def test_a_elapsed_time_comes_from_the_monotonic_clock_not_wall_clock_subtraction() -> None:
    watch = runner.Stopwatch(_JumpingClock())
    watch.start()
    timing = watch.stop()
    assert timing["wall_seconds"] == pytest.approx(2.5)
    assert timing["started_utc"] > timing["ended_utc"]  # the wall clock went back; the duration did not
    assert timing["monotonic_source"] == "time.perf_counter_ns"


def test_a_a_real_run_records_at_least_the_time_the_child_slept(repo, run_root) -> None:
    out = runner.execute(_request(run_root, repo, [PY, "-c", "import time; time.sleep(0.4)"]))
    assert out.receipt["timing"]["wall_seconds"] >= 0.4
    assert out.receipt["timing"]["started_utc"].endswith("Z")


# --------------------------------------------------------------------------------------------
# B. exit codes and result readings


@pytest.mark.parametrize("code, status", [(0, "RUN_PASS"), (3, "RUN_FAIL"), (1, "RUN_FAIL")])
def test_b_the_child_exit_code_is_preserved(repo, run_root, code, status) -> None:
    out = runner.execute(_request(run_root, repo, [PY, "-c", f"import sys; sys.exit({code})"]))
    assert out.exit_code == code
    assert out.receipt["result"]["exit_code"] == code
    assert out.receipt["result"]["status"] == status


def test_b_a_command_that_cannot_start_still_leaves_an_error_receipt(repo, run_root) -> None:
    out = runner.execute(_request(run_root, repo, ["forge-obs-no-such-executable-xyz", "--flag"]))
    assert out.exit_code == 127
    assert out.receipt["result"]["status"] == "RUN_ERROR"
    assert out.receipt["result"]["started"] is False
    assert receipt.verify(json.loads(out.receipt_path.read_text(encoding="utf-8")))


def test_b_a_missing_working_directory_is_an_error_before_start(tmp_path, run_root) -> None:
    out = runner.execute(_request(run_root, tmp_path / "missing", [PY, "-c", "pass"]))
    assert out.receipt["result"]["status"] == "RUN_ERROR" and out.receipt["result"]["started"] is False
    assert out.exit_code != 0


def test_b_generic_command_never_scrapes_counts_from_log_text(repo, run_root) -> None:
    out = runner.execute(_request(run_root, repo, [PY, "-c", "print('12 passed, 3 failed')"]))
    assert out.receipt["counters"]["values"] == {}
    assert out.receipt["counters"]["derived"] == {}


# --------------------------------------------------------------------------------------------
# C / D. git identity


def test_c_the_exact_head_and_tree_are_captured(repo) -> None:
    git = identity.capture_git(repo)
    assert git["status"] == "OK"
    assert git["head_sha"] == _git(repo, "rev-parse", "HEAD")
    assert git["tree_id"] == _git(repo, "rev-parse", "HEAD^{tree}")
    assert git["branch"] == "main" and git["detached"] is False
    assert git["tree_clean"] is True and git["uncommitted_diff_sha256"] is None
    assert Path(git["repository_root"]).resolve() == repo.resolve()


def test_d_a_dirty_tree_is_distinguishable_and_its_diff_is_bound(repo) -> None:
    clean = identity.capture_git(repo)
    (repo / "work.py").write_text("print('changed')\n", encoding="utf-8")
    dirty = identity.capture_git(repo)
    assert dirty["tree_clean"] is False and dirty["TREE_CLEAN"] is False
    assert dirty["head_sha"] == clean["head_sha"]
    assert dirty["uncommitted_diff_sha256"] and dirty["code_identity"] != clean["code_identity"]
    (repo / "work.py").write_text("print('changed again')\n", encoding="utf-8")
    assert identity.capture_git(repo)["code_identity"] != dirty["code_identity"]


def test_d_an_untracked_file_makes_the_tree_dirty(repo) -> None:
    (repo / "new.txt").write_text("x", encoding="utf-8")
    git = identity.capture_git(repo)
    assert git["tree_clean"] is False and git["untracked_sha256"]


def test_d_capturing_git_never_writes_the_observed_index(repo) -> None:
    (repo / "work.py").write_text("print('changed')\n", encoding="utf-8")
    index = repo / ".git" / "index"
    before = index.read_bytes()
    identity.capture_git(repo)
    assert index.read_bytes() == before


def test_d_outside_a_repository_git_identity_is_unknown_not_clean(tmp_path) -> None:
    git = identity.capture_git(tmp_path)
    assert git["status"] == "NOT_A_REPOSITORY"
    assert git["tree_clean"] is None and git["code_identity"] is None


def test_the_run_root_may_not_live_inside_the_observed_repository(repo) -> None:
    with pytest.raises(runner.RunRootInsideRepository):
        runner.execute(_request(repo / "ledger", repo, [PY, "-c", "pass"]))
    assert not (repo / "ledger").exists()


# --------------------------------------------------------------------------------------------
# E / F. workload identity


def _workload(repo: Path, **kw) -> dict:
    kw.setdefault("argv", [PY, "-c", "print(1)"])
    kw.setdefault("cwd", repo)
    kw.setdefault("repo_root", repo)
    kw.setdefault("environ", {})
    return identity.workload_identity(**kw)


def test_e_the_same_workload_yields_the_same_workload_id(repo) -> None:
    (repo / "a.csv").write_text("1,2\n", encoding="utf-8")
    (repo / "b.csv").write_text("3,4\n", encoding="utf-8")
    first = _workload(repo, inputs=[repo / "a.csv", repo / "b.csv"], seeds=["7"], declared={"plan": "P1"})
    again = _workload(repo, inputs=[repo / "b.csv", repo / "a.csv"], seeds=["7"], declared={"plan": "P1"})
    assert first["workload_id"] == again["workload_id"]
    assert len(first["workload_id"]) == 64


def test_e_workload_id_does_not_depend_on_where_the_checkout_lives(tmp_path) -> None:
    ids = []
    for name in ("one", "two"):
        root = tmp_path / name
        (root / "data").mkdir(parents=True)
        (root / "data" / "x.csv").write_text("1\n", encoding="utf-8")
        ids.append(identity.workload_identity(
            argv=[str(tmp_path / name / "venv" / "python"), str(root / "data" / "x.csv")],
            cwd=root, repo_root=root, inputs=[root / "data" / "x.csv"], environ={})["workload_id"])
    assert ids[0] == ids[1]


def test_f_a_changed_dataset_changes_the_workload_id(repo) -> None:
    data = repo / "data.csv"
    data.write_text("1,2\n", encoding="utf-8")
    before = _workload(repo, inputs=[data])
    data.write_text("1,3\n", encoding="utf-8")
    after = _workload(repo, inputs=[data])
    assert before["workload_id"] != after["workload_id"]
    assert before["components"]["inputs"] != after["components"]["inputs"]
    assert before["components"]["config"] == after["components"]["config"]


def test_f_a_changed_file_inside_an_input_directory_changes_the_workload_id(repo) -> None:
    folder = repo / "corpus"
    folder.mkdir()
    (folder / "one.txt").write_text("a", encoding="utf-8")
    before = _workload(repo, inputs=[folder])
    (folder / "two.txt").write_text("b", encoding="utf-8")
    assert _workload(repo, inputs=[folder])["workload_id"] != before["workload_id"]


def test_f_a_changed_config_or_seed_changes_the_workload_id_as_a_config_component(repo) -> None:
    config = repo / "plan.json"
    config.write_text('{"n": 1}', encoding="utf-8")
    base = _workload(repo, configs=[config], seeds=["7"])
    config.write_text('{"n": 2}', encoding="utf-8")
    changed_config = _workload(repo, configs=[config], seeds=["7"])
    changed_seed = _workload(repo, configs=[config], seeds=["8"])
    for other in (changed_config, changed_seed):
        assert other["workload_id"] != base["workload_id"]
        assert other["components"]["command"] == base["components"]["command"]
    assert changed_config["components"]["config"] != base["components"]["config"]
    assert changed_seed["components"]["config"] != changed_config["components"]["config"]


def test_f_changed_arguments_or_declared_plan_change_the_workload_id(repo) -> None:
    base = _workload(repo, declared={"plan": "P1"})
    assert _workload(repo, argv=[PY, "-c", "print(2)"], declared={"plan": "P1"})["workload_id"] != base["workload_id"]
    assert _workload(repo, declared={"plan": "P2"})["workload_id"] != base["workload_id"]


def test_f_relevant_environment_configuration_is_bound_by_hash_never_by_value(repo) -> None:
    one = _workload(repo, environ={"OMP_NUM_THREADS": "4"})
    two = _workload(repo, environ={"OMP_NUM_THREADS": "8"})
    assert one["workload_id"] != two["workload_id"]
    assert '"4"' not in json.dumps(one) and '"8"' not in json.dumps(two)
    declared = _workload(repo, workload_env=["FORGE_DATASET_VARIANT"], environ={"FORGE_DATASET_VARIANT": "nasa-b05"})
    assert "nasa-b05" not in json.dumps(declared)


def test_f_a_secret_named_variable_cannot_be_bound_into_a_workload(repo) -> None:
    with pytest.raises(ValueError):
        _workload(repo, workload_env=["OPENAI_API_KEY"], environ={"OPENAI_API_KEY": "sk-x"})


# --------------------------------------------------------------------------------------------
# G. environment identity


def test_g_environment_id_is_stable_for_the_same_machine_and_changes_with_it(tmp_path) -> None:
    facts = identity.environment_facts(salt=b"salt")
    again = identity.environment_facts(salt=b"salt")
    assert identity.environment_identity(facts) == identity.environment_identity(again)
    for path in (("python", "version"), ("cpu", "logical_cores"), ("os", "release"), ("memory", "total_bytes")):
        changed = copy.deepcopy(facts)
        changed[path[0]][path[1]] = "different"
        assert identity.environment_identity(changed) != identity.environment_identity(facts), path


def test_g_environment_facts_hold_a_pseudonymous_host_id_and_no_environment_values() -> None:
    facts = identity.environment_facts(salt=b"salt")
    text = json.dumps(facts)
    host = socket.gethostname()
    if len(host) >= 4:
        assert host not in text and host.lower() not in text
    assert facts["host_id"] != identity.environment_facts(salt=b"other")["host_id"]
    assert os.environ.get("PATH", "<none>") not in text
    for key in ("os", "arch", "python", "packages", "cpu", "memory", "gpu", "runtime"):
        assert key in facts


# --------------------------------------------------------------------------------------------
# I. unsupported metrics


def test_i_unsupported_metrics_are_unsupported_not_zero(repo, run_root, monkeypatch) -> None:
    monkeypatch.setattr(metrics, "psutil", None)
    out = runner.execute(_request(run_root, repo, [PY, "-c", "pass"]))
    resources = out.receipt["resources"]
    assert resources["network_bytes"] == {**resources["network_bytes"], "support": "UNSUPPORTED", "value": None}
    assert resources["gpu_utilization"]["support"] == "UNSUPPORTED" and resources["gpu_utilization"]["value"] is None
    assert resources["avg_rss_bytes"]["support"] == "UNSUPPORTED" and resources["avg_rss_bytes"]["value"] is None
    for name, record in resources.items():
        assert record["support"] in {"SUPPORTED", "PARTIAL", "UNSUPPORTED"}, name
        assert record.get("method"), name
        if record["support"] == "UNSUPPORTED":
            assert record["value"] is None, name


@pytest.mark.skipif(sys.platform not in ("win32", "linux", "darwin"), reason="tree accounting is per-OS")
def test_process_tree_cpu_counts_the_grandchild_not_only_the_wrapper(repo, run_root) -> None:
    burn = "import time\nt=time.process_time()\nwhile time.process_time()-t<0.6: pass\n"
    parent = f"import subprocess,sys; subprocess.run([sys.executable,'-c',{burn!r}],check=True)"
    out = runner.execute(_request(run_root, repo, [PY, "-c", parent]))
    cpu = out.receipt["resources"]["cpu_seconds"]
    assert cpu["support"] in {"SUPPORTED", "PARTIAL"} and cpu["scope"] == "PROCESS_TREE"
    assert cpu["value"] >= 0.5, cpu  # the grandchild burned 0.6 s; the direct child almost nothing


# --------------------------------------------------------------------------------------------
# J. receipt integrity


def test_j_a_sealed_receipt_detects_mutation(repo, run_root) -> None:
    out = runner.execute(_request(run_root, repo, [PY, "-c", "pass"]))
    sealed = json.loads(out.receipt_path.read_text(encoding="utf-8"))
    assert receipt.verify(sealed)
    tampered = copy.deepcopy(sealed)
    tampered["timing"]["wall_seconds"] = 0.0001
    assert not receipt.verify(tampered)
    resealed = receipt.seal({k: v for k, v in tampered.items() if k != "integrity"})
    assert receipt.verify(resealed)  # self-consistent, but the ledger still remembers the original digest
    book = ledger.Ledger(run_root)
    assert book.verify_receipt(sealed) == "VALID"
    assert book.verify_receipt(resealed) == "LEDGER_MISMATCH"
    assert book.verify_receipt(tampered) == "INTEGRITY_FAILED"


def test_j_a_sealed_receipt_file_is_never_overwritten(repo, run_root) -> None:
    out = runner.execute(_request(run_root, repo, [PY, "-c", "pass"]))
    with pytest.raises(FileExistsError):
        receipt.write_sealed(out.receipt_path, out.receipt)


# --------------------------------------------------------------------------------------------
# K. secrets


FAKE_KEY = "sk-fakeKEY0123456789abcdefXYZ"
SECRETS = (FAKE_KEY, "tok-supersecret-123", "hunter2pass", "ghp_FAKEfake0123456789abcdefghij",
           "tok-declared-secret-999", "plain-marker-7c1e9")


def test_k_planted_secrets_never_reach_the_receipt_ledger_or_stored_logs(repo, run_root) -> None:
    environ = dict(os.environ, FORGE_OBS_TEST_API_KEY=FAKE_KEY, FORGE_OBS_TEST_PLAIN="plain-marker-7c1e9")
    code = ("import os,sys; print(os.environ['FORGE_OBS_TEST_API_KEY']); "
            "print('Authorization: Bearer ghp_FAKEfake0123456789abcdefghij'); "
            "print(os.environ['FORGE_OBS_TEST_API_KEY'], file=sys.stderr)")
    argv = [PY, "-c", code, "--api-key", FAKE_KEY, "--token=tok-supersecret-123",
            "https://user:hunter2pass@example.invalid/x"]
    out = runner.execute(_request(run_root, repo, argv, declared={"provider_token": "tok-declared-secret-999",
                                                                 "plan": "P1"}), environ=environ)
    assert out.exit_code == 0
    assert out.receipt["outputs"]["stdout"]["redactions"] >= 2
    con = sqlite3.connect(run_root / "ledger.sqlite")
    con.execute("PRAGMA wal_checkpoint(FULL)")
    con.close()
    blobs = {p: p.read_bytes() for p in run_root.rglob("*") if p.is_file()}
    assert any(p.suffix == ".log" for p in blobs)
    for path, blob in blobs.items():
        for secret in SECRETS:
            assert secret.encode() not in blob, (secret, path)
    assert "<REDACTED>" in json.dumps(out.receipt["command"])


def test_k_redaction_covers_flag_forms_urls_headers_and_known_values() -> None:
    red = redaction.Redactor.from_environ({"MY_SERVICE_TOKEN": "abcdef123456", "PATH": "/usr/bin"})
    argv = red.redact_argv(["tool", "--password", "pw1", "--api_key=k2", "-p", "keep", "API_KEY=v3",
                            "https://a:b0b@host/p", "abcdef123456", "/usr/bin"])
    assert argv == ["tool", "--password", "<REDACTED>", "--api_key=<REDACTED>", "-p", "keep", "API_KEY=<REDACTED>",
                    "https://a:<REDACTED>@host/p", "<REDACTED>", "/usr/bin"]
    text, count = red.redact_text("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl")
    assert "eyJ" not in text and count >= 1
    text, _ = red.redact_text("AKIAABCDEFGHIJKLMNOP and ghp_" + "a" * 36 + " and xoxb-1-2-abc")
    assert "AKIA" not in text and "ghp_a" not in text and "xoxb-" not in text
    assert red.redact_mapping({"plan": "P1", "db_password": "x"}) == {"plan": "P1", "db_password": "<REDACTED>"}


# --------------------------------------------------------------------------------------------
# M / N. comparability and deltas


def _synthetic(*, workload="w", command="c", inputs="i", config="k", declared="d", env="e", code="tree:1",
               clean=True, wall=10.0, rss=1000, cpu=8.0, status="RUN_PASS", partial=False,
               failures=None, run_id="r") -> dict:
    def metric(value):
        return {"value": value, "support": "SUPPORTED", "method": "test", "scope": "PROCESS_TREE"}
    return {
        "run_id": run_id, "partial": partial,
        "workload": {"workload_id": workload,
                     "components": {"command": command, "inputs": inputs, "config": config, "declared": declared}},
        "environment": {"environment_id": env},
        "git": {"status": "OK", "code_identity": code, "tree_clean": clean},
        "timing": {"wall_seconds": wall},
        "resources": {"cpu_seconds": metric(cpu), "peak_rss_bytes": metric(rss),
                      "io_read_bytes": metric(100), "io_write_bytes": metric(50)},
        "counters": {"values": {}, "derived": {}},
        "result": {"status": status, "exit_code": 0 if status == "RUN_PASS" else 1,
                   "adapter_outcomes": None if failures is None else {"failure_set": sorted(failures)}},
    }


def test_n_exact_comparable_runs_produce_correct_deltas() -> None:
    base = _synthetic(run_id="base")
    cand = _synthetic(run_id="cand", wall=8.16, rss=888, cpu=6.0)
    policy = compare.make_policy(regression_threshold_pct=10.0, improvement_threshold_pct=10.0)
    result = compare.compare(cand, base, policy)
    assert result["comparability"] == "EXACT_COMPARABLE" and result["benchmark_speedup"] is True
    assert result["baseline_run_id"] == "base"
    assert result["deltas"]["wall_seconds"]["delta"] == pytest.approx(-1.84)
    assert result["deltas"]["wall_seconds"]["pct"] == pytest.approx(-18.4)
    assert result["deltas"]["peak_rss_bytes"]["pct"] == pytest.approx(-11.2)
    assert result["deltas"]["cpu_seconds"]["delta"] == pytest.approx(-2.0)
    assert result["performance"] == "PERFORMANCE_IMPROVED"
    assert result["result_delta"] == "UNCHANGED"
    assert result["policy"]["policy_id"] == compare.DEFAULT_POLICY["policy_id"] and result["policy"]["version"] == 1


def test_15_the_default_policy_is_explicit_and_not_aggressive() -> None:
    policy = compare.DEFAULT_POLICY
    assert policy["regression_threshold_pct"] >= 20.0 and policy["min_absolute_seconds"] > 0
    result = compare.compare(_synthetic(wall=8.16), _synthetic(), policy)
    assert result["performance"] == "UNCHANGED"  # -18.4 % sits inside measured whole-run noise


def test_15_a_slowdown_past_the_declared_threshold_is_a_regression() -> None:
    policy = compare.make_policy(regression_threshold_pct=10.0)
    assert compare.compare(_synthetic(wall=13.0), _synthetic(), policy)["performance"] == "PERFORMANCE_REGRESSION"
    tiny = compare.compare(_synthetic(wall=0.2), _synthetic(wall=0.1), policy)
    assert tiny["performance"] == "UNCHANGED"  # +100 % but below the absolute bar


def test_16_a_result_change_is_reported_separately_from_performance() -> None:
    policy = compare.make_policy(improvement_threshold_pct=10.0)
    result = compare.compare(_synthetic(wall=5.0, status="RUN_FAIL"), _synthetic(), policy)
    assert result["performance"] == "PERFORMANCE_IMPROVED"
    assert result["result_delta"] == "CHANGED"


@pytest.mark.parametrize("change, expected", [
    ({"workload": "w2", "inputs": "i2"}, "WORKLOAD_VARIANT"),
    ({"workload": "w2", "command": "c2"}, "WORKLOAD_VARIANT"),
    ({"workload": "w2", "declared": "d2"}, "WORKLOAD_VARIANT"),
    ({"workload": "w2", "config": "k2"}, "CONFIG_VARIANT"),
    ({"env": "e2"}, "ENVIRONMENT_VARIANT"),
    ({"partial": True}, "NOT_COMPARABLE"),
])
def test_m_non_comparable_runs_never_report_a_speedup(change, expected) -> None:
    result = compare.compare(_synthetic(wall=1.0, **change), _synthetic(), compare.DEFAULT_POLICY)
    assert result["comparability"] == expected
    assert result["deltas"] is None and result["benchmark_speedup"] is False
    assert result["performance"] == "NOT_COMPARABLE"
    assert "pct" not in json.dumps({k: v for k, v in result.items() if k != "policy"})


def test_m_a_dirty_run_is_never_exact_with_a_clean_one() -> None:
    result = compare.compare(_synthetic(code="dirty:abc", clean=False), _synthetic(), compare.DEFAULT_POLICY)
    assert result["comparability"] == "CODE_VARIANT"
    assert result["benchmark_speedup"] is False
    assert result["deltas"]["wall_seconds"]["comparability"] == "CODE_VARIANT"  # never a bare percentage


def test_m_unknown_code_identity_is_not_comparable() -> None:
    cand = _synthetic()
    cand["git"] = {"status": "NOT_A_REPOSITORY", "code_identity": None, "tree_clean": None}
    assert compare.compare(cand, _synthetic(), compare.DEFAULT_POLICY)["comparability"] == "NOT_COMPARABLE"


def test_16_no_new_failures_only_after_a_real_failure_set_comparison() -> None:
    policy = compare.DEFAULT_POLICY
    same = compare.compare(_synthetic(failures=["t::a"]), _synthetic(failures=["t::a", "t::b"]), policy)
    assert same["failure_set"] == "NO_NEW_FAILURES"
    new = compare.compare(_synthetic(failures=["t::c"]), _synthetic(failures=["t::a"]), policy)
    assert new["failure_set"] == "NEW_FAILURES" and new["new_failures"] == ["t::c"]
    assert compare.compare(_synthetic(failures=["t::a"]), _synthetic(), policy)["failure_set"] == "NOT_CHECKED"
    other = compare.compare(_synthetic(workload="w2", inputs="i2", failures=[]), _synthetic(failures=[]), policy)
    assert other["failure_set"] == "NOT_CHECKED"


# --------------------------------------------------------------------------------------------
# Ledger


def test_13_the_ledger_indexes_and_answers_the_standard_queries(repo, run_root) -> None:
    fast = runner.execute(_request(run_root, repo, [PY, "-c", "pass"], name="q"))
    slow = runner.execute(_request(run_root, repo, [PY, "-c", "pass"], name="q"))
    failed = runner.execute(_request(run_root, repo, [PY, "-c", "import sys; sys.exit(2)"], kind="TEST", name="f"))
    book = ledger.Ledger(run_root)
    assert book.journal_mode() == "wal"
    assert [r["run_id"] for r in book.latest(limit=3)] == [failed.run_id, slow.run_id, fast.run_id]
    assert [r["run_id"] for r in book.by_kind("TEST")] == [failed.run_id]
    workload = fast.receipt["workload"]["workload_id"]
    assert {r["run_id"] for r in book.by_workload(workload)} == {fast.run_id, slow.run_id}
    assert {r["run_id"] for r in book.by_git_sha(fast.receipt["git"]["head_sha"])} == {
        fast.run_id, slow.run_id, failed.run_id}
    assert [r["run_id"] for r in book.failed()] == [failed.run_id]
    fastest = book.fastest_exact_comparable(slow.run_id)
    assert fastest["run_id"] in {fast.run_id, slow.run_id}
    assert fastest["wall_seconds"] == min(fast.receipt["timing"]["wall_seconds"], slow.receipt["timing"]["wall_seconds"])
    assert len(book.history(workload)) == 2
    assert slow.receipt["comparison"]["baseline_run_id"] == fast.run_id
    assert slow.receipt["comparison"]["comparability"] == "EXACT_COMPARABLE"


def test_13_the_receipts_are_canonical_and_the_index_can_be_rebuilt_from_them(repo, run_root) -> None:
    runs = [runner.execute(_request(run_root, repo, [PY, "-c", "pass"])) for _ in range(2)]
    (run_root / "ledger.sqlite").unlink()
    for suffix in ("-wal", "-shm"):
        (run_root / f"ledger.sqlite{suffix}").unlink(missing_ok=True)
    book = ledger.Ledger(run_root)
    assert book.reindex() == {"indexed": 2, "rejected": []}
    assert {r["run_id"] for r in book.latest()} == {r.run_id for r in runs}


# --------------------------------------------------------------------------------------------
# Throughput, data and scientific efficiency hooks, cost, replay


def test_11_throughput_is_derived_only_from_declared_counters(repo, run_root) -> None:
    out = runner.execute(_request(run_root, repo, [PY, "-c", "import time; time.sleep(0.2)"],
                                  counters={"cases": 1000, "bytes_processed": 2_000_000_000}))
    wall = out.receipt["timing"]["wall_seconds"]
    derived = out.receipt["counters"]["derived"]
    assert derived["cases_per_second"]["value"] == pytest.approx(1000 / wall)
    assert derived["GB_per_second"]["value"] == pytest.approx(2.0 / wall)
    assert "tests_per_second" not in derived
    assert out.receipt["counters"]["values"]["cases"] == {"value": 1000, "source": "DECLARED", "category": "throughput"}


def test_18_19_efficiency_counters_are_typed_and_reported_by_the_child(repo, run_root) -> None:
    code = ("import json,os; json.dump({'counters': {'dataset_available_bytes': 1000, 'dataset_read_bytes': 250, "
            "'decisions': 5, 'hypotheses_proposed': 40, 'solver_calls': 300}}, "
            "open(os.environ['FORGE_RUN_REPORT_FILE'], 'w'))")
    out = runner.execute(_request(run_root, repo, [PY, "-c", code]))
    values, derived = out.receipt["counters"]["values"], out.receipt["counters"]["derived"]
    assert values["dataset_read_bytes"] == {"value": 250, "source": "CHILD_REPORTED", "category": "data_efficiency"}
    assert values["hypotheses_proposed"]["category"] == "scientific_efficiency"
    assert derived["data_fraction_read"]["value"] == pytest.approx(0.25)
    assert derived["bytes_per_decision"]["value"] == pytest.approx(50.0)
    assert "experiments_per_second" not in derived


def test_11_an_undeclared_counter_name_is_refused(repo, run_root) -> None:
    with pytest.raises(ValueError):
        runner.execute(_request(run_root, repo, [PY, "-c", "pass"], counters={"speedups": 3}))
    out = runner.execute(_request(run_root, repo, [PY, "-c", "pass"], counters={"custom.cards_drawn": 3}))
    assert out.receipt["counters"]["values"]["custom.cards_drawn"]["category"] == "custom"


def test_20_cost_is_not_available_by_default_and_estimated_when_given(repo, run_root) -> None:
    plain = runner.execute(_request(run_root, repo, [PY, "-c", "pass"]))
    assert plain.receipt["cost"]["label"] == "NOT_AVAILABLE" and plain.receipt["cost"]["compute_cost_estimate"] is None
    priced = runner.execute(_request(run_root, repo, [PY, "-c", "pass"],
                                     cost={"compute_cost_estimate": 0.12, "currency": "USD", "cost_model_id": "m1"}))
    assert priced.receipt["cost"]["label"] == "ESTIMATED"
    with pytest.raises(ValueError):
        runner.execute(_request(run_root, repo, [PY, "-c", "pass"], cost={"compute_cost_estimate": 0.12}))


def test_17_replay_identity_is_exact_mismatch_or_not_checked(repo, run_root) -> None:
    original = runner.execute(_request(run_root, repo, [PY, "-c", "pass"], kind="REPLAY",
                                       output_identity="sha256:aa", trace_identity="sha256:tt"))
    exact = runner.execute(_request(run_root, repo, [PY, "-c", "pass"], kind="REPLAY", replay_of=original.run_id,
                                    output_identity="sha256:aa", trace_identity="sha256:tt"))
    mismatch = runner.execute(_request(run_root, repo, [PY, "-c", "pass"], kind="REPLAY", replay_of=original.run_id,
                                       output_identity="sha256:bb"))
    unchecked = runner.execute(_request(run_root, repo, [PY, "-c", "pass"], kind="REPLAY", replay_of=original.run_id))
    assert exact.receipt["replay"]["status"] == "EXACT" and exact.receipt["replay"]["reading"] == "REPLAY_EXACT"
    assert mismatch.receipt["replay"]["status"] == "MISMATCH"
    assert unchecked.receipt["replay"]["status"] == "NOT_CHECKED"
    assert original.receipt["replay"]["status"] == "NOT_CHECKED"
    assert exact.receipt["parent"]["replay_of"] == original.run_id


def test_declared_artifacts_are_hashed_not_embedded(repo, run_root) -> None:
    out_file = repo / "out.bin"
    code = f"open({str(out_file)!r}, 'wb').write(b'x' * 4096)"
    out = runner.execute(_request(run_root, repo, [PY, "-c", code], artifacts=[out_file]))
    record = out.receipt["outputs"]["artifacts"][0]
    assert record["exists"] is True and record["bytes"] == 4096 and len(record["sha256"]) == 64
    assert "xxxx" not in out.receipt_path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------------------------
# Authority boundary


def test_the_observatory_vocabulary_never_contains_a_scientific_verdict() -> None:
    forbidden = obs.FORBIDDEN_SCIENTIFIC_VERDICTS
    assert {"SUPPORTED", "REFUSED", "MODEL_ADEQUATE", "DISCOVERY_CONFIRMED"} <= forbidden
    for vocabulary in (obs.RUN_STATUSES, obs.COMPARABILITY_CLASSES, obs.PERFORMANCE_READINGS, obs.REPLAY_READINGS,
                       obs.FAILURE_SET_READINGS):
        assert not (set(vocabulary) & forbidden), vocabulary
    assert set(obs.RUN_KINDS) == {"TEST", "FAST", "SCIENTIFIC", "REPLAY", "BENCHMARK", "SOLVER", "PROVIDER",
                                  "DATA_PIPELINE", "CAMPAIGN", "FORMAL", "CERTIFICATION", "UTILITY"}


def test_a_receipt_says_it_is_not_evidence_and_its_readings_stay_in_vocabulary(repo, run_root) -> None:
    out = runner.execute(_request(run_root, repo, [PY, "-c", "pass"]))
    rec = out.receipt
    assert "not scientific evidence" in rec["classification"] and "not certification" in rec["classification"]
    assert rec["result"]["status"] in obs.RUN_STATUSES
    assert rec["comparison"]["performance"] in obs.PERFORMANCE_READINGS
    assert rec["schema"] == obs.RECEIPT_SCHEMA


def test_the_observatory_imports_nothing_from_the_scientific_runtime() -> None:
    package = ROOT / "tools" / "run_observatory"
    for path in package.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else (
                [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            assert not any(n == "engcore" or n.startswith(("engcore.", "src.")) for n in names), (path, names)


def test_an_unknown_run_kind_is_refused(repo, run_root) -> None:
    with pytest.raises(ValueError):
        runner.execute(_request(run_root, repo, [PY, "-c", "pass"], kind="GENESIS"))


def test_run_ids_are_unique_and_not_bare_timestamps(repo, run_root) -> None:
    ids = {runner.execute(_request(run_root, repo, [PY, "-c", "pass"])).run_id for _ in range(3)}
    assert len(ids) == 3
    for run_id in ids:
        stamp, _, nonce = run_id.partition("-")
        assert len(nonce) >= 12


def test_the_utc_stamps_are_iso_and_the_duration_is_not_their_difference(repo, run_root) -> None:
    out = runner.execute(_request(run_root, repo, [PY, "-c", "pass"]))
    timing = out.receipt["timing"]
    start = datetime.strptime(timing["started_utc"], "%Y-%m-%dT%H:%M:%S.%fZ")
    end = datetime.strptime(timing["ended_utc"], "%Y-%m-%dT%H:%M:%S.%fZ")
    assert abs((end - start) - timedelta(seconds=timing["wall_seconds"])) < timedelta(seconds=1)
