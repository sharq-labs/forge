"""HUQ-04 (grid part): a PosteriorGrid's weights must be the posterior its log-likelihood states.

The resolution guard reads ``log_likelihood`` (aliasing, curvature); the
effective sample size and every moment read ``weights``. Nothing bound the two,
so a record could carry an honest, broad, well-resolved log-likelihood beside
sharpened weights (``weights ** 4``: the reported sd halves) or the refused
weights of an aliased grid beside a laundered log-likelihood -- and every check
passed on one array while every number was read off the other.

``PosteriorGrid`` now refuses weights that are not the normalized
``exp(log_likelihood)`` over the nodes that are admissible and have a finite
likelihood, within roundoff.
"""

from __future__ import annotations

import numpy as np
import pytest

from engcore.inference import (
    AdmittedForwardTable,
    GaussianObservation,
    InferenceProblemError,
    ObservationSet,
    PosteriorGrid,
    gaussian_grid_posterior,
)
from engcore.scientific.units.quantity import Quantity
from engcore.uq import condition_posterior_on_predictive_admission


def _honest(per_axis: int = 41) -> PosteriorGrid:
    axes = [np.linspace(0.6, 1.3, per_axis), np.linspace(1.4, 2.7, per_axis)]
    mesh = np.array(np.meshgrid(*axes, indexing="ij")).reshape(2, -1).T
    x = np.linspace(0.0, 1.0, 6)
    y = 1.0 + 2.0 * x + np.asarray([0.01, -0.02, 0.0, 0.015, -0.01, 0.005])
    obs = ObservationSet(tuple(
        GaussianObservation(f"o{i}", "y", Quantity(float(v), "dimensionless"),
                            Quantity(0.05, "dimensionless"), f"synthetic:{i}")
        for i, v in enumerate(y)), dataset_id="binding")
    table = AdmittedForwardTable(
        parameter_names=("a", "b"), observation_keys=obs.keys, points=mesh,
        values=mesh[:, [0]] + mesh[:, [1]] * x[None, :],
        admissible_mask=np.ones(len(mesh), dtype=bool),
        admission_refs=tuple(tuple("analytic" for _ in obs.keys) for _ in mesh),
        rejection_reasons=tuple("" for _ in mesh),
    )
    return gaussian_grid_posterior(table, obs)


def _rebuild(posterior: PosteriorGrid, **changes) -> PosteriorGrid:
    fields = dict(
        parameter_names=posterior.parameter_names, points=posterior.points, weights=posterior.weights,
        log_likelihood=posterior.log_likelihood, admissible_mask=posterior.admissible_mask,
        dataset_id=posterior.dataset_id,
    )
    fields.update(changes)
    return PosteriorGrid(**fields)


def test_the_honest_posterior_rebuilds():
    honest = _honest()
    again = _rebuild(honest)
    assert np.array_equal(again.weights, honest.weights)


def test_sharpened_weights_beside_the_honest_log_likelihood_are_refused():
    honest = _honest()
    sharpened = honest.weights ** 4
    sharpened = sharpened / sharpened.sum()
    sharpened = sharpened / float(sharpened.sum())
    with pytest.raises(InferenceProblemError, match="not the normalized likelihood"):
        _rebuild(honest, weights=sharpened)


def test_a_laundered_log_likelihood_beside_the_original_weights_is_refused():
    honest = _honest()
    top = honest.points[int(np.argmax(honest.weights))]
    broad = -0.5 * np.sum(((honest.points - top) / 5.0) ** 2, axis=1)
    with pytest.raises(InferenceProblemError, match="not the normalized likelihood"):
        _rebuild(honest, log_likelihood=broad)


def test_mass_on_an_inadmissible_node_is_refused():
    honest = _honest(per_axis=11)
    mask = np.array(honest.admissible_mask, copy=True)
    mask[int(np.argmax(honest.weights))] = False
    with pytest.raises(InferenceProblemError, match="mass"):
        _rebuild(honest, admissible_mask=mask)


def test_a_nan_log_likelihood_is_refused():
    honest = _honest(per_axis=11)
    ll = np.array(honest.log_likelihood, copy=True)
    ll[0] = np.nan
    with pytest.raises(InferenceProblemError, match="log-likelihood"):
        _rebuild(honest, log_likelihood=ll)


def test_a_conditioned_posterior_still_binds_its_weights():
    """K3.1 conditioning zeroes rejected mass; its record must state that in the likelihood too."""
    honest = _honest(per_axis=11)
    # a node whose mass is inside the budget but far above roundoff
    rejected = int(np.argmin(np.abs(np.log(honest.weights + 1.0e-300) - np.log(1.0e-5))))
    assert 1.0e-7 < honest.weights[rejected] < 1.0e-3
    mask = np.ones(len(honest.points), dtype=bool)
    mask[rejected] = False
    table = AdmittedForwardTable(
        parameter_names=honest.parameter_names, observation_keys=("H:y",), points=honest.points,
        values=np.ones((len(honest.points), 1)), admissible_mask=mask,
        admission_refs=tuple(("r",) if ok else () for ok in mask),
        rejection_reasons=tuple("" if ok else "rejected" for ok in mask),
    )
    assert honest.weights[rejected] > 0.0
    conditioned = condition_posterior_on_predictive_admission(
        honest, table, maximum_unsupported_mass=1.0e-3
    ).posterior
    assert conditioned.weights[rejected] == 0.0
    assert np.array_equal(_rebuild(conditioned).weights, conditioned.weights)
