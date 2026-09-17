"""Batch 22 of the 2026-09-16 core re-audit: a prediction's domain statement, bound to its calibration (I-13 part A).

I-13 is four problems about a routed prediction. This part takes the two that are one claim: **a prediction's
domain statement must be bound to the calibration it came from.**

* **R-12.** `calibration_observations` are bound to nothing. Another dataset's observations, the same
  observations with their conditions rescaled, or a predictor evaluated elsewhere all silence
  PREDICTION_OUTSIDE_CALIBRATED_CONDITIONS: a far extrapolation to x = 1e4 reads SUPPORTED although the
  posterior carries its own dataset_id.
* **R-31.** The gate compares only the conditions the PREDICTION chooses to declare. A prediction at
  T = 900 K against a calibration at T = 300 K is DOWNGRADED, and the same prediction with T omitted is
  SUPPORTED. And the comparison is per condition, so with three observations covering a LINE in (T, x) a
  prediction inside both marginal ranges but 0.707 of the scaled spread off that line passes.

Preregistered in `benchmarks/core_v4_false_confidence/BATCH22_THRESHOLD_PROTOCOL.json`. No new threshold: the
joint-support rule is convex-hull membership, which at ONE condition IS the [min, max] interval it replaces,
on the same `PREDICTION_RANGE_RELATIVE_TOLERANCE`.
"""

from __future__ import annotations

import dataclasses

import hybrid_synthetic as S
import numpy as np
import pytest

from engcore.hybrid_uq import (
    MultistartPolicy,
    RouteClaim,
    RouteReason,
    linearized_predictive_uq,
    local_gaussian_posterior,
)
from engcore.hybrid_uq.vocabulary import HybridUQError
from engcore.inference import ObservationSet, calibrate
from engcore.scientific.units.quantity import Quantity
from engcore.uq import PredictiveObservableSpec

UNIT = "dimensionless"
KELVIN = "kelvin"


def _module():
    import engcore.hybrid_uq.predictive as module

    return module


def _symbol(module, name):
    """A named helper, asserted rather than assumed, so a reproduction fails on its assertion."""
    value = getattr(module, name, None)
    assert value is not None, f"engcore.hybrid_uq.predictive.{name} is what part A adds"
    return value


def _field(record, name):
    assert hasattr(record, name), f"the local Gaussian posterior records {name}"
    return getattr(record, name)


def _line(conditions):
    """A p = 2 affine problem whose n observations carry the declared ``conditions`` rows."""
    n = len(conditions)
    x = np.linspace(0.0, 1.0, n)
    problem = S.Problem("B22_line", lambda t, x: t[0] + t[1] * np.asarray(x, dtype=float), x, (1.0, 2.0), 0.05,
                        (-10.0, -10.0), (10.0, 10.0), (0.0, 0.0))
    observations = ObservationSet(tuple(
        dataclasses.replace(o, conditions=row)
        for o, row in zip(problem.observations.observations, conditions)
    ), dataset_id=problem.observations.dataset_id)
    fit = calibrate(problem.spec, observations, problem.forward,
                    heldout_dataset_id="synthetic.B22_line.heldout")
    post = local_gaussian_posterior(fit, observations, problem.forward, multistart=MultistartPolicy())
    return problem, observations, post


def _temperature_only(n=6, kelvin=300.0):
    return _line([{"temperature": Quantity(kelvin, KELVIN)} for _ in range(n)])


#: The audited two-condition case: observations on a LINE in (temperature, load). Its bounding box is
#: [300, 320] x [1, 3] and the calibration covered the diagonal of that box. SIX points rather than three, so
#: that four residual degrees of freedom keep I-04's GOODNESS_OF_FIT_UNDERPOWERED off the record -- otherwise
#: every claim here reads DOWNGRADED whatever the domain gate says, and the reproduction would pass for a
#: reason that has nothing to do with R-31.
AUDITED_LINE = [
    {"temperature": Quantity(300.0 + 4.0 * i, KELVIN), "load": Quantity(1.0 + 0.4 * i, UNIT)}
    for i in range(6)
]


def _spec(conditions):
    return PredictiveObservableSpec("g", UNIT, None, conditions=conditions)


def _predict(theta):
    return [Quantity(float(theta[0]) + float(theta[1]), UNIT)]


def _reasons(post, observations, spec):
    (record,) = linearized_predictive_uq(post, _predict, [spec], calibration_observations=observations)
    return set(record.reasons), record


