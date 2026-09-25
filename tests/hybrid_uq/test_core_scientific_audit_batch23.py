"""Batch 23 of the 2026-09-16 core re-audit: a routed prediction's own numbers (I-13 part B).

Part A bound a prediction's DOMAIN statement to its calibration. Part B is the two problems about the
prediction's NUMBERS.

* **R-37.** The linearized nonlinearity is ONE number pooled across every spec in a call, and it is never
  refused. A prediction whose parameter standard uncertainty is 0 and whose probes move it records
  `predictive_nonlinearity = inf` and is emitted DOWNGRADED; and an exactly affine prediction in the same
  call as a quadratic one records the quadratic one's inf as its own.
* **R-23.** A grid-route prediction reads its numbers out of a predictive TABLE and never checks the table
  against the `predict` the caller passed in the same call. A table of twice the model gives a SUPPORTED mean
  of 3.949 where the honest answer is 1.975.

Preregistered in `benchmarks/core_v4_false_confidence/BATCH23_THRESHOLD_PROTOCOL.json`. No new threshold: the
nonlinearity rule is a finiteness requirement and a per-row maximum, and the table check is an identity at
three named nodes to floating-point roundoff.

The nine reproductions that reproduced were committed as strict xfails in `49e0b2f2`, before any of part B
was written, and each was confirmed there to fail on its own assertion. The markers came off in the
implementing commit. The tenth held already and was unmarked at preregistration, with a comment above it
saying why it is kept.
"""

from __future__ import annotations

import dataclasses
import math

import hybrid_synthetic as S
import numpy as np
import pytest

from engcore.hybrid_uq import (
    MultistartPolicy,
    RouteClaim,
    RouteDecision,
    RouteReason,
    grid_predictive_uncertainty,
    linearized_predictive_uq,
    local_gaussian_posterior,
    route_uncertainty,
    routed_predictive_uncertainty,
)
from engcore.hybrid_uq.sensitivity import RouteRefusedError
from engcore.hybrid_uq.vocabulary import HybridUQError
from engcore.scientific.twins import TwinReference
from engcore.scientific.units.quantity import Quantity
from engcore.uq import PredictiveObservableSpec

UNIT = "dimensionless"
#: Total predictive uncertainty refuses to treat an undeclared observation noise as zero, so every
#: fixture declares one. Its size is immaterial to the nonlinearity / table claims these tests are about.
NOISE = Quantity(0.05, UNIT)
TWIN = TwinReference("twin.synthetic", "1")


def _module():
    import engcore.hybrid_uq.predictive as module

    return module


def _symbol(module, name):
    """A named helper, asserted rather than assumed, so a reproduction fails on its assertion."""
    value = getattr(module, name, None)
    assert value is not None, f"engcore.hybrid_uq.predictive.{name} is what part B adds"
    return value


def _takes_predict(func):
    """``predict`` on the grid path, asserted rather than assumed, so a reproduction fails on its assertion."""
    import inspect

    assert "predict" in inspect.signature(func).parameters, (
        f"{func.__name__} takes the predict the table is supposed to BE the values of")
    return func


def _reason(name):
    got = getattr(RouteReason, name, None)
    assert got is not None, f"RouteReason.{name} is what part B adds"
    return got


# =====================================================================
# R-37: the nonlinearity, per spec and finite
# =====================================================================
def _affine_frame():
    problem = S.affine("B23_affine")
    post = local_gaussian_posterior(problem.calibrate(), problem.observations, problem.forward,
                                    multistart=MultistartPolicy())
    assert post.claim is RouteClaim.SUPPORTED and not post.reasons
    cov = np.asarray(post.covariance)
    lam, vec = np.linalg.eigh(cov)
    return post, np.asarray(post.inference_point), vec, np.sqrt(lam)


