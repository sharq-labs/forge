"""GATE 4 — UNKNOWN carried four meanings and could not say which.

THE DEFECT.

    c = RangeCondition(name="cell_peclet", maximum=Quantity(2.0, "dimensionless"))
    c.evaluate(None)                      -> UNKNOWN
    c.evaluate(np.array([0.1, 9.0, 0.2])) -> UNKNOWN   <- identical

Nobody supplied the input, and the input arrived in a shape the core cannot
read. Two different situations, one symbol, and `derive_verdict` maps both to
INSUFFICIENT_EVIDENCE. The external verdict stays honest — it degrades to "I do
not know" rather than lying — but the reason is lost, so no consumer can act on
it and no audit can tell a core limitation from a missing declaration.

It is also the ceiling on the universality claim: because a field-valued
condition returns UNKNOWN *silently*, a domain built on fields can never reach
SUPPORTED however good its physics, and nothing anywhere counts how often that
happens.

WHAT THIS GATE DOES AND DOES NOT DO. It makes the gap visible and named. It
does not close it: no field, mesh, tensor or topology support is added, and no
`requires`/prerequisite primitive is added — the reason channel has to exist
before a prerequisite mechanism has anywhere to record why it skipped
something. `derive_verdict`'s rules are unchanged; UNKNOWN still produces
INSUFFICIENT_EVIDENCE. Only the explanation gets richer.
"""

from __future__ import annotations

import numpy as np
import pytest

from engcore.scientific.errors import ModelValidityError, ScientificCoreError
from engcore.scientific.models.definition import (
    CategoryCondition,
    FlagCondition,
    RangeCondition,
    UnknownCondition,
    UnknownReason,
    ValidityAssessment,
    ValidityDomain,
    ValidityStatus,
)
from engcore.scientific.units.quantity import Quantity


def peclet() -> RangeCondition:
    return RangeCondition(
        name="cell_peclet", maximum=Quantity(2.0, "dimensionless")
    )


def test_a_missing_input_and_a_field_valued_one_are_no_longer_the_same_answer():
    """The reproduction. Both are still UNKNOWN; they no longer say the same thing."""
    condition = peclet()
    field = np.array([0.1, 9.0, 0.2])

    # The status is deliberately unchanged: this gate does not touch the
    # three-value model or derive_verdict's rules.
    assert condition.evaluate(None) is ValidityStatus.UNKNOWN
    assert condition.evaluate(field) is ValidityStatus.UNKNOWN

    # The reason is what changed.
    assert condition.explain_in({}) is UnknownReason.NOT_SUPPLIED
    assert (
        condition.explain_in({"cell_peclet": field})
        is UnknownReason.UNREADABLE_SHAPE
    )


def test_a_domain_records_why_each_condition_could_not_be_assessed():
    """Derived at the one place that knows both the condition and the context."""
    domain = ValidityDomain(
        conditions=(
            peclet(),
            RangeCondition(name="biot_number", maximum=Quantity(0.1, "dimensionless")),
        )
    )
    assessment = domain.assess({"cell_peclet": np.array([1.0, 2.0])})

    assert assessment.status is ValidityStatus.UNKNOWN
    assert set(assessment.unknown) == {"cell_peclet", "biot_number"}
    assert assessment.reason_for("cell_peclet") is UnknownReason.UNREADABLE_SHAPE
    assert assessment.reason_for("biot_number") is UnknownReason.NOT_SUPPLIED
    assert assessment.reason_for("something_else") is None
    assert assessment.actionable_unknowns == ("biot_number",)
    assert assessment.unknown_because(UnknownReason.UNREADABLE_SHAPE) == (
        "cell_peclet",
    )


def test_every_condition_type_answers_the_question_the_same_way():
    """The four core condition types, absent and unreadable."""
    cases = (
        (peclet(), "cell_peclet", "not a quantity"),
        (CategoryCondition(name="phase", allowed=frozenset({"liquid"})), "phase", 7),
        (FlagCondition(name="steady_state", expected=True), "steady_state", "yes"),
    )
    for condition, key, unreadable in cases:
        assert condition.explain_in({}) is UnknownReason.NOT_SUPPLIED, key
        assert (
            condition.explain_in({key: unreadable})
            is UnknownReason.UNREADABLE_SHAPE
        ), key


