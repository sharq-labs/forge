"""``CrossLimitCondition`` — one declared limit against another.

``RangeCondition`` compares a quantity to a bound written into the model
record. Nothing in the core expressed *this declared limit must stand in a
relation to that declared limit*, so the three conditions that needed it in the
electrical material model were built by hand: a domain assembled a ratio, gave
it a name, and a RangeCondition bounded the name. Every domain that declares
limits will want the same shape.

The three properties this type exists for, and every one of them is tested
below:

* the comparison is between **two declared values**;
* it is decidable **before any solve**, because neither operand is a state;
* it is **UNKNOWN when either is absent**, and never IN_DOMAIN.
"""

from __future__ import annotations

import pytest

from engcore.scientific.errors import ModelValidityError
from engcore.scientific.models.definition import (
    CategoryCondition,
    CrossLimitCondition,
    FlagCondition,
    RangeCondition,
    ValidityDomain,
    ValidityStatus,
)
from engcore.scientific.units.quantity import Quantity

Q = Quantity
ONE = "dimensionless"
K = "kelvin"


def ceiling(**kwargs) -> CrossLimitCondition:
    """T_ref / T_max <= 1 — the shape the electrical model uses."""
    defaults = dict(
        name="reference_below_ceiling",
        numerator="reference_temperature",
        denominator="maximum_temperature",
        maximum=Q(1.0, ONE),
    )
    defaults.update(kwargs)
    return CrossLimitCondition(**defaults)


def assess(condition, context):
    return ValidityDomain(conditions=(condition,)).assess(context)


# =====================================================================
# The comparison
# =====================================================================

def test_a_declared_limit_inside_another_is_in_domain() -> None:
    verdict = assess(
        ceiling(),
        {
            "reference_temperature": Q(293.15, K),
            "maximum_temperature": Q(450.0, K),
        },
    )
    assert verdict.status is ValidityStatus.IN_DOMAIN
    assert verdict.satisfied == ("reference_below_ceiling",)


def test_a_declared_limit_outside_another_is_a_finding() -> None:
    """The contradiction is in the declaration, and needs no state to see."""
    verdict = assess(
        ceiling(),
        {
            "reference_temperature": Q(500.0, K),
            "maximum_temperature": Q(450.0, K),
        },
    )
    assert verdict.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert verdict.violated == ("reference_below_ceiling",)


def test_the_bound_is_exact_with_no_epsilon_either_side() -> None:
    """Same contract logic as RangeCondition, and it shares the code."""
    for reference, expected in (
        (449.999, ValidityStatus.IN_DOMAIN),
        (450.0, ValidityStatus.IN_DOMAIN),        # inclusive by default
        (450.001, ValidityStatus.OUTSIDE_VALIDATED_DOMAIN),
    ):
        verdict = assess(
            ceiling(),
            {
                "reference_temperature": Q(reference, K),
                "maximum_temperature": Q(450.0, K),
            },
        )
        assert verdict.status is expected

    strict = ceiling(maximum_inclusive=False)
    verdict = assess(
        strict,
        {
            "reference_temperature": Q(450.0, K),
            "maximum_temperature": Q(450.0, K),
        },
    )
    assert verdict.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN


def test_a_floor_works_as_well_as_a_ceiling() -> None:
    """T_max / theta_D >= 1/3, the other shape the electrical model uses."""
    floor = CrossLimitCondition(
        name="ceiling_above_debye_floor",
        numerator="maximum_temperature",
        denominator="debye_temperature",
        minimum=Q(1.0 / 3.0, ONE),
    )
    inside = assess(
        floor,
        {
            "maximum_temperature": Q(450.0, K),
            "debye_temperature": Q(343.0, K),
        },
    )
    assert inside.status is ValidityStatus.IN_DOMAIN

    outside = assess(
        floor,
        {
            "maximum_temperature": Q(450.0, K),
            "debye_temperature": Q(2000.0, K),
        },
    )
    assert outside.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN


