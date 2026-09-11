"""A strong verdict must be harder to earn than a refusal -- systematically.

WHY THIS MODULE EXISTS
----------------------
``derive_verdict`` is the single place a credibility verdict is decided, and
before this module its coverage was a handful of assertions inside guards about
other things: one SUPPORTED case, one UNKNOWN case, one shape refusal. Every one
of them checks that a *particular* input maps to a *particular* verdict. None
asks the question a reader of a SUPPORTED report actually needs answered, which
is not "is this input mapped correctly" but:

    can anything I could ADD, REMOVE or REPEAT make this report say more?

That is a property over the whole input space rather than a point in it, and it
is the property false confidence would have to break. So these enumerate.

THE FOUR PROPERTIES, AND WHY EACH IS THE RIGHT ONE
--------------------------------------------------
Verdicts are ordered by how much they claim: NOT_SUPPORTED < INSUFFICIENT_
EVIDENCE < SUPPORTED. "Stronger" below means further up that order.

*Adverse evidence never strengthens.* Adding a validity record that is UNKNOWN
or OUTSIDE_VALIDATED_DOMAIN, a check that FAILED or did not run, a model nobody
assessed, an assessment nothing attributes, a coupling that missed its
criterion, or a level the caller says it needs -- none of these may move a
verdict up. Note this is deliberately **not** the symmetric claim: removing a
FAIL *should* strengthen, because the evidence against the design is gone.

*Removing support never strengthens.* Drop a passing check that established a
level and the verdict may fall or stay; it may never rise. This is the
monotonic-refusal direction, and it is what makes a report's SUPPORTED depend
on evidence being present rather than on evidence being absent.

*Repetition is inert.* The same check twice, the same validity record twice, is
one piece of evidence stated twice. If duplication moved anything, evidence
could be manufactured by copying it -- the cheapest possible attack on a
credibility claim.

*Order is inert.* The docstring calls the function order-independent. Nothing
asserted it over more than one arrangement.

WHAT THIS DOES NOT CLAIM
------------------------
That the rules are the scientifically right rules. It claims they are
monotone in the direction a trust boundary has to be monotone in. Whether
``analytically_verified`` is worth what it sounds like is a question for
``docs/assurance/ORACLE_REGISTER.md``, not for this module.
"""

from __future__ import annotations

import itertools

import pytest

from engcore.mcp.evidence import (
    CouplingEvidence,
    CredibilityVerdict,
    ModelValidityRecord,
    derive_verdict,
)
from engcore.scientific.models.definition import (
    UnknownCondition,
    UnknownReason,
    ValidityAssessment,
    ValidityStatus,
)
from engcore.scientific.results.validation import (
    ValidationCheck,
    ValidationLevel,
    ValidationOutcome,
)
from engcore.scientific.units.quantity import Quantity


#: How much a verdict claims. The whole module is written against this order.
STRENGTH = {
    CredibilityVerdict.NOT_SUPPORTED: 0,
    CredibilityVerdict.INSUFFICIENT_EVIDENCE: 1,
    CredibilityVerdict.SUPPORTED: 2,
}


def _record(model_id: str, status: ValidityStatus) -> ModelValidityRecord:
    if status is ValidityStatus.IN_DOMAIN:
        assessment = ValidityAssessment(
            status=status, satisfied=("biot_number",)
        )
    elif status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN:
        assessment = ValidityAssessment(
            status=status, violated=("biot_number",)
        )
    else:
        assessment = ValidityAssessment(
            status=status,
            unknown=("biot_number",),
            unknown_reasons=(
                UnknownCondition("biot_number", UnknownReason.NOT_SUPPLIED),
            ),
        )
    return ModelValidityRecord(
        model_id=model_id, version="0.1.0", assessment=assessment
    )


def _check(name: str, outcome: ValidationOutcome, level=None) -> ValidationCheck:
    """A check that is internally coherent, so the shape guards admit it."""
    if outcome is ValidationOutcome.PASS:
        return ValidationCheck(
            name=name,
            outcome=outcome,
            detail="a passing comparison",
            establishes=level,
            residual=0.0,
            tolerance=1e-9,
        )
    if outcome is ValidationOutcome.FAIL:
        return ValidationCheck(
            name=name,
            outcome=outcome,
            detail="a comparison outside its bound",
            residual=1.0,
            tolerance=1e-9,
        )
    return ValidationCheck(name=name, outcome=outcome, detail="no comparison")


