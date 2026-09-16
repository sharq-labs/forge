"""I-15: the audited false-confidence reproductions as invariants, against pinned reference posteriors.

Re-audit 2026-09-16 (`docs/audits/CORE_REAUDIT_2026-09-16.md`). Each test here is one of the 15 hybrid-UQ
problems R-01, R-03, R-05..R-08, R-11, R-13..R-18, R-20, R-26, turned from "here is a number that is wrong"
into an invariant a correct implementation must satisfy. The invariants, and every threshold in them, are
preregistered in `benchmarks/core_v4_false_confidence/BATCH6_THRESHOLD_PROTOCOL.json`:

* **INV-1, the mass floor.** A SUPPORTED central 95% interval holds at least 0.90 of that parameter's
  marginal mass under the case's pinned dense reference posterior.
* **INV-7, the moments.** A SUPPORTED route's mean is within 0.10 reference sd of the reference mean and its
  reported sd is within 10% of the reference sd.
* **INV-2, equivariance.** Restating a parameter in a rescaled unit changes no claim and no dimensionless
  diagnostic, and rescales every number.
* **INV-3, information.** Observations that carry no information never raise a claim, and a variance ratio
  the refusal names is never SUPPORTED however few the degrees of freedom.
* **INV-4, the declared bound.** A SUPPORTED width does not depend on where a declared bound is put.
* **INV-5, the tails.** A SUPPORTED claim's tail behaviour is measured, not skipped, in every direction.
* **INV-6, records.** Editing one carried field of a serialized record never raises its claim.

A case whose fix has not landed yet is `xfail(strict=True)`: when the fix lands the test passes, the strict
xfail turns the pass into a failure, and the marker has to come off. That is the ratchet, and it is why the
markers name the improvement they are waiting for rather than being skips.

The suite is single-process by design (I-15): the reference file is read once and the cases are independent.
"""

from __future__ import annotations

import base64
import hashlib
import json
import pathlib

import numpy as np
import pytest
from scipy.stats import norm

import false_confidence_cases as F
import hybrid_synthetic as S
from engcore.hybrid_uq import (
    GridRebuildPolicy,
    MultistartPolicy,
    RouteClaim,
    RouteDecision,
    RouteReason,
    local_gaussian_posterior,
    route_uncertainty,
)
from engcore.hybrid_uq.local_gaussian import LocalGaussianPosterior
from engcore.hybrid_uq.vocabulary import HybridUQError

REFERENCE_PATH = (pathlib.Path(__file__).resolve().parents[2]
                  / "benchmarks" / "core_v4_false_confidence" / "REFERENCE_POSTERIORS.json")
REFERENCE = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))

#: preregistered in BATCH6_THRESHOLD_PROTOCOL.json
MASS_FLOOR = 0.90
MEAN_TOLERANCE_SD = 0.10
SD_RELATIVE_TOLERANCE = 0.10
EQUIVARIANCE_RELATIVE_TOLERANCE = 1.0e-6
Z_95 = float(norm.ppf(0.975))


# ---------------------------------------------------------------------------
# the pinned reference posteriors
# ---------------------------------------------------------------------------
def _case(label):
    assert label in REFERENCE["cases"], f"no pinned reference for {label!r}; regenerate REFERENCE_POSTERIORS.json"
    return REFERENCE["cases"][label]


def _quantiles(label, axis):
    payload = _case(label)["quantiles_f8_base64"][axis]
    return np.frombuffer(base64.b64decode(payload.encode("ascii")), dtype="<f8")


def reference_mass(label, axis, low, high) -> float:
    """The pinned reference marginal mass in ``[low, high]``.

    The reference is pinned as its marginal quantile function on a uniform probability grid, so the mass in an
    interval is the fraction of quantile points inside it. That fraction is within one probability step
    (1/quantile_steps) of the true mass whatever the density, which a CDF sampled on a uniform NODE grid would
    not be: a narrow mode between two nodes would carry its whole mass in one step.
    """
    q = _quantiles(label, axis)
    inside = int(np.searchsorted(q, float(high), side="right")) - int(np.searchsorted(q, float(low), side="left"))
    return inside / len(q)


def reference_moments(label):
    case = _case(label)
    return np.asarray(case["mean"], dtype=float), np.asarray(case["sd"], dtype=float)


