"""Scientific core audit 2026-09-16, batch 2: identifiability that does not depend on units, and grid priors.

Findings CORE-004 and CORE-010 (docs/audits/CORE_SCIENTIFIC_AUDIT_2026-09-16.md), under
benchmarks/core_v4_false_confidence/BATCH2_THRESHOLD_PROTOCOL.json. Recorded as strict xfails before the fix.
"""

from __future__ import annotations

import numpy as np
import pytest

import hybrid_synthetic as S
from engcore.hybrid_uq import (
    HybridUQError,
    MultistartPolicy,
    RouteDecision,
    assess_routed_identifiability,
    grid_predictive_uncertainty,
    local_gaussian_posterior,
    route_uncertainty,
)
from engcore.inference.calibration import IdentifiabilityStatus, assess_identifiability
from engcore.scientific.twins import TwinReference
from engcore.uq import PredictiveObservableSpec

AUDITED = pytest.mark.xfail(strict=True, reason="reproduced before batch 2; fixed in batch 2")


# ---------------------------------------------------------------------------
# CORE-004: the verdict moved with a unit
# ---------------------------------------------------------------------------
def _slope_problem(scale):
    x = np.linspace(-1.0, 1.0, 12)
    obs = 3.0 + 0.5 * x + np.random.default_rng(5).normal(0, 0.01, len(x))
    return S.Problem(f"CORE004_unit{scale:g}", lambda t, x, s=scale: t[0] + t[1] * s * x, x, (3.0, 0.5 / scale), 0.01,
                     (-100.0, -100.0 / scale), (100.0, 100.0 / scale), (1.0, 0.1 / scale), observed=obs)


@AUDITED
def test_core004_the_local_verdict_does_not_depend_on_the_unit_of_a_parameter():
    verdicts = []
    for scale in (1.0, 1.0e-6):
        P = _slope_problem(scale)
        post = local_gaussian_posterior(P.calibrate(), P.observations, P.forward, multistart=MultistartPolicy())
        report = assess_routed_identifiability(post).report
        verdicts.append((report.status, round(report.condition_number, 6)))
    assert verdicts[0] == verdicts[1] and verdicts[0][0] is IdentifiabilityStatus.IDENTIFIABLE


@AUDITED
def test_core004_the_grid_verdict_does_not_depend_on_the_unit_of_a_parameter():
    verdicts = []
    for scale in (1.0, 1.0e-6):
        P = _slope_problem(scale)
        z = np.asarray(P.calibrate().estimate_vector)
        grid = P.grid([np.linspace(z[0] - 0.03, z[0] + 0.03, 61), np.linspace(z[1] - 0.06 / scale, z[1] + 0.06 / scale, 61)])
        report = assess_identifiability(grid)
        verdicts.append((report.status, round(report.condition_number, 6)))
    assert verdicts[0] == verdicts[1]


@AUDITED
def test_core004_the_verdict_says_its_widths_are_relative_to_each_parameters_declared_zero():
    P = S.affine("CORE004_zero")
    post = local_gaussian_posterior(P.calibrate(), P.observations, P.forward, multistart=MultistartPolicy())
    assert "declared zero" in assess_routed_identifiability(post).report.why


# ---------------------------------------------------------------------------
# CORE-010: node density was an undeclared prior
# ---------------------------------------------------------------------------
def _prior_problem(transform="identity"):
    x = np.linspace(0.1, 1.0, 5)
    obs = x + np.random.default_rng(11).normal(0, 0.25, len(x))
    return S.Problem("CORE010_prior", lambda t, x: t[0] * x, x, (1.0,), 0.25, (0.05,), (4.0,), (1.0,), observed=obs,
                     transforms=(transform,))


CLUSTERED = np.concatenate([np.linspace(0.05, 1.0, 350, endpoint=False), np.linspace(1.0, 4.0, 60)])


@AUDITED
@pytest.mark.parametrize("axis", [CLUSTERED, np.geomspace(0.05, 4.0, 400)], ids=["clustered", "geomspace_identity"])
def test_core010_a_grid_not_uniform_in_the_inference_coordinate_is_passed_over(axis):
    P = _prior_problem()
    result = route_uncertainty(grid=P.grid([axis]), calibration=P.calibrate(), observations=P.observations,
                               forward=P.forward)
    assert result.decision is not RouteDecision.GRID_AS_SUPPLIED
    assert result.considered[0]["reason"] == "GRID_PRIOR_NOT_UNIFORM_IN_INFERENCE_COORDINATES"


def test_core010_a_log_spaced_grid_is_the_declared_prior_of_a_log_parameter():
    P = _prior_problem("log")
    result = route_uncertainty(grid=P.grid([np.geomspace(0.05, 4.0, 400)]), calibration=P.calibrate(),
                               observations=P.observations, forward=P.forward)
    assert result.considered[0]["reason"] != "GRID_PRIOR_NOT_UNIFORM_IN_INFERENCE_COORDINATES"


def test_core010_a_linspace_grid_is_still_the_declared_prior_of_an_identity_parameter():
    P = _prior_problem()
    result = route_uncertainty(grid=P.grid([np.linspace(0.05, 4.0, 400)]), calibration=P.calibrate(),
                               observations=P.observations, forward=P.forward)
    assert result.considered[0]["reason"] != "GRID_PRIOR_NOT_UNIFORM_IN_INFERENCE_COORDINATES"


@AUDITED
def test_core010_the_standalone_grid_predictive_refuses_an_undeclared_prior_given_the_evidence():
    P = _prior_problem()
    grid = P.grid([CLUSTERED])
    table = P.table_builder()(grid.points)
    spec = PredictiveObservableSpec(observation_key=P.observations.keys[2], unit="dimensionless")
    with pytest.raises(HybridUQError, match="GRID_PRIOR_NOT_UNIFORM_IN_INFERENCE_COORDINATES"):
        grid_predictive_uncertainty(grid, table, spec, twin=TwinReference("twin.synthetic", "1"), model=S.MODEL,
                                    source_ref="audit", observations=P.observations, forward=P.forward,
                                    calibration=P.calibrate())
