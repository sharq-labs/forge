"""INF-04 (P0, with HUQ-02): a grid too coarse to be checked must not certify zero uncertainty.

``_grid_resolution_refusal`` waived every check -- including the effective
sample size floor -- for a posterior over fewer admissible nodes than a local
quadratic fit needs, when called with ``discrete_posterior_passes=True``. That is
exactly how ``posterior_predictive_uq`` calls it. So a 3x3 grid spanning +/-40
standard errors, whose whole mass sits on one node (ESS 1.000), was accepted and
reported an epistemic standard uncertainty of 0.0 ohm, while a 4x4 grid of the
same span -- enough nodes to reach the checks -- was refused.

The rule fixed here: a COLLAPSED posterior (ESS below p + 1, the fewest effective
points that can carry a p-parameter covariance) is refused regardless of how
many nodes it has, before any discrete waiver. A small posterior whose mass is
genuinely spread keeps its documented exact discrete-mixture meaning.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from engcore.inference import (
    AdmittedForwardTable,
    GridResolutionError,
    PosteriorGrid,
    gaussian_grid_posterior,
    posterior_effective_sample_size,
)
from engcore.scientific.ir.problem import ModelReference
from engcore.scientific.twins import TwinReference
from engcore.scientific.units.quantity import Quantity
from engcore.studies import tcr
from engcore.uq import PredictiveObservableSpec, posterior_predictive_uq

TWIN = TwinReference("audit-inference-grid", "1")
MODEL = ModelReference("audit-inference-grid.model", "1")
T_REF = Quantity(300.0, "kelvin")
SIG = Quantity(0.002, "ohm")


def _table(points: np.ndarray, values: np.ndarray, key: str = "H:y") -> AdmittedForwardTable:
    n = points.shape[0]
    return AdmittedForwardTable(
        parameter_names=tuple(f"p{i}" for i in range(points.shape[1])),
        observation_keys=(key,),
        points=points,
        values=values.reshape(n, 1),
        admissible_mask=np.ones(n, dtype=bool),
        admission_refs=tuple((f"numerical|p-{i}|v-{i}|b-{i}",) for i in range(n)),
        rejection_reasons=tuple("" for _ in range(n)),
        observation_units=("kelvin",),
    )


def _posterior_from_log_likelihood(points: np.ndarray, log_like: np.ndarray) -> PosteriorGrid:
    weights = np.exp(log_like - log_like.max())
    weights = weights / weights.sum()
    weights = weights / float(weights.sum())
    return PosteriorGrid(
        parameter_names=tuple(f"p{i}" for i in range(points.shape[1])),
        points=points,
        weights=weights,
        log_likelihood=log_like,
        admissible_mask=np.ones(points.shape[0], dtype=bool),
        dataset_id="audit-coarse",
    )


def _uq(posterior: PosteriorGrid, values: np.ndarray):
    return posterior_predictive_uq(
        posterior,
        _table(posterior.points, values),
        PredictiveObservableSpec("H:y", "kelvin", Quantity(0.1, "kelvin")),
        twin=TWIN,
        model=MODEL,
        source_ref="audit:inf-04",
    )


def test_a_collapsed_three_by_three_grid_is_refused_by_predictive_uq():
    """Nine nodes, one step = 1.0 against a posterior sd of 0.03: ESS is 1.000."""
    axes = [np.linspace(0.0, 2.0, 3), np.linspace(1.0, 3.0, 3)]
    points = np.array(np.meshgrid(*axes, indexing="ij")).reshape(2, -1).T
    centre = np.asarray([1.0, 2.0])
    log_like = -0.5 * np.sum(((points - centre) / 0.03) ** 2, axis=1)
    posterior = _posterior_from_log_likelihood(points, log_like)
    assert posterior_effective_sample_size(posterior) == pytest.approx(1.0)
    with pytest.raises(GridResolutionError, match="effective sample size 1 is below 3"):
        _uq(posterior, points[:, 0] + 3.0 * points[:, 1])


def test_a_collapsed_one_parameter_posterior_is_refused_by_predictive_uq():
    points = np.asarray([[0.0], [1.0], [2.0]])
    log_like = -0.5 * ((points[:, 0] - 1.0) / 0.01) ** 2
    posterior = _posterior_from_log_likelihood(points, log_like)
    with pytest.raises(GridResolutionError, match="GRID_TOO_COARSE_FOR_INFERENCE"):
        _uq(posterior, 10.0 + points[:, 0])


def test_the_tcr_three_by_three_forty_standard_error_grid_is_refused():
    """The audit scenario itself, through the production forward model."""
    temps = [250.0, 300.0, 350.0, 400.0, 450.0]
    by = {f"T{i}": Quantity(t, "kelvin") for i, t in enumerate(temps)}
    truth = tcr.TcrTruth(Quantity(1.0, "ohm"), Quantity(0.004, "1/kelvin"), T_REF)
    src = tcr.synthesize_tcr_observations(truth, temps, sigma=SIG, dataset_id="cal", seed=11)
    held = tcr.synthesize_tcr_observations(truth, [440.0], sigma=SIG, dataset_id="held", seed=12)
    held_by = {"T0": Quantity(440.0, "kelvin")}
    o = tcr.ols_reference_estimate(src, by, T_REF)
    span = 40.0
    r = np.linspace(o["reference_resistance"] - span * o["se_reference_resistance"],
                    o["reference_resistance"] + span * o["se_reference_resistance"], 3)
    a = np.linspace(o["temperature_coefficient"] - span * o["se_temperature_coefficient"],
                    o["temperature_coefficient"] + span * o["se_temperature_coefficient"], 3)
    pts = [(float(x), float(y)) for x in r for y in a]
    post = gaussian_grid_posterior(
        tcr.tcr_forward_table(src, pts, reference_temperature=T_REF, temperatures_by_condition=by), src
    )
    ptable = tcr.tcr_forward_table(held, pts, reference_temperature=T_REF, temperatures_by_condition=held_by)
    assert posterior_effective_sample_size(post) < 1.001
    with pytest.raises(GridResolutionError, match="GRID_TOO_COARSE_FOR_INFERENCE"):
        posterior_predictive_uq(
            post, ptable, PredictiveObservableSpec(held.observations[0].key, "ohm", SIG),
            twin=TWIN, model=tcr.TCR_MODEL_REF, source_ref="audit:inf-04:tcr",
        )


@pytest.mark.parametrize("weights", [(0.3, 0.4, 0.3), (0.1, 0.2, 0.4, 0.2, 0.1)])
def test_a_small_posterior_whose_mass_is_spread_keeps_its_exact_mixture(weights):
    """The documented waiver survives for posteriors that are not collapsed."""
    w = np.asarray(weights)
    points = np.arange(w.size, dtype=float)[:, None]
    posterior = PosteriorGrid(parameter_names=("p0",), points=points, weights=w, log_likelihood=np.log(w),
                              admissible_mask=np.ones(w.size, dtype=bool), dataset_id="discrete")
    assert posterior_effective_sample_size(posterior) >= 2.0
    values = 10.0 + 4.0 * np.arange(w.size)
    mean = float(w @ values)
    result = _uq(posterior, values)
    assert result.epistemic_standard_uncertainty.magnitude_in("kelvin") == pytest.approx(
        math.sqrt(float(w @ (values - mean) ** 2))
    )