def test_the_pinned_reference_posteriors_are_the_bytes_their_digest_names():
    """Cheap integrity: the committed file is the one its own digest was computed over.

    Re-deriving the references from the models is
    `benchmarks/core_v4_false_confidence/audit/reference_posteriors.py`, guarded by the expensive test below.
    """
    payload = {k: v for k, v in REFERENCE.items() if k != "digest"}
    rebuilt = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    assert rebuilt == REFERENCE["digest"]
    for label, case in REFERENCE["cases"].items():
        assert case["converged"], f"{label}: the reference did not converge under a halved step"
        assert case["halved_step_moved_sd"] < REFERENCE["reference_convergence_sd"], label
        for axis, encoded in enumerate(case["quantiles_f8_base64"]):
            q = _quantiles(label, axis)
            assert len(q) == case["quantile_steps"] + 1, (label, axis)
            assert np.all(np.diff(q) >= 0.0), f"{label} axis {axis}: the quantile function is not monotone"
            lo, hi = case["bounds"][axis]
            assert lo - 1e-12 <= q[0] and q[-1] <= hi + 1e-12, (label, axis)


@pytest.mark.expensive
def test_the_pinned_reference_posteriors_are_re_derivable_from_the_models():
    """The references are evidence, so they are re-derived, not trusted (about 30 s)."""
    import importlib

    module = importlib.import_module("benchmarks.core_v4_false_confidence.audit.reference_posteriors")
    rebuilt = module.build()
    assert rebuilt["digest"] == REFERENCE["digest"], "the pinned reference posteriors no longer match their models"


# ---------------------------------------------------------------------------
# invariant helpers
# ---------------------------------------------------------------------------
def _reported(result):
    """``(names, mean, sd)`` of whatever a routed result reports, refusing a case whose coordinates are not natural."""
    assert result.coordinates in ("natural", "inference"), result.coordinates
    mean = np.asarray(result.mean, dtype=float)
    sd = np.sqrt(np.diag(np.asarray(result.covariance, dtype=float)))
    return tuple(result.parameter_names), mean, sd


def assert_mass_floor(result, label, *, axes=None):
    """INV-1. Only says anything about a SUPPORTED claim: a DOWNGRADED or REFUSED route claims nothing."""
    if result.claim is not RouteClaim.SUPPORTED:
        return
    _names, mean, sd = _reported(result)
    for axis in range(len(mean)) if axes is None else axes:
        low, high = mean[axis] - Z_95 * sd[axis], mean[axis] + Z_95 * sd[axis]
        mass = reference_mass(label, axis, low, high)
        assert mass >= MASS_FLOOR, (
            f"{label} axis {axis}: a SUPPORTED 95% interval [{low:.6g}, {high:.6g}] holds {mass:.4f} of the "
            f"reference posterior, below the floor of {MASS_FLOOR}")


def assert_moments(result, label, *, axes=None):
    """INV-7."""
    if result.claim is not RouteClaim.SUPPORTED:
        return
    _names, mean, sd = _reported(result)
    reference_mean, reference_sd = reference_moments(label)
    for axis in range(len(mean)) if axes is None else axes:
        offset = abs(mean[axis] - reference_mean[axis]) / reference_sd[axis]
        assert offset <= MEAN_TOLERANCE_SD, (
            f"{label} axis {axis}: a SUPPORTED mean {mean[axis]:.6g} is {offset:.3g} reference sd from the "
            f"reference mean {reference_mean[axis]:.6g}")
        ratio = sd[axis] / reference_sd[axis]
        assert abs(ratio - 1.0) <= SD_RELATIVE_TOLERANCE, (
            f"{label} axis {axis}: a SUPPORTED sd {sd[axis]:.6g} is {ratio:.4g}x the reference sd "
            f"{reference_sd[axis]:.6g}")


def _rebuilt(problem, **kw):
    return route_uncertainty(calibration=problem.calibrate(), observations=problem.observations,
                             forward=problem.forward, rebuild=GridRebuildPolicy(problem.table_builder()), **kw)


def _local(problem, multistart=None):
    if multistart is None:
        multistart = MultistartPolicy()
    return local_gaussian_posterior(problem.calibrate(), problem.observations, problem.forward, multistart=multistart)


