"""Scientific core audit 2026-09-16, batch 4: prediction domain, content-bound adequacy and decisive comparison.

Findings CORE-006, CORE-007, CORE-011 and CORE-012 (docs/audits/CORE_SCIENTIFIC_AUDIT_2026-09-16.md), under
benchmarks/core_v4_false_confidence/BATCH4_THRESHOLD_PROTOCOL.json. Recorded as strict xfails before the fix.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "hybrid_uq"))
import hybrid_synthetic as S  # noqa: E402

from engcore.adequacy import assess_predictive_observation, compare_log_predictive_scores  # noqa: E402
from engcore.hybrid_uq import MultistartPolicy, RouteClaim, linearized_predictive_uq, local_gaussian_posterior  # noqa: E402
from engcore.inference import AdmittedForwardTable, GaussianObservation, ObservationSet, gaussian_grid_posterior  # noqa: E402
from engcore.inference.split import ObservationSplit  # noqa: E402
from engcore.scientific import ModelReference, Quantity, TwinReference  # noqa: E402
from engcore.uq import PredictiveObservableSpec  # noqa: E402

AUDITED = pytest.mark.xfail(strict=True, reason="reproduced before batch 4; fixed in batch 4")
UNIT = "dimensionless"
TWIN = TwinReference("rig", "1")


# ---------------------------------------------------------------------------
# CORE-006: no prediction domain
# ---------------------------------------------------------------------------
def _affine_with_conditions():
    P = S.affine("CORE006")
    observations = ObservationSet(tuple(
        GaussianObservation(o.condition_id, o.observable_name, o.value, o.sigma, o.source_ref,
                            conditions={"x": Quantity(float(x), UNIT)})
        for o, x in zip(P.observations.observations, P.x)), dataset_id=P.observations.dataset_id)
    P.observations = observations
    return P


def _predict_at(x):
    return lambda t: [Quantity(float(t[0] + t[1] * x), UNIT)]


def _spec(x=None):
    conditions = {} if x is None else {"x": Quantity(float(x), UNIT)}
    return PredictiveObservableSpec(f"y@{x}", UNIT, Quantity(0.05, UNIT), conditions=conditions)


@AUDITED
def test_core006_a_prediction_with_no_declared_domain_is_downgraded():
    P = _affine_with_conditions()
    post = local_gaussian_posterior(P.calibrate(), P.observations, P.forward, multistart=MultistartPolicy())
    record = linearized_predictive_uq(post, _predict_at(0.5), [_spec()], calibration_observations=P.observations)[0]
    assert record.route_claim is RouteClaim.DOWNGRADED
    assert "PREDICTION_DOMAIN_NOT_DECLARED" in {r.value for r in record.reasons}
    unbound = linearized_predictive_uq(post, _predict_at(0.5), [_spec(0.5)])[0]
    assert "PREDICTION_DOMAIN_NOT_DECLARED" in {r.value for r in unbound.reasons}


@AUDITED
def test_core006_an_extrapolated_prediction_is_downgraded_and_an_interpolated_one_is_not():
    P = _affine_with_conditions()
    post = local_gaussian_posterior(P.calibrate(), P.observations, P.forward, multistart=MultistartPolicy())
    far = linearized_predictive_uq(post, _predict_at(1.0e4), [_spec(1.0e4)], calibration_observations=P.observations)[0]
    assert far.route_claim is RouteClaim.DOWNGRADED
    assert "PREDICTION_OUTSIDE_CALIBRATED_CONDITIONS" in {r.value for r in far.reasons}
    near = linearized_predictive_uq(post, _predict_at(0.5), [_spec(0.5)], calibration_observations=P.observations)[0]
    assert near.route_claim is RouteClaim.SUPPORTED and near.reasons == ()


# ---------------------------------------------------------------------------
# CORE-012: the independence assumption is stated on the record
# ---------------------------------------------------------------------------
@AUDITED
def test_core012_every_routed_prediction_states_that_errors_are_assumed_independent():
    P = _affine_with_conditions()
    post = local_gaussian_posterior(P.calibrate(), P.observations, P.forward, multistart=MultistartPolicy())
    record = linearized_predictive_uq(post, _predict_at(0.5), [_spec(0.5)], calibration_observations=P.observations)[0]
    assert record.measurement_errors_assumed_independent is True
    assert record.to_dict()["measurement_errors_assumed_independent"] is True


# ---------------------------------------------------------------------------
# CORE-007 and CORE-011: adequacy bound by content; a preference only when decisive
# ---------------------------------------------------------------------------
XS = {"c1": 1.0, "c2": 2.0, "c3": 3.0, "c4": 1.5, "h1": 4.0, "h2": 5.0, "h3": 6.0}
GRID = np.linspace(1.0, 3.0, 2001)


def _obs(cid, value):
    return GaussianObservation(cid, "y", Quantity(value, "kelvin"), Quantity(0.5, "kelvin"), f"lab:{cid}")


def _table(keys, fn):
    points = GRID.reshape(-1, 1)
    values = np.asarray([[fn(p[0], k) for k in keys] for p in points])
    return AdmittedForwardTable(parameter_names=("theta",), observation_keys=tuple(keys), points=points, values=values,
                                admissible_mask=np.ones(len(points), bool),
                                admission_refs=tuple(("analytic",) * len(keys) for _ in points),
                                rejection_reasons=("",) * len(points))


def _split():
    noise = {"c1": 0.3, "c2": -0.4, "c3": 0.2, "c4": -0.1, "h1": 0.35, "h2": -0.25, "h3": 0.1}
    source = ObservationSet(tuple(_obs(k, 2.0 * x + noise[k]) for k, x in XS.items()), dataset_id="source")
    return ObservationSplit.partition(source, held_out_condition_ids=("h1", "h2", "h3"), twin=TWIN,
                                      calibration_dataset_id="calibration", heldout_dataset_id="heldout")


def _assessments(model, fn, split, *, bound=True):
    cal_table = _table(split.calibration.keys, fn)
    posterior = gaussian_grid_posterior(cal_table, split.calibration)
    out = []
    for o in split.held_out.observations:
        extra = {"split": split, "calibration_table": cal_table} if bound else {}
        out.append(assess_predictive_observation(
            posterior, _table([o.key], fn), PredictiveObservableSpec(o.key, "kelvin", o.sigma), o.value, twin=TWIN,
            model=ModelReference(model, "1"), source_ref=model, heldout_dataset_id=split.heldout_dataset_id, **extra))
    return out


GOOD = lambda th, key: th * XS[key.split(":")[0]]  # noqa: E731
BIASED = lambda th, key: th * XS[key.split(":")[0]] + 2.0  # noqa: E731
TWIN_OF_GOOD = lambda th, key: th * XS[key.split(":")[0]] + 1e-9  # noqa: E731


@AUDITED
def test_core007_a_held_out_point_inside_the_conditioning_set_is_refused_when_the_split_is_given():
    split = _split()
    leaky = ObservationSet(split.calibration.observations + (split.held_out.observations[0],), dataset_id="calibration")
    posterior = gaussian_grid_posterior(_table(leaky.keys, GOOD), leaky)
    o = split.held_out.observations[0]
    with pytest.raises(Exception, match="calibration"):
        assess_predictive_observation(posterior, _table([o.key], GOOD), PredictiveObservableSpec(o.key, "kelvin", o.sigma),
                                      o.value, twin=TWIN, model=ModelReference("A", "1"), source_ref="A",
                                      heldout_dataset_id="heldout", split=split,
                                      calibration_table=_table(split.calibration.keys, GOOD))


@AUDITED
def test_core011_a_negligible_difference_names_no_preferred_model():
    split = _split()
    comparison = compare_log_predictive_scores(ModelReference("A", "1"), _assessments("A", GOOD, split),
                                               ModelReference("B", "1"), _assessments("B", TWIN_OF_GOOD, split))
    assert comparison.preferred_model is None and comparison.n == 3 and "4 nats" in comparison.why


@AUDITED
def test_core011_a_decisive_difference_on_content_bound_evidence_names_the_better_model():
    split = _split()
    comparison = compare_log_predictive_scores(ModelReference("A", "1"), _assessments("A", GOOD, split),
                                               ModelReference("B", "1"), _assessments("B", BIASED, split))
    assert comparison.delta_a_minus_b > 4.0
    assert comparison.preferred_model == ModelReference("A", "1")


@AUDITED
def test_core007_the_same_decisive_difference_on_unbound_evidence_names_no_preferred_model():
    split = _split()
    comparison = compare_log_predictive_scores(ModelReference("A", "1"), _assessments("A", GOOD, split, bound=False),
                                               ModelReference("B", "1"), _assessments("B", BIASED, split, bound=False))
    assert comparison.delta_a_minus_b > 4.0
    assert comparison.preferred_model is None and "content" in comparison.why
