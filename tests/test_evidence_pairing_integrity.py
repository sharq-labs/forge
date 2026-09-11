"""Two models receive a comparative conclusion only on the same canonical evidence.

Sprint 3, Part A. Reproductions written against ``compare_log_predictive_scores``
at ``3a4f063``, before any fix. Every refused pair below shares the observation
key, the assessment count and the model structure -- everything the comparison
checked -- and differs in the evidence itself. At that commit each of them was
compared, and two of them manufactured a model preference.

    Two models may only receive a comparative scientific conclusion if they
    were assessed against the same canonical evidence.
"""

from __future__ import annotations

import numpy as np
import pytest

from engcore.adequacy import (
    ModelAdequacyError,
    PredictiveObservationAssessment,
    assess_predictive_observation,
    compare_log_predictive_scores,
)
from engcore.inference import AdmittedForwardTable, PosteriorGrid
from engcore.scientific import ModelReference, Quantity, TwinReference
from engcore.uq import PredictiveObservableSpec

#: Reproduced at ``3a4f063``. Strict, so the fix has to remove these marks.
REPRODUCED = pytest.mark.xfail(
    strict=True,
    reason="Sprint 3 A2 reproduction: assessments of different evidence were compared at 3a4f063",
)

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


# ---- refused: the A2 reproductions ------------------------------------------------------
@REPRODUCED
@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"observed": 30.0}, id="1-same-key-different-observed-value"),
        pytest.param({"dataset": "TRAIN-2"}, id="2-different-posterior-dataset"),
        pytest.param({"heldout": "HOLD-2"}, id="3-different-heldout-partition"),
        pytest.param({"twin": TwinReference("another-twin", "1")}, id="4-different-twin"),
        pytest.param({"sigma": 9.0}, id="5-different-likelihood-sigma"),
    ],
)
def test_assessments_of_different_evidence_are_not_compared(changes):
    with pytest.raises(ModelAdequacyError, match="evidence"):
        _compare(**changes)


@REPRODUCED
def test_one_observation_counted_twice_is_not_paired_evidence():
    a = (_assess(MA, "H1:y"), _assess(MA, "H1:y"))
    b = (_assess(MB, "H1:y"), _assess(MB, "H1:y"))
    with pytest.raises(ModelAdequacyError, match="evidence"):
        compare_log_predictive_scores(MA, a, MB, b)


@REPRODUCED
def test_only_typed_assessments_are_compared():
    class _LooksLikeAnAssessment:
        observation_key = "H1:y"
        model = MB
        log_predictive_density = 100.0

    with pytest.raises(ModelAdequacyError, match="PredictiveObservationAssessment"):
        compare_log_predictive_scores(
            MA, (_assess(MA, "H1:y"),), MB, (_LooksLikeAnAssessment(),)
        )


# ---- serialization ------------------------------------------------------------------------------
@REPRODUCED
def test_an_assessment_round_trips_with_its_evidence_and_is_compared_again():
    item = _assess(MA, "H1:y")
    restored = PredictiveObservationAssessment.from_dict(item.to_dict())
    assert restored == item
    assert restored.to_dict() == item.to_dict()
    compare_log_predictive_scores(MA, (restored,), MB, (_assess(MB, "H1:y"),))


@REPRODUCED
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
