"""``ScientificResult.validity``: one assessment per model, and no third state.

``NEEDS.md`` §1.1 records that the result could not carry the model-validity
verdict the README lists among the four things a result carries, so every
assessment travelled beside it and each consumer re-carried it. This is that
field, and these tests are about the one thing that could go wrong with it.

**Empty is not UNKNOWN.** An empty mapping means nobody asked whether the
model applied. ``ValidityStatus.UNKNOWN`` means somebody asked and the context
could not settle it. The first is repaired by making the assessment, the second
by gathering the input the assessment needed, and a record that let them blur
would point a reader at the wrong work. Most of what follows is about the ways
that blur could be reintroduced — a ``None`` value, a total accessor, a
synthesized UNKNOWN, a serialized null — and about the fact that each is
refused rather than documented.
"""

from __future__ import annotations

import copy
import json

import pytest

from src.engcore.scientific import (
    ProvenanceRecord,
    Quantity,
    ScientificCoreError,
    ScientificResult,
    SolverIdentity,
    ValidationCheck,
    ValidationLevel,
    ValidationOutcome,
    ValidationReport,
    ValidityAssessment,
    ValidityStatus,
)
from src.engcore.scientific.results.result import (
    RESULT_SCHEMA,
    RESULT_SCHEMA_V1,
    RESULT_SCHEMA_V2,
    SUPPORTED_RESULT_SCHEMAS,
)

THERMAL = "thermal.lumped_capacity"
MATERIAL = "electrical.material.linear_tcr_resistance"

IN_DOMAIN = ValidityAssessment(
    status=ValidityStatus.IN_DOMAIN, satisfied=("biot_number", "fourier_number")
)
VIOLATED = ValidityAssessment(
    status=ValidityStatus.OUTSIDE_VALIDATED_DOMAIN, violated=("biot_number",)
)
UNKNOWN = ValidityAssessment(
    status=ValidityStatus.UNKNOWN, unknown=("body_conductivity",)
)


def provenance() -> ProvenanceRecord:
    return ProvenanceRecord(
        run_id="run-0001",
        software_version="core",
        git_commit="0" * 40,
        models=((THERMAL, "1.0.0"), (MATERIAL, "1.0.0")),
        solvers=(("closed_form", "1.0.0"),),
        inputs={"heat_input": Quantity(2.0, "watt")},
        assumptions=(),
        tolerances={},
        environment={},
        timestamp="2026-01-01T00:00:00+00:00",
    )


def result(**overrides) -> ScientificResult:
    payload = dict(
        result_id="res-0001",
        values={"final_temperature": Quantity(338.577, "kelvin")},
        models=((THERMAL, "1.0.0"), (MATERIAL, "1.0.0")),
        solver=SolverIdentity("closed_form", "1.0.0"),
        validation=ValidationReport(
            checks=(
                ValidationCheck(
                    name="metric_dimensions",
                    outcome=ValidationOutcome.PASS,
                    establishes=ValidationLevel.DIMENSIONALLY_VALID,
                    evidence=("fixture:metric=dimensionless declared by the model record",),
                ),
            )
        ),
        provenance=provenance(),
    )
    payload.update(overrides)
    return ScientificResult(**payload)


# =====================================================================
# The default: nothing breaks, and nothing is claimed
# =====================================================================

def test_a_result_built_without_validity_carries_none_and_says_so():
    """Optional and empty by default, so no existing construction site moved."""
    plain = result()
    assert plain.validity == {}
    assert plain.unassessed_models == (MATERIAL, THERMAL)
    assert not plain.is_assessed(THERMAL)


def test_a_result_with_no_models_and_no_validity_is_still_constructible():
    """The floor of the contract: the field is genuinely optional."""
    bare = result(models=())
    assert bare.validity == {}
    assert bare.unassessed_models == ()


# =====================================================================
# Empty is not UNKNOWN — the distinction, four ways
# =====================================================================

