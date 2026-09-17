"""Batch 12 of the 2026-09-16 core re-audit: per-mode grid resolution and admissibility cuts (I-05, R-05, R-17).

A grid is admitted on two checks that each look in one place only.

* **R-05** -- V1's `_fitted_lattice_covariance` fits ONE least-squares quadratic about the global argmax, over
  a window of 50 nats or more, with no test of how well it fits, and floors flat or convex directions to
  "cannot alias". With two modes in the box the window pools both, the fitted lattice variance comes out at
  285 to 7e3, and the aliasing check switches itself off: a mode of local sd 0.00065 at a step of 0.005 is
  SUPPORTED with an sd 14x too small and a narrow-mode mass of 0.0005 against a true 0.1111.
* **R-17** -- `grid_containment` takes each face's peak over ADMISSIBLE nodes only, so a face with no
  admissible node scores -inf and passes. A posterior cut off inside the box by the forward model's refusal
  never reaches a face: SUPPORTED with mean errors up to +0.57 true sd, where the same cut made by a declared
  bound is refused.

Preregistered in `benchmarks/core_v4_false_confidence/BATCH12_THRESHOLD_PROTOCOL.json`. The fourteen
reproductions here were committed as `xfail(strict=True)` at 556ad8e0 and run with `--runxfail` to watch
each fail on its own assertion; the markers came off when I-05 was implemented. One test carries no marker
and never did, because it passed at 556ad8e0 and must keep passing: an admissibility cut must never be
reported as GRID_POSTERIOR_BOUND_DOMINATED.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

import false_confidence_cases as F
import hybrid_synthetic as S
from engcore.hybrid_uq import (
    MultistartPolicy,
    RouteClaim,
    RouteDecision,
    RouteReason,
    route_uncertainty,
)
from engcore.inference.calibration import _ALIASING_NUMBER_MINIMUM


def _reason(name):
    """A reason member the batch adds, or None -- read by name so a test fails on its own assertion."""
    return getattr(RouteReason, name, None)


def _check(name):
    """A grid-evidence check the batch adds, or None."""
    from engcore.hybrid_uq import _grid_evidence

    return getattr(_grid_evidence, name, None)


def _routed(problem, axes, **kw):
    return route_uncertainty(grid=problem.grid(axes), calibration=problem.calibrate(),
                             observations=problem.observations, forward=problem.forward,
                             multistart=MultistartPolicy(), **kw)


# =====================================================================
# R-05: every mode in the band is checked, on its own nodes
# =====================================================================
def test_r05_a_supplied_grid_that_aliases_a_second_mode_is_passed_over():
    """The audited record: step 0.005 (and 0.008) gives GRID_AS_SUPPLIED SUPPORTED, sd ratio 0.070."""
    unresolved = _reason("GRID_MODE_UNRESOLVED")
    assert unresolved is not None, "the batch adds the reason for a mode the grid does not resolve"
    problem = F.narrow_second_mode_inside_the_box()
    result = _routed(problem, [np.arange(-1.0, 2.0 + 1e-9, 0.008)])
    assert result.decision is not RouteDecision.GRID_AS_SUPPLIED, (
        f"{result.decision.value} {result.claim.value}: the narrow mode at -0.124 has a local sd of 0.00065, "
        f"which a step of 0.008 aliases away")
    assert unresolved.value in {c.get("reason") for c in result.considered}, result.considered


def test_r05_the_same_grid_refined_is_still_used():
    """The check is a resolution test and not a refusal of two modes: a fine grid over both passes it."""
    resolution = _check("grid_mode_resolution")
    assert resolution is not None, "the batch adds the per-mode resolution check"
    problem = F.narrow_second_mode_inside_the_box()
    fine = problem.grid([np.arange(-1.0, 2.0 + 1e-9, 0.0005)])
    assert resolution(fine) is None, resolution(fine)
    coarse = problem.grid([np.arange(-1.0, 2.0 + 1e-9, 0.008)])
    assert resolution(coarse) is not None


def test_r05_the_narrow_modes_own_fit_is_what_finds_it():
    """The audited fit pooled both modes and read a lattice variance of 285 to 7e3; the local one reads 0.109.

    So the defect is the LOCALITY of the fit, and this is the measurement that says so.
    """
    from engcore.inference.calibration import _fitted_lattice_covariance, _minimum_aliasing_number, _tensor_lattice_steps

    modes_of = _check("_grid_modes")
    fit_of = _check("_mode_lattice_covariance")
    assert modes_of is not None and fit_of is not None, "the batch adds the per-mode scan and fit"
    problem = F.narrow_second_mode_inside_the_box()
    grid = problem.grid([np.arange(-1.0, 2.0 + 1e-9, 0.008)])
    steps = _tensor_lattice_steps(np.asarray(grid.points))
    pooled, _why = _fitted_lattice_covariance(grid, steps)
    assert _minimum_aliasing_number(pooled, _ALIASING_NUMBER_MINIMUM) is None, (
        "the pooled fit passes the aliasing bound, which is the audited defect")
    lattice, shape, found, axes = modes_of(grid)
    worst = []
    for index in found:
        covariance, residual, _radius = fit_of(lattice, shape, index, axes, steps)
        worst.append((None if covariance is None else _minimum_aliasing_number(covariance, _ALIASING_NUMBER_MINIMUM),
                      residual))
    assert any(aliasing is not None for aliasing, _residual in worst), worst
    assert any(residual > _ALIASING_NUMBER_MINIMUM / 2.0 for _aliasing, residual in worst), worst


def test_r05_a_mode_the_aliasing_bound_passes_can_still_fail_its_own_fit():
    """The two halves of the per-mode check are independent, and this is the case only the RESIDUAL test sees.

    A broad shoulder with a narrow spike at its centre: over the fit box the least-squares quadratic follows
    the six shoulder nodes, so its curvature is wide and V1's aliasing bound passes -- while the centre node
    sits 6.7 nats below the fit. The spike's mass is aliased and the fitted covariance says nothing about it.
    Not a reproduction: it is here so the residual test is a measured part of the rule.
    """
    resolution = _check("grid_mode_resolution")
    fit_of, modes_of = _check("_mode_lattice_covariance"), _check("_grid_modes")
    assert resolution is not None and fit_of is not None, "the batch adds the per-mode check"
    from engcore.hybrid_uq._grid_evidence import MODE_FIT_RESIDUAL_NATS
    from engcore.inference.calibration import _minimum_aliasing_number, _tensor_lattice_steps

    def model(t, _x):
        th = float(t[0])
        dip = 20.0 * (1.0 - np.exp(-((th / 1.0e-3) ** 2)))
        return np.asarray([th / 0.1, math.sqrt(max(dip, 0.0)), 0.0])

    problem = S.Problem("spike_on_a_shoulder", model, np.arange(3.0), (0.0,), 1.0, (-1.0,), (1.0,), (0.0,),
                        observed=(0.0, 0.0, 0.0))
    grid = problem.grid([np.linspace(-1.0, 1.0, 41)])
    lattice, shape, found, axes = modes_of(grid)
    steps = _tensor_lattice_steps(np.asarray(grid.points, dtype=float))
    assert len(found) == 1, found
    covariance, residual, _radius = fit_of(lattice, shape, found[0], axes, steps)
    assert _minimum_aliasing_number(covariance, _ALIASING_NUMBER_MINIMUM) is None, (
        "the aliasing bound must PASS here, or the case does not separate the two halves")
    assert residual > MODE_FIT_RESIDUAL_NATS, residual
    found_problem = resolution(grid)
    assert found_problem is not None and "misses its own nodes" in found_problem[1], found_problem


def test_r05_a_mode_its_own_fit_describes_perfectly_can_still_fail_the_aliasing_bound():
    """And this is the case only the ALIASING bound sees: a thin tilted ridge.

    The log-likelihood is exactly quadratic, so the fit's residual is 1e-10 nats, and the ridge is narrower
    perpendicular to itself than the lattice can sample. Not a reproduction: it is here so the aliasing half
    is a measured part of the rule and not carried by the residual test.
    """
    resolution = _check("grid_mode_resolution")
    fit_of, modes_of = _check("_mode_lattice_covariance"), _check("_grid_modes")
    assert resolution is not None and fit_of is not None, "the batch adds the per-mode check"
    from engcore.hybrid_uq._grid_evidence import MODE_FIT_RESIDUAL_NATS
    from engcore.inference.calibration import _minimum_aliasing_number, _tensor_lattice_steps
    from engcore.hybrid_uq import local_gaussian_posterior

    problem = S.thin_ridge()
    calibration = problem.calibrate()
    posterior = local_gaussian_posterior(calibration, problem.observations, problem.forward, multistart=None)
    estimate = np.asarray(calibration.estimate_vector, dtype=float)
    sd = np.sqrt(np.diag(np.asarray(posterior.covariance, dtype=float)))
    grid = problem.grid([np.linspace(estimate[i] - 4.0 * sd[i], estimate[i] + 4.0 * sd[i], 41) for i in range(2)])
    lattice, shape, found, axes = modes_of(grid)
    steps = _tensor_lattice_steps(np.asarray(grid.points, dtype=float))
    assert found, found
    covariance, residual, _radius = fit_of(lattice, shape, found[0], axes, steps)
    assert residual < MODE_FIT_RESIDUAL_NATS, (
        f"the fit must be ADEQUATE here, or the case does not separate the two halves: {residual}")
    assert _minimum_aliasing_number(covariance, _ALIASING_NUMBER_MINIMUM) is not None
    found_problem = resolution(grid)
    assert found_problem is not None and "aliasing number" in found_problem[1], found_problem


def test_r05_a_well_resolved_ridge_with_many_local_maxima_is_still_used():
    """A thin tilted ridge staircases over the lattice, and every staircase node yields the RIDGE's curvature.

    So the rule tolerates spurious maxima by construction: `bimodal_two_parameter` at 41 nodes per axis has
    11 of them on a grid whose moments are stable to 6 digits from 41 to 321 nodes per axis.
    """
    resolution = _check("grid_mode_resolution")
    assert resolution is not None, "the batch adds the per-mode resolution check"
    problem = S.bimodal_two_parameter()
    estimate = np.asarray(problem.calibrate().estimate_vector, dtype=float)
    grid = problem.grid([np.linspace(estimate[i] - 0.4, estimate[i] + 0.4, 41) for i in range(2)])
    assert resolution(grid) is None, resolution(grid)


def test_r05_a_mode_is_a_maximum_over_the_whole_lattice_stencil_not_the_axes():
    """Over the 2p axis neighbours alone an exactly Gaussian tilted ridge has 3 spurious maxima; over the
    full 3^p - 1 stencil it has one."""
    modes_of = _check("_grid_modes")
    assert modes_of is not None, "the batch adds the per-mode scan"
    problem = S.affine()
    estimate = np.asarray(problem.calibrate().estimate_vector, dtype=float)
    grid = problem.grid([np.linspace(estimate[i] - 0.4, estimate[i] + 0.4, 41) for i in range(2)])
    _lattice, _shape, found, _axes = modes_of(grid)
    assert len(found) == 1, found


def test_r05_a_rebuilt_grid_that_aliases_a_mode_is_refined_or_passed_over():
    """The audited rebuild: K = 9 gives SUPPORTED with narrow-mode mass 0.209 against a true 0.100."""
    from engcore.hybrid_uq import GridRebuildPolicy

    unresolved = _reason("GRID_MODE_UNRESOLVED")
    assert unresolved is not None, "the batch adds the reason for a mode the grid does not resolve"
    problem = F.narrow_second_mode_inside_the_box()
    result = route_uncertainty(calibration=problem.calibrate(), observations=problem.observations,
                               forward=problem.forward, multistart=MultistartPolicy(),
                               rebuild=GridRebuildPolicy(table_builder=problem.table_builder()))
    used = [c for c in result.considered
            if c["route"] == "GRID_REBUILT_FROM_LOCAL_COVARIANCE" and c["outcome"] == "USED"]
    if used:
        resolution = _check("grid_mode_resolution")
        assert resolution is not None, "the batch adds the per-mode resolution check"
        assert resolution(result.grid) is None, (
            f"a rebuilt grid that is USED resolves every mode in its band: {resolution(result.grid)}")
    else:
        assert unresolved.value in {c.get("reason") for c in result.considered}, result.considered


# =====================================================================
# R-17: an admissibility cut is a truncation face
# =====================================================================
def test_r17_a_supplied_grid_cut_by_inadmissibility_is_passed_over():
    """The audited record: cut offsets of 0.02, 0.50 and 0.98 steps give SUPPORTED with mean errors of
    -0.40, +0.05 and +0.57 true sd, where the same cut at a declared bound is REFUSED."""
    cut = _reason("GRID_CUT_BY_INADMISSIBILITY")
    assert cut is not None, "the batch adds the reason for a posterior the admissible region cuts"
    problem = F.admissibility_cut()
    result = _routed(problem, [F.admissibility_cut_grid_axis(problem)])
    assert result.decision is not RouteDecision.GRID_AS_SUPPLIED, (
        f"{result.decision.value} {result.claim.value}: every node past the cut is inadmissible, so no face "
        f"carries density and containment passes")
    assert cut.value in {c.get("reason") for c in result.considered}, result.considered


def test_r17_the_cut_is_named_as_itself_and_not_as_a_box_too_small():
    """`GRID_DOES_NOT_CONTAIN_POSTERIOR` says to grow the box, which cannot fix a cut inside it."""
    cut = _reason("GRID_CUT_BY_INADMISSIBILITY")
    assert cut is not None, "the batch adds the reason for a posterior the admissible region cuts"
    problem = F.admissibility_cut()
    result = _routed(problem, [F.admissibility_cut_grid_axis(problem)])
    named = [c.get("reason") for c in result.considered if c["route"] == "GRID_AS_SUPPLIED"]
    assert named and named[0] == cut.value, named


def test_r17_a_grid_whose_admissible_region_is_not_cut_is_still_used():
    """The route that must keep working: an admissible box with no inadmissible neighbour anywhere."""
    check = _check("grid_admissibility_truncation")
    assert check is not None, "the batch adds the admissibility-cut check"
    problem = S.affine()
    grid = problem.grid([np.linspace(0.6, 1.3, 61), np.linspace(1.4, 2.7, 61)])
    assert check(grid) is None, check(grid)


def test_r17_an_inadmissible_node_far_below_the_peak_is_not_a_cut():
    """Only a cut the posterior REACHES matters: an inadmissible neighbour of a node a factor 1e6 below the
    peak truncates nothing the moments depend on."""
    check = _check("grid_admissibility_truncation")
    assert check is not None, "the batch adds the admissibility-cut check"
    # the optimum 20 local sd above the cut, so every admissible node beside the cut is about 200 nats below
    # the peak -- far outside the ln 1e6 band the containment check already uses
    far = F.admissibility_cut(offset_sd=20.0)
    grid = far.grid([F.admissibility_cut_grid_axis(far, steps_below=2.0, span_sd=8.0)])
    lattice = np.asarray(grid.log_likelihood, dtype=float)
    usable = np.asarray(grid.admissible_mask, dtype=bool) & np.isfinite(lattice)
    peak = float(np.max(np.where(usable, lattice, -np.inf)))
    beside = float(np.max(np.where(usable, lattice, -np.inf)[:2]))
    assert peak - beside > math.log(1.0e6), (peak, beside)
    assert check(grid) is None, check(grid)
    # and the audited case, whose optimum sits half a local sd above the cut, IS one
    assert check(F.admissibility_cut().grid([F.admissibility_cut_grid_axis(F.admissibility_cut())])) is not None


def test_r17_a_rebuild_halves_the_step_across_the_cut_until_the_moments_converge():
    """The audited rebuild ends SUPPORTED with '0 truncation halving(s)' and a mean error of -0.144 sd,
    about 3x the router's own TRUNCATION_CONVERGENCE_SD of 0.05."""
    from engcore.hybrid_uq import GridRebuildPolicy

    problem = F.admissibility_cut()
    result = route_uncertainty(calibration=problem.calibrate(), observations=problem.observations,
                               forward=problem.forward, multistart=MultistartPolicy(),
                               rebuild=GridRebuildPolicy(table_builder=problem.table_builder()))
    rebuilt = [c for c in result.considered if c["route"] == "GRID_REBUILT_FROM_LOCAL_COVARIANCE"]
    assert rebuilt, result.considered
    # the LAST entry is the outcome; the earlier ones are refinements V1 refused
    final = rebuilt[-1]
    if final["outcome"] == "USED":
        assert "0 truncation halving(s)" not in final.get("detail", ""), (
            f"the admissible region cuts this posterior, so the rebuild refines across the cut: {final}")
    else:
        assert final["reason"], final


