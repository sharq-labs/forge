"""Executable guards over the shipped record <-> runtime contract.

These are the tests the round's mutation catalog runs against. Each one fails
when a published record and the guarded runtime stop saying the same thing, in
one of the two directions Phase CG-7 names:

* the record advertises applicability the runtime refuses (RECORD_TOO_BROAD)
* the record disclaims applicability the runtime grants (RECORD_TOO_NARROW)

They are generic. There is no per-model fixture and no per-condition expected
value written down anywhere: every assertion is derived from the shipped
records themselves and checked against real ``assess_validity`` calls, so a
model or a condition added later is covered the day it ships.
"""

from benchmarks.contract_guard.guard import (
    capabilities,
    enforcement,
    prerequisites,
    prose,
    records,
)


def test_every_shipped_model_is_reachable_from_the_declaring_modules():
    models = records.shipped_models()
    assert len(models) == len({model.model_id for model in models})
    assert len(models) >= 16, "the guarded surface shrank; a model stopped shipping"
    systems = {records.system_of(model.model_id) for model in models}
    assert systems >= {
        "thermal.lumped",
        "thermal.conduction1d",
        "battery.cell",
        "kinetics.cstr",
        "electrical.dc",
        "electrical.material",
    }


def test_every_shipped_condition_carries_a_structured_bound():
    """A condition with no readable bound is a claim nothing can enforce."""
    unbounded = [
        ref.ref
        for ref in records.conditions()
        if ref.minimum is None and ref.maximum is None
    ]
    assert unbounded == []


def test_every_structured_bound_is_enforced_by_the_runtime():
    """Each declared edge, probed on both sides, must land where the record says.

    This is the record -> runtime direction with no prose in the loop: the
    bound a model publishes is walked across its own edges and the verdict the
    runtime returns is compared with the verdict the bound promises.
    """
    report = enforcement.survey()
    assert report["probes"] > 0
    assert report["disagreements"] == [], report["disagreements"]


def test_no_record_advertises_applicability_the_runtime_refuses():
    """RECORD_TOO_BROAD: prose says a value is in scope, the runtime says no."""
    too_broad = [
        finding
        for finding in prose.check()["findings"]
        if finding["direction"] == prose.RECORD_TOO_BROAD
    ]
    assert too_broad == [], too_broad


def test_no_record_disclaims_applicability_the_runtime_grants():
    """RECORD_TOO_NARROW: prose says a value is out of scope, the runtime accepts."""
    too_narrow = [
        finding
        for finding in prose.check()["findings"]
        if finding["direction"] == prose.RECORD_TOO_NARROW
    ]
    assert too_narrow == [], too_narrow


def test_a_record_that_restates_its_bound_in_prose_restates_the_right_number():
    """Prose and structure are two publications of one bound; they must agree.

    The runtime probes above already catch a prose bound that is *wrong*. This
    catches the narrower case of a prose bound that is merely stale -- the
    structured edge moved and the sentence did not -- before it becomes a
    reader's incorrect belief.
    """
    mismatched = []
    for ref in records.conditions():
        claimed = prose.prose_bound(ref)
        if claimed is None:
            continue
        if not _same(claimed.minimum, ref.minimum) or not _same(
            claimed.maximum, ref.maximum
        ):
            mismatched.append((ref.ref, claimed, ref.minimum, ref.maximum))
            continue
        if claimed.minimum is not None and (
            claimed.minimum_inclusive != ref.minimum_inclusive
        ):
            mismatched.append((ref.ref, "minimum inclusivity", claimed, ref))
        if claimed.maximum is not None and (
            claimed.maximum_inclusive != ref.maximum_inclusive
        ):
            mismatched.append((ref.ref, "maximum inclusivity", claimed, ref))
    assert mismatched == [], mismatched


def _same(left, right) -> bool:
    if left is None or right is None:
        return left is right
    return abs(left - right) <= 1e-9 * max(1.0, abs(left))


# --- audit-side self-tests -------------------------------------------------
#
# The guards above are only worth their green if the extractor underneath them
# reads English the way it claims to. These pin the three readings that were
# wrong in a first draft and would have produced confident false accusations.


def test_a_decimal_point_does_not_end_the_leading_clause():
    assert prose.leading_clause("Bi = h L_c / k <= 0.1, the ratio") == (
        "Bi = h L_c / k <= 0.1"
    )
    bound = prose._restrictive("Fo = (t/tau)/Bi >= 0.2")
    assert bound is not None and bound.minimum == 0.2


