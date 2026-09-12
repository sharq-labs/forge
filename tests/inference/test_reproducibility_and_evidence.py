"""B7 and B8: evidence integrity under relabelling, and reproducibility.

B8's two halves are both tested, because only one of them is obvious:

    same inputs + same seed  -> the SAME scientific record, byte for byte
    a different seed         -> different numbers, STATISTICALLY consistent

The second is the one that catches a study which is reproducible because it is
not actually random.
"""

from __future__ import annotations

import numpy as np
import pytest

from engcore.adequacy.predictive import (
    ModelAdequacyError,
    PredictiveEvidenceIdentity,
    compare_log_predictive_scores,
)
from engcore.inference.calibration import CalibrationSpec, NoiseModel, calibrate
from engcore.inference.grid import gaussian_grid_posterior
from engcore.inference.split import DataLeakageError, ObservationSplit
from engcore.scientific.twins import TwinReference
from engcore.scientific.units.quantity import Quantity
from engcore.studies import (
    TcrTruth,
    build_tcr_parameter_set,
    ols_reference_estimate,
    synthesize_tcr_observations,
    tcr_forward_evaluator,
    tcr_forward_table,
)
from engcore.studies.calibration_study import validate_held_out

OHM, KELVIN, PER_KELVIN = "ohm", "kelvin", "1/kelvin"
T_REF = Quantity(293.15, KELVIN)
SIGMA = Quantity(0.002, OHM)
TWIN = TwinReference(twin_id="conductor.copper.sample_a", version="1")
OTHER_TWIN = TwinReference(twin_id="conductor.copper.sample_b", version="1")

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


def split_for(seed):
    source = synthesize_tcr_observations(
        TRUTH, ALL_T, sigma=SIGMA, dataset_id=f"src.{seed}", seed=seed,
    )
    return ObservationSplit.partition(
        source=source, held_out_condition_ids=HELD_IDS, twin=TWIN,
        calibration_dataset_id=f"cal.{seed}", heldout_dataset_id=f"held.{seed}",
    )


def calibrate_for(seed):
    split = split_for(seed)
    spec = CalibrationSpec(
        parameters=build_tcr_parameter_set(),
        fixed={"reference_temperature": T_REF},
        initial_point={
            "reference_resistance": Quantity(0.80, OHM),
            "temperature_coefficient": Quantity(0.0010, PER_KELVIN),
        },
        noise_model=NoiseModel(),
    )
    return split, calibrate(
        spec, split.calibration,
        tcr_forward_evaluator(
            split.calibration, reference_temperature=T_REF,
            temperatures_by_condition=BY_CONDITION,
        ),
        heldout_dataset_id=split.heldout_dataset_id, seed=seed,
    )


# =====================================================================
# B8 -- reproducibility
# =====================================================================

def test_the_same_seed_reproduces_the_observations_exactly():
    a = synthesize_tcr_observations(
        TRUTH, ALL_T, sigma=SIGMA, dataset_id="d", seed=4242,
    )
    b = synthesize_tcr_observations(
        TRUTH, ALL_T, sigma=SIGMA, dataset_id="d", seed=4242,
    )
    assert a.to_dict() == b.to_dict()


def test_the_same_seed_reproduces_the_scientific_record():
    _, first = calibrate_for(4242)
    _, second = calibrate_for(4242)

    assert first.estimate_vector == second.estimate_vector
    assert first.objective_value == second.objective_value
    assert first.status is second.status
    # the whole serialized record, not just the numbers a reader happens to
    # look at -- wall time is the one field that legitimately differs
    a, b = first.to_dict(), second.to_dict()
    a["provenance"].pop("wall_seconds")
    b["provenance"].pop("wall_seconds")
    assert a == b


def test_a_different_seed_gives_different_numbers():
    """If this passes trivially, the study is not actually random."""
    _, first = calibrate_for(1)
    _, second = calibrate_for(2)
    assert first.estimate_vector != second.estimate_vector


def test_different_seeds_remain_statistically_consistent():
    """Different draws, same distribution -- checked, not asserted.

    Twenty seeds, and the recovered parameters must scatter around the truth
    at about the scale the closed-form standard error predicts. A study that
    reproduced exactly AND scattered correctly is reproducible; one that
    reproduces exactly because it ignores its seed would fail here.
    """
    estimates = []
    for seed in range(500, 520):
        _, result = calibrate_for(seed)
        estimates.append(result.estimate_vector)
    array = np.asarray(estimates, dtype=np.float64)

    split = split_for(500)
    oracle = ols_reference_estimate(split.calibration, BY_CONDITION, T_REF)
    true_r, true_alpha = TRUTH.vector

    # centred on the truth to within a few standard errors of the MEAN
    assert abs(array[:, 0].mean() - true_r) < 3.0 * oracle[
        "se_reference_resistance"
    ] / np.sqrt(len(array))
    assert abs(array[:, 1].mean() - true_alpha) < 3.0 * oracle[
        "se_temperature_coefficient"
    ] / np.sqrt(len(array))
    # and scattered at roughly the predicted scale (factor of two either way)
    assert 0.5 < array[:, 0].std(ddof=1) / oracle["se_reference_resistance"] < 2.0
    assert 0.5 < array[:, 1].std(ddof=1) / oracle["se_temperature_coefficient"] < 2.0


