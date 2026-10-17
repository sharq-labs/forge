import itertools
import math

import numpy as np
import pytest

from engcore.mcp.probabilistic_uq import (
    build_deterministic_samples,
    latin_hypercube_provenance,
    predictive_intervals,
)
from engcore.scientific.units.quantity import Quantity


def _answer(value, verdict="supported"):
    return {
        "status": "completed",
        "verdict": verdict,
        "results": [{
            "subject": "R1",
            "values": {"temperature": {
                "magnitude": value, "units": "kelvin"
            }},
        }],
    }


def test_uniform_samples_are_deterministic_stratified_and_unit_bearing():
    spec = [{
        "path": "ambient",
        "distribution": "uniform",
        "lower": "290 kelvin",
        "upper": "310 kelvin",
    }]
    first = build_deterministic_samples(
        spec, sample_count=8, dependence="independent", seed=7
    )
    second = build_deterministic_samples(
        spec, sample_count=8, dependence="independent", seed=7
    )
    assert first == second
    assert len({sample["ambient"] for sample in first}) == 8
    assert all("kelvin" in sample["ambient"] for sample in first)


def test_dependence_is_never_assumed_or_silently_dropped():
    with pytest.raises(ValueError, match="explicitly 'independent'"):
        build_deterministic_samples(
            [{
                "path": "x", "distribution": "normal",
                "mean": "1 volt", "standard_deviation": "0.1 volt",
            }],
            sample_count=8,
            dependence="correlated",
            seed=0,
        )


def test_predictive_interval_fails_closed_on_unsupported_sample_mass():
    result = predictive_intervals(
        [_answer(300), _answer(310, "not_supported")], credible_mass=0.9
    )
    assert result["status"] == "predictive_support_not_admitted"
    assert result["rejected_sample_indices"] == [1]
    assert result["intervals"] == []


def test_supported_samples_produce_empirical_central_interval():
    result = predictive_intervals(
        [_answer(value) for value in (300, 302, 304, 306)], credible_mass=0.5
    )
    assert result["status"] == "completed"
    assert result["schema"] == "engineering_probabilistic_uq/2"
    assert "finite-sample estimation error of the interval endpoints" in (
        result["does_not_include"]
    )
    interval = result["intervals"][0]
    assert interval["method"] == (
        "seeded_latin_hypercube_midpoint_empirical_central_interval"
    )
    assert interval["mean"]["magnitude"] == pytest.approx(303)
    assert interval["lower"]["magnitude"] == pytest.approx(301.5)
    assert interval["upper"]["magnitude"] == pytest.approx(304.5)


# ---------------------------------------------------------------------------
# Sample design (review finding B1). The previous sampler permuted every column
# with a fixed modular stride, which coupled the inputs: rho(X0, X1) ~ 0.42 at
# n = 64 and n = 256, so sd(X0 + X1) came out ~1.69 and sd(X0 - X1) ~1.07 for
# independent N(0, 1) inputs whose true value is sqrt(2) for both.
# ---------------------------------------------------------------------------

def _normals(dimension):
    return [{
        "path": f"x{column}", "distribution": "normal",
        "mean": "0 meter", "standard_deviation": "1 meter",
    } for column in range(dimension)]


def _unit_uniforms(dimension):
    return [{
        "path": f"x{column}", "distribution": "uniform",
        "lower": "0 meter", "upper": "1 meter",
    } for column in range(dimension)]


def _matrix(samples, dimension):
    return np.asarray([
        [Quantity.parse(sample[f"x{column}"]).magnitude
         for column in range(dimension)]
        for sample in samples
    ], dtype=float)


def _draw(inputs, count, seed):
    return _matrix(
        build_deterministic_samples(
            inputs, sample_count=count, dependence="independent", seed=seed
        ),
        len(inputs),
    )


def test_the_seed_is_required_and_never_silently_defaulted():
    with pytest.raises(TypeError):
        build_deterministic_samples(
            _normals(2), sample_count=8, dependence="independent"
        )
    for bad in (None, 1.5, "3", True):
        with pytest.raises(TypeError, match="seed"):
            build_deterministic_samples(
                _normals(2), sample_count=8, dependence="independent", seed=bad
            )
    with pytest.raises(ValueError, match="seed"):
        build_deterministic_samples(
            _normals(2), sample_count=8, dependence="independent", seed=-1
        )


def test_same_seed_reproduces_and_a_different_seed_changes_the_design():
    first = build_deterministic_samples(
        _normals(3), sample_count=64, dependence="independent", seed=11
    )
    again = build_deterministic_samples(
        _normals(3), sample_count=64, dependence="independent", seed=11
    )
    other = build_deterministic_samples(
        _normals(3), sample_count=64, dependence="independent", seed=12
    )
    assert first == again
    assert first != other


