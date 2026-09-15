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


# --- an unevaluated predictive probe is not evidence of linearity --------------------------------------------------------
#
# The +/-2 sd principal-axis probes are what stands behind a SUPPORTED linearized prediction. A probe outside the
# declared bounds or refused by the predictive model was never compared with the linear extrapolation, so it cannot
# leave the claim SUPPORTED just because the finite-difference points next to the estimate were admissible. Before
# this was tracked, every probe could be skipped and the record still said SUPPORTED with a nonlinearity of 0.0.


def _probe_points(post):
    """The 2p probe points linearized_predictive_uq evaluates, in inference coordinates, with their axis and sign."""
    from engcore.hybrid_uq.local_gaussian import PROBE_SD

    cov = np.asarray(post.covariance)
    z0 = np.asarray(post.inference_point)
    lam, vec = np.linalg.eigh(cov)
    return [(k, sign, z0 + sign * PROBE_SD * math.sqrt(max(float(lam[k]), 0.0)) * vec[:, k])
            for k in range(len(z0)) for sign in (1.0, -1.0)]


def _linear(t):
    return [Quantity(t[0] + 0.5 * t[1], UNIT)]


def _supported_affine_posterior():
    post = _local(S.affine())
    assert post.claim is RouteClaim.SUPPORTED and not post.reasons
    return post


def _with_bound_cutting_a_probe(post, side):
    """The same posterior with one declared bound moved inside the reach of a +/-2 sd probe, clear of the FD steps.

    A posterior's bounds can arrive with a record rather than from the fit that produced its diagnostics, so the
    predictive check has to judge the probes it actually evaluated, not the posterior's history.
    """
    import dataclasses

    z0 = np.asarray(post.inference_point)
    points = _probe_points(post)
    j = 1
    if side == "upper":
        reach = max(point[j] for _, _, point in points)
        upper = list(post.upper_bounds)
        upper[j] = z0[j] + 0.5 * (reach - z0[j])
        cut = dataclasses.replace(post, upper_bounds=tuple(upper))
        beyond = [p for p in points if p[2][j] > upper[j]]
    else:
        reach = min(point[j] for _, _, point in points)
        lower = list(post.lower_bounds)
        lower[j] = z0[j] - 0.5 * (z0[j] - reach)
        cut = dataclasses.replace(post, lower_bounds=tuple(lower))
        beyond = [p for p in points if p[2][j] < lower[j]]
    assert beyond and len(beyond) < len(points), "the bound cuts some probes and leaves others evaluated"
    h = 1.0e-5 * (np.asarray(cut.upper_bounds) - np.asarray(cut.lower_bounds))
    assert np.all(z0 + h < np.asarray(cut.upper_bounds)) and np.all(z0 - h > np.asarray(cut.lower_bounds))
    assert cut.claim is RouteClaim.SUPPORTED
    return cut


@pytest.mark.parametrize("side", ["upper", "lower"])
def test_a_probe_beyond_a_declared_bound_is_not_linearity_evidence(side):
    """Tests E (upper, the +2 sd reach) and F (lower, the -2 sd reach)."""
    complete = _supported_affine_posterior()
    post = _with_bound_cutting_a_probe(complete, side)
    (r,) = linearized_predictive_uq(post, _linear, [_spec("y@0.5")])
    assert r.route_claim is RouteClaim.DOWNGRADED
    assert RouteReason.NONLINEARITY_PROBE_INCOMPLETE in r.reasons
    assert RouteReason.PREDICTIVE_NONLINEAR not in r.reasons
    # the model is affine, so the probes that were evaluated agree with the extrapolation; that is not enough
    assert r.predictive_nonlinearity < 1e-6
    # an incomplete check changes the claim, not the numbers
    (full,) = linearized_predictive_uq(complete, _linear, [_spec("y@0.5")])
    assert full.route_claim is RouteClaim.SUPPORTED
    assert math.isclose(r.mean, full.mean, rel_tol=1e-9)
    assert math.isclose(r.parameter_standard_uncertainty, full.parameter_standard_uncertainty, rel_tol=1e-6)


