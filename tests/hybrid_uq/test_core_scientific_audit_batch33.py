"""Core re-audit 2026-09-16, batch 33: the spot-checked rows are not the supplier's to choose.

Problem R-19 (benchmarks/core_v4_false_confidence/REAUDIT_2026-09-16.json), improvement I-07 part B of
two, under benchmarks/core_v4_false_confidence/BATCH33_THRESHOLD_PROTOCOL.json.

Recorded as strict xfails in commit <XFAIL-SHA>, each seen failing on its own assertion, before the fix.
"""

from __future__ import annotations

import hashlib
import inspect
import math

import numpy as np
import pytest

import hybrid_synthetic as S
from engcore.hybrid_uq import MultistartPolicy, RouteDecision, RouteReason, route_uncertainty
from engcore.hybrid_uq import _grid_evidence as GE
from engcore.hybrid_uq import router as RO

AXES = [np.linspace(0.6, 1.4, 141), np.linspace(1.4, 2.6, 141)]


def _problem():
    return S.affine("R19_grind")


def _forged(problem, grid, sharpen=4.0, share=0.25, tail_nudge=0.0):
    """The audited forgery: keep the fixed rows honest, sharpen the posterior bulk.

    The bulk is the ``share`` highest-weight nodes, whose log-likelihood is pushed ``sharpen`` times further
    below the peak -- which narrows every reported width. ``tail_nudge`` adds a change of that size to one
    far-tail node, which moves no posterior weight and is the audit's grinding step: it re-rolls the seed
    that the baseline draws its rows from, at no cost to the forger.
    """
    ll = np.asarray(grid.log_likelihood, dtype=np.float64).copy()
    mask = np.asarray(grid.admissible_mask, dtype=bool)
    peak = float(np.max(ll[mask]))
    order = np.argsort(np.where(mask, ll, -np.inf))[::-1]
    bulk = order[: max(int(share * int(np.sum(mask))), 1)]
    # The four rows the baseline always checks are left exactly as they were.
    honest = {0, len(ll) - 1, int(np.argmax(np.where(mask, ll, -np.inf)))}
    bulk = np.asarray([row for row in bulk if int(row) not in honest], dtype=int)
    ll[bulk] = peak - sharpen * (peak - ll[bulk])
    if tail_nudge:
        ll[order[-1]] += tail_nudge
    weight = np.where(mask & np.isfinite(ll), np.exp(ll - np.max(ll[mask])), 0.0)
    return type(grid)(parameter_names=grid.parameter_names, points=grid.points,
                      weights=weight / np.sum(weight), log_likelihood=ll,
                      admissible_mask=mask, dataset_id=grid.dataset_id)


def _binding(problem, grid, **kw):
    return GE.grid_is_this_evidence(grid, problem.calibrate(), problem.observations, problem.forward, **kw)


