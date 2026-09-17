"""Batch 13 of the 2026-09-16 core re-audit: a sound adequacy comparison (I-18, R-24, R-32, R-33, R-34).

Out-of-sample model comparison rests on four things, and each one was a label.

* **R-24** -- content binding binds less than "content". The split branch never compares the spec's sigma
  with the held-out observation's declared sigma (a 0.05 K spec sigma against a declared 0.5 K creates a
  decisive preference; 5 K erases a genuine 11.5-nat one), never compares the twin with the split's twin, and
  the evidence identity carries two dataset-id STRINGS rather than the calibration content -- so two
  campaigns pair as the same evidence and the difference in their training data is reported as a model
  preference. That is the original CORE-007 failure reached through a label again.
* **R-32** -- the copy detectors run only ACROSS the halves. One held-out reading listed four times gives
  n = 4, a sample variance of exactly 0 and a "decisive" preference; and a reading re-imported with a
  re-declared sigma, or renamed, crosses into held-out.
* **R-33** -- delta / SE is a t statistic on n - 1 degrees of freedom and the gate compares it with 2, the
  NORMAL quantile. At n = 2 that is a Cauchy tail: the audit measured a preferred model in 27.5 % of runs
  between exact mirror-image models.
* **R-34** -- content_bound is a caller-settable field and the comparison treats it as proof, so a flipped
  flag on unbound assessments (or fabricated log densities) names a model.

Preregistered in `benchmarks/core_v4_false_confidence/BATCH13_THRESHOLD_PROTOCOL.json`. The sixteen
reproductions here were committed as `xfail(strict=True)` first and run with `--runxfail` to watch each fail
on its own assertion. Five tests carry no marker and never did, because they pass at the preregistration
commit and must keep passing: the same split still pairs and is still decisive; declared replicates are still
allowed; a copy rounded to eight significant digits is already caught; and two comparison cases that this
data already answers correctly.
"""

from __future__ import annotations

import dataclasses
import json
import math

import numpy as np
import pytest
from scipy.stats import norm, t

from engcore.adequacy import assess_predictive_observation, compare_log_predictive_scores
from engcore.adequacy.predictive import (
    COMPARISON_MINIMUM_ABS_DELTA,
    COMPARISON_MINIMUM_N,
    COMPARISON_MINIMUM_SE_MULTIPLE,
    ModelAdequacyError,
    PredictiveObservationAssessment,
)
from engcore.inference import AdmittedForwardTable, GaussianObservation, ObservationSet, gaussian_grid_posterior
from engcore.inference.split import DataLeakageError, ObservationSplit, allow_exact_replicates
from engcore.scientific import ModelReference, Quantity, TwinReference
from engcore.uq import PredictiveObservableSpec

KELVIN = "kelvin"
TWIN = TwinReference("rig", "1")
OTHER_TWIN = TwinReference("other-rig", "1")
SIGMA = 0.5
GRID = np.linspace(1.0, 3.0, 2001)
A = ModelReference("A", "1")
B = ModelReference("B", "1")


def _reading(condition, value, *, sigma=SIGMA, observable="y", source=None):
    return GaussianObservation(condition, observable, Quantity(value, KELVIN), Quantity(sigma, KELVIN),
                               source if source is not None else f"lab:{condition}")


def _xs(count):
    """``count`` conditions, the first two thirds calibration and the rest held out."""
    return {f"c{i}": 1.0 + 0.25 * i for i in range(count)}


def _table(keys, model, xs):
    points = GRID.reshape(-1, 1)
    values = np.asarray([[model(p[0], xs[k.split(":")[0]]) for k in keys] for p in points])
    return AdmittedForwardTable(parameter_names=("theta",), observation_keys=tuple(keys), points=points,
                               values=values, admissible_mask=np.ones(len(points), bool),
                               admission_refs=tuple(("analytic",) * len(keys) for _ in points),
                               rejection_reasons=("",) * len(points))