@pytest.mark.parametrize("refused", ["every_probe", "one_probe"])
def test_a_probe_the_predictive_model_refuses_is_not_linearity_evidence(refused):
    """Test G. The finite-difference points next to the estimate are all admitted; the wider probes are not."""
    post = _supported_affine_posterior()
    cov_inv = np.linalg.inv(np.asarray(post.covariance))
    z0 = np.asarray(post.inference_point)
    k, sign, target = _probe_points(post)[0]
    calls = {"refused": 0, "admitted": 0}

    def predict(t):
        z = np.asarray(t, dtype=float)
        if refused == "every_probe":
            refuse = float((z - z0) @ cov_inv @ (z - z0)) > 1.0
        else:
            refuse = bool(np.allclose(z, target, rtol=0.0, atol=1e-12))
        calls["refused" if refuse else "admitted"] += 1
        return None if refuse else _linear(t)

    (r,) = linearized_predictive_uq(post, predict, [_spec("y@0.5")])
    assert calls["refused"] == (4 if refused == "every_probe" else 1)
    # 1 + 4p finite-difference calls (a step and its half, per column), then whichever probes were admitted
    assert calls["admitted"] == 1 + 4 * 2 + (0 if refused == "every_probe" else 3)
    assert r.route_claim is RouteClaim.DOWNGRADED
    assert RouteReason.NONLINEARITY_PROBE_INCOMPLETE in r.reasons
    if refused == "every_probe":
        # the exact state the unchecked code reported as SUPPORTED: no probe evaluated, nonlinearity 0.0
        assert r.predictive_nonlinearity == 0.0


def test_a_refused_probe_downgrades_the_routed_prediction_too():
    from engcore.hybrid_uq import RouteDecision, route_uncertainty, routed_predictive_uncertainty

    P = S.affine()
    result = route_uncertainty(calibration=P.calibrate(), observations=P.observations, forward=P.forward,
                               multistart=MultistartPolicy())
    assert result.decision is RouteDecision.LOCAL_GAUSSIAN and result.claim is RouteClaim.SUPPORTED
    z0 = np.asarray(result.local_posterior.inference_point)
    sd = np.asarray(result.local_posterior.standard_deviations)

    def predict(t):
        return None if np.max(np.abs(np.asarray(t) - z0) / sd) > 0.5 else _linear(t)

    (r,) = routed_predictive_uncertainty(result, [_spec("y@0.5")], predict=predict)
    assert r.route_claim is RouteClaim.DOWNGRADED and RouteReason.NONLINEARITY_PROBE_INCOMPLETE in r.reasons


def test_a_complete_linear_check_is_supported():
    """Test H: every probe evaluated, the model affine, nothing else wrong -- SUPPORTED is still reachable."""
    post = _supported_affine_posterior()
    calls = []

    def predict(t):
        calls.append(tuple(t))
        return _linear(t)

    (r,) = linearized_predictive_uq(post, predict, [_spec("y@0.5")])
    assert len(calls) == 1 + 4 * 2 + 2 * 2
    assert r.route_claim is RouteClaim.SUPPORTED and r.reasons == ()
    assert r.predictive_nonlinearity < 1e-6


def test_a_complete_nonlinear_check_still_downgrades_for_nonlinearity_not_incompleteness():
    """Test I: every probe evaluated and the prediction curves over the posterior."""
    post = _supported_affine_posterior()
    (r,) = linearized_predictive_uq(post, lambda t: [Quantity(math.exp(40.0 * t[1]) * 1e-35, UNIT)], [_spec("steep", 1e-9)])
    assert r.route_claim is RouteClaim.DOWNGRADED
    assert RouteReason.PREDICTIVE_NONLINEAR in r.reasons
    assert RouteReason.NONLINEARITY_PROBE_INCOMPLETE not in r.reasons
    assert r.predictive_nonlinearity > 0.10
