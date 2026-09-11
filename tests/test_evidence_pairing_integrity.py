"""Two models receive a comparative conclusion only on the same canonical evidence.

Sprint 3, Part A. ``test(evidence): reproduce mismatched-evidence comparisons``
recorded these as strict xfails against ``compare_log_predictive_scores`` at
``3a4f063``: every refused pair below shares the observation key, the assessment
count and the model structure -- everything the comparison checked -- and
differs in the evidence itself. Each of them was compared, and two of them
manufactured a model preference.

    Two models may only receive a comparative scientific conclusion if they
    were assessed against the same canonical evidence.

The identity is :class:`PredictiveEvidenceIdentity`: the observation key, the
observed value and the likelihood sigma in the observable's unit, the held-out
partition, the posterior's dataset and the twin. ``source_ref`` and the credible
mass are deliberately outside it, and the tests below say why.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from engcore.adequacy import (
    EVIDENCE_IDENTITY_FIELDS,
    ModelAdequacyError,
    PredictiveEvidenceIdentity,
    PredictiveObservationAssessment,
    assess_predictive_observation,
    compare_log_predictive_scores,
)
from engcore.inference import AdmittedForwardTable, PosteriorGrid
from engcore.scientific import ModelReference, Quantity, TwinReference
from engcore.uq import PredictiveObservableSpec

KEYS = ("H1:y", "H2:y")
OBSERVED = {"H1:y": 12.0, "H2:y": 21.0}
TWIN = TwinReference("twin", "1")
MA = ModelReference("model-a", "1")
MB = ModelReference("model-b", "1")


def _posterior(dataset_id: str = "TRAIN-1") -> PosteriorGrid:
    points = np.asarray([[0.0], [1.0]], dtype=np.float64)
    return PosteriorGrid(
        parameter_names=("p",),
        points=points,
        weights=np.asarray([0.25, 0.75]),
        log_likelihood=np.log(np.asarray([0.25, 0.75])),
        admissible_mask=np.asarray([True, True]),
        dataset_id=dataset_id,
    )


def _table() -> AdmittedForwardTable:
    return AdmittedForwardTable(
        parameter_names=("p",),
        observation_keys=KEYS,
        points=np.asarray([[0.0], [1.0]], dtype=np.float64),
        values=np.asarray([[10.0, 20.0], [14.0, 22.0]], dtype=np.float64),
        admissible_mask=np.asarray([True, True]),
        admission_refs=(("a:H1", "a:H2"), ("b:H1", "b:H2")),
        rejection_reasons=("", ""),
    )


def _assess(
    model: ModelReference,
    key: str,
    *,
    observed: float | None = None,
    dataset: str = "TRAIN-1",
    heldout: str = "HOLD-1",
    twin: TwinReference = TWIN,
    sigma: float = 2.0,
    source: str | None = None,
    mass: float = 0.95,
) -> PredictiveObservationAssessment:
    return assess_predictive_observation(
        _posterior(dataset),
        _table(),
        PredictiveObservableSpec(key, "kelvin", Quantity(sigma, "kelvin")),
        Quantity(OBSERVED[key] if observed is None else observed, "kelvin"),
        twin=twin,
        model=model,
        source_ref=source or f"{model.model_id}|heldout:{heldout}",
        heldout_dataset_id=heldout,
        credible_mass=mass,
    )


def _side(model: ModelReference, **first_changes):
    """Every held-out observation for one model; ``first_changes`` alter only the first."""
    return tuple(
        _assess(model, key, **(first_changes if index == 0 else {}))
        for index, key in enumerate(KEYS)
    )


def _compare(**b_changes):
    return compare_log_predictive_scores(MA, _side(MA), MB, _side(MB, **b_changes))


# ---- allowed ----------------------------------------------------------------------
def test_the_same_canonical_evidence_is_compared():
    comparison = _compare()
    assert comparison.delta_a_minus_b == pytest.approx(0.0)
    assert comparison.preferred_model is None


def test_a_different_source_reference_alone_is_provenance_not_evidence():
    """``source_ref`` names who produced an assessment. K4 writes a different one
    per model for one held-out set, so it cannot be the evidence identity."""
    comparison = _compare(source="another-writer|same held-out set, different wording")
    assert comparison.delta_a_minus_b == pytest.approx(0.0)


def test_a_different_credible_mass_does_not_change_the_log_score_evidence():
    """The credible mass sets an interval for coverage; the log score does not read it."""
    comparison = _compare(mass=0.5)
    assert comparison.delta_a_minus_b == pytest.approx(0.0)


def test_the_comparison_records_the_evidence_it_was_made_on():
    comparison = _compare(source="another-writer")
    again = _compare()
    assert comparison.evidence_digest == again.evidence_digest
    assert comparison.to_dict()["evidence_digest"] == comparison.evidence_digest
    other_partition = compare_log_predictive_scores(
        MA, _side(MA, heldout="HOLD-2"), MB, _side(MB, heldout="HOLD-2")
    )
    assert other_partition.evidence_digest != comparison.evidence_digest


# ---- refused: the A2 reproductions ------------------------------------------------------
@pytest.mark.parametrize(
    "changes, field",
    [
        pytest.param({"observed": 30.0}, "observed_value", id="1-same-key-different-observed-value"),
        pytest.param({"dataset": "TRAIN-2"}, "posterior_dataset_id", id="2-different-posterior-dataset"),
        pytest.param({"heldout": "HOLD-2"}, "heldout_dataset_id", id="3-different-heldout-partition"),
        pytest.param({"twin": TwinReference("another-twin", "1")}, "twin", id="4-different-twin"),
        pytest.param({"sigma": 9.0}, "likelihood_sigma", id="5-different-likelihood-sigma"),
    ],
)
def test_assessments_of_different_evidence_are_not_compared(changes, field):
    with pytest.raises(ModelAdequacyError, match="different evidence") as refused:
        _compare(**changes)
    assert field in str(refused.value)


def test_one_observation_counted_twice_is_not_paired_evidence():
    a = (_assess(MA, "H1:y"), _assess(MA, "H1:y"))
    b = (_assess(MB, "H1:y"), _assess(MB, "H1:y"))
    with pytest.raises(ModelAdequacyError, match="evidence"):
        compare_log_predictive_scores(MA, a, MB, b)


def test_only_typed_assessments_are_compared():
    class _LooksLikeAnAssessment:
        observation_key = "H1:y"
        model = MB
        log_predictive_density = 100.0

    with pytest.raises(ModelAdequacyError, match="PredictiveObservationAssessment"):
        compare_log_predictive_scores(
            MA, (_assess(MA, "H1:y"),), MB, (_LooksLikeAnAssessment(),)
        )


def test_the_identity_covers_exactly_the_declared_fields():
    assert EVIDENCE_IDENTITY_FIELDS == (
        "observation_key",
        "observed_value",
        "unit",
        "likelihood_sigma",
        "heldout_dataset_id",
        "posterior_dataset_id",
        "twin",
    )
    item = _assess(MA, "H1:y")
    assert item.evidence.likelihood_sigma == 2.0
    assert item.evidence.heldout_dataset_id == "HOLD-1"


# ---- Part C: the direct constructor is not a way around it ---------------------------------------
@pytest.mark.parametrize(
    "field, value",
    [
        pytest.param("observed_value", 30.0, id="observed-value"),
        pytest.param("posterior_dataset_id", "TRAIN-2", id="posterior-dataset"),
        pytest.param("twin", TwinReference("another-twin", "1"), id="twin"),
        pytest.param("observation_key", "H2:y", id="observation-key"),
        pytest.param("likelihood_sigma", 1.0e6, id="sigma-no-score-could-have-used"),
    ],
)
def test_an_assessment_whose_evidence_describes_other_evidence_is_refused(field, value):
    item = _assess(MA, "H1:y")
    forged = dataclasses.replace(item.evidence, **{field: value})
    with pytest.raises(ModelAdequacyError, match="does not match its evidence identity"):
        dataclasses.replace(item, evidence=forged)


def test_an_assessment_without_an_evidence_identity_cannot_be_built():
    item = _assess(MA, "H1:y")
    with pytest.raises(ModelAdequacyError, match="PredictiveEvidenceIdentity"):
        dataclasses.replace(item, evidence=item.evidence.to_dict())


def test_relabelling_a_record_to_the_other_evidence_still_cannot_be_compared():
    """Forge both the fields and the identity of B to name A's evidence, while
    B's score stays what B's own evidence produced: construction accepts it,
    because the record is now coherent -- and it is A's evidence, so the forger
    has only succeeded in comparing on A's evidence with a number from elsewhere.
    The pairing check is about evidence; score integrity is not claimed here."""
    b = _assess(MB, "H1:y", heldout="HOLD-2")
    relabelled = dataclasses.replace(
        b, evidence=dataclasses.replace(b.evidence, heldout_dataset_id="HOLD-1")
    )
    compare_log_predictive_scores(MA, (_assess(MA, "H1:y"),), MB, (relabelled,))


# ---- serialization ------------------------------------------------------------------------------
def test_an_assessment_round_trips_with_its_evidence_and_is_compared_again():
    item = _assess(MA, "H1:y")
    restored = PredictiveObservationAssessment.from_dict(item.to_dict())
    assert restored == item
    assert restored.to_dict() == item.to_dict()
    assert restored.evidence.digest == item.evidence.digest
    compare_log_predictive_scores(MA, (restored,), MB, (_assess(MB, "H1:y"),))


@pytest.mark.parametrize(
    "field, value",
    [
        pytest.param("observed", Quantity(99.0, "kelvin").to_dict(), id="observed-value"),
        pytest.param("posterior_dataset_id", "TRAIN-2", id="posterior-dataset"),
        pytest.param("twin", TwinReference("another-twin", "1").to_dict(), id="twin"),
    ],
)
def test_a_tampered_serialized_assessment_is_refused(field, value):
    payload = _assess(MA, "H1:y").to_dict()
    payload[field] = value
    with pytest.raises(ModelAdequacyError, match="evidence"):
        PredictiveObservationAssessment.from_dict(payload)


@pytest.mark.parametrize(
    "field, value",
    [
        pytest.param("heldout_dataset_id", "HOLD-2", id="heldout-partition"),
        pytest.param("likelihood_sigma", 9.0, id="likelihood-sigma"),
        pytest.param("observed_value", 30.0, id="observed-value"),
    ],
)
def test_a_tampered_serialized_evidence_identity_is_refused(field, value):
    payload = _assess(MA, "H1:y").to_dict()
    payload["evidence"][field] = value
    with pytest.raises(ModelAdequacyError, match="evidence"):
        PredictiveObservationAssessment.from_dict(payload)


def test_a_tampered_identity_with_a_recomputed_digest_is_still_different_evidence():
    payload = _assess(MB, "H1:y").to_dict()
    evidence = PredictiveEvidenceIdentity.from_dict(payload["evidence"])
    payload["evidence"] = dataclasses.replace(evidence, heldout_dataset_id="HOLD-2").to_dict()
    restored = PredictiveObservationAssessment.from_dict(payload)
    with pytest.raises(ModelAdequacyError, match="different evidence"):
        compare_log_predictive_scores(MA, (_assess(MA, "H1:y"),), MB, (restored,))


def test_a_serialized_assessment_without_evidence_is_refused():
    payload = _assess(MA, "H1:y").to_dict()
    del payload["evidence"]
    with pytest.raises(ModelAdequacyError, match="no evidence identity"):
        PredictiveObservationAssessment.from_dict(payload)