def _split(count=12, *, offset=0.0, calibration="calibration", heldout="heldout", twin=TWIN, extra=()):
    xs = _xs(count)
    held = tuple(k for i, k in enumerate(xs) if i >= count - max(3, count // 3))
    rng = np.random.default_rng(20260917)
    readings = []
    for key, x in xs.items():
        noise = float(rng.normal(0.0, 0.2))
        readings.append(_reading(key, 2.0 * x + noise + (offset if key not in held else 0.0)))
    source = ObservationSet(tuple(readings) + tuple(extra), dataset_id=f"source-{calibration}")
    return ObservationSplit.partition(source, held_out_condition_ids=held, twin=twin,
                                      calibration_dataset_id=calibration, heldout_dataset_id=heldout), xs


GOOD = lambda th, x: th * x  # noqa: E731
BIASED = lambda th, x: th * x + 2.0  # noqa: E731
MIRROR = lambda th, x: th * x - 2.0  # noqa: E731


def _assess(model_name, model, split, xs, *, bound=True, sigma=None, twin=TWIN):
    calibration_table = _table(split.calibration.keys, model, xs)
    posterior = gaussian_grid_posterior(calibration_table, split.calibration)
    out = []
    for observation in split.held_out.observations:
        extra = {"split": split, "calibration_table": calibration_table} if bound else {}
        spec = PredictiveObservableSpec(observation.key, KELVIN,
                                        observation.sigma if sigma is None else Quantity(sigma, KELVIN))
        out.append(assess_predictive_observation(
            posterior, _table([observation.key], model, xs), spec, observation.value, twin=twin,
            model=ModelReference(model_name, "1"), source_ref=model_name,
            heldout_dataset_id=split.heldout_dataset_id, **extra))
    return out


def _verified(item):
    """Whether the batch's in-process binding holds for this record, read by name."""
    return getattr(item, "content_binding_verified", None)


# =====================================================================
# R-24: content binding binds the content
# =====================================================================
@pytest.mark.xfail(strict=True, reason="I-18 not implemented yet (batch 13 preregistration)")
def test_r24_a_spec_sigma_that_is_not_the_declared_one_is_refused():
    """The audited record: a 0.05 K spec sigma against a declared 0.5 K makes B decisively preferred."""
    split, xs = _split()
    with pytest.raises(ModelAdequacyError, match="(?i)sigma"):
        _assess("A", GOOD, split, xs, sigma=0.05)


@pytest.mark.xfail(strict=True, reason="I-18 not implemented yet (batch 13 preregistration)")
def test_r24_a_twin_that_is_not_the_splits_twin_is_refused():
    split, xs = _split()
    with pytest.raises(ModelAdequacyError, match="(?i)twin"):
        _assess("A", GOOD, split, xs, twin=OTHER_TWIN)


@pytest.mark.xfail(strict=True, reason="I-18 not implemented yet (batch 13 preregistration)")
def test_r24_the_identity_carries_the_splits_content():
    split, xs = _split()
    items = _assess("A", GOOD, split, xs)
    digests = {getattr(item.evidence, "split_content_digest", None) for item in items}
    assert len(digests) == 1 and next(iter(digests)), digests
    other, other_xs = _split(offset=0.75)
    assert {getattr(item.evidence, "split_content_digest", None)
            for item in _assess("A", GOOD, other, other_xs)} != digests


@pytest.mark.xfail(strict=True, reason="I-18 not implemented yet (batch 13 preregistration)")
def test_r24_two_campaigns_under_the_same_labels_do_not_pair_as_one_evidence():
    """The audited record: identical models on different calibration data, delta -5.8 and se 0.86, decisive.

    Both splits carry the same held-out readings and the same 'calibration'/'heldout' id strings; only the
    calibration half differs, by an offset. The same forward function is labelled A and B.
    """
    first, xs = _split()
    second, second_xs = _split(offset=0.75)
    left = _assess("A", GOOD, first, xs)
    right = _assess("B", GOOD, second, second_xs)
    try:
        comparison = compare_log_predictive_scores(A, left, B, right)
    except ModelAdequacyError:
        return
    assert comparison.preferred_model is None, (comparison.delta_a_minus_b, comparison.why)


def test_r24_the_same_split_still_pairs_and_is_still_decisive():
    """The route that must keep working, with enough paired observations for the new minimum."""
    split, xs = _split(count=40)
    comparison = compare_log_predictive_scores(A, _assess("A", GOOD, split, xs), B, _assess("B", BIASED, split, xs))
    assert comparison.n >= 10 and comparison.delta_a_minus_b > COMPARISON_MINIMUM_ABS_DELTA
    assert comparison.preferred_model == A, comparison.why


# =====================================================================
# R-34: content binding is verified, not declared
# =====================================================================
@pytest.mark.xfail(strict=True, reason="I-18 not implemented yet (batch 13 preregistration)")
def test_r34_a_flipped_flag_on_unbound_assessments_names_no_preferred_model():
    """The audited record: dataclasses.replace(x, content_bound=True) gives a decisive 15.9-nat preference."""
    split, xs = _split(count=40)
    left = [dataclasses.replace(item, content_bound=True) for item in _assess("A", GOOD, split, xs, bound=False)]
    right = [dataclasses.replace(item, content_bound=True) for item in _assess("B", BIASED, split, xs, bound=False)]
    assert all(item.content_bound for item in (*left, *right)), "the flag really is settable"
    comparison = compare_log_predictive_scores(A, left, B, right)
    assert comparison.preferred_model is None, comparison.why


@pytest.mark.xfail(strict=True, reason="I-18 not implemented yet (batch 13 preregistration)")
def test_r34_a_fabricated_log_density_names_no_preferred_model():
    split, xs = _split(count=40)
    left = _assess("A", GOOD, split, xs)
    right = _assess("B", GOOD, split, xs)
    inflated = [dataclasses.replace(item, log_predictive_density=item.log_predictive_density + 50.0)
                for item in left]
    assert all(item.content_bound for item in inflated), "the flag survives a replace"
    comparison = compare_log_predictive_scores(A, inflated, B, right)
    assert comparison.preferred_model is None, comparison.why


@pytest.mark.xfail(strict=True, reason="I-18 not implemented yet (batch 13 preregistration)")
def test_r34_a_deserialized_assessment_names_no_preferred_model():
    """Content binding is an in-process fact. A stored record's flag is integrity-only, as the audit says."""
    split, xs = _split(count=40)
    left = _assess("A", GOOD, split, xs)
    right = _assess("B", BIASED, split, xs)
    back = [PredictiveObservationAssessment.from_dict(json.loads(json.dumps(item.to_dict()))) for item in left]
    assert all(item.content_bound for item in back), "the record still CLAIMS it, which is integrity-only"
    comparison = compare_log_predictive_scores(A, back, B, right)
    assert comparison.preferred_model is None, comparison.why


@pytest.mark.xfail(strict=True, reason="I-18 not implemented yet (batch 13 preregistration)")
def test_r34_a_bound_assessment_is_verified_and_an_unbound_one_is_not():
    split, xs = _split()
    assert all(_verified(item) is True for item in _assess("A", GOOD, split, xs))
    assert all(_verified(item) is False for item in _assess("A", GOOD, split, xs, bound=False))


# =====================================================================
# R-32: a copy is a copy inside a half too
# =====================================================================
def _repeat(count=12, *, side="held", times=3):
    xs = _xs(count)
    held = tuple(k for i, k in enumerate(xs) if i >= count - max(3, count // 3))
    target = held[0] if side == "held" else next(k for k in xs if k not in held)
    value = 2.0 * xs[target]
    copies = tuple(_reading(f"{target}-copy{i}", value) for i in range(times))
    readings = tuple(_reading(k, 2.0 * x) for k, x in xs.items()) + copies
    source = ObservationSet(readings, dataset_id="source")
    extra = tuple(c.condition_id for c in copies) if side == "held" else ()
    return source, tuple(held) + extra


@pytest.mark.xfail(strict=True, reason="I-18 not implemented yet (batch 13 preregistration)")
def test_r32_a_repeated_reading_inside_the_held_out_half_is_refused():
    """The audited record: one reading listed four times gives n = 4, SE exactly 0 and a decisive preference."""
    source, held = _repeat(side="held")
    with pytest.raises(DataLeakageError, match="(?i)copy|both sides|repeat"):
        ObservationSplit.partition(source, held_out_condition_ids=held, twin=TWIN,
                                   calibration_dataset_id="calibration", heldout_dataset_id="heldout")


@pytest.mark.xfail(strict=True, reason="I-18 not implemented yet (batch 13 preregistration)")
def test_r32_a_repeated_reading_inside_the_calibration_half_is_refused():
    source, held = _repeat(side="calibration")
    with pytest.raises(DataLeakageError, match="(?i)copy|both sides|repeat"):
        ObservationSplit.partition(source, held_out_condition_ids=held, twin=TWIN,
                                   calibration_dataset_id="calibration", heldout_dataset_id="heldout")


def test_r32_declared_replicates_are_still_allowed():
    """The declaration exists for exactly this, and it now switches off the within-half test too."""
    source, held = _repeat(side="held")
    split = ObservationSplit(**allow_exact_replicates(dict(
        calibration=ObservationSet(tuple(o for o in source.observations if o.condition_id not in held),
                                   dataset_id="calibration"),
        held_out=ObservationSet(tuple(o for o in source.observations if o.condition_id in held),
                                dataset_id="heldout"),
        twin=TWIN, source_dataset_id="source")))
    assert split.exact_replicates_allowed is True


@pytest.mark.parametrize("sigma,observable,source,label", [
    (0.625, "y", None, "a re-declared sigma on the same value"),
    (SIGMA, "R", "lab:c9", "a renamed observable from the same source row"),
])
@pytest.mark.xfail(strict=True, reason="I-18 not implemented yet (batch 13 preregistration)")
def test_r32_a_copy_the_old_rule_admitted_is_a_copy(sigma, observable, source, label):
    xs = _xs(12)
    held = tuple(k for i, k in enumerate(xs) if i >= 8)
    keep = next(k for k in xs if k not in held)
    readings = tuple(_reading(k, 2.0 * x) for k, x in xs.items())
    original = next(o for o in readings if o.condition_id == keep)
    copy = _reading("re-import", original.value.magnitude, sigma=sigma, observable=observable,
                    source=original.source_ref if source is None else source)
    if source is not None:
        readings = tuple(dataclasses.replace(o, source_ref="lab:c9") if o.condition_id == keep else o
                         for o in readings)
    source_set = ObservationSet(readings + (copy,), dataset_id="source")
    with pytest.raises(DataLeakageError, match="(?i)copy|repeat"):
        ObservationSplit.partition(source_set, held_out_condition_ids=held + ("re-import",), twin=TWIN,
                                   calibration_dataset_id="calibration", heldout_dataset_id="heldout")


def test_r32_a_copy_rounded_to_eight_significant_digits_is_a_copy():
    xs = _xs(12)
    held = tuple(k for i, k in enumerate(xs) if i >= 8)
    keep = next(k for k in xs if k not in held)
    readings = tuple(_reading(k, 2.0 * x + 0.123456789012) for k, x in xs.items())
    original = next(o for o in readings if o.condition_id == keep)
    rounded = float(f"{original.value.magnitude:.8g}")
    assert rounded != original.value.magnitude
    source_set = ObservationSet(readings + (_reading("re-import", rounded),), dataset_id="source")
    with pytest.raises(DataLeakageError, match="(?i)copy|repeat"):
        ObservationSplit.partition(source_set, held_out_condition_ids=held + ("re-import",), twin=TWIN,
                                   calibration_dataset_id="calibration", heldout_dataset_id="heldout")


@pytest.mark.xfail(strict=True, reason="I-18 not implemented yet (batch 13 preregistration)")
def test_r32_two_paired_positions_of_one_reading_name_no_preferred_model():
    """The audited record: one held-out reading listed four times gives n = 4, a sample variance of exactly
    0 and a decisive preference.

    The split accepts it only because the study DECLARED replicates, which is the honest way to have them --
    and the paired standard error still treats the copies as independent measurements, so the comparison is
    where the declaration has to be honoured.
    """
    xs = _xs(40)
    held = tuple(k for i, k in enumerate(xs) if i >= 27)
    target = held[0]
    copies = tuple(_reading(f"{target}-copy{i}", 2.0 * xs[target]) for i in range(3))
    readings = tuple(_reading(k, 2.0 * x) for k, x in xs.items()) + copies
    xs = dict(xs, **{c.condition_id: xs[target] for c in copies})
    split = ObservationSplit(**allow_exact_replicates(dict(
        calibration=ObservationSet(tuple(o for o in readings if o.condition_id not in held
                                         and not o.condition_id.startswith(f"{target}-copy")),
                                   dataset_id="calibration"),
        held_out=ObservationSet(tuple(o for o in readings if o.condition_id in held
                                      or o.condition_id.startswith(f"{target}-copy")), dataset_id="heldout"),
        twin=TWIN, source_dataset_id="source")))
    left = _assess("A", GOOD, split, xs)
    right = _assess("B", BIASED, split, xs)
    comparison = compare_log_predictive_scores(A, left, B, right)
    assert comparison.preferred_model is None, (comparison.n, comparison.standard_error, comparison.why)


@pytest.mark.xfail(strict=True, reason="I-18 not implemented yet (batch 13 preregistration)")
def test_r32_the_comparison_records_the_independence_it_assumes():
    split, xs = _split(count=40)
    comparison = compare_log_predictive_scores(A, _assess("A", GOOD, split, xs), B, _assess("B", BIASED, split, xs))
    assert getattr(comparison, "measurement_errors_assumed_independent", None) is True
    assert comparison.to_dict().get("measurement_errors_assumed_independent") is True


# =====================================================================
# R-33: a t critical value, and a standard error worth dividing by
# =====================================================================
@pytest.mark.xfail(strict=True, reason="I-18 not implemented yet (batch 13 preregistration)")
def test_r33_the_se_multiple_is_a_t_quantile_on_n_minus_one_degrees_of_freedom():
    from engcore.adequacy import predictive as P

    alpha = getattr(P, "COMPARISON_ALPHA", None)
    multiple = getattr(P, "_critical_se_multiple", None)
    assert alpha is not None and multiple is not None, "the batch declares the level and the t multiple"
    assert abs(alpha - 2.0 * (1.0 - float(norm.cdf(COMPARISON_MINIMUM_SE_MULTIPLE)))) < 1e-12, alpha
    for n in (2, 3, 10, 100):
        assert abs(multiple(n) - float(t.ppf(1.0 - alpha / 2.0, n - 1))) < 1e-12, n
    assert multiple(10) > COMPARISON_MINIMUM_SE_MULTIPLE


@pytest.mark.xfail(strict=True, reason="I-18 not implemented yet (batch 13 preregistration)")
def test_r33_the_minimum_paired_count_is_where_the_standard_error_is_worth_a_quarter():
    assert COMPARISON_MINIMUM_N == 10, COMPARISON_MINIMUM_N
    assert 1.0 / math.sqrt(2.0 * (COMPARISON_MINIMUM_N - 1)) < 0.25
    assert 1.0 / math.sqrt(2.0 * (COMPARISON_MINIMUM_N - 2)) >= 0.25, "and 10 is the SMALLEST such n"


def test_r33_three_paired_observations_name_no_preferred_model():
    """Not a reproduction: this data is already within 2 standard errors at n = 3, so it passes today.

    It is here as the guard that the minimum-n rule and the SE rule agree on the same answer for it after
    the change, for the new reason rather than the old one. R-33's reproduction is the RULE itself -- the
    critical value and the minimum -- which the two tests above assert directly.
    """
    split, xs = _split(count=9)
    comparison = compare_log_predictive_scores(A, _assess("A", GOOD, split, xs), B, _assess("B", BIASED, split, xs))
    assert comparison.n == 3
    assert comparison.preferred_model is None, comparison.why


def test_r33_mirror_image_models_are_not_decisive_on_ten_observations():
    """Two models that are exact mirror images have equal expected scores, so neither is preferred."""
    split, xs = _split(count=30)
    comparison = compare_log_predictive_scores(A, _assess("A", BIASED, split, xs), B, _assess("B", MIRROR, split, xs))
    assert comparison.n >= 10
    assert comparison.preferred_model is None, (comparison.delta_a_minus_b, comparison.standard_error, comparison.why)
