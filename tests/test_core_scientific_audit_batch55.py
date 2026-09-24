"""Core re-audit 2026-09-16, batch 55: the round's own guard evidence, inside the area that is verified.

Problems R-67 (findings 92 and 97), R-68 (finding 93) and R-66's population half (finding 91), improvement
I-30, under benchmarks/core_v4_false_confidence/BATCH55_THRESHOLD_PROTOCOL.json.

Fifty-four batches wrote 563 guard mutations and a log for each. The evidence is real and it sits where
nothing checks it: outside the certificate's scope, applied by runners nobody certifies, credited as a kill
by any non-zero exit code. This suite is the other side of that -- the population as DATA in the pinned
harness area, a runner whose kill names its own test, and a certificate that pins every module its certified
suites import.

Recorded as strict xfails in commit ccc72f94, each seen failing on its own assertion, before the fix.
"""

from __future__ import annotations

import importlib
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
if str(REPO / "tests") not in sys.path:  # the harness is a support module, not a package
    sys.path.insert(0, str(REPO / "tests"))

import mutation_guards as mg  # noqa: E402 - after the path is set, as the harness's own tests do


def _measured():
    """The population scan, from the suite that owns it, so both cannot disagree."""
    from test_mutation_population_v4 import applied

    return applied()


def _module(name: str):
    """Import ``name``, or FAIL saying what is missing rather than erroring on the import.

    A reproduction that dies on ImportError proves the module is absent and nothing about the rule, so
    the absence is turned into the assertion the rule is about.
    """
    try:
        return importlib.import_module(name)
    except ImportError as exc:
        pytest.fail(f"{name} does not exist, so the rule it carries is not stated anywhere: {exc}")


def _attribute(module, name: str):
    found = getattr(module, name, None)
    assert found is not None, (
        f"{module.__name__} has no {name!r}: the rule this test is about is not stated in the tree")
    return found


def _region(spec: str) -> tuple[str, int, int]:
    relative, _, scope = spec.partition("::")
    path = REPO / relative
    assert path.is_file(), f"{relative} does not exist"
    text = path.read_bytes().decode("utf-8").replace(mg.CRLF, mg.LF)
    if not scope:
        return text, 0, len(text)
    low, high = mg._scope_span(text, scope)
    return text, low, high


# ---------------------------------------------------------------------------
# R-67: the population, in the pinned area
# ---------------------------------------------------------------------------
def test_r67_the_rounds_guard_mutations_are_declared_inside_the_pinned_harness_area():
    """563 mutations of evidence, and the certificate measured none of their bytes."""
    population = _module("mutation_population_v4")
    policy = _module("tools.certification.mutation_population")
    entries = _attribute(population, "POPULATION_V4")
    assert len(entries) == policy.EXPECTED_V4_POPULATION, (
        f"the population declares {len(entries)} of the round's declared V4 mutation population")
    certificate = _module("tools.certification.core_certificate")
    harness = next(area for area in certificate.SCOPE if area.name == "harness")
    pinned = set(certificate.enumerate_area(REPO, harness))
    assert "tests/mutation_population_v4.py" in pinned, (
        "the round's guard evidence is outside the area the certificate pins, which is finding 92: a reader "
        f"has to trust 55 scripts under benchmarks/ that nothing verifies. Pinned: {len(pinned)} file(s)")


def test_r67_every_folded_mutation_still_matches_the_live_source_exactly_once():
    """The check that caught five silently dead mutations, applied to the folded 563.

    Delegated to `tests/test_mutation_population_v4.py`, which is where the rule LIVES from now on
    and which measures the population once for both suites. The reproduction stays here because this
    is the batch that had to state it.
    """
    stale, _inert, _fstring = _measured()
    assert stale == {}, (
        "these folded mutations no longer describe the source, so the guards behind them are "
        "unverified whatever their batch log printed:\n  "
        + "\n  ".join(f"{k}: {v}" for k, v in sorted(stale.items())))


def test_r67_every_folded_mutation_changes_executable_code():
    """A mutation whose only effect is prose reports a guard nobody tested."""
    _stale, inert, _fstring = _measured()
    population = _module("mutation_population_v4")
    expected_inert = (
        set(population.FSTRING_ONLY_ON_3_12)
        if sys.version_info < (3, 12)
        else set()
    )
    assert set(inert) == expected_inert, sorted(inert.items())


