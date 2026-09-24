"""A grid that cannot resolve a thin, tilted posterior ridge must be refused, not certified.

The frozen resolution check compared each AXIS step with that axis's MARGINAL
standard deviation. A lattice sum of a Gaussian differs from its integral by
terms exp(-k^T Sigma k / 2) at every reciprocal-lattice vector k = 2 pi n / h
(Poisson summation). Along a coordinate axis k^T Sigma k = (2 pi sigma_i / h_i)^2,
which the old check bounds; along an OFF-AXIS n aligned with a thin principal
direction it can be << 1 while every marginal is wide. The grid then returns
moments that are stable under refinement and wrong, and the guard accepted them.

Reviewed in benchmarks/core_gap_thin_ridge (commit 273bfff). The cases below are
the committed ones: the HD-UQ F5 ridge, the TCR narrow-span design, and the
frozen K2 kinetics grid (fixture regenerated with K2's own builder, reproducing
experiments/kinetics_k2/k2_report.md to 1e-9). Healthy controls: TCR wide and
the B3 battery P2/P3 grids, whose exact posteriors are known.

Materiality is fixed here and not moved: a grid is materially wrong when a
marginal mean is off by more than 0.1 true sd, a marginal sd ratio leaves
[0.9, 1.1], or the sd along the true thin principal direction leaves [0.9, 1.1].
"""

from __future__ import annotations

import json
import math
import pathlib

import numpy as np
import pytest

from engcore.inference import (
    AdmittedForwardTable,
    GaussianObservation,
    GridResolutionError,
    ObservationSet,
    PosteriorGrid,
    assess_identifiability,
    gaussian_grid_posterior,
)
from engcore.scientific.ir.problem import ModelReference
from engcore.scientific.twins import TwinReference
from engcore.scientific.units.quantity import Quantity
from engcore.uq import PredictiveObservableSpec, posterior_predictive_uq

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "grid_resolution"
TWIN = TwinReference("grid-resolution-regression", "1")
MODEL = ModelReference("grid-resolution-regression.model", "1")

#: The committed F5 observations (benchmarks/core_gap_hd_uq/FAILURE_CASES.json, seed 20260913).
F5_Y = (4.012109370682078, 3.993802969724079, 4.028708261476341, 4.01713738737486, 4.008245240318426, 4.012439099280156)
F5_X = np.linspace(10.0, 10.05, 6)
F5_SIGMA = 0.01
F5_LOWER, F5_UPPER = np.asarray([-50.0, -5.0]), np.asarray([50.0, 5.0])

# =====================================================================
# construction helpers (no private Core names)
# =====================================================================

def _synthetic_posterior(label, predict, y, sigma, axes):
    obs = ObservationSet(tuple(
        GaussianObservation(condition_id=f"o{i}", observable_name="y", value=Quantity(float(v), "dimensionless"),
                            sigma=Quantity(float(sigma), "dimensionless"), source_ref=f"synthetic:{label}:{i}")
        for i, v in enumerate(y)), dataset_id=f"grid-resolution.{label}")
    mesh = np.array(np.meshgrid(*axes, indexing="ij")).reshape(len(axes), -1).T
    table = AdmittedForwardTable(
        parameter_names=tuple(f"t{i + 1}" for i in range(len(axes))), observation_keys=obs.keys, points=mesh,
        values=np.asarray(predict(mesh), dtype=float), admissible_mask=np.ones(len(mesh), dtype=bool),
        admission_refs=tuple(tuple(f"analytic|{label}|ver|bind" for _ in obs.keys) for _ in mesh), rejection_reasons=tuple("" for _ in mesh),
        observation_units=tuple(o.value.units for o in obs.observations))
    return gaussian_grid_posterior(table, obs)


def _gaussian_posterior(label, mu, sigma, axes):
    """A grid posterior whose frozen likelihood IS N(mu, sigma): admitted linear observations y = L^-1 theta."""
    A = np.linalg.inv(np.linalg.cholesky(sigma))
    return _synthetic_posterior(label, lambda pts: pts @ A.T, A @ mu, 1.0, axes)


