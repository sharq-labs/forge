from __future__ import annotations

import numpy as np
import pytest

from src.engcore.inference import AdmittedForwardTable, PosteriorGrid
from src.engcore.uq import (
    UQProblemError,
    condition_posterior_on_predictive_admission,
)


def _safe_log_weights(weights: tuple[float, ...]) -> np.ndarray:
    values = np.asarray(weights, dtype=np.float64)
    result = np.full(values.shape, -np.inf, dtype=np.float64)
    positive = values > 0.0
    result[positive] = np.log(values[positive])
    return result


def _posterior(weights=(0.7, 0.2, 0.1), *, dataset_id="p") -> PosteriorGrid:
    points = np.asarray([[0.0], [1.0], [2.0]], dtype=np.float64)
    return PosteriorGrid(
        parameter_names=("x",),
        points=points,
        weights=np.asarray(weights, dtype=np.float64),
        log_likelihood=_safe_log_weights(tuple(weights)),
        admissible_mask=np.asarray([True, True, True]),
        dataset_id=dataset_id,
    )


def _table(mask=(True, True, False)) -> AdmittedForwardTable:
    points = np.asarray([[0.0], [1.0], [2.0]], dtype=np.float64)
    return AdmittedForwardTable(
        parameter_names=("x",),
        observation_keys=("H:y",),
        points=points,
        values=np.asarray([[10.0], [20.0], [30.0]], dtype=np.float64),
        admissible_mask=np.asarray(mask, dtype=bool),
        admission_refs=(("a",), ("b",), ()),
        rejection_reasons=("", "", "numerical convergence failed"),
    )


def test_zero_unsupported_mass_preserves_weights_exactly() -> None:
    posterior = _posterior((0.7, 0.3, 0.0))
    result = condition_posterior_on_predictive_admission(
        posterior,
        _table(),
        maximum_unsupported_mass=1.0e-12,
    )

    assert result.posterior is posterior
    assert np.array_equal(result.posterior.weights, posterior.weights)
    assert result.audit.unsupported_mass == 0.0
    assert result.audit.supported_mass == 1.0
    assert result.audit.conditioning_factor == 1.0
    assert result.audit.conditional_on_predictive_admission is False
    assert result.audit.rejected_point_indices == (2,)


def test_small_nonzero_mass_is_conditioned_and_audited() -> None:
    tiny = 1.0e-14
    posterior = _posterior((0.7, 0.3 - tiny, tiny))
    result = condition_posterior_on_predictive_admission(
        posterior,
        _table(),
        maximum_unsupported_mass=1.0e-12,
    )

    assert result.audit.unsupported_mass == pytest.approx(tiny, rel=0.0, abs=1.0e-30)
    assert result.audit.supported_mass == pytest.approx(1.0 - tiny)
    assert result.audit.conditioning_factor == pytest.approx(1.0 / (1.0 - tiny))
    assert result.audit.conditional_on_predictive_admission is True
    assert result.audit.positive_weight_rejected_point_indices == (2,)
    assert result.posterior.weights[2] == 0.0
    assert float(result.posterior.weights.sum()) == pytest.approx(1.0, abs=1.0e-15)


def test_float64_supported_sum_one_bit_above_one_is_audited_not_rejected() -> None:
    # Reproduces the scored weak-C2 shape: normalized float64 weights can sum
    # one final bit above 1 while rejected mass is positive but far below the
    # preregistered budget. The audit must preserve those measured values rather
    # than turning roundoff into a false scientific failure.
    tiny = 4.1546995154574106e-59
    posterior = _posterior((0.7, 0.3000000000000002, tiny), dataset_id="roundoff")
    result = condition_posterior_on_predictive_admission(
        posterior,
        _table(),
        maximum_unsupported_mass=1.0e-12,
    )

    assert result.audit.unsupported_mass == tiny
    assert result.audit.supported_mass == 1.0000000000000002
    assert result.audit.conditioning_factor == 0.9999999999999998
    assert abs(
        result.audit.supported_mass + result.audit.unsupported_mass - 1.0
    ) <= 1.0e-12
    assert result.audit.conditional_on_predictive_admission is True
    assert result.posterior.weights[2] == 0.0
    assert float(result.posterior.weights.sum()) == pytest.approx(1.0, abs=1.0e-15)


def test_mass_above_budget_fails_closed() -> None:
    posterior = _posterior((0.7, 0.2, 0.1))
    with pytest.raises(UQProblemError, match="exceeds declared budget"):
        condition_posterior_on_predictive_admission(
            posterior,
            _table(),
            maximum_unsupported_mass=1.0e-12,
        )


def test_parameter_support_mismatch_fails_closed() -> None:
    posterior = _posterior()
    table = AdmittedForwardTable(
        parameter_names=("x",),
        observation_keys=("H:y",),
        points=np.asarray([[0.0], [1.0], [3.0]], dtype=np.float64),
        values=np.asarray([[10.0], [20.0], [30.0]], dtype=np.float64),
        admissible_mask=np.asarray([True, True, True]),
        admission_refs=(("a",), ("b",), ("c",)),
        rejection_reasons=("", "", ""),
    )
    with pytest.raises(UQProblemError, match="identical parameter support"):
        condition_posterior_on_predictive_admission(
            posterior,
            table,
            maximum_unsupported_mass=1.0e-12,
        )


def test_audit_serialization_is_deterministic() -> None:
    tiny = 1.0e-14
    posterior = _posterior((0.7, 0.3 - tiny, tiny), dataset_id="det")
    a = condition_posterior_on_predictive_admission(
        posterior, _table(), maximum_unsupported_mass=1.0e-12
    ).audit.to_dict()
    b = condition_posterior_on_predictive_admission(
        posterior, _table(), maximum_unsupported_mass=1.0e-12
    ).audit.to_dict()
    assert a == b
    assert a["posterior_dataset_id"] == "det"
    assert a["rejection_reasons"] == ["numerical convergence failed"]
