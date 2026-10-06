"""Hostile local control-plane tests; synthetic evidence is never production assurance."""
from __future__ import annotations

import copy
import json
import pathlib
import re
import subprocess

import pytest

from tests import certification_fixtures as fx
from tools.certification import core_certificate as cc
from tools.certification import hardening_assurance as ha
from tools.certification import local_assurance as la
from tools.certification import mutation_population as mp
from tools.certification import recertification_scope as rs
from tools.certification.certificate_lineage import verify_certificate_child

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def measured(tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "SCOPE", fx.SCOPE)
    gates = tuple(g for g in rs.RECERTIFY_SOURCE_GATES if g not in {
        f"v4_mutations_{i}" for i in range(4, 8)})
    monkeypatch.setattr(rs, "RECERTIFY_SOURCE_GATES", gates)
    monkeypatch.setattr(ha, "RECERTIFY_SOURCE_GATES", gates)
    monkeypatch.setattr(mp, "V4_SHARD_COUNT", fx.POLICY.v4_shard_count)
    root = tmp_path / "repo"
    source = fx.make_repo(root)
    fx.git(root, "remote", "add", "origin", "https://github.com/owner/repo.git")
    base = tmp_path / "evidence"
    monkeypatch.setenv("FORGE_LOCAL_EVIDENCE_DIR", str(base))
    directory = fx.write_evidence(root, source, base / source)
    runtimes = {}
    for version, gate in (("3.11", "fast311"), ("3.12", "fast312")):
        freeze = la.evidence_path(directory, source, gate, "pip_freeze").read_text()
        runtimes[version] = {"version": version + ".9", "executable": "/synthetic/python" + version,
            "executable_sha256": "a" * 64, "implementation": "CPython", "os": "synthetic OS",
            "argv": ["/synthetic/python" + version], "pip_freeze": freeze,
            "pip_freeze_sha256": la.digest(freeze.encode())}
    records = {gate: {"result": "success", "source_commit": source,
        "runtime": "3.11" if gate == "fast311" else "3.12", "clean_before": True,
        "clean_after": True, "commands": [{"argv": ["synthetic"], "exit_code": 0,
        "duration_seconds": 1, "log": "synthetic.log"}], "duration_seconds": 1}
        for gate in gates}
    for gate in gates:
        version = "3.11" if gate == "fast311" else "3.12"
        records[gate]["commands"] = [{"argv": argv, "exit_code": 0, "duration_seconds": 1,
            "log": "synthetic.log"} for argv in la.gate_commands(root, directory, source,
            gate, runtimes[version]["argv"], tmp_path / "scratch", 4)]
        for index, command in enumerate(records[gate]["commands"]):
            location = la.evidence_path(directory, source, gate, "gate").parent
            name = (ha.EVIDENCE[gate][1]["log"] if gate.startswith("formal_mutations_") and index == 0
                    else f"command-{index}.log")
            command["log"] = name
            if not (location / name).exists():
                (location / name).write_bytes(b"synthetic command log\n")
    receipt = la.make_receipt(root, source, directory, runtimes=runtimes, gates=records,
        started="2026-10-06T00:00:00+00:00", ended="2026-10-06T00:00:01+00:00",
        duration=1, scratch=tmp_path / "scratch", workers=4, policy=fx.POLICY)
    la.write(directory / "receipt.json", receipt)
    return root, source, directory, receipt


def problems(measured, receipt=None):
    root, source, directory, original = measured
    return la.receipt_problems(root, receipt if receipt is not None else original,
                              directory, source_commit=source, policy=fx.POLICY)


def test_every_workflow_is_dispatch_only():
    workflows = list((ROOT / ".github/workflows").glob("*.y*ml"))
    assert workflows
    for path in workflows:
        blocks = re.findall(r"(?m)^on:\n((?:[ \t].*\n|\n)*)", path.read_text())
        assert len(blocks) == 1 and blocks[0].strip() == "workflow_dispatch:", path
        jobs = re.split(r"(?m)^  [A-Za-z0-9_-]+:\s*$", path.read_text().split("jobs:\n", 1)[1])[1:]
        assert jobs and all(re.search(r"(?m)^    if: false", job) for job in jobs), path
        assert "git push" not in path.read_text(), path


def test_synthetic_local_receipt_rederives_and_is_canonical(measured):
    assert problems(measured) == []
    receipt = measured[-1]
    assert la.canonical(receipt) == la.canonical(json.loads(la.canonical(receipt)))
    assert receipt["assurance"]["schema"] == ha.LOCAL_ASSURANCE_SCHEMA
    assert receipt["assurance"]["provenance_mode"] == "local"
    assert "workflow_run_id" not in receipt["assurance"]["lineage"]


@pytest.mark.parametrize("field", ["source_commit", "source_tree", "repository"])
def test_receipt_binds_exact_source_and_repository(measured, field):
    receipt = copy.deepcopy(measured[-1])
    receipt[field] = "wrong"
    assert problems(measured, receipt)


