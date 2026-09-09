"""A scientific record must not be able to contradict itself, or move.

THREE DEFECTS
-------------
**A validity assessment could disagree with its own conditions.**
``ValidityAssessment(status=IN_DOMAIN, violated=("biot_number",))`` constructed
happily: the model is applicable, and here is the bound it broke. Three more of
the same shape were reachable, including the quiet one --
``status=IN_DOMAIN`` over three empty lists, which is the strongest claim in
the vocabulary awarded for evaluating nothing.

The rule that resolves it already existed and was **written out three times**:
in ``ValidityDomain.assess``, in the credibility boundary's
``classify_assessment``, and again in a domain's coupling combiner. The
boundary's copy existed *because* the core did not enforce it. Three statements
of one rule is three chances to drift, invisibly, because each copy looks
correct alone.

**Eight frozen records still had mutable containers.** ``frozen=True`` protects
the attribute, not the object behind it. An audit over every frozen dataclass
in the core found 24 container fields, 16 already routed through ``freeze`` and
8 merely copied -- among them ``BoundaryCondition.coefficients``, which is the
physics of a boundary condition.

**An initial condition could start at 5 volts.** ``time`` was checked with
``isinstance(Quantity)``, which says "this carries a unit" and not "this is a
time" -- and the instant a state is declared at is the origin every later
instant is measured from.

WHY ONE MODULE
--------------
Each is a record that could hold a state its own contents deny. The fix in
every case is to make the invalid state unconstructible rather than to detect
it downstream.
"""

from __future__ import annotations

import dataclasses

import pytest

from src.engcore.mcp.evidence import classify_assessment, combine_assessments
from src.engcore.scientific.composition.conversion import ConversionOutcome
from src.engcore.scientific.errors import (
    InvalidScientificProblem,
    ModelValidityError,
    UnitCompatibilityError,
)
from src.engcore.scientific.ir.conditions import (
    BoundaryCondition,
    BoundaryKind,
    InitialCondition,
)
from src.engcore.scientific.models.definition import (
    UnknownCondition,
    UnknownReason,
    ValidityAssessment,
    ValidityStatus,
    classify_conditions,
)
from src.engcore.scientific.units.quantity import Quantity

NOT_SUPPLIED = UnknownReason.NOT_SUPPLIED


def _unknown(*names: str) -> tuple[UnknownCondition, ...]:
    return tuple(
        UnknownCondition(name=name, reason=NOT_SUPPLIED) for name in names
    )


# ===================================================================== C1


@pytest.mark.parametrize(
    "status,fields,why",
    [
        (
            ValidityStatus.IN_DOMAIN,
            {"violated": ("biot_number",)},
            "applicable, and here is the bound it broke",
        ),
        (
            ValidityStatus.IN_DOMAIN,
            {"unknown": ("biot_number",), "unknown_reasons": _unknown("biot_number")},
            "applicable, with a condition nobody could evaluate",
        ),
        (
            ValidityStatus.IN_DOMAIN,
            {},
            "applicable, having evaluated nothing at all",
        ),
        (
            ValidityStatus.IN_DOMAIN,
            {"satisfied": ("a",), "violated": ("b",)},
            "one condition held, so never mind the one that did not",
        ),
        (
            ValidityStatus.UNKNOWN,
            {"violated": ("biot_number",)},
            "a violation reported as a gap",
        ),
        (
            ValidityStatus.UNKNOWN,
            {"satisfied": ("biot_number",)},
            "everything evaluated and held, reported as unknown",
        ),
        (
            ValidityStatus.OUTSIDE_VALIDATED_DOMAIN,
            {"satisfied": ("biot_number",)},
            "outside the domain, with nothing violated",
        ),
        (
            ValidityStatus.OUTSIDE_VALIDATED_DOMAIN,
            {},
            "outside the domain, having evaluated nothing",
        ),
        (
            ValidityStatus.OUTSIDE_VALIDATED_DOMAIN,
            {"unknown": ("b",), "unknown_reasons": _unknown("b")},
            "a finding claimed from a condition nobody could read",
        ),
    ],
)
def test_a_contradictory_validity_assessment_cannot_be_constructed(
    status, fields, why
):
    """Every contradiction the classification rule can express, refused.

    Enumerated rather than sampled. The rule has four branches and three
    statuses, and a check that exercised one contradiction would leave the
    others reachable -- which is exactly how the original defect survived: the
    boundary caught IN_DOMAIN-over-violated and nothing else looked at the rest.
    """
    with pytest.raises(ModelValidityError) as raised:
        ValidityAssessment(status=status, **fields)
    assert "contradict" in str(raised.value), why