def test_a_declared_zero_is_supplied_and_not_missing():
    """Absence is `is None`, never truthiness.

    A declared `0.0`, an empty string and `False` are all values somebody
    supplied. Reading them as "missing" would report a caller who declared
    something as a caller who declared nothing — and would send repair guidance
    to ask for a declaration that is already there.
    """
    flag = FlagCondition(name="steady_state", expected=True)
    # False is supplied, and it is readable: it is a violation, not a gap.
    assert flag.evaluate_in({"steady_state": False}) is (
        ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    )
    # 0.0 is supplied but is not a Quantity, so it is a shape problem and not
    # an omission.
    assert (
        peclet().explain_in({"cell_peclet": 0.0}) is UnknownReason.UNREADABLE_SHAPE
    )


def test_an_unknown_with_no_reason_cannot_be_constructed():
    """The invariant. A name on its own is what this gate exists to remove."""
    with pytest.raises(ModelValidityError, match="with no reason"):
        ValidityAssessment(
            status=ValidityStatus.UNKNOWN, unknown=("biot_number",)
        )


def test_a_reason_outside_the_declared_situations_is_refused_not_defaulted():
    """Refused rather than defaulted — defaulting is how this defect started."""
    with pytest.raises(ModelValidityError, match="not one of the declared"):
        UnknownCondition(name="biot_number", reason="because")
    with pytest.raises(ModelValidityError, match="not one of the declared"):
        UnknownCondition(name="biot_number", reason="")


def test_reasons_must_correspond_exactly_to_the_unknown_conditions():
    """Not a parallel list that may drift: a total, one-to-one correspondence."""
    supplied = UnknownCondition(
        name="biot_number", reason=UnknownReason.NOT_SUPPLIED
    )
    # explaining something that is not unknown
    with pytest.raises(ModelValidityError, match="does not report as unknown"):
        ValidityAssessment(status=ValidityStatus.UNKNOWN, unknown=(), unknown_reasons=(supplied,))
    # two reasons for one condition
    with pytest.raises(ModelValidityError, match="more than one reason"):
        ValidityAssessment(
            status=ValidityStatus.UNKNOWN,
            unknown=("biot_number",),
            unknown_reasons=(
                supplied,
                UnknownCondition(
                    name="biot_number", reason=UnknownReason.UNREADABLE_SHAPE
                ),
            ),
        )
    # a bare string is exactly the thing being replaced
    with pytest.raises(ModelValidityError, match="not an UnknownCondition"):
        ValidityAssessment(
            status=ValidityStatus.UNKNOWN,
            unknown=("biot_number",),
            unknown_reasons=("biot_number",),
        )


def test_the_reason_survives_serialization_and_a_v1_record_cannot_be_guessed():
    """A stored assessment carries its reasons, and an old one is refused.

    The schema is bumped to /2 because a /1 record with unknown conditions has
    no field to say why, and "not recorded" is not one of the four situations.
    Defaulting it would put the defect straight back. A /1 record with nothing
    unknown has nothing to explain and still reads.
    """
    domain = ValidityDomain(conditions=(peclet(),))
    assessment = domain.assess({"cell_peclet": np.array([1.0])})
    payload = assessment.to_dict()
    assert payload["schema"].endswith("/2")

    restored = ValidityAssessment.from_dict(payload)
    assert restored.reason_for("cell_peclet") is UnknownReason.UNREADABLE_SHAPE
    assert restored == assessment

    legacy = {
        "schema": "validity_assessment/1",
        "status": "unknown",
        "satisfied": [],
        "violated": [],
        "unknown": ["cell_peclet"],
    }
    with pytest.raises(ScientificCoreError, match="no field to say why"):
        ValidityAssessment.from_dict(legacy)

    legacy_empty = dict(legacy, unknown=[], status="in_domain", satisfied=["x"])
    assert ValidityAssessment.from_dict(legacy_empty).unknown == ()


