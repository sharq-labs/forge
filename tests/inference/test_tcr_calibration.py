"""Stage 8A: the calibration core, proven on synthetic truth.

The seven things this file exists to establish, each with its own test:

    1. known synthetic parameters are recovered
    2. the recovery error is justified by the DECLARED noise, not by a round number
    3. the identifiable case is classified identifiable
    4. the weak/correlated case does not report false precision
    5. parameter covariance is available
    6. calibration convergence is explicitly separate from model adequacy
    7. provenance records all ten declared items

Every forward evaluation runs the production solver and crosses the analytic
admission boundary. Nothing here computes a resistance itself.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from engcore.inference.calibration import (
    CalibrationError,
    CalibrationSpec,
    CalibrationStatus,
    GridResolutionError,
    IdentifiabilityStatus,
    NoiseModel,
    assess_identifiability,
    calibrate,
    posterior_effective_sample_size,
)
from engcore.inference.grid import gaussian_grid_posterior
from engcore.inference.parameters import ParameterIdentityError
from engcore.scientific.units.quantity import Quantity
from engcore.studies import (
    TcrTruth,
    build_tcr_parameter_set,
    ols_reference_estimate,
    synthesize_tcr_observations,
    tcr_forward_evaluator,
    tcr_forward_table,
)

OHM, KELVIN, PER_KELVIN = "ohm", "kelvin", "1/kelvin"
T_REF = Quantity(293.15, KELVIN)
SIGMA = Quantity(0.002, OHM)

#: Deliberately not round numbers: a recovery test that passes because the
#: truth is 1.0 and the initial guess is 1.0 has established nothing.
TRUTH = TcrTruth(
    reference_resistance=Quantity(1.2570, OHM),
    temperature_coefficient=Quantity(0.003930, PER_KELVIN),
    reference_temperature=T_REF,
)

WIDE_SPAN = [300.0, 320.0, 340.0, 360.0, 380.0, 400.0, 420.0, 440.0]
NARROW_SPAN = [299.0, 299.5, 300.0, 300.5, 301.0, 301.5]


def conditions(temperatures):
    return {f"T{i}": Quantity(t, KELVIN) for i, t in enumerate(temperatures)}


def spec(initial=(0.80, 0.0010)):
    """A deliberately imperfect initial guess: ~36% low on R_ref, ~75% low on alpha."""
    parameters = build_tcr_parameter_set()
    return CalibrationSpec(
        parameters=parameters,
        fixed={"reference_temperature": T_REF},
        initial_point={
            "reference_resistance": Quantity(initial[0], OHM),
            "temperature_coefficient": Quantity(initial[1], PER_KELVIN),
        },
        noise_model=NoiseModel(),
    )


def run(temperatures=WIDE_SPAN, seed=20260912, curvature=0.0, initial=(0.80, 0.0010)):
    observations = synthesize_tcr_observations(
        TRUTH, temperatures, sigma=SIGMA, dataset_id="tcr.cal", seed=seed,
        curvature_per_k2=curvature,
    )
    by_condition = conditions(temperatures)
    counter: dict[str, int] = {}
    result = calibrate(
        spec(initial),
        observations,
        tcr_forward_evaluator(
            observations,
            reference_temperature=T_REF,
            temperatures_by_condition=by_condition,
            counter=counter,
        ),
        heldout_dataset_id="tcr.heldout",
        seed=seed,
    )
    return result, observations, by_condition, counter


# =====================================================================
# 1 + 2 -- recovery, graded against the declared noise
# =====================================================================

def test_the_known_parameters_are_recovered_from_a_deliberately_bad_start():
    result, observations, by_condition, _ = run()
    assert result.status is CalibrationStatus.CONVERGED

    oracle = ols_reference_estimate(observations, by_condition, T_REF)
    true_r, true_alpha = TRUTH.vector

    got_r = result.estimate_of("reference_resistance").magnitude
    got_alpha = result.estimate_of("temperature_coefficient").magnitude

    # The tolerance is FOUR standard errors, and the standard errors come from
    # the declared sigma and the design -- not from the fit's own residuals and
    # not from a round percentage. At 4 s.e. a correct estimator fails this
    # about 6 times in 100,000, which is the level a deterministic seeded test
    # can carry without being flaky.
    assert abs(got_r - true_r) <= 4.0 * oracle["se_reference_resistance"], (
        f"R_ref {got_r} vs truth {true_r}, "
        f"4 s.e. = {4.0 * oracle['se_reference_resistance']}"
    )
    assert abs(got_alpha - true_alpha) <= 4.0 * oracle["se_temperature_coefficient"], (
        f"alpha {got_alpha} vs truth {true_alpha}, "
        f"4 s.e. = {4.0 * oracle['se_temperature_coefficient']}"
    )


def test_the_optimizer_agrees_with_the_closed_form_oracle():
    """Phase 26: an independent derivation, not the optimizer grading itself.

    OLS on ``R = a + b*dT`` is exact for this model, so the two should agree to
    optimizer tolerance. They are computed from the same data by completely
    different routes -- one iterative and bounded, one a closed-form normal
    equation over the raw observation values.
    """
    result, observations, by_condition, _ = run()
    oracle = ols_reference_estimate(observations, by_condition, T_REF)

    assert result.estimate_of("reference_resistance").magnitude == pytest.approx(
        oracle["reference_resistance"], rel=1e-6
    )
    assert result.estimate_of("temperature_coefficient").magnitude == pytest.approx(
        oracle["temperature_coefficient"], rel=1e-6
    )


def test_the_objective_falls_from_the_deliberately_bad_start():
    """Phase 10's objective reduction, measured rather than assumed."""
    result, observations, by_condition, _ = run()
    evaluator = tcr_forward_evaluator(
        observations, reference_temperature=T_REF,
        temperatures_by_condition=by_condition,
    )
    start = evaluator((0.80, 0.0010))
    observed, sigma = observations.numeric_vectors()
    start_residual = (
        np.asarray([q.magnitude_in(OHM) for q in start]) - observed
    ) / sigma
    start_objective = float(np.sum(start_residual**2))

    assert result.objective_value < start_objective
    assert start_objective / result.objective_value > 1000.0


