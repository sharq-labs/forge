from dataclasses import replace
from itertools import product

import pytest

from benchmarks.genesis_lite.analysis_v3 import PairedComparisonPlan, bounded_paired_test, compare_paired_scores


def plan(n=30, repeats=("a",)):
    return PairedComparisonPlan("candidate", ("baseline",), tuple(f"u{i}" for i in range(n)), repeats)


def scores(p, candidate=1., baseline=0.):
    return {arm: {u: {r: value for r in p.replicate_ids} for u in p.unit_ids}
            for arm, value in ((p.candidate, candidate), ("baseline", baseline))}


def test_one_positive_sample_does_not_establish_significance():
    result = bounded_paired_test([.01])
    assert result["p_value_upper_bound"] > .99
    assert result["lower_confidence_bound"] < 0


def test_new_boundary_never_promotes_historical_positive_control(monkeypatch):
    from benchmarks.genesis_lite import analysis, analysis_v3
    from tests.genesis_lite.lift_records import GRID, BETTER, field, records
    monkeypatch.setattr(analysis, "FORMAL_GRID", GRID)
    monkeypatch.setattr(analysis, "BOOTSTRAP", 100)
    result = analysis_v3.lift_decision(field() + records("mind", BETTER), "mind", grid=GRID)
    assert result["historical_rule_would_claim"] is True
    assert result["lift_claimed"] is False
    assert not any(result["holm_significant"].values())


def test_large_effect_positive_control_and_zero_effect_control():
    p = plan(100)
    positive = compare_paired_scores(p, scores(p, 6., -6.))
    null = compare_paired_scores(p, scores(p, 0., 0.))
    assert positive["statistical_superiority_to_all_baselines"]
    assert not positive["lift_claimed"]
    assert not null["statistical_superiority_to_all_baselines"]


def test_repeating_same_units_does_not_inflate_sample_size_or_significance():
    p1, p2 = plan(), plan(repeats=tuple(f"r{i}" for i in range(20)))
    t1 = compare_paired_scores(p1, scores(p1))["tests"]["baseline"]
    t2 = compare_paired_scores(p2, scores(p2))["tests"]["baseline"]
    assert t1 == t2
    assert t2["independent_units"] == 30


def test_all_registered_baselines_must_be_beaten():
    p = replace(plan(100), baselines=("baseline", "strong"))
    records = scores(p, 6., -6.)
    records["strong"] = records["candidate"]
    result = compare_paired_scores(p, records)
    assert result["tests"]["baseline"]["holm_reject_null"]
    assert not result["tests"]["strong"]["holm_reject_null"]
    assert not result["statistical_superiority_to_all_baselines"]


@pytest.mark.parametrize("defect", ["arm", "unit", "repeat", "nan", "out_of_range"])
def test_incomplete_or_invalid_grid_cannot_silently_drop_rows(defect):
    p = plan()
    records = scores(p)
    if defect == "arm":
        records.pop("baseline")
    elif defect == "unit":
        records["candidate"].pop("u0")
    elif defect == "repeat":
        records["candidate"]["u0"].clear()
    else:
        records["candidate"]["u0"]["a"] = float("nan") if defect == "nan" else 7
    with pytest.raises(ValueError):
        compare_paired_scores(p, records)


def test_exact_symmetric_null_calibration_is_conservative():
    # Enumerate all 2**10 independent two-point null samples, no Monte Carlo
    # noise. Also checks ties, negative means and bounded extreme differences.
    pvalues = [bounded_paired_test(sample)["p_value_upper_bound"]
               for sample in product((-12., 12.), repeat=10)]
    for alpha in (.01, .05, .10):
        assert sum(p <= alpha for p in pvalues) / len(pvalues) <= alpha


@pytest.mark.parametrize("values", [[], [float("nan")], [float("inf")], [12.1]])
def test_invalid_differences_refuse(values):
    with pytest.raises(ValueError):
        bounded_paired_test(values)
