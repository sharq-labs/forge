"""Identifiability under the frozen rule for either route, and predictive uncertainty with its sources kept apart."""

from __future__ import annotations

import inspect
import math

import numpy as np
import pytest

import hybrid_synthetic as S
from engcore.hybrid_uq import (
    MEASUREMENT_UNCERTAINTY,
    MODEL_DISCREPANCY_NOT_MODELLED,
    PARAMETER_UNCERTAINTY,
    UNCERTAINTY_SOURCES,
    ApproximationClass,
    HybridUQError,
    MultistartPolicy,
    RouteClaim,
    RouteReason,
    RouteRefusedError,
    assess_routed_identifiability,
    grid_predictive_uncertainty,
    linearized_predictive_uq,
    local_gaussian_posterior,
)
from engcore.hybrid_uq.identifiability import classify
from engcore.inference import AdmittedForwardTable, GridResolutionError, IdentifiabilityStatus, assess_identifiability
from engcore.scientific.ir.problem import ModelReference
from engcore.scientific.twins import TwinReference
from engcore.scientific.units.quantity import Quantity
from engcore.uq import PredictiveObservableSpec

UNIT = "dimensionless"


def _local(problem, multistart=MultistartPolicy()):
    calibration = problem.calibrate()
    return local_gaussian_posterior(calibration, problem.observations, problem.forward, multistart=multistart)


# ---------------------------------------------------------------------------
# identifiability
# ---------------------------------------------------------------------------
def test_the_routed_defaults_are_the_frozen_defaults():
    frozen = inspect.signature(assess_identifiability).parameters
    routed = inspect.signature(assess_routed_identifiability).parameters
    for name in ("correlation_threshold", "condition_threshold", "width_threshold"):
        assert routed[name].default == frozen[name].default


def _correlated():
    """Intercept and slope over x in [2, 3]: correlation about -0.99, resolvable by an axis-aligned grid of 161 nodes."""
    return S.Problem("correlated", lambda t, x: t[0] + t[1] * x, np.linspace(2.0, 3.0, 10), (0.4, 1.0), 0.05,
                     (-10.0, -10.0), (10.0, 10.0), (0.0, 0.0))


def _grids():
    affine = S.affine()
    yield "affine", affine.grid([np.linspace(0.6, 1.3, 61), np.linspace(1.4, 2.7, 61)])
    ridge = _correlated()
    mu, cov = S.gaussian_truth(ridge)
    sd = np.sqrt(np.diag(cov))
    yield "correlated_resolved", ridge.grid([np.linspace(mu[i] - 6 * sd[i], mu[i] + 6 * sd[i], 161) for i in range(2)])
    nonlinear = S.strong_nonlinearity()
    yield "nonlinear", nonlinear.grid([np.linspace(0.01, 20.0, 241), np.linspace(0.01, 10.0, 241)])
    near_zero = S.Problem("near_zero", lambda t, x: t[0] + t[1] * x, np.linspace(0, 1, 12), (0.01, 2.0), 0.05,
                          (-10.0, -10.0), (10.0, 10.0), (0.0, 0.0))
    yield "near_zero", near_zero.grid([np.linspace(-0.2, 0.2, 81), np.linspace(1.6, 2.4, 81)])


@pytest.mark.parametrize("label,grid", list(_grids()), ids=lambda v: v if isinstance(v, str) else "")
def test_the_v2_classifier_is_the_frozen_classifier_on_the_same_inputs(label, grid):
    frozen = assess_identifiability(grid)
    lows, highs = zip(*(grid.marginal_interval(i, 0.95) for i in range(len(grid.parameter_names))))
    status, condition, correlation, widths, why = classify(
        grid.mean, grid.covariance, lows, highs, grid.parameter_names, correlation_threshold=0.95,
        condition_threshold=1.0e6, width_threshold=1.0)
    assert status is frozen.status
    assert condition == frozen.condition_number and correlation == frozen.max_abs_correlation
    assert widths == frozen.relative_widths and why == frozen.why


def test_a_grid_is_classified_by_the_frozen_function_itself_refusals_included():
    weak = S.weak_identification()
    aliased = weak.grid([np.linspace(-50, 50, 401), np.linspace(-5, 5, 401)])
    with pytest.raises(GridResolutionError):
        assess_routed_identifiability(aliased)
    affine = S.affine()
    grid = affine.grid([np.linspace(0.6, 1.3, 61), np.linspace(1.4, 2.7, 61)])
    routed = assess_routed_identifiability(grid)
    assert routed.approximation_class is ApproximationClass.POSTERIOR_GRID
    assert routed.report == assess_identifiability(grid)


