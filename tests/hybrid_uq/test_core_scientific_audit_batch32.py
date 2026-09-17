"""Core re-audit 2026-09-16, batch 32: a grid that cannot stand is passed over, and uniformity is an effect.

Problems R-30 and R-29 (benchmarks/core_v4_false_confidence/REAUDIT_2026-09-16.json), improvement I-07
part A of two, under benchmarks/core_v4_false_confidence/BATCH32_THRESHOLD_PROTOCOL.json. Part B is R-19,
the spot-check sampling.

Recorded as strict xfails in commit <XFAIL-SHA>, each seen failing on its own assertion, before the fix.
"""

from __future__ import annotations

import numpy as np
import pytest

import hybrid_synthetic as S
from engcore.hybrid_uq import MultistartPolicy, RouteClaim, RouteDecision, RouteReason, route_uncertainty
from engcore.hybrid_uq import _grid_evidence as GE
from engcore.hybrid_uq.vocabulary import HybridUQError


# ---------------------------------------------------------------------------
# R-30: a grid off at solver-tolerance level aborted the whole request
# ---------------------------------------------------------------------------
def _linear_problem():
    x = np.linspace(0.1, 1.0, 6)
    return S.Problem("R30_binding", lambda t, x: t[0] * np.asarray(x, dtype=float), x, (1.0,), 1.0e-4,
                     (0.05,), (4.0,), (1.0,))


def _nudged_grid(problem, relative=1.0e-9):
    """A grid whose log-likelihood is off by a solver's own convergence, not by a different model."""
    grid = problem.grid([np.linspace(0.05, 4.0, 41)])
    shifted = np.asarray(grid.log_likelihood, dtype=float) * (1.0 + relative)
    mask = np.asarray(grid.admissible_mask, dtype=bool)
    # The record's own invariant is that the weights ARE the likelihood, so they move with it.
    weight = np.where(mask & np.isfinite(shifted), np.exp(shifted - np.max(shifted[mask])), 0.0)
    return type(grid)(
        parameter_names=grid.parameter_names,
        points=grid.points,
        weights=weight / np.sum(weight),
        log_likelihood=shifted,
        admissible_mask=mask,
        dataset_id=grid.dataset_id,
    )


@pytest.mark.xfail(strict=True, reason="R-30: the binding raises from inside the router")
def test_r30_a_binding_mismatch_passes_the_grid_over_instead_of_aborting_the_request():
    problem = _linear_problem()
    result = route_uncertainty(grid=_nudged_grid(problem), calibration=problem.calibrate(),
                               observations=problem.observations, forward=problem.forward,
                               multistart=MultistartPolicy())
    assert result.decision is not RouteDecision.GRID_AS_SUPPLIED
    rows = [row for row in result.considered if row["route"] == "GRID_AS_SUPPLIED"]
    assert rows and rows[0]["outcome"] == "PASSED_OVER", rows
    assert rows[0]["reason"] == RouteReason.GRID_NOT_THIS_EVIDENCE.value, rows[0]


@pytest.mark.xfail(strict=True, reason="R-30: the whole request aborts")
def test_r30_the_request_is_still_answered_by_the_route_that_can_answer_it():
    """The audited comparison: the same request WITHOUT the grid is LOCAL_GAUSSIAN SUPPORTED."""
    problem = _linear_problem()
    without = route_uncertainty(calibration=problem.calibrate(), observations=problem.observations,
                                forward=problem.forward, multistart=MultistartPolicy())
    with_grid = route_uncertainty(grid=_nudged_grid(problem), calibration=problem.calibrate(),
                                  observations=problem.observations, forward=problem.forward,
                                  multistart=MultistartPolicy())
    assert without.claim is RouteClaim.SUPPORTED
    assert with_grid.decision is without.decision, (
        f"supplying a grid that is not this request's evidence changed the answer from "
        f"{without.decision.value} to {with_grid.decision.value}; a fact about the grid is not a fact "
        f"about the request"
    )


@pytest.mark.xfail(strict=True, reason="R-30: both chi-squares print as 1064.66")
def test_r30_the_mismatch_is_reported_in_digits_and_units_a_reader_can_act_on():
    problem = _linear_problem()
    result = route_uncertainty(grid=_nudged_grid(problem), calibration=problem.calibrate(),
                               observations=problem.observations, forward=problem.forward,
                               multistart=MultistartPolicy())
    detail = next(row for row in result.considered if row["route"] == "GRID_AS_SUPPLIED").get("detail", "")
    assert "sigma" in detail, f"the disagreement must be stated in the unit its tolerance is: {detail!r}"
    numbers = [word for word in detail.replace(",", " ").split() if word.count(".") == 1 and word[0].isdigit()]
    assert any(len(word.split(".")[1]) >= 12 for word in numbers), (
        f"the two chi-squares printed as 1064.66 and 1064.66 in the audited message, six significant "
        f"figures for a disagreement at the twelfth. Detail: {detail!r}"
    )


@pytest.mark.xfail(strict=True, reason="R-30: there is no GRID_NOT_THIS_EVIDENCE yet")
def test_r30_a_grid_from_another_model_is_still_refused_as_not_this_evidence():
    """The control: passing over is not the same as accepting."""
    problem = _linear_problem()
    result = route_uncertainty(grid=_nudged_grid(problem, relative=0.5), calibration=problem.calibrate(),
                               observations=problem.observations, forward=problem.forward,
                               multistart=MultistartPolicy())
    assert result.decision is not RouteDecision.GRID_AS_SUPPLIED
    rows = [row for row in result.considered if row["route"] == "GRID_AS_SUPPLIED"]
    assert rows[0]["reason"] == RouteReason.GRID_NOT_THIS_EVIDENCE.value


