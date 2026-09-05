from __future__ import annotations

import math

import numpy as np
import pytest

from src.engcore.inference import AdmittedForwardTable, PosteriorGrid
from src.engcore.scientific import ModelReference, Quantity, TwinReference
from src.engcore.uq import (
    PredictiveObservableSpec,
    UQProblemError,
    posterior_predictive_uq,
)


def _posterior(*, weights=(0.25, 0.75), dataset_id="posterior-a") -> PosteriorGrid:
    return PosteriorGrid(
        parameter_names=("p",),
        points=np.asarray([[0.0], [1.0]], dtype=np.float64),
        weights=np.asarray(weights, dtype=np.float64),
        log_likelihood=np.asarray([-1.0, 0.0], dtype=np.float64),
        admissible_mask=np.asarray([True, True], dtype=bool),
        dataset_id=dataset_id,
    )


def _table(*, values=(10.0, 14.0), mask=(True, True)) -> AdmittedForwardTable:
    return AdmittedForwardTable(
        parameter_names=("p",),
        observation_keys=("H1:y",),
        points=np.asarray([[0.0], [1.0]], dtype=np.float64),
        values=np.asarray([[values[0]], [values[1]]], dtype=np.float64),
        admissible_mask=np.asarray(mask, dtype=bool),
        admission_refs=(("admission:0",), ("admission:1",)),
        rejection_reasons=("", "" if mask[1] else "rejected"),
    )


def _run(*, sigma=2.0):
    return posterior_predictive_uq(
        _posterior(),
        _table(),
        PredictiveObservableSpec(
            observation_key="H1:y",
            unit="kelvin",
            observation_sigma=Quantity(sigma, "K") if sigma is not None else None,
        ),
        twin=TwinReference("system-a", "1"),
        model=ModelReference("model-a", "1"),
        source_ref="evidence:k3:test",
    )


def test_weighted_moments_and_variance_decomposition_are_exact() -> None:
    result = _run(sigma=2.0)

    # 0.25*10 + 0.75*14 = 13; weighted latent variance = 3.
    assert result.mean.magnitude_in("K") == pytest.approx(13.0, abs=1e-14)
    assert result.epistemic_variance == pytest.approx(3.0, abs=1e-14)
    assert result.total_variance == pytest.approx(7.0, abs=1e-14)
    assert result.total_variance == pytest.approx(
        result.epistemic_variance + 2.0**2,
        abs=1e-14,
    )
    assert result.epistemic_standard_uncertainty.magnitude_in("K") == pytest.approx(
        math.sqrt(3.0), abs=1e-14
    )
    assert result.total_standard_uncertainty.magnitude_in("K") == pytest.approx(
        math.sqrt(7.0), abs=1e-14
    )


def test_total_interval_uses_noise_and_is_wider_than_latent_interval() -> None:
    result = _run(sigma=2.0)

    e_lo = result.epistemic_interval.lower.magnitude_in("K")
    e_hi = result.epistemic_interval.upper.magnitude_in("K")
    t_lo = result.total_interval.lower.magnitude_in("K")
    t_hi = result.total_interval.upper.magnitude_in("K")

    assert (e_lo, e_hi) == (10.0, 14.0)
    assert t_lo < e_lo
    assert t_hi > e_hi
    assert result.epistemic_interval.confidence_level == 0.95
    assert result.total_interval.confidence_level == 0.95
    assert "gaussian_mixture" in result.total_interval.method


def test_without_observation_noise_total_equals_epistemic() -> None:
    result = _run(sigma=None)

    assert result.total_standard_uncertainty == result.epistemic_standard_uncertainty
    assert result.total_interval.lower == result.epistemic_interval.lower
    assert result.total_interval.upper == result.epistemic_interval.upper
    assert result.total_interval.method == "weighted_posterior_predictive_discrete"


def test_replay_and_serialized_summary_are_deterministic() -> None:
    first = _run(sigma=2.0)
    second = _run(sigma=2.0)

    assert first == second
    assert first.to_dict() == second.to_dict()
    assert first.posterior_dataset_id == "posterior-a"
    assert first.twin == TwinReference("system-a", "1")
    assert first.model == ModelReference("model-a", "1")
    assert first.posterior_support_size == 2


def test_parameter_support_mismatch_fails_closed() -> None:
    table = AdmittedForwardTable(
        parameter_names=("p",),
        observation_keys=("H1:y",),
        points=np.asarray([[0.0], [2.0]], dtype=np.float64),
        values=np.asarray([[10.0], [14.0]], dtype=np.float64),
        admissible_mask=np.asarray([True, True]),
        admission_refs=(("a",), ("b",)),
        rejection_reasons=("", ""),
    )

    with pytest.raises(UQProblemError, match="identical parameter support"):
        posterior_predictive_uq(
            _posterior(),
            table,
            PredictiveObservableSpec("H1:y", "K", Quantity(0.2, "K")),
            twin=TwinReference("system-a", "1"),
            model=ModelReference("model-a", "1"),
            source_ref="evidence:test",
        )


def test_posterior_mass_on_rejected_predictive_support_fails_closed() -> None:
    with pytest.raises(UQProblemError, match="refusing silent renormalization"):
        posterior_predictive_uq(
            _posterior(weights=(0.25, 0.75)),
            _table(mask=(True, False)),
            PredictiveObservableSpec("H1:y", "K", Quantity(0.2, "K")),
            twin=TwinReference("system-a", "1"),
            model=ModelReference("model-a", "1"),
            source_ref="evidence:test",
        )


def test_predictive_observable_noise_is_typed_and_dimension_checked() -> None:
    with pytest.raises(UQProblemError, match="strictly positive"):
        PredictiveObservableSpec("H1:y", "K", Quantity(0.0, "K"))

    with pytest.raises(Exception):
        PredictiveObservableSpec("H1:y", "K", Quantity(1.0, "kg"))