def test_local_and_resolved_grid_agree_on_identifiability_where_the_posterior_is_gaussian():
    for problem, axes in ((S.affine(), [np.linspace(0.6, 1.3, 61), np.linspace(1.4, 2.7, 61)]),):
        local = assess_routed_identifiability(_local(problem))
        grid = assess_routed_identifiability(problem.grid(axes))
        assert local.status is grid.status
        assert local.approximation_class is ApproximationClass.LOCAL_GAUSSIAN_APPROXIMATION
    ridge = _correlated()
    mu, cov = S.gaussian_truth(ridge)
    sd = np.sqrt(np.diag(cov))
    local = assess_routed_identifiability(_local(ridge))
    grid = assess_routed_identifiability(ridge.grid([np.linspace(mu[i] - 6 * sd[i], mu[i] + 6 * sd[i], 161) for i in range(2)]))
    assert local.status is grid.status
    assert local.report.max_abs_correlation > 0.95 and grid.report.max_abs_correlation > 0.95


def test_identifiability_depends_on_parameterization_and_says_which():
    """Knot values versus successive differences: the same Gaussian, two verdicts, two identities."""
    x = np.linspace(0.0, 1.0, 12)
    knots = S.Problem("two_knots", lambda t, x: t[0] * (1 - x) + t[1] * x, x, (3.300, 3.3005), 0.001, (2.0, 2.0), (4.0, 4.0), (3.0, 3.0))
    post = _local(knots)
    declared = assess_routed_identifiability(post)
    differences = assess_routed_identifiability(
        post.reparameterized([[1.0, 0.0], [-1.0, 1.0]], ("v0", "v1_minus_v0"), ("volt", "volt"), "successive_differences"))
    assert declared.status is IdentifiabilityStatus.IDENTIFIABLE
    assert differences.status is IdentifiabilityStatus.NOT_IDENTIFIABLE
    assert declared.parameterization_digest != differences.parameterization_digest
    assert "successive_differences" in differences.report.why


def test_a_refused_local_route_has_no_identifiability():
    with pytest.raises(RouteRefusedError):
        assess_routed_identifiability(_local(S.strong_nonlinearity()))


# ---------------------------------------------------------------------------
# predictive
# ---------------------------------------------------------------------------
def _spec(key, sigma=0.05):
    return PredictiveObservableSpec(key, UNIT, None if sigma is None else Quantity(sigma, UNIT))


def test_linearized_predictive_is_exact_for_an_affine_model_and_keeps_its_sources_apart():
    P = S.affine()
    post = _local(P)
    mu, cov = S.gaussian_truth(P)
    xs = (0.25, 0.5, 2.0)
    specs = [_spec(f"y@{x}") for x in xs]
    results = linearized_predictive_uq(post, lambda t: [Quantity(t[0] + t[1] * x, UNIT) for x in xs], specs)
    for x, r in zip(xs, results):
        g = np.asarray([1.0, x])
        expected_mean = float(g @ mu)
        expected_parameter_sd = math.sqrt(g @ cov @ g)
        # The affine model is exact; compare the optimizer-derived centre in
        # posterior-predictive sigma units rather than a SciPy-version-specific
        # absolute epsilon. 1e-6 sigma is still a very strict numerical check.
        assert abs(r.mean - expected_mean) / expected_parameter_sd < 1e-6
        assert math.isclose(r.parameter_standard_uncertainty, expected_parameter_sd, rel_tol=1e-6)
        assert r.measurement_standard_uncertainty == 0.05
        assert math.isclose(r.total_standard_uncertainty, math.hypot(r.parameter_standard_uncertainty, 0.05), rel_tol=1e-12)
        assert r.parameter_standard_uncertainty > 0.0
        assert r.total_standard_uncertainty > r.parameter_standard_uncertainty
        assert r.sources == UNCERTAINTY_SOURCES == (PARAMETER_UNCERTAINTY, MEASUREMENT_UNCERTAINTY, MODEL_DISCREPANCY_NOT_MODELLED)
        assert r.model_discrepancy == MODEL_DISCREPANCY_NOT_MODELLED
        assert r.approximation_class is ApproximationClass.LINEARIZED_PREDICTIVE_UQ
        q = 1.959963984540054
        assert math.isclose(r.parameter_interval[1] - r.mean, q * r.parameter_standard_uncertainty, rel_tol=1e-9)
        assert math.isclose(r.total_interval[1] - r.mean, q * r.total_standard_uncertainty, rel_tol=1e-9)