def _f5_exact():
    X = np.column_stack([np.ones(6), F5_X]) / F5_SIGMA
    cov = np.linalg.inv(X.T @ X)
    return cov @ X.T @ (np.asarray(F5_Y) / F5_SIGMA), cov


def _f5_posterior(axes, label):
    return _synthetic_posterior(label, lambda pts: pts[:, [0]] + pts[:, [1]] * F5_X[None, :], F5_Y, F5_SIGMA, axes)


def _fixture_posterior(name, dataset_id):
    """Rebuild a PosteriorGrid with the frozen weight arithmetic from stored axes and log-likelihood."""
    z = np.load(FIXTURES / f"{name}.npz", allow_pickle=False)
    axes = [z[f"axis{i}"] for i in range(len([k for k in z.files if k.startswith("axis")]))]
    points = np.array(np.meshgrid(*axes, indexing="ij")).reshape(len(axes), -1).T
    ll = np.asarray(z["log_likelihood"], dtype=np.float64)
    finite = np.isfinite(ll)
    unnormalized = np.zeros_like(ll)
    unnormalized[finite] = np.exp(ll[finite] - float(np.max(ll[finite])))
    weights = unnormalized / float(np.sum(unnormalized))
    weights = weights / float(np.sum(weights))
    posterior = PosteriorGrid(parameter_names=tuple(f"t{i + 1}" for i in range(len(axes))), points=points, weights=weights,
                              log_likelihood=ll, admissible_mask=z["admissible_mask"], dataset_id=dataset_id)
    return posterior, z


def _thin_direction_sd_ratio(grid_cov, true_cov):
    lam, vec = np.linalg.eigh(true_cov)
    u = vec[:, 0]
    return math.sqrt(max(float(u @ grid_cov @ u), 0.0)) / math.sqrt(lam[0])


def _material(post, mu, cov):
    sd_t = np.sqrt(np.diag(cov))
    mean_err = float(np.max(np.abs(post.mean - mu) / sd_t))
    ratio = np.sqrt(np.diag(post.covariance)) / sd_t
    thin = _thin_direction_sd_ratio(post.covariance, cov)
    return mean_err > 0.1 or ratio.min() < 0.9 or ratio.max() > 1.1 or not 0.9 <= thin <= 1.1


def _epistemic_sd(posterior, values):
    obs_key = "pred:y"
    table = AdmittedForwardTable(parameter_names=posterior.parameter_names, observation_keys=(obs_key,), points=posterior.points,
                                 values=np.asarray(values, float)[:, None], admissible_mask=posterior.admissible_mask,
                                 admission_refs=tuple((("analytic|fixture|ver|bind",) if ok else ()) for ok in posterior.admissible_mask),
                                 rejection_reasons=tuple("" if ok else "inadmissible" for ok in posterior.admissible_mask),
                                 observation_units=("dimensionless",))
    uq = posterior_predictive_uq(posterior, table, PredictiveObservableSpec(obs_key, "dimensionless", None), twin=TWIN, model=MODEL,
                                 source_ref="prediction")
    return uq.epistemic_standard_uncertainty.magnitude