def test_the_units_of_the_two_operands_need_not_match_only_their_dimension(
) -> None:
    """A ratio is a ratio: rankine over kelvin is the same number."""
    verdict = assess(
        ceiling(),
        {
            # 527.67 degR is 293.15 K exactly.
            "reference_temperature": Q(527.67, "rankine"),
            "maximum_temperature": Q(450.0, K),
        },
    )
    assert verdict.status is ValidityStatus.IN_DOMAIN


# =====================================================================
# It needs no state, and no solve
# =====================================================================

def test_it_is_decided_without_any_state_coordinate() -> None:
    """The context carries only declarations. Nothing was run.

    This is the property that makes the type worth having: a caller can be
    told the declaration contradicts itself before a solver is chosen.
    """
    domain = ValidityDomain(
        conditions=(
            ceiling(),
            RangeCondition(name="temperature", minimum=Q(200.0, K)),
        )
    )
    verdict = domain.assess(
        {
            "reference_temperature": Q(500.0, K),
            "maximum_temperature": Q(450.0, K),
        }
    )
    # The state-facing condition is UNKNOWN because no state was supplied;
    # the cross-limit one is decided anyway, and it outranks.
    assert verdict.violated == ("reference_below_ceiling",)
    assert verdict.unknown == ("temperature",)
    assert verdict.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN


# =====================================================================
# Missing means UNKNOWN, never IN_DOMAIN
# =====================================================================

@pytest.mark.parametrize(
    "context",
    [
        {},
        {"reference_temperature": Q(293.15, K)},
        {"maximum_temperature": Q(450.0, K)},
        {"reference_temperature": None, "maximum_temperature": Q(450.0, K)},
        # A bare number is not a declaration.
        {"reference_temperature": 293.15, "maximum_temperature": Q(450.0, K)},
    ],
)
def test_either_operand_absent_is_unknown(context) -> None:
    verdict = assess(ceiling(), context)
    assert verdict.status is ValidityStatus.UNKNOWN
    assert verdict.unknown == ("reference_below_ceiling",)
    assert verdict.satisfied == () and verdict.violated == ()


def test_omitting_the_denominator_cannot_satisfy_the_condition() -> None:
    """The asymmetry the whole platform rests on, checked for this type.

    A caller who leaves out the limit that would refuse them gets UNKNOWN, not
    IN_DOMAIN. Supplying it can only move the verdict away from UNKNOWN.
    """
    without = assess(ceiling(), {"reference_temperature": Q(500.0, K)})
    assert without.status is ValidityStatus.UNKNOWN
    with_it = assess(
        ceiling(),
        {
            "reference_temperature": Q(500.0, K),
            "maximum_temperature": Q(450.0, K),
        },
    )
    assert with_it.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN


# =====================================================================
# Refusals at construction and at assessment
# =====================================================================

def test_a_condition_comparing_a_name_with_itself_is_refused() -> None:
    with pytest.raises(ModelValidityError):
        CrossLimitCondition(
            name="silly", numerator="t", denominator="t", maximum=Q(1.0, ONE)
        )


def test_a_condition_with_no_bound_is_refused() -> None:
    with pytest.raises(ModelValidityError):
        CrossLimitCondition(name="n", numerator="a", denominator="b")


@pytest.mark.parametrize("field", ["name", "numerator", "denominator"])
def test_an_empty_operand_name_is_refused(field) -> None:
    kwargs = dict(name="n", numerator="a", denominator="b", maximum=Q(1.0, ONE))
    kwargs[field] = "   "
    with pytest.raises(ModelValidityError):
        CrossLimitCondition(**kwargs)


