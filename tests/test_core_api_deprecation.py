"""Part S: the deprecation policy, enforced rather than described.

There are ZERO deprecations in the Core API right now, and that is the point
of this file rather than a reason not to have it. A deprecation policy written
on the day of the first deprecation is written by somebody who wants to ship
the deprecation, and it will be shaped to permit whatever they were about to
do. Written now, against an empty registry, it is shaped by nothing.

So everything here runs against a SYNTHETIC entry injected into the registry.
That is what makes an empty policy testable: the mechanism is exercised end to
end -- classification, required fields, warning category, frozen-surface
membership, removal ordering -- without pretending anything is deprecated.

THE ONE RULE THAT IS NOT OBVIOUS
---------------------------------
A DEPRECATED symbol stays INSIDE the frozen snapshot. The tempting alternative
is to drop it, on the grounds that it is no longer promised. That is exactly
backwards: if deprecating a symbol removed it from the frozen surface, then
actually DELETING it later would not move the frozen digest, and the removal --
the only part a caller's program can notice -- would be the one step in the
whole lifecycle that passed silently.
"""

from __future__ import annotations

import warnings

import pytest

from engcore import api_snapshot

#: A symbol that genuinely exists in the frozen contract, borrowed to stand in
#: for a deprecated one. Using a real symbol matters: a made-up name would test
#: the registry's bookkeeping and nothing about how a real entry behaves.
VICTIM = ("engcore.execution", "run_sweep")


def synthetic(**overrides) -> dict:
    record = {
        "reason": "superseded by a spelling that does not imply a schedule",
        "replacement": "engcore.execution.run_sweep_v2",
        "category": DeprecationWarning,
        "since": "1.0",
        "removal": "2.0",
    }
    record.update(overrides)
    return record


@pytest.fixture
def registered(monkeypatch):
    """Inject one synthetic deprecation for the duration of a test."""

    def install(record):
        monkeypatch.setitem(api_snapshot.DEPRECATED_SYMBOLS, VICTIM, record)
        return api_snapshot.build()

    return install


# =====================================================================
# The claim: nothing is deprecated
# =====================================================================

def test_the_registry_is_empty_and_that_is_the_claim():
    """Not an absence of policy -- a statement that nothing is on its way out.

    If this fails, someone added a deprecation. That is allowed; it just has to
    be a decision, which means updating this number and saying why in the
    freeze policy.
    """
    assert api_snapshot.DEPRECATED_SYMBOLS == {}


def test_no_symbol_is_classified_deprecated_today():
    classifications = {
        entry["classification"] for entry in api_snapshot.build()["symbols"]
    }
    assert "DEPRECATED" not in classifications
    assert classifications <= {"FREEZE", "EXPERIMENTAL"}


def test_nothing_is_deprecated_by_docstring_only():
    """The failure mode a registry exists to prevent.

    A docstring that says "deprecated" and a registry that does not know about
    it is the worst of both: callers who read the source stop using it, callers
    who do not carry on, and no tool can tell either group when it goes away.
    """
    import importlib

    offenders = []
    for entry in api_snapshot.frozen_only()["symbols"]:
        module = importlib.import_module(entry["module"])
        doc = getattr(getattr(module, entry["name"], None), "__doc__", "") or ""
        if "deprecat" in doc.lower():
            key = (entry["module"], entry["name"])
            if key not in api_snapshot.DEPRECATED_SYMBOLS:
                offenders.append(key)
    assert not offenders, (
        f"{offenders} announce deprecation in prose but are not in "
        f"DEPRECATED_SYMBOLS, so no tool and no consumer can act on it"
    )


# =====================================================================
# The mechanism, exercised against a synthetic entry
# =====================================================================

def test_a_registered_symbol_is_classified_deprecated(registered):
    snapshot = registered(synthetic())
    entry = next(
        e for e in snapshot["symbols"]
        if (e["module"], e["name"]) == VICTIM
    )
    assert entry["classification"] == "DEPRECATED"
    assert entry["deprecation"]["replacement"] == "engcore.execution.run_sweep_v2"
    assert entry["deprecation"]["category"] == "DeprecationWarning"


def test_a_deprecated_symbol_stays_in_the_frozen_contract(registered):
    """The rule from the module docstring, checked rather than asserted."""
    snapshot = registered(synthetic())
    frozen = {(e["module"], e["name"]) for e in
              api_snapshot.frozen_only(snapshot)["symbols"]}
    assert VICTIM in frozen, (
        "a deprecated symbol left the frozen surface, which would let its "
        "later REMOVAL happen without moving the frozen digest"
    )


def test_deprecating_a_symbol_does_move_the_frozen_digest(registered):
    """Deprecation IS a compatibility event, and the digest has to say so."""
    before = api_snapshot.frozen_digest()
    after = api_snapshot.frozen_digest(registered(synthetic()))
    assert before != after


