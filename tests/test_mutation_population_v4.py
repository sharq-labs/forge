"""The V4 guard-mutation population's own guard: every folded mutation still bites (I-30, R-67).

`tests/mutation_population_v4.py` holds the 563 guard mutations the 2026-09-16 core re-audit's 55
batches wrote. Each was run once, in its own batch, against the tree as it stood that day -- and then
the tree moved. Twenty-five of them had already stopped describing the source when this round folded
them in, which is the same defect `tests/test_mutation_harness.py` exists for one level up: a
mutation that no longer applies is a guard verified by nobody, and its batch log still says KILLED.

So the cheap half runs here on every FAST invocation, exactly as it does for the pinned MUTATIONS:
every entry is applied to the live source IN MEMORY and must land exactly once inside the scope it
names, and must change executable code. No tree is copied, no suite is run, nothing is written. It
cannot tell whether an entry is KILLED -- only the formal round with
`tools/certification/mutation_v4_runner.py` can, and there a kill is the ONE test the entry names
failing -- but it is what turns "the population went stale" from a discovery into a test failure in
the same commit that moved the code.

The declarations are checked for the same reason: a duplicate id, an entry whose target test does not
exist, a repointed entry that does not say what it used to name, or a silent addition to the set that
only bites on Python 3.12 are all states a formal round must not be started in, and there is no
reason to wait hours to be told.
"""

from __future__ import annotations

import functools
import io
import hashlib
import pathlib
import sys
import tokenize

REPO = pathlib.Path(__file__).resolve().parent.parent
if str(REPO / "tests") not in sys.path:
    sys.path.insert(0, str(REPO / "tests"))

import mutation_guards as mg
import mutation_population_v4 as pop


def _region(spec: str) -> tuple[str, int, int]:
    """``(text, low, high)``: the file and the span this spec's mutation searches, as the harness reads it."""
    relative, _, scope = spec.partition("::")
    path = REPO / relative
    assert path.is_file(), f"{relative} does not exist"
    text = path.read_bytes().decode("utf-8").replace(mg.CRLF, mg.LF)
    if not scope:
        return text, 0, len(text)
    low, high = mg._scope_span(text, scope)
    return text, low, high


def _conservative_digest(text: str) -> str:
    """``_code_digest`` as the OLDEST supported Python computes it.

    Since PEP 701 (3.12) an f-string tokenizes into its parts, so a mutation that only rewrites what
    is interpolated inside one changes executable tokens here and NOTHING on 3.11. Five entries are
    exactly that -- a refusal message mutated into the text the audit found misleading -- and they are
    declared rather than dropped, because the test that kills each of them reads the message.
    """
    kept: list[str] = []
    depth = 0
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        name = tokenize.tok_name.get(token.type, "")
        if name == "FSTRING_START":
            depth += 1
            continue
        if name == "FSTRING_END":
            depth -= 1
            continue
        if depth:
            continue
        if token.type in (tokenize.COMMENT, tokenize.STRING, tokenize.NL,
                          tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT):
            continue
        kept.append(token.string)
    return hashlib.sha256("\x00".join(kept).encode("utf-8")).hexdigest()[:16]


@functools.lru_cache(maxsize=1)
def applied() -> tuple[dict[str, str], dict[str, str], tuple[str, ...]]:
    """``(stale, inert, changes code only on 3.12+)``, measured once for every caller.

    Cached because two suites ask -- this one and the batch that introduced the population -- and the
    scan reads 563 entries against the tree. One measurement, one answer, no chance of the two
    disagreeing.
    """
    stale: dict[str, str] = {}
    inert: dict[str, str] = {}
    fstring_only: list[str] = []
    for mid, spec, old, new, _test, expect, _note, also, _source in pop.POPULATION_V4:
        if expect == pop.NOT_MUTATED:
            continue
        conservative_moved = False
        for target_spec, target_old, target_new in ((spec, old, new), *also):
            text, low, high = _region(target_spec)
            count = text[low:high].count(target_old)
            if count != 1:
                stale[mid] = f"{target_spec} matched {count} times"
                continue
            mutated = text[:low] + text[low:high].replace(target_old, target_new) + text[high:]
            if mg._code_digest(text) == mg._code_digest(mutated):
                inert[mid] = f"{target_spec} changes no code"
            if _conservative_digest(text) != _conservative_digest(mutated):
                conservative_moved = True
        if not conservative_moved and mid not in stale:
            fstring_only.append(mid)
    return stale, inert, tuple(fstring_only)


def test_no_two_folded_mutations_share_an_id():
    """The runner writes its work tree at ``mut_<id>``, so two entries under one name is one run."""
    ids = [entry[0] for entry in pop.POPULATION_V4]
    assert len(ids) == len(set(ids)), sorted(i for i in set(ids) if ids.count(i) > 1)
    assert len(ids) == 563, f"{len(ids)} entries; the population the certificate claims is 563"


def test_every_folded_mutation_still_matches_the_source_it_names():
    stale, _inert, _fstring = applied()
    assert stale == {}, (
        "these folded mutations no longer describe the source, so the guards behind them are "
        "unverified whatever their batch log printed:\n  "
        + "\n  ".join(f"{k}: {v}" for k, v in sorted(stale.items())))


def test_every_folded_mutation_changes_executable_code():
    _stale, inert, _fstring = applied()
    assert inert == {}, sorted(inert.items())


