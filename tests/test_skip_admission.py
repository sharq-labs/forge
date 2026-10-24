"""Hostile checks for semantic skip admission (Local Assurance Pass 13).

A skip used to count against a per-suite ceiling (FAST 19, SCIENTIFIC 5). A count
admits a newly skipping trust test whenever another test stops skipping, and it
refused the first complete local run for 142 skips that were each explained.
Every case below tries to get a skip admitted that should not be, or shows that a
legitimate skip is admitted for the stated reason and no other.
"""

from __future__ import annotations

import argparse
import copy
import json
import pathlib
from contextlib import nullcontext
from xml.sax.saxutils import quoteattr, escape

import pytest

from tests import certification_fixtures as fx
from tools.certification import core_certificate, skip_admission as sa
from tools.certification.hardening_assurance import (
    EVIDENCE,
    TRUST_SCRIPT,
    AssuranceError,
    RunContext,
    _Evidence,
    assurance_problems,
    build_assurance,
    skip_admission_section,
)
from tools.certification.recertification_scope import CERTIFICATE_SELF_CHECKS

REPO = pathlib.Path(__file__).resolve().parents[1]
MEASURED = REPO / "tests" / "certification_data" / "skip_inventory_d5d886f9.json"

FAKE_TEST = "providers/fake/tests/test_fake_provider.py"
CORE_TEST = "tests/test_core_thing.py"
POLICY = sa.SkipPolicy(
    providers=(
        sa.OptionalProvider("fake", sa.OPTIONAL_PROVIDER_UNAVAILABLE, (sa.Facet("registry", "fake"),)),
        sa.OptionalProvider("other", sa.OPTIONAL_PROVIDER_UNAVAILABLE, (
            sa.Facet("callable", "forge_other:other_available"), sa.Facet("module_spec", "other"))),
    ),
    rules=(
        sa.SkipRule("fake", FAKE_TEST, "Fake unavailable", sa.OPTIONAL_PROVIDER_UNAVAILABLE, ("fake",)),
        sa.SkipRule("other-mesh", FAKE_TEST, "Other: {other}", sa.OPTIONAL_PROVIDER_UNAVAILABLE, ("other",),
                    tests=("test_needs_other",)),
        sa.SkipRule("conditional", CORE_TEST, "this tree is a descendant", sa.DECLARED_CONDITIONAL_SKIP,
                    tests=("test_only_on_the_exact_freeze",), why="binds only on the exact freeze"),
    ),
)
ABS = "/abs/checkout/"


def _skip(path, test, reason, *, line=12, kind="pytest.skip", located=None, classname=None):
    module = path[:-3].replace("/", ".")
    parts = test.split("::")
    classname = classname or ".".join([module, *parts[:-1]])
    location = located if located is not None else ABS + path
    return (classname, parts[-1], kind, reason, f"{location}:{line}: {reason}")


def _junit(*skips, passed=3, declared=None):
    cases = "".join(f'<testcase classname="tests.t" name="p{i}"/>' for i in range(passed))
    for classname, name, kind, message, text in skips:
        attrs = f"type={quoteattr(kind)}" if kind else ""
        if message is not None:
            attrs += f" message={quoteattr(message)}"
        cases += (f"<testcase classname={quoteattr(classname)} name={quoteattr(name)}>"
                  f"<skipped {attrs}>{escape(text)}</skipped></testcase>")
    count = len(skips) if declared is None else declared
    return (f'<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest" errors="0" '
            f'failures="0" skipped="{count}" tests="{passed + len(skips)}">{cases}</testsuite></testsuites>'
            ).encode("utf-8")


def _statuses(policy=POLICY, **overrides):
    """``provider -> {status, detail}`` as availability_statuses derives it; UNAVAILABLE by default."""
    document = fx.availability_document(
        "Python 3.12.9", policy,
        status=lambda pid: overrides.get(pid, sa.UNAVAILABLE),
        detail=lambda pid: {"other": "ModuleNotFoundError: No module named 'other'"}.get(pid))
    statuses, problems = sa.availability_statuses(document, policy)
    assert problems == []
    return statuses


