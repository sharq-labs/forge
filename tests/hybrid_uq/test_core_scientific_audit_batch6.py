"""Batch 6 of the 2026-09-16 core re-audit: the router's uniqueness contract (I-01, closing R-01 and R-06).

Preregistered in `benchmarks/core_v4_false_confidence/BATCH6_THRESHOLD_PROTOCOL.json`. The scientific
invariants these rules exist to protect are in `test_core_v4_false_confidence_conformance.py`; what is
asserted here is the contract itself: which route is passed over, under which word, and what a record with an
unresolved uniqueness search may no longer say.

Every test in this file was committed as `xfail(strict=True)` first and run with `--runxfail` at f9bab88 to
watch it fail. What each one failed on there, recorded so the evidence is not overstated:

* on its own assertion: ``below_the_minimum`` (`'USED' == 'PASSED_OVER'`), ``runs_the_canonical_search``
  (`'NOT_ASSESSED' == 'SECOND_MODE_FOUND'`), ``refused_on_read`` (`DID NOT RAISE HybridUQError`),
  ``misses_a_found_mode`` (`'USED' == 'PASSED_OVER'`), and ``a_search_at_the_minimum`` and
  ``canonical_search_backs_a_supplied_grid`` (`KeyError: 'detail'`, the basis the USED entry does not record).
* on the absent keyword (`TypeError: unexpected keyword argument 'canonical_uniqueness_search'`):
  ``when_no_uniqueness_search_ran``, ``no_uniqueness_basis_at_all`` and ``spans_the_declared_bounds``. These
  three name the opt-out the improvement adds, so at f9bab88 there was no way to pose them; the scientific
  content they share with the first group is preregistered by that group and by
  `test_core_v4_false_confidence_conformance.py`, which fails on its assertions with the audited numbers.
* ``no_search_is_run_for_a_local_route_that_no_grid_route_needs`` already held at f9bab88 and is not a
  reproduction: it is the guard that this batch does not change that path, so it carries no xfail.
"""

from __future__ import annotations

import numpy as np
import pytest

import false_confidence_cases as F
import hybrid_synthetic as S
from engcore.hybrid_uq import (
    GridRebuildPolicy,
    HybridUQError,
    MultistartPolicy,
    RouteClaim,
    RouteDecision,
    RouteReason,
    local_gaussian_posterior,
    route_uncertainty,
)
from engcore.hybrid_uq.router import HybridUQResult


def _entry(result, route):
    matching = [dict(c) for c in result.considered if c["route"] == route]
    assert matching, f"no {route} entry in {[dict(c) for c in result.considered]}"
    return matching[-1]


# ---------------------------------------------------------------------------
# R-01: a grid is not rebuilt past an unresolved uniqueness search
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="I-01 not implemented yet (batch 6 preregistration)")
def test_r01_a_rebuild_is_passed_over_when_no_uniqueness_search_ran():
    """The audited record: multistart omitted, the local route DOWNGRADED GLOBAL_UNIQUENESS_NOT_ASSESSED, and
    step 3 rebuilding a SUPPORTED grid around the one estimate anyway. A grid claim is SUPPORTED or absent, so
    the caveat that nobody looked has to block the grid."""
    problem = S.bimodal_two_parameter()
    result = route_uncertainty(calibration=problem.calibrate(), observations=problem.observations,
                               forward=problem.forward, multistart=None, canonical_uniqueness_search=False,
                               rebuild=GridRebuildPolicy(problem.table_builder()))
    entry = _entry(result, "GRID_REBUILT_FROM_LOCAL_COVARIANCE")
    assert entry["outcome"] == "PASSED_OVER"
    assert entry["reason"] == RouteReason.GLOBAL_UNIQUENESS_NOT_ASSESSED.value
    assert result.decision is RouteDecision.LOCAL_GAUSSIAN and result.claim is RouteClaim.DOWNGRADED