@pytest.mark.parametrize(
    "status,fields",
    [
        (ValidityStatus.IN_DOMAIN, {"satisfied": ("a", "b")}),
        (ValidityStatus.OUTSIDE_VALIDATED_DOMAIN, {"violated": ("a",)}),
        (
            ValidityStatus.OUTSIDE_VALIDATED_DOMAIN,
            {"satisfied": ("a",), "violated": ("b",)},
        ),
        (
            ValidityStatus.UNKNOWN,
            {"unknown": ("a",), "unknown_reasons": _unknown("a")},
        ),
        (
            ValidityStatus.UNKNOWN,
            {
                "satisfied": ("a",),
                "unknown": ("b",),
                "unknown_reasons": _unknown("b"),
            },
        ),
        # A domain with NO CONDITIONS. Three empty lists and UNKNOWN, and this
        # one is legitimate: `ValidityDomain.assess` returns exactly it, and
        # `electrical.dc.kcl` is a real model with that domain. Absence of
        # declared limits is not evidence of unlimited validity.
        (ValidityStatus.UNKNOWN, {}),
    ],
)
def test_every_coherent_assessment_still_constructs(status, fields):
    """The half a refusal this strict has to keep proving.

    A guard that refused the legitimate records too would be a breakage, and it
    would be invisible in a suite that only tested refusals.
    """
    assessment = ValidityAssessment(status=status, **fields)
    assert assessment.status is status
    assert assessment.implied_status is status


def test_the_classification_rule_is_stated_once_and_the_layers_agree():
    """Three copies became one, and the delegation is asserted rather than read.

    `classify_assessment` is the credibility boundary's entry point and is kept
    for its callers; it must now be the CORE's rule, not a second opinion about
    it. Checked over every combination of empty and non-empty lists, so a
    re-divergence in any branch fails here.
    """
    for satisfied in ((), ("s",)):
        for violated in ((), ("v",)):
            for unknown in ((), ("u",)):
                expected = classify_conditions(
                    satisfied=satisfied, violated=violated, unknown=unknown
                )
                assessment = ValidityAssessment(
                    status=expected,
                    satisfied=satisfied,
                    violated=violated,
                    unknown=unknown,
                    unknown_reasons=_unknown(*unknown),
                )
                assert assessment.implied_status is expected
                assert classify_assessment(assessment) is expected

    # And the rule itself, spelled out, so a silent reordering of the branches
    # is a failure here rather than a different verdict somewhere downstream.
    assert classify_conditions(satisfied=("s",), violated=("v",), unknown=("u",)) \
        is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert classify_conditions(satisfied=("s",), violated=(), unknown=("u",)) \
        is ValidityStatus.UNKNOWN
    assert classify_conditions(satisfied=("s",), violated=(), unknown=()) \
        is ValidityStatus.IN_DOMAIN
    assert classify_conditions(satisfied=(), violated=(), unknown=()) \
        is ValidityStatus.UNKNOWN


def test_combining_assessments_produces_a_coherent_record():
    """The combiner used to build a contradictory placeholder on the way.

    It constructed `status=UNKNOWN` beside a non-empty `violated`, read the
    real status off that record and rebuilt. The placeholder was itself the
    thing this round refuses; it existed only because nothing stopped it.
    """
    combined = combine_assessments([
        ValidityAssessment(status=ValidityStatus.IN_DOMAIN, satisfied=("a",)),
        ValidityAssessment(
            status=ValidityStatus.OUTSIDE_VALIDATED_DOMAIN, violated=("b",)
        ),
    ])
    assert combined.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert combined.implied_status is combined.status
    assert combined.violated == ("b",)

    # An empty sequence is UNKNOWN, not IN_DOMAIN: nothing was assessed.
    assert combine_assessments([]).status is ValidityStatus.UNKNOWN