def test_the_seed_and_method_reach_the_record():
    _, result = calibrate_for(7)
    provenance = result.provenance.to_dict()
    assert provenance["seed"] == 7
    assert provenance["method"] == "bounded_least_squares_trf"
    assert provenance["evaluation_count"] > 0
    assert provenance["noise_model"]["kind"] == "gaussian_independent"


def test_the_coverage_study_is_a_function_of_its_seed_schedule():
    from engcore.studies.calibration_study import run_coverage_study

    common = dict(
        truth=TRUTH, calibration_temperatures=CAL_T, heldout_temperatures=HELD_T,
        reference_temperature=T_REF, observation_sigma=SIGMA, twin=TWIN,
        grid_points_per_axis=11,
    )
    first, _, _ = run_coverage_study(seeds=[11, 12, 13], **common)
    second, _, _ = run_coverage_study(seeds=[11, 12, 13], **common)
    assert first.to_dict() == second.to_dict()
    assert first.seeds == (11, 12, 13)
    assert first.algorithm


# =====================================================================
# B7 -- evidence integrity beyond the label
# =====================================================================

def test_a_held_out_reading_relabelled_into_calibration_is_refused():
    """The probe that a dataset_id comparison cannot see."""
    split = split_for(99)
    smuggled = split.held_out.observations[0]
    relabelled = type(smuggled)(
        condition_id="T99_looks_new",
        observable_name=smuggled.observable_name,
        value=smuggled.value,
        sigma=smuggled.sigma,
        source_ref="import/second-spreadsheet",
    )
    from engcore.inference.grid import ObservationSet

    with pytest.raises(DataLeakageError, match="under different labels"):
        ObservationSplit(
            calibration=ObservationSet(
                (*split.calibration.observations, relabelled), "cal.99"
            ),
            held_out=split.held_out,
            twin=TWIN,
            source_dataset_id="src.99",
        )


def test_scoring_against_the_wrong_held_out_identity_is_refused():
    split = split_for(99)
    with pytest.raises(DataLeakageError, match="cites"):
        split.require_scored_against_held_out("held.other")


def test_two_assessments_of_different_evidence_cannot_be_compared():
    """Evidence identity, not the observation key, decides comparability."""
    base = dict(
        observation_key="T6:resistance",
        observed_value=1.30,
        unit=OHM,
        likelihood_sigma=0.002,
        heldout_dataset_id="held.99",
        posterior_dataset_id="cal.99",
        twin=TWIN,
    )
    mine = PredictiveEvidenceIdentity(**base)
    # same key, different observed value -> different evidence
    theirs = PredictiveEvidenceIdentity(**{**base, "observed_value": 1.31})
    assert mine.observation_key == theirs.observation_key
    assert mine.differences(theirs) == ("observed_value",)
    assert mine.digest != theirs.digest


def test_a_different_twin_is_different_evidence():
    base = dict(
        observation_key="T6:resistance", observed_value=1.30, unit=OHM,
        likelihood_sigma=0.002, heldout_dataset_id="held.99",
        posterior_dataset_id="cal.99",
    )
    mine = PredictiveEvidenceIdentity(**base, twin=TWIN)
    theirs = PredictiveEvidenceIdentity(**base, twin=OTHER_TWIN)
    assert mine.differences(theirs) == ("twin",)


def test_a_split_with_a_different_twin_is_a_different_split():
    a = split_for(99)
    b = ObservationSplit(
        calibration=a.calibration, held_out=a.held_out,
        twin=OTHER_TWIN, source_dataset_id="src.99",
    )
    assert a.digest != b.digest


def test_held_out_metrics_name_both_dataset_identities():
    split = split_for(99)
    oracle = ols_reference_estimate(split.calibration, BY_CONDITION, T_REF)
    r_axis = np.linspace(
        oracle["reference_resistance"] - 6 * oracle["se_reference_resistance"],
        oracle["reference_resistance"] + 6 * oracle["se_reference_resistance"], 15,
    )
    a_axis = np.linspace(
        oracle["temperature_coefficient"] - 6 * oracle["se_temperature_coefficient"],
        oracle["temperature_coefficient"] + 6 * oracle["se_temperature_coefficient"], 15,
    )
    posterior = gaussian_grid_posterior(
        tcr_forward_table(
            split.calibration, [(float(r), float(a)) for r in r_axis for a in a_axis],
            reference_temperature=T_REF, temperatures_by_condition=BY_CONDITION,
        ),
        split.calibration,
    )
    metrics = validate_held_out(
        posterior, split, reference_temperature=T_REF,
        temperatures_by_condition=BY_CONDITION, observation_sigma=SIGMA, twin=TWIN,
    )
    payload = metrics.to_dict()
    assert payload["heldout_dataset_id"] == "held.99"
    assert payload["posterior_dataset_id"] == "cal.99"
    assert payload["heldout_dataset_id"] != payload["posterior_dataset_id"]