# =====================================================================
# 3 + 4 + 5 -- identifiability and parameter uncertainty
# =====================================================================

def posterior_over(temperatures, seed=20260912, curvature=0.0, sigma_span=6.0, n=41):
    """A grid sized to the posterior it has to resolve.

    The half-width is a multiple of the closed-form STANDARD ERRORS rather than
    a fixed number, because the two designs below differ in how sharp their
    likelihoods are by orders of magnitude. A fixed half-width that resolves
    the narrow-span posterior leaves the wide-span one collapsed onto a single
    grid point -- which is how the first version of this helper produced a
    "perfectly determined" parameter with a zero-width credible interval.
    `assess_identifiability` now refuses that case outright; sizing the grid is
    the caller-side half of the same lesson.
    """
    observations = synthesize_tcr_observations(
        TRUTH, temperatures, sigma=SIGMA, dataset_id="tcr.cal", seed=seed,
        curvature_per_k2=curvature,
    )
    by_condition = conditions(temperatures)
    oracle = ols_reference_estimate(observations, by_condition, T_REF)
    centre_r = oracle["reference_resistance"]
    centre_a = oracle["temperature_coefficient"]
    r_axis = np.linspace(
        centre_r - sigma_span * oracle["se_reference_resistance"],
        centre_r + sigma_span * oracle["se_reference_resistance"],
        n,
    )
    a_axis = np.linspace(
        centre_a - sigma_span * oracle["se_temperature_coefficient"],
        centre_a + sigma_span * oracle["se_temperature_coefficient"],
        n,
    )
    points = [(float(r), float(a)) for r in r_axis for a in a_axis]
    table = tcr_forward_table(
        observations, points, reference_temperature=T_REF,
        temperatures_by_condition=by_condition,
    )
    return gaussian_grid_posterior(table, observations)


def test_the_wide_span_case_is_classified_identifiable():
    report = assess_identifiability(posterior_over(WIDE_SPAN))
    assert report.status is IdentifiabilityStatus.IDENTIFIABLE, report.why
    assert report.max_abs_correlation < 0.95


def test_the_narrow_span_case_is_not_reported_as_identifiable():
    """The same model, a different DESIGN -- which is the honest comparison.

    Over a 2.5 K span the intercept and the slope cannot be separated: every
    observation is essentially at T_ref, so raising R_ref and lowering alpha
    traces a ridge the data cannot distinguish along.
    """
    report = assess_identifiability(posterior_over(NARROW_SPAN))
    assert report.status is not IdentifiabilityStatus.IDENTIFIABLE, report.why
    assert report.max_abs_correlation > 0.95