# The supporting core: one in-domain model and one passing check that
# establishes a level. `derive_verdict` returns SUPPORTED for it, and every
# property below perturbs it.
SUPPORTING_VALIDITY = (_record("m.a", ValidityStatus.IN_DOMAIN),)
SUPPORTING_CHECK = _check(
    "analytic", ValidationOutcome.PASS, ValidationLevel.ANALYTICALLY_VERIFIED
)
SUPPORTING_VALIDATION = (SUPPORTING_CHECK,)

#: Every way this module knows of to say "something here is not established".
#: Each entry is a keyword-argument patch onto a call.
ADVERSE = {
    "unknown validity record": {
        "validity": SUPPORTING_VALIDITY + (
            _record("m.b", ValidityStatus.UNKNOWN),
        )
    },
    "violated validity record": {
        "validity": SUPPORTING_VALIDITY + (
            _record("m.b", ValidityStatus.OUTSIDE_VALIDATED_DOMAIN),
        )
    },
    "failed check": {
        "validation": SUPPORTING_VALIDATION + (
            _check("other", ValidationOutcome.FAIL),
        )
    },
    "check that did not run": {
        "validation": SUPPORTING_VALIDATION + (
            _check("other", ValidationOutcome.NOT_RUN),
        )
    },
    "unassessed model": {"unassessed_models": (("m.z", "0.1.0"),)},
    "unattributed assessment": {"unattributed_assessments": (("m.z", "0.1.0"),)},
    "coupling that missed its criterion": {
        "coupling": CouplingEvidence(
            outcome="iteration_limit_reached",
            iterations_run=200,
            iteration_limit=200,
            largest_iterate_change=Quantity(1.0, "kelvin"),
            tolerance=Quantity(1e-6, "kelvin"),
        )
    },
    "a required level nothing attained": {
        "required_levels": (ValidationLevel.EXPERIMENTALLY_VALIDATED,)
    },
}


def _verdict(**overrides) -> CredibilityVerdict:
    call = {
        "validity": SUPPORTING_VALIDITY,
        "validation": SUPPORTING_VALIDATION,
    }
    call.update(overrides)
    return derive_verdict(**call)


def test_the_baseline_this_module_perturbs_really_is_supported():
    """Every property below is vacuous if the starting point is not the top."""
    assert _verdict() is CredibilityVerdict.SUPPORTED


# =====================================================================
# Property 1 -- adverse evidence never strengthens
# =====================================================================

@pytest.mark.parametrize("label", sorted(ADVERSE))
def test_adding_adverse_evidence_never_strengthens_a_verdict(label):
    before = _verdict()
    after = _verdict(**ADVERSE[label])
    assert STRENGTH[after] <= STRENGTH[before], (
        f"adding {label!r} moved the verdict UP: "
        f"{before.value} -> {after.value}"
    )


def test_every_adverse_kind_is_exercised():
    """A walk that stopped covering its space must fail, not pass silently."""
    assert len(ADVERSE) == 8


@pytest.mark.parametrize(
    "first,second", list(itertools.combinations(sorted(ADVERSE), 2))
)
def test_adverse_evidence_does_not_cancel_out_in_pairs(first, second):
    """Two problems are not better than one."""
    combined = {**ADVERSE[first], **ADVERSE[second]}
    # Merge rather than overwrite where both patch the same argument.
    for key in set(ADVERSE[first]) & set(ADVERSE[second]):
        merged = list(ADVERSE[first][key])
        for item in ADVERSE[second][key]:
            if item not in merged:
                merged.append(item)
        combined[key] = tuple(merged)
    pair = _verdict(**combined)
    assert STRENGTH[pair] <= STRENGTH[_verdict(**ADVERSE[first])]
    assert STRENGTH[pair] <= STRENGTH[_verdict(**ADVERSE[second])]


# =====================================================================
# Property 2 -- removing support never strengthens
# =====================================================================

def test_removing_the_only_level_bearing_check_never_strengthens():
    with_support = _verdict()
    without = _verdict(validation=())
    assert STRENGTH[without] <= STRENGTH[with_support]
    assert without is CredibilityVerdict.INSUFFICIENT_EVIDENCE


