"""One classifier decides who owns a change, and it can never be narrower than the certificate.

Findings C, F and the workflow-ownership half of G. Before this round the
recertify workflow's path filter and the Tests workflow's shell ``case`` were
two hand-kept lists in two wildcard dialects, and neither covered four of the
certificate's own scope areas. These tests enumerate ``SCOPE`` itself, so a new
scope area that is not a recertification trigger fails here rather than merging
on the ordinary suite.

Workflow behaviour is tested through the Python both workflows call. The last
section reads the workflow files only as tripwires for divergence between those
files and the Python constants; it is not where behaviour is proved.
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

from tests import certification_fixtures as fx
from tools.certification import core_certificate
from tools.certification import recertification_scope as rs
from tools.certification.branch_policy import REQUIRED_STATUS_CHECKS
from tools.certification.hardening_assurance import EVIDENCE

REPO = pathlib.Path(__file__).resolve().parents[1]
WORKFLOWS = REPO / ".github" / "workflows"


def _examples(pattern: str) -> list[str]:
    """Concrete paths a pattern must match: each ``**`` as zero, one and two segments."""
    variants = [[]]
    for segment in pattern.split("/"):
        if segment == "**":
            variants = [v + extra for v in variants for extra in ([], ["a"], ["a", "b"])]
        else:
            variants = [v + [segment.replace("*", "x").replace("?", "q")] for v in variants]
    return sorted({"/".join(v) for v in variants})


# ---- every SCOPE pattern is a trigger -----------------------------------------------------------
@pytest.mark.parametrize("area", core_certificate.SCOPE, ids=lambda a: a.name)
def test_every_scope_pattern_requires_recertification(area):
    for pattern in area.patterns:
        for path in _examples(pattern):
            assert f"certified:{area.name}" in rs.recertification_reasons(path), (pattern, path)


@pytest.mark.parametrize("area", core_certificate.SCOPE, ids=lambda a: a.name)
def test_every_file_the_certificate_enumerates_requires_recertification(area):
    files = core_certificate.enumerate_area(REPO, area)
    assert files
    assert [f for f in files if not rs.requires_recertification(f)] == []


@pytest.mark.parametrize("path", [
    "src/engcore/scientific/results/validation.py",
    "src/engcore/scientific/new_subpackage/module.py",
    "src/engcore/scientific/py.typed",
    "src/engcore/domains/__init__.py",
    "src/engcore/data/store.py",
    "src/engcore/data/fixtures/reference.json",
    "src/engcore/adequacy/predictive.py",
    "src/engcore/inference/calibration.py",
    "tools/certification/core_certificate.py",
    "tools/certification/a_new_module.py",
    "tools/__init__.py",
    ".github/workflows/recertify-hardened-core.yml",
    ".github/workflows/tests.yml",
    "benchmarks/core_freeze_v1/audit/reproduce.py",
    "certification/current_core_v2.json",
    "src/engcore/execution/trusted.py",
    "benchmarks/trust_hardening/audit/mutations.py",
    "tests/test_anything.py",
    "pyproject.toml",
])
def test_certified_and_trust_sensitive_paths_require_recertification(path):
    assert rs.requires_recertification(path), path


@pytest.mark.parametrize("path", [
    "README.md",
    "docs/TESTING.md",
    "src/engcore/domains/thermal/conduction1d/solver.py",
    "src/engcore/mcp/server.py",
    "src/engcore/uq/representation.py",
    "src/engcore/scientificx/module.py",
    "src/engcore/scientific.py",
    "experiments/thermal_t1/config.py",
    "benchmarks/hard/score_hard.py",
    "requirements.txt",
    "Dockerfile",
    ".github/workflows/trust-mutations.yml",
    "tools/other/helper.py",
])
def test_non_core_paths_stay_ordinary(path):
    assert not rs.requires_recertification(path), (path, rs.recertification_reasons(path))


def test_dependency_manifests_are_decided_not_collected():
    assert set(rs.recertification_reasons("pyproject.toml")) == {"certified:runtime_dependencies", "dependency_manifest"}
    excluded = dict(rs.EVALUATED_AND_EXCLUDED)
    assert {"requirements.txt", "Dockerfile"} <= set(excluded)
    # The exclusion's premise, as a tripwire: nothing CI runs installs from it.
    for workflow in WORKFLOWS.glob("*.yml"):
        text = workflow.read_text(encoding="utf-8")
        assert not re.search(r"pip[^\n]*install[^\n]*-r\s", text), workflow.name
        assert "requirements.txt" not in text, workflow.name
    dockerfile = (REPO / "Dockerfile").read_text(encoding="utf-8")
    assert not re.search(r"pip[^\n]*install[^\n]*requirements", dockerfile)


# ---- the matcher agrees with how the certificate enumerates ---------------------------------------
NEAR_MISSES = (
    "src/engcore/scientific/a.py", "src/engcore/scientific/sub/b.py",
    "src/engcore/scientific/sub/deeper/c.py", "src/engcore/scientific/data.json",
    "src/engcore/scientific.py", "src/engcore/scientificx/d.py",
    "src/engcore/domains/__init__.py", "src/engcore/domains/thermal/__init__.py",
    "src/engcore/data/e.py", "src/engcore/adequacy/f.py", "src/engcore/inference/g/h.py",
    "tests/mutation_guards.py", "tests/sub/mutation_guards.py",
    "tools/__init__.py", "tools/certification/i.py", "tools/certification/sub/j.py",
    "tools/certification/k.txt", ".github/workflows/tests.yml", ".github/workflows/other.yml",
    "benchmarks/core_freeze_v1/audit/reproduce.py", "pyproject.toml", "sub/pyproject.toml",
    "certification/current_core_v2.json",
)


def test_the_matcher_agrees_with_pathlib_glob_for_every_scope_pattern(tmp_path):
    for relative in NEAR_MISSES:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x")
    for area in core_certificate.SCOPE:
        for pattern in area.patterns:
            globbed = {p.relative_to(tmp_path).as_posix() for p in tmp_path.glob(pattern) if p.is_file()}
            matched = {p for p in NEAR_MISSES if rs.match(pattern, p)}
            assert matched == globbed, (pattern, sorted(matched ^ globbed))


def test_a_trigger_is_never_narrower_than_its_scope_pattern():
    for area in core_certificate.SCOPE:
        for pattern in area.patterns:
            for path in NEAR_MISSES:
                if rs.match(pattern, path):
                    assert rs.match(rs.widen(pattern), path), (pattern, path)


def test_a_single_star_does_not_cross_a_directory_as_a_shell_case_would():
    assert rs.match("tools/certification/*.py", "tools/certification/a.py")
    assert not rs.match("tools/certification/*.py", "tools/certification/sub/a.py")
    assert rs.match("src/engcore/data/**", "src/engcore/data/a/b.json")
    assert not rs.match("src/engcore/data/**", "src/engcore/data")


# ---- ownership of a real event ----------------------------------------------------------------------
@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    base = fx.make_repo(root)
    fx.git(root, "branch", "-q", "base")
    return root, base


def _pull_request(root, base, *changes, message="change"):
    for path, content in changes:
        fx.write(root, path, content)
    head = fx.commit(root, message)
    return rs.classify(root, event="pull_request", base=base, head=head)


@pytest.mark.parametrize("path", [
    "src/engcore/scientific/record.py", "src/engcore/domains/__init__.py",
    "src/engcore/data/store.py", "src/engcore/adequacy/predictive.py",
    "src/engcore/inference/grid.py", "pyproject.toml",
])
def test_a_core_pull_request_is_delegated_to_recertification(repo, path):
    root, base = repo
    ownership = _pull_request(root, base, (path, "CHANGED = True\n"))
    assert ownership.mode == rs.RECERTIFY_SOURCE
    outputs = ownership.outputs()
    assert outputs["recertification"] == "source" and outputs["delegate_to_recertify"] == "true"
    assert outputs["source_sha"] == ownership.head
    assert path in ownership.reasons


def test_an_ordinary_pull_request_uses_the_normal_tests(repo):
    root, base = repo
    ownership = _pull_request(root, base, ("docs/guide.md", "words\n"))
    assert ownership.mode == rs.ORDINARY
    assert ownership.outputs() | {} == {**ownership.outputs(), "recertification": "not_required",
                                        "delegate_to_recertify": "false", "certificate_child": "false"}


def test_a_main_push_uses_the_normal_tests(repo):
    root, _base = repo
    for event in ("push", "workflow_dispatch"):
        ownership = rs.classify(root, event=event)
        assert ownership.mode == rs.FULL_SUITE
        assert ownership.outputs()["recertification"] == "not_required"


def test_a_certificate_child_is_lightweight_and_names_its_parent(repo):
    root, base = repo
    fx.write(root, "src/engcore/scientific/record.py", "VALUE = 5\n")
    source = fx.commit(root, "core change")
    child = fx.commit_child(root, b'{"schema": "core_certificate/2"}\n')
    ownership = rs.classify(root, event="pull_request", base=base, head=child)
    assert ownership.mode == rs.CERTIFICATE_CHILD
    assert ownership.outputs() | {} == {**ownership.outputs(), "certificate_child": "true",
                                        "recertification": "certificate_child",
                                        "source_sha": source, "certificate_sha": child}


def test_the_reserved_subject_on_a_commit_that_changes_more_is_an_error(repo):
    root, base = repo
    fx.write(root, "README.md", "also changed\n")
    fx.git(root, "add", "README.md")
    child = fx.commit_child(root, b"{}\n")
    with pytest.raises(rs.OwnershipError, match="not a certificate-only child"):
        rs.classify(root, event="pull_request", base=base, head=child)


def test_an_edit_to_the_certificate_without_the_subject_is_recertified(repo):
    root, base = repo
    head = fx.commit_child(root, b"{}\n", subject="tweak the certificate")
    ownership = rs.classify(root, event="pull_request", base=base, head=head)
    assert ownership.mode == rs.RECERTIFY_SOURCE
    assert "stored_certificate" in ownership.reasons[rs.CERTIFICATE_PATH]


def test_a_core_change_behind_a_later_docs_commit_is_still_recertified(repo):
    root, base = repo
    fx.write(root, "src/engcore/inference/grid.py", "GRID = 1\n")
    fx.commit(root, "core")
    ownership = _pull_request(root, base, ("docs/later.md", "later\n"))
    assert ownership.mode == rs.RECERTIFY_SOURCE


def test_a_certificate_child_followed_by_any_commit_is_recertified_again(repo):
    root, base = repo
    fx.write(root, "src/engcore/scientific/record.py", "VALUE = 6\n")
    fx.commit(root, "core")
    fx.commit_child(root, b"{}\n")
    ownership = _pull_request(root, base, ("docs/after.md", "after the certificate\n"))
    assert ownership.mode == rs.RECERTIFY_SOURCE


def test_the_changed_set_includes_the_pull_requests_own_diff_when_the_base_moved(repo):
    root, base = repo
    fx.write(root, "src/engcore/adequacy/predictive.py", "PAIRING = 1\n")
    head = fx.commit(root, "core change on the branch")
    fx.git(root, "checkout", "-q", "base")
    fx.write(root, "src/engcore/adequacy/predictive.py", "PAIRING = 1\n")
    fx.write(root, "docs/base.md", "base moved\n")
    moved_base = fx.commit(root, "the same change landed on base")
    ownership = rs.classify(root, event="pull_request", base=moved_base, head=head)
    assert "src/engcore/adequacy/predictive.py" in ownership.changed
    assert ownership.mode == rs.RECERTIFY_SOURCE


# ---- the aggregate gates: a skipped required job must not pass ----------------------------------------
def _needs(names, default="skipped", **results):
    return {name: {"result": results.get(name, default), "outputs": {}} for name in names}


def test_the_recertification_gate_for_a_source_commit():
    ok = _needs(rs.RECERTIFY_JOBS, default="success", verify_certificate_child="skipped")
    assert rs.recertification_gate_problems("source", ok) == []
    for job in (*rs.RECERTIFY_SOURCE_GATES, "certify"):
        for state in ("failure", "skipped", "cancelled"):
            broken = {**ok, job: {"result": state}}
            assert rs.recertification_gate_problems("source", broken), (job, state)


def test_the_recertification_gate_for_a_certificate_child_requires_the_child_job_to_run():
    ok = _needs(rs.RECERTIFY_JOBS, classify="success", verify_certificate_child="success")
    assert rs.recertification_gate_problems("certificate_child", ok) == []
    skipped = {**ok, "verify_certificate_child": {"result": "skipped"}}
    assert rs.recertification_gate_problems("certificate_child", skipped)


def test_the_recertification_gate_for_a_change_that_needs_none():
    ok = _needs(rs.RECERTIFY_JOBS, classify="success")
    assert rs.recertification_gate_problems("not_required", ok) == []
    assert rs.recertification_gate_problems("not_required", {**ok, "certify": {"result": "failure"}})


@pytest.mark.parametrize("mode", ["", "unclassified", "full_suite"])
def test_the_recertification_gate_refuses_an_unknown_mode(mode):
    assert rs.recertification_gate_problems(mode, _needs(rs.RECERTIFY_JOBS, classify="success"))


def test_the_recertification_gate_refuses_a_failed_classification_or_a_missing_job():
    assert rs.recertification_gate_problems("not_required", _needs(rs.RECERTIFY_JOBS, classify="failure"))
    partial = _needs([j for j in rs.RECERTIFY_JOBS if j != "certify"], classify="success")
    assert rs.recertification_gate_problems("not_required", partial)


def test_the_tests_gate_for_each_mode():
    ordinary = _needs(rs.TESTS_JOBS, default="success", **{"certificate-child": "skipped"})
    assert rs.tests_gate_problems(rs.ORDINARY, ordinary, event="pull_request") == []
    assert rs.tests_gate_problems(rs.FULL_SUITE, ordinary, event="push") == []
    assert rs.tests_gate_problems(rs.ORDINARY, {**ordinary, "scientific": {"result": "skipped"}}, event="pull_request")
    assert rs.tests_gate_problems(rs.FULL_SUITE, ordinary, event="pull_request")

    delegated = _needs(rs.TESTS_JOBS, scope="success", **{"repo-layout": "success"})
    assert rs.tests_gate_problems(rs.RECERTIFY_SOURCE, delegated, event="pull_request") == []

    child = _needs(rs.TESTS_JOBS, scope="success", **{"repo-layout": "success", "certificate-child": "success"})
    assert rs.tests_gate_problems(rs.CERTIFICATE_CHILD, child, event="pull_request") == []
    assert rs.tests_gate_problems(rs.CERTIFICATE_CHILD, {**child, "certificate-child": {"result": "skipped"}},
                                  event="pull_request")
    assert rs.tests_gate_problems("unclassified", child, event="pull_request")


# ---- the deferred self-checks ----------------------------------------------------------------------------
def test_every_deferred_self_check_names_a_real_test():
    for node in rs.CERTIFICATE_SELF_CHECKS:
        module, _, name = node.partition("::")
        tree = ast.parse((REPO / module).read_bytes().decode("utf-8-sig"))
        assert name in {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}, node


def _junit(cases):
    body = "".join(
        f'<testcase classname="{c}" name="{n}">{extra}</testcase>' for c, n, extra in cases
    )
    return f'<testsuites><testsuite name="pytest" tests="{len(cases)}">{body}</testsuite></testsuites>'.encode()


def _self_check_cases(**extras):
    cases = []
    for node in rs.CERTIFICATE_SELF_CHECKS:
        module, _, name = node.partition("::")
        cases.append((module.removesuffix(".py").replace("/", "."), name, extras.get(name, "")))
    return cases


def test_self_checks_must_all_be_reported_passed():
    assert rs.junit_problems(_junit(_self_check_cases())) == []
    first = rs.CERTIFICATE_SELF_CHECKS[0].split("::")[1]
    for extra in ('<skipped message="skipped by a hook"/>', '<failure message="no"/>', '<error message="e"/>'):
        problems = rs.junit_problems(_junit(_self_check_cases(**{first: extra})))
        assert problems and first in problems[0]
    assert rs.junit_problems(_junit(_self_check_cases()[1:]))
    assert rs.junit_problems(_junit([*_self_check_cases(), ("tests.other", "test_x", "")]))
    assert rs.junit_problems(b"<not xml")


# ---- tripwires: the workflow files agree with the Python they call --------------------------------------------
def _jobs(workflow: str) -> dict[str, str]:
    text = (WORKFLOWS / workflow).read_text(encoding="utf-8")
    body = text.split("\njobs:\n", 1)[1]
    blocks: dict[str, str] = {}
    for chunk in re.split(r"\n(?=  [A-Za-z0-9_-]+:\n)", "\n" + body):
        match_ = re.match(r"\n?  ([A-Za-z0-9_-]+):\n", chunk)
        if match_:
            blocks[match_.group(1)] = chunk
    return blocks


def _needs_of(block: str) -> list[str]:
    inline = re.search(r"\n    needs: ([A-Za-z0-9_-]+)\n", block)
    if inline:
        return [inline.group(1)]
    listed = re.search(r"\n    needs:\n((?:      - [A-Za-z0-9_-]+\n)+)", block)
    return re.findall(r"- ([A-Za-z0-9_-]+)", listed.group(1)) if listed else []


def test_recertification_has_no_path_filter_and_both_workflows_call_the_classifier():
    recertify = (WORKFLOWS / "recertify-hardened-core.yml").read_text(encoding="utf-8")
    trigger = recertify.split("\npermissions:", 1)[0]
    assert "paths" not in trigger
    for workflow in ("recertify-hardened-core.yml", "tests.yml"):
        assert "tools.certification.recertification_scope classify" in (WORKFLOWS / workflow).read_text(encoding="utf-8")


def test_the_recertify_topology_matches_the_python_it_is_judged_by():
    jobs = _jobs("recertify-hardened-core.yml")
    assert set(rs.RECERTIFY_JOBS) | {"recertification_gate"} == set(jobs)
    assert set(_needs_of(jobs["certify"])) == {"classify", *rs.RECERTIFY_SOURCE_GATES}
    assert _needs_of(jobs["recertification_gate"]) == list(rs.RECERTIFY_JOBS)
    for gate in rs.RECERTIFY_SOURCE_GATES:
        block = jobs[gate]
        assert "tools.certification.assert_clean_tree" in block, gate
        prefix, files = EVIDENCE[gate]
        index = gate.rsplit("_", 1)[-1] if gate.startswith("formal_mutations_") else None
        if index is not None:
            prefix = prefix.removesuffix(f"-{index}") + "-${{ env.SHARD_INDEX }}"
        assert f"name: {prefix}-${{{{ needs.classify.outputs.source_sha }}}}" in block, gate
        for filename in files.values():
            expected = filename.replace(index, "${{ env.SHARD_INDEX }}") if index else filename
            assert expected in block, (gate, filename)
        assert "if-no-files-found: error" in block, gate
        if index is not None:
            assert f'SHARD_INDEX: "{index}"' in block, gate


def test_the_tests_topology_matches_the_python_it_is_judged_by():
    jobs = _jobs("tests.yml")
    assert _needs_of(jobs["tests-gate"]) == list(rs.TESTS_JOBS)
    for job in ("fast", "mutations", "scientific", "certificate-child"):
        assert "tools.certification.assert_clean_tree" in jobs[job], job


def test_the_gate_names_are_the_checks_branch_policy_requires():
    names = set()
    for workflow in ("recertify-hardened-core.yml", "tests.yml"):
        for block in _jobs(workflow).values():
            found = re.search(r"\n    name: ([^\n]+)\n", block)
            if found and found.group(1).endswith("-gate"):
                assert "    if: always()" in block
                names.add(found.group(1))
    assert names == set(REQUIRED_STATUS_CHECKS)


def test_no_workflow_erases_evidence_before_the_clean_tree_check():
    for workflow in WORKFLOWS.glob("*.yml"):
        text = workflow.read_text(encoding="utf-8")
        assert not re.search(r"git\s+clean\b", text), workflow.name
        assert not re.search(r"git\s+checkout\s+--\s+\.", text), workflow.name
        assert not re.search(r"git\s+(reset|stash)\b", text), workflow.name