def test_dirty_tree_is_refused_before_any_runtime_or_gate(measured, monkeypatch):
    root, source, _, _ = measured
    fx.write(root, "README.md", "dirty")
    monkeypatch.setattr(la, "probe_runtime", lambda *a: pytest.fail("runtime probe on dirty source"))
    with pytest.raises(la.Refused, match="dirty source tree"):
        la.run(root, ["missing311"], ["missing312"], 4)


def test_changed_head_is_refused(measured):
    root, source, _, _ = measured
    fx.git(root, "commit", "--allow-empty", "-qm", "changed")
    with pytest.raises(la.Refused, match="HEAD changed"):
        la.assert_source(root, source)


@pytest.mark.parametrize("version", la.REQUIRED_PYTHONS)
def test_missing_required_runtime_is_refused(measured, version):
    with pytest.raises(la.Refused, match="Python " + version):
        la.probe_runtime(measured[0], ["FORGE_NONEXISTENT_PYTHON_" + version], version)


def test_probe_script_parses_and_requires_dependencies():
    compile(la.PROBE, "runtime-probe", "exec")
    assert "pip', 'check" in la.PROBE
    assert "md.version" in la.PROBE


@pytest.mark.parametrize("version", la.REQUIRED_PYTHONS)
def test_missing_runtime_identity_in_receipt_is_refused(measured, version):
    receipt = copy.deepcopy(measured[-1])
    del receipt["runtimes"][version]
    assert problems(measured, receipt)


def test_incomplete_gate_evidence_is_refused(measured):
    receipt = copy.deepcopy(measured[-1])
    del receipt["gates"]["scientific312"]
    assert "incomplete gate evidence" in problems(measured, receipt)


def test_failed_mutation_shard_is_refused(measured):
    receipt = copy.deepcopy(measured[-1])
    receipt["gates"]["formal_mutations_0"]["commands"][0]["exit_code"] = 1
    assert any("formal_mutations_0" in p for p in problems(measured, receipt))


def test_surviving_mutation_transcript_is_rederived(measured):
    root, source, directory, receipt = measured
    path = la.evidence_path(directory, source, "formal_mutations_0", "log")
    original = path.read_bytes()
    changed = original.replace(b"RED ", b"GREEN ", 1)
    assert changed != original
    path.write_bytes(changed)
    # Updating the inventory cannot make an inconsistent transcript admissible.
    receipt = copy.deepcopy(receipt)
    receipt["evidence_files"][path.relative_to(directory).as_posix()] = la.digest(path.read_bytes())
    assert problems(measured, receipt)


def test_altered_evidence_is_detected(measured):
    root, source, directory, _ = measured
    la.evidence_path(directory, source, "fast311", "junit_fast").write_bytes(b"altered")
    assert any("altered evidence" in p for p in problems(measured))


def test_evidence_path_escape_is_refused(measured):
    receipt = copy.deepcopy(measured[-1])
    receipt["evidence_files"]["../escape"] = "a" * 64
    assert problems(measured, receipt)


def test_certificate_cannot_claim_another_source(measured):
    root, source, directory, receipt = measured
    assurance = la.bound_assurance(receipt)
    certificate = {"repository": {"commit": "wrong"}}
    assert ha.assurance_problems(root, assurance, source_commit=source,
                                 certificate=certificate, policy=fx.POLICY)


def test_local_provenance_verifies_and_legacy_remains_legacy(measured):
    root, source, directory, receipt = measured
    local = la.bound_assurance(receipt)
    assert ha.assurance_problems(root, local, source_commit=source, policy=fx.POLICY) == []
    old = ha.build_assurance(root, source_commit=source, evidence_dir=directory,
        run=ha.RunContext(executed_commit=source, **fx.RUN), policy=fx.POLICY)
    assert old["schema"] == ha.ASSURANCE_SCHEMA
    assert old["lineage"]["workflow_run_id"] == fx.RUN["run_id"]
    assert ha.assurance_problems(root, old, source_commit=source, policy=fx.POLICY) == []
    old["schema"] = ha.LOCAL_ASSURANCE_SCHEMA
    assert ha.assurance_problems(root, old, source_commit=source, policy=fx.POLICY)


def test_receipt_digest_is_bound_into_certificate(measured):
    root, source, directory, receipt = measured
    assurance = la.bound_assurance(receipt)
    assurance["local_provenance"]["receipt"]["duration_seconds"] += 1
    assert ha.assurance_problems(root, assurance, source_commit=source, policy=fx.POLICY)