@pytest.fixture(scope="module")
def repo_template(tmp_path_factory):
    """``repo`` and the evidence ``evidence_repo`` adds, built once per module; tests receive private copies."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(core_certificate, "SCOPE", fx.SCOPE)
        base = tmp_path_factory.mktemp("skip-admission")
        root = _build_repo(base / "repo")
        head = fx.git(root, "rev-parse", "HEAD")
        fx.write_evidence(root, head, base / "evidence", skip_policy=POLICY)
    return base


@pytest.fixture
def repo(repo_template, tmp_path, monkeypatch):
    """A synthetic committed repository with a provider test module, a core test and the harnesses."""
    monkeypatch.setattr(core_certificate, "SCOPE", fx.SCOPE)
    return fx.clone_tree(repo_template / "repo", tmp_path / "repo")


def _build_repo(root):
    fx.make_repo(root)
    fx.write(root, FAKE_TEST, (
        "import pytest\n"
        "pytestmark = pytest.mark.skipif(True, reason=\"Fake unavailable\")\n"
        "def test_runs_fake():\n    pass\n"
        "def test_needs_other():\n    pass\n"))
    fx.write(root, CORE_TEST, "def test_only_on_the_exact_freeze():\n    pass\n"
                              "def test_core_invariant():\n    pass\n")
    # the synthetic harnesses' kill suites, as real files: protection is by existing test file
    for guard in (*fx.FORMAL_TARGETS, *fx.TRUST_TESTS, "tests/test_v4.py"):
        fx.write(root, guard, "def test_guard():\n    pass\n")
    fx.commit(root, "provider and core tests")
    return root


def _protected(root):
    return sa.protected_tests(root, trust_script=TRUST_SCRIPT)


def _admit(root, *skips, statuses=None, suite="junit_fast", policy=POLICY, **kw):
    return sa.admit_suite(_junit(*skips, **kw), suite=suite, statuses=statuses or _statuses(policy),
                          protected=_protected(root), policy=policy)


def _only(result):
    assert len(result["rows"]) == 1, result["rows"]
    return result["rows"][0]


# --- 1 ------------------------------------------------------------------------------------------
def test_an_approved_provider_that_is_unavailable_admits_its_skip(repo):
    result = _admit(repo, _skip(FAKE_TEST, "test_runs_fake", "Fake unavailable"))
    row = _only(result)
    assert row["admitted"] is True and result["unexpected"] == 0
    assert row["classification"] == sa.OPTIONAL_PROVIDER_UNAVAILABLE and row["rule_id"] == "fake"
    assert row["providers"] == {"fake": sa.UNAVAILABLE}
    assert row["nodeid"] == f"{FAKE_TEST}::test_runs_fake" and row["location"] == f"{FAKE_TEST}:12"


def test_a_reason_rendered_from_the_probe_admits_only_with_the_probes_own_words(repo):
    reason = "Other: ModuleNotFoundError: No module named 'other'"
    assert _only(_admit(repo, _skip(FAKE_TEST, "test_needs_other", reason)))["admitted"] is True
    worded = _only(_admit(repo, _skip(FAKE_TEST, "test_needs_other", "Other: not installed")))
    assert worded["admitted"] is False and "declared reason" in worded["refused_because"]


# --- 2 ------------------------------------------------------------------------------------------
def test_an_available_provider_cannot_be_claimed_unavailable(repo):
    row = _only(_admit(repo, _skip(FAKE_TEST, "test_runs_fake", "Fake unavailable"),
                       statuses=_statuses(fake=sa.AVAILABLE)))
    assert row["admitted"] is False and "AVAILABLE" in row["refused_because"]


# --- 3 ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("reason", [
    "Fake crashed: RuntimeError: solver diverged",   # an unrelated exception turned into a skip
    "Fake unavailable ",                              # near miss
    "Other: ModuleNotFoundError: No module named 'other'",  # the right words of another rule
])
def test_the_right_provider_with_the_wrong_reason_is_refused(repo, reason):
    row = _only(_admit(repo, _skip(FAKE_TEST, "test_runs_fake", reason)))
    assert row["admitted"] is False and row["classification"] == sa.UNEXPECTED_SKIP


# --- 4 ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("path, test", [
    (CORE_TEST, "test_core_invariant"),                       # an unrelated test borrowing the words
    ("providers/fake/tests/test_fake_provider_extra.py", "test_runs_fake"),   # a sibling file
    ("providers/fake/test_fake_provider.py", "test_runs_fake"),               # a moved module
])
def test_the_right_reason_outside_the_approved_scope_is_refused(repo, path, test):
    row = _only(_admit(repo, _skip(path, test, "Fake unavailable")))
    assert row["admitted"] is False and "no committed rule" in row["refused_because"]


def test_a_test_scoped_rule_does_not_cover_its_neighbours(repo):
    row = _only(_admit(repo, _skip(FAKE_TEST, "test_runs_fake", "Other: ModuleNotFoundError: No module named 'other'")))
    assert row["admitted"] is False


# --- 5 ------------------------------------------------------------------------------------------
def test_an_unknown_provider_is_refused_by_the_policy_and_by_admission(repo):
    ghost = sa.SkipPolicy(POLICY.providers, (
        sa.SkipRule("ghost", FAKE_TEST, "Fake unavailable", sa.OPTIONAL_PROVIDER_UNAVAILABLE, ("ghost",)),))
    assert any("unknown provider 'ghost'" in p for p in sa.policy_problems(ghost))
    row = _only(sa.admit_suite(_junit(_skip(FAKE_TEST, "test_runs_fake", "Fake unavailable")), suite="junit_fast",
                               statuses=_statuses(), protected=_protected(repo), policy=ghost))
    assert row["admitted"] is False


# --- 6 ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("skip, fragment", [
    (_skip(FAKE_TEST, "test_runs_fake", "Fake unavailable", kind="pytest.xfail"), "not pytest.skip"),
    (_skip(FAKE_TEST, "test_runs_fake", "Fake unavailable", kind=None), "not pytest.skip"),
    (("providers.fake.tests.test_fake_provider", "test_runs_fake", "pytest.skip", None, "x:1: Fake unavailable"),
     "no classname, name or reason"),
    (("providers.fake.tests.test_fake_provider", "test_runs_fake", "pytest.skip", "Fake unavailable", ""),
     "location text"),
    (_skip(FAKE_TEST, "test_runs_fake", "Fake unavailable", located=ABS + "tests/conftest.py"),
     "not raised in the test's own module"),
    (("", "test_runs_fake", "pytest.skip", "Fake unavailable", f"{ABS}{FAKE_TEST}:3: Fake unavailable"),
     "no classname"),
])
def test_malformed_skip_metadata_is_refused(repo, skip, fragment):
    row = _only(_admit(repo, skip))
    assert row["admitted"] is False and fragment in row["refused_because"]


def test_a_declared_skip_count_without_skipped_testcases_is_a_report_problem(repo):
    result = _admit(repo, _skip(FAKE_TEST, "test_runs_fake", "Fake unavailable"), declared=5)
    assert result["report_problems"] and "declares 5 skipped but carries 1" in result["report_problems"][0]


# --- 7 ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("nodeid", [
    "tests/test_formal_guard.py::test_guard",            # a Formal TARGET
    "tests/test_trust_guard.py::test_guard",             # a trust-mutation test
    "tests/test_v4.py::test_guard",                      # a V4 target test
    CERTIFICATE_SELF_CHECKS[0],                          # a deferred certificate self-check
    sa.DEPENDENCY_GUARD,
])
def test_a_skipped_hardened_core_trust_test_is_never_admitted(repo, nodeid):
    path, _, test = nodeid.partition("::")
    reason = "Fake unavailable"
    rule = sa.SkipRule("trap", path, reason, sa.OPTIONAL_PROVIDER_UNAVAILABLE, ("fake",), tests=(test,))
    trap = sa.SkipPolicy(POLICY.providers, (*POLICY.rules, rule))
    row = _only(sa.admit_suite(_junit(_skip(path, test, reason)), suite="junit_fast",
                               statuses=_statuses(trap), protected=_protected(repo), policy=trap))
    assert row["admitted"] is False and "hardened-core trust test" in row["refused_because"]


def test_the_real_policy_names_no_hardened_core_trust_test():
    files, nodeids = sa.protected_tests(REPO, trust_script=TRUST_SCRIPT)
    assert len(files) >= 48 and set(CERTIFICATE_SELF_CHECKS) <= nodeids and sa.DEPENDENCY_GUARD in nodeids
    for rule in sa.RULES:
        assert rule.path not in files, rule.rule_id
        assert not any(f"{rule.path}::{t}" in nodeids for t in rule.tests), rule.rule_id


def test_without_protected_tests_no_skip_is_admitted(repo):
    row = _only(sa.admit_suite(_junit(_skip(FAKE_TEST, "test_runs_fake", "Fake unavailable")), suite="junit_fast",
                               statuses=_statuses(), protected=None, policy=POLICY))
    assert row["admitted"] is False


# --- 8 ------------------------------------------------------------------------------------------
def _registry_row(available, refused, detail):
    row = {"kind": "registry", "target": "fake", "available": available, "found_but_refused": refused,
           "detail": detail, "version": ""}
    return dict(row, status=sa.facet_status(row))


@pytest.mark.parametrize("facets", [
    [fx.facet_observation(sa.Facet("registry", "fake"), sa.UNKNOWN)],          # present but refused
    # present but broken in ways ProviderStatus.found_but_refused does not recognise (review finding 1)
    [_registry_row(False, False, "TimeoutExpired: Command '['ccx', '-v']' timed out after 30 seconds")],
    [_registry_row(False, False, "no installed distribution metadata among ('fake',)")],
    [_registry_row(False, False, "declared dependency distribution 'numpy' is not installed")],
    [_registry_row(False, False, "OSError: [Errno 13] Permission denied: 'ccx'")],
    [{"kind": "registry", "target": "fake", "status": "MAYBE", "detail": "?"}],
    [],
])
def test_an_unknown_provider_status_never_admits(repo, facets):
    document = fx.availability_document("Python 3.12.9", POLICY)
    document["providers"]["fake"]["facets"] = facets
    document["providers"]["fake"]["status"] = sa.aggregate(facets)
    document["providers"]["fake"]["detail"] = facets[0]["detail"] if facets else ""
    statuses, _ = sa.availability_statuses(document, POLICY)
    assert statuses["fake"]["status"] == sa.UNKNOWN
    row = _only(_admit(repo, _skip(FAKE_TEST, "test_runs_fake", "Fake unavailable"), statuses=statuses))
    assert row["admitted"] is False


@pytest.mark.parametrize("detail, expected", [
    ("python module 'pybamm' is not installed", sa.UNAVAILABLE),
    ("executable 'ccx' not found", sa.UNAVAILABLE),
    ("OpenFOAM icoFoam not found under the provider prefix", sa.UNAVAILABLE),
    ("python module 'pybamm' is not installed (but a stub is on sys.path)", sa.UNKNOWN),
    ("could not establish the version of /usr/bin/ccx", sa.UNKNOWN),
    ("ValueError: bad version string", sa.UNKNOWN),
])
def test_only_an_exact_registry_absence_reason_means_unavailable(detail, expected):
    assert sa.facet_status(_registry_row(False, False, detail)) == expected
    assert sa.facet_status(_registry_row(True, True, "1.0")) == sa.UNKNOWN


def test_every_registry_provider_is_corroborated_by_an_independent_facet():
    for provider in sa.PROVIDERS:
        kinds = [facet.kind for facet in provider.facets]
        if "registry" in kinds and provider.provider_id != "openfoam":
            assert any(kind in ("module_spec", "executable") for kind in kinds), provider.provider_id


def test_facets_that_disagree_aggregate_to_unknown():
    absent = fx.facet_observation(sa.Facet("module_spec", "x"), sa.UNAVAILABLE)
    present = fx.facet_observation(sa.Facet("executable", "x"), sa.AVAILABLE)
    assert sa.aggregate([absent, present]) == sa.UNKNOWN
    assert sa.aggregate([absent, absent]) == sa.UNAVAILABLE
    assert sa.aggregate([dict(absent, status=sa.AVAILABLE), present]) == sa.UNKNOWN   # status re-derived
    assert sa.aggregate([]) == sa.UNKNOWN


def test_a_probe_that_raises_is_unknown_not_unavailable():
    row = sa._facet(sa.Facet("callable", "tools.certification.skip_admission:no_such_probe"), registry=None)
    assert row["status"] == sa.UNKNOWN and "raised" in row["detail"]
    row = sa._facet(sa.Facet("registry", "fake"), registry=RuntimeError("registry import failed"))
    assert row["status"] == sa.UNKNOWN


@pytest.mark.parametrize("tamper, fragment", [
    (lambda d: d["providers"]["fake"].update(status=sa.UNAVAILABLE), "facets say AVAILABLE"),
    (lambda d: d["providers"]["fake"]["facets"][0].update(status=sa.UNAVAILABLE), "disagrees with its observation"),
    (lambda d: d["providers"]["fake"].update(detail="something else"), "detail"),
    (lambda d: d["providers"].pop("other"), "exactly the policy's providers"),
    (lambda d: d.update(policy_sha256="0" * 64), "different skip policy"),
    (lambda d: d["providers"]["fake"]["facets"][0].update(kind="module_spec"), "facets do not match"),
    (lambda d: d.update(schema="forge.provider_availability/0"), "wrong schema"),
])
def test_an_inconsistently_edited_availability_record_is_not_believed(tamper, fragment):
    document = fx.availability_document("Python 3.12.9", POLICY, status=lambda pid: sa.AVAILABLE)
    tamper(document)
    statuses, problems = sa.availability_statuses(document, POLICY)
    assert any(fragment in p for p in problems), problems
    assert statuses["fake"]["status"] == sa.UNKNOWN


# --- 9 ------------------------------------------------------------------------------------------
@pytest.fixture
def evidence_repo(repo, repo_template, tmp_path):
    head = fx.git(repo, "rev-parse", "HEAD")
    evidence = fx.clone_tree(repo_template / "evidence", tmp_path / "evidence")
    return repo, head, evidence


def _put_junit(evidence, head, gate, suite, blob):
    prefix, files = EVIDENCE[gate]
    (evidence / f"{prefix}-{head}" / files[suite]).write_bytes(blob)


def _build(root, head, evidence):
    return build_assurance(root, source_commit=head, evidence_dir=evidence,
                           run=RunContext(executed_commit=head, **fx.RUN), policy=fx.POLICY, skip_policy=POLICY)


def _with_skips(evidence, head, *skips, gates=("fast311", "fast312")):
    for gate in gates:
        _put_junit(evidence, head, gate, "junit_fast", _junit(*skips))


def test_one_unexpected_skip_beside_an_accepted_one_refuses_the_whole_record(evidence_repo):
    root, head, evidence = evidence_repo
    _with_skips(evidence, head, _skip(FAKE_TEST, "test_runs_fake", "Fake unavailable"),
                _skip(CORE_TEST, "test_core_invariant", "flaky on this host"))
    with pytest.raises(AssuranceError) as caught:
        _build(root, head, evidence)
    unexpected = [p for p in caught.value.problems if "UNEXPECTED_SKIP" in p]
    assert len(unexpected) == 2 and all(CORE_TEST in p for p in unexpected)   # once per FAST gate
    assert caught.value.details["unexpected_skip_count"] == 2
    assert {row["nodeid"] for row in caught.value.details["unexpected_skips"]} == {f"{CORE_TEST}::test_core_invariant"}


def test_a_skip_in_a_suite_no_rule_allows_is_refused(evidence_repo):
    root, head, evidence = evidence_repo
    _put_junit(evidence, head, "campaign312", "junit_campaign",
               _junit(_skip(FAKE_TEST, "test_runs_fake", "Fake unavailable")))
    with pytest.raises(AssuranceError) as caught:
        _build(root, head, evidence)
    assert any("campaign312: junit_campaign: UNEXPECTED_SKIP" in p for p in caught.value.problems)


def test_availability_probed_under_another_interpreter_admits_nothing(evidence_repo):
    root, head, evidence = evidence_repo
    _with_skips(evidence, head, _skip(FAKE_TEST, "test_runs_fake", "Fake unavailable"), gates=("fast311",))
    prefix, files = EVIDENCE["fast311"]
    (evidence / f"{prefix}-{head}" / files["provider_availability"]).write_bytes(
        json.dumps(fx.availability_document("Python 3.12.9", POLICY)).encode())
    with pytest.raises(AssuranceError) as caught:
        _build(root, head, evidence)
    assert any("probed under 'Python 3.12.9'" in p for p in caught.value.problems)
    assert any("UNEXPECTED_SKIP" in p for p in caught.value.problems)


def test_missing_availability_evidence_is_refused(evidence_repo):
    root, head, evidence = evidence_repo
    prefix, files = EVIDENCE["scientific312"]
    (evidence / f"{prefix}-{head}" / files["provider_availability"]).unlink()
    with pytest.raises(AssuranceError) as caught:
        _build(root, head, evidence)
    assert any("scientific312: missing evidence" in p for p in caught.value.problems)


# --- 10 -----------------------------------------------------------------------------------------
def test_the_same_skip_on_python_3_11_and_3_12_is_admitted_identically(evidence_repo):
    root, head, evidence = evidence_repo
    _with_skips(evidence, head, _skip(FAKE_TEST, "test_runs_fake", "Fake unavailable"),
                _skip(CORE_TEST, "test_only_on_the_exact_freeze", "this tree is a descendant"))
    gates = _build(root, head, evidence)["skip_admission"]["gates"]
    left, right = gates["fast311"]["suites"]["junit_fast"], gates["fast312"]["suites"]["junit_fast"]
    assert left["inventory_sha256"] == right["inventory_sha256"]
    strip = lambda rows: [{k: v for k, v in r.items() if k not in ("gate", "python")} for r in rows]
    assert strip(left["accepted_skips"]) == strip(right["accepted_skips"])
    assert {r["python"] for r in left["accepted_skips"]} == {"Python 3.11.9"}
    assert {r["python"] for r in right["accepted_skips"]} == {"Python 3.12.9"}


# --- 11 -----------------------------------------------------------------------------------------
def test_the_admission_record_survives_serialization_with_a_stable_identity(evidence_repo):
    root, head, evidence = evidence_repo
    _with_skips(evidence, head, _skip(FAKE_TEST, "test_runs_fake", "Fake unavailable"))
    record = _build(root, head, evidence)
    reloaded = json.loads(json.dumps(record, sort_keys=True))
    assert reloaded == record
    assert assurance_problems(root, reloaded, source_commit=head, policy=fx.POLICY, skip_policy=POLICY) == []
    rows = reloaded["skip_admission"]["gates"]["fast311"]["suites"]["junit_fast"]["accepted_skips"]
    assert sa.inventory_digest(rows) == record["skip_admission"]["gates"]["fast311"]["suites"]["junit_fast"]["inventory_sha256"]
    assert sa.inventory_digest(list(reversed(rows + rows))) != sa.inventory_digest(rows)
    section = record["skip_admission"]
    assert section["claim"] == sa.CLAIM_WITH_PROVIDERS and section["unavailable_optional_providers"] == ["fake"]
    assert "ALL PROVIDERS" not in json.dumps(section).upper()
    assert section["totals"] == {"skipped": 2, "accepted": 2, "unexpected": 0}


# --- 12 -----------------------------------------------------------------------------------------
def _altered(record, change):
    altered = copy.deepcopy(record)
    change(altered)
    return altered


def _fast_rows(record):
    return record["skip_admission"]["gates"]["fast311"]["suites"]["junit_fast"]["accepted_skips"]


@pytest.mark.parametrize("change, fragment", [
    (lambda r: _fast_rows(r)[0].update(reason="Fake crashed"), "not re-admitted"),
    (lambda r: _fast_rows(r)[0].update(nodeid=f"{CORE_TEST}::test_core_invariant"), "not re-admitted"),
    (lambda r: _fast_rows(r).append(dict(_fast_rows(r)[0], nodeid=f"{FAKE_TEST}::test_new")), "skipped/accepted"),
    (lambda r: _fast_rows(r).clear(), "skipped/accepted"),
    (lambda r: r["skip_admission"]["gates"]["fast311"]["providers"]["fake"].update(status=sa.AVAILABLE),
     "recorded 'AVAILABLE'"),
    (lambda r: r["skip_admission"].update(policy_sha256="0" * 64), "different skip policy"),
    (lambda r: r["skip_admission"].update(claim=sa.CLAIM_NO_SKIPS), "claim"),
    (lambda r: r["skip_admission"]["gates"]["fast311"]["suites"]["junit_fast"].update(inventory_sha256="0" * 64),
     "inventory digest"),
    (lambda r: r["skip_admission"]["gates"]["fast311"]["suites"]["junit_fast"].update(unexpected=1),
     "skipped/accepted/unexpected"),
    (lambda r: _fast_rows(r)[0].update(python="Python 3.12.9"), "not bound to this gate"),
    (lambda r: r["skip_admission"]["gates"]["fast311"].update(python="Python 3.11.0"), "is not the environment's"),
    (lambda r: r.pop("skip_admission"), "absent"),
])
def test_an_altered_admission_record_does_not_revalidate(evidence_repo, change, fragment):
    root, head, evidence = evidence_repo
    _with_skips(evidence, head, _skip(FAKE_TEST, "test_runs_fake", "Fake unavailable"))
    record = _build(root, head, evidence)
    problems = assurance_problems(root, _altered(record, change), source_commit=head,
                                  policy=fx.POLICY, skip_policy=POLICY)
    assert any(fragment in p for p in problems), problems


def test_evidence_altered_after_generation_no_longer_yields_the_stored_admission(evidence_repo):
    root, head, evidence = evidence_repo
    _with_skips(evidence, head, _skip(FAKE_TEST, "test_runs_fake", "Fake unavailable"))
    record = _build(root, head, evidence)
    # what local_assurance verify re-derives, before and after one JUnit report changes
    derived, problems = skip_admission_section(root, _Evidence(evidence, head), POLICY)
    assert not problems
    for block in derived["gates"].values():
        for suite in block["suites"].values():
            suite.pop("unexpected_skips")
    assert derived == record["skip_admission"]
    _put_junit(evidence, head, "fast312", "junit_fast",
               _junit(_skip(FAKE_TEST, "test_runs_fake", "Fake unavailable"),
                      _skip(FAKE_TEST, "test_needs_other", "Other: ModuleNotFoundError: No module named 'other'")))
    rederived, _ = skip_admission_section(root, _Evidence(evidence, head), POLICY)
    for block in rederived["gates"].values():
        for suite in block["suites"].values():
            suite.pop("unexpected_skips")
    assert rederived != record["skip_admission"]


def test_a_legacy_counted_skip_record_keeps_its_old_meaning(evidence_repo):
    root, head, evidence = evidence_repo
    record = _build(root, head, evidence)
    legacy = _altered(record, lambda r: r.update(schema="forge.core_hardening_assurance/6"))
    legacy.pop("skip_admission")
    assert assurance_problems(root, legacy, source_commit=head, policy=fx.POLICY) == []
    legacy["functional"]["fast_python_3_11"]["suites"]["fast"]["skipped"] = 20
    assert any("above the declared ceiling of 19" in p
               for p in assurance_problems(root, legacy, source_commit=head, policy=fx.POLICY))


# --- 13 -----------------------------------------------------------------------------------------
def test_zero_skips_is_a_valid_record_that_claims_nothing_was_skipped(evidence_repo):
    root, head, evidence = evidence_repo
    record = _build(root, head, evidence)
    section = record["skip_admission"]
    assert section["totals"] == {"skipped": 0, "accepted": 0, "unexpected": 0}
    assert section["claim"] == sa.CLAIM_NO_SKIPS and section["unavailable_optional_providers"] == []
    assert record["functional"]["fast_python_3_11"]["suites"]["fast"]["skips"]["unexpected"] == 0
    assert assurance_problems(root, record, source_commit=head, policy=fx.POLICY, skip_policy=POLICY) == []


# --- 14 -----------------------------------------------------------------------------------------
def _measured_report():
    measured = json.loads(MEASURED.read_bytes())
    skips = [(row["classname"], row["name"], row["type"], row["message"],
              f"/home/runner/checkout/{row['location']}: {row['message']}") for row in measured["skips"]]
    statuses_by_pid = measured["provider_statuses"]
    # Providers declared AFTER the d5d886f9 measurement (Big Rocks: chrono, openvsp, openradioss) have no measured
    # status. They are UNKNOWN -- which never admits a skip -- and the historical file is not rewritten.
    later = {"status": sa.UNKNOWN, "detail": "provider declared after the d5d886f9 measurement"}
    document = fx.availability_document(
        "Python 3.11.13", sa.DEFAULT_POLICY,
        status=lambda pid: statuses_by_pid.get(pid, later)["status"], detail=lambda pid: statuses_by_pid.get(pid, later)["detail"])
    statuses, problems = sa.availability_statuses(document)
    assert problems == []
    return _junit(*skips, passed=9133), statuses


BLIND_GUARD = "tests/test_blind_challenge_guards.py::test_importing_the_truth_layer_loads_no_runtime_module"


def test_the_measured_d5d886f9_population_is_explained_skip_by_skip():
    """141 of the 142 skips d5d886f9 measured are admitted for their stated reason. The 142nd, the
    blind-challenge import guard, skipped only because its pytest worker had already imported the
    runtime; Pass 13 made it run in a fresh interpreter, so a skip of it is now unexpected."""
    blob, statuses = _measured_report()
    protected = sa.protected_tests(REPO, trust_script=TRUST_SCRIPT)
    result = sa.admit_suite(blob, suite="junit_fast", statuses=statuses, protected=protected)
    refused = [(r["nodeid"], r["refused_because"]) for r in result["rows"] if not r["admitted"]]
    assert refused == [(BLIND_GUARD, "no committed rule covers this node id")]
    assert result["report_problems"] == []
    assert result["skipped"] == 142 and result["accepted"] == 141 and result["unexpected"] == 1
    admitted = [r for r in result["rows"] if r["admitted"]]
    summary = sa.summarize(admitted)["by_classification"]
    assert summary == {sa.DECLARED_CONDITIONAL_SKIP: 3, sa.OPTIONAL_EXTRA_UNAVAILABLE: 5,
                       sa.OPTIONAL_PROVIDER_UNAVAILABLE: 133}
    assert sa.claim(admitted) == sa.CLAIM_WITH_PROVIDERS_AND_CONDITIONAL
    scientific = sa.admit_suite(blob, suite="junit_scientific", statuses=statuses, protected=protected)
    assert scientific["accepted"] == 141 and scientific["unexpected"] == 1


def test_the_claim_names_every_class_it_admitted():
    provider = {"classification": sa.OPTIONAL_PROVIDER_UNAVAILABLE}
    conditional = {"classification": sa.DECLARED_CONDITIONAL_SKIP}
    assert sa.claim([provider, conditional]) == sa.CLAIM_WITH_PROVIDERS_AND_CONDITIONAL
    assert sa.claim([provider]) == sa.CLAIM_WITH_PROVIDERS == (
        "CORE ASSURANCE PASSED WITH DECLARED OPTIONAL PROVIDERS UNAVAILABLE")
    assert sa.claim([conditional]) == sa.CLAIM_WITH_CONDITIONAL
    assert sa.claim([]) == sa.CLAIM_NO_SKIPS
    assert all("ALL PROVIDERS" not in text for text in (
        sa.CLAIM_WITH_PROVIDERS, sa.CLAIM_WITH_PROVIDERS_AND_CONDITIONAL, sa.CLAIM_WITH_CONDITIONAL, sa.CLAIM_NO_SKIPS))


def test_a_protected_entry_that_is_not_an_existing_test_file_protects_nothing_and_is_refused(repo):
    harness = repo / "tests" / "mutation_guards.py"
    harness.write_bytes(harness.read_bytes().replace(b"TARGETS = ('tests/test_formal_guard.py',)",
                                                     b"TARGETS = ('tests/',)"))
    with pytest.raises(sa.SkipPolicyError, match="not existing test files"):
        sa.protected_tests(repo, trust_script=TRUST_SCRIPT)
    row = _only(sa.admit_suite(_junit(_skip(FAKE_TEST, "test_runs_fake", "Fake unavailable")), suite="junit_fast",
                               statuses=_statuses(), protected=None, policy=POLICY))
    assert row["admitted"] is False


def test_the_measured_population_refuses_once_a_provider_becomes_available():
    blob, statuses = _measured_report()
    statuses = dict(statuses, pybamm={"status": sa.AVAILABLE, "detail": "24.1"})
    result = sa.admit_suite(blob, suite="junit_fast", statuses=statuses,
                            protected=sa.protected_tests(REPO, trust_script=TRUST_SCRIPT))
    refused = {r["nodeid"].split("::")[0] for r in result["rows"] if not r["admitted"]}
    # only the modules that need PyBaMM alone; a module that also needs an absent TESPy still skips legitimately
    assert refused == {"providers/pybamm/tests/test_pybamm_coupling_options.py",
                       "providers/pybamm/tests/test_pybamm_multiscale.py",
                       "providers/pybamm/tests/test_pybamm_provider.py",
                       BLIND_GUARD.split("::")[0]}


def test_pybamm_checkpoint_skip_is_admitted_only_for_the_exact_unavailable_provider_test():
    path = "providers/pybamm/tests/test_pybamm_checkpoint_identity.py"
    test = "test_own_checkpoint_round_trip_reproduces_the_next_window"
    reason = "PyBaMM is required (executed-provider test)"
    availability = fx.availability_document("Python 3.12.9", sa.DEFAULT_POLICY)
    statuses, problems = sa.availability_statuses(availability, sa.DEFAULT_POLICY)
    assert problems == []
    protected = sa.protected_tests(REPO, trust_script=TRUST_SCRIPT)

    admitted = _only(sa.admit_suite(_junit(_skip(path, test, reason)), suite="junit_fast",
                                    statuses=statuses, protected=protected, policy=sa.DEFAULT_POLICY))
    assert admitted["admitted"] is True
    assert admitted["classification"] == sa.OPTIONAL_PROVIDER_UNAVAILABLE
    assert admitted["rule_id"] == "pybamm-checkpoint-identity"

    unlisted = _only(sa.admit_suite(_junit(_skip(path, "test_unlisted_future_case", reason)),
                                    suite="junit_fast", statuses=statuses, protected=protected,
                                    policy=sa.DEFAULT_POLICY))
    assert unlisted["admitted"] is False


def test_the_committed_policy_is_narrow_and_true_of_this_tree():
    assert sa.policy_problems(sa.DEFAULT_POLICY, REPO, trust_script=TRUST_SCRIPT) == []
    assert sa.INSTALLED_EXTRAS == ("dev", "mcp", "oracles")
    from tools.certification.hardening_assurance import INSTALL_COMMAND
    assert INSTALL_COMMAND.endswith('".[dev,mcp,oracles]"')


@pytest.mark.parametrize("rule, fragment", [
    (sa.SkipRule("w", "providers/**/test_*.py", "Fake unavailable", sa.OPTIONAL_PROVIDER_UNAVAILABLE, ("fake",)),
     "not one exact test file"),
    (sa.SkipRule("w", "providers/fake/tests/", "Fake unavailable", sa.OPTIONAL_PROVIDER_UNAVAILABLE, ("fake",)),
     "not one exact test file"),
    (sa.SkipRule("c", CORE_TEST, "descendant", sa.DECLARED_CONDITIONAL_SKIP, why="x"), "never a module"),
    (sa.SkipRule("c", CORE_TEST, "descendant", sa.DECLARED_CONDITIONAL_SKIP, tests=("t",)), "state why"),
    (sa.SkipRule("p", FAKE_TEST, "Fake unavailable", sa.OPTIONAL_PROVIDER_UNAVAILABLE), "name its provider"),
    (sa.SkipRule("p", FAKE_TEST, "Fake: {other}", sa.OPTIONAL_PROVIDER_UNAVAILABLE, ("fake",)),
     "does not declare"),
    (sa.SkipRule("p", FAKE_TEST, "Fake unavailable", sa.OPTIONAL_PROVIDER_UNAVAILABLE, ("fake",),
                 suites=("junit_campaign",)), "suites"),
    (sa.SkipRule("fake", FAKE_TEST, "Fake unavailable", sa.OPTIONAL_PROVIDER_UNAVAILABLE, ("fake",)), "overlap"),
])
def test_a_broad_or_unbound_rule_is_refused(rule, fragment):
    policy = sa.SkipPolicy(POLICY.providers, (*POLICY.rules, rule))
    assert any(fragment in p for p in sa.policy_problems(policy)), sa.policy_problems(policy)


def test_module_scope_must_be_the_modules_own_pytestmark(repo):
    assert sa.policy_problems(POLICY, repo, trust_script=TRUST_SCRIPT) == []
    borrowed = sa.SkipPolicy(POLICY.providers, (
        sa.SkipRule("core-module", CORE_TEST, "Fake unavailable", sa.OPTIONAL_PROVIDER_UNAVAILABLE, ("fake",)),))
    assert any("no top-level pytestmark" in p for p in sa.policy_problems(borrowed, repo, trust_script=TRUST_SCRIPT))
    protected = sa.SkipPolicy(POLICY.providers, (
        sa.SkipRule("guard", "tests/test_formal_guard.py", "Fake unavailable", sa.OPTIONAL_PROVIDER_UNAVAILABLE,
                    ("fake",), tests=("test_guard",)),))
    assert any("hardened-core trust tests" in p
               for p in sa.policy_problems(protected, repo, trust_script=TRUST_SCRIPT))


def test_an_installed_extra_can_never_be_unavailable():
    policy = sa.SkipPolicy((sa.OptionalProvider("mpmath", sa.OPTIONAL_EXTRA_UNAVAILABLE,
                                                (sa.Facet("module_spec", "mpmath"),), extra="oracles",
                                                module="mpmath"),), ())
    assert any("installed by assurance" in p for p in sa.policy_problems(policy))


def test_the_live_probe_covers_exactly_the_policy_and_rederives_cleanly():
    document = sa.probe(REPO)
    assert document["schema"] == sa.AVAILABILITY_SCHEMA and set(document["providers"]) == set(sa.DEFAULT_POLICY.provider_ids)
    statuses, problems = sa.availability_statuses(json.loads(json.dumps(document)))
    assert problems == []
    assert all(row["status"] in sa.STATUSES for row in statuses.values())


# --- 15 -----------------------------------------------------------------------------------------
def test_an_assurance_refusal_prints_refused_and_never_safe_to_push(monkeypatch, capsys, tmp_path):
    from tools.certification import local_assurance as la
    record = tmp_path / "local-assurance-failure.json"
    record.write_bytes(b'{"status": "REFUSED"}\n')

    def refuse(args):
        error = AssuranceError(["fast311: junit_fast: UNEXPECTED_SKIP tests/t.py::t: no committed rule"])
        error.failure_record = str(record)
        raise error
    monkeypatch.setattr(la, "run", refuse)
    assert la.main(["run"]) == 1
    err = capsys.readouterr().err
    assert "LOCAL_ASSURANCE: REFUSED" in err and "EXPECTED_ASSURANCE_REFUSAL" in err
    assert err.rstrip().endswith("SAFE_TO_PUSH: NO") and "SAFE_TO_PUSH: YES" not in err
    assert f"FAILURE_RECORD: {record}" in err and f"FAILURE_RECORD_SHA256: {la._sha256(record)}" in err
    assert "Traceback" not in err


def test_an_internal_error_is_distinguished_and_never_safe_to_push(monkeypatch, capsys):
    from tools.certification import local_assurance as la
    monkeypatch.setattr(la, "run", lambda args: {}["programmer error"])
    assert la.main(["run"]) == 2
    err = capsys.readouterr().err
    assert "LOCAL_ASSURANCE: INTERNAL_ERROR" in err and "UNEXPECTED_INTERNAL_ERROR" in err
    assert "Traceback" in err and "KeyError" in err
    assert err.rstrip().endswith("SAFE_TO_PUSH: NO") and "SAFE_TO_PUSH: YES" not in err
    assert "LOCAL_ASSURANCE: REFUSED" not in err


def test_a_skip_refusal_at_assurance_build_writes_its_record_and_no_certificate(tmp_path, monkeypatch, capsys):
    from tools.certification import local_assurance as la
    monkeypatch.setattr(la, "_require_linux", lambda: None)
    monkeypatch.setattr(la, "_assurance_lock", lambda root: nullcontext())
    monkeypatch.setattr(la.core_certificate, "repo_root", lambda _: tmp_path)
    monkeypatch.setattr(la, "_require_clean", lambda *a: None)
    monkeypatch.setattr(la, "_require_head", lambda *a: None)
    monkeypatch.setattr(la, "_git", lambda root, *a: "source")
    monkeypatch.setattr(la, "_repository_slug", lambda *a: "owner/repo")
    monkeypatch.setattr(la, "_resolve_python", lambda *a: "python")
    monkeypatch.setattr(la, "_version", lambda *a: None)
    monkeypatch.setattr(la.shutil, "which", lambda *a: "ngspice")
    monkeypatch.setattr(la, "_run_source_gates", lambda *a, **k: {"fast311": 1.0})
    monkeypatch.setattr(la, "_build_evidence_manifest", lambda *a, **k: (tmp_path / "m.json", "a" * 64, 3))

    def refuse(*args, **kwargs):
        raise AssuranceError(["fast311: junit_fast: UNEXPECTED_SKIP tests/t.py::t: no committed rule"],
                             details={"unexpected_skip_count": 1, "unexpected_skips": [{"nodeid": "tests/t.py::t"}]})
    monkeypatch.setattr(la, "build_assurance", refuse)
    monkeypatch.setattr(la.core_certificate, "build_certificate",
                        lambda *a, **k: pytest.fail("certificate generation after a skip refusal"))
    assert la.main(["run"]) == 1
    err = capsys.readouterr().err
    run_root = tmp_path / ".forge/assurance/source"
    failure = run_root / "local-assurance-failure.json"
    document = json.loads(failure.read_bytes())
    assert document["failed_gate"] == "assurance_build" and document["safe_to_push"] is False
    assert document["failure_context"]["assurance_build"]["details"]["unexpected_skip_count"] == 1
    assert not (run_root / "local-assurance-receipt.json").exists()
    assert "LOCAL_ASSURANCE: REFUSED" in err and f"FAILURE_RECORD: {failure}" in err
    assert err.rstrip().endswith("SAFE_TO_PUSH: NO")