def test_removing_every_validity_record_never_strengthens():
    """No records at all is a refusal, not a clean bill of health."""
    assert STRENGTH[_verdict(validity=())] <= STRENGTH[_verdict()]
    assert _verdict(validity=()) is CredibilityVerdict.INSUFFICIENT_EVIDENCE


def test_downgrading_a_passing_check_to_one_that_earns_nothing_never_strengthens():
    weaker = _verdict(
        validation=(_check("analytic", ValidationOutcome.PASS),)
    )
    assert STRENGTH[weaker] <= STRENGTH[_verdict()]


@pytest.mark.parametrize("keep", [(), (0,)])
def test_no_subset_of_the_supporting_evidence_outranks_the_whole(keep):
    """Enumerated rather than argued: every subset, against the full set."""
    subset = tuple(SUPPORTING_VALIDATION[i] for i in keep)
    assert STRENGTH[_verdict(validation=subset)] <= STRENGTH[_verdict()]


# =====================================================================
# Property 3 -- repetition is inert
# =====================================================================

def test_duplicating_the_supporting_check_changes_nothing():
    """Evidence stated twice is one piece of evidence."""
    assert _verdict(
        validation=SUPPORTING_VALIDATION * 2
    ) is _verdict()


def test_duplicating_a_validity_record_changes_nothing():
    assert _verdict(validity=SUPPORTING_VALIDITY * 2) is _verdict()


@pytest.mark.parametrize("label", sorted(ADVERSE))
def test_duplicating_adverse_evidence_cannot_dilute_it(label):
    """Repeating a problem must not average it away either."""
    once = _verdict(**ADVERSE[label])
    patch = {
        key: (tuple(value) * 2 if isinstance(value, tuple) else value)
        for key, value in ADVERSE[label].items()
    }
    assert _verdict(**patch) is once


def test_duplicating_a_level_bearing_check_does_not_attain_a_further_level():
    """Two copies of one check are not two independent confirmations."""
    needs_two = _verdict(
        validation=SUPPORTING_VALIDATION * 2,
        required_levels=(
            ValidationLevel.ANALYTICALLY_VERIFIED,
            ValidationLevel.CROSS_SOLVER_VALIDATED,
        ),
    )
    assert needs_two is CredibilityVerdict.INSUFFICIENT_EVIDENCE


# =====================================================================
# Property 4 -- order is inert
# =====================================================================

MIXED_VALIDITY = (
    _record("m.a", ValidityStatus.IN_DOMAIN),
    _record("m.b", ValidityStatus.UNKNOWN),
    _record("m.c", ValidityStatus.OUTSIDE_VALIDATED_DOMAIN),
)
MIXED_VALIDATION = (
    SUPPORTING_CHECK,
    _check("warned", ValidationOutcome.WARNING),
    _check("failed", ValidationOutcome.FAIL),
)


def test_no_arrangement_of_the_inputs_changes_the_verdict():
    """All 36 arrangements of a deliberately contradictory report."""
    verdicts = {
        derive_verdict(validity=list(v), validation=list(c))
        for v in itertools.permutations(MIXED_VALIDITY)
        for c in itertools.permutations(MIXED_VALIDATION)
    }
    assert len(verdicts) == 1, f"order changed the verdict: {verdicts}"
    assert verdicts.pop() is CredibilityVerdict.NOT_SUPPORTED


def test_that_permutation_walk_really_covered_thirty_six_arrangements():
    assert (
        len(list(itertools.permutations(MIXED_VALIDITY)))
        * len(list(itertools.permutations(MIXED_VALIDATION)))
        == 36
    )


# =====================================================================
# Precedence -- a violation outranks a gap, in every arrangement
# =====================================================================

def test_a_violation_outranks_a_gap_however_the_two_arrive():
    violated = _record("m.v", ValidityStatus.OUTSIDE_VALIDATED_DOMAIN)
    unknown = _record("m.u", ValidityStatus.UNKNOWN)
    for order in itertools.permutations((violated, unknown)):
        assert (
            derive_verdict(validity=list(order), validation=SUPPORTING_VALIDATION)
            is CredibilityVerdict.NOT_SUPPORTED
        )