# ---------------------------------------------------------------------------
# R-01, R-06: the router's uniqueness contract (I-01, this batch)
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-01 open until I-01 lands in this same batch")
def test_r01_a_grid_rebuilt_without_a_uniqueness_search_never_claims_one_mode():
    """R-01: with multistart omitted the rebuild used to launder DOWNGRADED into a SUPPORTED one-mode grid.

    The audited record reported mean (1.0217, 0.4061) and sd [0.0243, 0.0760] SUPPORTED, against a reference
    sd of 1.0220 on theta1 -- 42x too narrow -- and a 95% interval holding 0.4748 of the reference posterior.
    """
    problem = S.bimodal_two_parameter()
    result = _rebuilt(problem)
    assert_mass_floor(result, "bimodal_two_parameter")
    assert_moments(result, "bimodal_two_parameter")


@pytest.mark.xfail(strict=True, reason="R-06 open until I-01 lands in this same batch")
def test_r06_a_supplied_grid_over_one_of_two_modes_is_never_supported():
    """R-06: step 1 returned GRID_AS_SUPPLIED SUPPORTED before the caller's own MultistartPolicy ever ran."""
    problem = S.bimodal_two_parameter()
    calibration = problem.calibrate()
    one_mode = problem.grid(F.bimodal_one_mode_axes())
    result = route_uncertainty(grid=one_mode, calibration=calibration, observations=problem.observations,
                               forward=problem.forward, multistart=MultistartPolicy())
    assert_mass_floor(result, "bimodal_two_parameter")
    assert_moments(result, "bimodal_two_parameter")


# ---------------------------------------------------------------------------
# R-07, R-08, R-18: the multistart search itself (I-02)
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-07 open until I-02: a separated optimum is classified by peak height alone")
def test_r07_a_broad_basin_that_holds_the_mass_is_not_a_single_mode():
    """R-07: every refit reaches a basin 10 chi-square units up, is called WORSE_LOCAL_OPTIMUM, and is ignored.

    The audited record is SUPPORTED with a 95% interval of [-0.0196, 0.0196] holding 0.177 of the posterior,
    while 0.792 of it sits in the broad basin at theta > 1.5.
    """
    problem = F.worse_local_optimum_holds_the_mass()
    result = route_uncertainty(calibration=problem.calibrate(), observations=problem.observations,
                               forward=problem.forward, multistart=MultistartPolicy())
    assert_mass_floor(result, "worse_local_optimum_holds_the_mass")


@pytest.mark.xfail(strict=True, reason="R-08 open until I-02: max_evaluations is not part of the minimum search")
def test_r08_a_refit_budget_below_the_canonical_one_never_claims_a_single_mode():
    """R-08: max_evaluations 12 drops exactly the slow refit that reaches the second mode, with no shortfall recorded."""
    problem = F.second_mode_behind_a_refit_budget()
    result = route_uncertainty(calibration=problem.calibrate(), observations=problem.observations,
                               forward=problem.forward, multistart=MultistartPolicy(max_evaluations=12))
    assert_mass_floor(result, "second_mode_behind_a_refit_budget")


@pytest.mark.xfail(strict=True, reason="R-18 open until I-02: a retracted start counts as a full-span start")
def test_r18_starts_retracted_into_the_estimates_basin_never_claim_a_single_mode():
    """R-18: five of six starts are halved toward the estimate, and the search reads MULTISTART_NO_SECOND_MODE."""
    problem = F.retracted_starts_never_leave_the_basin()
    result = route_uncertainty(calibration=problem.calibrate(), observations=problem.observations,
                               forward=problem.forward, multistart=MultistartPolicy())
    assert_mass_floor(result, "retracted_starts_never_leave_the_basin")


# ---------------------------------------------------------------------------
# R-05, R-17: what one quadratic fit at the argmax cannot see (I-05)
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-05 open until I-05: resolution is fitted at the argmax only")
def test_r05_a_narrow_second_mode_inside_the_box_is_not_resolved_away():
    """R-05: a mode of local sd 0.00065 aliased by the grid step, SUPPORTED with an sd tens of times too small."""
    problem = F.narrow_second_mode_inside_the_box()
    calibration = problem.calibrate()
    grid = problem.grid([np.arange(-1.0, 2.0 + 1e-9, 0.008)])
    result = route_uncertainty(grid=grid, calibration=calibration, observations=problem.observations,
                               forward=problem.forward, multistart=MultistartPolicy())
    assert_mass_floor(result, "narrow_second_mode_inside_the_box")
    assert_moments(result, "narrow_second_mode_inside_the_box")