def _tcr(temps, per_axis=41, sigma_span=6.0):
    from engcore.studies import TcrTruth, ols_reference_estimate, synthesize_tcr_observations, tcr_forward_table
    t_ref = Quantity(293.15, "kelvin")
    truth = TcrTruth(reference_resistance=Quantity(1.2570, "ohm"), temperature_coefficient=Quantity(0.003930, "1/kelvin"), reference_temperature=t_ref)
    obs = synthesize_tcr_observations(truth, temps, sigma=Quantity(0.002, "ohm"), dataset_id="tcr.cal", seed=20260912)
    by = {f"T{i}": Quantity(t, "kelvin") for i, t in enumerate(temps)}
    oracle = ols_reference_estimate(obs, by, t_ref)
    ra = np.linspace(oracle["reference_resistance"] - sigma_span * oracle["se_reference_resistance"], oracle["reference_resistance"] + sigma_span * oracle["se_reference_resistance"], per_axis)
    aa = np.linspace(oracle["temperature_coefficient"] - sigma_span * oracle["se_temperature_coefficient"], oracle["temperature_coefficient"] + sigma_span * oracle["se_temperature_coefficient"], per_axis)
    posterior = gaussian_grid_posterior(tcr_forward_table(obs, [(float(a), float(b)) for a in ra for b in aa], reference_temperature=t_ref, temperatures_by_condition=by), obs)
    # exact posterior of the closed-form law by dense quadrature along the local principal axes
    y = np.asarray([o.value.magnitude_in("ohm") for o in obs.observations])
    dT = np.asarray([by[o.condition_id].magnitude_in("kelvin") for o in obs.observations]) - 293.15
    mu0 = np.asarray([oracle["reference_resistance"], oracle["temperature_coefficient"]])
    J = np.column_stack([1 + mu0[1] * dT, mu0[0] * dT]) / 0.002
    lam, V = np.linalg.eigh(np.linalg.inv(J.T @ J))
    g = np.linspace(-12, 12, 1201)
    A, B = np.meshgrid(g * math.sqrt(lam[0]), g * math.sqrt(lam[1]), indexing="ij")
    th = mu0 + np.stack([A.ravel(), B.ravel()], axis=1) @ V.T
    chi = np.sum(((th[:, [0]] * (1 + th[:, [1]] * dT[None, :]) - y[None, :]) / 0.002) ** 2, axis=1)
    w = np.exp(-0.5 * (chi - chi.min()))
    w /= w.sum()
    m = w @ th
    return posterior, m, (th - m).T @ ((th - m) * w[:, None])


def _k2_proxy_covariance():
    path = pathlib.Path(__file__).resolve().parents[2] / "benchmarks" / "core_gap_hd_uq" / "DOMAIN_KINETICS.json"
    return np.asarray(json.loads(path.read_text(encoding="utf-8"))["MULTI"]["local_gaussian"]["posterior"]["covariance"])


# =====================================================================
# the reference proves the defect is material (independent of the guard)
# =====================================================================

@pytest.fixture(scope="module")
def f5_bounds():
    return _f5_posterior([np.linspace(F5_LOWER[i], F5_UPPER[i], 801) for i in range(2)], "f5.bounds.801")


@pytest.fixture(scope="module")
def tcr_narrow():
    return _tcr([299.0, 299.5, 300.0, 300.5, 301.0, 301.5])


@pytest.fixture(scope="module")
def tcr_wide():
    return _tcr([300.0, 320.0, 340.0, 360.0, 380.0, 400.0, 420.0, 440.0])


@pytest.fixture(scope="module")
def k2_multi():
    return _fixture_posterior("k2_multi", "K2-seed-20260809")


def test_f5_grid_is_materially_wrong_and_bit_stable_under_refinement(f5_bounds):
    mu, cov = _f5_exact()
    assert _material(f5_bounds, mu, cov)
    assert float(np.max(np.abs(f5_bounds.mean - mu) / np.sqrt(np.diag(cov)))) > 1.0
    coarse = _f5_posterior([np.linspace(F5_LOWER[i], F5_UPPER[i], 201) for i in range(2)], "f5.bounds.201")
    assert np.allclose(coarse.mean, f5_bounds.mean, rtol=1e-9) and np.allclose(coarse.covariance, f5_bounds.covariance, rtol=1e-9)


def test_tcr_narrow_grid_is_wrong_in_its_thin_direction(tcr_narrow):
    posterior, m, C = tcr_narrow
    assert _thin_direction_sd_ratio(posterior.covariance, C) < 0.8
    assert np.allclose(np.sqrt(np.diag(posterior.covariance)) / np.sqrt(np.diag(C)), 1.0, atol=0.01)  # marginals right


def test_k2_fixture_reproduces_the_committed_report_and_collapses_its_thin_direction(k2_multi):
    posterior, _ = k2_multi
    assert np.allclose(posterior.mean, [20.979314794931746, 8775.076414950117], rtol=1e-9)
    assert np.allclose(np.sqrt(np.diag(posterior.covariance)), [0.15202805349527396, 49.51789691706498], rtol=1e-9)
    assert _thin_direction_sd_ratio(posterior.covariance, _k2_proxy_covariance()) < 0.2


