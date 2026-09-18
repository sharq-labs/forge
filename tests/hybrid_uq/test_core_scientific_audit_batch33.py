"""Core re-audit 2026-09-16, batch 33: the spot-checked rows are not the supplier's to choose.

Problem R-19 (benchmarks/core_v4_false_confidence/REAUDIT_2026-09-16.json), improvement I-07 part B of
two, under benchmarks/core_v4_false_confidence/BATCH33_THRESHOLD_PROTOCOL.json.

Recorded as strict xfails in commit 2ff40531, each seen failing on its own assertion, before the fix.
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


def test_r19_the_draw_is_not_a_function_of_the_grids_own_bytes(monkeypatch):
    """Two calls with no nonce must not check the same rows, or the seed is still the supplier's.

    Observed THROUGH `grid_is_this_evidence`, not by calling the row chooser directly: mutation B33b pins
    the nonce to a constant at that call site, which a direct call to the chooser cannot see. The captured
    nonces are checked too, because a caller that hard-codes one is worse than the grid's own bytes -- it
    never even changes.
    """
    problem = _problem()
    grid = problem.grid(AXES)
    seen, nonces = set(), []
    original = GE._spot_check_rows

    def capturing(grid_, calibration_, *, nonce=None):
        nonces.append(nonce)
        rows = original(grid_, calibration_, nonce=nonce)
        seen.add(tuple(sorted(rows)))
        return rows

    monkeypatch.setattr(GE, "_spot_check_rows", capturing)
    for _ in range(6):
        _binding(problem, grid)
    assert len(seen) > 1, (
        "six checks with no nonce chose the same rows every time, so the seed is a function of something "
        "the supplier controls -- which is what two grinding attempts defeated"
    )
    assert len(set(nonces)) == 6 or nonces == [None] * 6, (
        f"the binding handed the chooser a repeated nonce: {nonces!r}. A verifier-side nonce is fresh per "
        f"call, or it is a constant the supplier searches once"
    )


def test_r19_a_pinned_nonce_makes_the_draw_reproducible():
    """The other half: a test, or an audit, must be able to replay a draw."""
    problem = _problem()
    grid = problem.grid(AXES)
    first = GE._spot_check_rows(grid, problem.calibrate(), nonce=b"\x01" * 32)
    second = GE._spot_check_rows(grid, problem.calibrate(), nonce=b"\x01" * 32)
    assert tuple(sorted(first)) == tuple(sorted(second))
    other = GE._spot_check_rows(grid, problem.calibrate(), nonce=b"\x02" * 32)
    assert tuple(sorted(first)) != tuple(sorted(other))


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


def test_r19_the_honest_grid_is_still_this_requests_evidence():
    """The control. A check that refuses everything detects nothing."""
    problem = _problem()
    for attempt in range(12):
        assert _binding(problem, problem.grid(AXES), nonce=bytes([attempt + 1]) * 32) is None


# ---------------------------------------------------------------------------
# the_rows_are_sampled_by_posterior_weight
# ---------------------------------------------------------------------------
def test_r19_the_sample_size_is_computed_from_a_stated_detection_probability():
    assert hasattr(GE, "SPOT_CHECK_WEIGHTED_ROWS") and hasattr(GE, "SPOT_CHECK_INADMISSIBLE_ROWS")
    expected = math.ceil(math.log(1.0 - 0.99) / math.log(1.0 - 0.25))
    assert GE.SPOT_CHECK_WEIGHTED_ROWS == expected == 17, (
        "17 weight-proportional draws miss a region holding a quarter of the posterior weight with "
        "probability at most 0.01; the audited forgery tampered 25.3% of the nodes"
    )
    assert GE.SPOT_CHECK_INADMISSIBLE_ROWS == expected


def test_r19_the_draw_lands_where_the_posterior_weight_is():
    """Weight-proportional, not uniform: the bulk is what a moment is made of."""
    problem = _problem()
    grid = problem.grid(AXES)
    weight = np.asarray(grid.weights, dtype=float)
    order = np.argsort(weight)[::-1]
    # The smallest set of nodes holding 95% of the posterior MASS -- not the top 25% of node COUNT, which is
    # a quarter of the box and which a uniform draw hits just as often. Mutation B33d survived that weaker
    # version. On this grid the mass set is a small fraction of the nodes, so a weighted draw lands in it
    # almost always and a uniform one almost never.
    cumulative = np.cumsum(weight[order])
    mass = set(int(r) for r in order[: int(np.searchsorted(cumulative, 0.95)) + 1])
    share = len(mass) / len(weight)
    assert share < 0.1, f"the fixture's 95% mass set is {share:.3g} of the nodes, too large to discriminate"
    hits = 0
    draws = 20
    for attempt in range(draws):
        rows = GE._spot_check_rows(grid, problem.calibrate(), nonce=bytes([attempt + 1]) * 32)
        hits += len(mass & set(int(r) for r in rows))
    # A weighted draw of 17 puts essentially every one of them in the mass set; a uniform draw over the
    # admissible nodes would put about `share` of them there, which for this fixture is under two per draw.
    assert hits >= 10 * draws, (
        f"over {draws} draws the checked rows landed in the nodes holding 95% of the posterior mass "
        f"({share:.3g} of the grid) only {hits} times; a weight-proportional sample of "
        f"{GE.SPOT_CHECK_WEIGHTED_ROWS} should land there almost every time"
    )


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
def test_r19_the_highest_node_of_every_face_is_checked():
    problem = _problem()
    grid = problem.grid(AXES)
    shape = (len(AXES[0]), len(AXES[1]))
    ll = np.asarray(grid.log_likelihood, dtype=float).reshape(shape)
    faces = set()
    for axis in range(2):
        for index in (0, shape[axis] - 1):
            # Taking index ALONG `axis` leaves a slice over the other axis, so the fixed index goes at
            # position `axis` and the argmax at the other. The first version of this test had the two the
            # wrong way round and reported four nodes that are not faces at all.
            face = np.take(ll, index, axis=axis)
            position = [int(np.argmax(face))]
            position.insert(axis, index)
            faces.add(int(np.ravel_multi_index(tuple(position), shape)))
    rows = set(int(r) for r in GE._spot_check_rows(grid, problem.calibrate(), nonce=b"\x07" * 32))
    assert faces <= rows, (
        f"the faces' highest nodes {sorted(faces)} are what grid_containment reads, and a contained "
        f"posterior has almost no weight there, so a weighted draw is least likely to reach them. "
        f"Missing: {sorted(faces - rows)}"
    )


# ---------------------------------------------------------------------------
# the_rebuilt_table_check_gets_the_same_rule
# ---------------------------------------------------------------------------
def test_r19_the_rebuilt_table_check_takes_a_nonce_too():
    signature = inspect.signature(RO._require_table_agrees_with_forward)
    assert "nonce" in signature.parameters, (
        "router._require_table_agrees_with_forward takes no nonce; the audit says in one sentence that a "
        "rebuild table_builder can do the same to it"
    )
    assert signature.parameters["nonce"].kind is inspect.Parameter.KEYWORD_ONLY


def test_r19_the_rebuilt_table_check_no_longer_seeds_from_the_table():
    source = inspect.getsource(RO._require_table_agrees_with_forward)
    seeding = [line for line in source.splitlines() if "hashlib.sha256(" in line]
    assert seeding, "the rebuilt-table check no longer seeds anything at all"
    # Whatever the seed is built from, it must not be the TABLE. Asserted over the whole seed expression
    # rather than as one exact substring: mutation B33g survived that, by wrapping the same digest of
    # `table.values` in a `nonce if nonce is not None else ...` that did not match the string being looked
    # for.
    joined = " ".join(seeding)
    assert "table" not in joined and "mask" not in joined and "predictions" not in joined, (
        f"the rebuilt-table check still draws its rows from a digest of the table's own bytes, which is the "
        f"seed the supplier controls: {joined!r}"
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