def test_local_certificate_child_has_exactly_one_measured_parent(measured):
    root, source, directory, receipt = measured
    cert = cc.build_certificate(root, assurance=la.bound_assurance(receipt))
    child = fx.commit_child(root, cert)
    assert fx.git(root, "rev-parse", "HEAD^") == source
    result = verify_certificate_child(root, policy=fx.POLICY)
    assert result.ok, result.render()
    fx.write(root, "README.md", "unrelated change")
    fx.commit(root, "extra commit after certificate")
    assert not verify_certificate_child(root, policy=fx.POLICY).ok


def test_github_status_checks_are_not_required():
    from tools.certification.branch_policy import REQUIRED_STATUS_CHECKS
    assert REQUIRED_STATUS_CHECKS == ()


def test_partial_execution_never_prints_pass(measured, monkeypatch, capsys):
    monkeypatch.setattr(cc, "repo_root", lambda *_: measured[0])
    monkeypatch.setattr(la, "run", lambda *a: (_ for _ in ()).throw(la.Refused("incomplete")))
    assert la.main(["run"]) == 1
    output = capsys.readouterr().out
    assert "LOCAL_ASSURANCE: REFUSED" in output and "SAFE_TO_PUSH: NO" in output
    assert "LOCAL_ASSURANCE: PASS" not in output


def test_a_changed_gate_plan_cannot_claim_passing_evidence(measured):
    receipt = copy.deepcopy(measured[-1])
    receipt["gates"]["fast311"]["commands"][1]["argv"].extend(["-k", "one_test"])
    assert any("mandatory gate plan" in p for p in problems(measured, receipt))


def test_linked_worktree_is_refused_before_mutation_execution(measured, tmp_path):
    root, source, _, _ = measured
    linked = tmp_path / "linked"
    fx.git(root, "worktree", "add", "--detach", str(linked), source)
    with pytest.raises(la.Refused, match="standalone Git clone"):
        la.require_supported_checkout(linked)


def test_failed_command_keeps_exact_timing_without_pass_receipt(tmp_path):
    import sys
    log = tmp_path / "failed.log"
    with pytest.raises(la.Refused, match="gate command failed"):
        la.execute(tmp_path, [sys.executable, "-c", "raise SystemExit(7)"], log)
    result = json.loads((tmp_path / "failed.log.result.json").read_bytes())
    assert result["exit_code"] == 7 and result["duration_seconds"] >= 0
    assert not (tmp_path / "receipt.json").exists()


@pytest.mark.parametrize("proof", [[], {"receipt": []}, {"receipt": {"assurance": []}}])
def test_malformed_local_proof_refuses_without_crashing(measured, proof):
    root, source, _, _ = measured
    assurance = {"schema": ha.LOCAL_ASSURANCE_SCHEMA, "provenance_mode": "local",
                 "local_provenance": proof}
    assert ha.assurance_problems(root, assurance, source_commit=source, policy=fx.POLICY)


@pytest.mark.parametrize("tamper", ["evidence", "runtime311", "runtime312", "head", "receipt"])
def test_self_checks_cannot_change_evidence_runtime_or_head_before_push(measured, monkeypatch, tamper):
    from types import SimpleNamespace
    from tools.certification import certificate_lineage
    root, source, directory, receipt = measured
    cert = cc.build_certificate(root, assurance=la.bound_assurance(receipt))
    fx.commit_child(root, cert)
    checked = []

    def load_checked(root, source):
        current = json.loads((directory / "receipt.json").read_bytes())
        reasons = la.receipt_problems(root, current, directory, source_commit=source, policy=fx.POLICY)
        if reasons:
            raise la.Refused("; ".join(reasons))
        return directory, current

    def probe(root, argv, version):
        checked.append(version)
        result = copy.deepcopy(receipt["runtimes"][version])
        if ran[0] and tamper == "runtime" + version.replace(".", ""):
            result["executable_sha256"] = "b" * 64
        return result

    ran = [False]
    def execute(root, argv, log):
        pathlib.Path(argv[-1]).write_bytes(b"synthetic self-check report")
        log.write_bytes(b"synthetic self-check log")
        ran[0] = True
        if tamper == "evidence":
            la.evidence_path(directory, source, "fast311", "junit_fast").write_bytes(b"tampered")
        if tamper == "head":
            fx.git(root, "commit", "--allow-empty", "-qm", "changed during self checks")
        if tamper == "receipt":
            altered = copy.deepcopy(receipt)
            altered["duration_seconds"] += 1
            la.write(directory / "receipt.json", altered)
        return {"argv": argv, "exit_code": 0, "duration_seconds": 1, "log": log.name}

    monkeypatch.setattr(la, "load_receipt", load_checked)
    monkeypatch.setattr(la, "probe_runtime", probe)
    monkeypatch.setattr(la, "execute", execute)
    monkeypatch.setattr(certificate_lineage, "verify_certificate_child", lambda *a: SimpleNamespace(ok=True))
    monkeypatch.setattr(rs, "junit_problems", lambda *a: [])
    with pytest.raises(la.Refused):
        la.verify(root)
    assert ran[0]
    assert "3.11" in checked and "3.12" in checked
