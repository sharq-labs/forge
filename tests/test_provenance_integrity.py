"""Provenance must be able to record every input that changed the answer.

THE GAP
-------
``ScientificProblem`` has always carried its parameters as a
:data:`ScientificValue` -- a dimensional ``Quantity``, an exact ``IntegerValue``
count, a declared ``BooleanValue`` flag, or a ``CategoricalValue``.
``ProvenanceRecord.inputs`` accepted **only the first of the four**.

A study legitimately turns on ``steady_state = True`` or
``material = "aluminum"``: those decide which model applies, whether a solve is
transient, and what the number at the end means. None of them could be written
into the record of what the run was computed from.

**It was a refusal, not a drop**, which is the one thing that would have been
worse -- but it left a producer two options, and both lose the input: leave it
out of provenance entirely, or put it in untyped ``metadata``, where nothing
checks it and nothing can read its type back.

THE FIX, AND WHY IT NEEDED NO MIGRATION
---------------------------------------
``inputs`` is now the union the problem already speaks, encoded through
``encode_value``/``decode_value``. Those dispatch on each value's **own**
schema, so a ``provenance_record/1`` record -- whose inputs are all
``quantity/1`` payloads -- decodes to exactly the ``Quantity`` objects it always
did. No version branch, no defaulting, and nothing older reinterpreted.

The record version moved to ``/4`` anyway, because the bump is about the
**reader**: code predating this calls ``Quantity.from_dict`` on every input and
would fail on a categorical one.
"""

from __future__ import annotations

import json

import pytest

from engcore.scientific.errors import (
    InvalidScientificProblem,
    ScientificCoreError,
)
from engcore.scientific.ir.values import (
    BooleanValue,
    CategoricalValue,
    IntegerValue,
    ValueKind,
    value_kind,
)
from engcore.scientific.results.provenance import (
    PROVENANCE_SCHEMA,
    PROVENANCE_SCHEMA_V1,
    PROVENANCE_SCHEMA_V2,
    PROVENANCE_SCHEMA_V3,
    SUPPORTED_PROVENANCE_SCHEMAS,
    ProvenanceRecord,
)
from engcore.scientific.serialization import to_json
from engcore.scientific.units.quantity import Quantity

#: One of every kind in the union, so a round trip that lost one would fail.
EVERY_KIND = {
    "ambient_temperature": Quantity(293.15, "kelvin"),
    "segment_count": IntegerValue(5),
    "steady_state": BooleanValue(True),
    "material": CategoricalValue("aluminum", vocabulary=("aluminum", "steel")),
}


def test_every_scientific_value_kind_can_be_recorded():
    """The gap, closed. Each kind is an input that changes what a result means."""
    record = ProvenanceRecord(run_id="run-1", inputs=EVERY_KIND)
    assert set(record.inputs) == set(EVERY_KIND)
    assert {value_kind(v) for v in record.inputs.values()} == {
        ValueKind.QUANTITY,
        ValueKind.INTEGER,
        ValueKind.BOOLEAN,
        ValueKind.CATEGORICAL,
    }, "a kind in the union is not representable in provenance"


def test_the_semantic_type_survives_a_round_trip():
    """A category that comes back as a string has lost what made it a category.

    Types are compared with `is` rather than `isinstance`, because `bool` is an
    `int` subclass and `BooleanValue`/`IntegerValue` exist precisely to keep
    that distinction -- an `isinstance` check would pass over the confusion the
    union was built to prevent.
    """
    record = ProvenanceRecord(run_id="run-1", inputs=EVERY_KIND)
    restored = ProvenanceRecord.from_dict(json.loads(to_json(record)))

    assert restored == record
    assert type(restored.inputs["ambient_temperature"]) is Quantity
    assert type(restored.inputs["segment_count"]) is IntegerValue
    assert type(restored.inputs["steady_state"]) is BooleanValue
    assert type(restored.inputs["material"]) is CategoricalValue

    assert restored.inputs["segment_count"].value == 5
    assert restored.inputs["steady_state"].value is True
    assert restored.inputs["material"].value == "aluminum"
    # The declared vocabulary is part of what the category MEANS, so it travels.
    assert restored.inputs["material"].vocabulary == ("aluminum", "steel")
    assert restored.inputs["ambient_temperature"] == Quantity(293.15, "kelvin")


def test_serialization_is_deterministic_and_json_clean():
    record = ProvenanceRecord(run_id="run-1", inputs=EVERY_KIND)
    once = to_json(record)
    assert once == to_json(ProvenanceRecord.from_dict(json.loads(once)))
    payload = json.loads(once)
    assert payload["schema"] == PROVENANCE_SCHEMA
    assert list(payload["inputs"]) == sorted(EVERY_KIND)
    # Each input carries its OWN schema, which is what makes decoding a
    # dispatch rather than a version branch.
    assert payload["inputs"]["material"]["schema"] == "categorical_value/1"
    assert payload["inputs"]["ambient_temperature"]["schema"] == "quantity/1"