def test_a_dimensional_bound_is_refused_at_construction() -> None:
    """The ratio of two same-dimension declarations is dimensionless.

    A bound carrying kelvin would make this a range condition wearing the
    wrong type, so it is refused where it is written rather than where it is
    read.
    """
    with pytest.raises(ModelValidityError):
        CrossLimitCondition(
            name="n", numerator="a", denominator="b", maximum=Q(450.0, K)
        )


def test_a_maximum_below_a_minimum_is_refused() -> None:
    with pytest.raises(ModelValidityError):
        CrossLimitCondition(
            name="n",
            numerator="a",
            denominator="b",
            minimum=Q(2.0, ONE),
            maximum=Q(1.0, ONE),
        )


def test_operands_of_different_dimensions_are_a_loud_failure() -> None:
    """Not UNKNOWN: a resistance over a temperature is not a missing value.

    UNKNOWN means nobody said; this means somebody said something that cannot
    be what the condition is about, and collapsing the two would hide a
    specification error inside an honest verdict.
    """
    with pytest.raises(ModelValidityError):
        assess(
            ceiling(),
            {
                "reference_temperature": Q(10.0, "ohm"),
                "maximum_temperature": Q(450.0, K),
            },
        )


def test_a_zero_denominator_is_a_loud_failure() -> None:
    """The ratio does not exist, and an infinity nobody computed is worse."""
    with pytest.raises(ModelValidityError):
        assess(
            ceiling(),
            {
                "reference_temperature": Q(293.15, K),
                "maximum_temperature": Q(0.0, K),
            },
        )


# =====================================================================
# It travels
# =====================================================================

def test_a_cross_limit_condition_round_trips() -> None:
    condition = ceiling(
        minimum=Q(0.1, ONE),
        minimum_inclusive=False,
        description="a reference below its own ceiling",
    )
    assert CrossLimitCondition.from_dict(condition.to_dict()) == condition


def test_a_domain_carrying_one_round_trips() -> None:
    domain = ValidityDomain(
        conditions=(
            RangeCondition(name="temperature", minimum=Q(200.0, K)),
            ceiling(),
            CategoryCondition(name="phase", allowed=frozenset({"solid"})),
            FlagCondition(name="steady_state", expected=True),
        ),
        description="every condition type at once",
    )
    restored = ValidityDomain.from_dict(domain.to_dict())
    assert restored == domain

    context = {
        "temperature": Q(300.0, K),
        "reference_temperature": Q(293.15, K),
        "maximum_temperature": Q(450.0, K),
        "phase": "solid",
        "steady_state": True,
    }
    assert restored.assess(context) == domain.assess(context)
    assert restored.assess(context).status is ValidityStatus.IN_DOMAIN


def test_the_decoder_refuses_an_unknown_schema() -> None:
    payload = ceiling().to_dict()
    payload["schema"] = "not_a_condition/1"
    with pytest.raises(ModelValidityError):
        ValidityDomain.from_dict(
            {
                "schema": ValidityDomain(
                    conditions=(ceiling(),)
                ).to_dict()["schema"],
                "conditions": [payload],
                "description": "",
            }
        )


# =====================================================================
# The other three types still read exactly one key
# =====================================================================

def test_every_condition_type_evaluates_against_a_context() -> None:
    """``assess`` reads through ``evaluate_in`` now, so all four implement it.

    The three single-key types implement it as exactly the lookup ``assess``
    used to do inline, which is why nothing about them changed.
    """
    context = {
        "temperature": Q(300.0, K),
        "phase": "solid",
        "steady_state": True,
    }
    for condition in (
        RangeCondition(name="temperature", minimum=Q(200.0, K)),
        CategoryCondition(name="phase", allowed=frozenset({"solid"})),
        FlagCondition(name="steady_state", expected=True),
    ):
        assert condition.evaluate_in(context) is ValidityStatus.IN_DOMAIN
        assert (
            condition.evaluate_in(context)
            is condition.evaluate(context.get(condition.name))
        )
        assert condition.evaluate_in({}) is ValidityStatus.UNKNOWN