@pytest.mark.xfail(strict=True, reason="R-17 open until I-05: an inadmissibility cut is not a truncation face")
def test_r17_a_posterior_cut_by_inadmissibility_is_not_contained_by_accident():
    """R-17: every node past the cut is inadmissible, so no face carries density and containment passes."""
    problem = F.admissibility_cut()
    calibration = problem.calibrate()
    grid = problem.grid([F.admissibility_cut_grid_axis(problem)])
    result = route_uncertainty(grid=grid, calibration=calibration, observations=problem.observations,
                               forward=problem.forward, multistart=MultistartPolicy())
    assert_moments(result, "admissibility_cut")


# ---------------------------------------------------------------------------
# R-03, R-20: where the information is (I-04)
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-03 open until I-04: the goodness-of-fit test pools every residual")
def test_r03_observations_that_carry_no_information_never_raise_the_claim():
    """R-03: ten precise points at chi2/dof 9 are REFUSED alone and SUPPORTED with 60 uninformative points added.

    The uninformative readings are the model's own prediction at the estimate with a sigma 1e6 times the
    largest declared one, so they add degrees of freedom and no information: the covariance is unchanged.
    """
    problem = F.gross_misfit_with_ten_precise_points()
    alone = _local(problem)
    assert alone.claim is RouteClaim.REFUSED and RouteReason.MODEL_MISFIT_BEYOND_DECLARED_NOISE in alone.reasons
    diluted = _dilute(problem, count=60, sigma_factor=1.0e6)
    after = _local(diluted)
    assert _claim_order(after.claim) <= _claim_order(alone.claim), (
        f"adding 60 observations that carry no information raised the claim from {alone.claim.value} to "
        f"{after.claim.value}")


@pytest.mark.xfail(strict=True, reason="R-20 open until I-04: the variance-ratio refusal is gated behind the p-value")
@pytest.mark.parametrize("chi_square,points", [(6.6, 3), (9.15, 4)], ids=["dof_1", "dof_2"])
def test_r20_a_variance_ratio_above_four_is_never_supported(chi_square, points):
    """R-20: chi2/dof of 6.6 on 1 dof and 4.57 on 2 dof read SUPPORTED, because p >= 0.01 returns first."""
    problem = F.small_dof_variance_ratio(chi_square, points)
    post = _local(problem)
    dof = points - 2
    assert chi_square / dof > 4.0, "the case must exceed the ratio the refusal names"
    assert post.claim is not RouteClaim.SUPPORTED, (
        f"chi-square {chi_square} on {dof} degrees of freedom is a variance ratio of {chi_square / dof:.3g}, "
        f"which MODEL_MISFIT_BEYOND_DECLARED_NOISE names, and the claim is {post.claim.value}")


# ---------------------------------------------------------------------------
# R-11: the declared bound must not set the reported width (I-06)
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-11 open until I-06: domination is refused only when both sides truncate")
def test_r11_a_supported_width_does_not_depend_on_where_a_declared_bound_is_put():
    """R-11: the same data give a rate sd of 4.98, 10.33 and 16.14 with the upper bound at 40, 60 and 80."""
    widths = {}
    for bound in (40.0, 60.0, 80.0):
        problem = F.decay_with_upper_bound(bound)
        result = _rebuilt(problem, multistart=MultistartPolicy())
        if result.claim is RouteClaim.SUPPORTED:
            widths[bound] = float(np.sqrt(np.asarray(result.covariance, dtype=float)[0][0]))
    if len(widths) < 2:
        return
    spread = max(widths.values()) / min(widths.values())
    assert spread - 1.0 <= SD_RELATIVE_TOLERANCE, (
        f"a SUPPORTED width moved by a factor {spread:.4g} when only the declared upper bound moved: {widths}")


# ---------------------------------------------------------------------------
# R-13, R-14, R-15: the probes (I-08)
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-13 open until I-08: the probes bound each direction, not the matrix")
def test_r13_a_curvature_error_spread_over_every_pair_is_not_supported():
    """R-13: a residual curvature of -0.099 on every pair passes every probe at index 0.0992.

    Along the equal-weight direction the true chi-square rise at 2, 3 and 6 reported sd is 0.5, 1.303 and
    9.068, against a Gaussian's 4, 9 and 36: the true sd there is 2.24x the reported one.
    """
    problem = F.collective_curvature_error()
    post = _local(problem, MultistartPolicy(starts=22))
    if post.claim is not RouteClaim.SUPPORTED:
        return
    worst = _worst_direction_rise_ratio(problem, post)
    assert worst >= 0.5, (
        f"a SUPPORTED local Gaussian's chi-square rise along its worst probed-free direction is {worst:.4g} of "
        f"the Gaussian's, which TAIL_HEAVIER_THAN_LOCAL_GAUSSIAN names as a refusal on the principal axes")