def test_healthy_controls_are_right_including_their_thin_direction(tcr_wide):
    posterior, m, C = tcr_wide
    assert not _material(posterior, m, C)
    for name in ("battery_p2", "battery_p3"):
        post, z = _fixture_posterior(name, name)
        assert not _material(post, z["exact_linear_gaussian_mean"], z["exact_linear_gaussian_covariance"]), name


# =====================================================================
# the guard: refuse what it cannot resolve, keep what it can
# =====================================================================

def test_the_f5_thin_ridge_is_refused(f5_bounds):
    with pytest.raises(GridResolutionError):
        assess_identifiability(f5_bounds)


def test_the_tcr_narrow_design_grid_is_refused(tcr_narrow):
    with pytest.raises(GridResolutionError):
        assess_identifiability(tcr_narrow[0])


def test_the_k2_multi_grid_is_refused(k2_multi):
    with pytest.raises(GridResolutionError):
        assess_identifiability(k2_multi[0])


def test_healthy_grids_are_still_classified(tcr_wide):
    assess_identifiability(tcr_wide[0])
    for name in ("battery_p2", "battery_p3"):
        assess_identifiability(_fixture_posterior(name, name)[0])


def test_a_tcr_narrow_grid_that_resolves_the_ridge_is_classified_and_right():
    posterior, m, C = _tcr([299.0, 299.5, 300.0, 300.5, 301.0, 301.5], per_axis=161)
    assert not _material(posterior, m, C)
    assert assess_identifiability(posterior).status.value != "PARAMETERS_IDENTIFIABLE"


# =====================================================================
# ESS: effectively one point is never a certified covariance
# =====================================================================

def test_k2_effective_sample_size_near_one_is_refused_even_with_small_axis_spacing(k2_multi):
    posterior, _ = k2_multi
    weights = posterior.weights
    assert 1.0 / float(np.sum(weights ** 2)) < 2.0
    with pytest.raises(GridResolutionError):
        assess_identifiability(posterior)


def test_mass_on_one_node_is_refused_even_when_the_fitted_curvature_looks_resolved():
    """ESS 1.56 with 0.22 sd axis spacing and aliasing number ~6900: only the ESS floor sees it."""
    axes = [np.linspace(-3.0, 3.0, 41)] * 2
    points = np.array(np.meshgrid(*axes, indexing="ij")).reshape(2, -1).T
    broad = np.exp(-0.125 * np.sum(points ** 2, axis=1))
    weights = 0.2 * broad / broad.sum() + 0.8 * np.all(points == 0.0, axis=1)
    posterior = PosteriorGrid(parameter_names=("a", "b"), points=points, weights=weights, log_likelihood=np.log(weights),
                              admissible_mask=np.ones(len(weights), dtype=bool), dataset_id="spike")
    with pytest.raises(GridResolutionError, match="effective sample size 1.56 is below 3"):
        assess_identifiability(posterior)
    with pytest.raises(GridResolutionError, match="effective sample size 1.56 is below 3"):
        _epistemic_sd(posterior, points[:, 0])


# =====================================================================
# predictive UQ must not emit uncertainty the grid cannot resolve
# =====================================================================

def test_predictive_uq_refuses_the_f5_thin_ridge(f5_bounds):
    with pytest.raises(GridResolutionError):
        _epistemic_sd(f5_bounds, f5_bounds.points @ np.asarray([1.0, 10.025]))


def test_predictive_uq_refuses_k2_c2_predictions(k2_multi):
    posterior, z = k2_multi
    with pytest.raises(GridResolutionError):
        _epistemic_sd(posterior, z["c2_predictions"][:, 0])


def test_predictive_uq_works_on_a_healthy_grid(tcr_wide):
    posterior, m, C = tcr_wide
    dT = 350.0 - 293.15
    values = posterior.points[:, 0] * (1 + posterior.points[:, 1] * dT)
    g = np.asarray([1 + m[1] * dT, m[0] * dT])
    assert _epistemic_sd(posterior, values) == pytest.approx(math.sqrt(g @ C @ g), rel=0.02)