def test_a_comma_inside_brackets_or_bars_does_not_end_the_leading_clause():
    assert prose.leading_clause("min(f, 1 - f) <= 0.05 for f, then") == (
        "min(f, 1 - f) <= 0.05 for f"
    )
    assert prose.leading_clause("|T - T_Q,ref| / span <= 1: because") == (
        "|T - T_Q,ref| / span <= 1"
    )


def test_a_bound_stated_about_another_symbol_is_not_read_as_this_condition_s():
    """The ``Pr >= 0.6`` sentence is about the Prandtl number, not the ratio."""
    ref = records.model_by_id("thermal.lumped.first_order_capacity")
    condition = next(
        item
        for item in records.conditions()
        if item.name == "convection_property_range_utilization"
    )
    assert "Pr >= 0.6" in condition.description
    assert prose.prose_bound(condition) is None


def test_a_permissive_sentence_is_read_as_a_claim_about_scope():
    """The phrasing the SC5 mutation introduces must register as a claim."""
    claims = prose._permissive(
        next(
            item
            for item in records.conditions()
            if item.ref == "thermal.lumped.first_order_capacity::heat_capacity"
        ),
        "Any capacity, including zero, is supported.",
    )
    assert any(claim.value == 0.0 and claim.verdict == prose.ACCEPTS for claim in claims)


def test_the_word_unbounded_about_another_quantity_is_not_a_permissive_claim():
    condition = next(
        item for item in records.conditions() if item.name == "lumped_electrical_length"
    )
    assert "unbounded" in condition.description
    assert prose._permissive(condition, condition.description) == []


# --- dimension A: required/optional inputs ---------------------------------


def test_required_means_required_and_optional_means_optional():
    """The word in the record is checked against the public constructor.

    Required: the constructor must refuse without it. Optional: the
    constructor must build without it. Inputs that are solved unknowns, and
    declarations that reach the model through the validity context rather than
    a constructor argument, are excluded here and covered by the
    UNKNOWN-prerequisite guard below; the survey reports that denominator.
    """
    survey = prerequisites.required_input_survey()
    assert survey["checks"] > 0
    assert "NO_BUILDER" not in survey["baseline_construction"].values(), (
        "a shipped system lost its constructor probe: "
        f"{survey['baseline_construction']}"
    )
    assert survey["contradictions"] == [], survey["contradictions"]


# --- dimension B: UNKNOWN prerequisites ------------------------------------


def test_every_published_unknown_prerequisite_still_holds():
    """Withhold what each "UNKNOWN unless ..." clause names; demand UNKNOWN.

    RECORD_TOO_BROAD here means the runtime answers a condition whose record
    says it cannot; RECORD_TOO_NARROW means an alternative route the record
    advertises no longer serves alone.
    """
    review = prerequisites.unknown_promise_review()
    assert review["checks"] > 0
    assert review["disagreements"] == [], review["disagreements"]


def test_no_shipped_condition_is_missing_from_the_claim_map():
    """A condition nobody mapped is a condition nobody checks.

    This is what stops a model shipping into the guarded surface unguarded:
    add a condition, and the prerequisite review has nothing to say about it
    until someone writes down what its record means.
    """
    coverage = prerequisites.claim_map_coverage()
    assert coverage["unmapped"] == [], coverage["unmapped"]


def test_no_condition_is_satisfied_before_anything_is_declared():
    """An empty context cannot satisfy a claim about a caller's system."""
    premature = []
    for model in records.shipped_models():
        assessment = model.assess_validity(declared={}, assembled={})
        for name in assessment.satisfied:
            premature.append(f"{model.model_id}::{name}")
    assert premature == [], premature


# --- dimension F: reason/result agreement ----------------------------------


def test_every_unknown_condition_carries_a_reason():
    """UNKNOWN without a reason is a refusal a caller cannot act on."""
    silent = []
    for model in records.shipped_models():
        assessment = model.assess_validity(declared={}, assembled={})
        for name in assessment.unknown:
            if assessment.reason_for(name) is None:
                silent.append(f"{model.model_id}::{name}")
        if assessment.unknown and assessment.status.name != "UNKNOWN":
            silent.append(f"{model.model_id}: status {assessment.status.name}")
    assert silent == [], silent


# --- dimension G: capability declarations ----------------------------------


def test_no_model_requires_a_capability_nothing_serves():
    survey = capabilities.survey()
    assert survey["models"] >= 16
    assert survey["unserved"] == [], survey["unserved"]


def test_nothing_declared_derives_nothing_unless_the_record_says_so():
    """An assembler that invents a quantity dissolves every prerequisite at once.

    The exception is a condition the record publishes as settled by the
    model's own scope; that one must say so in the text a caller reads.
    """
    survey = prerequisites.self_derived_survey()
    assert survey["contexts"] > 0
    assert survey["undeclared"] == [], survey["undeclared"]