def test_no_declared_sigma_means_no_measurement_part_not_a_zero_one():
    P = S.affine()
    (r,) = linearized_predictive_uq(_local(P), lambda t: [Quantity(t[0] + t[1], UNIT)], [_spec("y@1", None)])
    assert r.measurement_standard_uncertainty is None
    assert r.total_standard_uncertainty == r.parameter_standard_uncertainty


def test_a_merged_total_is_rejected_by_the_record():
    P = S.affine()
    (r,) = linearized_predictive_uq(_local(P), lambda t: [Quantity(t[0] + t[1], UNIT)], [_spec("y@1")])
    import dataclasses

    with pytest.raises(HybridUQError, match="root-sum-square"):
        dataclasses.replace(r, total_standard_uncertainty=r.parameter_standard_uncertainty + 0.05)


def test_predictive_uq_refuses_a_refused_local_route():
    post = _local(S.strong_nonlinearity())
    with pytest.raises(RouteRefusedError):
        linearized_predictive_uq(post, lambda t: [Quantity(1.0, UNIT)], [_spec("y")])


def test_predictive_nonlinearity_downgrades():
    P = S.affine()
    post = _local(P)
    (r,) = linearized_predictive_uq(post, lambda t: [Quantity(math.exp(40.0 * t[1]) * 1e-35, UNIT)], [_spec("steep", 1e-9)])
    assert RouteReason.PREDICTIVE_NONLINEAR in r.reasons and r.route_claim is RouteClaim.DOWNGRADED
    assert r.predictive_nonlinearity > 0.10


def test_a_downgraded_posterior_passes_its_downgrade_to_its_predictions():
    P = S.affine()
    post = _local(P, multistart=None)
    (r,) = linearized_predictive_uq(post, lambda t: [Quantity(t[0], UNIT)], [_spec("a")])
    assert r.route_claim is RouteClaim.DOWNGRADED and RouteReason.GLOBAL_UNIQUENESS_NOT_ASSESSED in r.reasons


def test_a_linearly_mapped_posterior_has_no_forward_model_to_predict_from():
    post = _local(S.affine())
    mapped = post.reparameterized([[1.0, 0.0], [0.0, 1.0]], ("a", "b"), (UNIT, UNIT), "copy")
    with pytest.raises(HybridUQError, match="declared parameterization"):
        linearized_predictive_uq(mapped, lambda t: [Quantity(t[0], UNIT)], [_spec("a")])


def _table(problem, grid, xs):
    values = np.asarray([[row[0] + row[1] * x for x in xs] for row in grid.points])
    keys = tuple(f"y@{x}" for x in xs)
    return AdmittedForwardTable(parameter_names=grid.parameter_names, observation_keys=keys, points=grid.points, values=values,
                                admissible_mask=np.ones(len(grid.points), bool), admission_refs=tuple(("analytic",) * len(keys) for _ in grid.points),
                                rejection_reasons=tuple("" for _ in grid.points)), keys


def test_grid_predictive_wraps_the_frozen_result_and_its_refusal():
    P = S.affine()
    grid = P.grid([np.linspace(0.6, 1.3, 61), np.linspace(1.4, 2.7, 61)])
    table, keys = _table(P, grid, (0.5,))
    twin, model = TwinReference("hybrid-uq-test", "1"), ModelReference("hybrid-uq-test.model", "1")
    r = grid_predictive_uncertainty(grid, table, _spec(keys[0]), twin=twin, model=model, source_ref="test")
    assert r.approximation_class is ApproximationClass.POSTERIOR_GRID
    local = linearized_predictive_uq(_local(P), lambda t: [Quantity(t[0] + 0.5 * t[1], UNIT)], [_spec(keys[0])])[0]
    assert math.isclose(r.parameter_standard_uncertainty, local.parameter_standard_uncertainty, rel_tol=0.02)
    assert r.measurement_standard_uncertainty == 0.05
    weak = S.weak_identification()
    aliased = weak.grid([np.linspace(-50, 50, 401), np.linspace(-5, 5, 401)])
    table, keys = _table(weak, aliased, (10.0,))
    with pytest.raises(GridResolutionError):
        grid_predictive_uncertainty(aliased, table, _spec(keys[0]), twin=twin, model=model, source_ref="test")
