from __future__ import annotations

import math

import numpy as np
import pytest

from experiments.kinetics_k4.k4_config import (
    ARRHENIUS_MODEL_REF,
    CONSTANT_RATE_GRID_SIZE,
    CONSTANT_RATE_MODEL_REF,
    LOG_K_CONST_BOUNDS,
    chemistry_from_log_k_const,
    constant_rate_grid,
    k4_ensemble_twin,
)
from src.engcore.scientific import TwinKind


def test_constant_rate_grid_is_frozen_one_dimensional_support() -> None:
    grid = constant_rate_grid()
    assert grid.shape == (CONSTANT_RATE_GRID_SIZE, 1)
    assert grid.flags.writeable is False
    assert grid[0, 0] == pytest.approx(LOG_K_CONST_BOUNDS[0])
    assert grid[-1, 0] == pytest.approx(LOG_K_CONST_BOUNDS[1])
    assert np.all(np.diff(grid[:, 0]) > 0.0)


def test_constant_rate_realization_has_exactly_zero_activation_energy() -> None:
    midpoint = 0.5 * (LOG_K_CONST_BOUNDS[0] + LOG_K_CONST_BOUNDS[1])
    chemistry = chemistry_from_log_k_const(midpoint)
    assert chemistry.activation_energy.magnitude_in("J/mol") == 0.0
    assert chemistry.k0.magnitude_in("1/s") == pytest.approx(math.exp(midpoint))


def test_k4_twin_is_explicit_two_model_ensemble() -> None:
    twin = k4_ensemble_twin()
    assert twin.kind is TwinKind.ENSEMBLE
    assert tuple(model.key for model in twin.models) == (
        ARRHENIUS_MODEL_REF.key,
        CONSTANT_RATE_MODEL_REF.key,
    )
    assert ARRHENIUS_MODEL_REF != CONSTANT_RATE_MODEL_REF
