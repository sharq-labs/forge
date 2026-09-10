"""The mutation harness's own guard: every mutation still bites.

`tests/mutation_guards.py` takes about forty minutes and is run by hand. That
is the right cost for what it does -- copy the tree seventy-two times and run
three suites against each copy -- and it is the wrong cadence for noticing that
a mutation has stopped matching the source it names.

**Five had, and nobody knew for months.** `G2f` and `G2g` anchored a two-line
window and 6238531 inserted a line into the middle of it. `G22a`, `G22b` and
`G22c` were reconciled in from a working tree whose implementation never
landed, and have never applied at any commit. Each was reported as MUTATION DID
NOT APPLY, which is the harness being honest, and each was still a guard
verified by nobody -- because the report only appears when somebody runs the
forty minutes.

So the cheap half runs here, on every FAST invocation: every mutation is
applied to the live source **in memory**, and must land exactly once and change
executable code. No tree is copied, no suite is run, nothing is written. It
cannot tell whether a mutation is KILLED -- only the slow harness can -- but it
is what turns "the pattern went stale" from a discovery into a test failure in
the same commit that moved the code.

The declarations are checked here too, for the same reason: a duplicate id, a
mutation with no declared kill mechanism, or one of the five deleted outright
are all states the slow harness refuses to run in, and there is no reason to
wait forty minutes to be told.
"""

from __future__ import annotations

import pathlib

import mutation_guards as mg

REPO = pathlib.Path(__file__).resolve().parent.parent


def _source(spec: str) -> tuple[str, str]:
    """The file's text and the region a mutation searches, newline-normalised.

    Normalisation matches the harness exactly, and for the reason recorded
    there: a target is written with a bare line feed and a working tree on
    Windows holds a carriage return before it.
    """
    relative, _, scope = spec.partition("::")
    path = REPO / relative
    assert path.is_file(), f"{relative} does not exist"
    text = path.read_bytes().decode("utf-8").replace(mg.CRLF, mg.LF)
    if not scope:
        return text, text
    low, high = mg._scope_span(text, scope)
    return text, text[low:high]


def test_no_two_mutations_share_an_id():
    """The runner writes its work tree at `mut_<id>`.

    Two mutations under one name is not a naming quibble: the second deletes
    the first's tree before running, and the summary counts both. It happened
    -- `G8a` and `G8b` each carried two entries, one electrical and one over
    the unit registry -- and the count said 69 either way.
    """
    ids = [m[0] for m in mg.MUTATIONS]
    assert len(ids) == len(set(ids)), sorted(
        i for i in set(ids) if ids.count(i) > 1
    )


def test_every_mutation_says_what_would_kill_it():
    """A result nobody can classify is not evidence.

    Both directions, because either gap is silent: a mutation with no entry
    would run unclassified, and an entry naming no mutation is a guard
    somebody believes is covered.
    """
    mg._validate_declarations()
    assert set(mg.EVIDENCE) == {m[0] for m in mg.MUTATIONS}
    for mid, (mechanism, _expect) in mg.EVIDENCE.items():
        assert mechanism in mg.MECHANISMS, (mid, mechanism)
        assert mechanism not in mg.UNACCEPTABLE, (mid, mechanism)


def test_every_mutation_still_matches_the_source_it_names():
    """The check the slow harness makes, made cheaply and often.

    Exactly once: zero means the pattern went stale and the guard is being
    verified by nobody; more than one means the mutation changes several
    places at once and no result from it can be attributed.
    """
    stale = {}
    for mid, spec, old, _new, _what in mg.MUTATIONS:
        _text, region = _source(spec)
        count = region.count(old)
        if count != 1:
            stale[mid] = f"{spec} matched {count} times"
    assert stale == {}, (
        "these mutations no longer describe the source, so the guards behind "
        "them are unverified whatever the harness last printed:\n  "
        + "\n  ".join(f"{k}: {v}" for k, v in sorted(stale.items()))
    )


def test_every_mutation_changes_executable_code():
    """A mutation that changes a comment reports a guard nobody tested.

    The same rule the harness applies before running a suite, applied here
    before anyone waits for one. `_code_digest` drops COMMENT and STRING
    tokens, so a mutation whose only effect is prose is caught in both places.
    """
    inert = []
    for mid, spec, old, new, _what in mg.MUTATIONS:
        text, region = _source(spec)
        mutated = text.replace(region, region.replace(old, new), 1)
        if mg._code_digest(text) == mg._code_digest(mutated):
            inert.append(mid)
    assert inert == [], inert


def test_the_five_that_were_dead_are_still_declared():
    """Named, so that deleting one is a failure rather than a tidy-up.

    `G2f`, `G2g`, `G22a`, `G22b` and `G22c` were each unexercised when this
    round opened. The way that becomes true again quietly is for a later
    round to meet a stale pattern and remove the entry instead of repointing
    it, which reads as housekeeping and is a guard being retired without
    anyone deciding to retire it.
    """
    declared = {m[0] for m in mg.MUTATIONS}
    assert set(mg.REPAIRED) <= declared, sorted(set(mg.REPAIRED) - declared)


def test_the_harness_verifies_its_own_verifier():
    """`_code_digest` is a check, and an unrun check is unverified."""
    mg._self_test()