def test_r17_the_bound_domination_rule_is_not_fired_by_an_admissibility_cut():
    """`GRID_POSTERIOR_BOUND_DOMINATED` is about the DECLARED range being what a width describes.

    An admissibility cut is the model's own domain, so it must never be reported as that -- the rebuild keeps
    the two lists apart and runs the domination check before the cuts join the halving list.
    """
    from engcore.hybrid_uq import GridRebuildPolicy

    problem = F.admissibility_cut()
    result = route_uncertainty(calibration=problem.calibrate(), observations=problem.observations,
                               forward=problem.forward, multistart=MultistartPolicy(),
                               rebuild=GridRebuildPolicy(table_builder=problem.table_builder()))
    assert RouteReason.GRID_POSTERIOR_BOUND_DOMINATED.value not in {c.get("reason") for c in result.considered}, \
        result.considered


# =====================================================================
# both checks run wherever a grid is held to its evidence
# =====================================================================
def test_both_checks_run_in_routed_prediction():
    """A grid the router would not route is not predicted from either: the same chain runs there."""
    from engcore.hybrid_uq.predictive import _grid_evidence_judgement
    from engcore.hybrid_uq.vocabulary import HybridUQError

    cut = F.admissibility_cut()
    for problem, axes in ((F.narrow_second_mode_inside_the_box(), [np.arange(-1.0, 2.0 + 1e-9, 0.008)]),
                          (cut, [F.admissibility_cut_grid_axis(cut)])):
        grid = problem.grid(axes)
        with pytest.raises(HybridUQError):
            _grid_evidence_judgement(grid, RouteClaim.SUPPORTED, problem.observations, problem.forward,
                                     problem.calibrate())


def test_both_checks_run_in_the_supplied_grid_problem_chain():
    from engcore.hybrid_uq._grid_evidence import supplied_grid_problem

    problem = F.admissibility_cut()
    grid = problem.grid([F.admissibility_cut_grid_axis(problem)])
    cut = _reason("GRID_CUT_BY_INADMISSIBILITY")
    assert cut is not None, "the batch adds the reason for a posterior the admissible region cuts"
    found = supplied_grid_problem(grid, problem.calibrate(), problem.observations, problem.forward)
    assert found is not None and found[0] is cut, found


def test_a_grid_with_more_maxima_than_the_limit_is_passed_over():
    from engcore.hybrid_uq import _grid_evidence

    limit = getattr(_grid_evidence, "MODE_FIT_LIMIT", None)
    assert limit == 1024, limit
    assert math.isclose(getattr(_grid_evidence, "MODE_FIT_RESIDUAL_NATS", 0.0), _ALIASING_NUMBER_MINIMUM / 2.0), \
        getattr(_grid_evidence, "MODE_FIT_RESIDUAL_NATS", None)
