import pytest

from engcore.mcp.probabilistic_uq import (
    build_deterministic_samples,
    predictive_intervals,
)


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
        spec, sample_count=8, dependence="independent"
    )
    second = build_deterministic_samples(
        spec, sample_count=8, dependence="independent"
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
    interval = result["intervals"][0]
    assert interval["mean"]["magnitude"] == pytest.approx(303)
    # Hazen positions 1/8, 3/8, 5/8, 7/8 (FDA-14). Under /1 the type-7 rule
    # gave 301.5 and 304.5, which belong to positions 0, 1/3, 2/3, 1.
    assert interval["lower"]["magnitude"] == pytest.approx(301.0)
    assert interval["upper"]["magnitude"] == pytest.approx(305.0)


# ---------------------------------------------------------------------------
# BUY-01: FDA-04 (lattice anti-correlation), FDA-14 (stated vs realised mass)
# and the spread-unit defect beside them (BVB B26). R-04 of the 2026-10-19
# deep audit reproduced FDA-04 and FDA-14 on this module.
# ---------------------------------------------------------------------------

import numpy as np

import engcore.mcp.probabilistic_uq as puq
from engcore.scientific.errors import UnitCompatibilityError
from engcore.scientific.units.quantity import Quantity, is_ratio_scale


def _uniform(columns, lower="0 m", upper="1 m"):
    return [
        {"path": f"x{i}", "distribution": "uniform", "lower": lower, "upper": upper}
        for i in range(columns)
    ]


def _column(samples, path, unit="m"):
    return np.asarray([Quantity.parse(s[path]).magnitude_in(unit) for s in samples])


def _answers(values, units="kelvin"):
    return [{
        "status": "completed", "verdict": "supported",
        "results": [{"subject": "y", "values": {"Y": {"magnitude": float(v), "units": units}}}],
    } for v in values]


def _rank_lambda_min(cols):
    """Smallest eigenvalue of the realised Spearman matrix, computed here from
    the sample values alone and not through the module under test."""
    ranks = np.argsort(np.argsort(np.column_stack(cols), axis=0), axis=0)
    return float(np.linalg.eigvalsh(np.corrcoef(ranks, rowvar=False))[0])


def test_fda04_r04_trigger_design_no_longer_gives_a_zero_width_completed_interval():
    """R-04: n=32 with 17 inputs made x15+x16 constant: sd 0, status completed.

    Under ODC-04a (owner-approved Option D) 32 samples cannot carry 17 inputs
    within the dependence bound, so that call is refused; at n=64 it completes
    with a real spread.
    """
    with pytest.raises(ValueError, match="cannot represent independence"):
        build_deterministic_samples(
            _uniform(17), sample_count=32, dependence="independent")
    samples = build_deterministic_samples(
        _uniform(17), sample_count=64, dependence="independent")
    total = _column(samples, "x15") + _column(samples, "x16")
    result = predictive_intervals(_answers(total, "m"), credible_mass=0.95)
    assert result["status"] == "completed"
    (interval,) = result["intervals"]
    assert interval["standard_uncertainty"]["magnitude"] > 0.1
    assert interval["upper"]["magnitude"] - interval["lower"]["magnitude"] > 0.5


@pytest.mark.parametrize("columns", [2, 3, 5, 10, 17])
def test_fda04_every_admitted_design_meets_the_dependence_bound(columns):
    """Over every allowed sample_count a design either refuses, or

    * no pair of declared-independent inputs has a constant sum or difference
      (the FDA-04 failure and its co-monotone twin), and
    * the realised rank-correlation matrix has lambda_min >= 0.64 (ODC-04a), so
      no linear combination of standardised inputs has its design sd below 0.8
      of the truth.

    A property of the fixed-seed design family, not a proof that a finite
    design is independent, and no statement about nonlinear outputs.
    """
    admitted = 0
    for count in range(4, 257):
        try:
            samples = build_deterministic_samples(
                _uniform(columns), sample_count=count, dependence="independent")
        except ValueError as exc:
            assert "cannot represent independence" in str(exc)
            continue
        admitted += 1
        cols = [_column(samples, f"x{i}") for i in range(columns)]
        assert count > columns
        assert _rank_lambda_min(cols) >= 0.64 - 1e-12, count
        for a in range(columns):
            for b in range(a + 1, columns):
                assert np.ptp(cols[a] + cols[b]) > 0, (count, a, b)
                assert np.ptp(cols[a] - cols[b]) > 0, (count, a, b)
    assert admitted > 150, admitted


def test_a_sample_count_not_above_the_input_count_is_refused():
    """With n <= k some linear combination of the inputs has zero sample
    variance, whatever the pairing: FDA-04 in its general form."""
    for count, columns in ((8, 8), (5, 5), (8, 9)):
        with pytest.raises(ValueError, match="cannot represent independence"):
            build_deterministic_samples(
                _uniform(columns), sample_count=count, dependence="independent")


@pytest.mark.parametrize("count, columns", [(32, 5), (64, 10), (128, 17)])
def test_fda04_every_marginal_keeps_one_midpoint_in_every_stratum(count, columns):
    """The re-pairing changes which values share a row, never the values."""
    samples = build_deterministic_samples(
        _uniform(columns), sample_count=count, dependence="independent")
    for i in range(columns):
        scaled = _column(samples, f"x{i}") * count
        assert sorted(np.floor(scaled).astype(int)) == list(range(count))
        assert np.allclose(scaled - np.floor(scaled), 0.5)


def test_the_dependence_band_is_reported_and_matches_the_samples():
    record = puq.sample_design(32, 10)
    assert record["sampler"]["pairing"] == "iman_conover_identity_vdw/1"
    assert record["minimum_lambda"] == 0.64
    assert record["admitted"] is True
    assert record["role"] == "sampling_design_dependence_diagnostic"
    assert record["bound_scope"] == "linear_outputs_only"
    low, high = record["linear_output_sd_ratio_band"]
    assert low == pytest.approx(np.sqrt(record["lambda_min"]))
    assert high == pytest.approx(np.sqrt(record["lambda_max"]))
    assert 0.8 <= low <= 1.0 <= high
    samples = build_deterministic_samples(
        _uniform(10), sample_count=32, dependence="independent")
    cols = [_column(samples, f"x{i}") for i in range(10)]
    assert _rank_lambda_min(cols) == pytest.approx(record["lambda_min"])

    refused = puq.sample_design(32, 17)
    assert refused["admitted"] is False
    assert refused["lambda_min"] < 0.64
    assert puq.sample_design(5, 5)["lambda_min"] == 0.0
    assert puq.sample_design(5, 5)["admitted"] is False
    single = puq.sample_design(8, 1)
    assert single["admitted"] is True and single["lambda_min"] is None


def test_a_pairing_that_cannot_be_decorrelated_fails_closed():
    """An exactly reversed pair has a singular score correlation; the pairing
    step must leave it detectable (lambda_min 0) rather than raise or hide it."""
    base = (np.arange(8) + 0.5) / 8
    design = np.column_stack([base, base[::-1]])
    repaired = puq._pair_for_independence(design)
    assert puq._rank_eigenvalues(repaired)[0] == pytest.approx(0.0, abs=1e-12)


def test_sampler_identity_and_design_correlation_are_recorded():
    record = puq.sample_design(32, 17)
    sampler = record["sampler"]
    assert sampler["algorithm"] == "scipy.stats.qmc.LatinHypercube"
    assert sampler["scramble"] is False
    assert sampler["seed"] == puq.SAMPLER_SEED
    assert sampler["scipy_version"] and sampler["numpy_version"]
    assert 0.0 <= record["max_abs_pairwise_rank_correlation"] < 1.0
    first, second = record["max_correlation_pair"]
    assert 0 <= first < second < 17
    assert record == puq.sample_design(32, 17)
    single = puq.sample_design(8, 1)
    assert single["max_abs_pairwise_rank_correlation"] is None
    assert single["max_correlation_pair"] is None


def test_fda14_monotone_output_realises_the_stated_mass_end_to_end():
    """Y = X0 with X0 ~ U(0, 1): the interval width IS the covered input mass.

    R-04 measured 0.920 at n=32 for a stated 0.95 (type-7 quantiles on midpoint
    strata). Midpoint strata read with Hazen plotting positions make it exact.
    """
    for count, mass in ((32, 0.95), (40, 0.95), (64, 0.9), (4, 0.5), (20, 0.95)):
        samples = build_deterministic_samples(
            _uniform(1), sample_count=count, dependence="independent")
        result = predictive_intervals(
            _answers(_column(samples, "x0"), "m"), credible_mass=mass)
        assert result["status"] == "completed", count
        (interval,) = result["intervals"]
        width = interval["upper"]["magnitude"] - interval["lower"]["magnitude"]
        assert width == pytest.approx(mass, abs=1e-12), count
        assert interval["requested_central_mass"] == mass
        assert interval["interpretation"]["coverage_guaranteed"] is False


def test_fda14_a_tail_beyond_the_outermost_midpoint_is_refused_not_clipped():
    """n=4 cannot place a 2.5 % tail: its first midpoint is at 12.5 %. Before,
    NumPy clipped to the sample extremes and called 0.7125 of the mass 0.95."""
    result = predictive_intervals(
        [_answer(value) for value in (300, 302, 304, 306)], credible_mass=0.95)
    assert result["status"] == "sample_resolution_insufficient"
    assert result["schema"] == puq.PROBABILISTIC_UQ_SCHEMA
    assert result["intervals"] == []
    assert result["credible_mass"] == 0.95
    assert result["minimum_tail_mass"] == pytest.approx(0.125)


def test_schema_and_method_label_moved_with_the_semantics():
    assert puq.PROBABILISTIC_UQ_SCHEMA == "engineering_probabilistic_uq/2"
    result = predictive_intervals(
        [_answer(v) for v in range(300, 340)], credible_mass=0.9)
    (interval,) = result["intervals"]
    assert interval["method"] == "midpoint_latin_hypercube_hazen_empirical_central_interval"
    assert "calibrated coverage of any interval" in result["does_not_include"]
    assert "sampling error of the quantile estimate" in result["does_not_include"]


def test_a_standard_deviation_on_an_offset_scale_is_refused_not_read_as_a_temperature():
    """A sigma of 2 degC about 300 K was converted as the TEMPERATURE 2 degC,
    a 275.15 K standard deviation, and sampled without complaint."""
    with pytest.raises(UnitCompatibilityError):
        build_deterministic_samples([{
            "path": "t", "distribution": "normal",
            "mean": "300 kelvin", "standard_deviation": "2 degC",
        }], sample_count=8, dependence="independent")


def test_a_difference_unit_sigma_is_converted_as_a_difference():
    def kelvin_samples(mean, sigma):
        return _column(build_deterministic_samples([{
            "path": "t", "distribution": "normal",
            "mean": mean, "standard_deviation": sigma,
        }], sample_count=8, dependence="independent"), "t", "kelvin")

    reference = kelvin_samples("300 kelvin", "2 kelvin")
    assert np.allclose(kelvin_samples("26.85 degC", "2 delta_degC"), reference)
    assert np.allclose(kelvin_samples("26.85 degC", "2 kelvin"), reference)
    assert np.allclose(kelvin_samples("300 kelvin", "3.6 delta_degF"), reference)


def test_a_standard_uncertainty_of_an_offset_scale_output_is_stated_as_a_spread():
    """The mean and bounds are points on the scale; the standard uncertainty is
    a difference and must not be written as the temperature 5.9 degF."""
    values = [50.0 + i for i in range(40)]
    result = predictive_intervals(_answers(values, "degF"), credible_mass=0.9)
    (interval,) = result["intervals"]
    assert interval["lower"]["units"] == Quantity(1.0, "degF").units
    spread = Quantity.from_dict(interval["standard_uncertainty"])
    assert is_ratio_scale(spread.units)
    assert spread.magnitude_as_spread_in("delta_degF") == pytest.approx(
        float(np.std(values, ddof=1)))


# ---------------------------------------------------------------------------
# ODC-14b / ODC-04a: what the records say an interval and the design guard are.
# ---------------------------------------------------------------------------

import re

from engcore.mcp.server import _PROBABILISTIC_UQ_DESCRIPTION

# Negations the public text is allowed to make. Everything else is scanned.
_ALLOWED_NEGATIONS = (
    "it is not a credible, confidence or prediction interval",
    "the requested mass is not a guaranteed or calibrated coverage",
    "not a bayesian credible probability",
    "is not evidence of output accuracy, calibrated uncertainty or model validity",
)
_OVERSTATEMENTS = (
    r"\b(credible|confidence|prediction|predictive|tolerance) interval",
    r"\bguarantee[sd]? (the )?coverage",
    r"\b(calibrated|guaranteed|nominal) coverage",
    r"\bcoverage (of|is|=) ?\d",
    r"\bcredible probability",
    r"\baccura(te|cy)\b",
    r"\b(proves?|ensures?|certif(y|ies|ied))\b",
)


def _public_text(payload, skip=("does_not_include", "does_not_establish")):
    """Every key and string value, except lists that are negations by construction.
    Fields are kept apart by ' | ' so no phrase is read across two of them."""
    if isinstance(payload, dict):
        return " | ".join(f"{key} | {_public_text(value)}" for key, value in payload.items()
                          if key not in skip)
    if isinstance(payload, (list, tuple)):
        return " | ".join(_public_text(item) for item in payload)
    return payload if isinstance(payload, str) else ""


def _overstatements(text):
    text = re.sub(r"\s+", " ", text.replace("_", " ").replace("`", "").lower())
    for allowed in _ALLOWED_NEGATIONS:
        text = text.replace(allowed, " ")
    return [hit for pattern in _OVERSTATEMENTS for hit in re.findall(pattern, text)]


def test_odc14b_an_interval_states_a_requested_mass_never_a_coverage():
    result = predictive_intervals(
        [_answer(v) for v in range(300, 340)], credible_mass=0.9)
    (interval,) = result["intervals"]
    assert interval["requested_central_mass"] == 0.9
    assert interval["credible_mass"] == interval["requested_central_mass"]
    interpretation = interval["interpretation"]
    assert interpretation == dict(puq.INTERVAL_INTERPRETATION)
    assert interpretation["kind"] == "empirical_central_quantile_interval"
    assert interpretation["coverage_guaranteed"] is False
    assert interpretation["coverage_calibrated"] is False
    assert interpretation["quantile_rule"] == "hazen"
    # no field anywhere in the record carries a number as a coverage
    def coverage_numbers(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if "coverage" in key and isinstance(value, (int, float)) and not isinstance(value, bool):
                    yield key
                yield from coverage_numbers(value)
        elif isinstance(node, list):
            for item in node:
                yield from coverage_numbers(item)
    assert list(coverage_numbers(result)) == []
    refused = predictive_intervals(
        [_answer(v) for v in (300, 302, 304, 306)], credible_mass=0.95)
    assert refused["requested_central_mass"] == refused["credible_mass"] == 0.95


def test_odc14b_odc04a_no_public_wording_overstates_the_interval_or_the_guard():
    """The tool description and every record it can return may describe an
    empirical central quantile interval and a design diagnostic, and may deny
    being more; they may never claim coverage, credibility or accuracy."""
    completed = predictive_intervals(
        [_answer(v) for v in range(300, 340)], credible_mass=0.9)
    refusals = [
        predictive_intervals([_answer(v) for v in (300, 302, 304, 306)], credible_mass=0.95),
        predictive_intervals([_answer(300), _answer(301, "not_supported")], credible_mass=0.5),
    ]
    texts = {
        "description": _PROBABILISTIC_UQ_DESCRIPTION,
        "completed": _public_text(completed),
        "refusals": _public_text(refusals),
        "design": _public_text([puq.sample_design(32, 10), puq.sample_design(32, 17)]),
    }
    for exc_args in ((_uniform(17), 32), (_uniform(5), 5)):
        with pytest.raises(ValueError) as caught:
            build_deterministic_samples(exc_args[0], sample_count=exc_args[1],
                                        dependence="independent")
        texts[f"refusal n={exc_args[1]}"] = str(caught.value)
    found = {name: _overstatements(text) for name, text in texts.items()}
    assert all(not hits for hits in found.values()), found
    # and the scanner itself still sees an overstatement when one is written
    assert _overstatements("a 95 % confidence interval with calibrated coverage")


def test_odc04a_the_design_record_is_a_diagnostic_and_says_what_it_does_not_establish():
    record = puq.sample_design(64, 10)
    assert record["role"] == "sampling_design_dependence_diagnostic"
    assert record["bound_scope"] == "linear_outputs_only"
    assert set(record["does_not_establish"]) >= {
        "accuracy of any output",
        "accuracy of nonlinear outputs",
        "calibrated coverage of any interval",
        "model validity",
    }
    digest = record["design_sha256"]
    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    assert digest == puq.sample_design(64, 10)["design_sha256"]
    assert digest != puq.sample_design(32, 10)["design_sha256"]
