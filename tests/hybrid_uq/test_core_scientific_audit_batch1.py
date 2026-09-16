"""Scientific core audit 2026-09-16, batch 1: the acceptance criteria of routed-UQ claims.

Findings CORE-001, CORE-002, CORE-003 and CORE-005 (docs/audits/CORE_SCIENTIFIC_AUDIT_2026-09-16.md). Each test
states the honest behaviour and reproduces the audited input exactly; each was recorded as a strict xfail against
``4033c22`` before its fix was written. The thresholds they exercise were preregistered in
benchmarks/core_v4_false_confidence/BATCH1_THRESHOLD_PROTOCOL.json.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

import hybrid_synthetic as S
from engcore.hybrid_uq import (
    GridRebuildPolicy,
    HybridUQError,
    MultistartPolicy,
    RouteClaim,
    RouteDecision,
    linearized_predictive_uq,
    local_gaussian_posterior,
    route_uncertainty,
)
from engcore.scientific.units.quantity import Quantity
from engcore.uq import PredictiveObservableSpec

UNIT = "dimensionless"
AUDITED = pytest.mark.xfail(strict=True, reason="reproduced at 4033c22; fixed in batch 1")


# ---------------------------------------------------------------------------
# CORE-001: no goodness-of-fit gate
# ---------------------------------------------------------------------------
def _misfit(sigma=0.01):
    x = np.linspace(0.0, 1.0, 12)
    return S.Problem("CORE001_misfit", lambda t, x: t[0] + t[1] * x, x, (1.0, 2.0), sigma, (-50.0, -50.0), (50.0, 50.0),
                     (0.0, 0.0), observed=1.0 + 2.0 * x + 3.0 * x ** 2)


@AUDITED
def test_core001_a_gross_misfit_is_refused_and_emits_no_covariance():
    """chi2 8204 on 10 dof: variance ratio 820 > 4. Was LOCAL_GAUSSIAN SUPPORTED, PARAMETERS_IDENTIFIABLE."""
    P = _misfit()
    result = route_uncertainty(calibration=P.calibrate(), observations=P.observations, forward=P.forward,
                               multistart=MultistartPolicy())
    assert result.claim is RouteClaim.REFUSED and result.covariance is None
    assert "MODEL_MISFIT_BEYOND_DECLARED_NOISE" in {r.value for r in result.local_posterior.reasons}


@AUDITED
def test_core001_a_misfit_is_not_rescued_by_rebuilding_a_grid():
    P = _misfit()
    result = route_uncertainty(calibration=P.calibrate(), observations=P.observations, forward=P.forward,
                               multistart=MultistartPolicy(), rebuild=GridRebuildPolicy(table_builder=P.table_builder()))
    assert result.decision is RouteDecision.REFUSED
    assert any(c["route"] == "GRID_REBUILT_FROM_LOCAL_COVARIANCE" and c["outcome"] == "PASSED_OVER" for c in result.considered)


@AUDITED
def test_core001_a_moderate_misfit_is_downgraded_and_says_why():
    """The same design with sigma 0.165: chi2 ~30 on 10 dof, p ~ 9e-4 and variance ratio ~3 -> downgrade, not refuse."""
    P = _misfit(sigma=0.165)
    cal = P.calibrate()
    chi = float(np.sum(np.asarray(cal.residuals) ** 2))
    from scipy.stats import chi2
    assert chi2.sf(chi, 10) < 0.01 and chi / 10 <= 4.0
    local = local_gaussian_posterior(cal, P.observations, P.forward, multistart=MultistartPolicy())
    assert local.claim is RouteClaim.DOWNGRADED
    assert "RESIDUALS_EXCEED_DECLARED_NOISE" in {r.value for r in local.reasons}
    prediction = linearized_predictive_uq(local, lambda t: [Quantity(float(t[0] + 2.0 * t[1]), UNIT)],
                                          [PredictiveObservableSpec("y@2", UNIT, Quantity(0.165, UNIT))])[0]
    assert prediction.route_claim is RouteClaim.DOWNGRADED


def test_core001_a_well_specified_fit_is_not_gated():
    P = S.affine()
    local = local_gaussian_posterior(P.calibrate(), P.observations, P.forward, multistart=MultistartPolicy())
    assert local.claim is RouteClaim.SUPPORTED


@AUDITED
def test_core001_a_misfit_supplied_grid_is_passed_over():
    P = _misfit(sigma=0.165)
    cal = P.calibrate()
    z = np.asarray(cal.estimate_vector)
    grid = P.grid([np.linspace(z[0] - 0.6, z[0] + 0.6, 61), np.linspace(z[1] - 1.0, z[1] + 1.0, 61)])
    result = route_uncertainty(grid=grid, calibration=cal, observations=P.observations, forward=P.forward,
                               multistart=MultistartPolicy())
    assert result.decision is not RouteDecision.GRID_AS_SUPPLIED
    assert result.considered[0]["reason"] == "RESIDUALS_EXCEED_DECLARED_NOISE"


# ---------------------------------------------------------------------------
# CORE-002: a supplied grid's box became the posterior
# ---------------------------------------------------------------------------
@AUDITED
def test_core002_a_parameter_the_data_never_touch_is_not_certified_on_a_supplied_grid():
    x = np.linspace(0.0, 1.0, 10)
    P = S.Problem("CORE002_structural", lambda t, x: t[0] * x + 0.0 * t[1], x, (1.0, 100.0), 0.05, (0.0, 1.0),
                  (5.0, 1000.0), (1.0, 100.0))
    grid = P.grid([np.linspace(0.9, 1.1, 21), np.linspace(95.0, 105.0, 21)])
    result = route_uncertainty(grid=grid, observations=P.observations, forward=P.forward)
    assert result.decision is not RouteDecision.GRID_AS_SUPPLIED
    assert result.considered[0]["reason"] == "GRID_DOES_NOT_CONTAIN_POSTERIOR"


@AUDITED
def test_core002_a_supplied_grid_that_truncates_the_posterior_is_passed_over():
    P = S.affine("CORE002_truncated")
    cal = P.calibrate()
    local = local_gaussian_posterior(cal, P.observations, P.forward, multistart=None)
    sd, z = np.sqrt(np.diag(np.asarray(local.covariance))), np.asarray(cal.estimate_vector)
    grid = P.grid([np.linspace(z[i] - 0.6 * sd[i], z[i] + 0.6 * sd[i], 25) for i in range(2)])
    result = route_uncertainty(grid=grid, calibration=cal, observations=P.observations, forward=P.forward)
    assert result.decision is not RouteDecision.GRID_AS_SUPPLIED
    assert result.considered[0]["reason"] == "GRID_DOES_NOT_CONTAIN_POSTERIOR"


@AUDITED
def test_core002_a_grid_without_the_evidence_it_describes_is_not_certified():
    P = S.affine()
    result = route_uncertainty(grid=P.grid([np.linspace(0.6, 1.3, 61), np.linspace(1.4, 2.7, 61)]))
    assert result.decision is RouteDecision.REFUSED
    assert result.considered[0]["reason"] == "GRID_NOT_BOUND_TO_EVIDENCE"


def test_core002_a_resolved_contained_grid_bound_to_its_evidence_is_still_used():
    P = S.affine()
    grid = P.grid([np.linspace(0.6, 1.3, 61), np.linspace(1.4, 2.7, 61)])
    result = route_uncertainty(grid=grid, calibration=P.calibrate(), observations=P.observations, forward=P.forward)
    assert result.decision is RouteDecision.GRID_AS_SUPPLIED and result.claim is RouteClaim.SUPPORTED


# ---------------------------------------------------------------------------
# CORE-003: probes only at +/-2 sd
# ---------------------------------------------------------------------------
def _tail_problem(eps=0.01, c=2.05):
    def model(t, x):
        th = float(t[0]) - 100.0
        return np.asarray([max(-c, min(c, th)), math.sqrt(eps * max(abs(th) - c, 0.0)), 0.0])
    return S.Problem("CORE003_tail", model, [0.0, 1.0, 2.0], (100.0,), 1.0, (-900.0,), (1100.0,), (100.3,),
                     observed=[0.0, 0.0, 0.0])


@AUDITED
def test_core003_a_tail_far_heavier_than_the_gaussian_is_refused():
    """The exact posterior's 95% interval is [-468, 668]; the route reported [98.04, 101.96] SUPPORTED (4.7% of the mass)."""
    P = _tail_problem()
    result = route_uncertainty(calibration=P.calibrate(), observations=P.observations, forward=P.forward,
                               multistart=MultistartPolicy())
    assert result.claim is RouteClaim.REFUSED
    assert "TAIL_HEAVIER_THAN_LOCAL_GAUSSIAN" in {r.value for r in result.local_posterior.reasons}


# ---------------------------------------------------------------------------
# CORE-005: a supplied grid was bound to its request by label
# ---------------------------------------------------------------------------
@AUDITED
def test_core005_a_grid_computed_from_other_data_under_the_same_id_is_refused():
    P = S.affine("CORE005_binding")
    cal = P.calibrate()
    other = S.affine("CORE005_binding", observed=P.observed + 5.0)
    z = np.asarray(cal.estimate_vector)
    grid = other.grid([np.linspace(z[0] + 4.85, z[0] + 5.15, 31), np.linspace(z[1] - 0.25, z[1] + 0.25, 31)])
    assert grid.dataset_id == P.observations.dataset_id
    with pytest.raises(HybridUQError, match="not this request's evidence"):
        route_uncertainty(grid=grid, calibration=cal, observations=P.observations, forward=P.forward)