@pytest.mark.xfail(strict=True, reason="I-01 not implemented yet (batch 6 preregistration)")
def test_r01_a_rebuild_is_passed_over_when_the_search_was_below_the_minimum():
    """MultistartPolicy(starts=1) gave the identical SUPPORTED grid: MULTISTART_INCOMPLETE must block it too."""
    problem = S.bimodal_two_parameter()
    result = route_uncertainty(calibration=problem.calibrate(), observations=problem.observations,
                               forward=problem.forward, multistart=MultistartPolicy(starts=1),
                               rebuild=GridRebuildPolicy(problem.table_builder()))
    entry = _entry(result, "GRID_REBUILT_FROM_LOCAL_COVARIANCE")
    assert entry["outcome"] == "PASSED_OVER"
    assert entry["reason"] == RouteReason.MULTISTART_INCOMPLETE.value


@pytest.mark.xfail(strict=True, reason="I-01 not implemented yet (batch 6 preregistration)")
def test_r01_the_router_runs_the_canonical_search_when_a_grid_route_needs_one():
    """The other way to make the claim honest: resolve uniqueness instead of withholding the grid.

    With a rebuild policy and no multistart, the router runs the canonical MultistartPolicy() itself, finds
    the mode at theta1 = -1, designs the box over both, and reports the honest bimodal posterior.
    """
    problem = S.bimodal_two_parameter()
    result = route_uncertainty(calibration=problem.calibrate(), observations=problem.observations,
                               forward=problem.forward, rebuild=GridRebuildPolicy(problem.table_builder()))
    assert result.decision is RouteDecision.GRID_REBUILT_FROM_LOCAL_COVARIANCE
    assert result.local_posterior.diagnostics.uniqueness == "SECOND_MODE_FOUND"
    assert result.local_posterior.diagnostics.multistart, "the canonical search ran, so its starts are recorded"
    sd = np.sqrt(np.diag(np.asarray(result.covariance, dtype=float)))
    assert sd[0] == pytest.approx(1.0220179476127045, rel=0.05)


def test_r01_no_search_is_run_for_a_local_route_that_no_grid_route_needs():
    """multistart=None keeps its V2 meaning where there is no grid to make honest: nobody looked, DOWNGRADED.

    Running a search here would only cost evaluations: the downgrade already says exactly what is not known.
    """
    problem = S.bimodal_two_parameter()
    result = route_uncertainty(calibration=problem.calibrate(), observations=problem.observations,
                               forward=problem.forward, multistart=None)
    assert result.decision is RouteDecision.LOCAL_GAUSSIAN and result.claim is RouteClaim.DOWNGRADED
    assert RouteReason.GLOBAL_UNIQUENESS_NOT_ASSESSED in result.local_posterior.reasons
    assert result.local_posterior.diagnostics.multistart == ()


@pytest.mark.xfail(strict=True, reason="I-01 not implemented yet (batch 6 preregistration)")
def test_r01_a_rebuilt_grid_record_with_an_unresolved_search_is_refused_on_read():
    """The read rule is the write rule: a record the router can no longer produce cannot be read back either."""
    problem = S.bimodal_two_parameter()
    calibration = problem.calibrate()
    honest = route_uncertainty(calibration=calibration, observations=problem.observations, forward=problem.forward,
                               multistart=MultistartPolicy(), rebuild=GridRebuildPolicy(problem.table_builder()))
    assert honest.decision is RouteDecision.GRID_REBUILT_FROM_LOCAL_COVARIANCE
    unassessed = local_gaussian_posterior(calibration, problem.observations, problem.forward, multistart=None)
    assert unassessed.diagnostics.uniqueness == "NOT_ASSESSED"
    payload = honest.to_dict()
    payload["local_posterior"] = unassessed.to_dict()
    with pytest.raises(HybridUQError, match="uniqueness"):
        HybridUQResult.from_dict(payload)


# ---------------------------------------------------------------------------
# R-06: a supplied grid needs a uniqueness basis
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="I-01 not implemented yet (batch 6 preregistration)")
def test_r06_a_supplied_grid_that_misses_a_found_mode_is_passed_over():
    """The audited record: GRID_AS_SUPPLIED SUPPORTED over one of two equal modes, with the caller's own
    MultistartPolicy passed in and never run."""
    problem = S.bimodal_two_parameter()
    result = route_uncertainty(grid=problem.grid(F.bimodal_one_mode_axes()), calibration=problem.calibrate(),
                               observations=problem.observations, forward=problem.forward,
                               multistart=MultistartPolicy())
    entry = _entry(result, "GRID_AS_SUPPLIED")
    assert entry["outcome"] == "PASSED_OVER"
    assert entry["reason"] == RouteReason.GRID_MISSES_A_FOUND_MODE.value
    assert "theta1" in entry["detail"]