def test_not_assessed_and_assessed_unknown_are_different_records():
    """The two states the field exists to keep apart, side by side."""
    nobody_asked = result()
    asked_and_unsettled = result(validity={THERMAL: UNKNOWN})

    assert nobody_asked.validity == {}
    assert asked_and_unsettled.validity[THERMAL].status is ValidityStatus.UNKNOWN
    assert nobody_asked.to_dict()["validity"] == {}
    assert asked_and_unsettled.to_dict()["validity"] != {}
    # and they disagree about which models still need work
    assert THERMAL in nobody_asked.unassessed_models
    assert THERMAL not in asked_and_unsettled.unassessed_models


def test_the_accessor_raises_for_an_unassessed_model_rather_than_defaulting():
    """Not total, and deliberately so.

    A ``None`` return or a synthesized UNKNOWN would put every caller one
    ``or`` away from reading an unasked question as an unanswerable one.
    """
    with pytest.raises(ScientificCoreError) as excinfo:
        result().validity_of(THERMAL)
    message = str(excinfo.value)
    assert "not assessed" in message
    assert "UNKNOWN" in message


def test_nothing_in_the_core_ever_synthesizes_an_unknown_status():
    """The statuses a result carries are only ones a model actually produced.

    Asserted over every accessor at once: with no assessments in, no assessment
    of any status comes out, and the record refuses to be asked for one.
    """
    plain = result()
    assert plain.validity == {}
    assert not plain.is_assessed(MATERIAL)
    with pytest.raises(ScientificCoreError):
        plain.validity_of(MATERIAL)
    assert ValidityStatus.UNKNOWN not in {
        assessment.status for assessment in plain.validity.values()
    }


def test_a_none_value_in_the_mapping_is_refused():
    """The one shape that would reintroduce the third state.

    A key present with no assessment would mean "listed, but not assessed",
    which is neither of the two states and would have to be interpreted.
    """
    with pytest.raises(ScientificCoreError) as excinfo:
        result(validity={THERMAL: None})
    assert "no such state" in str(excinfo.value)


def test_is_assessed_is_the_total_question_and_validity_of_is_not():
    """The pair that makes the difference visible at the call site."""
    assessed = result(validity={THERMAL: IN_DOMAIN})
    assert assessed.is_assessed(THERMAL) is True
    assert assessed.is_assessed(MATERIAL) is False
    assert assessed.validity_of(THERMAL) is IN_DOMAIN
    with pytest.raises(ScientificCoreError):
        assessed.validity_of(MATERIAL)


# =====================================================================
# One assessment per model, and the mapping is why
# =====================================================================

def test_a_coupled_result_carries_one_verdict_per_model_without_collapsing_them():
    """The reason this is a mapping and not a field.

    A run whose thermal model is in domain and whose material model is not has
    two answers. A single field would have to report one of them, and would
    report the wrong one half the time.
    """
    coupled = result(validity={THERMAL: IN_DOMAIN, MATERIAL: VIOLATED})
    assert coupled.validity_of(THERMAL).status is ValidityStatus.IN_DOMAIN
    assert (
        coupled.validity_of(MATERIAL).status
        is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    )
    assert coupled.unassessed_models == ()


def test_a_partially_assessed_coupled_result_names_the_gap():
    partial = result(validity={THERMAL: IN_DOMAIN})
    assert partial.unassessed_models == (MATERIAL,)


def test_an_assessment_for_a_model_that_did_not_take_part_is_refused():
    """Otherwise a clean verdict about an unrelated model could travel here."""
    with pytest.raises(ScientificCoreError) as excinfo:
        result(validity={"kinetics.cstr": IN_DOMAIN})
    assert "not among the models this result declares" in str(excinfo.value)


def test_validity_without_declared_models_is_refused():
    """An assessment names a model at a version; a result naming none cannot."""
    with pytest.raises(ScientificCoreError) as excinfo:
        result(models=(), validity={THERMAL: IN_DOMAIN})
    assert "declares no models" in str(excinfo.value)


def test_an_unrecognised_status_is_refused_rather_than_carried():
    """A status no branch understands must not travel inside a result.

    ``ValidityAssessment`` has no ``__post_init__`` (``NEEDS.md`` §1.9), so it
    accepts a bare string. This field refuses one it cannot recognise, and
    normalises one it can.
    """
    with pytest.raises(ScientificCoreError):
        result(validity={THERMAL: ValidityAssessment(status="probably_fine")})

    normalised = result(
        validity={THERMAL: ValidityAssessment(status="in_domain")}
    )
    assert normalised.validity_of(THERMAL).status is ValidityStatus.IN_DOMAIN
    # and the normalised copy serializes, which a bare string would not
    assert normalised.to_dict()["validity"][THERMAL]["status"] == "in_domain"