# =====================================================================
# R-12: the calibration content, digested once and bound
# =====================================================================
@pytest.mark.xfail(strict=True, reason="I-13 part A not implemented yet (batch 22 preregistration)")
def test_r12_the_posterior_carries_one_digest_of_the_content_it_was_calibrated_on():
    module = _module()
    _problem, observations, post = _temperature_only()
    digest = _field(post, "calibration_content_digest")
    assert digest, "a posterior that was calibrated on observations carries their digest"
    assert digest == _symbol(module, "_observation_content_digest")(observations)


@pytest.mark.xfail(strict=True, reason="I-13 part A not implemented yet (batch 22 preregistration)")
def test_r12_the_posterior_carries_the_conditions_it_was_calibrated_at():
    _problem, _observations, post = _line(AUDITED_LINE)
    assert tuple(_field(post, "calibrated_conditions")) == (("load", UNIT), ("temperature", KELVIN))
    points = tuple(tuple(row) for row in _field(post, "calibrated_condition_points"))
    assert points == tuple((1.0 + 0.4 * i, 300.0 + 4.0 * i) for i in range(6)), points


@pytest.mark.xfail(strict=True, reason="I-13 part A not implemented yet (batch 22 preregistration)")
def test_r12_another_datasets_observations_are_refused_rather_than_weighed():
    """A caller who supplies them is ASSERTING they are the calibration's. That is true or false, not evidence."""
    _problem, _observations, post = _temperature_only()
    _other_problem, other, _other_post = _temperature_only(kelvin=900.0)
    with pytest.raises(HybridUQError):
        linearized_predictive_uq(post, _predict, [_spec({"temperature": Quantity(300.0, KELVIN)})],
                                 calibration_observations=other)


@pytest.mark.xfail(strict=True, reason="I-13 part A not implemented yet (batch 22 preregistration)")
def test_r12_the_same_observations_with_rescaled_conditions_are_refused():
    """Two of the three audited reproductions keep the dataset_id and change the content."""
    _problem, observations, post = _temperature_only()
    rescaled = ObservationSet(tuple(
        dataclasses.replace(o, conditions={"temperature": Quantity(1.0e4, KELVIN)})
        for o in observations.observations), dataset_id=observations.dataset_id)
    assert rescaled.dataset_id == observations.dataset_id
    with pytest.raises(HybridUQError):
        linearized_predictive_uq(post, _predict, [_spec({"temperature": Quantity(1.0e4, KELVIN)})],
                                 calibration_observations=rescaled)


# Already held at the baseline and unmarked at preregistration: it is the no-regression half of R-12's fix.
# The binding must let the RIGHT observations through, and a check that only ever refuses is a check that
# gets switched off.
def test_r12_the_observations_the_posterior_was_calibrated_on_are_accepted():
    _problem, observations, post = _temperature_only()
    reasons, record = _reasons(post, observations, _spec({"temperature": Quantity(300.0, KELVIN)}))
    assert RouteReason.PREDICTION_DOMAIN_NOT_DECLARED not in reasons
    assert RouteReason.PREDICTION_OUTSIDE_CALIBRATED_CONDITIONS not in reasons


@pytest.mark.xfail(strict=True, reason="I-13 part A not implemented yet (batch 22 preregistration)")
def test_r12_an_extrapolation_cannot_be_hidden_by_supplying_no_observations_at_all():
    """The posterior's own stored design is what it was fitted to, so omitting the observations applies the check."""
    _problem, _observations, post = _temperature_only()
    (record,) = linearized_predictive_uq(post, _predict, [_spec({"temperature": Quantity(1.0e4, KELVIN)})])
    assert RouteReason.PREDICTION_OUTSIDE_CALIBRATED_CONDITIONS in record.reasons, (
        [r.value for r in record.reasons])


# =====================================================================
# R-31: every declared condition, and the joint support
# =====================================================================
@pytest.mark.xfail(strict=True, reason="I-13 part A not implemented yet (batch 22 preregistration)")
def test_r31_a_prediction_that_omits_a_condition_the_calibration_declares_is_not_declared():
    _problem, observations, post = _line(AUDITED_LINE)
    partial, _record = _reasons(post, observations, _spec({"temperature": Quantity(310.0, KELVIN)}))
    assert RouteReason.PREDICTION_DOMAIN_NOT_DECLARED in partial, partial
    # and declaring nothing at all still answers the same way, as it always did
    empty, _record = _reasons(post, observations, _spec({}))
    assert RouteReason.PREDICTION_DOMAIN_NOT_DECLARED in empty, empty


# Already held at the baseline and unmarked at preregistration: the per-condition range check DID work for
# a condition the prediction declares, and R-31 is about the two cases where it did not. Kept so the
# rewrite cannot lose the case that already worked.
def test_r31_a_prediction_outside_a_declared_condition_is_still_outside():
    _problem, observations, post = _temperature_only()
    outside, _record = _reasons(post, observations, _spec({"temperature": Quantity(900.0, KELVIN)}))
    assert RouteReason.PREDICTION_OUTSIDE_CALIBRATED_CONDITIONS in outside, outside


