"""Bounded development rehearsal tests; no formal measurement."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

spec = importlib.util.spec_from_file_location(
    "blindfold_demo", Path(__file__).resolve().parents[2] / "tools/forge_blindfold_demo.py")
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


def test_real_development_path_and_replay_without_formal_access(monkeypatch):
    # The pinned preregistration builder imports these modules for code identity.
    # Imports are not formal admissions or access to a registry/root.
    from benchmarks.genesis_lite.v0_3 import formal, registry
    def forbidden(*args, **kwargs):
        raise AssertionError("formal entrypoint / registry access forbidden")
    for name in ("run_formal", "preflight", "verify_attempt", "master_for"):
        monkeypatch.setattr(formal, name, forbidden)
    monkeypatch.setattr(registry.AttemptRegistry, "__init__", forbidden)
    monkeypatch.setattr(registry.EvaluatorInbox, "__init__", forbidden)
    from benchmarks.genesis_lite import harness as old_harness
    original_key = old_harness.export_answer_key
    def public_key_only(seed, campaign, *args, **kwargs):
        assert seed == demo.PUBLIC_SEED and campaign.startswith("public-demo-v1-")
        return original_key(seed, campaign, *args, **kwargs)
    monkeypatch.setattr(old_harness, "export_answer_key", public_key_only)
    a = demo.worker("careful", "anonymous")
    b = demo.worker("careful", "anonymous")
    assert demo.complete(a) and demo.complete(b)
    assert a["tier_bound"] == "development" and a["isolation"] == "in_process"
    assert demo.semantic(a) == demo.semantic(b)
    assert {r["kind"] for r in a["universes"]} == set(demo.KINDS)
    assert all("proposal" in r and "observe_calls" in r for r in a["universes"])
    altered = copy.deepcopy(b)
    altered["report_digest"] = "ephemeral"
    altered["wall_seconds"] = 999
    altered["universes"][0]["proposer_seconds"] = 999
    assert demo.semantic(a) == demo.semantic(altered)
    altered["universes"][0]["credit"] += 1
    assert demo.semantic(a) != demo.semantic(altered)
    altered = copy.deepcopy(b)
    altered["key_digest"] = "different-world"
    assert demo.semantic(a) != demo.semantic(altered)


@pytest.mark.parametrize("args", [
    ["--formal"], ["--tier", "formal"], ["--root", "/private"], ["--registry", "/registry"],
    ["--seed", "better"], ["--arm-spec", "evil:run"], ["--worker", "evil:run", "anonymous"],
    ["--worker", "careful", "trap"], ["--worker", "careful", "raw"], ["--timeout", "121"],
])
def test_entrypoint_rejects_forbidden_inputs(args):
    with pytest.raises(SystemExit) as exc:
        demo.main(args)
    assert exc.value.code == 2


def test_arbitrary_callable_rejected_before_harness(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("untrusted proposer was executed")
    with pytest.raises(ValueError):
        demo.worker(forbidden, "anonymous")
    with pytest.raises(ValueError):
        demo.worker("custom.module:arm", "anonymous")


def test_timeout_and_worker_error_retained(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 1, output=b"partial", stderr=b"timeout detail")
    monkeypatch.setattr(subprocess, "run", timeout)
    record = demo.execute("careful", "anonymous", 1)
    assert record["status"] == "DEMO_EXECUTION_FAILED"
    assert record["evaluator_status"] == "UNKNOWN" and record["stderr"] == "timeout detail"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], 7, "", "failure detail"))
    assert demo.execute("careful", "anonymous")["stderr"] == "failure detail"


def test_failures_retained_in_matrix_and_html(monkeypatch):
    calls = []
    def fail(arm, presentation, timeout):
        calls.append((arm, presentation))
        return dict(arm=arm, presentation=presentation, status="DEMO_EXECUTION_FAILED",
                    reasons=["<failure>"], universes=[], evaluator_status="UNKNOWN")
    monkeypatch.setattr(demo, "execute", fail)
    monkeypatch.setattr(demo, "provenance", lambda: {"head": "test-only"})
    report = demo.run_demo()
    assert len(calls) == 12 and len(report["runs"]) == len(report["replay_runs"]) == 6
    assert all(c["status"] == "UNKNOWN" for c in report["semantic_replay"])
    assert report["summary"]["observation_calls"] == "UNKNOWN"
    assert report["status"] == "EXECUTION_INCOMPLETE"
    page = demo.render(report)
    assert "&lt;failure&gt;" in page and "<failure>" not in page
    for label in demo.LABELS:
        assert label in page and label in json.dumps(report)


def test_output_directory_cannot_be_overwritten(tmp_path):
    with pytest.raises(FileExistsError):
        demo.main(["--output", str(tmp_path)])
