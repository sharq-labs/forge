"""Core re-audit 2026-09-16, batch 50: a declaration that inverts, and an omission misdiagnosed as a core gap.

Problems R-51 (the audit's finding 63) and R-54 (finding 66), improvement I-31, under
benchmarks/core_v4_false_confidence/BATCH50_THRESHOLD_PROTOCOL.json.

`CategoryCondition(allowed='laminar')` stores the six letters of the word, so 'laminar' is outside the
domain and 'a' is inside it. A ratio bound orders its operands only while they are positive, and nothing
required that. And when one operand of a cross-limit condition is declared and the other omitted -- the
ordinary case for the production rated TCR model -- the reason reads UNREADABLE_SHAPE, so the repair layer
tells the caller that declaring the missing limit will not help, which is false.

Recorded as strict xfails in commit dd234130, each seen failing on its own assertion, before the fix.
"""

from __future__ import annotations

import pytest

from engcore.domains.repair import actionable_declarations, unassessable_guidance
from engcore.scientific.models.definition import (
    CategoryCondition,
    CrossLimitCondition,
    ModelValidityError,
    UnknownReason,
    ValidityStatus,
)
from engcore.scientific.units.quantity import Quantity

REFERENCE = "reference_temperature"
CEILING = "maximum_operating_temperature"


def _cross(**overrides) -> CrossLimitCondition:
    fields = dict(
        name="reference_temperature_utilization", numerator=REFERENCE, denominator=CEILING,
        maximum=Quantity(1.0, "dimensionless"),
    )
    fields.update(overrides)
    return CrossLimitCondition(**fields)


def _assessment(condition, context):
    """One UNKNOWN condition, as the assessment record a caller reads it through."""
    from engcore.scientific.models.definition import (
        UnknownCondition,
        ValidityAssessment,
    )

    assert condition.evaluate_in(context) is ValidityStatus.UNKNOWN
    return ValidityAssessment(
        status=ValidityStatus.UNKNOWN,
        unknown=(condition.name,),
        unknown_reasons=(
            UnknownCondition(name=condition.name, reason=condition.explain_in(context)),
        ),
    )


# ---------------------------------------------------------------------------
# a_bare_string_is_not_an_allowed_set
# ---------------------------------------------------------------------------
def test_r54_a_list_of_words_is_still_an_allowed_set():
    """The control: what a caller who meant a set gets."""
    condition = CategoryCondition(name="regime", allowed=["laminar", "turbulent"])
    assert condition.evaluate("laminar") is ValidityStatus.IN_DOMAIN


def test_r54_a_bare_string_allowed_set_is_refused():
    with pytest.raises(ModelValidityError, match="laminar|letter|string"):
        CategoryCondition(name="regime", allowed="laminar")


def test_r54_a_bare_string_allowed_set_is_refused_on_read():
    payload = CategoryCondition(name="regime", allowed=["laminar"]).to_dict()
    payload["allowed"] = "laminar"
    with pytest.raises(ModelValidityError, match="laminar|letter|string"):
        CategoryCondition.from_dict(payload)


def test_r54_the_audited_inversion_cannot_be_declared():
    """As audited: 'laminar' outside its own allowed set, and 'a' inside it."""
    try:
        condition = CategoryCondition(name="regime", allowed="laminar")
    except ModelValidityError:
        return
    assert condition.evaluate("laminar") is ValidityStatus.IN_DOMAIN, (
        "the word is outside its own allowed set")
    assert condition.evaluate("a") is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN, (
        "a single letter is inside it")


# ---------------------------------------------------------------------------
# a_ratio_bound_cannot_order_operands_whose_sign_it_does_not_know
# ---------------------------------------------------------------------------
def test_r54_a_positive_ratio_still_orders_its_operands():
    """The control, and every in-tree case: absolute temperatures, and a above b is refused."""
    condition = _cross()
    below = {REFERENCE: Quantity(300.0, "kelvin"), CEILING: Quantity(400.0, "kelvin")}
    above = {REFERENCE: Quantity(500.0, "kelvin"), CEILING: Quantity(400.0, "kelvin")}
    assert condition.evaluate_in(below) is ValidityStatus.IN_DOMAIN
    assert condition.evaluate_in(above) is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN


def test_r54_two_negative_operands_are_not_ordered_by_their_ratio():
    condition = _cross(numerator="a", denominator="b")
    context = {"a": Quantity(-0.5, "volt"), "b": Quantity(-1.0, "volt")}
    assert condition.evaluate_in(context) is ValidityStatus.UNKNOWN, (
        "a is above b and the ratio 0.5 reads as satisfied")


def test_r54_a_sign_indefinite_pair_is_not_ordered_by_their_ratio():
    condition = _cross(numerator="a", denominator="b")
    context = {"a": Quantity(2.0, "volt"), "b": Quantity(-1.0, "volt")}
    assert condition.evaluate_in(context) is ValidityStatus.UNKNOWN


def test_r54_the_unordered_ratio_has_its_own_reason_and_its_own_guidance():
    condition = _cross(numerator="a", denominator="b")
    context = {"a": Quantity(2.0, "volt"), "b": Quantity(-1.0, "volt")}
    reason = condition.explain_in(context)
    assert reason not in {UnknownReason.NOT_SUPPLIED, UnknownReason.UNREADABLE_SHAPE}, reason
    (item,) = unassessable_guidance(_assessment(condition, context))
    assert item.actionable is False and item.guidance.strip()


# ---------------------------------------------------------------------------
# a_missing_operand_is_a_declaration_the_caller_can_supply
# ---------------------------------------------------------------------------
def test_r51_an_omitted_limit_is_not_supplied_rather_than_unreadable():
    condition = _cross()
    context = {REFERENCE: Quantity(300.0, "kelvin")}
    assert condition.explain_in(context) is UnknownReason.NOT_SUPPLIED


def test_r51_both_omitted_is_still_not_supplied():
    """The control, and the one case the audited code got right."""
    assert _cross().explain_in({}) is UnknownReason.NOT_SUPPLIED


def test_r51_an_operand_in_a_shape_the_core_cannot_read_is_still_unreadable():
    """The control the precedence is about: supplying the other limit would not help."""
    condition = _cross()
    context = {REFERENCE: 300.0, CEILING: Quantity(400.0, "kelvin")}
    assert condition.explain_in(context) is UnknownReason.UNREADABLE_SHAPE


def test_r51_the_repair_layer_tells_the_caller_to_declare_the_missing_limit():
    condition = _cross()
    context = {REFERENCE: Quantity(300.0, "kelvin")}
    assessment = _assessment(condition, context)
    (item,) = unassessable_guidance(assessment)
    assert item.actionable is True, item.guidance
    assert actionable_declarations(assessment) == (condition.name,)


# ---------------------------------------------------------------------------
# the_diagnostic_names_a_key_a_caller_could_supply
# ---------------------------------------------------------------------------
def test_r51_the_diagnostic_names_the_operand_the_context_is_missing():
    from engcore.scientific.models.definition import ValidityDomain
    from engcore.scientific.models.unknown_diagnostics import diagnose_unknowns

    condition = _cross()
    context = {REFERENCE: Quantity(300.0, "kelvin")}
    domain = ValidityDomain(conditions=(condition,))
    (diagnostic,) = diagnose_unknowns(domain, _assessment(condition, context), context)
    assert diagnostic.context_key == CEILING, diagnostic
    assert diagnostic.stable_reason is UnknownReason.NOT_SUPPLIED