def test_the_two_designs_do_not_report_the_same_confidence():
    """Phase 11's actual requirement, stated as a comparison rather than a threshold."""
    wide = assess_identifiability(posterior_over(WIDE_SPAN))
    narrow = assess_identifiability(posterior_over(NARROW_SPAN))

    assert wide.status is not narrow.status
    assert narrow.max_abs_correlation > wide.max_abs_correlation
    # and the weak case's interval for alpha is materially wider
    assert max(narrow.relative_widths) > max(wide.relative_widths)


def test_parameter_covariance_and_intervals_are_available():
    posterior = posterior_over(WIDE_SPAN)
    covariance = posterior.covariance
    assert covariance.shape == (2, 2)
    assert np.all(np.isfinite(covariance))
    assert covariance[0, 0] > 0.0 and covariance[1, 1] > 0.0
    low, high = posterior.marginal_interval(0, 0.95)
    assert low < high
    summary = posterior.summary()
    assert summary["parameter_names"] == [
        "reference_resistance", "temperature_coefficient"
    ]
    assert "covariance" in summary and "correlation" in summary


def test_a_grid_that_cannot_resolve_the_posterior_is_refused_not_classified():
    """The false-precision trap, caught rather than reported as certainty.

    This is not hypothetical: it is what the first version of `posterior_over`
    did. A grid spanning +/-0.25 ohm at sigma = 0.002 ohm is far coarser than
    the likelihood, so every unit of posterior mass lands on ONE point. Its
    covariance is zero, its correlation numerically 1, and its 95% interval has
    zero width -- and a naive reading calls that an exquisitely determined
    parameter.

    It is refused, and the refusal says it is about the GRID rather than about
    the parameters, because "not identifiable" would be the wrong diagnosis and
    would send the next reader to fix the wrong thing.
    """
    observations = synthesize_tcr_observations(
        TRUTH, WIDE_SPAN, sigma=SIGMA, dataset_id="tcr.cal", seed=1,
    )
    true_r, true_alpha = TRUTH.vector
    points = [
        (float(r), float(a))
        for r in np.linspace(true_r - 0.25, true_r + 0.25, 41)
        for a in np.linspace(true_alpha - 0.0015, true_alpha + 0.0015, 41)
    ]
    table = tcr_forward_table(
        observations, points, reference_temperature=T_REF,
        temperatures_by_condition=conditions(WIDE_SPAN),
    )
    coarse = gaussian_grid_posterior(table, observations)

    assert posterior_effective_sample_size(coarse) == pytest.approx(1.0, abs=1e-6)
    # the collapsed posterior really does look like certainty
    low, high = coarse.marginal_interval(0, 0.95)
    assert high - low == 0.0

    with pytest.raises(GridResolutionError, match="FALSE PRECISION"):
        assess_identifiability(coarse)


def test_the_effective_sample_size_is_reported_with_the_verdict():
    report = assess_identifiability(posterior_over(WIDE_SPAN))
    assert report.effective_sample_size > 8.0
    assert report.to_dict()["effective_sample_size"] == report.effective_sample_size


def test_identifiability_thresholds_are_declared_in_the_report():
    """A verdict whose thresholds are invisible is not checkable."""
    report = assess_identifiability(posterior_over(WIDE_SPAN))
    payload = report.to_dict()
    assert payload["thresholds"]["correlation"] == 0.95
    assert payload["thresholds"]["condition_number"] == 1.0e6
    assert payload["why"]


# =====================================================================
# 6 -- convergence is not adequacy
# =====================================================================

def test_a_calibration_result_carries_no_adequacy_verdict():
    """The structural half of "convergence != adequacy".

    A `CalibrationResult` has no `adequate` field and no bare `success`
    boolean, so there is nothing on it a caller could mistake for a verdict
    about the model. The empirical half -- a converged fit that is REJECTED on
    held-out data -- is Stage 8B's misspecification case.
    """
    result, _, _, _ = run()
    assert result.status is CalibrationStatus.CONVERGED
    assert not hasattr(result, "adequate")
    assert not hasattr(result, "success")
    assert not hasattr(result, "valid")
    payload = result.to_dict()
    assert payload["status"] == "CALIBRATION_CONVERGED"
    assert "adequate" not in payload and "adequacy" not in payload