def test_a_blank_model_id_is_refused():
    with pytest.raises(ScientificCoreError):
        result(validity={"   ": IN_DOMAIN})


# =====================================================================
# Serialization
# =====================================================================

def test_the_schema_moved_and_the_accept_set_grew_rather_than_shifting():
    assert RESULT_SCHEMA == "scientific_result/3"
    assert SUPPORTED_RESULT_SCHEMAS == (
        RESULT_SCHEMA_V1,
        RESULT_SCHEMA_V2,
        RESULT_SCHEMA,
    )


def test_validity_round_trips_through_the_serialized_form():
    original = result(validity={THERMAL: IN_DOMAIN, MATERIAL: VIOLATED})
    payload = json.loads(json.dumps(original.to_dict(), sort_keys=True))
    restored = ScientificResult.from_dict(payload)

    assert restored.to_dict() == original.to_dict()
    assert restored.validity == original.validity
    assert restored.validity_of(MATERIAL).violated == ("biot_number",)
    assert restored.unassessed_models == ()


def test_an_unknown_assessment_survives_the_round_trip_as_unknown():
    """The state most easily lost: it must not come back as "not assessed"."""
    original = result(validity={THERMAL: UNKNOWN})
    restored = ScientificResult.from_dict(
        json.loads(json.dumps(original.to_dict(), sort_keys=True))
    )
    assert restored.is_assessed(THERMAL)
    assert restored.validity_of(THERMAL).status is ValidityStatus.UNKNOWN
    assert restored.validity_of(THERMAL).unknown == ("body_conductivity",)


@pytest.mark.parametrize("version", ["scientific_result/1", "scientific_result/2"])
def test_a_payload_written_before_this_field_loads_as_not_assessed(version):
    """Which is the truth about it: those writers could not carry one."""
    payload = json.loads(json.dumps(result().to_dict(), sort_keys=True))
    payload["schema"] = version
    payload.pop("validity")
    if version == "scientific_result/1":
        payload.pop("data_references")

    restored = ScientificResult.from_dict(payload)
    assert restored.validity == {}
    assert restored.unassessed_models == (MATERIAL, THERMAL)
    # re-serializing upgrades it; the writer emits one version only
    assert restored.to_dict()["schema"] == RESULT_SCHEMA


def test_an_older_payload_carrying_the_key_is_not_read_as_if_it_had_written_it():
    """By version, not by key presence — the rule ``/1`` already established."""
    original = result(validity={THERMAL: IN_DOMAIN})
    payload = json.loads(json.dumps(original.to_dict(), sort_keys=True))
    payload["schema"] = "scientific_result/2"
    assert payload["validity"], "the payload must actually carry one"

    assert ScientificResult.from_dict(payload).validity == {}


def test_an_explicit_null_loads_as_not_assessed_and_not_as_an_error():
    """One representation of "nobody asked", reachable from either encoding."""
    payload = json.loads(json.dumps(result().to_dict(), sort_keys=True))
    payload["validity"] = None
    assert ScientificResult.from_dict(payload).validity == {}


def test_the_serialized_form_never_encodes_a_null_assessment():
    """The refused in-memory state has no serialized counterpart either."""
    payload = result(validity={THERMAL: IN_DOMAIN, MATERIAL: UNKNOWN}).to_dict()
    assert None not in payload["validity"].values()
    assert set(payload["validity"]) == {THERMAL, MATERIAL}


def test_the_result_copies_the_mapping_it_is_given():
    given = {THERMAL: IN_DOMAIN}
    carried = result(validity=given)
    given[MATERIAL] = VIOLATED
    assert set(carried.validity) == {THERMAL}


def test_a_deep_copy_carries_the_assessments():
    original = result(validity={THERMAL: IN_DOMAIN, MATERIAL: VIOLATED})
    assert copy.deepcopy(original).validity == original.validity