# ---------------------------------------------------------------------------
# the_rows_are_drawn_from_a_seed_the_supplier_does_not_control
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-19: the seed is a digest of the grid's own bytes")
def test_r19_the_binding_takes_a_verifier_side_nonce():
    signature = inspect.signature(GE.grid_is_this_evidence)
    assert "nonce" in signature.parameters, (
        "grid_is_this_evidence takes no nonce; the rule "
        "'the_rows_are_drawn_from_a_seed_the_supplier_does_not_control' needs one"
    )
    assert signature.parameters["nonce"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["nonce"].default is None, (
        "the default must be a FRESH nonce, so a caller who passes nothing gets one the supplier could not "
        "have searched"
    )


@pytest.mark.xfail(strict=True, reason="R-19: the draw IS a function of them")
def test_r19_the_draw_is_not_a_function_of_the_grids_own_bytes():
    """Two calls with no nonce must not check the same rows, or the seed is still the grid's."""
    problem = _problem()
    grid = problem.grid(AXES)
    seen = set()
    for _ in range(6):
        rows = GE._spot_check_rows(grid, problem.calibrate(), nonce=None)
        seen.add(tuple(sorted(rows)))
    assert len(seen) > 1, (
        "six draws with no nonce chose the same rows every time, so the seed is a function of something the "
        "supplier controls -- which is what two grinding attempts defeated"
    )


@pytest.mark.xfail(strict=True, reason="R-19: there is no nonce and no row helper")
def test_r19_a_pinned_nonce_makes_the_draw_reproducible():
    """The other half: a test, or an audit, must be able to replay a draw."""
    problem = _problem()
    grid = problem.grid(AXES)
    first = GE._spot_check_rows(grid, problem.calibrate(), nonce=b"\x01" * 32)
    second = GE._spot_check_rows(grid, problem.calibrate(), nonce=b"\x01" * 32)
    assert tuple(sorted(first)) == tuple(sorted(second))
    other = GE._spot_check_rows(grid, problem.calibrate(), nonce=b"\x02" * 32)
    assert tuple(sorted(first)) != tuple(sorted(other))


@pytest.mark.xfail(strict=True, reason="R-19: two grinding attempts were enough")
def test_r19_a_ground_forgery_no_longer_survives_the_draw():
    """The audited attack, and the grinding step that made it cheap.

    The baseline needed two attempts: the forger changes one far-tail log-likelihood by 1e-9, which moves no
    posterior weight, until the four seeded rows miss the bulk. With a verifier-side nonce the forger has
    nothing to grind against, so the attack is tried 12 times with 12 different nudges and every one is
    caught.
    """
    problem = _problem()
    honest = problem.grid(AXES)
    for attempt in range(12):
        forged = _forged(problem, honest, tail_nudge=1.0e-9 * (attempt + 1))
        problem_found = _binding(problem, forged, nonce=bytes([attempt + 1]) * 32)
        assert problem_found is not None and problem_found[0] is RouteReason.GRID_NOT_THIS_EVIDENCE, (
            f"grinding attempt {attempt} produced a forged grid the binding accepted"
        )


@pytest.mark.xfail(strict=True, reason="R-19: the nonce keyword does not exist yet")
def test_r19_the_honest_grid_is_still_this_requests_evidence():
    """The control. A check that refuses everything detects nothing."""
    problem = _problem()
    for attempt in range(12):
        assert _binding(problem, problem.grid(AXES), nonce=bytes([attempt + 1]) * 32) is None


# ---------------------------------------------------------------------------
# the_rows_are_sampled_by_posterior_weight
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-19: four rows, chosen by the supplier's seed")
def test_r19_the_sample_size_is_computed_from_a_stated_detection_probability():
    assert hasattr(GE, "SPOT_CHECK_WEIGHTED_ROWS") and hasattr(GE, "SPOT_CHECK_INADMISSIBLE_ROWS")
    expected = math.ceil(math.log(1.0 - 0.99) / math.log(1.0 - 0.25))
    assert GE.SPOT_CHECK_WEIGHTED_ROWS == expected == 17, (
        "17 weight-proportional draws miss a region holding a quarter of the posterior weight with "
        "probability at most 0.01; the audited forgery tampered 25.3% of the nodes"
    )
    assert GE.SPOT_CHECK_INADMISSIBLE_ROWS == expected


@pytest.mark.xfail(strict=True, reason="R-19: the draw is uniform over node indices")
def test_r19_the_draw_lands_where_the_posterior_weight_is():
    """Weight-proportional, not uniform: the bulk is what a moment is made of."""
    problem = _problem()
    grid = problem.grid(AXES)
    weight = np.asarray(grid.weights, dtype=float)
    order = np.argsort(weight)[::-1]
    bulk = set(int(r) for r in order[: max(int(0.25 * len(weight)), 1)])
    hits = 0
    for attempt in range(20):
        rows = GE._spot_check_rows(grid, problem.calibrate(), nonce=bytes([attempt + 1]) * 32)
        hits += len(bulk & set(int(r) for r in rows))
    assert hits >= 20, (
        f"over 20 draws the checked rows landed in the 25% highest-weight nodes only {hits} times; a "
        f"weight-proportional sample of 17 should land there almost every draw"
    )


@pytest.mark.xfail(strict=True, reason="R-19: inadmissible marks go unchecked")
def test_r19_an_inadmissible_node_the_model_admits_is_caught():
    """An inadmissible node carries ZERO weight, so a weighted draw can never reach one."""
    problem = _problem()
    grid = problem.grid(AXES)
    mask = np.asarray(grid.admissible_mask, dtype=bool).copy()
    ll = np.asarray(grid.log_likelihood, dtype=float).copy()
    # Remove a quarter of the posterior's own support by marking it refused: mass deleted without a
    # likelihood being touched.
    order = np.argsort(np.where(mask, ll, -np.inf))[::-1]
    victims = order[: max(int(0.25 * int(np.sum(mask))), 1)]
    honest_rows = {0, len(ll) - 1, int(np.argmax(np.where(mask, ll, -np.inf)))}
    victims = np.asarray([row for row in victims if int(row) not in honest_rows], dtype=int)
    mask[victims] = False
    ll[victims] = -np.inf
    weight = np.where(mask & np.isfinite(ll), np.exp(ll - np.max(ll[mask])), 0.0)
    forged = type(grid)(parameter_names=grid.parameter_names, points=grid.points,
                        weights=weight / np.sum(weight), log_likelihood=ll,
                        admissible_mask=mask, dataset_id=grid.dataset_id)
    caught = sum(1 for attempt in range(8)
                 if _binding(problem, forged, nonce=bytes([attempt + 1]) * 32) is not None)
    assert caught == 8, f"a quarter of the support marked refused was caught {caught} times in 8 draws"


# ---------------------------------------------------------------------------
# every_face_is_checked_because_containment_depends_on_it
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-19: face nodes go unchecked, which defeats containment")
def test_r19_the_highest_node_of_every_face_is_checked():
    problem = _problem()
    grid = problem.grid(AXES)
    shape = (len(AXES[0]), len(AXES[1]))
    ll = np.asarray(grid.log_likelihood, dtype=float).reshape(shape)
    faces = set()
    for axis in range(2):
        for index in (0, -1):
            face = np.take(ll, index, axis=axis)
            flat = np.argmax(face)
            faces.add(int(np.ravel_multi_index(
                (flat, index % shape[1]) if axis == 0 else (index % shape[0], flat), shape)))
    rows = set(int(r) for r in GE._spot_check_rows(grid, problem.calibrate(), nonce=b"\x07" * 32))
    assert faces <= rows, (
        f"the faces' highest nodes {sorted(faces)} are what grid_containment reads, and a contained "
        f"posterior has almost no weight there, so a weighted draw is least likely to reach them. "
        f"Missing: {sorted(faces - rows)}"
    )


# ---------------------------------------------------------------------------
# the_rebuilt_table_check_gets_the_same_rule
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-19: the rebuilt-table check has the same gap")
def test_r19_the_rebuilt_table_check_takes_a_nonce_too():
    signature = inspect.signature(RO._require_table_agrees_with_forward)
    assert "nonce" in signature.parameters, (
        "router._require_table_agrees_with_forward takes no nonce; the audit says in one sentence that a "
        "rebuild table_builder can do the same to it"
    )
    assert signature.parameters["nonce"].kind is inspect.Parameter.KEYWORD_ONLY


@pytest.mark.xfail(strict=True, reason="R-19: it seeds from the table's own values and mask")
def test_r19_the_rebuilt_table_check_no_longer_seeds_from_the_table():
    source = inspect.getsource(RO._require_table_agrees_with_forward)
    assert "hashlib.sha256(np.ascontiguousarray(table.values" not in source, (
        "the rebuilt-table check still draws its rows from a digest of the table's own values and mask, "
        "which is the seed the supplier controls"
    )


def test_r19_an_honest_rebuild_still_routes():
    """The control for the rebuild half: the cost went up, the verdict did not change.

    `affine` never reaches the rebuild -- its local route is USED, and the rebuild is only tried when the
    local route cannot stand. Batch 31's contained one-sided case does reach it and is SUPPORTED there, so
    it is the fixture that can say the rebuild still works.
    """
    import false_confidence_cases as F
    from engcore.hybrid_uq import GridRebuildPolicy, RouteClaim

    problem = F.one_sided_declared_bound(40.0, rate=8.0)
    result = route_uncertainty(calibration=problem.calibrate(), observations=problem.observations,
                               forward=problem.forward, rebuild=GridRebuildPolicy(problem.table_builder()),
                               multistart=MultistartPolicy())
    rows = [row for row in result.considered if str(row["route"]).startswith("GRID_REBUILT")]
    assert rows and rows[0]["outcome"] == "USED", rows
    assert result.claim is RouteClaim.SUPPORTED
    assert result.decision is not RouteDecision.GRID_AS_SUPPLIED