def test_r67_the_entries_that_moved_and_the_declared_survivors_each_carry_their_reason():
    """A stale entry is repointed with its reason, or it is a guard retired by nobody's decision."""
    population = _module("mutation_population_v4")
    not_mutated = _attribute(population, "NOT_MUTATED")
    fstring_only = _attribute(population, "FSTRING_ONLY_ON_3_12")
    repointed, survivors, unmutated = [], [], []
    for mid, _spec, _old, _new, _test, expect, note, _also, _source in _attribute(population, "POPULATION_V4"):
        if "[REPOINTED 2026-09-18:" in note:
            # The marker is dated and bracketed on purpose: a batch note may use the word in prose.
            repointed.append(mid)
            assert "; was " in note, f"{mid}: repointed without saying what it used to name"
        if expect == "SURVIVED":
            survivors.append(mid)
            assert note.strip(), f"{mid}: declared SURVIVED with no recorded reason"
        if expect == not_mutated:
            unmutated.append(mid)
            assert note.strip(), f"{mid}: declared NOT MUTATED with no recorded reason"
    # 27 now: 26 at batch 55 (amendments 1 and 3 of BATCH55_THRESHOLD_PROTOCOL.json), plus B1p,
    # which batch 56's formal round found SURVIVING because this round's own R-11 fix made a second
    # rule catch its case. Recorded in BATCH56_THRESHOLD_PROTOCOL.json rule 9. The two NOT MUTATED placeholders
    # carry an EMPTY `old`, which `str.count` finds everywhere, so the first measurement counted them
    # among the entries that no longer describe the tree. They are asserted separately below.
    assert len(repointed) == 27, (
        f"{len(repointed)} of the round's 27 moved entries are repointed; the rest are stale, dropped, or "
        f"silently rewritten: {sorted(repointed)}")
    assert len(unmutated) == 2, sorted(unmutated)
    assert sorted(fstring_only) == ["B31f", "B32e", "B34b", "B47e", "B48e"], sorted(fstring_only)
    assert survivors, "the round declared survivors with reasons and the population carries none"


# ---------------------------------------------------------------------------
# R-67: a kill is the named test failing
# ---------------------------------------------------------------------------
_NODEID = "tests/test_thing.py::test_the_guard_fires"

_JUNIT_NAMED_FAILURE = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="1" failures="1">
<testcase classname="tests.test_thing" name="test_the_guard_fires" file="tests/test_thing.py">
<failure message="assert False">assert False</failure></testcase>
</testsuite></testsuites>
"""

_JUNIT_OTHER_FAILURE = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="1" failures="1">
<testcase classname="tests.test_thing" name="test_something_else" file="tests/test_thing.py">
<failure message="assert False">assert False</failure></testcase>
</testsuite></testsuites>
"""

_JUNIT_COLLECTION_ERROR = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="1" errors="1">
<testcase classname="" name="tests/test_thing.py" file="tests/test_thing.py">
<error message="collection failure">ImportError: cannot import name 'gone'</error></testcase>
</testsuite></testsuites>
"""

_JUNIT_NAMED_ERROR = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="1" errors="1">
<testcase classname="tests.test_thing" name="test_the_guard_fires" file="tests/test_thing.py">
<error message="fixture failed">KeyError: 'store'</error></testcase>
</testsuite></testsuites>
"""

_JUNIT_PASSED = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="1" failures="0">
<testcase classname="tests.test_thing" name="test_the_guard_fires" file="tests/test_thing.py"/>
</testsuite></testsuites>
"""

_JUNIT_EMPTY = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="0" failures="0"></testsuite></testsuites>
"""