@pytest.mark.xfail(strict=True, reason="R-14 open until I-08: tail probes run along principal axes only")
def test_r14_a_posterior_flat_along_its_diagonals_is_not_supported():
    """R-14: exactly Gaussian on both axes out to 6 sd, saturating along the diagonals beyond about 3 sd."""
    problem = F.off_axis_flat_tail()
    result = route_uncertainty(calibration=problem.calibrate(), observations=problem.observations,
                               forward=problem.forward, multistart=MultistartPolicy())
    assert_mass_floor(result, "off_axis_flat_tail")


@pytest.mark.xfail(strict=True, reason="R-15 open until I-08: a tail probe beyond a bound is dropped uncounted")
def test_r15_moving_a_declared_bound_across_a_probe_radius_does_not_raise_the_claim():
    """R-15: the same flat-tailed posterior is REFUSED with bounds at 6.01 sd and SUPPORTED at 5.99 sd."""
    outside = _local(F.tail_beyond_a_bound(6.01))
    inside = _local(F.tail_beyond_a_bound(5.99))
    assert _claim_order(inside.claim) <= _claim_order(outside.claim), (
        f"pulling a declared bound from 6.01 to 5.99 posterior sd raised the claim from {outside.claim.value} "
        f"to {inside.claim.value}: the 6 sd tail probe disappeared instead of being counted")


# ---------------------------------------------------------------------------
# R-16, R-26: the same request in another unit (I-08)
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-16 open until I-08: probe directions come from eigh(cov) in declared units")
def test_r16_restating_a_parameter_in_another_unit_changes_no_claim_and_no_diagnostic():
    """R-16: the same model and data, SUPPORTED in one unit and REFUSED (TAIL_HEAVIER) in another."""
    declared = _local(F.coupled_off_axis_flat_tail(1.0, "R16_declared"))
    restated = _local(F.coupled_off_axis_flat_tail(2.0, "R16_restated"))
    assert restated.claim is declared.claim, (
        f"restating theta2's unit by a factor 2 moved the claim from {declared.claim.value} to "
        f"{restated.claim.value}")
    for label in ("nonlinearity_index", "minimum_tail_rise_ratio"):
        a = float(getattr(declared.diagnostics, label))
        b = float(getattr(restated.diagnostics, label))
        assert abs(b - a) <= EQUIVARIANCE_RELATIVE_TOLERANCE * max(abs(a), 1.0), (
            f"{label} is dimensionless and moved from {a:.6g} to {b:.6g} under a pure unit restatement")


@pytest.mark.xfail(strict=True, reason="R-26 open until I-08: POORLY_SCALED is judged on the raw condition number")
def test_r26_a_smaller_unit_does_not_downgrade_an_exactly_gaussian_result():
    """R-26: a slope in nanovolts (raw condition 3.19e9, equilibrated 3.47) downgrades an exact Gaussian."""
    declared = _local(F.rescaled_slope(1.0, "R26_volt"))
    restated = _local(F.rescaled_slope(1.0e9, "R26_nanovolt"))
    assert declared.claim is RouteClaim.SUPPORTED, "the case must be SUPPORTED in its declared unit"
    assert restated.diagnostics.jacobian_condition == pytest.approx(declared.diagnostics.jacobian_condition, rel=1e-6)
    assert restated.claim is declared.claim, (
        f"restating the slope in nanovolts moved the claim to {restated.claim.value} with reasons "
        f"{[r.value for r in restated.reasons]}, on an equilibrated condition number of "
        f"{restated.diagnostics.jacobian_condition:.4g}")