def test_r30_the_raising_entry_point_still_raises():
    """`require_grid_is_this_evidence` keeps its name, its signature and its behaviour."""
    problem = _linear_problem()
    with pytest.raises(HybridUQError, match="not"):
        GE.require_grid_is_this_evidence(_nudged_grid(problem), problem.calibrate(),
                                         problem.observations, problem.forward)


# ---------------------------------------------------------------------------
# R-29: uniformity was judged per step, not by what the node density would move
# ---------------------------------------------------------------------------
def _log_problem():
    x = np.linspace(0.1, 1.0, 5)
    observed = x * 0.2 + np.random.default_rng(11).normal(0, 0.01, len(x))
    return S.Problem("R29_prior", lambda t, x: t[0] * np.asarray(x, dtype=float), x, (0.2,), 0.01,
                     (0.05,), (4.0,), (0.2,), observed=observed, transforms=("log",))


#: The audited pair: a LOG-declared parameter whose grid is evenly spaced in NATURAL units over +/-2%.
NATURAL = np.linspace(0.19957772 * 0.98, 0.19957772 * 1.02, 401)
LOGGED = np.geomspace(0.19957772 * 0.98, 0.19957772 * 1.02, 401)


@pytest.mark.xfail(strict=True, reason="R-29: uniformity is judged per step")
def test_r29_a_grid_that_is_uniform_in_effect_is_not_refused_on_a_step_deviation():
    problem = _log_problem()
    result = route_uncertainty(grid=problem.grid([NATURAL]), calibration=problem.calibrate(),
                               observations=problem.observations, forward=problem.forward)
    rows = [row for row in result.considered if row["route"] == "GRID_AS_SUPPLIED"]
    assert rows[0].get("reason") != RouteReason.GRID_PRIOR_NOT_UNIFORM_IN_INFERENCE_COORDINATES.value, (
        f"the grid's moments match the accepted log-spaced grid's to six digits, and it is refused for a "
        f"2% step deviation: {rows[0]}"
    )


@pytest.mark.xfail(strict=True, reason="R-29: the bound it is stated in does not exist yet")
def test_r29_the_two_spellings_of_one_prior_report_the_same_moments():
    """Why the refusal was wrong: the two grids ARE the same posterior to six digits."""
    problem = _log_problem()
    moments = {}
    for label, axis in (("natural", NATURAL), ("logged", LOGGED)):
        grid = problem.grid([axis])
        weight = np.exp(np.asarray(grid.log_likelihood, dtype=float)
                        - np.max(np.asarray(grid.log_likelihood, dtype=float)))
        weight = weight / np.sum(weight)
        node = np.asarray(grid.points, dtype=float)[:, 0]
        mean = float(np.sum(weight * node))
        moments[label] = (mean, float(np.sqrt(np.sum(weight * (node - mean) ** 2))))
    # Stated in the unit the rule is stated in: the two spellings' means differ by a fraction of the sd
    # far below PRIOR_REWEIGHT_MOMENT_SD, and their sds agree to a relative 1e-3. The audit's own fixture
    # gave means of 0.19957772 and 0.19957611 against an sd of 0.00056666, a difference of 0.0029 sd.
    offset = abs(moments["natural"][0] - moments["logged"][0]) / moments["logged"][1]
    assert offset < GE.PRIOR_REWEIGHT_MOMENT_SD, (
        f"the two spellings of one prior differ by {offset:.4g} sd in their mean, which is not 'the same "
        f"posterior' at the resolution the rule is written in"
    )
    assert moments["natural"][1] == pytest.approx(moments["logged"][1], rel=1e-3)


@pytest.mark.xfail(strict=True, reason="R-29: there is no moment-effect bound yet")
def test_r29_the_moment_effect_bound_exists_and_is_the_repositorys_own_resolution():
    assert hasattr(GE, "PRIOR_REWEIGHT_MOMENT_SD"), (
        "engcore.hybrid_uq._grid_evidence has no PRIOR_REWEIGHT_MOMENT_SD; the rule "
        "'prior_uniformity_is_judged_by_what_the_node_density_would_move' needs it"
    )
    from engcore.hybrid_uq.router import TRUNCATION_CONVERGENCE_SD

    assert GE.PRIOR_REWEIGHT_MOMENT_SD == TRUNCATION_CONVERGENCE_SD, (
        "the bound is the resolution at which this core already declares a moment unchanged; if the two "
        "drift apart the reuse argument in BATCH32_THRESHOLD_PROTOCOL.json stops holding"
    )


@pytest.mark.parametrize(
    "axis",
    [np.concatenate([np.linspace(0.05, 1.0, 350, endpoint=False), np.linspace(1.0, 4.0, 60)]),
     np.geomspace(0.05, 4.0, 400)],
    ids=["clustered", "geomspace_identity"],
)
def test_r29_a_node_density_that_does_move_the_moments_is_still_refused(axis):
    """The control, and the direction that matters: a heaped grid is an undeclared prior and stays refused."""
    x = np.linspace(0.1, 1.0, 5)
    observed = x + np.random.default_rng(11).normal(0, 0.25, len(x))
    problem = S.Problem("R29_control", lambda t, x: t[0] * np.asarray(x, dtype=float), x, (1.0,), 0.25,
                        (0.05,), (4.0,), (1.0,), observed=observed)
    result = route_uncertainty(grid=problem.grid([axis]), calibration=problem.calibrate(),
                               observations=problem.observations, forward=problem.forward)
    assert result.decision is not RouteDecision.GRID_AS_SUPPLIED
    rows = [row for row in result.considered if row["route"] == "GRID_AS_SUPPLIED"]
    assert rows[0]["reason"] == RouteReason.GRID_PRIOR_NOT_UNIFORM_IN_INFERENCE_COORDINATES.value, rows[0]