def test_r67_a_kill_requires_the_named_target_test_to_fail():
    """Finding 97: any non-zero exit was a kill, so an unrelated failure credited the guard."""
    runner = _module("tools.certification.mutation_v4_runner")
    verdict = _attribute(runner, "verdict_from_junit")
    assert verdict(_JUNIT_NAMED_FAILURE, _NODEID) == "KILLED"
    for label, xml in (("another test failed", _JUNIT_OTHER_FAILURE),
                       ("the named test raised outside its own body", _JUNIT_NAMED_ERROR),
                       ("the module did not import", _JUNIT_COLLECTION_ERROR),
                       ("nothing was collected", _JUNIT_EMPTY)):
        found = verdict(xml, _NODEID)
        assert found != "KILLED", (
            f"{label}: counted as a kill, so the mutation is credited to a guard the run says nothing about")
        assert found, f"{label}: the verdict says nothing about what happened"
    assert verdict(_JUNIT_PASSED, _NODEID) == "SURVIVED"


def test_r67_the_runner_refuses_to_mutate_the_repository_itself():
    """Finding 97's other half: the runners mutated the shared checkout in place."""
    runner = _module("tools.certification.mutation_v4_runner")
    refuse = _attribute(runner, "require_an_isolated_tree")
    with pytest.raises(runner.MutationRoundError, match="isolat"):
        refuse(REPO, REPO)
    refuse(REPO, REPO.parent / "forge_mutation_scratch" / "mut_B1a")


# ---------------------------------------------------------------------------
# R-68: the certificate pins what its suites import
# ---------------------------------------------------------------------------
def test_r68_every_module_the_certified_suites_import_is_pinned_by_the_certificate():
    """Finding 93: hybrid_synthetic.py is imported by ten certified targets and pinned by nothing."""
    certificate = _module("tools.certification.core_certificate")
    closure = _attribute(certificate, "harness_import_closure")(REPO)
    # Both classifications, as the rule itself reads them: the certification control plane pins the
    # population's own FAST-tier check, and a file the certificate measures under that heading is
    # measured whichever area names it.
    pinned = {
        relative
        for area in certificate.SCOPE if area.classification in ("HARNESS", "CERTIFICATION_CONTROL")
        for relative in certificate.enumerate_area(REPO, area)
    }
    missing = sorted(set(closure) - pinned)
    assert "tests/hybrid_uq/hybrid_synthetic.py" in closure, (
        "the closure does not even reach the helper the finding names, so it is not the closure")
    assert missing == [], (
        "the certificate's 'N/N killed' is a statement about these bytes and it does not measure them:\n  "
        + "\n  ".join(missing))


def test_r68_a_scope_whose_harness_area_misses_an_imported_helper_is_refused():
    """The derived check, not a longer list: the reason finding 93 happened is that the list was a list."""
    certificate = _module("tools.certification.core_certificate")
    harness = next(area for area in certificate.SCOPE if area.name == "harness")
    narrowed = [area for area in certificate.SCOPE if area.name != "harness"]
    narrowed.append(type(harness)(
        name="harness", classification="HARNESS",
        patterns=tuple(p for p in harness.patterns if "hybrid_synthetic" not in p),
        why=harness.why,
    ))
    problems = _attribute(certificate, "harness_pinning_problems")(REPO, tuple(narrowed))
    assert any("hybrid_synthetic" in problem for problem in problems), (
        f"a scope that pins a suite and not the module it imports is accepted: {problems}")


# ---------------------------------------------------------------------------
# R-66: the population half
# ---------------------------------------------------------------------------
def test_r66_the_v4_population_digests_are_re_derived_from_the_definitions():
    """Finding 91: a copied population sha passed every assurance check."""
    module = _module("tools.certification.mutation_population")
    population = _attribute(module, "v4_population")(REPO)
    assert population.count == module.EXPECTED_V4_POPULATION, population.count
    assert population.sha256 == module.sha256_lines(population.ids)
    assert population.definitions_sha256, "the population's bodies are not hashed, so the same ids with a different mutation are the same population"
    other = type(population)(ids=population.ids, definitions_sha256="")
    assert other.sha256 == population.sha256 and other.definitions_sha256 != population.definitions_sha256, (
        "the two digests are not independent, so one of them is decoration")