def test_r37_each_record_carries_its_own_nonlinearity():
    """One curved output in a call must not make an exactly affine one in the same call report its number."""
    post, z0, vec, s = _affine_frame()

    def predict(theta):
        dz = np.asarray(theta, dtype=float) - z0
        u1, u2 = float(vec[:, 0] @ dz) / s[0], float(vec[:, 1] @ dz) / s[1]
        return [Quantity(100.0 + u1 + u2, UNIT), Quantity(100.0 + u1 + 50.0 * u1 * u2, UNIT)]

    affine, curved = linearized_predictive_uq(
        post, predict, [PredictiveObservableSpec("flat", UNIT, NOISE), PredictiveObservableSpec("curved", UNIT, NOISE)])
    assert float(curved.predictive_nonlinearity) > 1.0
    assert float(affine.predictive_nonlinearity) < 1.0e-6, affine.predictive_nonlinearity
    assert RouteReason.PREDICTIVE_NONLINEAR in curved.reasons
    assert RouteReason.PREDICTIVE_NONLINEAR not in affine.reasons
    # both records carry PREDICTION_DOMAIN_NOT_DECLARED, because neither spec declares a condition -- part A's
    # rule and nothing to do with this one. What this test is about is that the CURVATURE reason and the
    # number behind it are the ones this prediction's own probes measured.
    assert set(affine.reasons) == {RouteReason.PREDICTION_DOMAIN_NOT_DECLARED}, [r.value for r in affine.reasons]


def test_r37_a_prediction_with_no_parameter_uncertainty_that_the_probes_move_is_refused():
    """inf is not a large nonlinearity; it is the absence of a scale to measure one against."""
    post, z0, vec, s = _affine_frame()

    def predict(theta):
        dz = np.asarray(theta, dtype=float) - z0
        u1 = float(vec[:, 0] @ dz) / s[0]
        # purely quadratic: the first derivative at the estimate is 0, so the parameter sd is 0, and the
        # probes move it by 4 sd^2 -- a prediction whose reported interval is a point and is wrong
        return [Quantity(100.0 + u1 * u1, UNIT)]

    with pytest.raises(RouteRefusedError):
        linearized_predictive_uq(post, predict, [PredictiveObservableSpec("quadratic", UNIT, NOISE)])


def test_r37_a_record_carrying_a_nonfinite_nonlinearity_is_refused_on_read():
    post, _z0, _vec, _s = _affine_frame()
    (good,) = linearized_predictive_uq(post, lambda t: [Quantity(float(t[0]) + float(t[1]), UNIT)],
                                       [PredictiveObservableSpec("y", UNIT, NOISE)])
    for bad in (math.inf, -math.inf):
        with pytest.raises(HybridUQError):
            dataclasses.replace(good, predictive_nonlinearity=bad,
                                reasons=tuple(good.reasons) + (RouteReason.PREDICTIVE_NONLINEAR,),
                                route_claim=RouteClaim.DOWNGRADED)


# Already held at the baseline and unmarked at preregistration: NaN and None keep exactly the meaning they
# have -- nothing was measured, which is NONLINEARITY_PROBE_INCOMPLETE. Kept because a finiteness rule that
# also refused "not measured" would delete the one honest thing an unmeasured record can say.
def test_r37_a_nonlinearity_that_was_not_measured_still_means_that_and_not_a_refusal():
    post, _z0, _vec, _s = _affine_frame()
    (record,) = linearized_predictive_uq(post, lambda t: [Quantity(float(t[0]) + float(t[1]), UNIT)],
                                         [PredictiveObservableSpec("y", UNIT, NOISE)], check_nonlinearity=False)
    assert record.predictive_nonlinearity is None
    assert RouteReason.NONLINEARITY_PROBE_INCOMPLETE in record.reasons
    assert record.route_claim is RouteClaim.DOWNGRADED


# =====================================================================
# R-23: the predictive table, checked against predict
# =====================================================================
def _grid_frame():
    problem = S.affine("B23_grid")
    z = np.asarray(problem.calibrate().estimate_vector)
    axes = [np.linspace(z[0] - 0.4, z[0] + 0.4, 41), np.linspace(z[1] - 0.8, z[1] + 0.8, 41)]
    grid = problem.grid(axes)
    table = problem.table_builder()(grid.points)
    spec = PredictiveObservableSpec(
        observation_key=problem.observations.keys[2], unit=UNIT, observation_sigma=NOISE)
    return problem, grid, table, spec


def _predict_one(problem, spec):
    """``predict`` for a grid prediction returns THAT prediction's value, one per spec, as the local path does."""
    index = list(problem.observations.keys).index(spec.observation_key)

    def predict(theta):
        values = problem.forward(theta)
        return None if values is None else [values[index]]

    return predict


def _doubled(table):
    return dataclasses.replace(table, values=np.asarray(table.values, dtype=float) * 2.0)


def test_r23_a_table_of_twice_the_model_is_refused_when_predict_is_passed():
    """The audited case: a table of twice the model, passed together with the correct predict()."""
    problem, grid, table, spec = _grid_frame()
    _takes_predict(grid_predictive_uncertainty)
    with pytest.raises(HybridUQError, match="is refused rather than reported"):
        grid_predictive_uncertainty(grid, _doubled(table), spec, twin=TWIN, model=S.MODEL, source_ref="audit",
                                    observations=problem.observations, forward=problem.forward,
                                    calibration=problem.calibrate(), predict=_predict_one(problem, spec))


