"""The assurance record is built from evidence, and refuses evidence that does not support it.

``forge.core_hardening_assurance/2`` was written from job output strings, with
``"passed": true`` and ``"survived": 0`` as literals. Version 3 is built by
``tools/certification/hardening_assurance.py`` from the artifacts each gate
uploads. Each case below starts from complete synthetic evidence and removes or
falsifies one piece; the builder must refuse and say which.
"""

from __future__ import annotations

import json

import pytest

from tests import certification_fixtures as fx
from tools.certification import core_certificate
from tools.certification.hardening_assurance import (
    ASSURANCE_SCHEMA,
    EVIDENCE,
    AssuranceError,
    RunContext,
    build_assurance,
    ngspice_version,
)
from tools.certification.recertification_scope import RECERTIFY_SOURCE_GATES


@pytest.fixture
def source(tmp_path, monkeypatch):
    monkeypatch.setattr(core_certificate, "SCOPE", fx.SCOPE)
    root = tmp_path / "repo"
    fx.make_repo(root)
    head = fx.git(root, "rev-parse", "HEAD")
    evidence = fx.write_evidence(root, head, tmp_path / "evidence")
    return root, head, evidence


def _build(root, head, evidence, **run):
    context = dict(fx.RUN, executed_commit=head)
    context.update(run)
    return build_assurance(root, source_commit=head, evidence_dir=evidence,
                           run=RunContext(**context), policy=fx.POLICY)


def _file(evidence, head, gate, key):
    prefix, files = EVIDENCE[gate]
    return evidence / f"{prefix}-{head}" / files[key]


def _refused(root, head, evidence, fragment, **run):
    with pytest.raises(AssuranceError) as caught:
        _build(root, head, evidence, **run)
    assert any(fragment in problem for problem in caught.value.problems), caught.value.problems


def test_every_source_gate_has_an_evidence_layout():
    assert set(EVIDENCE) == set(RECERTIFY_SOURCE_GATES)


def test_complete_evidence_builds_a_record_that_distinguishes_its_claims(source):
    root, head, evidence = source
    record = _build(root, head, evidence)
    assert record["schema"] == ASSURANCE_SCHEMA
    assert record["source_commit"] == head == record["environment"]["source_commit"]
    assert record["lineage"]["certificate_parent"] == head
    assert record["lineage"]["workflow_run_id"] == fx.RUN["run_id"]
    functional = record["functional"]["fast_python_3_11"]
    assert functional["suites"]["fast"]["tests"] == 3 and "junit_sha256" in functional["suites"]["fast"]
    assert "passed" not in json.dumps(record["functional"]).replace("PASSED", "")
    assert record["formal_guard_mutations"]["ids"] == list(fx.FORMAL_IDS)
    assert record["trust_hardening_mutations"]["ids"] == list(fx.TRUST_IDS)
    assert record["environment"]["ngspice"] == "ngspice-42 : Circuit level simulation program"
    assert record["control_plane"]["area"] == "certification_control"


def test_a_missing_gate_record_is_refused(source):
    root, head, evidence = source
    _file(evidence, head, "scientific312", "gate").unlink()
    _refused(root, head, evidence, "scientific312: missing evidence")


def test_a_gate_that_measured_another_commit_is_refused(source):
    root, head, evidence = source
    path = _file(evidence, head, "fast312", "gate")
    record = json.loads(path.read_bytes())
    record["head_commit"] = "0" * 40
    path.write_bytes(json.dumps(record).encode())
    _refused(root, head, evidence, "fast312: measured")


def test_a_gate_that_did_not_prove_a_clean_checkout_is_refused(source):
    root, head, evidence = source
    path = _file(evidence, head, "trust_mutations", "gate")
    record = json.loads(path.read_bytes())
    record["clean_tree_after_gate"] = False
    path.write_bytes(json.dumps(record).encode())
    _refused(root, head, evidence, "trust_mutations: did not prove a clean checkout")


@pytest.mark.parametrize("suite, xml, fragment", [
    ("junit_fast", b'<testsuites><testsuite tests="9" failures="1" errors="0" skipped="0"/></testsuites>', "no failures"),
    ("junit_fast", b'<testsuites><testsuite tests="0" failures="0" errors="0" skipped="0"/></testsuites>', "needs tests"),
    ("junit_dependency_guard", b"<testsuites", "not a JUnit report"),
])
def test_a_functional_suite_without_a_clean_report_is_refused(source, suite, xml, fragment):
    root, head, evidence = source
    _file(evidence, head, "fast311", suite).write_bytes(xml)
    _refused(root, head, evidence, fragment)


def test_a_wrong_interpreter_is_refused(source):
    root, head, evidence = source
    _file(evidence, head, "fast311", "python").write_bytes(b"Python 3.12.1\n")
    _refused(root, head, evidence, "fast311 ran under")


def test_the_masked_ngspice_banner_is_not_a_version(source):
    root, head, evidence = source
    assert ngspice_version(b"******\n") == ""
    _file(evidence, head, "scientific312", "ngspice").write_bytes(b"******\n")
    _refused(root, head, evidence, "ngspice-<version>")


def test_a_shard_transcript_with_a_surviving_mutation_is_refused(source):
    root, head, evidence = source
    ids = tuple(_file(evidence, head, "formal_mutations_1", "ids").read_bytes().decode().split())
    _file(evidence, head, "formal_mutations_1", "log").write_bytes(
        fx.harness_log(ids, verdicts={ids[0]: "GREEN -- DECORATION"}, tally=(len(ids), len(ids)))
    )
    _refused(root, head, evidence, "not killed")


def test_a_duplicated_shard_is_refused_even_with_a_consistent_count(source):
    root, head, evidence = source
    for key in ("ids", "log", "record"):
        _file(evidence, head, "formal_mutations_1", key).write_bytes(
            _file(evidence, head, "formal_mutations_0", key).read_bytes()
        )
    _refused(root, head, evidence, "recorded more than once")


def test_a_trust_population_with_a_survivor_is_refused(source):
    root, head, evidence = source
    result = fx.trust_result(status=lambda mid: "SURVIVED" if mid == fx.TRUST_IDS[1] else "KILLED")
    _file(evidence, head, "trust_mutations", "result").write_bytes(json.dumps(result).encode())
    _refused(root, head, evidence, "not killed")


def test_a_trust_result_for_a_different_population_is_refused(source):
    root, head, evidence = source
    result = fx.trust_result(ids=(fx.TRUST_IDS[0], "TRUST-ELSEWHERE"))
    _file(evidence, head, "trust_mutations", "result").write_bytes(json.dumps(result).encode())
    _refused(root, head, evidence, "not the runner's population")


def test_a_merge_preview_with_different_certified_bytes_is_refused(source):
    root, head, evidence = source
    fx.write(root, "src/engcore/scientific/record.py", "VALUE = 7\n")
    preview = fx.commit(root, "base moved a certified file")
    fx.git(root, "checkout", "-q", head)
    _refused(root, head, evidence, "differ in certified files", executed_commit=preview)


def test_certify_must_run_on_the_source_commit(source):
    root, head, evidence = source
    fx.write(root, "README.md", "moved on\n")
    fx.commit(root, "another commit")
    _refused(root, head, evidence, "certify is running on")