def test_predictive_uq_is_right_on_a_weak_but_resolved_grid():
    posterior, m, C = _tcr([299.0, 299.5, 300.0, 300.5, 301.0, 301.5], per_axis=161)
    dT = 300.25 - 293.15
    values = posterior.points[:, 0] * (1 + posterior.points[:, 1] * dT)
    g = np.asarray([1 + m[1] * dT, m[0] * dT])
    assert _epistemic_sd(posterior, values) == pytest.approx(math.sqrt(g @ C @ g), rel=0.05)


# Three nodes (the frozen ESS-and-spacing rule refuses its identifiability), and
# five broad ones that the frozen rule passes and only the node-count check sees.
# INF-04 (audit): the first case used to be two nodes weighted (0.25, 0.75). Their
# effective sample size, 1.6, is below the p + 1 = 2 a one-parameter covariance
# needs, and a collapsed posterior is now refused by predictive UQ too, whatever its
# node count (tests/inference/test_audit_inference_grid_resolution.py). Three nodes
# with ESS 2.9 keep the case the waiver exists for.
@pytest.mark.parametrize("weights", [(0.25, 0.375, 0.375), (0.1, 0.2, 0.4, 0.2, 0.1)])
def test_a_discrete_posterior_too_small_to_carry_curvature_keeps_its_exact_mixture(weights):
    w = np.asarray(weights)
    values = 10.0 + 4.0 * np.arange(w.size)
    log_like = np.log(w)
    posterior = PosteriorGrid(parameter_names=("p",), points=np.arange(w.size, dtype=float)[:, None], weights=w,
                              log_likelihood=log_like, admissible_mask=np.ones(w.size, dtype=bool), dataset_id="discrete")
    mean = float(w @ values)
    assert _epistemic_sd(posterior, values) == pytest.approx(math.sqrt(float(w @ (values - mean) ** 2)))
    with pytest.raises(GridResolutionError, match="GRID_TOO_COARSE_FOR_INFERENCE" if w.size < 5 else "fewer than the 6 a local quadratic fit needs"):
        assess_identifiability(posterior)


def _log_likelihood_posterior(log_like, mask=None, per_axis=41):
    axes = [np.linspace(-3.0, 3.0, per_axis)] * 2
    points = np.array(np.meshgrid(*axes, indexing="ij")).reshape(2, -1).T
    mask = np.ones(len(points), dtype=bool) if mask is None else mask(points)
    ll = np.where(mask, log_like(points), -np.inf)
    weights = np.where(mask, np.exp(ll - ll[mask].max()), 0.0)
    return PosteriorGrid(parameter_names=("a", "b"), points=points, weights=weights / weights.sum(), log_likelihood=ll,
                         admissible_mask=mask, dataset_id="shape")


_NOT_NARROW = {
    # a non-identified axis: the likelihood is exactly flat along b
    "flat_axis": lambda p: -0.5 * (p[:, 0] / 0.3) ** 2 + 0.0 * p[:, 1],
    # a posterior cut off by the grid's bounds: still rising at the edge
    "bounded": lambda p: -0.5 * (p[:, 0] / 0.5) ** 2 + 0.3 * p[:, 1],
    # two broad modes: the fitted curvature between them is convex
    "bimodal": lambda p: np.logaddexp(-0.5 * ((p[:, 0] - 1.5) ** 2 + (p[:, 1] - 1.5) ** 2) / 0.25,
                                      -0.5 * ((p[:, 0] + 1.5) ** 2 + (p[:, 1] + 1.5) ** 2) / 0.25),
}


@pytest.mark.parametrize("shape", sorted(_NOT_NARROW))
def test_a_flat_or_convex_direction_is_not_mistaken_for_an_unresolved_one(shape):
    """Only a concave direction can be thin; a flat or convex one cannot alias and is answered."""
    posterior = _log_likelihood_posterior(_NOT_NARROW[shape])
    assert isinstance(assess_identifiability(posterior).status.value, str)
    assert _epistemic_sd(posterior, posterior.points[:, 0] + posterior.points[:, 1]) > 0.0


