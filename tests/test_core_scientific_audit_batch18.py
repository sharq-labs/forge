"""Batch 18 of the 2026-09-16 core re-audit: the study's own verdict arithmetic (I-03 part B).

Part A (batch 17) routed the production study's statements through the V2 evidence gates. This batch is the
arithmetic the study does itself, and three problems live in it.

* **R-35** -- `HELD_OUT_VALIDATION_PASS` is issued for any n >= 1 whenever the omnibus chi-square is not
  rejected at 0.01. There is no power floor and no INCONCLUSIVE, so with ONE held-out point a residual of
  2.11 sd reads "consistent with the model's own predictive distribution". Measured over the production TCR
  pipeline: a linear model fitted to curved truth PASSED in 24 of 40 seeds with one held-out point and 12 of
  40 with three, at a mean standardized residual of about 2.3 on every point. The omnibus test squares the
  residuals, so it is blind to exactly the common-SIGN bias a truncated expansion leaves.
* **R-36** -- the coverage verdict pools every interval of every repetition as an independent Bernoulli
  trial. Within one repetition they share one posterior; the audit measured an intraclass correlation of
  0.365 and a design effect of 2.09 over 300 repetitions of 4 intervals, so the reported Wilson interval
  overstates precision by about 1.45x and verdicts near the band edges are wrong.
* **R-38** -- one caller-supplied `observation_sigma` is compared with EVERY held-out sigma, so a half
  declaring [0.002, 0.002, 0.003] ohm can never be validated whatever is passed; and every coverage
  repetition records `CALIBRATION_CONVERGED` although no optimizer runs.

Preregistered in `benchmarks/core_v4_false_confidence/BATCH18_THRESHOLD_PROTOCOL.json`.

Fifteen of these were audited reproductions, recorded as `xfail(strict=True)` in commit **90ffb681** and
confirmed there to fail on their own assertions against the pre-batch tree (15 failed, 2 passed under
`--runxfail`). The markers came off with the implementation. The two unmarked tests are no-regression guards:
INF-02's supplied-sigma refusal still holds, and the pooled Wilson interval is the same number as before.
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np
import pytest

from engcore.inference.grid import GaussianObservation, ObservationSet, gaussian_grid_posterior
from engcore.inference.split import ObservationSplit
from engcore.scientific.twins import TwinReference
from engcore.scientific.units.quantity import Quantity
from engcore.studies import tcr
from engcore.studies.calibration_study import (
    CoverageStudy,
    CoverageVerdict,
    HeldOutValidation,
    classify_coverage,
    predict_held_out,
    validate_held_out,
)

TWIN = TwinReference("audit-batch18", "1")
T_REF = Quantity(300.0, "kelvin")
TRUTH = tcr.TcrTruth(Quantity(1.0, "ohm"), Quantity(0.004, "1/kelvin"), T_REF)
SIG = Quantity(0.002, "ohm")
OHM = "ohm"


def _fields(record) -> frozenset[str]:
    return frozenset(f.name for f in dataclasses.fields(record))


def _symbol(name):
    """Read a module symbol by NAME, so a reproduction fails on its own assertion."""
    import engcore.studies.calibration_study as module

    return getattr(module, name, None)


def _sigma_is_optional() -> bool:
    """Whether `observation_sigma` has a default, read by name for the same reason."""
    import inspect

    parameter = inspect.signature(validate_held_out).parameters.get("observation_sigma")
    return parameter is not None and parameter.default is not inspect.Parameter.empty


def _study(*, cal_t, held_t, curvature=0.0, seed=1, grid=15, span=6.0, sigmas=None):
    all_t = list(cal_t) + list(held_t)
    by = {f"T{i}": Quantity(float(t), "kelvin") for i, t in enumerate(all_t)}
    held_ids = tuple(f"T{i}" for i in range(len(cal_t), len(all_t)))
    source = tcr.synthesize_tcr_observations(
        TRUTH, all_t, sigma=SIG, dataset_id="src", seed=seed, curvature_per_k2=curvature)
    if sigmas is not None:
        # One reading's DECLARED sigma differs, which is the audited case: a half whose readings
        # were taken on instruments of different precision.
        rebuilt = []
        for index, observation in enumerate(source.observations):
            sigma = sigmas.get(observation.condition_id, observation.sigma)
            rebuilt.append(dataclasses.replace(observation, sigma=sigma))
        source = ObservationSet(tuple(rebuilt), dataset_id=source.dataset_id)
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


def _validate(split, posterior, by, **kwargs):
    return validate_held_out(posterior, split, reference_temperature=T_REF,
                             temperatures_by_condition=by, twin=TWIN, **kwargs)


#: Eight calibration points and eight held out, so the power floor is met and the tests below are
#: about the rule under test rather than about the floor.
WIDE_CAL = [250.0, 260.0, 270.0, 280.0, 290.0, 300.0, 310.0, 320.0]
WIDE_HELD = [255.0, 265.0, 275.0, 285.0, 295.0, 305.0, 315.0, 319.0]


# =====================================================================
# R-35: a verdict needs the power to have found something
# =====================================================================
def test_r35_there_is_a_third_held_out_verdict():
    assert getattr(HeldOutValidation, "INCONCLUSIVE", None) is not None, list(HeldOutValidation)
    assert HeldOutValidation.INCONCLUSIVE.value == "HELD_OUT_VALIDATION_INCONCLUSIVE"


def test_r35_the_minimum_is_where_a_one_sigma_bias_is_found_at_better_than_even_odds():
    """Derived from the alpha this module already declares, and from no new number."""
    from scipy.stats import norm

    from engcore.studies.calibration_study import HELD_OUT_CHI_SQUARE_ALPHA

    minimum = _symbol("HELD_OUT_MINIMUM_N")
    assert minimum is not None, "the module declares a held-out minimum n"
    z = norm.ppf(1.0 - HELD_OUT_CHI_SQUARE_ALPHA / 2.0)
    assert minimum == math.ceil(z * z) == 7, (minimum, z * z)


def test_r35_a_single_held_out_point_cannot_validate_a_model():
    """The audited case: one point, a 2.11 sd residual, and 'consistent with' in the record."""
    assert _sigma_is_optional(), "observation_sigma is optional, so the evidence's own sigmas are used"
    split, posterior, by = _study(cal_t=[250.0, 275.0, 300.0, 325.0, 350.0], held_t=[375.0])
    metrics = _validate(split, posterior, by)
    assert metrics.n == 1
    assert metrics.verdict is HeldOutValidation.INCONCLUSIVE, metrics.why
    assert "7" in metrics.why or "power" in metrics.why.lower(), metrics.why


def test_r35_a_rejection_is_still_a_rejection_below_the_floor():
    """A FAIL at any n: a rejection is evidence whatever the sample size, and withholding it
    would be the opposite error to the one this rule closes."""
    verdict_of = _symbol("held_out_verdict")
    assert verdict_of is not None, "the module states its held-out verdict rule as a function"
    verdict, why = verdict_of(standardized_residuals=(6.0,))
    assert verdict is HeldOutValidation.FAIL, (verdict, why)
    inconclusive, _ = verdict_of(standardized_residuals=(0.4,))
    assert inconclusive is HeldOutValidation.INCONCLUSIVE


def test_r35_a_common_sign_bias_is_found_where_the_omnibus_test_is_blind():
    """The shape a truncated expansion leaves, and the shape a sum of squares cannot see.

    Ten residuals of +1.2 give chi-square 14.4 on 10 dof -- p = 0.155, not rejected -- while their
    mean of 1.2 gives z = 3.79, p = 1.5e-4, which is below the 0.005 the two tests share.
    """
    from scipy.stats import chi2, norm

    verdict_of = _symbol("held_out_verdict")
    assert verdict_of is not None, "the module states its held-out verdict rule as a function"
    residuals = (1.2,) * 10
    assert chi2.sf(sum(r * r for r in residuals), df=len(residuals)) > 0.01
    assert 2.0 * norm.sf(abs(math.sqrt(len(residuals)) * 1.2)) < 0.005
    verdict, why = verdict_of(standardized_residuals=residuals)
    assert verdict is HeldOutValidation.FAIL, (verdict, why)
    assert "bias" in why.lower() or "mean" in why.lower(), why


def test_r35_the_family_wise_level_is_the_one_the_module_declares():
    """Two tests, each at half the declared alpha, so the union rate stays at or below it."""
    from engcore.studies.calibration_study import HELD_OUT_CHI_SQUARE_ALPHA

    per_test = _symbol("HELD_OUT_PER_TEST_ALPHA")
    assert per_test is not None, "the module declares the per-test level it splits its alpha into"
    assert per_test == HELD_OUT_CHI_SQUARE_ALPHA / 2.0


# =====================================================================
# R-36: the coverage interval accounts for its clustering
# =====================================================================
def test_r36_the_coverage_study_records_its_design_effect():
    assert {"intraclass_correlation", "design_effect", "effective_sample_size",
            "intervals_per_repetition"} <= _fields(CoverageStudy), sorted(_fields(CoverageStudy))


def test_r36_perfectly_clustered_indicators_give_a_design_effect_of_the_cluster_size():
    """The arithmetic, on the two extremes where the answer is known without estimation."""
    coverage_design_effect = _symbol("coverage_design_effect")
    assert coverage_design_effect is not None, "the module measures its own design effect"
    # every repetition all-covered or all-missed: ICC 1, design effect = intervals per repetition
    icc, deff, effective = coverage_design_effect([(4, 4), (0, 4), (4, 4), (0, 4)])
    assert icc == pytest.approx(1.0, abs=1e-9)
    assert deff == pytest.approx(4.0, abs=1e-9)
    assert effective == pytest.approx(4.0, abs=1e-9)
    # indicators that carry no repetition signal: ICC at or below 0, design effect clamped to 1
    even = [(2, 4)] * 8
    icc, deff, effective = coverage_design_effect(even)
    assert icc <= 0.0 + 1e-9
    assert deff == pytest.approx(1.0, abs=1e-9)
    assert effective == pytest.approx(32.0, abs=1e-9)


def test_r36_the_audited_verdict_flip_reproduces_at_the_effective_sample_size():
    """The audit's own numbers: 1104/1200 reads CALIBRATED pooled and INCONCLUSIVE effectively."""
    # The half-width is the module's own default of 0.05, which is what the audit measured against:
    # the band is [0.90, 1.00], the pooled Wilson interval is (0.9033, 0.934) and lies inside it, and
    # at the effective sample size it is (0.8948, 0.9394), whose lower end falls below the band.
    import inspect

    assert "effective_sample_size" in inspect.signature(classify_coverage).parameters, (
        "classify_coverage can be told the effective sample size")
    pooled, _ = classify_coverage(1104, 1200, nominal=0.95, acceptance_half_width=0.05)
    assert pooled is CoverageVerdict.CALIBRATED
    effective, why = classify_coverage(1104, 1200, nominal=0.95, acceptance_half_width=0.05,
                                       effective_sample_size=574.0)
    assert effective is CoverageVerdict.INCONCLUSIVE, why


