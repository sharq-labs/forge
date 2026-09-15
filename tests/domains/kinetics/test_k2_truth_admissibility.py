from __future__ import annotations

import numpy as np

import pytest

from experiments.kinetics_k2.k2_config import (
    CONDITION_BY_ID,
    MULTI_CONDITION_IDS,
    OBSERVABLE_NAMES,
    PRIMARY_SEED,
    TRUTH_COORDINATES,
    chemistry_from_coordinates,
)
from experiments.kinetics_k2.k2_forward import (
    evaluate_truth_predictions,
    observation_set_from_truth_means,
)
from engcore.domains.kinetics.cstr.inference import CSTRInferenceForwardAdapter
from engcore.domains.kinetics.cstr.problem import METRIC_UNITS
from engcore.inference import (
    InferenceAdmissibilityError,
    require_admissible_numerical_prediction,
)
from engcore.scientific.results.validation import ValidationLevel
from engcore.scientific.units.quantity import Quantity
from engcore.domains.kinetics.cstr.fluids import SEBORG_TEXTBOOK_LIQUID, declare_fluid


#: Audit CAP-01, lead decision. The CSTR's single-liquid-phase conditions read
#: the fluid's own boiling and freezing temperatures and are UNKNOWN until they
#: are declared, so the frozen K-series code -- which declares none -- is
#: refused on applicability. The textbook liquid's real range is declared once,
#: in the domain (``engcore.domains.kinetics.cstr.fluids.SEBORG_TEXTBOOK_LIQUID``:
#: a dilute aqueous liquid at an assumed 101.325 kPa, 273.15-373.124 K), and a
#: solved run is assessed at the temperatures it actually reached. Runs that
#: stay liquid are admitted; runs that truly boil stay refused.
PHASE_CONDITIONS = (
    "declared_temperature_to_boiling_ratio",
    "reachable_maximum_to_boiling_ratio",
    "reachable_minimum_to_freezing_ratio",
)


def declared_liquid(chemistry):
    return declare_fluid(chemistry, SEBORG_TEXTBOOK_LIQUID)


def with_declared_liquid(run):
    from dataclasses import replace

    return replace(run, chemistry=declared_liquid(run.chemistry))


def test_k2_truth_conditions_cross_frozen_k15_boundary_and_seeded_observations_replay():
    chemistry = chemistry_from_coordinates(*TRUTH_COORDINATES)
    assert np.isclose(chemistry.k0_per_s, 1.2e9, rtol=0.0, atol=1.0e-6)
    assert np.isclose(chemistry.e_over_r_k, 8750.0, rtol=0.0, atol=1.0e-12)

    # Audit CAP-01: the frozen truth declares no liquid range, so the frozen
    # evaluation is refused on applicability ...
    with pytest.raises(InferenceAdmissibilityError, match="applicability"):
        evaluate_truth_predictions()

    # ... and with the textbook liquid's real range declared, C3 truly boils
    # (its truth trajectory peaks at 524 K against 373.124 K) and stays
    # refused, so K2 as preregistered -- all three conditions -- cannot be
    # re-derived (experiments/kinetics_k2/SUPERSEDED_CAP01.md). C1 and C2 stay
    # liquid and still cross the boundary with everything asserted below.
    liquid = declared_liquid(chemistry)
    adapter = CSTRInferenceForwardAdapter()
    assert MULTI_CONDITION_IDS == ("C1", "C2", "C3")
    with pytest.raises(InferenceAdmissibilityError, match="applicability"):
        adapter.evaluate(
            CONDITION_BY_ID["C3"].build(liquid),
            observable_names=OBSERVABLE_NAMES,
            run_id_prefix="k2-truth-C3",
        )
    liquid_ids = ("C1", "C2")
    predictions = {
        condition_id: adapter.evaluate(
            CONDITION_BY_ID[condition_id].build(liquid),
            observable_names=OBSERVABLE_NAMES,
            run_id_prefix=f"k2-truth-{condition_id}",
        )
        for condition_id in liquid_ids
    }
    assert tuple(predictions) == liquid_ids

    means: dict[str, Quantity] = {}
    for condition_id, prediction in predictions.items():
        admitted = require_admissible_numerical_prediction(prediction)
        assert ValidationLevel.NUMERICALLY_CONVERGED in admitted.attained_levels
        assert admitted.source_result.is_usable is True
        assert admitted.source_result.provenance is not None
        for observable_name in OBSERVABLE_NAMES:
            value = admitted.value(observable_name)
            assert isinstance(value, Quantity)
            value.magnitude_in(METRIC_UNITS[observable_name])
            means[f"{condition_id}:{observable_name}"] = value

    first = observation_set_from_truth_means(
        means, seed=PRIMARY_SEED, condition_ids=liquid_ids
    )
    second = observation_set_from_truth_means(
        means, seed=PRIMARY_SEED, condition_ids=liquid_ids
    )
    assert first.keys == second.keys
    assert [item.value.to_dict() for item in first.observations] == [
        item.value.to_dict() for item in second.observations
    ]
    assert all(item.sigma.magnitude > 0.0 for item in first.observations)
