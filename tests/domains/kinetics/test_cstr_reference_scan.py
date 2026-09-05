"""Portability checks for the vectorized steady-state bracketing scan.

The production reference evaluates the dense *bracketing* scan with NumPy and
keeps scalar ``steady_state_residual`` + Brent refinement for the actual roots.

A previous regression test required every NumPy residual sample to be bit-for-
bit identical to the scalar ``math.exp`` path.  That is not a portable IEEE-754
contract: scalar libm and vectorized ufunc implementations may differ by a few
last-place bits on different CPU/libm combinations even when they make exactly
the same scientific decision.

What is scientifically load-bearing here is stricter and more direct:

* the two scans must make the same zero/sign-change bracketing decisions;
* the vectorized samples must remain numerically equivalent to the scalar
  expression (a guard against an algebraic rewrite, not a platform promise);
* because root refinement is still scalar Brent on the same brackets, the
  reported root temperatures must match a scalar-scan reference exactly.

These tests pin those properties on every preregistered K1 regime without
claiming cross-platform bit identity for an intermediate NumPy array.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.optimize import brentq

from src.engcore.domains.kinetics.cstr.reference import (
    _R_J_PER_MOL_K,
    steady_state_residual,
    steady_states,
)
from src.engcore.domains.kinetics.cstr.errors import ReactorConfigurationError
from src.engcore.domains.kinetics.cstr.validation import (
    MAX_VALID_TEMPERATURE_K,
    MIN_VALID_TEMPERATURE_K,
)
from experiments.kinetics_k1.k1_config import REGIMES

SCAN_POINTS = 20001
XTOL = 1.0e-12


def _physics(run) -> dict:
    return dict(
        dilution_rate_per_s=run.operation.dilution_rate_per_s,
        feed_concentration_mol_per_m3=run.operation.caf_mol_per_m3,
        feed_temperature_k=run.operation.tf_k,
        coolant_temperature_k=run.operation.tc_k,
        beta_m3_k_per_mol=run.chemistry.beta_m3_k_per_mol,
        gamma_per_s=run.gamma_per_s,
        k0_per_s=run.chemistry.k0_per_s,
        activation_energy_j_per_mol=run.chemistry.e_j_per_mol,
    )


def _scalar_scan(grid: np.ndarray, physics: dict) -> np.ndarray:
    """The original formulation: one Python call per grid point."""
    return np.array([steady_state_residual(float(t), **physics) for t in grid])


def _vector_scan(grid: np.ndarray, physics: dict) -> np.ndarray:
    """The formulation the reference now uses for bracket discovery."""
    a = physics["dilution_rate_per_s"]
    rate = physics["k0_per_s"] * np.exp(
        -physics["activation_energy_j_per_mol"] / (_R_J_PER_MOL_K * grid)
    )
    ca_star = a * physics["feed_concentration_mol_per_m3"] / (a + rate)
    return (
        a * (physics["feed_temperature_k"] - grid)
        + physics["beta_m3_k_per_mol"] * rate * ca_star
        - physics["gamma_per_s"] * (grid - physics["coolant_temperature_k"])
    )


def _brackets(grid: np.ndarray, values: np.ndarray) -> list[tuple[str, int]]:
    """Exactly the bracket-selection rule ``steady_states`` applies."""
    out: list[tuple[str, int]] = []
    for index in range(len(grid) - 1):
        left, right = float(values[index]), float(values[index + 1])
        if left == 0.0:
            out.append(("zero", index))
        elif left * right < 0.0:
            out.append(("sign", index))
    if float(values[-1]) == 0.0:
        out.append(("zero_last", len(grid) - 1))
    return out


def _scalar_root_temperatures(grid: np.ndarray, physics: dict) -> tuple[float, ...]:
    """Original scalar scan + the same scalar Brent refinement used in production."""
    values = _scalar_scan(grid, physics)

    def residual(temperature: float) -> float:
        return steady_state_residual(temperature, **physics)

    roots: list[float] = []
    for index in range(len(grid) - 1):
        left, right = float(grid[index]), float(grid[index + 1])
        f_left, f_right = float(values[index]), float(values[index + 1])
        if f_left == 0.0:
            roots.append(left)
        elif f_left * f_right < 0.0:
            roots.append(float(brentq(residual, left, right, xtol=XTOL)))
    if float(values[-1]) == 0.0:
        roots.append(float(grid[-1]))

    deduplicated: list[float] = []
    for temperature in sorted(roots):
        if deduplicated and abs(temperature - deduplicated[-1]) < 1.0e-9:
            continue
        deduplicated.append(temperature)
    return tuple(deduplicated)


REGIME_IDS = [spec.regime_id for spec in REGIMES]


@pytest.mark.parametrize("spec", REGIMES, ids=REGIME_IDS)
def test_array_and_scalar_scans_make_identical_bracketing_decisions(spec) -> None:
    physics = _physics(spec.build())
    grid = np.linspace(
        MIN_VALID_TEMPERATURE_K, MAX_VALID_TEMPERATURE_K, SCAN_POINTS
    )
    scalar = _scalar_scan(grid, physics)
    vector = _vector_scan(grid, physics)

    # The scan is consumed only through exact-zero and sign-change decisions.
    assert np.array_equal(scalar == 0.0, vector == 0.0)
    assert _brackets(grid, scalar) == _brackets(grid, vector)


@pytest.mark.parametrize("spec", REGIMES, ids=REGIME_IDS)
def test_array_scan_remains_numerically_equivalent_to_scalar_expression(spec) -> None:
    physics = _physics(spec.build())
    grid = np.linspace(
        MIN_VALID_TEMPERATURE_K, MAX_VALID_TEMPERATURE_K, SCAN_POINTS
    )
    scalar = _scalar_scan(grid, physics)
    vector = _vector_scan(grid, physics)

    assert np.all(np.isfinite(scalar))
    assert np.all(np.isfinite(vector))
    # Scalar libm and vector ufuncs are allowed a few final bits of implementation
    # variation.  This bound is only an algebraic-equivalence guard; the exact
    # scientific decision is pinned independently by the bracket/root tests.
    np.testing.assert_allclose(vector, scalar, rtol=1.0e-13, atol=1.0e-13)


@pytest.mark.parametrize("spec", REGIMES, ids=REGIME_IDS)
def test_reported_root_temperatures_match_scalar_scan_reference_exactly(spec) -> None:
    physics = _physics(spec.build())
    grid = np.linspace(
        MIN_VALID_TEMPERATURE_K, MAX_VALID_TEMPERATURE_K, SCAN_POINTS
    )
    expected = _scalar_root_temperatures(grid, physics)
    found = steady_states(
        **physics,
        search_min_k=MIN_VALID_TEMPERATURE_K,
        search_max_k=MAX_VALID_TEMPERATURE_K,
        scan_points=SCAN_POINTS,
        xtol=XTOL,
    )
    assert tuple(state.temperature_k for state in found) == expected


@pytest.mark.parametrize("spec", REGIMES, ids=REGIME_IDS)
def test_roots_stay_ordered_and_transversal(spec) -> None:
    """Ordering is part of the contract: the nearest-root comparison uses it."""
    found = steady_states(
        **_physics(spec.build()),
        search_min_k=MIN_VALID_TEMPERATURE_K,
        search_max_k=MAX_VALID_TEMPERATURE_K,
    )
    temperatures = [s.temperature_k for s in found]
    assert temperatures == sorted(temperatures)
    for state in found:
        assert MIN_VALID_TEMPERATURE_K <= state.temperature_k <= MAX_VALID_TEMPERATURE_K


# =====================================================================
# The refusals the scalar residual used to make on every call
# =====================================================================

def _valid_physics() -> dict:
    return _physics(REGIMES[0].build())


@pytest.mark.parametrize(
    "field, bad",
    (
        ("k0_per_s", 0.0),
        ("k0_per_s", -1.0),
        ("activation_energy_j_per_mol", -1.0),
    ),
)
def test_an_invalid_rate_declaration_is_still_refused(field: str, bad: float) -> None:
    """Vectorizing must not turn a refusal into a fabricated residual curve."""
    physics = _valid_physics()
    physics[field] = bad
    with pytest.raises(ReactorConfigurationError):
        steady_states(
            **physics,
            search_min_k=MIN_VALID_TEMPERATURE_K,
            search_max_k=MAX_VALID_TEMPERATURE_K,
        )