def test_a_misspecified_model_still_converges():
    """Setup for Phase 18: curvature the linear law cannot represent.

    The optimizer finds a minimum perfectly well. That is precisely the point
    -- convergence is a statement about the search, and the model being wrong
    does not stop the search from succeeding.
    """
    result, _, _, _ = run(curvature=6.0e-6)
    assert result.status is CalibrationStatus.CONVERGED
    # and the fit is measurably worse than the well-specified case
    clean, _, _, _ = run(curvature=0.0)
    assert result.objective_value > 10.0 * clean.objective_value


def test_calibration_and_identifiability_are_separate_verdicts():
    result, _, _, _ = run(temperatures=NARROW_SPAN)
    report = assess_identifiability(posterior_over(NARROW_SPAN))
    assert result.status is CalibrationStatus.CONVERGED
    assert report.status is not IdentifiabilityStatus.IDENTIFIABLE
    assert CalibrationStatus.CONVERGED.value == "CALIBRATION_CONVERGED"
    assert report.status.value.startswith("PARAMETERS_")


# =====================================================================
# 7 -- provenance
# =====================================================================

def test_provenance_records_every_declared_item():
    result, _, _, counter = run()
    p = result.provenance.to_dict()

    assert p["model_ids"] == ["electrical.material.linear_tcr_resistance@0.1.0"]
    assert p["parameter_set_digest"] == result.spec.parameters.digest
    assert p["calibration_dataset_id"] == "tcr.cal"
    assert p["heldout_dataset_id"] == "tcr.heldout"
    assert p["method"] == "bounded_least_squares_trf"
    assert p["objective"] == "gaussian_negative_log_likelihood"
    assert p["noise_model"]["kind"] == "gaussian_independent"
    assert p["noise_model"]["sigma_source"] == "declared_per_observation"
    assert p["uncertainty_method"] == "grid_posterior_covariance"
    assert p["evaluation_count"] > 0
    assert p["wall_seconds"] >= 0.0
    assert p["seed"] == 20260912

    # bounds and the initial point reach provenance through the spec digest,
    # and the spec itself serializes both
    payload = result.spec.to_dict()
    assert payload["initial_point"]["reference_resistance"]["magnitude"] == 0.80
    lower = payload["parameters"]["parameters"][0]["lower"]
    assert lower["magnitude"] == 0.0
    assert result.provenance.spec_digest == result.spec.digest

    # estimates
    assert [e.identity.name for e in result.estimates] == [
        "reference_resistance", "temperature_coefficient"
    ]


def test_provenance_does_not_carry_bulk_arrays():
    """Phase 20: identity in provenance, contents on the data plane."""
    result, _, _, _ = run()
    blob = repr(result.provenance.to_dict())
    assert len(blob) < 2000
    assert "points" not in blob and "weights" not in blob


# =====================================================================
# The declaration is held to -- Phase 5
# =====================================================================

def test_a_parameter_cannot_be_both_estimated_and_fixed():
    with pytest.raises(CalibrationError, match="both estimated and fixed"):
        CalibrationSpec(
            parameters=build_tcr_parameter_set(),
            fixed={"reference_resistance": Quantity(1.0, OHM)},
            initial_point={
                "reference_resistance": Quantity(1.0, OHM),
                "temperature_coefficient": Quantity(0.004, PER_KELVIN),
            },
        )


def test_an_initial_point_outside_the_declared_bounds_is_refused_before_running():
    with pytest.raises(ParameterIdentityError, match="outside its admissible range"):
        spec(initial=(-1.0, 0.004))


def test_an_unimplemented_noise_model_is_refused_rather_than_substituted():
    with pytest.raises(CalibrationError, match="unsupported noise model"):
        NoiseModel(kind="student_t")


def test_a_sigma_fitted_from_the_residuals_is_refused():
    with pytest.raises(CalibrationError, match="unsupported sigma source"):
        NoiseModel(sigma_source="estimated_from_residuals")


def test_every_forward_value_crossed_the_analytic_admission_boundary():
    """Phase 8: the audit trail says which boundary, per value."""
    observations = synthesize_tcr_observations(
        TRUTH, WIDE_SPAN, sigma=SIGMA, dataset_id="tcr.cal", seed=1,
    )
    table = tcr_forward_table(
        observations, [(1.25, 0.004)], reference_temperature=T_REF,
        temperatures_by_condition=conditions(WIDE_SPAN),
    )
    assert bool(table.admissible_mask[0])
    for ref in table.admission_refs[0]:
        assert ref.startswith("analytic|"), ref