def test_r36_a_refused_fraction_above_the_studys_own_tolerance_is_inconclusive():
    """Derived from the study's declared acceptance half-width, and from no new number.

    A refused repetition's intervals are unobserved, so the selection alone can move the measured
    coverage by at most the refused fraction. At or below the half-width it cannot carry the
    measurement across the band; above it, the verdict is about the gate rather than the model.
    """
    coverage_verdict_with_refusals = _symbol("coverage_verdict_with_refusals")
    assert coverage_verdict_with_refusals is not None, "the module reads its own refused fraction"
    # The module's own default half-width of 0.05, so the band is [0.90, 1.00] and 190/200 at an
    # effective size of 200 lies inside it -- which makes the refused fraction the only thing under
    # test here. 3 of 10 repetitions is 0.3, six times the half-width.
    verdict, why = coverage_verdict_with_refusals(
        covered=190, total=200, nominal=0.95, acceptance_half_width=0.05,
        effective_sample_size=200.0, refused=3, repetitions=10)
    assert verdict is CoverageVerdict.INCONCLUSIVE, why
    assert "0.3" in why or "refus" in why.lower(), why
    kept, _ = coverage_verdict_with_refusals(
        covered=190, total=200, nominal=0.95, acceptance_half_width=0.05,
        effective_sample_size=200.0, refused=0, repetitions=10)
    assert kept is CoverageVerdict.CALIBRATED


