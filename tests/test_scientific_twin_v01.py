from __future__ import annotations

import pytest

from engcore.scientific import (
    BooleanValue,
    CategoricalValue,
    IntegerValue,
    InvalidScientificProblem,
    ModelReference,
    Quantity,
    ScientificTwin,
    TwinDatum,
    TwinDatumRole,
    TwinKind,
    TwinReference,
    to_json,
)


def _model(name: str = "model-a", version: str = "1") -> ModelReference:
    return ModelReference(name, version)


def _datum(
    name: str = "mass",
    value=None,
    role: TwinDatumRole = TwinDatumRole.PARAMETER,
) -> TwinDatum:
    if value is None:
        value = Quantity(2.0, "kg")
    return TwinDatum(name=name, value=value, role=role)


def test_all_preregistered_twin_kinds_can_be_constructed() -> None:
    concept = ScientificTwin("concept-1", "1", TwinKind.CONCEPT)
    reference = ScientificTwin("reference-1", "1", TwinKind.REFERENCE, models=(_model(),))
    candidate = ScientificTwin("candidate-1", "1", TwinKind.CANDIDATE, models=(_model(),))
    calibrated = ScientificTwin(
        "calibrated-1",
        "1",
        TwinKind.CALIBRATED,
        models=(_model(),),
        calibration_evidence_refs=("evidence:calibration:1",),
    )
    ensemble = ScientificTwin(
        "ensemble-1",
        "1",
        TwinKind.ENSEMBLE,
        models=(_model("model-a"), _model("model-b")),
    )
    derived = ScientificTwin(
        "candidate-1",
        "2",
        TwinKind.DERIVED,
        models=(_model(),),
        parent=TwinReference("candidate-1", "1"),
    )

    assert concept.models == ()
    assert reference.kind is TwinKind.REFERENCE
    assert candidate.kind is TwinKind.CANDIDATE
    assert calibrated.calibration_evidence_refs == ("evidence:calibration:1",)
    assert len(ensemble.models) == 2
    assert derived.parent == TwinReference("candidate-1", "1")


@pytest.mark.parametrize(
    ("twin_id", "version"),
    [("", "1"), ("twin", "")],
)
def test_blank_twin_identity_or_version_is_rejected(twin_id: str, version: str) -> None:
    with pytest.raises(InvalidScientificProblem):
        ScientificTwin(twin_id, version, TwinKind.CONCEPT)


def test_non_concept_requires_model_and_duplicate_models_are_rejected() -> None:
    with pytest.raises(InvalidScientificProblem):
        ScientificTwin("candidate", "1", TwinKind.CANDIDATE)

    with pytest.raises(InvalidScientificProblem):
        ScientificTwin(
            "candidate",
            "1",
            TwinKind.CANDIDATE,
            models=(_model(), _model()),
        )


def test_bare_numeric_datum_is_rejected() -> None:
    with pytest.raises(InvalidScientificProblem):
        TwinDatum("mass", 2.0)  # type: ignore[arg-type]


def test_duplicate_declaration_names_are_rejected_across_roles() -> None:
    with pytest.raises(InvalidScientificProblem):
        ScientificTwin(
            "candidate",
            "1",
            TwinKind.CANDIDATE,
            models=(_model(),),
            declarations=(
                _datum("temperature", Quantity(300.0, "K"), TwinDatumRole.PARAMETER),
                _datum("temperature", Quantity(310.0, "K"), TwinDatumRole.STATE),
            ),
        )


def test_calibrated_ensemble_and_derived_invariants_fail_closed() -> None:
    with pytest.raises(InvalidScientificProblem):
        ScientificTwin(
            "calibrated",
            "1",
            TwinKind.CALIBRATED,
            models=(_model(),),
        )

    with pytest.raises(InvalidScientificProblem):
        ScientificTwin(
            "ensemble",
            "1",
            TwinKind.ENSEMBLE,
            models=(_model(),),
        )

    with pytest.raises(InvalidScientificProblem):
        ScientificTwin(
            "derived",
            "1",
            TwinKind.DERIVED,
            models=(_model(),),
        )


def test_twin_round_trip_and_json_are_deterministic() -> None:
    twin = ScientificTwin(
        twin_id="drone-candidate-184",
        version="3",
        kind=TwinKind.DERIVED,
        name="Candidate 184 v3",
        models=(_model("aero", "2"), _model("electrical", "4")),
        declarations=(
            _datum("mass", Quantity(2.3, "kg")),
            _datum(
                "motor_count",
                IntegerValue(4),
                TwinDatumRole.PARAMETER,
            ),
            _datum(
                "flight_mode",
                CategoricalValue("cruise", vocabulary=("hover", "cruise")),
                TwinDatumRole.OPERATING_CONDITION,
            ),
            _datum(
                "controller_enabled",
                BooleanValue(True),
                TwinDatumRole.CONTROL,
            ),
        ),
        assumptions=("rigid frame",),
        evidence_refs=("evidence:manufacturer:1",),
        parent=TwinReference("drone-candidate-184", "2"),
        metadata={"display_only": "not scientific context"},
    )

    payload = twin.to_dict()
    restored = ScientificTwin.from_dict(payload)

    assert restored == twin
    assert restored.to_dict() == payload
    assert to_json(twin) == to_json(restored)
    assert to_json(twin) == to_json(twin)


def test_scientific_context_uses_typed_declarations_and_excludes_metadata() -> None:
    twin = ScientificTwin(
        "reference-system",
        "1",
        TwinKind.REFERENCE,
        models=(_model(),),
        declarations=(
            _datum("temperature", Quantity(300.0, "K"), TwinDatumRole.STATE),
            _datum("segments", IntegerValue(5)),
            _datum("enabled", BooleanValue(True), TwinDatumRole.CONTROL),
            _datum(
                "material",
                CategoricalValue("aluminum", vocabulary=("aluminum", "steel")),
            ),
        ),
        metadata={"hidden_scientific_value": 999.0},
    )

    context = twin.scientific_context()

    assert context["temperature"] == Quantity(300.0, "K")
    assert context["segments"] == 5
    assert context["enabled"] is True
    assert context["material"] == "aluminum"
    assert "hidden_scientific_value" not in context


def test_self_parent_exact_version_is_rejected() -> None:
    with pytest.raises(InvalidScientificProblem):
        ScientificTwin(
            "same",
            "1",
            TwinKind.DERIVED,
            models=(_model(),),
            parent=TwinReference("same", "1"),
        )
