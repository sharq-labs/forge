"""Cross-domain regression, TCR: the V2 local route agrees with the repaired resolved grid and the exact posterior."""

from __future__ import annotations

import math

import numpy as np
import pytest

from engcore.hybrid_uq import MultistartPolicy, RouteClaim, RouteDecision, route_uncertainty
from engcore.inference import CalibrationSpec, NoiseModel, calibrate, gaussian_grid_posterior
from engcore.scientific.units.quantity import Quantity
from engcore.studies import (
    TcrTruth, build_tcr_parameter_set, ols_reference_estimate, synthesize_tcr_observations, tcr_forward_evaluator, tcr_forward_table,
)

T_REF = Quantity(293.15, "kelvin")
TRUTH = TcrTruth(reference_resistance=Quantity(1.2570, "ohm"), temperature_coefficient=Quantity(0.003930, "1/kelvin"), reference_temperature=T_REF)
WIDE = [300.0, 320.0, 340.0, 360.0, 380.0, 400.0, 420.0, 440.0]
NARROW = [299.0, 299.5, 300.0, 300.5, 301.0, 301.5]


def _design(temps, nodes):
    obs = synthesize_tcr_observations(TRUTH, temps, sigma=Quantity(0.002, "ohm"), dataset_id="tcr.v2", seed=20260912)
    by = {f"T{i}": Quantity(t, "kelvin") for i, t in enumerate(temps)}
    forward = tcr_forward_evaluator(obs, reference_temperature=T_REF, temperatures_by_condition=by)
    spec = CalibrationSpec(parameters=build_tcr_parameter_set(), fixed={"reference_temperature": T_REF}, noise_model=NoiseModel(),
                           initial_point={"reference_resistance": Quantity(0.80, "ohm"), "temperature_coefficient": Quantity(0.0010, "1/kelvin")})
    fit = calibrate(spec, obs, forward, heldout_dataset_id="tcr.v2.heldout", seed=20260912)
    o = ols_reference_estimate(obs, by, T_REF)
    axes = [np.linspace(o["reference_resistance"] - 6 * o["se_reference_resistance"], o["reference_resistance"] + 6 * o["se_reference_resistance"], nodes),
            np.linspace(o["temperature_coefficient"] - 6 * o["se_temperature_coefficient"], o["temperature_coefficient"] + 6 * o["se_temperature_coefficient"], nodes)]
    grid = gaussian_grid_posterior(tcr_forward_table(obs, [(float(a), float(b)) for a in axes[0] for b in axes[1]], reference_temperature=T_REF,
                                                     temperatures_by_condition=by), obs)
    return obs, forward, fit, grid


@pytest.mark.parametrize("temps,nodes", [(WIDE, 41), (NARROW, 81)], ids=["wide", "narrow"])
def test_the_local_route_agrees_with_the_resolved_grid(temps, nodes):
    obs, forward, fit, grid = _design(temps, nodes)
    # The canonical multistart. This asked for 3 starts before audit HUQ-01; a search below max(6, 2p + 2) starts
    # can no longer stand behind a SUPPORTED claim, which is what this test asserts.
    local = route_uncertainty(calibration=fit, observations=obs, forward=forward, multistart=MultistartPolicy())
    gridded = route_uncertainty(grid=grid)
    assert local.decision is RouteDecision.LOCAL_GAUSSIAN and local.claim is RouteClaim.SUPPORTED
    assert gridded.decision is RouteDecision.GRID_AS_SUPPLIED
    gs = np.sqrt(np.diag(gridded.covariance))
    assert np.all(np.abs(np.asarray(local.mean) - np.asarray(gridded.mean)) / gs < 0.05)
    assert np.all(np.abs(np.sqrt(np.diag(local.covariance)) / gs - 1.0) < 0.05)
    assert local.identifiability.status is gridded.identifiability.status


def test_the_router_follows_v1_on_the_aliased_narrow_design_grid():
    obs, forward, fit, coarse = _design(NARROW, 41)
    result = route_uncertainty(grid=coarse, calibration=fit, observations=obs, forward=forward, multistart=MultistartPolicy(starts=3))
    assert result.considered[0]["outcome"] == "REFUSED_BY_V1"
    assert result.decision is RouteDecision.LOCAL_GAUSSIAN
    assert math.isfinite(result.covariance[0][0])