def test_provenance_records_the_seed_and_the_sampler():
    record = latin_hypercube_provenance(seed=11, sample_count=64, dimension=3)
    assert record["sampler"] == "scipy.stats.qmc.LatinHypercube"
    assert record["seed"] == 11
    assert record["sample_count"] == 64
    assert record["dimension"] == 3
    assert record["scipy_version"] and record["numpy_version"]


@pytest.mark.parametrize("dimension", [2, 3])
@pytest.mark.parametrize("count", [64, 256])
def test_every_marginal_has_exactly_one_point_per_stratum(dimension, count):
    unit = _draw(_unit_uniforms(dimension), count, seed=3)
    for column in range(dimension):
        strata = np.floor(unit[:, column] * count).astype(int)
        assert sorted(strata.tolist()) == list(range(count))


@pytest.mark.parametrize("dimension", [2, 3])
@pytest.mark.parametrize("count", [64, 256])
def test_pairwise_sample_correlation_is_within_a_statistical_bound(
    dimension, count
):
    # For independent columns the sample correlation has sd ~ 1/sqrt(n - 1).
    # It is not zero, and the test does not ask for zero.
    bound = 4.0 / math.sqrt(count - 1)
    per_pair = {pair: [] for pair in itertools.combinations(range(dimension), 2)}
    for seed in range(10):
        matrix = _draw(_normals(dimension), count, seed)
        correlation = np.corrcoef(matrix.T)
        for a, b in per_pair:
            assert abs(correlation[a, b]) < bound, (seed, a, b, correlation[a, b])
            per_pair[(a, b)].append(correlation[a, b])
    for (a, b), values in per_pair.items():
        # Averaged over seeds, any systematic coupling would remain.
        assert abs(np.mean(values)) < 4.0 / math.sqrt(10 * (count - 1)), (a, b)


@pytest.mark.parametrize("count", [64, 256])
def test_sum_and_difference_of_independent_normals_have_sqrt2_spread(count):
    # var(X0 +/- X1) = 2 S (1 +/- r), with S the (deterministic) variance of
    # the stratum-midpoint normal marginal and r the sample correlation, whose
    # sd is 1/sqrt(n - 1) for a correct design. Bounds are 4 sigma of that.
    # The old sampler gave var(sum) ~ 2.85 and var(diff) ~ 1.14 here.
    marginal = float(np.var(_draw(_normals(1), count, seed=0)[:, 0], ddof=1))
    assert marginal == pytest.approx(1.0, abs=0.01)
    seeds = 10
    sums, differences = [], []
    for seed in range(seeds):
        matrix = _draw(_normals(2), count, seed)
        sums.append(np.var(matrix[:, 0] + matrix[:, 1], ddof=1))
        differences.append(np.var(matrix[:, 0] - matrix[:, 1], ddof=1))
        for variance in (sums[-1], differences[-1]):
            # sd/sqrt(2S) - 1 ~ +/- r/2, so 4 sigma is 2/sqrt(n - 1).
            assert abs(math.sqrt(variance / (2.0 * marginal)) - 1.0) < (
                2.0 / math.sqrt(count - 1)
            ), (seed, variance)
    tolerance = 4.0 * 2.0 * marginal / math.sqrt(seeds * (count - 1))
    assert abs(np.mean(sums) - 2.0 * marginal) < tolerance
    assert abs(np.mean(differences) - 2.0 * marginal) < tolerance
    # and the propagated spread is the independent-input value, sqrt(2)
    assert math.sqrt(np.mean(sums)) == pytest.approx(math.sqrt(2.0), rel=0.06)
    assert math.sqrt(np.mean(differences)) == pytest.approx(math.sqrt(2.0), rel=0.06)


def test_no_input_stratum_is_a_fixed_function_of_another_inputs_stratum():
    # The old design paired x0's stratum k with x1's stratum (3k + 1) mod n
    # whatever the run. Across seeds the partner of a stratum must move.
    count = 64
    partners = set()
    for seed in range(10):
        unit = _draw(_unit_uniforms(3), count, seed)
        strata = np.floor(unit * count).astype(int)
        lowest = int(np.flatnonzero(strata[:, 0] == 0)[0])
        partners.add((int(strata[lowest, 1]), int(strata[lowest, 2])))
    assert len(partners) >= 8


def test_adding_an_input_does_not_couple_the_existing_ones():
    count = 256
    for seed in range(5):
        matrix = _draw(_normals(3), count, seed)
        correlation = np.corrcoef(matrix.T)
        bound = 4.0 / math.sqrt(count - 1)
        assert np.all(np.abs(correlation[np.triu_indices(3, 1)]) < bound)