def test_every_registry_entry_carries_all_five_fields(registered):
    """Applied to the real registry AND to the synthetic one.

    The real registry is empty, so this iteration is vacuous today. It is
    written over the registry rather than over a literal so that it starts
    working the moment the first entry lands, with no one having to remember.
    """
    for key, record in api_snapshot.DEPRECATED_SYMBOLS.items():
        assert set(record) == set(api_snapshot.DEPRECATION_FIELDS), key

    assert set(synthetic()) == set(api_snapshot.DEPRECATION_FIELDS)


@pytest.mark.parametrize("missing", api_snapshot.DEPRECATION_FIELDS)
def test_an_entry_missing_any_field_is_incomplete(missing):
    """Each of the five, one at a time, so none of them is decorative."""
    record = synthetic()
    del record[missing]
    assert set(record) != set(api_snapshot.DEPRECATION_FIELDS)


def test_replacement_may_be_none_but_must_be_said(registered):
    """"There is no replacement" is a legitimate answer.

    It is also a completely different answer from having forgotten to write
    one, which is why the field is required and the VALUE is allowed to be
    None rather than the field being allowed to be absent.
    """
    snapshot = registered(synthetic(replacement=None))
    entry = next(e for e in snapshot["symbols"]
                 if (e["module"], e["name"]) == VICTIM)
    assert entry["deprecation"]["replacement"] is None
    assert "replacement" in entry["deprecation"]


# =====================================================================
# The warning category
# =====================================================================

def test_the_category_must_be_a_deprecation_warning():
    """UserWarning is the wrong choice, for a reason worth stating.

    Python silences DeprecationWarning by default outside __main__. That is
    the behaviour a LIBRARY wants: the application author sees it when they run
    their tests or pass -W, and the end user of an application that happens to
    depend on this Core is not shown a warning about code they did not write
    and cannot change.
    """
    for key, record in api_snapshot.DEPRECATED_SYMBOLS.items():
        assert issubclass(record["category"], DeprecationWarning), key

    assert issubclass(synthetic()["category"], DeprecationWarning)
    assert not issubclass(UserWarning, DeprecationWarning)


def test_a_deprecation_warning_is_silent_by_default_and_visible_on_request():
    """The property the category choice is FOR, demonstrated on real warnings.

    Without this, "use DeprecationWarning" is a convention nobody has checked.
    """
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("ignore", DeprecationWarning)
        warnings.warn("going away", DeprecationWarning, stacklevel=2)
    assert seen == []

    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        warnings.warn("going away", DeprecationWarning, stacklevel=2)
    assert len(seen) == 1
    assert issubclass(seen[0].category, DeprecationWarning)


# =====================================================================
# Removal ordering
# =====================================================================

def test_removal_is_never_earlier_than_the_deprecating_version():
    """A removal scheduled before the deprecation is a contradiction."""
    def parts(text: str) -> tuple[int, ...]:
        return tuple(int(p) for p in text.split("."))

    for key, record in api_snapshot.DEPRECATED_SYMBOLS.items():
        assert parts(record["removal"]) > parts(record["since"]), key

    record = synthetic()
    assert parts(record["removal"]) > parts(record["since"])


def test_removal_is_a_major_version():
    """The freeze policy's actual promise: nothing frozen disappears in a minor.

    A deprecation whose removal is scheduled for 1.1 is not a deprecation, it
    is a breaking change with a warning attached.
    """
    def is_major(text: str) -> bool:
        pieces = text.split(".")
        return len(pieces) >= 2 and all(int(p) == 0 for p in pieces[1:])

    for key, record in api_snapshot.DEPRECATED_SYMBOLS.items():
        assert is_major(record["removal"]), (
            f"{key} is scheduled for removal in {record['removal']}, which is "
            f"not a major version"
        )

    assert is_major(synthetic()["removal"])
    assert not is_major("1.1")


# =====================================================================
# Experimental is not deprecable
# =====================================================================

def test_deprecating_an_experimental_symbol_is_a_no_op(monkeypatch):
    """You cannot withdraw a promise you never made.

    Marking an experimental symbol DEPRECATED would tell a consumer that the
    Core is ending a contract it explicitly never entered -- and would move the
    frozen digest for a symbol that is not in the frozen surface at all.
    """
    experimental = ("engcore.studies", "tcr_prediction")
    monkeypatch.setitem(
        api_snapshot.DEPRECATED_SYMBOLS, experimental, synthetic()
    )
    snapshot = api_snapshot.build()
    entry = next(e for e in snapshot["symbols"]
                 if (e["module"], e["name"]) == experimental)
    assert entry["classification"] == "EXPERIMENTAL"
    assert "deprecation" not in entry
    assert api_snapshot.frozen_digest(snapshot) == api_snapshot.frozen_digest()
