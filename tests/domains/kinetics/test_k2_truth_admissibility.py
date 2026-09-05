from __future__ import annotations

import numpy as np

from experiments.kinetics_k2.k2_config import (
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
from src.engcore.domains.kinetics.cstr.problem import METRIC_UNITS
from src.engcore.inference import require_admissible_numerical_prediction
from src.engcore.scientific.results.validation import ValidationLevel
from src.engcore.scientific.units.quantity import Quantity


def test_k2_truth_conditions_cross_frozen_k15_boundary_and_seeded_observations_replay():
    chemistry = chemistry_from_coordinates(*TRUTH_COORDINATES)
    assert np.isclose(chemistry.k0_per_s, 1.2e9, rtol=0.0, atol=1.0e-6)
    assert np.isclose(chemistry.e_over_r_k, 8750.0, rtol=0.0, atol=1.0e-12)

    predictions = evaluate_truth_predictions()
    assert tuple(predictions) == MULTI_CONDITION_IDS

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

    first = observation_set_from_truth_means(means, seed=PRIMARY_SEED)
    second = observation_set_from_truth_means(means, seed=PRIMARY_SEED)
    assert first.keys == second.keys
    assert [item.value.to_dict() for item in first.observations] == [
        item.value.to_dict() for item in second.observations
    ]
    assert all(item.sigma.magnitude > 0.0 for item in first.observations)
