"""Audit stream "hybrid": the grid routes at their trust boundary (HUQ-02, HUQ-04, HUQ-05, HUQ-06).

HUQ-02  grid_predictive_uncertainty stamped SUPPORTED on a 3 x 3 grid the router itself refuses;
HUQ-04  grid_digest ignored log_likelihood and the admissible mask, and nothing held a grid's weights to its own
        likelihood, so a refused grid could be laundered under the same digest;
HUQ-05  a rebuilt grid was checked for its coordinates, never for its values, so a builder answering with another
        model's predictions was certified;
HUQ-06  a supplied grid was never bound to the request it was routed with: other data, other parameters.

Forged grids are made by reaching past the PosteriorGrid constructor with ``object.__setattr__``, as a corrupted or
hand-built object would be, so these tests exercise the router's own checks whatever the constructor enforces.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

import hybrid_synthetic as S
from engcore.hybrid_uq import (
    GridRebuildPolicy,
    HybridUQError,
    MultistartPolicy,
    RouteDecision,
    grid_predictive_uncertainty,
    route_uncertainty,
)
from engcore.hybrid_uq.predictive import grid_digest
from engcore.inference import AdmittedForwardTable, GridResolutionError
from engcore.scientific.twins import TwinReference
from engcore.uq import PredictiveObservableSpec

AXES = [np.linspace(0.6, 1.3, 61), np.linspace(1.4, 2.7, 61)]


def _forged(grid, **arrays):
    forged = dataclasses.replace(grid)
    for name, value in arrays.items():
        object.__setattr__(forged, name, np.asarray(value))
    return forged


# ---------------------------------------------------------------------------
# HUQ-02
# ---------------------------------------------------------------------------
def test_huq02_the_grid_predictive_never_supports_a_grid_the_router_refuses():
    P = S.affine()
    coarse = P.grid([np.linspace(0.0, 2.0, 3), np.linspace(1.0, 3.0, 3)])
    # the grid is held to the evidence it describes since CORE-005 (scientific core audit 2026-09-16): a supplied grid is
    # routed only with the observations and forward model its likelihood is re-evaluated from
    routed = route_uncertainty(grid=coarse, observations=P.observations, forward=P.forward)
    assert routed.decision is RouteDecision.REFUSED and routed.considered[0]["outcome"] == "REFUSED_BY_V1"
    table = P.table_builder()(coarse.points)
    spec = PredictiveObservableSpec(observation_key=P.observations.keys[5], unit="dimensionless")
    with pytest.raises(GridResolutionError):
        grid_predictive_uncertainty(coarse, table, spec, twin=TwinReference("twin.synthetic", "1"), model=S.MODEL,
                                    source_ref="audit")


def test_huq02_the_wrapper_judges_the_grid_itself_where_the_v1_checks_would_pass():
    """The wrapper's own judgement, isolated from the resolution refusal that now shadows it.

    The 3 x 3 case above is refused twice over: by the wrapper's judgement and, since the same audit's
    INF-04 fix, by the resolution check inside the frozen predictive call. Redundancy is good and
    unobservable: removing the wrapper's judgement leaves that test green. A grid whose weights do not
    follow its own likelihood is resolved enough for V1 and is caught ONLY by the wrapper, so this is
    where the wrapper's judgement is visible.
    """
    P = S.affine()
    grid = P.grid(AXES)
    table = P.table_builder()(grid.points)
    spec = PredictiveObservableSpec(observation_key=P.observations.keys[5], unit="dimensionless")
    weights = np.array(grid.weights, copy=True)
    weights[int(np.argmax(weights))] *= 4.0
    laundered = _forged(grid, weights=weights / weights.sum())
    with pytest.raises(HybridUQError, match="softmax"):
        grid_predictive_uncertainty(laundered, table, spec, twin=TwinReference("twin.synthetic", "1"), model=S.MODEL,
                                    source_ref="audit")


def test_huq02_a_resolved_grid_is_still_supported_through_the_same_judgement():
    P = S.affine()
    grid = P.grid(AXES)
    table = P.table_builder()(grid.points)
    spec = PredictiveObservableSpec(observation_key=P.observations.keys[5], unit="dimensionless")
    record = grid_predictive_uncertainty(grid, table, spec, twin=TwinReference("twin.synthetic", "1"), model=S.MODEL,
                                         source_ref="audit", observations=P.observations, forward=P.forward)
    assert record.route_claim.value == "SUPPORTED" and record.parameter_standard_uncertainty > 0.0
    # CORE-005: without the evidence that binds it, the same grid is not SUPPORTED
    unbound = grid_predictive_uncertainty(grid, table, spec, twin=TwinReference("twin.synthetic", "1"), model=S.MODEL,
                                          source_ref="audit")
    assert unbound.route_claim.value == "DOWNGRADED" and [r.value for r in unbound.reasons] == ["GRID_NOT_BOUND_TO_EVIDENCE"]


# ---------------------------------------------------------------------------
# HUQ-04
# ---------------------------------------------------------------------------
def test_huq04_the_grid_digest_covers_the_likelihood_and_the_mask():
    grid = S.affine().grid(AXES)
    assert grid_digest(_forged(grid, log_likelihood=np.zeros_like(grid.log_likelihood))) != grid_digest(grid)
    mask = np.array(grid.admissible_mask, copy=True)
    mask[0] = not mask[0]
    assert grid_digest(_forged(grid, admissible_mask=mask)) != grid_digest(grid)


def test_huq04_a_refused_grid_laundered_with_a_smooth_likelihood_is_refused():
    P = S.weak_identification()
    aliased = P.grid([np.linspace(-50, 50, 401), np.linspace(-5, 5, 401)])
    top = aliased.points[int(np.argmax(aliased.weights))]
    steps = np.array([100 / 400, 10 / 400])
    broad = -0.5 * np.sum(((aliased.points - top) / (40 * steps)) ** 2, axis=1)
    laundered = _forged(aliased, log_likelihood=broad)
    with pytest.raises(HybridUQError, match="softmax"):
        route_uncertainty(grid=laundered)


def test_huq04_sharpened_weights_over_an_honest_likelihood_are_refused():
    grid = S.affine().grid(AXES)
    w = np.exp(4.0 * (grid.log_likelihood - grid.log_likelihood.max()))
    with pytest.raises(HybridUQError, match="softmax"):
        route_uncertainty(grid=_forged(grid, weights=w / w.sum()))


# ---------------------------------------------------------------------------
# HUQ-05
# ---------------------------------------------------------------------------
def _other_model(honest, observed, factor=4.0, rows=None):
    def build(points):
        t = honest(points)
        values = np.array(t.values, copy=True)
        selected = slice(None) if rows is None else rows(t)
        values[selected] = observed[None, :] + factor * (values[selected] - observed[None, :])
        return AdmittedForwardTable(parameter_names=t.parameter_names, observation_keys=t.observation_keys, points=t.points,
                                    values=values, admissible_mask=t.admissible_mask, admission_refs=t.admission_refs,
                                    rejection_reasons=t.rejection_reasons)
    return build


def test_huq05_a_rebuild_table_from_another_model_is_never_certified():
    F = S.strong_nonlinearity()
    calibration = F.calibrate()
    builder = _other_model(F.table_builder(), F.observed)
    with pytest.raises(HybridUQError, match="forward"):
        route_uncertainty(calibration=calibration, observations=F.observations, forward=F.forward,
                          multistart=MultistartPolicy(), rebuild=GridRebuildPolicy(builder))


def test_huq05_a_table_altered_only_at_its_peak_is_caught():
    F = S.strong_nonlinearity()
    calibration = F.calibrate()

    def peak(table):
        residual = (np.asarray(table.values) - F.observed[None, :]) / F.sigma[None, :]
        return [int(np.argmin(np.sum(residual ** 2, axis=1)))]

    builder = _other_model(F.table_builder(), F.observed, factor=0.5, rows=peak)
    with pytest.raises(HybridUQError, match="forward"):
        route_uncertainty(calibration=calibration, observations=F.observations, forward=F.forward,
                          multistart=MultistartPolicy(), rebuild=GridRebuildPolicy(builder))


# ---------------------------------------------------------------------------
# HUQ-06
# ---------------------------------------------------------------------------
def test_huq06_a_grid_for_other_data_is_not_routed_for_this_request():
    """Since CORE-005 a grid of other data is refused by content (test_core005_*). The dataset-id guard is kept for what
    content cannot see: a grid that names another dataset. B carries A's exact observations under another id, so only
    the label guard can refuse it -- otherwise the content refusal shadows this guard and a mutation removing it lives."""
    A = S.affine("A")
    B = S.affine("B", observed=A.observed)
    with pytest.raises(HybridUQError, match="computed from dataset 'synthetic.B'"):
        route_uncertainty(grid=B.grid(AXES), calibration=A.calibrate(), observations=A.observations, forward=A.forward,
                          multistart=MultistartPolicy())
    other = S.affine("A", seed=999)
    with pytest.raises(HybridUQError, match="not this request's evidence"):
        route_uncertainty(grid=other.grid(AXES), calibration=A.calibrate(), observations=A.observations, forward=A.forward,
                          multistart=MultistartPolicy())


def test_huq06_a_grid_over_other_parameters_is_not_routed_for_this_request():
    A = S.affine("A")
    W = S.Problem("A", lambda t, x: t[0] + t[1] * x, np.linspace(0, 1, 12), (5.0, -3.0), 0.05, (-10, -10), (10, 10), (0, 0),
                  names=("R_ohm", "C_farad"))
    grid = W.grid([np.linspace(4.6, 5.4, 61), np.linspace(-3.7, -2.3, 61)])
    assert grid.dataset_id == A.observations.dataset_id
    with pytest.raises(HybridUQError, match="parameter"):
        route_uncertainty(grid=grid, calibration=A.calibrate(), observations=A.observations, forward=A.forward)