def test_two_thin_tilted_modes_are_refused():
    ridge = lambda p, c: -0.5 * (((p[:, 0] - p[:, 1]) / 0.02) ** 2 + ((p[:, 0] + p[:, 1] - c) / 2.0) ** 2)
    posterior = _log_likelihood_posterior(lambda p: np.logaddexp(ridge(p, 2.0), ridge(p, -2.0)))
    with pytest.raises(GridResolutionError, match="lattice aliasing number"):
        assess_identifiability(posterior)


def test_a_grid_whose_curvature_cannot_be_fitted_is_refused_not_passed():
    """Admissible nodes on one line: ESS 23.5 and axis spacing 0.15 sd pass the frozen rule."""
    posterior = _log_likelihood_posterior(lambda p: -0.5 * p[:, 0] ** 2, mask=lambda p: np.isclose(p[:, 0], p[:, 1]))
    with pytest.raises(GridResolutionError, match="cannot be verified"):
        assess_identifiability(posterior)
    with pytest.raises(GridResolutionError, match="cannot be verified"):
        _epistemic_sd(posterior, posterior.points[:, 0])


# =====================================================================
# units and parameterization
# =====================================================================

def _scaled_f5(c):
    return _synthetic_posterior(f"f5.scaled.{c}", lambda pts: pts[:, [0]] + (pts[:, [1]] / c) * F5_X[None, :], F5_Y, F5_SIGMA,
                                [np.linspace(F5_LOWER[0], F5_UPPER[0], 401), np.linspace(F5_LOWER[1] * c, F5_UPPER[1] * c, 401)])


@pytest.mark.parametrize("c", [1.0, 10.0, 100.0])
def test_rescaling_a_parameter_does_not_rescue_the_thin_ridge(c):
    with pytest.raises(GridResolutionError):
        assess_identifiability(_scaled_f5(c))


@pytest.mark.parametrize("c", [1.0, 10.0, 100.0])
def test_rescaling_a_parameter_does_not_break_a_healthy_grid(c):
    mu, cov = np.asarray([1.0, 2.0]), np.asarray([[1.0, 0.6], [0.6, 1.0]])
    S = np.diag([1.0, c])
    axes = [np.linspace(mu[0] - 6, mu[0] + 6, 61), np.linspace((mu[1] - 6) * c, (mu[1] + 6) * c, 61)]
    assess_identifiability(_gaussian_posterior(f"healthy.scaled.{c}", S @ mu, S @ cov @ S, axes))


@pytest.mark.parametrize("frame", ["principal_axes", "whitened"])
def test_a_rotated_frame_with_an_unresolved_thin_axis_is_refused(frame):
    """Rotating the F5 posterior onto its principal axes gives a different LATTICE, not merely new units:
    the thin axis now has its own step, and a step far wider than the thin width collapses it onto a node."""
    mu, cov = _f5_exact()
    lam, V = np.linalg.eigh(cov)
    T = V.T if frame == "principal_axes" else np.diag(1 / np.sqrt(lam)) @ V.T
    psi_mu, psi_cov = T @ mu, T @ cov @ T.T
    sd = np.sqrt(np.diag(psi_cov))
    axes = [np.linspace(psi_mu[0] - 240 * sd[0], psi_mu[0] + 240 * sd[0], 81), np.linspace(psi_mu[1] - 6 * sd[1], psi_mu[1] + 6 * sd[1], 81)]  # thin step 6 sd
    with pytest.raises(GridResolutionError):
        assess_identifiability(_gaussian_posterior(f"f5.{frame}", psi_mu, psi_cov, axes))


@pytest.mark.parametrize("frame", ["principal_axes", "whitened"])
def test_a_rotated_frame_that_resolves_its_thin_axis_is_classified(frame):
    mu, cov = _f5_exact()
    lam, V = np.linalg.eigh(cov)
    T = V.T if frame == "principal_axes" else np.diag(1 / np.sqrt(lam)) @ V.T
    psi_mu, psi_cov = T @ mu, T @ cov @ T.T
    sd = np.sqrt(np.diag(psi_cov))
    axes = [np.linspace(psi_mu[i] - 6 * sd[i], psi_mu[i] + 6 * sd[i], 61) for i in range(2)]
    assess_identifiability(_gaussian_posterior(f"f5.{frame}.resolved", psi_mu, psi_cov, axes))
