"""Held-out validation and predictive study findings from the inference audit.

INF-01  a held-out PASS issued where the model's own validity assessment says the
        conditions are outside its validated domain (4000 K for a linear TCR law
        declared over 200-450 K);
INF-02  a caller-supplied ``observation_sigma`` silently replaced each held-out
        observation's declared sigma and flipped FAIL (chi2 49.3) to PASS;
INF-03  the posterior<->split binding compared a ``dataset_id`` string, so a
        posterior fitted on every row -- held-out rows included -- and labelled
        with the calibration id was scored as held-out evidence;
INF-05  coverage was CALIBRATED on almost no evidence (1 of 2; 0 of 0);
INF-08  TCR forward tables admitted grid rows outside the declared parameter
        bounds (alpha = 1.0 /K against a declared +/-0.02 /K).
"""

from __future__ import annotations

import numpy as np
import pytest

from engcore.inference.admissibility import InferenceAdmissibilityError
from engcore.inference.grid import InferenceProblemError, ObservationSet, GaussianObservation, gaussian_grid_posterior
from engcore.inference.parameters import ParameterIdentityError
from engcore.inference.split import DataLeakageError, ObservationSplit
from engcore.scientific.twins import TwinReference
from engcore.scientific.units.quantity import Quantity
from engcore.studies import tcr
from engcore.studies.calibration_study import (
    CoverageVerdict,
    HeldOutValidation,
    classify_coverage,
    predict_held_out,
    validate_held_out,
)

TWIN = TwinReference("audit-inference-heldout", "1")
T_REF = Quantity(300.0, "kelvin")
TRUTH = tcr.TcrTruth(Quantity(1.0, "ohm"), Quantity(0.004, "1/kelvin"), T_REF)
SIG = Quantity(0.002, "ohm")
CAL_T = [250.0, 275.0, 300.0, 325.0, 350.0]
HELD_T = [375.0, 400.0, 425.0, 440.0]


def _study(cal_t, held_t, *, curvature=0.0, leak=False, seed=1, grid=15, span=6.0):
    all_t = list(cal_t) + list(held_t)
    by = {f"T{i}": Quantity(float(t), "kelvin") for i, t in enumerate(all_t)}
    held_ids = tuple(f"T{i}" for i in range(len(cal_t), len(all_t)))
    source = tcr.synthesize_tcr_observations(
        TRUTH, all_t, sigma=SIG, dataset_id="src", seed=seed, curvature_per_k2=curvature
    )
    split = ObservationSplit.partition(
        source, held_out_condition_ids=held_ids, twin=TWIN,
        calibration_dataset_id="cal", heldout_dataset_id="held",
    )
    fit = ObservationSet(source.observations, dataset_id="cal") if leak else split.calibration
    oracle = tcr.ols_reference_estimate(fit, by, T_REF)
    r = np.linspace(oracle["reference_resistance"] - span * oracle["se_reference_resistance"],
                    oracle["reference_resistance"] + span * oracle["se_reference_resistance"], grid)
    a = np.linspace(oracle["temperature_coefficient"] - span * oracle["se_temperature_coefficient"],
                    oracle["temperature_coefficient"] + span * oracle["se_temperature_coefficient"], grid)
    points = [(float(x), float(y)) for x in r for y in a]
    table = tcr.tcr_forward_table(fit, points, reference_temperature=T_REF, temperatures_by_condition=by)
    return split, gaussian_grid_posterior(table, fit), by


def _validate(split, posterior, by, sigma=SIG):
    return validate_held_out(posterior, split, reference_temperature=T_REF, temperatures_by_condition=by,
                             observation_sigma=sigma, twin=TWIN)


def _predict(split, posterior, by, sigma=SIG):
    return predict_held_out(posterior, split, reference_temperature=T_REF, temperatures_by_condition=by,
                            observation_sigma=sigma, twin=TWIN)


# =====================================================================
# INF-01 -- applicability at the declared conditions
# =====================================================================

def test_holding_out_far_outside_the_validated_domain_is_not_a_pass():
    split, posterior, by = _study(CAL_T, [900.0, 1500.0, 2500.0, 4000.0])
    with pytest.raises(InferenceAdmissibilityError, match="outside_validated_domain"):
        _validate(split, posterior, by)


def test_a_prediction_far_outside_the_validated_domain_is_not_issued():
    split, posterior, by = _study(CAL_T, [900.0, 1500.0, 2500.0, 4000.0])
    with pytest.raises(InferenceAdmissibilityError, match="outside_validated_domain"):
        _predict(split, posterior, by)