@pytest.mark.xfail(strict=True, reason="I-01 not implemented yet (batch 6 preregistration)")
def test_r06_a_supplied_grid_with_no_uniqueness_basis_at_all_is_passed_over():
    """No search asked for, no search run, and a box narrower than the declared bounds: nothing says the
    posterior has one mode, and a grid route has no DOWNGRADED claim to say so with."""
    problem = S.bimodal_two_parameter()
    result = route_uncertainty(grid=problem.grid(F.bimodal_one_mode_axes()), calibration=problem.calibrate(),
                               observations=problem.observations, forward=problem.forward,
                               multistart=None, canonical_uniqueness_search=False)
    entry = _entry(result, "GRID_AS_SUPPLIED")
    assert entry["outcome"] == "PASSED_OVER"
    assert entry["reason"] == RouteReason.GRID_UNIQUENESS_NOT_ASSESSED.value


@pytest.mark.xfail(strict=True, reason="I-01 not implemented yet (batch 6 preregistration)")
def test_r06_a_grid_that_spans_the_declared_bounds_needs_no_search():
    """The declared bounds are the whole space the request admits, and containment has already shown the
    posterior does not reach the faces: there is no outside for a mode to hide in."""
    problem = S.bimodal_two_parameter()
    over_the_bounds = problem.grid([np.linspace(-3.0, 3.0, 1201), np.linspace(-2.0, 2.0, 801)])
    result = route_uncertainty(grid=over_the_bounds, calibration=problem.calibrate(),
                               observations=problem.observations, forward=problem.forward,
                               multistart=None, canonical_uniqueness_search=False)
    assert result.decision is RouteDecision.GRID_AS_SUPPLIED and result.claim is RouteClaim.SUPPORTED
    assert "spans the declared bounds" in _entry(result, "GRID_AS_SUPPLIED")["detail"]
    sd = np.sqrt(np.diag(np.asarray(result.covariance, dtype=float)))
    assert sd[0] == pytest.approx(1.0220179476127045, rel=1e-6)


@pytest.mark.xfail(strict=True, reason="I-01 not implemented yet (batch 6 preregistration)")
def test_r06_a_search_at_the_minimum_that_finds_one_mode_is_a_basis():
    """The route that must keep working: an honest unimodal problem, a grid narrower than its bounds."""
    problem = S.affine()
    grid = problem.grid([np.linspace(0.6, 1.3, 61), np.linspace(1.4, 2.7, 61)])
    result = route_uncertainty(grid=grid, calibration=problem.calibrate(), observations=problem.observations,
                               forward=problem.forward, multistart=MultistartPolicy())
    assert result.decision is RouteDecision.GRID_AS_SUPPLIED and result.claim is RouteClaim.SUPPORTED
    assert "MULTISTART_NO_SECOND_MODE" in _entry(result, "GRID_AS_SUPPLIED")["detail"]


@pytest.mark.xfail(strict=True, reason="I-01 not implemented yet (batch 6 preregistration)")
def test_r06_the_canonical_search_backs_a_supplied_grid_by_default():
    """With no multistart asked for, the router runs the canonical search rather than passing the grid over."""
    problem = S.affine()
    grid = problem.grid([np.linspace(0.6, 1.3, 61), np.linspace(1.4, 2.7, 61)])
    result = route_uncertainty(grid=grid, calibration=problem.calibrate(), observations=problem.observations,
                               forward=problem.forward)
    assert result.decision is RouteDecision.GRID_AS_SUPPLIED and result.claim is RouteClaim.SUPPORTED
    assert "MULTISTART_NO_SECOND_MODE" in _entry(result, "GRID_AS_SUPPLIED")["detail"]
