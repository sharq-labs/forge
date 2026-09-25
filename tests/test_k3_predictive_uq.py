from __future__ import annotations

import math

import numpy as np
import pytest

from engcore.inference import AdmittedForwardTable, PosteriorGrid
from engcore.scientific import ModelReference, Quantity, TwinReference
from engcore.uq import (
    PredictiveObservableSpec,
    UQProblemError,
    posterior_predictive_uq,
)


# INF-04 / HUQ-04 (audit): the posterior used to be two nodes weighted (0.25, 0.75),
# with a log-likelihood of [-1, 0] that did not produce those weights. Two unequal
# nodes have an effective sample size of 1.6, below the p + 1 = 2 a one-parameter
# covariance needs, and a collapsed posterior is now refused regardless of node
# count; weights are now also required to be the normalized likelihood. The 0.75
# node is split across two parameter points with the SAME predicted value, so the
# predictive mixture -- and every exact number pinned below -- is unchanged (ESS 2.9).
def _posterior(*, weights=(0.25, 0.375, 0.375), dataset_id="posterior-a") -> PosteriorGrid:
    return PosteriorGrid(
        parameter_names=("p",),
        points=np.asarray([[0.0], [1.0], [2.0]], dtype=np.float64),
        weights=np.asarray(weights, dtype=np.float64),
        log_likelihood=np.log(np.asarray(weights, dtype=np.float64)),
        admissible_mask=np.asarray([True, True, True], dtype=bool),
        dataset_id=dataset_id,
    )


def _table(
    *, values=(10.0, 14.0, 14.0), mask=(True, True, True), unit="kelvin"
) -> AdmittedForwardTable:
    return AdmittedForwardTable(
        parameter_names=("p",),
        observation_keys=("H1:y",),
        points=np.asarray([[0.0], [1.0], [2.0]], dtype=np.float64),
        values=np.asarray([[v] for v in values], dtype=np.float64),
        admissible_mask=np.asarray(mask, dtype=bool),
        admission_refs=tuple((f"numerical|p-{i}|v-{i}|b-{i}",) if ok else () for i, ok in enumerate(mask)),
        rejection_reasons=tuple("" if ok else "rejected" for ok in mask),
        observation_units=(unit,),
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


def test_predictive_values_are_converted_from_table_units() -> None:
    result = posterior_predictive_uq(
        _posterior(),
        _table(values=(1.0, 2.0, 2.0), unit="volt"),
        PredictiveObservableSpec(
            "H1:y", "millivolt", observation_sigma=Quantity(1.0, "millivolt")
        ),
        twin=TwinReference("system-a", "1"),
        model=ModelReference("model-a", "1"),
        source_ref="evidence:unit-binding",
    )
    assert result.mean.magnitude_in("millivolt") == pytest.approx(1750.0)


def test_predictive_uq_refuses_an_unbound_numeric_table() -> None:
    table = AdmittedForwardTable(
        parameter_names=("p",),
        observation_keys=("H1:y",),
        points=np.asarray([[0.0], [1.0], [2.0]], dtype=np.float64),
        values=np.asarray([[10.0], [14.0], [14.0]], dtype=np.float64),
        admissible_mask=np.asarray([True, True, True], dtype=bool),
        admission_refs=(
            ("numerical|p-0|v-0|b-0",),
            ("numerical|p-1|v-1|b-1",),
            ("numerical|p-2|v-2|b-2",),
        ),
        rejection_reasons=("", "", ""),
    )
    with pytest.raises(UQProblemError, match="declares no observation units"):
        posterior_predictive_uq(
            _posterior(),
            table,
            # noise is declared so the refusal under test is the missing unit binding, not the missing noise
            PredictiveObservableSpec("H1:y", "kelvin", Quantity(0.1, "kelvin")),
            twin=TwinReference("system-a", "1"),
            model=ModelReference("model-a", "1"),
            source_ref="evidence:unit-binding",
        )


def test_offset_scale_predictive_noise_is_kept_as_a_spread() -> None:
    result = posterior_predictive_uq(
        _posterior(),
        _table(values=(20.0, 22.0, 22.0), unit="degC"),
        PredictiveObservableSpec(
            "H1:y", "degC", observation_sigma=Quantity(1.0, "kelvin")
        ),
        twin=TwinReference("system-a", "1"),
        model=ModelReference("model-a", "1"),
        source_ref="evidence:offset-noise",
    )
    assert result.mean.magnitude_in("degC") == pytest.approx(21.5)
    assert result.epistemic_standard_uncertainty.units == "kelvin"
    assert result.total_standard_uncertainty.units == "kelvin"
    assert result.total_variance > result.epistemic_variance


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


def test_without_observation_noise_total_predictive_uq_is_refused() -> None:
    with pytest.raises(
        UQProblemError,
        match="missing uncertainty is not zero uncertainty",
    ):
        _run(sigma=None)


def test_replay_and_serialized_summary_are_deterministic() -> None:
    first = _run(sigma=2.0)
    second = _run(sigma=2.0)

    assert first == second
    assert first.to_dict() == second.to_dict()
    assert first.posterior_dataset_id == "posterior-a"
    assert first.twin == TwinReference("system-a", "1")
    assert first.model == ModelReference("model-a", "1")
    assert first.posterior_support_size == 3


def test_parameter_support_mismatch_fails_closed() -> None:
    table = AdmittedForwardTable(
        parameter_names=("p",),
        observation_keys=("H1:y",),
        points=np.asarray([[0.0], [2.0]], dtype=np.float64),
        values=np.asarray([[10.0], [14.0]], dtype=np.float64),
        admissible_mask=np.asarray([True, True]),
        admission_refs=(("numerical|p-a|v-a|b-a",), ("numerical|p-b|v-b|b-b",)),
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
            _posterior(weights=(0.25, 0.375, 0.375)),
            _table(mask=(True, True, False)),
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