def test_held_out_conditions_inside_the_validated_domain_still_validate():
    split, posterior, by = _study(CAL_T, HELD_T)
    assert _validate(split, posterior, by).verdict is HeldOutValidation.PASS
    assert len(_predict(split, posterior, by)) == len(HELD_T)


# =====================================================================
# INF-02 -- the declared sigma, not a caller override
# =====================================================================

def test_an_inflated_observation_sigma_cannot_flip_fail_to_pass():
    split, posterior, by = _study(CAL_T, HELD_T, curvature=1.0e-6)
    honest = _validate(split, posterior, by)
    assert honest.verdict is HeldOutValidation.FAIL, honest.why
    with pytest.raises(InferenceProblemError, match="declared sigma"):
        _validate(split, posterior, by, sigma=Quantity(0.02, "ohm"))
    with pytest.raises(InferenceProblemError, match="declared sigma"):
        _predict(split, posterior, by, sigma=Quantity(0.02, "ohm"))


def test_the_declared_sigma_in_another_unit_is_the_same_sigma():
    split, posterior, by = _study(CAL_T, HELD_T)
    assert _validate(split, posterior, by, sigma=Quantity(2.0, "milliohm")).verdict is HeldOutValidation.PASS


# =====================================================================
# INF-03 -- a posterior is bound to the calibration half by content
# =====================================================================

def test_a_posterior_fitted_on_every_row_and_relabelled_is_refused():
    split, leaked, by = _study(CAL_T, HELD_T, curvature=6.0e-7, leak=True)
    assert leaked.dataset_id == split.calibration_dataset_id
    with pytest.raises(DataLeakageError, match="calibration half"):
        _validate(split, leaked, by)
    with pytest.raises(DataLeakageError, match="calibration half"):
        _predict(split, leaked, by)


def test_an_honest_posterior_is_bound_to_its_calibration_half():
    split, honest, by = _study(CAL_T, HELD_T, curvature=6.0e-7)
    assert _validate(split, honest, by).verdict is HeldOutValidation.FAIL


# =====================================================================
# INF-05 -- coverage is CALIBRATED only on evidence that shows it
# =====================================================================

def test_no_intervals_is_refused_not_calibrated():
    with pytest.raises(ValueError, match="no intervals"):
        classify_coverage(0, 0, nominal=0.95, acceptance_half_width=0.05)


@pytest.mark.parametrize("covered,total", [(1, 2), (0, 1), (9, 10), (3, 10)])
def test_too_little_evidence_is_not_calibrated(covered, total):
    verdict, why = classify_coverage(covered, total, nominal=0.95, acceptance_half_width=0.05)
    assert verdict is not CoverageVerdict.CALIBRATED, why


def test_an_interval_inside_the_band_is_calibrated():
    verdict, why = classify_coverage(950, 1000, nominal=0.95, acceptance_half_width=0.05)
    assert verdict is CoverageVerdict.CALIBRATED, why


# =====================================================================
# INF-08 -- forward tables respect the declared parameter bounds
# =====================================================================

@pytest.mark.parametrize("point", [(1.0, 0.5), (1.0, -0.5), (50.0, 0.004), (-1.0, 0.004)])
def test_a_tcr_forward_row_outside_the_declared_bounds_is_refused(point):
    obs = ObservationSet((GaussianObservation("T0", tcr.RESISTANCE, Quantity(1.2, "ohm"), SIG, "s"),), "d")
    with pytest.raises(ParameterIdentityError):
        tcr.tcr_forward_table(obs, [point], reference_temperature=T_REF,
                              temperatures_by_condition={"T0": Quantity(350.0, "kelvin")})


def test_a_tcr_forward_row_inside_the_declared_bounds_is_admitted():
    obs = ObservationSet((GaussianObservation("T0", tcr.RESISTANCE, Quantity(1.2, "ohm"), SIG, "s"),), "d")
    table = tcr.tcr_forward_table(obs, [(1.0, 0.004)], reference_temperature=T_REF,
                                  temperatures_by_condition={"T0": Quantity(350.0, "kelvin")})
    assert table.admissible_mask.tolist() == [True]


def test_the_coverage_study_grid_axes_are_clipped_to_the_declared_bounds():
    from engcore.studies.calibration_study import _bounded_axis

    axis = _bounded_axis(0.019, 0.004, 9, lower=-0.02, upper=0.02)
    assert axis.min() >= -0.02 and axis.max() <= 0.02
    assert axis.size == 9