@pytest.mark.xfail(strict=True, reason="I-13 part A not implemented yet (batch 22 preregistration)")
def test_r31_the_joint_support_is_the_region_covered_and_not_the_box_around_it():
    """The audited geometry: three observations on a line, and a point in the box that is off the line."""
    _problem, observations, post = _line(AUDITED_LINE)
    off_line, _record = _reasons(post, observations, _spec(
        {"temperature": Quantity(300.0, KELVIN), "load": Quantity(3.0, UNIT)}))
    assert RouteReason.PREDICTION_OUTSIDE_CALIBRATED_CONDITIONS in off_line, off_line
    for temperature, load in ((310.0, 2.0), (306.0, 1.6), (300.0, 1.0), (320.0, 3.0)):
        on_line, _record = _reasons(post, observations, _spec(
            {"temperature": Quantity(temperature, KELVIN), "load": Quantity(load, UNIT)}))
        assert RouteReason.PREDICTION_OUTSIDE_CALIBRATED_CONDITIONS not in on_line, (temperature, load, on_line)
        assert RouteReason.PREDICTION_DOMAIN_NOT_DECLARED not in on_line, (temperature, load, on_line)


@pytest.mark.xfail(strict=True, reason="I-13 part A not implemented yet (batch 22 preregistration)")
def test_r31_the_audited_off_line_point_is_0_707_of_the_scaled_spread_away():
    """The number the audit measured, from the rule that now decides: 1/sqrt(2) off a unit diagonal."""
    module = _module()
    residual = _symbol(module, "_condition_support_residual")
    rows = np.array([[1.0, 300.0], [2.0, 310.0], [3.0, 320.0]])
    scales = np.array([2.0, 20.0])
    assert residual(rows, scales, np.array([3.0, 300.0])) == pytest.approx(0.5, abs=0.01)
    assert residual(rows, scales, np.array([2.0, 310.0])) == pytest.approx(0.0, abs=1e-12)
    # the Euclidean distance to the segment is 1/sqrt(2) of the scaled spread; the LP minimizes the largest
    # coordinate residual, which for this geometry is half the scaled offset
    scaled = np.array([3.0, 300.0]) / scales - np.array([1.0, 300.0]) / scales
    assert float(np.linalg.norm(scaled - 0.5 * np.array([1.0, 1.0]))) == pytest.approx(0.7071, abs=0.001)


@pytest.mark.xfail(strict=True, reason="I-13 part A not implemented yet (batch 22 preregistration)")
def test_r31_at_one_condition_the_rule_is_the_interval_it_always_was():
    module = _module()
    residual = _symbol(module, "_condition_support_residual")
    rows = np.array([[300.0], [310.0], [320.0]])
    scales = np.array([20.0])
    for value, inside in ((300.0, True), (310.0, True), (320.0, True), (299.0, False), (321.0, False)):
        got = residual(rows, scales, np.array([value]))
        assert (got <= module.PREDICTION_RANGE_RELATIVE_TOLERANCE) is inside, (value, got)


# Already held at the baseline and unmarked at preregistration: with min = max the interval is one point,
# and the convex hull of one repeated point is the same point. Kept because that degeneracy is the first
# thing a hull-membership rule can get wrong.
def test_r31_a_calibration_that_held_a_condition_fixed_admits_only_that_value():
    _problem, observations, post = _temperature_only(kelvin=300.0)
    at, _record = _reasons(post, observations, _spec({"temperature": Quantity(300.0, KELVIN)}))
    assert RouteReason.PREDICTION_OUTSIDE_CALIBRATED_CONDITIONS not in at
    beside, _record = _reasons(post, observations, _spec({"temperature": Quantity(300.1, KELVIN)}))
    assert RouteReason.PREDICTION_OUTSIDE_CALIBRATED_CONDITIONS in beside, beside


@pytest.mark.xfail(strict=True, reason="I-13 part A not implemented yet (batch 22 preregistration)")
def test_r31_the_claim_follows_the_reason_on_the_record_itself():
    """The record is what a reader sees, so the word has to be on it and not only in the helper."""
    _problem, observations, post = _line(AUDITED_LINE)
    _reasons_set, record = _reasons(post, observations, _spec(
        {"temperature": Quantity(300.0, KELVIN), "load": Quantity(3.0, UNIT)}))
    assert record.route_claim is RouteClaim.DOWNGRADED, [r.value for r in record.reasons]
