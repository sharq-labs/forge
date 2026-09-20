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
    assert interval["lower"]["magnitude"] == pytest.approx(301.5)
    assert interval["upper"]["magnitude"] == pytest.approx(304.5)
