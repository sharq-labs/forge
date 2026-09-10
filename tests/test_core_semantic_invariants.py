"""Public contracts of the current Core, as properties rather than examples.

Every test here came from an audit of the *current* production code, and each
one is written over a derived population rather than a hand-written list
wherever the population can be derived. A guard over the three records somebody
remembered is a guard that stops covering the fourth.

Four proven defects are pinned here, each with the reproduction that found it:

* a result could declare one model at two versions and carry a SINGLE validity
  verdict answering for both;
* ``FlagCondition(expected="false")`` required the flag be **True**, and the
  inclusive-endpoint flags were not checked at all, so an exclusive bound
  behaved as an inclusive one;
* two registries wrote an explicit versioned schema and read anything;
* ``ScientificDataReference(count=1.9)`` silently declared 1 value and compared
  equal to the reference that honestly declared 1.

And three findings that are **not** defects are pinned too, because an audit
that only records what it changed leaves the next reader to redo it:
``is_usable`` deliberately excludes validity, ``ScientificVariable`` represents
kind combinations that its only consumer refuses, and exact-boundary equality
across unit spellings is a floating-point property that no comparison basis
removes.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import pathlib

import pytest

from src.engcore.scientific.errors import ScientificCoreError
from src.engcore.scientific.ir.values import IntegerValue
from src.engcore.scientific.ir.variables import ScientificVariable, VariableKind
from src.engcore.scientific.models.definition import (
    CrossLimitCondition,
    FlagCondition,
    RangeCondition,
    UnknownCondition,
    UnknownReason,
    ValidityAssessment,
    ValidityStatus,
)
from src.engcore.scientific.models.registry import ModelRegistry
from src.engcore.scientific.realizations.registry import RealizationRegistry
from src.engcore.scientific.results.data_reference import ScientificDataReference
from src.engcore.scientific.results.provenance import ProvenanceRecord
from src.engcore.scientific.results.result import ScientificResult
from src.engcore.scientific.solvers.protocol import SolverSettings
from src.engcore.scientific.results.uncertainty import (
    Uncertainty,
    UncertaintyKind,
)
from src.engcore.scientific.results.validation import (
    ValidationOutcome,
    ValidationReport,
)
from src.engcore.scientific.units.quantity import Quantity, base_unit

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Values that look like a boolean to a human and are not one to Python. Two of
#: them are *truthy while reading as false*, which is the direction that
#: inverts a declaration rather than merely mistyping it.
NOT_BOOLEANS = ("false", "true", 0, 1, [], (), None, 1.0, object())
#: Stable ids. `repr` of the sentinel carries its memory address, which
#: differs per xdist worker and makes collection disagree between them.
NOT_BOOLEAN_IDS = ("str_false", "str_true", "int_0", "int_1", "empty_list",
                   "empty_tuple", "none", "float_1", "object")

DIGEST = "a" * 64


def _dimensionless(value: float) -> Quantity:
    return Quantity(value, "dimensionless")


def _assessment(status: ValidityStatus = ValidityStatus.IN_DOMAIN) -> ValidityAssessment:
    """An assessment whose conditions imply the status it reports.

    `ValidityAssessment` refuses a status contradicting its own condition
    lists, so a test fixture has to carry the evidence for the verdict it
    names rather than asserting one.
    """
    if status is ValidityStatus.IN_DOMAIN:
        return ValidityAssessment(status=status, satisfied=("c",))
    if status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN:
        return ValidityAssessment(status=status, violated=("c",))
    return ValidityAssessment(
        status=status,
        unknown=("c",),
        unknown_reasons=(
            UnknownCondition(name="c", reason=UnknownReason.NOT_SUPPLIED),
        ),
    )


def _provenance(models: tuple[tuple[str, str], ...]) -> ProvenanceRecord:
    return ProvenanceRecord(
        run_id="run", software_version="0", git_commit="0", models=models
    )


# =====================================================================
# Versioned validity identity
# =====================================================================


def test_a_result_cannot_declare_one_model_at_two_versions():
    """One verdict may not answer for two claims.

    ``models`` carries ``(model_id, version)`` pairs and every validity
    accessor is keyed by model id alone. A result declaring ``m@1`` and ``m@2``
    therefore had ONE validity entry standing for both: ``validity_of("m")``
    returned a single status, ``unassessed_models`` reported no gap, and the
    qualified key ``"m@1"`` was refused as naming a model the result does not
    declare. Two versions of a model are two claims.
    """
    models = (("same-model", "1"), ("same-model", "2"))
    with pytest.raises(ScientificCoreError) as excinfo:
        ScientificResult(
            result_id="res",
            values={},
            provenance=_provenance(models),
            problem_id="p",
            models=models,
            validity={"same-model": _assessment()},
        )
    message = str(excinfo.value)
    assert "two versions" in message
    assert "'1'" in message and "'2'" in message


def test_one_version_of_a_model_still_carries_its_verdict():
    """The refusal above must not cost the case it exists to protect."""
    result = ScientificResult(
        result_id="res",
        values={},
        provenance=_provenance((("m", "1"),)),
        problem_id="p",
        models=(("m", "1"),),
        validity={"m": _assessment()},
    )
    assert result.validity_of("m").status is ValidityStatus.IN_DOMAIN
    assert result.unassessed_models == ()


def test_the_same_model_listed_twice_is_not_ambiguous():
    """One claim written down twice is not two claims.

    The refusal is about two VERSIONS, not about a repeated entry — narrowing
    it to exact duplicates would refuse a producer that lists a model twice
    while still admitting the ambiguity.
    """
    models = (("m", "1"), ("m", "1"))
    result = ScientificResult(
        result_id="res",
        values={},
        provenance=_provenance((("m", "1"),)),
        problem_id="p",
        models=models,
        validity={"m": _assessment()},
    )
    assert result.validity_of("m").status is ValidityStatus.IN_DOMAIN


def test_provenance_keeps_the_version_the_result_refuses_to_blur():
    """Where the asymmetry was, so a future edit cannot quietly close it here.

    ``ProvenanceRecord`` compares its models against binding keys with the
    version intact, and must go on doing so: the result refuses the ambiguous
    declaration precisely because provenance is the record that keeps
    versions apart.
    """
    provenance = _provenance((("m", "1"), ("m", "2")))
    assert provenance.models == (("m", "1"), ("m", "2"))


# =====================================================================
# Semantic flags are booleans or refusals
# =====================================================================


def _boolean_fields(record_type) -> tuple[str, ...]:
    """Every ``bool``-typed field of a record, derived from the dataclass.

    Derived so that a flag added later is covered without editing this file.
    That is not hypothetical here: ``conservative_screen`` was checked and the
    two endpoint flags beside it were not.
    """
    return tuple(
        field.name
        for field in dataclasses.fields(record_type)
        if field.type in ("bool", bool)
    )


BOOLEAN_CASES: list[tuple[str, object, str]] = []
for _type, _base in (
    (RangeCondition, dict(name="r", minimum=_dimensionless(0.0),
                          maximum=_dimensionless(1.0))),
    (CrossLimitCondition, dict(name="x", numerator="a", denominator="b",
                               minimum=_dimensionless(0.0),
                               maximum=_dimensionless(1.0))),
    (FlagCondition, dict(name="f")),
):
    for _field in _boolean_fields(_type):
        BOOLEAN_CASES.append((f"{_type.__name__}.{_field}", _type, _field))
    if not _boolean_fields(_type):  # pragma: no cover - a record lost its flags
        raise AssertionError(f"{_type.__name__} declares no boolean field")

_BASES = {
    RangeCondition: dict(name="r", minimum=_dimensionless(0.0),
                         maximum=_dimensionless(1.0)),
    CrossLimitCondition: dict(name="x", numerator="a", denominator="b",
                              minimum=_dimensionless(0.0),
                              maximum=_dimensionless(1.0)),
    FlagCondition: dict(name="f"),
}


@pytest.mark.parametrize("label,record_type,field", BOOLEAN_CASES,
                         ids=[c[0] for c in BOOLEAN_CASES])
@pytest.mark.parametrize("value", NOT_BOOLEANS, ids=NOT_BOOLEAN_IDS)
def test_a_semantic_flag_refuses_anything_that_is_not_a_boolean(
    label, record_type, field, value
):
    """Every boolean on every condition record, over every false-looking value.

    ``bool(value)`` is not a repair. ``bool("false")`` is ``True``, so the
    coercion this replaced turned a declaration into its opposite; the two
    candidate meanings of ``"false"`` are opposites, and there is nothing safe
    to guess between them.
    """
    with pytest.raises(ScientificCoreError):
        record_type(**{**_BASES[record_type], field: value})


@pytest.mark.parametrize("expected", [True, False])
def test_a_flag_condition_asks_for_the_value_it_was_given(expected):
    """The inversion, stated as the behaviour rather than as the type.

    ``expected="false"`` used to build a condition demanding the flag be True.
    A type check alone would not say that; this does.
    """
    condition = FlagCondition(name="f", expected=expected)
    assert condition.evaluate(expected) is ValidityStatus.IN_DOMAIN
    assert condition.evaluate(not expected) is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN


def test_an_exclusive_bound_stays_exclusive():
    """The decision the unchecked endpoint flags changed.

    A value sitting exactly on an exclusive maximum is outside it. With the
    flag stored as the string ``"false"`` — truthy — the bound closed and the
    same value was reported IN_DOMAIN.
    """
    exclusive = RangeCondition(
        name="r", minimum=_dimensionless(0.0), maximum=_dimensionless(1.0),
        maximum_inclusive=False,
    )
    inclusive = RangeCondition(
        name="r", minimum=_dimensionless(0.0), maximum=_dimensionless(1.0),
        maximum_inclusive=True,
    )
    at_bound = {"r": _dimensionless(1.0)}
    assert exclusive.evaluate_in(at_bound) is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert inclusive.evaluate_in(at_bound) is ValidityStatus.IN_DOMAIN


@pytest.mark.parametrize("value", ["false", 0, 1])
def test_the_constructor_and_the_reader_refuse_the_same_declaration(value):
    """The asymmetry that proved this was a defect and not a design.

    ``from_dict`` already refused a non-boolean with "a serialized scientific
    declaration is refused rather than guessed" while the constructor stored
    it. A record could be built in memory that this module's own reader would
    not accept, which is not a contract — it is two contracts.
    """
    payload = RangeCondition(
        name="r", minimum=_dimensionless(0.0), maximum=_dimensionless(1.0)
    ).to_dict()
    with pytest.raises(ScientificCoreError):
        RangeCondition.from_dict({**payload, "maximum_inclusive": value})
    with pytest.raises(ScientificCoreError):
        RangeCondition(
            name="r", minimum=_dimensionless(0.0), maximum=_dimensionless(1.0),
            maximum_inclusive=value,
        )


# =====================================================================
# Serialization: a writer that versions its payload reads that version
# =====================================================================

#: Readers that legitimately carry no schema of their own: they are nested
#: sub-records whose parent checks, and they emit no ``schema`` key. Derived
#: membership is asserted below rather than assumed — an entry here that
#: starts emitting a schema is a failure, not an exemption.
_NESTED_WITHOUT_SCHEMA = frozenset({
    "EntryClassification", "RouteComparison", "ExperimentBudget",
    "SolverSettings", "CheckpointStore", "CalibrationState",
})
_SCHEMA_CHECKERS = frozenset({"require_schema", "require_schema_any"})


def _readers_missing_a_schema_check() -> dict[str, str]:
    """Classes whose ``from_dict`` calls no schema checker, walked not listed."""
    found: dict[str, str] = {}
    for path in sorted((REPO_ROOT / "src" / "engcore").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_bytes().decode("utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for member in node.body:
                if not (isinstance(member, ast.FunctionDef)
                        and member.name == "from_dict"):
                    continue
                called = {
                    getattr(c.func, "id", None) or getattr(c.func, "attr", None)
                    for c in ast.walk(member) if isinstance(c, ast.Call)
                }
                # A reader passes if it delegates to the helper OR names the
                # key itself: `MultirotorStudyBinding` compares
                # `payload.get("schema")` by hand, which is the rule applied
                # rather than the helper called. The property is that the
                # schema is checked, not that one function does it.
                names_the_key = any(
                    isinstance(c, ast.Constant) and c.value == "schema"
                    for c in ast.walk(member)
                )
                if not (called & _SCHEMA_CHECKERS) and not names_the_key:
                    found[node.name] = path.relative_to(REPO_ROOT).as_posix()
    return found


def test_every_reader_that_writes_a_schema_also_checks_one():
    """Walked over the tree, so a new record cannot join the exceptions quietly.

    ``ModelRegistry`` and ``RealizationRegistry`` each wrote an explicit
    versioned schema and accepted any payload at all — garbage, missing, or a
    future version of their own family. 174 of the 183 readers here applied
    the rule; these two were the scientific-core exceptions, and a future
    shape read as the current one is exactly what a version exists to prevent.
    """
    missing = _readers_missing_a_schema_check()
    unexpected = {
        name: where for name, where in missing.items()
        if name not in _NESTED_WITHOUT_SCHEMA
    }
    assert unexpected == {}, (
        "these read a serialized record without checking the schema it "
        f"claims to be: {unexpected}"
    )


def test_the_nested_exemptions_really_are_nested():
    """An exemption that stops being true is a hole, so it is checked.

    Each name above is exempt because it emits no ``schema`` of its own and is
    read through a parent that does. If one starts emitting a schema, it has
    become a top-level record and the exemption must go.
    """
    still_missing = set(_readers_missing_a_schema_check())
    stale = sorted(_NESTED_WITHOUT_SCHEMA - still_missing)
    assert stale == [], (
        f"these no longer need an exemption and should be removed: {stale}"
    )


@pytest.mark.parametrize("registry_type", [ModelRegistry, RealizationRegistry])
def test_a_registry_refuses_a_schema_it_did_not_write(registry_type):
    """The behaviour behind the static walk, in all three directions."""
    payload = registry_type().to_dict()
    family = payload["schema"].split("/")[0]
    for broken in (
        {**payload, "schema": "garbage/999"},
        {key: value for key, value in payload.items() if key != "schema"},
        {**payload, "schema": f"{family}/99"},
    ):
        with pytest.raises(ScientificCoreError):
            registry_type.from_dict(broken)
    assert registry_type.from_dict(payload) is not None


# =====================================================================
# Identity-bearing integers
# =====================================================================


@pytest.mark.parametrize("value", [1.0, 1.2, 1.9, True, False, "1", "1.2"])
def test_a_declared_count_is_never_silently_coerced(value):
    """``int(value)`` truncated, and ``count`` is part of scientific equality.

    A reference declaring 1.9 values became one declaring 1 and compared EQUAL
    to the honest reference — the class docstring calls its equality "a
    scientific question and never a storage one". ``True`` became 1 on the
    same line, which is the distinction ``IntegerValue`` refuses bool to keep.
    """
    with pytest.raises(ScientificCoreError):
        ScientificDataReference(
            name="u", unit="dimensionless", count=value, digest=DIGEST
        )


@pytest.mark.parametrize("value", [1.9, True, "1"])
def test_the_count_rule_is_the_integer_rule_the_core_already_states(value):
    """One policy, asserted across both records rather than trusted to match.

    ``IntegerValue`` is where this repository states what an integer
    declaration is. ``count`` disagreed with it; if either moves, this says so.
    """
    with pytest.raises(ScientificCoreError):
        IntegerValue(value=value)
    with pytest.raises(ScientificCoreError):
        ScientificDataReference(
            name="u", unit="dimensionless", count=value, digest=DIGEST
        )


def test_an_honest_count_still_builds_and_a_zero_count_is_still_legal():
    """Zero is a declaration, not an absence; the refusal must not eat it."""
    empty = ScientificDataReference(
        name="u", unit="dimensionless", count=0, digest=DIGEST
    )
    assert empty.count == 0
    assert empty.byte_length == 0
    assert ScientificDataReference(
        name="u", unit="dimensionless", count=3, digest=DIGEST
    ).count == 3


def test_a_serialized_count_is_refused_rather_than_coerced():
    """The wire path pre-coerced, which stepped around the constructor."""
    payload = ScientificDataReference(
        name="u", unit="dimensionless", count=2, digest=DIGEST
    ).to_dict()
    with pytest.raises(ScientificCoreError):
        ScientificDataReference.from_dict({**payload, "count": 2.7})
    assert ScientificDataReference.from_dict(payload).count == 2


# =====================================================================
# is_usable means what the audit found it to mean, and no more
# =====================================================================


def _result_with(validity_status: ValidityStatus | None) -> ScientificResult:
    validity = {} if validity_status is None else {"m": _assessment(validity_status)}
    not_assessed = {"m": "not assessed here"} if validity_status is None else {}
    return ScientificResult(
        result_id="res",
        values={},
        provenance=_provenance((("m", "1"),)),
        problem_id="p",
        models=(("m", "1"),),
        validation=ValidationReport(),
        validity=validity,
        validity_not_assessed=not_assessed,
    )


@pytest.mark.parametrize(
    "status",
    [ValidityStatus.IN_DOMAIN, ValidityStatus.OUTSIDE_VALIDATED_DOMAIN,
     ValidityStatus.UNKNOWN, None],
    ids=["in_domain", "outside", "unknown", "unassessed"],
)
def test_is_usable_is_independent_of_validity_in_both_directions(status):
    """A deliberate distinction, pinned so it cannot drift either way.

    ``is_usable`` answers *converged, and no check failed*. It does not answer
    *is this model in its validated domain* — ``transportable()`` says in its
    own docstring that it deliberately does not use this property, and the
    inference boundary layers a separate NUMERICALLY_CONVERGED requirement on
    top of it. Both readings are defensible and only one is implemented, so
    the one that is gets asserted: a caller who wants validity must ask for
    validity.

    The audit that added this found the convergence and validation axes
    exhaustively pinned by ``test_core_v02_invariants.py`` and this third axis
    pinned by nothing at all.
    """
    result = _result_with(status)
    assert result.is_usable is True
    assert result.validation_status is ValidationOutcome.NOT_RUN


def test_a_result_outside_its_validated_domain_still_says_so():
    """Usable is not valid, and the record must keep the second answer."""
    result = _result_with(ValidityStatus.OUTSIDE_VALIDATED_DOMAIN)
    assert result.is_usable
    assert result.validity_of("m").status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN


# =====================================================================
# Variable kinds: what the type represents, and where the rule lives
# =====================================================================


@pytest.mark.parametrize(
    "kind,kwargs",
    [
        (VariableKind.BOOLEAN,
         dict(unit="kelvin", lower=Quantity(0.0, "kelvin"),
              upper=Quantity(500.0, "kelvin"))),
        (VariableKind.CATEGORICAL,
         dict(unit="dimensionless", categories=("a", "b"),
              lower=_dimensionless(0.0), upper=_dimensionless(1.0))),
        (VariableKind.INTEGER,
         dict(unit="dimensionless", lower=_dimensionless(0.2),
              upper=_dimensionless(0.8))),
    ],
    ids=["boolean_with_physical_bounds", "categorical_with_bounds",
         "integer_with_no_integer_in_range"],
)
def test_the_variable_type_represents_what_the_design_boundary_refuses(kind, kwargs):
    """CONTRACT GAP, recorded rather than invented away.

    ``ScientificVariable`` accepts all three. Its docstring says V0 only
    *represents* the non-continuous kinds and defers mixed-variable search,
    and the rules that would refuse these are stated in ``design/sampling.py``
    — dimensionless, integer-valued bounds, no numeric bounds on categorical
    or boolean — at the only place that consumes them.

    So the contract is split: the type carries the declaration and a consumer
    carries the rule. That is a real gap (a second consumer inherits no
    refusal) and it is NOT a defect today, because there is no second
    consumer. Asserted as-is so that closing it is a decision somebody makes
    rather than a change nobody notices.
    """
    variable = ScientificVariable(name="v", kind=kind, **kwargs)
    assert variable.kind is kind


def test_the_one_cross_field_rule_the_type_does_enforce():
    """Categories belong to categorical variables, both directions."""
    with pytest.raises(ScientificCoreError):
        ScientificVariable(name="v", unit="dimensionless",
                           kind=VariableKind.CONTINUOUS, categories=("a", "b"))
    with pytest.raises(ScientificCoreError):
        ScientificVariable(name="v", unit="dimensionless",
                           kind=VariableKind.CATEGORICAL, categories=("a",))


# =====================================================================
# Unit invariance
# =====================================================================

#: The same physical state written two ways, for families whose conversion is
#: exact in both directions. ``degC``/``kelvin`` is the pair the first blind
#: challenge found, and it is here because a fix nothing watches is a fix
#: waiting to be refactored away.
EQUIVALENT = [
    ("temperature", ("kelvin", 293.15), ("degC", 20.0)),
    ("time", ("second", 120.0), ("minute", 2.0)),
    ("resistance", ("ohm", 1000.0), ("kiloohm", 1.0)),
    ("power", ("watt", 1000.0), ("kilowatt", 1.0)),
]


@pytest.mark.parametrize("label,first,second", EQUIVALENT, ids=[c[0] for c in EQUIVALENT])
def test_equivalent_declarations_reach_the_same_verdict(label, first, second):
    """Four spellings of one comparison, one answer.

    The bound written either way, the value written either way. A decision
    that depends on which unit the caller happened to write is the one thing
    this layer says a unit may never do.
    """
    verdicts = set()
    for bound_unit, bound_value in (first, second):
        condition = RangeCondition(
            name="r",
            minimum=Quantity(bound_value, bound_unit),
            maximum=Quantity(bound_value, bound_unit),
        )
        for value_unit, value in (first, second):
            verdicts.add(condition.evaluate_in({"r": Quantity(value, value_unit)}))
    assert verdicts == {ValidityStatus.IN_DOMAIN}, (
        f"{label} decided differently depending on how it was written: {verdicts}"
    )


@pytest.mark.parametrize("label,first,second", EQUIVALENT, ids=[c[0] for c in EQUIVALENT])
def test_a_cross_limit_ratio_does_not_depend_on_the_scale_written(label, first, second):
    """The ratio path, over the same equivalences.

    A ratio taken on an interval scale is not a property of the values, which
    is why the numerator and denominator are put on a ratio scale first. Both
    operands are varied here, not just one.
    """
    condition = CrossLimitCondition(
        name="x", numerator="a", denominator="b",
        minimum=_dimensionless(0.9), maximum=_dimensionless(1.1),
    )
    verdicts = {
        condition.evaluate_in({
            "a": Quantity(av, au), "b": Quantity(bv, bu),
        })
        for au, av in (first, second)
        for bu, bv in (first, second)
    }
    assert verdicts == {ValidityStatus.IN_DOMAIN}, (
        f"{label} ratio depended on the spelling: {verdicts}"
    )


def test_exact_boundary_equality_across_units_is_a_float_property_not_a_rule():
    """Recorded, because the audit that found it nearly "fixed" it.

    ``1 kWh`` converts to exactly ``3600000 J``; ``3600000 J`` converts to
    ``0.9999999999999999 kWh``. ``_within`` converts the value into the
    BOUND's unit, so a value exactly on an inclusive maximum can land one ulp
    outside it depending on which unit the bound was written in.

    Normalising both operands onto the dimension's base unit was measured as
    the candidate repair and it is **not** a repair: over 3,200 same-state
    round-trips it was exact 94.9% of the time against the current basis's
    91.2%, and it was WORSE in 48 of them. Neither basis is invariant, so
    there is no basis to switch to — this is floating point, not a defect in
    the comparison, and ``_within`` says "Exact; no tolerance applied".

    Asserted rather than described so that the day it stops being true,
    somebody is told.
    """
    assert Quantity(1.0, "kilowatt_hour").magnitude_in("joule") == 3600000.0
    assert Quantity(3600000.0, "joule").magnitude_in("kilowatt_hour") != 1.0
    # And the semantic families above are exact in both directions, which is
    # why they are the ones asserted as invariant.
    for _label, (unit_a, value_a), (unit_b, value_b) in EQUIVALENT:
        assert Quantity(value_b, unit_b).magnitude_in(unit_a) == value_a
        assert base_unit(unit_a) == base_unit(unit_b)


# =====================================================================
# CURRENT-CORE CERTIFICATION ROUND — three proven contract gaps
#
# Each is a value the core's own stated rule forbids and its constructor
# admitted. None could be written down by ``to_json``, so each failed closed
# at the far end of the boundary rather than at the near end — which is the
# difference between "cannot be recorded" and "cannot exist", and the reason
# all three are refused at construction now.
# =====================================================================


def test_an_unknown_uncertainty_cannot_carry_a_confidence_level():
    """The one value the UNKNOWN branch did not reach.

    ``UNKNOWN uncertainty must not carry values`` was enforced over
    ``standard_uncertainty``, ``lower`` and ``upper`` — the estimates. A
    confidence level is the coverage probability *of an interval*, so a record
    carrying one while carrying no interval states the probability that a
    bound nobody computed contains the truth.

    It round-tripped, so the number reached the wire beside ``"kind":
    "unknown"`` and ``"lower": null``: a consumer reading the field to size a
    coverage interval got 0.95 from a record whose entire content is "nothing
    was evaluated". Nothing in this repository reads it, which is exactly why
    the refusal belongs at the constructor rather than in a convention every
    future reader has to know.
    """
    with pytest.raises(ScientificCoreError, match="confidence_level"):
        Uncertainty(kind=UncertaintyKind.UNKNOWN, confidence_level=0.95)


def test_an_unknown_uncertainty_still_says_why_nothing_was_computed():
    """The other half of the rule, so the refusal cannot be over-read.

    Prose stays permitted: an UNKNOWN record exists to say that nothing was
    evaluated and why. What is refused is a NUMBER that means nothing except
    beside an estimate that is not there.
    """
    record = Uncertainty(
        kind=UncertaintyKind.UNKNOWN,
        source="no propagation was performed",
        notes="the model declares no input uncertainty",
    )
    assert record.kind is UncertaintyKind.UNKNOWN
    assert record.confidence_level is None
    assert not record.is_quantified
    # And a level is still accepted where there IS something for it to cover.
    quantified = Uncertainty(
        kind=UncertaintyKind.STANDARD,
        standard_uncertainty=Quantity(1.0, "kelvin"),
        method="declared",
        confidence_level=0.95,
    )
    assert quantified.confidence_level == 0.95


@pytest.mark.parametrize("bad", [float("inf"), float("-inf"), float("nan")])
def test_a_provenance_tolerance_must_be_finite(bad):
    """The only float-bearing mapping in the core that admitted a non-finite.

    ``SolverSettings.tolerances`` refuses one and ``ProvenanceRecord.metadata``
    refuses one; the tolerance mapping beside them did not. A tolerance is the
    bound a result was judged against, so an infinite one says the run was
    solved to no bound while reading exactly like a run that was, and a NaN one
    cannot be ordered against anything.
    """
    with pytest.raises(ScientificCoreError, match="tolerance"):
        ProvenanceRecord(run_id="r", tolerances={"rtol": bad})


def test_a_non_finite_tolerance_cannot_return_through_the_wire_either():
    """The reader half, which is where a lenient producer's record arrives.

    It failed closed only at ``to_json``, which is both late and only on the
    canonical path: ``to_dict`` emitted the raw float, so
    ``json.dumps(record.to_dict())`` produced ``{"rtol": Infinity}`` — which no
    conforming reader accepts — and ``from_dict`` admitted it straight back,
    because ``json.loads`` reads that bare token by default. The refusal is in
    ``__post_init__``, which ``from_dict`` goes through, so one rule closes
    both directions.
    """
    assert json.loads('{"rtol": Infinity}') == {"rtol": float("inf")}
    payload = ProvenanceRecord(run_id="r").to_dict()
    payload["tolerances"] = {"rtol": float("inf")}
    with pytest.raises(ScientificCoreError, match="tolerance"):
        ProvenanceRecord.from_dict(payload)


@pytest.mark.parametrize(
    "label,bad",
    [
        ("non-finite", {"rtol": float("inf")}),
        ("non-string key", {"nested": {1: "one"}}),
        ("unserializable", {"handle": object()}),
    ],
)
def test_solver_options_are_held_to_the_free_form_rule(label, bad):
    """The last free-form mapping in the core that was not checked.

    ``ProvenanceRecord.metadata`` and ``ScientificResult.metadata`` both run
    ``unwritable``; ``SolverSettings.options`` did not, so the mapping sitting
    beside a checked ``tolerances`` accepted a non-finite float, a non-string
    key, or an object no record can carry. Settings that cannot be written down
    are settings the run cannot say it used.
    """
    with pytest.raises(ScientificCoreError, match="cannot be recorded"):
        SolverSettings(options=bad)


def test_the_options_every_domain_actually_declares_still_pass():
    """The rule reaches only what no record can carry.

    Every ``options`` mapping the domains in this repository build is strings,
    integers and booleans, and the check is derived from what survives being
    written down rather than from a list of permitted shapes.
    """
    settings = SolverSettings(
        options={
            "formulation": "modified_nodal_analysis",
            "n_output_points": 50,
            "dense_output": True,
        },
    )
    assert settings.options["n_output_points"] == 50
    assert json.loads(json.dumps(settings.to_dict()))["options"][
        "dense_output"] is True


def test_a_solver_settings_payload_is_the_callers_to_edit():
    """``to_dict`` detaches, like every other free-form branch in the core.

    It handed back the record's own frozen containers, so a caller editing the
    payload — the ordinary thing to do with a payload — got a refusal from a
    container it had every reason to think was its own. The record was never at
    risk; the payload was simply not a payload.
    """
    settings = SolverSettings(options={"nested": {"a": 1}, "listed": [1, 2]})
    payload = settings.to_dict()
    payload["options"]["nested"]["a"] = 99
    payload["options"]["listed"].append(3)
    assert settings.options["nested"]["a"] == 1
    assert list(settings.options["listed"]) == [1, 2]


# ---------------------------------------------------------------------------
# BLIND-V2-1: a validity record must describe the derivation it is stated over
# ---------------------------------------------------------------------------
def test_a_condition_that_says_unknown_unless_must_mean_it():
    """Blind Challenge v2 found the lumped geometry record contradicting itself.

    ``geometry_route_ratio`` published, in the record a caller reads and
    ``to_dict`` serializes, that it is *UNKNOWN unless characteristic_length,
    body_volume and surface_area are all supplied*. The derivation deliberately
    returns 1 with a single route -- ``test_one_route_alone_is_not_a_contradiction``
    pins that on purpose -- so a body declaring a length and no volume reached
    IN_DOMAIN with the condition in ``satisfied``. An independent reader of the
    contract predicted a refusal and got an acceptance.

    The record was the half that was wrong, and this test is what stops the two
    drifting apart again: for every condition on the lumped model whose
    description promises UNKNOWN in a named circumstance, that circumstance is
    constructed and the promise is checked against the derivation.
    """
    from engcore.domains.thermal_models import context as ctx
    from engcore.domains.thermal_models.lumped import LUMPED_CAPACITY_MODEL
    from engcore.scientific.units.quantity import Quantity

    conditions = {c.name: c for c in LUMPED_CAPACITY_MODEL.validity.conditions}

    # The promise that was broken, now stated the way the derivation behaves.
    geometry = conditions[ctx.GEOMETRY_ROUTE_RATIO]
    assert "UNKNOWN only when NEITHER route is available" in geometry.description
    assert "WITH ONE ROUTE THIS CONDITION IS SATISFIED" in geometry.description

    # ... and the derivation, at each of the three declarations that matter.
    both_routes = ctx.derived_lumped_quantities({
        ctx.CHARACTERISTIC_LENGTH: Quantity(0.002, "meter"),
        ctx.BODY_VOLUME: Quantity(2.0e-5, "meter**3"),
        ctx.SURFACE_AREA: Quantity(0.01, "meter**2"),
    })
    assert ctx.GEOMETRY_ROUTE_RATIO in both_routes

    one_route = ctx.derived_lumped_quantities({
        ctx.CHARACTERISTIC_LENGTH: Quantity(0.002, "meter"),
    })
    assert one_route[ctx.GEOMETRY_ROUTE_RATIO].magnitude_in("dimensionless") == 1.0

    neither_route = ctx.derived_lumped_quantities({
        ctx.SURFACE_AREA: Quantity(0.01, "meter**2"),
    })
    assert ctx.GEOMETRY_ROUTE_RATIO not in neither_route

    # Every OTHER condition on this model that promises UNKNOWN-unless keeps
    # that promise literally: with none of its declarations supplied, the
    # assembler does not produce it at all.
    promises = {
        ctx.MELTING_TEMPERATURE_UTILIZATION: (),
        ctx.RADIATION_TO_CONVECTION_RATIO: (),
        ctx.CONDUCTANCE_EXCURSION_RATIO: (),
        ctx.CAPACITY_EXCURSION_RATIO: (),
        ctx.BIOT_NUMBER: (),
    }
    bare = ctx.derived_lumped_quantities({})
    for name in promises:
        assert "UNKNOWN unless" in conditions[name].description, name
        assert name not in bare, name