# =====================================================================
# R-38: each observation is scored with its own declared sigma
# =====================================================================
def test_r38_a_heterogeneous_held_out_half_can_be_validated():
    """The audited case: sigmas [0.002, 0.002, 0.003] could not be validated with ANY single value."""
    assert _sigma_is_optional(), "observation_sigma is optional, so the evidence's own sigmas are used"
    heterogeneous = {"T10": Quantity(0.003, OHM)}
    split, posterior, by = _study(cal_t=WIDE_CAL, held_t=WIDE_HELD, sigmas=heterogeneous)
    declared = {o.condition_id: o.sigma for o in split.held_out.observations}
    assert len(set(str(s) for s in declared.values())) == 2, declared
    metrics = _validate(split, posterior, by)
    assert metrics.n == len(WIDE_HELD)
    assert metrics.verdict in (HeldOutValidation.PASS, HeldOutValidation.FAIL), metrics.why
    decompositions = predict_held_out(posterior, split, reference_temperature=T_REF,
                                      temperatures_by_condition=by, twin=TWIN)
    assert {str(d.observation_sigma) for d in decompositions} == {str(s) for s in declared.values()}


def test_r38_a_supplied_sigma_that_is_not_the_declared_one_is_still_refused():
    """INF-02's guard, unchanged: a caller's wider sigma turned a failing model into a passing one."""
    from engcore.inference.grid import InferenceProblemError

    split, posterior, by = _study(cal_t=WIDE_CAL, held_t=WIDE_HELD)
    with pytest.raises(InferenceProblemError, match="(?i)declared sigma"):
        _validate(split, posterior, by, observation_sigma=Quantity(0.02, OHM))


