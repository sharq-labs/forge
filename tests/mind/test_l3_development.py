import copy
import json
import subprocess
import sys
import pytest


@pytest.mark.parametrize("case,support", [("linear", ["x"]), ("quadratic", ["x2"]), ("mixed", ["x", "x2"])])
def test_recovers_bounded_support(case, support):
    from benchmarks.rediscovery_l3.run import evaluate
    from benchmarks.rediscovery_l3.fixtures import build
    result = evaluate(**build(case))
    assert result["decision"] == "ONE_MINIMAL_SUPPORT"
    assert result["selected"]["feature_names"] == support
    expected = {"linear": [2.], "quadratic": [3.], "mixed": [2., 3.]}[case]
    assert result["selected"]["coefficients"] == pytest.approx(expected, rel=1e-10, abs=1e-12)
    assert result["selected"]["intercept"] == pytest.approx(1., abs=1e-10)
    assert result["selected"]["holdout_rmse"] < 1e-10
    assert result["selected"]["evaluation_role"] == "selection"
    assert result["final_evaluation"] == "NOT_RUN"
    assert result["baseline"]["selection_rmse_volts"] < 1e-10


@pytest.mark.parametrize("case,decision", [("ambiguous", "AMBIGUOUS"), ("outside", "NONE_COMPATIBLE"), ("constant", "UNASSESSED")])
def test_negative_controls(case, decision):
    from benchmarks.rediscovery_l3.run import evaluate
    from benchmarks.rediscovery_l3.fixtures import build
    result = evaluate(**build(case))
    assert result["decision"] == decision
    assert result["selected"] is None


def test_selection_does_not_refit_candidates():
    from benchmarks.rediscovery_l3.run import evaluate
    from benchmarks.rediscovery_l3.fixtures import build
    case = build("mixed")
    before = evaluate(**case)
    case["selection"]["voltage"] = [v + 10 for v in case["selection"]["voltage"]]
    after = evaluate(**case)
    fits = lambda r: {tuple(c["feature_names"]): (c["coefficients"], c["intercept"]) for c in r["candidates"]}
    assert fits(before) == fits(after)


@pytest.mark.parametrize("key", ["sample_ids", "group_ids"])
def test_overlap_is_refused(key):
    from benchmarks.rediscovery_l3.run import evaluate
    from benchmarks.rediscovery_l3.fixtures import build
    case = build("mixed")
    case["selection"][key][0] = case["calibration"][key][0]
    with pytest.raises(ValueError, match="overlap"):
        evaluate(**case)


def test_units_preserve_recovered_support():
    from benchmarks.rediscovery_l3.run import evaluate
    from benchmarks.rediscovery_l3.fixtures import build
    case = copy.deepcopy(build("mixed"))
    for name in ("calibration", "selection"):
        case[name]["current"] = [v*1000 for v in case[name]["current"]]
        case[name]["current_unit"] = "mA"
        case[name]["voltage"] = [v*1000 for v in case[name]["voltage"]]
        case[name]["voltage_unit"] = "mV"
    assert evaluate(**case)["selected"]["feature_names"] == ["x", "x2"]


def test_missing_resolution_is_not_zero_uncertainty():
    from benchmarks.rediscovery_l3.run import evaluate
    from benchmarks.rediscovery_l3.fixtures import build
    case = build("mixed")
    case["resolution_volts"] = None
    result = evaluate(**case)
    assert result["decision"] == "UNASSESSED"
    assert result["selected"] is None


def test_out_of_domain_is_refused():
    from benchmarks.rediscovery_l3.run import evaluate
    from benchmarks.rediscovery_l3.fixtures import build
    case = build("mixed")
    case["selection"]["current"][0] = 10.
    with pytest.raises(ValueError, match="domain"):
        evaluate(**case)


def test_failed_engine_candidate_cannot_be_selected():
    from benchmarks.rediscovery_l3.run import evaluate
    def part(role, x, y):
        return {"current": x, "voltage": y, "current_unit": "A", "voltage_unit": "V",
                "sample_ids": [f"{role}-{i}" for i in range(len(x))], "group_ids": [role]*len(x)}
    result = evaluate(part("cal", [-1., 1.], [.999, 1.001]),
                      part("sel", [-.5, .5], [1., 1.]), .0002)
    assert result["selected"] is None
    assert result["decision"] == "NONE_COMPATIBLE"


def test_cli_replay_and_tamper(tmp_path):
    output = tmp_path / "l3.json"
    command = [sys.executable, "-m", "benchmarks.rediscovery_l3.run"]
    result = subprocess.run(command + ["--output", str(output)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stderr)["record_digest"]
    replay = subprocess.run(command + ["--replay", str(output)], capture_output=True, text=True)
    assert replay.returncode == 0, replay.stderr
    assert "EXACT" in replay.stdout
    record = json.loads(output.read_text())
    assert record["blindfold"] is False
    record["cases"]["mixed"]["result"]["selected"]["intercept"] = 999.
    output.write_text(json.dumps(record))
    rejected = subprocess.run(command + ["--replay", str(output)], capture_output=True, text=True)
    assert rejected.returncode != 0
    assert "ReplayMismatch" in rejected.stderr