# ---------------------------------------------------------------------------
# R-22: one edited field (I-14)
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-22 open until I-14: the observation count is a free carried field")
def test_r22_editing_one_carried_field_never_raises_a_records_claim():
    """R-22: raising the recorded observation count turns DOWNGRADED RESIDUALS_EXCEED_DECLARED_NOISE into SUPPORTED."""
    problem = F.small_dof_variance_ratio(30.0, 12)
    genuine = _local(problem)
    payload = genuine.to_dict()
    assert genuine.claim is RouteClaim.DOWNGRADED, [r.value for r in genuine.reasons]
    edited = json.loads(json.dumps(payload))
    edited["diagnostics"]["observations"] = 40
    # The claim and the reasons the edit implies are edited with it, as the audited reproduction does: the
    # record is internally consistent and only the count it carries is a lie.
    edited["diagnostics"]["claim"] = RouteClaim.SUPPORTED.value
    edited["diagnostics"]["downgrades"] = []
    edited["claim"] = RouteClaim.SUPPORTED.value
    try:
        read = LocalGaussianPosterior.from_dict(edited)
    except HybridUQError:
        return
    assert _claim_order(read.claim) <= _claim_order(genuine.claim), (
        f"editing the recorded observation count from {payload['diagnostics']['observations']} to 40 raised "
        f"the claim from {genuine.claim.value} to {read.claim.value}")


# ---------------------------------------------------------------------------
# shared machinery the cases above use
# ---------------------------------------------------------------------------
_CLAIM_ORDER = {RouteClaim.REFUSED: 0, RouteClaim.DOWNGRADED: 1, RouteClaim.SUPPORTED: 2}


def _claim_order(claim) -> int:
    return _CLAIM_ORDER[RouteClaim(claim)]


def _dilute(problem, *, count: int, sigma_factor: float):
    """``problem`` with ``count`` observations appended that carry no information about the parameters.

    Each added reading is the model's own prediction at the calibrated estimate, with a sigma ``sigma_factor``
    times the largest declared one, so it adds a degree of freedom and about ``sigma_factor**-2`` of one
    reading's Fisher information.
    """
    from engcore.inference import GaussianObservation, ObservationSet
    from engcore.scientific.units.quantity import Quantity

    estimate = np.asarray(problem.calibrate().estimate_vector, dtype=float)
    unit = problem.observations.observations[0].value.units
    sigma = float(np.max(problem.sigma)) * float(sigma_factor)
    predicted = float(np.asarray(problem.model(estimate, problem.x), dtype=float)[0])
    added = tuple(
        GaussianObservation(condition_id=f"uninformative{i}", observable_name="y", value=Quantity(predicted, unit),
                            sigma=Quantity(sigma, unit), source_ref=f"synthetic:uninformative:{i}")
        for i in range(int(count)))
    diluted = S.Problem.__new__(S.Problem)
    diluted.__dict__.update(problem.__dict__)
    diluted.observations = ObservationSet(problem.observations.observations + added,
                                          dataset_id=problem.observations.dataset_id + ".diluted")
    # The model is evaluated at problem.x, so the added rows need an x each; they carry the same x as the
    # first reading, which is what makes them exact copies of an informative condition with a huge sigma.
    diluted.x = np.concatenate([problem.x, np.full(int(count), problem.x[0])])
    diluted.sigma = np.concatenate([problem.sigma, np.full(int(count), sigma)])
    diluted.observed = np.concatenate([problem.observed, np.full(int(count), predicted)])
    return diluted


def _worst_direction_rise_ratio(problem, post) -> float:
    """The smallest ``chi2 rise / (r^2)`` at r = 2 reported sd over the equal-weight direction and the axes.

    The local route's own measure, evaluated in a direction its probes do not cover: the equal-weight
    combination of every parameter, which is where a curvature error spread over all pairs shows up.
    """
    from engcore.hybrid_uq.sensitivity import evaluate

    observed, sigma = problem.observations.numeric_vectors()
    keys = problem.observations.keys
    units = tuple(o.value.units for o in problem.observations.observations)
    references = tuple(o.value for o in problem.observations.observations)

    def chi_square(point):
        value = evaluate(problem.forward, point, keys, units, references)
        return None if value is None else float(np.sum(((value - observed) / sigma) ** 2))

    z0 = np.asarray(post.inference_point, dtype=float)
    covariance = np.asarray(post.covariance, dtype=float)
    base = chi_square(z0)
    p = len(z0)
    direction = np.ones(p) / np.sqrt(p)
    scale = float(np.sqrt(direction @ covariance @ direction))
    worst = np.inf
    for radius in (2.0, 3.0, 6.0):
        for sign in (1.0, -1.0):
            value = chi_square(z0 + sign * radius * scale * direction)
            if value is not None:
                worst = min(worst, (value - base) / radius ** 2)
    return float(worst)