def test_r66_a_shard_transcript_is_read_for_the_verdict_it_names():
    """A shard's evidence is its transcript, re-derived; a tally is not evidence."""
    module = _module("tools.certification.mutation_population")
    problems = _attribute(module, "v4_log_problems")
    population = module.v4_population(REPO)
    selected = population.shard(0)
    good = "\n".join(
        [f"{mid} {test.split('::')[-1]} -> {expect} | 1 failed | code aaaa->bbbb"
         for mid, _s, _o, _n, test, expect, _note, _also, _src in module.v4_entries(REPO)
         if mid in set(selected)]
        + ["CONTROL (unmutated) GREEN | 1 passed"]) + "\n"
    assert problems(good, population, selected) == [], problems(good, population, selected)
    lying = good.replace(" -> KILLED", " -> NOT_A_TEST_FAILURE(exit 2)", 1)
    assert problems(lying, population, selected), "a verdict that is not the declared one is accepted"
    no_control = "\n".join(line for line in good.splitlines() if not line.startswith("CONTROL")) + "\n"
    assert problems(no_control, population, selected), "a round with no green control is accepted"

#: What pytest's default JUnit family actually writes: `classname` as the dotted module, and no
#: `file` attribute at all. The first runner matched on `file` only and read every real report as
#: NOT_COLLECTED while the tests failed -- the same shape of wrong answer as the audited rule, in the
#: safe direction, and caught by this case.
_JUNIT_AS_PYTEST_WRITES_IT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites name="pytest tests"><testsuite name="pytest" errors="0" failures="1" skipped="0" tests="1">
<testcase classname="tests.hybrid_uq.test_core_scientific_audit_batch1" name="test_core001_a_gross_misfit_is_refused" time="0.001">
<failure message="Failed: DID NOT RAISE">assert False</failure></testcase>
</testsuite></testsuites>
"""


_JUNIT_PARAMETRIZED = """<?xml version="1.0" encoding="utf-8"?>
<testsuites name="pytest tests"><testsuite name="pytest" errors="0" failures="1" skipped="0" tests="2">
<testcase classname="tests.test_thing" name="test_the_guard_fires[4.0-3]" time="0.001">
<failure message="assert False">assert False</failure></testcase>
<testcase classname="tests.test_thing" name="test_the_guard_fires[1.0-3]" time="0.001"/>
</testsuite></testsuites>
"""

_JUNIT_A_LONGER_NAME = """<?xml version="1.0" encoding="utf-8"?>
<testsuites name="pytest tests"><testsuite name="pytest" errors="0" failures="1" skipped="0" tests="1">
<testcase classname="tests.test_thing" name="test_the_guard_fires_on_a_subset" time="0.001">
<failure message="assert False">assert False</failure></testcase>
</testsuite></testsuites>
"""


def test_r67_a_parametrized_target_is_killed_by_the_case_its_guard_is_about():
    """Four entries name a parametrized test, and pytest reports each case as ``name[case]``.

    One failing case is the kill: the guard fired on the case its batch built the mutation for, and a
    parametrization that also covers cases the guard says nothing about is a property of the suite.
    Requiring every case would make a verdict depend on how many examples somebody added later. What
    is NOT allowed is a different test whose name merely extends the entry's.
    """
    runner = _module("tools.certification.mutation_v4_runner")
    named = "tests/test_thing.py::test_the_guard_fires"
    assert runner.verdict_from_junit(_JUNIT_PARAMETRIZED, named) == "KILLED"
    assert runner.verdict_from_junit(_JUNIT_PARAMETRIZED, named + "[1.0-3]") == "SURVIVED", (
        "an entry that names ONE case is answered by another case's failure")
    assert runner.verdict_from_junit(_JUNIT_A_LONGER_NAME, named) == "NOT_COLLECTED", (
        "a differently named test whose name extends the entry's carries the kill")


def test_r67_the_kill_rule_reads_the_report_pytest_actually_writes():
    """A rule that only works on a hand-written report is not the rule the round runs under."""
    runner = _module("tools.certification.mutation_v4_runner")
    nodeid = ("tests/hybrid_uq/test_core_scientific_audit_batch1.py"
              "::test_core001_a_gross_misfit_is_refused")
    assert runner.verdict_from_junit(_JUNIT_AS_PYTEST_WRITES_IT, nodeid) == "KILLED"
    other = "tests/hybrid_uq/test_core_scientific_audit_batch2.py::test_core001_a_gross_misfit_is_refused"
    assert runner.verdict_from_junit(_JUNIT_AS_PYTEST_WRITES_IT, other) == "NOT_COLLECTED", (
        "the same test name in another file counts as the kill, so the nodeid's file is decoration")
