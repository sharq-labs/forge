from __future__ import annotations

import numpy as np

from src.engcore.inference import (
    AdmittedForwardTable,
    GaussianObservation,
    ObservationSet,
    gaussian_grid_posterior,
)
from src.engcore.scientific.units.quantity import Quantity


def _observations() -> ObservationSet:
    return ObservationSet(
        observations=(
            GaussianObservation(
                condition_id="c",
                observable_name="y",
                value=Quantity(1.0, "kelvin"),
                sigma=Quantity(0.2, "kelvin"),
                source_ref="unit-test",
            ),
        ),
        dataset_id="grid-unit",
    )


def test_gaussian_grid_posterior_normalizes_and_favors_closest_prediction():
    obs = _observations()
    table = AdmittedForwardTable(
        parameter_names=("theta",),
        observation_keys=obs.keys,
        points=np.asarray([[0.0], [1.0], [2.0]], dtype=np.float64),
        values=np.asarray([[0.0], [1.0], [2.0]], dtype=np.float64),
        admissible_mask=np.asarray([True, True, True]),
        admission_refs=(("a",), ("b",), ("c",)),
        rejection_reasons=("", "", ""),
    )
    posterior = gaussian_grid_posterior(table, obs)
    assert abs(float(posterior.weights.sum()) - 1.0) <= 1.0e-12
    assert int(np.argmax(posterior.weights)) == 1
    assert posterior.map_point.tolist() == [1.0]


def test_inadmissible_grid_row_gets_zero_posterior_mass():
    obs = _observations()
    table = AdmittedForwardTable(
        parameter_names=("theta",),
        observation_keys=obs.keys,
        points=np.asarray([[0.0], [1.0]], dtype=np.float64),
        values=np.asarray([[1.0], [1.0]], dtype=np.float64),
        admissible_mask=np.asarray([False, True]),
        admission_refs=((), ("admitted",)),
        rejection_reasons=("scientifically rejected", ""),
    )
    posterior = gaussian_grid_posterior(table, obs)
    assert posterior.weights[0] == 0.0
    assert posterior.weights[1] == 1.0


def test_posterior_replay_is_deterministic_on_same_numpy_path():
    obs = _observations()
    table = AdmittedForwardTable(
        parameter_names=("theta",),
        observation_keys=obs.keys,
        points=np.asarray([[0.0], [0.5], [1.0], [1.5]], dtype=np.float64),
        values=np.asarray([[0.2], [0.7], [1.1], [1.7]], dtype=np.float64),
        admissible_mask=np.asarray([True, True, True, True]),
        admission_refs=(("a",), ("b",), ("c",), ("d",)),
        rejection_reasons=("", "", "", ""),
    )
    first = gaussian_grid_posterior(table, obs)
    second = gaussian_grid_posterior(table, obs)
    assert np.array_equal(first.weights, second.weights)
    assert np.array_equal(first.log_likelihood, second.log_likelihood)