def test_r38_a_repetition_that_ran_no_optimizer_does_not_claim_one_converged():
    from engcore.studies.calibration_study import run_coverage_study

    status = _symbol("COVERAGE_CALIBRATION_STATUS")
    assert status is not None, "the module names the status a grid-posterior repetition actually has"
    assert "CONVERGED" not in status
    COVERAGE_CALIBRATION_STATUS = status
    _, repetitions, _ = run_coverage_study(
        truth=TRUTH,
        calibration_temperatures=[280.0, 300.0, 320.0, 340.0],
        heldout_temperatures=[360.0, 380.0],
        reference_temperature=T_REF,
        observation_sigma=SIG,
        twin=TWIN,
        seeds=[11, 12],
        grid_points_per_axis=15,
    )
    assert {r.calibration_status for r in repetitions} == {COVERAGE_CALIBRATION_STATUS}


# =====================================================================
# R-02's residual from part A: the prediction domain becomes informative
# =====================================================================
def test_r02_the_tcr_observations_declare_the_temperature_they_were_measured_at():
    source = tcr.synthesize_tcr_observations(
        TRUTH, [250.0, 300.0, 350.0], sigma=SIG, dataset_id="conditions", seed=3)
    for index, observation in enumerate(source.observations):
        assert "temperature" in observation.conditions, observation
        assert observation.conditions["temperature"] == Quantity(
            [250.0, 300.0, 350.0][index], "kelvin")


def test_r02_an_extrapolating_study_says_it_is_extrapolating():
    """The TCR flagship holds out temperatures above its calibration range by design."""
    assert _sigma_is_optional(), "observation_sigma is optional, so the evidence's own sigmas are used"
    split, posterior, by = _study(cal_t=[250.0, 275.0, 300.0, 325.0, 350.0],
                                  held_t=[375.0, 400.0, 425.0, 440.0])
    metrics = _validate(split, posterior, by)
    assert "PREDICTION_OUTSIDE_CALIBRATED_CONDITIONS" in metrics.reasons, metrics.reasons
    assert "PREDICTION_DOMAIN_NOT_DECLARED" not in metrics.reasons, metrics.reasons


def test_r02_a_study_inside_its_calibrated_range_says_nothing_about_the_domain():
    assert _sigma_is_optional(), "observation_sigma is optional, so the evidence's own sigmas are used"
    split, posterior, by = _study(cal_t=WIDE_CAL, held_t=WIDE_HELD)
    metrics = _validate(split, posterior, by)
    assert "PREDICTION_OUTSIDE_CALIBRATED_CONDITIONS" not in metrics.reasons, metrics.reasons
    assert "PREDICTION_DOMAIN_NOT_DECLARED" not in metrics.reasons, metrics.reasons


# =====================================================================
# No-regression
# =====================================================================
def test_the_wilson_interval_is_unchanged_on_the_pooled_counts():
    """The point estimate and the independent interval are the same numbers as before."""
    from engcore.studies.calibration_study import wilson_interval

    low, high = wilson_interval(1152, 1200)
    assert low == pytest.approx(0.9474, abs=5e-4) and high == pytest.approx(0.9697, abs=5e-4)


def test_r02_each_predictive_record_carries_its_own_conditions_domain_verdict():
    """The per-observation records, not only the one the held-out verdict reads.

    `validate_held_out` routes ONE spec for its verdict; `predict_held_out` routes one per held-out
    condition, and each carries its own. A guard mutation that dropped the conditions from the
    predictive specs alone survived the extrapolation test above, because that test reads the
    verdict's record. (Guard mutation B18o, batch 18.)
    """
    assert _sigma_is_optional(), "observation_sigma is optional, so the evidence's own sigmas are used"
    split, posterior, by = _study(cal_t=[250.0, 275.0, 300.0, 325.0, 350.0],
                                  held_t=[375.0, 400.0, 425.0, 440.0])
    decompositions = predict_held_out(posterior, split, reference_temperature=T_REF,
                                      temperatures_by_condition=by, twin=TWIN)
    assert decompositions
    for decomposition in decompositions:
        assert "PREDICTION_OUTSIDE_CALIBRATED_CONDITIONS" in decomposition.reasons, decomposition
        assert "PREDICTION_DOMAIN_NOT_DECLARED" not in decomposition.reasons, decomposition