def test_an_unrecognised_status_is_refused_at_construction():
    """A status no branch understands would be read as 'nothing argues against'."""
    with pytest.raises(ModelValidityError):
        ValidityAssessment(status="probably_fine")
    with pytest.raises(ModelValidityError):
        ValidityAssessment(status="")

    # A recognised status given as a bare string is still normalised, so a
    # serialized record loads and `to_dict` does not crash on `.value`.
    assessment = ValidityAssessment(status="in_domain", satisfied=("a",))
    assert assessment.status is ValidityStatus.IN_DOMAIN
    assert assessment.to_dict()["status"] == "in_domain"


def test_a_contradictory_assessment_cannot_be_smuggled_in_through_a_payload():
    """`from_dict` calls the constructor, so the wire gets no exemption."""
    payload = ValidityAssessment(
        status=ValidityStatus.OUTSIDE_VALIDATED_DOMAIN, violated=("b",)
    ).to_dict()
    payload["status"] = "in_domain"
    with pytest.raises(ModelValidityError):
        ValidityAssessment.from_dict(payload)


def test_the_unknown_reason_coverage_invariant_is_untouched():
    """The landed UNKNOWN-reason channel still holds beside the new rule."""
    with pytest.raises(ModelValidityError):
        ValidityAssessment(status=ValidityStatus.UNKNOWN, unknown=("a",))
    with pytest.raises(ModelValidityError):
        ValidityAssessment(
            status=ValidityStatus.UNKNOWN,
            unknown=("a",),
            unknown_reasons=_unknown("a", "b"),
        )


# ===================================================================== C2


def test_boundary_condition_coefficients_cannot_be_mutated():
    """The physics of a boundary condition, made unwritable.

    A Robin condition's film coefficient IS the boundary. Editing it after
    construction changes what problem was posed, on a record every downstream
    consumer treats as the statement of that problem.
    """
    boundary = BoundaryCondition(
        name="wall",
        variable="T",
        kind=BoundaryKind.ROBIN,
        region="outer",
        coefficients={"h": Quantity(5.0, "W/m^2/K")},
    )
    with pytest.raises(TypeError):
        boundary.coefficients["h"] = Quantity(9999.0, "W/m^2/K")
    with pytest.raises(TypeError):
        boundary.coefficients.update({"h": Quantity(9999.0, "W/m^2/K")})
    with pytest.raises(TypeError):
        boundary.coefficients.pop("h")
    assert boundary.coefficients["h"] == Quantity(5.0, "W/m^2/K")

    # The payload is still the caller's to edit, and round-trips.
    payload = boundary.to_dict()
    payload["coefficients"]["h"]["magnitude"] = 1.0
    assert boundary.coefficients["h"] == Quantity(5.0, "W/m^2/K")
    assert BoundaryCondition.from_dict(boundary.to_dict()) == boundary