def test_a_quantity_only_record_from_an_older_version_still_loads():
    """The compatibility claim, exercised at every version that ever existed.

    A /1../3 record's inputs are `quantity/1` payloads. `decode_value`
    dispatches on that schema and returns the same `Quantity` the old reader
    built, so there is nothing to migrate.
    """
    original = ProvenanceRecord(
        run_id="legacy",
        inputs={"mass": Quantity(2.0, "kilogram"), "length": Quantity(3.0, "meter")},
    )
    for version in (
        PROVENANCE_SCHEMA_V1,
        PROVENANCE_SCHEMA_V2,
        PROVENANCE_SCHEMA_V3,
    ):
        payload = original.to_dict()
        payload["schema"] = version
        if version == PROVENANCE_SCHEMA_V1:
            payload.pop("bindings", None)
        if version in (PROVENANCE_SCHEMA_V1, PROVENANCE_SCHEMA_V2):
            payload.pop("transfers", None)

        restored = ProvenanceRecord.from_dict(payload)
        assert restored.inputs["mass"] == Quantity(2.0, "kilogram")
        assert type(restored.inputs["mass"]) is Quantity
        assert restored.inputs["length"] == Quantity(3.0, "meter")
        # One-way upgrade: re-serializing writes the current version.
        assert restored.to_dict()["schema"] == PROVENANCE_SCHEMA


def test_the_supported_versions_are_exact_and_include_every_past_one():
    """A reader that quietly dropped an old version would strand records."""
    assert SUPPORTED_PROVENANCE_SCHEMAS == (
        "provenance_record/1",
        "provenance_record/2",
        "provenance_record/3",
        "provenance_record/4",
    )
    assert PROVENANCE_SCHEMA == "provenance_record/4"


@pytest.mark.parametrize(
    "value",
    [2.0, 5, True, "aluminum", None, [1, 2], {"a": 1}, Quantity],
)
def test_a_value_outside_the_union_is_still_refused(value):
    """Widening the contract must not have opened it.

    A bare float is a unit-stripped number, which is exactly what the original
    Quantity-only rule was protecting against, and a naked string is a category
    with no declared vocabulary and no type. Both are still refused -- what
    changed is that the TYPED forms of those things are now expressible.
    """
    with pytest.raises((ScientificCoreError, InvalidScientificProblem)):
        ProvenanceRecord(run_id="r", inputs={"x": value})


def test_the_refusal_names_the_input_that_caused_it():
    with pytest.raises(Exception) as raised:
        ProvenanceRecord(run_id="r", inputs={"segments": 5})
    assert "segments" in str(raised.value)


def test_inputs_stay_immutable_and_the_payload_stays_detached():
    """The trust-boundary rule the rest of this record already follows."""
    record = ProvenanceRecord(run_id="r", inputs=dict(EVERY_KIND))
    with pytest.raises(TypeError):
        record.inputs["injected"] = IntegerValue(9)
    with pytest.raises(TypeError):
        record.inputs.update({"segment_count": IntegerValue(9)})
    assert set(record.inputs) == set(EVERY_KIND)

    payload = record.to_dict()
    payload["inputs"]["segment_count"]["value"] = 99
    assert record.inputs["segment_count"].value == 5


def test_a_problems_own_parameters_can_be_recorded_without_loss():
    """The end-to-end statement: what a problem declares, provenance can hold.

    This is the property the gap actually broke. `parameter_values()` is the
    problem's own accessor and returns the whole union; before this round its
    result could not be handed to `ProvenanceRecord` at all.
    """
    from engcore.scientific.ir.problem import ScientificProblem
    from engcore.scientific.ir.variables import (
        ScientificParameter,
        ScientificVariable,
    )

    problem = ScientificProblem(
        problem_id="p",
        name="a study that turns on more than quantities",
        variables=(ScientificVariable("x", unit="meter"),),
        parameters=(
            ScientificParameter("ambient_temperature", Quantity(293.15, "kelvin")),
            ScientificParameter("segment_count", IntegerValue(5)),
            ScientificParameter("steady_state", BooleanValue(True)),
            ScientificParameter(
                "material",
                CategoricalValue("aluminum", vocabulary=("aluminum", "steel")),
            ),
        ),
    )

    declared = problem.parameter_values()
    record = ProvenanceRecord(run_id="p-run", inputs=declared)
    assert set(record.inputs) == set(declared)
    for name, value in declared.items():
        assert type(record.inputs[name]) is type(value)
        assert record.inputs[name] == value
