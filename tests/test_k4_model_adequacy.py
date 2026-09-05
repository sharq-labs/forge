from __future__ import annotations

import math

import numpy as np
import pytest

from src.engcore.adequacy import (
    ModelAdequacyError,
    assess_predictive_observation,
    compare_log_predictive_scores,
)
from src.engcore.inference import AdmittedForwardTable, PosteriorGrid
from src.engcore.scientific import ModelReference, Quantity, TwinReference
from src.engcore.uq import PredictiveObservableSpec


def _posterior(dataset_id: str = "fit") -> PosteriorGrid:
    points = np.asarray([[0.0], [1.0]], dtype=np.float64)
    return PosteriorGrid(
        parameter_names=("p",),
        points=points,
        weights=np.asarray([0.25, 0.75], dtype=np.float64),
        log_likelihood=np.log(np.asarray([0.25, 0.75], dtype=np.float64)),
        admissible_mask=np.asarray([True, True]),
        dataset_id=dataset_id,
    )


def _table(mask=(True, True)) -> AdmittedForwardTable:
    return AdmittedForwardTable(
        parameter_names=("p",),
        observation_keys=("H:y",),
        points=np.asarray([[0.0], [1.0]], dtype=np.float64),
        values=np.asarray([[10.0], [14.0]], dtype=np.float64),
        admissible_mask=np.asarray(mask, dtype=bool),
        admission_refs=(("a",), ("b",) if mask[1] else ()),
        rejection_reasons=("", "" if mask[1] else "rejected"),
    )


def _spec(sigma: Quantity | None = Quantity(2.0, "kelvin")) -> PredictiveObservableSpec:
    return PredictiveObservableSpec("H:y", "kelvin", sigma)


def _refs():
    return TwinReference("t", "1"), ModelReference("m", "1")


def test_exact_finite_mixture_cdf_and_log_density() -> None:
    twin, model = _refs()
    observed = Quantity(12.0, "kelvin")
    result = assess_predictive_observation(
        _posterior(),
        _table(),
        _spec(),
        observed,
        twin=twin,
        model=model,
        source_ref="heldout:test",
    )

    # Symmetric component offsets around y, but asymmetric mixture weights.
    # Each component has z = +/-1 at y=12 and sigma=2.
    from scipy.special import ndtr

    expected_cdf = 0.25 * float(ndtr(1.0)) + 0.75 * float(ndtr(-1.0))
    component_pdf = math.exp(-0.5) / (2.0 * math.sqrt(2.0 * math.pi))
    expected_log_density = math.log(component_pdf)

    assert result.predictive_cdf == pytest.approx(expected_cdf, abs=1e-15)
    assert result.log_predictive_density == pytest.approx(expected_log_density, abs=1e-15)
    assert result.two_sided_tail_probability == pytest.approx(
        2.0 * min(expected_cdf, 1.0 - expected_cdf), abs=1e-15
    )
    assert result.model == model
    assert result.twin == twin
    assert result.posterior_dataset_id == "fit"


def test_unit_conversion_is_applied_before_scoring() -> None:
    twin, model = _refs()
    a = assess_predictive_observation(
        _posterior(), _table(), _spec(), Quantity(12.0, "kelvin"),
        twin=twin, model=model, source_ref="a"
    )
    b = assess_predictive_observation(
        _posterior(), _table(), _spec(), Quantity(-261.15, "degC"),
        twin=twin, model=model, source_ref="b"
    )
    assert a.predictive_cdf == pytest.approx(b.predictive_cdf, abs=1e-15)
    assert a.log_predictive_density == pytest.approx(b.log_predictive_density, abs=1e-15)


def test_missing_observation_noise_fails_closed() -> None:
    twin, model = _refs()
    with pytest.raises(ModelAdequacyError, match="requires declared observation noise"):
        assess_predictive_observation(
            _posterior(), _table(), _spec(None), Quantity(12.0, "kelvin"),
            twin=twin, model=model, source_ref="heldout"
        )


def test_positive_mass_on_rejected_predictive_support_fails_closed() -> None:
    twin, model = _refs()
    with pytest.raises(ModelAdequacyError, match="rejects parameter support carrying posterior mass"):
        assess_predictive_observation(
            _posterior(), _table((True, False)), _spec(), Quantity(12.0, "kelvin"),
            twin=twin, model=model, source_ref="heldout"
        )


def test_log_score_comparison_is_paired_and_model_bound() -> None:
    twin = TwinReference("t", "1")
    ma = ModelReference("a", "1")
    mb = ModelReference("b", "1")
    posterior = _posterior()
    table = _table()
    spec = _spec()
    obs = Quantity(12.0, "kelvin")
    aa = assess_predictive_observation(
        posterior, table, spec, obs, twin=twin, model=ma, source_ref="a"
    )
    bb = assess_predictive_observation(
        posterior, table, spec, obs, twin=twin, model=mb, source_ref="b"
    )
    comparison = compare_log_predictive_scores(ma, (aa,), mb, (bb,))
    assert comparison.delta_a_minus_b == pytest.approx(0.0)
    assert comparison.preferred_model is None

    with pytest.raises(ModelAdequacyError, match="different ModelReference"):
        compare_log_predictive_scores(ma, (bb,), mb, (bb,))


def test_assessment_serialization_is_deterministic() -> None:
    twin, model = _refs()
    kwargs = dict(
        posterior=_posterior(),
        predictive_table=_table(),
        spec=_spec(),
        observed=Quantity(12.0, "kelvin"),
        twin=twin,
        model=model,
        source_ref="det",
    )
    assert assess_predictive_observation(**kwargs).to_dict() == assess_predictive_observation(**kwargs).to_dict()