def test_no_frozen_scientific_record_still_holds_a_mutable_container():
    """The sweep, kept honest.

    An audit that ran once and was written up in a commit message goes stale
    the first time somebody adds a field. This walks the core the way the audit
    did and fails on a new mutable container rather than waiting for one to be
    mutated.

    Classification, applied when this fails: harden a field that is scientific
    trust-boundary state; exempt one that is a deliberate cache or runtime
    machinery by adding it below with the reason. The exemption set is empty
    today, which is the point -- every container in the core is currently
    trust-boundary state.
    """
    import ast
    import pathlib
    import re

    core = pathlib.Path(__file__).resolve().parent.parent / "src" / "engcore" / "scientific"
    container = re.compile(r"\b(Mapping|MutableMapping|dict|Dict|list|List|set|Set)\b")

    #: field -> why it may stay mutable. Empty, deliberately.
    EXEMPT: dict[tuple[str, str], str] = {}

    offenders: list[str] = []
    checked = 0
    for path in sorted(core.rglob("*.py")):
        tree = ast.parse(path.read_bytes().decode("utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if not any(
                isinstance(d, ast.Call)
                and getattr(d.func, "attr", getattr(d.func, "id", "")) == "dataclass"
                and any(
                    kw.arg == "frozen"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is True
                    for kw in d.keywords
                )
                for d in node.decorator_list
            ):
                continue
            post_init = next(
                (
                    n for n in node.body
                    if isinstance(n, ast.FunctionDef) and n.name == "__post_init__"
                ),
                None,
            )
            body = ast.unparse(post_init) if post_init else ""
            for stmt in node.body:
                if not isinstance(stmt, ast.AnnAssign):
                    continue
                if not isinstance(stmt.target, ast.Name):
                    continue
                field = stmt.target.id
                annotation = ast.unparse(stmt.annotation)
                if annotation.startswith("tuple") or not container.search(annotation):
                    continue
                checked += 1
                if (node.name, field) in EXEMPT:
                    continue
                if f"'{field}', freeze(" not in body:
                    offenders.append(f"{node.name}.{field}: {annotation}")

    assert checked >= 24, (
        f"the walk found only {checked} container fields on frozen records; it "
        f"has stopped reading the core and would pass over anything"
    )
    assert offenders == [], (
        "frozen scientific records with a container field that is copied but "
        "not frozen:\n  " + "\n  ".join(offenders) + "\n\n"
        "frozen=True protects the attribute, not the object behind it. Route "
        "the field through results.immutable.freeze, or add it to EXEMPT above "
        "with the reason it is deliberate internal state."
    )


@pytest.mark.parametrize(
    "build,field",
    [
        (
            lambda: ConversionOutcome(
                status=ValidityStatus.IN_DOMAIN,
                value=Quantity(0.9, "joule"),
                losses={"heat": Quantity(0.1, "joule")},
            ),
            "losses",
        ),
        (
            lambda: BoundaryCondition(
                name="w", variable="T", kind=BoundaryKind.ROBIN, region="r",
                coefficients={"h": Quantity(5.0, "W/m^2/K")},
            ),
            "coefficients",
        ),
    ],
)
def test_the_hardened_records_refuse_mutation_in_practice(build, field):
    """A static walk proves the call is there; this proves it took effect."""
    record = build()
    container = getattr(record, field)
    assert container, "the fixture must be non-empty or this proves nothing"
    key = next(iter(container))
    with pytest.raises(TypeError):
        container[key] = Quantity(999.0, "joule")


# ===================================================================== C3


def test_an_initial_condition_must_start_at_a_time():
    """`time = 5 volt` was accepted, and would be the origin of the march."""
    with pytest.raises(UnitCompatibilityError):
        InitialCondition(
            variable="T", value=Quantity(300.0, "K"), time=Quantity(5.0, "volt")
        )
    with pytest.raises(UnitCompatibilityError):
        InitialCondition(
            variable="T",
            value=Quantity(300.0, "K"),
            time=Quantity(5.0, "dimensionless"),
        )
    with pytest.raises(UnitCompatibilityError):
        InitialCondition(
            variable="T", value=Quantity(300.0, "K"), time=Quantity(5.0, "meter")
        )


@pytest.mark.parametrize("unit", ["second", "s", "millisecond", "hour", "minute", "day"])
def test_any_unit_of_time_is_accepted(unit):
    """Compatible units, not one spelling of one unit.

    A check written against `"second"` by string would refuse an hour, which is
    a time by every standard that matters.
    """
    condition = InitialCondition(
        variable="T", value=Quantity(300.0, "K"), time=Quantity(5.0, unit)
    )
    assert condition.time is not None
    assert condition.time.is_compatible_with("second")


def test_a_condition_with_no_declared_time_is_still_valid():
    """`None` is a real answer: not every initial condition names an instant."""
    condition = InitialCondition(variable="T", value=Quantity(300.0, "K"))
    assert condition.time is None
    assert condition.to_dict()["time"] is None
    assert InitialCondition.from_dict(condition.to_dict()) == condition


def test_the_time_check_survives_the_wire():
    """A payload gets no exemption from a dimensional rule."""
    condition = InitialCondition(
        variable="T", value=Quantity(300.0, "K"), time=Quantity(5.0, "second")
    )
    payload = condition.to_dict()
    assert InitialCondition.from_dict(payload) == condition

    payload["time"] = Quantity(5.0, "volt").to_dict()
    with pytest.raises(UnitCompatibilityError):
        InitialCondition.from_dict(payload)


def test_a_non_quantity_time_is_still_refused_for_its_own_reason():
    """The type check and the dimension check are different refusals."""
    with pytest.raises(InvalidScientificProblem):
        InitialCondition(variable="T", value=Quantity(300.0, "K"), time=5.0)
    with pytest.raises(InvalidScientificProblem):
        InitialCondition(variable="T", value=Quantity(300.0, "K"), time="5 s")
