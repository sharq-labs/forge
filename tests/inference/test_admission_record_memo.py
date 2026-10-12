"""The admission-record memo in `AdmittedForwardTable` keeps R-71 exactly.

`AdmittedForwardTable.__post_init__` parses each DISTINCT admission-record
string once and checks every later occurrence against that answer (one TCR
grid used to parse one string 847,242 times). The memo is only sound if two
things hold, and before these tests nothing would notice either one breaking:

1. every occurrence is still checked -- a forgery placed AFTER a well-formed
   record has been remembered, in a later row or in the same row, is refused;
2. only an exact `str` is remembered -- an object that compares and hashes
   equal to a remembered record but reads as something else is parsed on its
   own and refused.

The R-71 batch (`tests/test_core_scientific_audit_batch45.py`) refuses the
audited forgery only at row 0, while the memo is still empty, so it cannot
tell the memo apart from a check that skips everything once one record parsed.
"""

from __future__ import annotations

import numpy as np
import pytest

from engcore.inference.grid import AdmittedForwardTable, InferenceProblemError

GOOD_REF = "numerical|pred-1|ver-1|bind-1"
OTHER_GOOD_REF = "analytic|pred-2|ver-2|bind-2"


def _table(rows_refs, *, keys=("c1:y",)):
    """One admitted row per entry of ``rows_refs``, each carrying one ref per key."""
    n = len(rows_refs)
    return AdmittedForwardTable(
        parameter_names=("x",),
        observation_keys=tuple(keys),
        points=np.arange(n, dtype=np.float64).reshape(n, 1),
        values=np.full((n, len(keys)), 1.0, dtype=np.float64),
        admissible_mask=np.ones(n, dtype=bool),
        admission_refs=tuple(tuple(refs) for refs in rows_refs),
        rejection_reasons=("",) * n,
    )


class _MaskedRecord(str):
    """Equal to, and hashed like, a well-formed record -- but reads as a forgery."""

    def __str__(self) -> str:
        return "forged"


def test_the_control_many_rows_repeating_one_record_are_accepted():
    table = _table([(GOOD_REF,)] * 50 + [(OTHER_GOOD_REF,)] * 50)
    assert table.admitted_routes == ("numerical", "analytic")


def test_a_forgery_after_a_remembered_record_in_a_later_row_is_refused():
    """R-71's audited forgery, one row later than batch 45 places it."""
    with pytest.raises(InferenceProblemError, match=r"row 1 carries 'forged'"):
        _table([(GOOD_REF,), ("forged",)])


def test_a_forgery_beside_a_remembered_record_in_the_same_row_is_refused():
    with pytest.raises(InferenceProblemError, match=r"row 0 carries 'x'"):
        _table([(GOOD_REF, "x")], keys=("c1:y", "c2:y"))


def test_the_first_failing_record_is_the_one_reported():
    """The memo may not change WHICH refusal is raised, only how often a good record is parsed."""
    with pytest.raises(InferenceProblemError, match=r"row 2 carries 'first-bad'"):
        _table([(GOOD_REF,), (GOOD_REF,), ("first-bad",), ("second-bad",)])


def test_an_object_equal_to_a_remembered_record_is_still_parsed_on_its_own():
    masked = _MaskedRecord(GOOD_REF)
    assert masked == GOOD_REF and hash(masked) == hash(GOOD_REF)
    with pytest.raises(InferenceProblemError, match=r"row 1 carries 'forged'"):
        _table([(GOOD_REF,), (masked,)])


def test_an_object_seen_first_is_not_remembered_for_the_exact_string():
    """The memo is fed only by exact `str`, so a masked record cannot vouch for anything."""
    masked = _MaskedRecord(GOOD_REF)
    with pytest.raises(InferenceProblemError, match=r"row 0 carries 'forged'"):
        _table([(masked,), (GOOD_REF,)])


class _DisguisedForgery(str):
    """Reads as a well-formed record, but its VALUE -- what a set compares -- is the forgery."""

    def __str__(self) -> str:
        return GOOD_REF


def test_a_disguised_record_cannot_vouch_for_the_forgery_it_equals():
    """If the memo remembered non-`str` objects, this one would admit the bare string 'forged' after it."""
    disguised = _DisguisedForgery("forged")
    assert disguised == "forged"
    with pytest.raises(InferenceProblemError, match=r"row 1 carries 'forged'"):
        _table([(disguised,), ("forged",)])