def test_r23_the_table_that_is_the_model_is_accepted_and_says_it_was_checked():
    problem, grid, table, spec = _grid_frame()
    _takes_predict(grid_predictive_uncertainty)
    record = grid_predictive_uncertainty(grid, table, spec, twin=TWIN, model=S.MODEL, source_ref="audit",
                                         observations=problem.observations, forward=problem.forward,
                                         calibration=problem.calibrate(), predict=_predict_one(problem, spec))
    assert _reason("PREDICTIVE_TABLE_NOT_CHECKED") not in record.reasons, [r.value for r in record.reasons]


def test_r23_a_table_nobody_checked_says_so():
    """A rule a caller turns off by passing nothing is not a rule -- R-12 one layer down."""
    problem, grid, table, spec = _grid_frame()
    record = grid_predictive_uncertainty(grid, table, spec, twin=TWIN, model=S.MODEL, source_ref="audit",
                                         observations=problem.observations, forward=problem.forward,
                                         calibration=problem.calibrate())
    assert _reason("PREDICTIVE_TABLE_NOT_CHECKED") in record.reasons, [r.value for r in record.reasons]
    assert record.route_claim is RouteClaim.DOWNGRADED


def test_r23_the_checked_nodes_are_the_ones_the_reported_numbers_stand_on():
    """The maximum-weight node and the two nodes attaining the table's extreme values on the support."""
    module = _module()
    problem, grid, table, spec = _grid_frame()
    nodes = _symbol(module, "_spot_check_nodes")(grid, table, spec)
    assert 1 <= len(nodes) <= 3, nodes
    weights = np.asarray(grid.weights, dtype=float)
    column = list(table.observation_keys).index(spec.observation_key)
    values = np.asarray(table.values, dtype=float)[:, column]
    usable = np.asarray(grid.admissible_mask, dtype=bool) & np.asarray(table.admissible_mask, dtype=bool) & (weights > 0.0)
    assert int(np.argmax(np.where(usable, weights, -np.inf))) in nodes
    assert int(np.argmin(np.where(usable, values, np.inf))) in nodes
    assert int(np.argmax(np.where(usable, values, -np.inf))) in nodes


def test_r23_the_router_checks_the_table_it_is_handed_beside_a_predict():
    problem, grid, table, spec = _grid_frame()
    result = route_uncertainty(grid=grid, calibration=problem.calibrate(), observations=problem.observations,
                               forward=problem.forward, multistart=MultistartPolicy())
    assert result.decision is RouteDecision.GRID_AS_SUPPLIED, result.considered
    _takes_predict(grid_predictive_uncertainty)
    with pytest.raises(HybridUQError, match="is refused rather than reported"):
        routed_predictive_uncertainty(result, [spec], predict=_predict_one(problem, spec), predictive_table=_doubled(table),
                                      twin=TWIN, model=S.MODEL, source_ref="audit")
    (record,) = routed_predictive_uncertainty(result, [spec], predict=_predict_one(problem, spec), predictive_table=table,
                                              twin=TWIN, model=S.MODEL, source_ref="audit")
    assert _reason("PREDICTIVE_TABLE_NOT_CHECKED") not in record.reasons
    (unchecked,) = routed_predictive_uncertainty(result, [spec], predictive_table=table, twin=TWIN,
                                                 model=S.MODEL, source_ref="audit")
    assert _reason("PREDICTIVE_TABLE_NOT_CHECKED") in unchecked.reasons


def test_r23_the_tolerance_is_roundoff_and_a_disagreement_of_one_part_in_a_million_is_refused():
    """`predict` is deterministic and the table is supposed to BE its values, so only roundoff is admissible."""
    problem, grid, table, spec = _grid_frame()
    nudged = np.asarray(table.values, dtype=float).copy()
    nudged *= 1.0 + 1.0e-6
    _takes_predict(grid_predictive_uncertainty)
    with pytest.raises(HybridUQError, match="is refused rather than reported"):
        grid_predictive_uncertainty(grid, dataclasses.replace(table, values=nudged), spec, twin=TWIN,
                                    model=S.MODEL, source_ref="audit", observations=problem.observations,
                                    forward=problem.forward, calibration=problem.calibrate(),
                                    predict=_predict_one(problem, spec))