def test_the_verdict_rules_did_not_change():
    """UNKNOWN still produces INSUFFICIENT_EVIDENCE. Only the reason is richer."""
    from engcore.mcp.evidence import (
        CredibilityVerdict,
        ModelValidityRecord,
        derive_verdict,
    )
    from engcore.scientific.results.validation import (
        ValidationCheck,
        ValidationLevel,
        ValidationOutcome,
    )

    record = ModelValidityRecord(
        model_id="thermal.lumped",
        version="1.0",
        assessment=ValidityAssessment(
            status=ValidityStatus.UNKNOWN,
            unknown=("cell_peclet",),
            unknown_reasons=(
                UnknownCondition(
                    name="cell_peclet", reason=UnknownReason.UNREADABLE_SHAPE
                ),
            ),
        ),
    )
    check = ValidationCheck(
        name="analytic_verification",
        outcome=ValidationOutcome.PASS,
        establishes=ValidationLevel.ANALYTICALLY_VERIFIED,
        residual=1e-9,
        tolerance=1e-6,
    )
    assert derive_verdict(validity=[record], validation=[check]) is (
        CredibilityVerdict.INSUFFICIENT_EVIDENCE
    )


# ---------------------------------------------------------------------
# The second consumer: repair guidance
# ---------------------------------------------------------------------


def test_repair_guidance_separates_declare_this_from_cannot_be_assessed():
    """The distinction repair.py could not previously make.

    Before reasons, `repair.py` said nothing at all about an unknown condition
    — its only use of the word "unknown" was about unrecognised condition
    NAMES, which is a different thing. There was nothing useful it could say,
    because every unknown arrived as a bare name.
    """
    from engcore.domains.repair import (
        actionable_declarations,
        unassessable_guidance,
    )

    assessment = ValidityAssessment(
        status=ValidityStatus.UNKNOWN,
        unknown=("biot_number", "cell_peclet", "fourier_number", "gated"),
        unknown_reasons=(
            UnknownCondition(
                name="biot_number", reason=UnknownReason.NOT_SUPPLIED
            ),
            UnknownCondition(
                name="cell_peclet", reason=UnknownReason.UNREADABLE_SHAPE
            ),
            UnknownCondition(
                name="fourier_number", reason=UnknownReason.CONSERVATIVE_SCREEN
            ),
            UnknownCondition(
                name="gated", reason=UnknownReason.PREREQUISITE_NOT_ESTABLISHED
            ),
        ),
    )
    guidance = {g.condition: g for g in unassessable_guidance(assessment)}

    assert guidance["biot_number"].actionable
    assert "declare biot_number" in guidance["biot_number"].guidance

    # The other three are not things a caller can declare their way out of,
    # and each says why rather than all three saying nothing.
    assert not guidance["cell_peclet"].actionable
    assert "the gap is in the core" in guidance["cell_peclet"].guidance
    assert not guidance["fourier_number"].actionable
    assert "not shown wrong" in guidance["fourier_number"].guidance
    assert not guidance["gated"].actionable
    assert "prerequisite" in guidance["gated"].guidance

    assert actionable_declarations(assessment) == ("biot_number",)


def test_repair_guidance_never_fabricates_a_number_for_an_unassessed_condition():
    """A condition never assessed has no bound it failed and no value to move.

    Fabricating a hint for one would be the most damaging thing this module
    could do, because it would look exactly like the hints that are real.
    Asserted structurally: the guidance record has no field a number could
    occupy, and every reason produces prose only.
    """
    import dataclasses

    from engcore.domains.repair import Unassessable, unassessable_guidance

    fields = {f.name for f in dataclasses.fields(Unassessable)}
    assert fields == {"condition", "reason", "actionable", "guidance"}

    for reason in UnknownReason:
        assessment = ValidityAssessment(
            status=ValidityStatus.UNKNOWN,
            unknown=("c",),
            unknown_reasons=(UnknownCondition(name="c", reason=reason),),
        )
        (item,) = unassessable_guidance(assessment)
        assert item.reason is reason
        assert isinstance(item.guidance, str) and item.guidance


def test_every_declared_reason_has_guidance_written_for_it():
    """A new situation must fail loudly here, not fall through to a default."""
    from engcore.domains.repair import _GUIDANCE

    assert set(_GUIDANCE) == set(UnknownReason), (
        "a declared UnknownReason has no guidance sentence, so a consumer "
        "would be told nothing about a situation somebody thought worth naming"
    )