def test_the_entries_that_only_bite_on_3_12_are_exactly_the_five_declared():
    """Declared, so that a sixth cannot join them by being written as an f-string edit."""
    _stale, _inert, fstring_only = applied()
    assert sorted(fstring_only) == sorted(pop.FSTRING_ONLY_ON_3_12), (
        f"measured {sorted(fstring_only)}, declared {sorted(pop.FSTRING_ONLY_ON_3_12)}")


def test_every_entry_names_a_target_test_that_exists():
    """A kill is the named test failing, so an entry naming no real test can never be killed."""
    missing = sorted(
        f"{entry[0]}: {entry[4]}" for entry in pop.POPULATION_V4
        if not (REPO / entry[4].split("::")[0]).is_file()
    )
    assert missing == [], missing


def test_every_entry_declares_a_verdict_the_runner_can_report():
    from tools.certification.mutation_v4_runner import verdict_from_junit  # noqa: PLC0415

    reportable = {"KILLED", "SURVIVED", pop.NOT_MUTATED}
    assert verdict_from_junit("<testsuites/>", "tests/x.py::y") == "NOT_COLLECTED"
    wrong = sorted(f"{entry[0]}: {entry[5]}" for entry in pop.POPULATION_V4 if entry[5] not in reportable)
    assert wrong == [], wrong


def test_the_population_is_pinned_by_the_certificate_and_its_digests_are_re_derived():
    """R-67 and R-66 together: the evidence is inside the measured area, and its identity is computed."""
    from tools.certification.core_certificate import SCOPE, enumerate_area  # noqa: PLC0415
    from tools.certification.mutation_population import v4_population  # noqa: PLC0415

    harness = next(area for area in SCOPE if area.name == "harness")
    assert "tests/mutation_population_v4.py" in set(enumerate_area(REPO, harness))
    population = v4_population(REPO)
    assert population.ids == pop.POPULATION_V4_IDS
    assert population.count == 563 and population.definitions_sha256


def test_the_closure_reaches_every_suite_the_population_names():
    """The seeds are half the derivation (R-68).

    A closure taken from the harness TARGETS alone would already contain `hybrid_synthetic.py` and
    would still not contain the suites this round's 563 entries name -- which are exactly the suites
    a V4 kill is a statement about.
    """
    from tools.certification.core_certificate import harness_import_closure  # noqa: PLC0415

    closure = set(harness_import_closure(REPO))
    named = {entry[4].split("::")[0] for entry in pop.POPULATION_V4}
    assert named <= closure, sorted(named - closure)
    assert "tests/test_core_scientific_audit_batch46.py" in closure, (
        "the closure does not reach a suite only the population names, so the population is not one "
        "of its seeds")


def test_a_manifest_is_refused_over_a_harness_area_that_misses_an_imported_helper():
    """Derived and ENFORCED: the check is part of what a certificate means, not only a test here."""
    import pytest  # noqa: PLC0415
    from tools.certification import core_certificate as cc  # noqa: PLC0415

    harness = next(area for area in cc.SCOPE if area.name == "harness")
    # The scope is the harness area ALONE, narrowed: a manifest over the full table would stop at the
    # first area that needs files an isolated copy of the tree does not carry (.github/, the freeze
    # probe), and this test is about which check fires, not about how much of the tree is present.
    narrowed = (type(harness)(
        name="harness", classification="HARNESS", why=harness.why,
        patterns=tuple(p for p in harness.patterns if "hybrid_synthetic" not in p)),)
    with pytest.raises(cc.CertificationError, match="hybrid_synthetic"):
        cc.build_manifest(REPO, narrowed)


def test_the_definitions_digest_covers_the_bodies_and_not_only_the_ids():
    """Finding 91's sharper half: the same ids with a different mutation must be a different population."""
    import json  # noqa: PLC0415

    from tools.certification.mutation_population import v4_population  # noqa: PLC0415

    population = v4_population(REPO)
    ids_only = hashlib.sha256(
        json.dumps([[entry[0]] for entry in pop.POPULATION_V4], sort_keys=True,
                   separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    assert population.definitions_sha256 != ids_only, (
        "the definitions digest is computed over the ids, so an entry whose target test or expected "
        "verdict was rewritten is the same population")
    assert population.declared["B25j"] == pop.NOT_MUTATED


def test_a_population_whose_entries_are_the_wrong_shape_is_refused():
    """An entry missing its target test or its expectation cannot be run; it is refused on READ.

    Not left to the runner: a round that decides at run time what to do with an entry it cannot read
    is a round whose transcript means something different per entry.

    Uses `tempfile` rather than the `tmp_path` fixture on purpose. This test is itself a target of a
    guard mutation, and the isolated runner gives pytest a `--basetemp` whose parent it does not
    create, so a `tmp_path` here ERRORS in every mutant copy -- a red result that says nothing about
    the guard, which is the failure this whole round is about.
    """
    import shutil  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    import pytest  # noqa: PLC0415
    from tools.certification.mutation_population import PopulationError, v4_entries  # noqa: PLC0415

    scratch = pathlib.Path(tempfile.mkdtemp(prefix="v4_population_shape_"))
    try:
        (scratch / "tests").mkdir()
        (scratch / "tests" / "mutation_population_v4.py").write_text(
            "POPULATION_V4 = (('B1a', 'src/x.py', 'a', 'b'),)\n", encoding="utf-8")
        with pytest.raises(PopulationError, match="malformed"):
            v4_entries(scratch)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
