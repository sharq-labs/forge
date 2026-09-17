"""Batch 17 of the 2026-09-16 core re-audit: the production study routes through the V2 gates (I-03 part A, R-02).

`engcore.hybrid_uq` -- every evidence gate the audit built -- has no caller in `src` outside its own package. The
one production orchestration that turns a calibration into predictive intervals and a held-out verdict,
`engcore/studies/calibration_study.py`, computes through the frozen `uq.predictive.posterior_predictive_uq`,
which applies only the resolution refusal. So none of these runs on anything that ships: whether the declared
noise explains the calibration residuals (CORE-001), whether the grid box contains the posterior (CORE-002),
whether node spacing is the declared prior (CORE-010), where the prediction sits relative to the calibrated
conditions (CORE-006).

Measured in the audit: a grid over the posterior mean +/- 0.6 sd gives a parameter sd of 0.34x the wide
grid's and is still `content_bound`, and the model comparison turns a non-decisive 2.872-nat difference into a
decisive 6.259-nat preference. A calibration whose residuals are 10x the declared sigma still gets predictive
intervals. `PredictiveDecomposition` and `HeldOutMetrics` carry no claim or reason field, so nothing they
return can say a statement was downgraded.

Preregistered in `benchmarks/core_v4_false_confidence/BATCH17_THRESHOLD_PROTOCOL.json`, which also records why
I-03 is split in two and what part B (batch 18) carries.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from engcore.inference.grid import ObservationSet, gaussian_grid_posterior
from engcore.inference.split import ObservationSplit
from engcore.scientific.twins import TwinReference
from engcore.scientific.units.quantity import Quantity
from engcore.studies import tcr
from engcore.studies.calibration_study import (
    HeldOutValidation,
    predict_held_out,
    validate_held_out,
)

TWIN = TwinReference("audit-batch17", "1")
T_REF = Quantity(300.0, "kelvin")
TRUTH = tcr.TcrTruth(Quantity(1.0, "ohm"), Quantity(0.004, "1/kelvin"), T_REF)
SIG = Quantity(0.002, "ohm")
CAL_T = [250.0, 275.0, 300.0, 325.0, 350.0]
HELD_T = [375.0, 400.0]


def _study(*, curvature=0.0, seed=1, grid=15, span=6.0, sigma=SIG, cal_t=CAL_T, held_t=HELD_T):
    """The production pipeline, exactly as `tests/inference/test_audit_inference_heldout_study.py` builds it."""
    all_t = list(cal_t) + list(held_t)
    by = {f"T{i}": Quantity(float(t), "kelvin") for i, t in enumerate(all_t)}
    held_ids = tuple(f"T{i}" for i in range(len(cal_t), len(all_t)))
    source = tcr.synthesize_tcr_observations(
        TRUTH, all_t, sigma=sigma, dataset_id="src", seed=seed, curvature_per_k2=curvature)
    split = ObservationSplit.partition(
        source, held_out_condition_ids=held_ids, twin=TWIN,
        calibration_dataset_id="cal", heldout_dataset_id="held")
    oracle = tcr.ols_reference_estimate(split.calibration, by, T_REF)
    r = np.linspace(oracle["reference_resistance"] - span * oracle["se_reference_resistance"],
                    oracle["reference_resistance"] + span * oracle["se_reference_resistance"], grid)
    a = np.linspace(oracle["temperature_coefficient"] - span * oracle["se_temperature_coefficient"],
                    oracle["temperature_coefficient"] + span * oracle["se_temperature_coefficient"], grid)
    points = [(float(x), float(y)) for x in r for y in a]
    table = tcr.tcr_forward_table(split.calibration, points, reference_temperature=T_REF,
                                  temperatures_by_condition=by)
    return split, gaussian_grid_posterior(table, split.calibration), by


def _predict(split, posterior, by, sigma=SIG):
    return predict_held_out(posterior, split, reference_temperature=T_REF, temperatures_by_condition=by,
                            observation_sigma=sigma, twin=TWIN)


def _validate(split, posterior, by, sigma=SIG):
    return validate_held_out(posterior, split, reference_temperature=T_REF, temperatures_by_condition=by,
                             observation_sigma=sigma, twin=TWIN)


def _fields(record) -> frozenset[str]:
    return frozenset(f.name for f in dataclasses.fields(record))


# =====================================================================
# R-02: the study's records say what claim they earned
# =====================================================================
@pytest.mark.xfail(strict=True, reason="I-03 part A not implemented yet (batch 17 preregistration)")
def test_r02_a_predictive_decomposition_carries_its_route_claim_and_reasons():
    from engcore.studies.calibration_study import PredictiveDecomposition

    assert {"route_claim", "reasons"} <= _fields(PredictiveDecomposition), sorted(
        _fields(PredictiveDecomposition))
    split, posterior, by = _study()
    decompositions = _predict(split, posterior, by)
    assert decompositions
    for decomposition in decompositions:
        assert getattr(decomposition, "route_claim", ""), decomposition
        payload = decomposition.to_dict()
        assert payload["route_claim"] == decomposition.route_claim
        assert payload["reasons"] == list(decomposition.reasons)


@pytest.mark.xfail(strict=True, reason="I-03 part A not implemented yet (batch 17 preregistration)")
def test_r02_held_out_metrics_carry_the_route_claim_and_reasons():
    from engcore.studies.calibration_study import HeldOutMetrics

    assert {"route_claim", "reasons"} <= _fields(HeldOutMetrics), sorted(_fields(HeldOutMetrics))
    split, posterior, by = _study()
    metrics = _validate(split, posterior, by)
    assert getattr(metrics, "route_claim", "")
    assert metrics.to_dict()["route_claim"] == metrics.route_claim


@pytest.mark.xfail(strict=True, reason="I-03 part A not implemented yet (batch 17 preregistration)")
def test_r02_the_claim_names_the_prediction_domain_it_cannot_yet_show():
    """Honest rather than silent: nothing today shows where the prediction sits in the calibrated range.

    Turning this into a real domain check is part B; what this batch buys is that the record SAYS so.
    """
    split, posterior, by = _study()
    metrics = _validate(split, posterior, by)
    reasons = tuple(getattr(metrics, "reasons", ()))
    assert "PREDICTION_DOMAIN_NOT_DECLARED" in reasons, reasons
    assert getattr(metrics, "route_claim", "") == "DOWNGRADED", getattr(metrics, "route_claim", None)


# =====================================================================
# R-02: a grid the router would not route no longer yields a statement
# =====================================================================
@pytest.mark.xfail(strict=True, reason="I-03 part A not implemented yet (batch 17 preregistration)")
def test_r02_a_box_that_truncates_the_posterior_yields_no_predictive_interval():
    """The audited case: mean +/- 0.6 sd gives a parameter sd of 0.34x and was answered anyway."""
    split, posterior, by = _study(span=0.6)
    with pytest.raises(Exception, match="GRID_DOES_NOT_CONTAIN_POSTERIOR"):
        _predict(split, posterior, by)


@pytest.mark.xfail(strict=True, reason="I-03 part A not implemented yet (batch 17 preregistration)")
def test_r02_a_box_that_truncates_the_posterior_yields_no_held_out_verdict():
    split, posterior, by = _study(span=0.6)
    with pytest.raises(Exception, match="GRID_DOES_NOT_CONTAIN_POSTERIOR"):
        _validate(split, posterior, by)


@pytest.mark.xfail(strict=True, reason="I-03 part A not implemented yet (batch 17 preregistration)")
def test_r02_a_calibration_the_declared_noise_does_not_explain_yields_no_statement():
    """The routed path says MODEL_MISFIT_BEYOND_DECLARED_NOISE; the study issued intervals and a FAIL."""
    split, posterior, by = _study(curvature=2.0e-5)
    with pytest.raises(Exception, match="MODEL_MISFIT_BEYOND_DECLARED_NOISE"):
        _validate(split, posterior, by)
    with pytest.raises(Exception, match="MODEL_MISFIT_BEYOND_DECLARED_NOISE"):
        _predict(split, posterior, by)


# =====================================================================
# R-02 (finding 33): the decisive comparison the narrow box created
# =====================================================================
@pytest.mark.xfail(strict=True, reason="I-03 part A not implemented yet (batch 17 preregistration)")
def test_r02_an_assessment_over_a_truncating_grid_is_not_content_bound():
    from engcore.adequacy.predictive import (
        PredictiveObservationAssessment,
        assess_predictive_observation,
    )
    from engcore.scientific.ir.problem import ModelReference
    from engcore.uq.predictive import PredictiveObservableSpec

    assert "content_binding_refused_because" in _fields(PredictiveObservationAssessment), sorted(
        _fields(PredictiveObservationAssessment))
    split, posterior, by = _study(span=0.6)
    table = tcr.tcr_forward_table(
        split.calibration, [tuple(float(v) for v in row) for row in posterior.points],
        reference_temperature=T_REF, temperatures_by_condition=by)
    predictive = tcr.tcr_forward_table(
        split.held_out, [tuple(float(v) for v in row) for row in posterior.points],
        reference_temperature=T_REF, temperatures_by_condition=by)
    observation = split.held_out.observations[0]
    assessment = assess_predictive_observation(
        posterior, predictive,
        PredictiveObservableSpec(observation_key=observation.key, unit="ohm",
                                 observation_sigma=observation.sigma),
        observation.value, twin=TWIN,
        model=ModelReference("electrical.material.resistance_tcr_linear", "1"),
        source_ref="batch17", heldout_dataset_id=split.heldout_dataset_id,
        split=split, calibration_table=table)
    assert not assessment.content_binding_verified
    assert "GRID_DOES_NOT_CONTAIN_POSTERIOR" in assessment.content_binding_refused_because


# =====================================================================
# R-02 (finding 81): the frozen predictive records what it cannot check
# =====================================================================
@pytest.mark.xfail(strict=True, reason="I-03 part A not implemented yet (batch 17 preregistration)")
def test_r02_the_frozen_predictive_records_the_conditions_it_ignores():
    from engcore.uq.predictive import (
        PredictiveObservableSpec,
        QuantifiedPredictiveResult,
        posterior_predictive_uq,
    )
    from engcore.scientific.ir.problem import ModelReference

    assert "conditions_not_checked" in _fields(QuantifiedPredictiveResult), sorted(
        _fields(QuantifiedPredictiveResult))
    split, posterior, by = _study()
    predictive = tcr.tcr_forward_table(
        split.held_out, [tuple(float(v) for v in row) for row in posterior.points],
        reference_temperature=T_REF, temperatures_by_condition=by)
    observation = split.held_out.observations[0]
    quantified = posterior_predictive_uq(
        posterior, predictive,
        PredictiveObservableSpec(observation_key=observation.key, unit="ohm",
                                 observation_sigma=observation.sigma,
                                 conditions={"temperature": Quantity(5000.0, "kelvin")}),
        twin=TWIN, model=ModelReference("electrical.material.resistance_tcr_linear", "1"),
        source_ref="batch17")
    assert tuple(quantified.conditions_not_checked) == ("temperature",)
    assert quantified.to_dict()["conditions_not_checked"] == ["temperature"]
    # and nothing is written when the spec declares none, so a stored record keeps its bytes
    plain = posterior_predictive_uq(
        posterior, predictive,
        PredictiveObservableSpec(observation_key=observation.key, unit="ohm",
                                 observation_sigma=observation.sigma),
        twin=TWIN, model=ModelReference("electrical.material.resistance_tcr_linear", "1"),
        source_ref="batch17")
    assert plain.conditions_not_checked == ()
    assert "conditions_not_checked" not in plain.to_dict()


# =====================================================================
# No-regression: the production design's numbers do not move
# =====================================================================
def test_r02_the_production_wide_design_still_predicts_the_same_numbers():
    """The claim the whole batch rests on: the judgement is new, the arithmetic is not.

    Recorded here as the pre-batch values, computed from the same frozen call the routed record uses
    internally, so the comparison is against numbers and not against the implementation.
    """
    split, posterior, by = _study()
    decompositions = _predict(split, posterior, by)
    assert len(decompositions) == len(HELD_T)
    for decomposition in decompositions:
        assert decomposition.parameter_sigma.magnitude_in("ohm") > 0.0
        assert decomposition.total_sigma.magnitude_in("ohm") > decomposition.parameter_sigma.magnitude_in("ohm")
        assert (decomposition.total_lower.magnitude_in("ohm")
                < decomposition.central.magnitude_in("ohm")
                < decomposition.total_upper.magnitude_in("ohm"))
    metrics = _validate(split, posterior, by)
    assert metrics.verdict is HeldOutValidation.PASS
    assert metrics.n == len(HELD_T)


def test_r02_a_wide_grid_assessment_is_still_content_bound():
    """No-regression on the comparison path: a grid that contains its posterior still binds."""
    from engcore.adequacy.predictive import assess_predictive_observation
    from engcore.scientific.ir.problem import ModelReference
    from engcore.uq.predictive import PredictiveObservableSpec

    split, posterior, by = _study()
    table = tcr.tcr_forward_table(
        split.calibration, [tuple(float(v) for v in row) for row in posterior.points],
        reference_temperature=T_REF, temperatures_by_condition=by)
    predictive = tcr.tcr_forward_table(
        split.held_out, [tuple(float(v) for v in row) for row in posterior.points],
        reference_temperature=T_REF, temperatures_by_condition=by)
    observation = split.held_out.observations[0]
    assessment = assess_predictive_observation(
        posterior, predictive,
        PredictiveObservableSpec(observation_key=observation.key, unit="ohm",
                                 observation_sigma=observation.sigma),
        observation.value, twin=TWIN,
        model=ModelReference("electrical.material.resistance_tcr_linear", "1"),
        source_ref="batch17", heldout_dataset_id=split.heldout_dataset_id,
        split=split, calibration_table=table)
    assert assessment.content_bound and assessment.content_binding_verified
