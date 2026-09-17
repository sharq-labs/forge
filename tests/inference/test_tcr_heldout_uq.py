"""Stage 8B: predictive uncertainty, held-out validation, and the central proof.

The central proof, B4, is :func:`test_a_misspecified_model_converges_and_is_rejected`:

    CALIBRATION_CONVERGED + PARAMETERS_IDENTIFIABLE + HELD_OUT_VALIDATION_FAIL

on one model, in one run. A fit can succeed completely and the model still be
wrong, and nothing in the calibration layer can tell you which happened.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from engcore.inference.calibration import (
    CalibrationStatus,
    GridResolutionError,
    IdentifiabilityStatus,
    assess_identifiability,
    posterior_grid_diagnostics,
)
from engcore.inference.grid import gaussian_grid_posterior
from engcore.inference.split import DataLeakageError, ObservationSplit
from engcore.scientific.twins import TwinReference
from engcore.scientific.units.quantity import Quantity
from engcore.studies import (
    TcrTruth,
    ols_reference_estimate,
    synthesize_tcr_observations,
    tcr_forward_table,
)
from engcore.studies.calibration_study import (
    MODEL_DISCREPANCY_NOT_MODELLED,
    UNCERTAINTY_SOURCES,
    CoverageVerdict,
    HeldOutValidation,
    classify_coverage,
    predict_held_out,
    validate_held_out,
    wilson_interval,
)

OHM, KELVIN, PER_KELVIN = "ohm", "kelvin", "1/kelvin"
T_REF = Quantity(293.15, KELVIN)
SIGMA = Quantity(0.002, OHM)
TWIN = TwinReference(twin_id="conductor.copper.sample_a", version="1")

TRUTH = TcrTruth(
    reference_resistance=Quantity(1.2570, OHM),
    temperature_coefficient=Quantity(0.003930, PER_KELVIN),
    reference_temperature=T_REF,
)

CAL_T = [300.0, 320.0, 340.0, 360.0, 380.0, 400.0]
HELD_T = [310.0, 350.0, 420.0]
ALL_T = CAL_T + HELD_T
BY_CONDITION = {f"T{i}": Quantity(t, KELVIN) for i, t in enumerate(ALL_T)}
HELD_IDS = tuple(f"T{i}" for i in range(len(CAL_T), len(ALL_T)))


def build(seed=20260912, curvature=0.0, grid=21, span=6.0):
    source = synthesize_tcr_observations(
        TRUTH, ALL_T, sigma=SIGMA, dataset_id="tcr.source", seed=seed,
        curvature_per_k2=curvature,
    )
    split = ObservationSplit.partition(
        source=source,
        held_out_condition_ids=HELD_IDS,
        twin=TWIN,
        calibration_dataset_id="tcr.cal",
        heldout_dataset_id="tcr.held",
    )
    oracle = ols_reference_estimate(split.calibration, BY_CONDITION, T_REF)
    r_axis = np.linspace(
        oracle["reference_resistance"] - span * oracle["se_reference_resistance"],
        oracle["reference_resistance"] + span * oracle["se_reference_resistance"],
        grid,
    )
    a_axis = np.linspace(
        oracle["temperature_coefficient"] - span * oracle["se_temperature_coefficient"],
        oracle["temperature_coefficient"] + span * oracle["se_temperature_coefficient"],
        grid,
    )
    points = [(float(r), float(a)) for r in r_axis for a in a_axis]
    table = tcr_forward_table(
        split.calibration, points, reference_temperature=T_REF,
        temperatures_by_condition=BY_CONDITION,
    )
    posterior = gaussian_grid_posterior(table, split.calibration)
    return split, posterior


def metrics_for(split, posterior, credible_mass=0.95):
    return validate_held_out(
        posterior, split, reference_temperature=T_REF,
        temperatures_by_condition=BY_CONDITION, observation_sigma=SIGMA,
        twin=TWIN, credible_mass=credible_mass,
    )


def standardized_residuals_for(split, posterior, credible_mass=0.95):
    """The per-observation residuals `validate_held_out` scores, computed the same way it does.

    Added by I-03 part A (batch 17): the study's held-out verdict now goes through the V2 evidence
    judgement first, which REFUSES a grid whose calibration residuals the declared noise does not
    explain. For a misspecified model that refusal comes before any held-out score, so the residual
    PATTERN -- the U shape a least-squares line fitted to a quadratic leaves, which is the central
    evidence of B4 -- has to be read from the same per-observation call the study makes rather than
    from metrics that no longer exist. `assess_predictive_observation` applies no goodness-of-fit
    gate (stated as a residual of batch 17), so it answers the same question it always did.
    """
    from engcore.adequacy.predictive import assess_predictive_observation
    from engcore.studies.calibration_study import TCR_MODEL_REF
    from engcore.uq.predictive import PredictiveObservableSpec

    predictive = tcr_forward_table(
        split.held_out, [tuple(float(v) for v in row) for row in posterior.points],
        reference_temperature=T_REF, temperatures_by_condition=BY_CONDITION,
    )
    out = []
    for observation in split.held_out.observations:
        assessment = assess_predictive_observation(
            posterior, predictive,
            PredictiveObservableSpec(observation_key=observation.key, unit=OHM,
                                     observation_sigma=observation.sigma),
            observation.value, twin=TWIN, model=TCR_MODEL_REF,
            source_ref=f"study:{split.heldout_dataset_id}",
            heldout_dataset_id=split.heldout_dataset_id, credible_mass=credible_mass,
        )
        out.append(assessment.standardized_residual)
    return tuple(out)


# =====================================================================
# B1 -- predictive uncertainty, decomposed
# =====================================================================

def test_parameter_and_measurement_uncertainty_are_separately_reported():
    split, posterior = build()
    decompositions = predict_held_out(
        posterior, split, reference_temperature=T_REF,
        temperatures_by_condition=BY_CONDITION, observation_sigma=SIGMA, twin=TWIN,
    )
    assert len(decompositions) == len(HELD_T)
    for d in decompositions:
        parameter = d.parameter_sigma.magnitude_in(OHM)
        measurement = d.observation_sigma.magnitude_in(OHM)
        total = d.total_sigma.magnitude_in(OHM)

        assert parameter > 0.0
        assert measurement == pytest.approx(0.002)
        # The two are separate numbers, and the total is not either of them.
        assert total > parameter
        assert total > measurement
        # Independent Gaussian addition in quadrature, which is what the
        # declared model says -- checked rather than assumed.
        assert total == pytest.approx(math.hypot(parameter, measurement), rel=1e-6)


def test_the_parameter_interval_is_strictly_inside_the_total_interval():
    split, posterior = build()
    for d in predict_held_out(
        posterior, split, reference_temperature=T_REF,
        temperatures_by_condition=BY_CONDITION, observation_sigma=SIGMA, twin=TWIN,
    ):
        assert d.parameter_lower.magnitude_in(OHM) > d.total_lower.magnitude_in(OHM)
        assert d.parameter_upper.magnitude_in(OHM) < d.total_upper.magnitude_in(OHM)


def test_model_discrepancy_is_recorded_as_not_modelled():
    """Not silently absent, and not invented. Named."""
    split, posterior = build()
    d = predict_held_out(
        posterior, split, reference_temperature=T_REF,
        temperatures_by_condition=BY_CONDITION, observation_sigma=SIGMA, twin=TWIN,
    )[0]
    payload = d.to_dict()
    assert payload["model_discrepancy"] == MODEL_DISCREPANCY_NOT_MODELLED
    assert MODEL_DISCREPANCY_NOT_MODELLED in payload["uncertainty_sources"]
    assert set(UNCERTAINTY_SOURCES) == {
        "PARAMETER_UNCERTAINTY", "MEASUREMENT_UNCERTAINTY",
        "MODEL_DISCREPANCY_NOT_MODELLED",
    }
    assert metrics_for(split, posterior).to_dict()["model_discrepancy"] == (
        MODEL_DISCREPANCY_NOT_MODELLED
    )


# =====================================================================
# B2 -- held-out validation
# =====================================================================

def test_the_well_specified_model_passes_held_out_validation():
    split, posterior = build()
    m = metrics_for(split, posterior)
    assert m.verdict is HeldOutValidation.PASS, m.why
    assert m.n == 3
    assert m.rmse > 0.0 and m.mae > 0.0
    assert m.rmse >= m.mae  # RMSE >= MAE always; a violation means a mixed-up metric
    assert len(m.standardized_residuals) == 3
    assert math.isfinite(m.mean_log_predictive_density)
    assert m.heldout_dataset_id == "tcr.held"
    assert m.posterior_dataset_id == "tcr.cal"


def test_scoring_the_calibration_half_as_held_out_is_refused():
    """The calibration objective is not a validation metric, enforced."""
    split, posterior = build()
    swapped = ObservationSplit(
        calibration=split.held_out,
        held_out=split.calibration,
        twin=TWIN,
        source_dataset_id="tcr.source",
    )
    # the posterior was fitted on tcr.cal, which is now the HELD-OUT half
    with pytest.raises(DataLeakageError, match="HELD-OUT set"):
        metrics_for(swapped, posterior)


def test_a_posterior_from_a_foreign_dataset_cannot_be_scored():
    split, _ = build()
    _, other_posterior = build(seed=999)
    foreign = ObservationSplit(
        calibration=split.calibration,
        held_out=split.held_out,
        twin=TWIN,
        source_dataset_id="tcr.source",
    )
    object.__setattr__(other_posterior, "dataset_id", "somewhere.else")
    with pytest.raises(DataLeakageError, match="neither half"):
        metrics_for(foreign, other_posterior)


# =====================================================================
# B4 -- THE CENTRAL PROOF
# =====================================================================

def test_a_misspecified_model_converges_and_is_rejected():
    """CONVERGED + IDENTIFIABLE + HELD_OUT_VALIDATION_FAIL, in one run.

    Truth carries a quadratic temperature term the fitted linear law cannot
    represent. The model's OWN record calls itself a linearization -- it ships
    `LINEARIZATION_BAND` and `LINEARIZATION_EXCURSION_RATIO` -- so this is its
    declared limitation rather than an invented strawman.

    Everything about the fit looks healthy. The optimizer converges, the
    posterior is well resolved, and the parameters are identifiable. The model
    is still wrong, and only the held-out evidence says so.
    """
    from engcore.inference.calibration import CalibrationSpec, NoiseModel, calibrate
    from engcore.studies import build_tcr_parameter_set, tcr_forward_evaluator

    curvature = 8.0e-6
    split, posterior = build(curvature=curvature)

    spec = CalibrationSpec(
        parameters=build_tcr_parameter_set(),
        fixed={"reference_temperature": T_REF},
        initial_point={
            "reference_resistance": Quantity(0.80, OHM),
            "temperature_coefficient": Quantity(0.0010, PER_KELVIN),
        },
        noise_model=NoiseModel(),
    )
    calibration = calibrate(
        spec,
        split.calibration,
        tcr_forward_evaluator(
            split.calibration, reference_temperature=T_REF,
            temperatures_by_condition=BY_CONDITION,
        ),
        heldout_dataset_id=split.heldout_dataset_id,
        seed=20260912,
    )
    identifiability = assess_identifiability(posterior)

    # 1. the search succeeded
    assert calibration.status is CalibrationStatus.CONVERGED
    # 2. the data determines the parameters
    assert identifiability.status is IdentifiabilityStatus.IDENTIFIABLE, identifiability.why
    # 3. and the model is rejected on evidence it never saw.
    #
    # I-03 part A (batch 17) made this rejection EARLIER and STRONGER, not weaker. The study's
    # held-out verdict now routes through the V2 evidence judgement, and this model's CALIBRATION
    # residuals already exceed the declared noise -- chi-square 129.887 on 4 degrees of freedom --
    # so the grid is refused before any held-out statement is made. The claim of B4 is unchanged and
    # is now made twice over: the fit converged, the parameters are identifiable, and the model is
    # refused. What moved is the mechanism, from a FAIL verdict to a refusal, which is a stronger
    # answer than the one it replaces.
    from engcore.hybrid_uq import HybridUQError

    with pytest.raises(HybridUQError, match="MODEL_MISFIT_BEYOND_DECLARED_NOISE") as refused:
        metrics_for(split, posterior)
    assert "129.887" in str(refused.value) or "chi-square" in str(refused.value)

    # The residual PATTERN is the tell, and its shape is specific.
    #
    # This assertion was first written as "all three residuals share a sign".
    # That is wrong, and the run said so: the residuals came back
    # (+1.33, -5.39, +13.0) at 310 / 350 / 420 K. A least-squares line fitted
    # to a quadratic does not miss in one direction -- it splits the
    # difference, sitting ABOVE the data in the middle of the range and BELOW
    # it at both ends, so the residuals are U-shaped. That is the classical
    # signature of a truncated expansion, and it is stronger evidence than a
    # shared sign would have been, because noise produces it far more rarely.
    residuals = standardized_residuals_for(split, posterior)  # ordered by held-out condition
    middle = residuals[1]
    assert (middle < 0 < residuals[0]) and (middle < 0 < residuals[2]), residuals
    # and the miss is enormous relative to the declared measurement noise
    assert max(abs(r) for r in residuals) > 10.0, residuals


def test_the_well_specified_and_misspecified_runs_differ_only_in_adequacy():
    """The contrast, side by side: same verdicts everywhere except held-out."""
    clean_split, clean_posterior = build(curvature=0.0)
    bad_split, bad_posterior = build(curvature=8.0e-6)

    clean_id = assess_identifiability(clean_posterior)
    bad_id = assess_identifiability(bad_posterior)
    clean_held = metrics_for(clean_split, clean_posterior)

    assert clean_id.status is bad_id.status is IdentifiabilityStatus.IDENTIFIABLE
    assert clean_held.verdict is HeldOutValidation.PASS
    # I-03 part A (batch 17): the misspecified run is now REFUSED rather than FAILED, because its
    # calibration residuals exceed the declared noise and the study routes through the V2 judgement
    # first. The contrast this test is about is unchanged and sharper -- same convergence, same
    # identifiability, and the adequacy side is the only one that separates them -- so the
    # comparison is made on the same two quantities the FAIL verdict was read from.
    from engcore.hybrid_uq import HybridUQError

    with pytest.raises(HybridUQError, match="MODEL_MISFIT_BEYOND_DECLARED_NOISE"):
        metrics_for(bad_split, bad_posterior)
    bad_residuals = standardized_residuals_for(bad_split, bad_posterior)
    clean_residuals = standardized_residuals_for(clean_split, clean_posterior)
    assert max(abs(r) for r in bad_residuals) > 10.0 * max(abs(r) for r in clean_residuals)


# =====================================================================
# B6 -- three posterior states, three diagnoses
# =====================================================================

def test_case_a_a_resolved_posterior_is_classified_not_refused():
    split, posterior = build(grid=21, span=6.0)
    diagnostics = posterior_grid_diagnostics(posterior)
    assert diagnostics["effective_sample_size"] > 8.0
    assert max(diagnostics["spacing_to_std"]) < 1.0
    assert assess_identifiability(posterior).status is IdentifiabilityStatus.IDENTIFIABLE


def test_case_b_a_collapsed_posterior_is_a_grid_refusal():
    """Likelihood far narrower than the grid step -> refuse, do not diagnose."""
    observations = synthesize_tcr_observations(
        TRUTH, CAL_T, sigma=SIGMA, dataset_id="tcr.cal", seed=1,
    )
    true_r, true_alpha = TRUTH.vector
    points = [
        (float(r), float(a))
        for r in np.linspace(true_r - 0.25, true_r + 0.25, 41)
        for a in np.linspace(true_alpha - 0.0015, true_alpha + 0.0015, 41)
    ]
    table = tcr_forward_table(
        observations, points, reference_temperature=T_REF,
        temperatures_by_condition=BY_CONDITION,
    )
    coarse = gaussian_grid_posterior(table, observations)
    diagnostics = posterior_grid_diagnostics(coarse)

    assert diagnostics["effective_sample_size"] < 8.0
    assert max(diagnostics["spacing_to_std"]) >= 1.0  # the discriminator
    with pytest.raises(GridResolutionError, match="GRID_TOO_COARSE_FOR_INFERENCE"):
        assess_identifiability(coarse)


def _narrow_design_posterior(observations, by_condition, nodes):
    oracle = ols_reference_estimate(observations, by_condition, T_REF)
    r_axis = np.linspace(
        oracle["reference_resistance"] - 6.0 * oracle["se_reference_resistance"],
        oracle["reference_resistance"] + 6.0 * oracle["se_reference_resistance"], nodes,
    )
    a_axis = np.linspace(
        oracle["temperature_coefficient"] - 6.0 * oracle["se_temperature_coefficient"],
        oracle["temperature_coefficient"] + 6.0 * oracle["se_temperature_coefficient"], nodes,
    )
    table = tcr_forward_table(
        observations, [(float(r), float(a)) for r in r_axis for a in a_axis],
        reference_temperature=T_REF, temperatures_by_condition=by_condition,
    )
    return gaussian_grid_posterior(table, observations)


def test_case_c_a_broad_posterior_is_a_scientific_verdict_not_a_grid_refusal():
    """Weakly identified: the posterior is BROAD, and a grid that resolves it answers.

    This is what stops case B and case C collapsing into one diagnosis. The
    narrow-temperature design produces a long ridge; on a grid that samples
    the ridge ACROSS its short axis too, the answer is a scientific one.

    Correction (benchmarks/core_v1_thin_ridge_repair/ERRATA.md): this test
    used a 21-node grid and said the grid "resolves it perfectly well"
    because every axis step was 0.6 of that axis's MARGINAL sd. It did not.
    The ridge is a correlation -0.993 posterior whose thin principal sd
    falls between the lattice nodes; the 21-node grid reported that thin sd
    at 0.055x the exact posterior and a correlation of -1.00000. Axis steps
    against marginal widths cannot see a tilted ridge. The 21-node grid is
    now refused and the verdict is read from an 81-node grid (thin sd
    0.9998x exact).
    """
    narrow_t = [299.0, 299.5, 300.0, 300.5, 301.0, 301.5]
    by_condition = {f"T{i}": Quantity(t, KELVIN) for i, t in enumerate(narrow_t)}
    observations = synthesize_tcr_observations(
        TRUTH, narrow_t, sigma=SIGMA, dataset_id="tcr.narrow", seed=5,
    )

    aliased = _narrow_design_posterior(observations, by_condition, 21)
    assert max(posterior_grid_diagnostics(aliased)["spacing_to_std"]) < 1.0
    with pytest.raises(GridResolutionError, match="lattice aliasing number"):
        assess_identifiability(aliased)

    posterior = _narrow_design_posterior(observations, by_condition, 81)
    assert max(posterior_grid_diagnostics(posterior)["spacing_to_std"]) < 1.0
    report = assess_identifiability(posterior)
    # A scientific VERDICT -- weak or none, depending on how long the ridge is
    # for this draw -- and crucially not an exception. Which of the two it
    # lands on is a property of the design and the noise; what B6 requires is
    # that it is answered rather than refused.
    assert report.status in (
        IdentifiabilityStatus.WEAKLY_IDENTIFIABLE,
        IdentifiabilityStatus.NOT_IDENTIFIABLE,
    ), report.why
    assert report.status is not IdentifiabilityStatus.IDENTIFIABLE
    assert report.occupied_support_fraction > 0.0


def test_b_and_c_do_not_produce_the_same_diagnosis():
    """Stated as a comparison, because that is the actual requirement."""
    narrow_t = [299.0, 299.5, 300.0, 300.5, 301.0, 301.5]
    by_condition = {f"T{i}": Quantity(t, KELVIN) for i, t in enumerate(narrow_t)}
    broad_obs = synthesize_tcr_observations(
        TRUTH, narrow_t, sigma=SIGMA, dataset_id="n", seed=5,
    )
    # 81 nodes: the 21-node grid this test once used aliases the ridge (case C).
    broad = _narrow_design_posterior(broad_obs, by_condition, 81)
    # broad -> a verdict; collapsed -> an exception. Different in KIND, which
    # is the requirement: one is answered, the other is refused.
    broad_report = assess_identifiability(broad)
    assert broad_report.status is not IdentifiabilityStatus.IDENTIFIABLE
    assert max(posterior_grid_diagnostics(broad)["spacing_to_std"]) < 1.0

    tight_obs = synthesize_tcr_observations(
        TRUTH, CAL_T, sigma=SIGMA, dataset_id="t", seed=1,
    )
    true_r, true_alpha = TRUTH.vector
    collapsed = gaussian_grid_posterior(
        tcr_forward_table(
            tight_obs,
            [(float(r), float(a))
             for r in np.linspace(true_r - 0.25, true_r + 0.25, 41)
             for a in np.linspace(true_alpha - 0.0015, true_alpha + 0.0015, 41)],
            reference_temperature=T_REF, temperatures_by_condition=BY_CONDITION,
        ),
        tight_obs,
    )
    with pytest.raises(GridResolutionError):
        assess_identifiability(collapsed)


# =====================================================================
# B5 -- identifiability is not decided by correlation alone
# =====================================================================

def test_the_wide_span_verdict_explains_itself_despite_strong_correlation():
    _, posterior = build()
    report = assess_identifiability(posterior)
    assert report.status is IdentifiabilityStatus.IDENTIFIABLE
    assert report.max_abs_correlation > 0.8
    # the verdict says WHY strong correlation is still identifiable
    assert "correlation says a ridge exists, not that it is long" in report.why
    # and the discriminator is the marginal width
    assert max(report.relative_widths) < 1.0


def test_the_report_carries_every_measure_it_used():
    _, posterior = build()
    payload = assess_identifiability(posterior).to_dict()
    for key in (
        "condition_number", "max_abs_correlation", "relative_widths",
        "effective_sample_size", "occupied_support_fraction", "spacing_to_std",
        "thresholds", "why",
    ):
        assert key in payload, key


# =====================================================================
# B3 -- the coverage machinery itself
# =====================================================================

def test_wilson_interval_brackets_the_point_estimate():
    low, high = wilson_interval(94, 100)
    assert low < 0.94 < high
    assert 0.0 < low and high < 1.0


def test_coverage_classification_uses_the_interval_not_the_point():
    """A small study cannot claim calibration it has not earned."""
    # 9/10 covered: point estimate 0.90, but the interval is far too wide to
    # distinguish anything. INF-05 (audit): this used to be CALIBRATED because
    # the Wilson interval [0.60, 0.98] OVERLAPS the band [0.90, 1.00]; by that
    # rule 1 of 2 was calibrated too. It is not contained in the band, so it is
    # INCONCLUSIVE -- still not a claim of miscalibration, and no longer a
    # claim of calibration.
    verdict, _ = classify_coverage(9, 10, nominal=0.95, acceptance_half_width=0.05)
    assert verdict is CoverageVerdict.INCONCLUSIVE
    # 700/1000 covered: unambiguous undercoverage
    verdict, why = classify_coverage(700, 1000, nominal=0.95, acceptance_half_width=0.05)
    assert verdict is CoverageVerdict.UNDERCOVERS, why
    # 1000/1000: unambiguous overcoverage
    verdict, _ = classify_coverage(1000, 1000, nominal=0.95, acceptance_half_width=0.02)
    assert verdict is CoverageVerdict.OVERCOVERS
