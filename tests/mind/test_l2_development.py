import copy
import json
import subprocess
import sys
import pytest


def test_selection_controls():
    from benchmarks.rediscovery_l2.run import evaluate
    from benchmarks.rediscovery_l2.fixtures import build
    for name, decision, selected in (("linear", "ONE_COMPATIBLE", "linear"),
                                      ("quadratic", "ONE_COMPATIBLE", "quadratic"),
                                      ("ambiguous", "AMBIGUOUS", None),
                                      ("neither", "NONE_COMPATIBLE", None)):
        result = evaluate(**build(name))
        assert result["decision"] == decision
        assert result["selected"] == selected
        assert result["evaluation_role"] == "selection"
        assert result["final_evaluation"] == "NOT_RUN"
        for model in result["models"].values():
            assert model["estimate"] == pytest.approx(model["reference_estimate"], rel=1e-8)
            assert model["selection_rmse_volts"] == pytest.approx(model["reference_selection_rmse_volts"], abs=1e-9)
            assert model["budget"] == {"calibration_available": 21, "calibration_scored": 20, "selection_scored": 20}


def test_selection_cannot_change_fitted_parameters():
    from benchmarks.rediscovery_l2.run import evaluate
    from benchmarks.rediscovery_l2.fixtures import build
    case = build("linear")
    before = evaluate(**case)
    case["selection"]["voltage"] = [v + 10 for v in case["selection"]["voltage"]]
    after = evaluate(**case)
    for name in before["models"]:
        assert before["models"][name]["assessment"] == after["models"][name]["assessment"]
    assert before["selection_digest"] != after["selection_digest"]


@pytest.mark.parametrize("key", ["sample_ids", "group_ids"])
def test_overlap_is_rejected(key):
    from benchmarks.rediscovery_l2.run import evaluate
    from benchmarks.rediscovery_l2.fixtures import build
    case = build("linear")
    case["selection"][key][0] = case["calibration"][key][0]
    with pytest.raises(ValueError, match="overlap"):
        evaluate(**case)


def test_missing_resolution_never_selects():
    from benchmarks.rediscovery_l2.run import evaluate
    from benchmarks.rediscovery_l2.fixtures import build
    case = build("linear")
    case["resolution_volts"] = None
    result = evaluate(**case)
    assert result["decision"] == "UNASSESSED"
    assert result["selected"] is None


def test_out_of_domain_selection_is_refused():
    from benchmarks.rediscovery_l2.run import evaluate
    from benchmarks.rediscovery_l2.fixtures import build
    case = build("linear")
    case["selection"]["current"][0] = 3.
    with pytest.raises(ValueError, match="domain"):
        evaluate(**case)


def test_unit_equivalence():
    from benchmarks.rediscovery_l2.run import evaluate
    from benchmarks.rediscovery_l2.fixtures import build
    a = build("quadratic")
    b = copy.deepcopy(a)
    for split in ("calibration", "selection"):
        b[split]["current"] = [x * 1000 for x in b[split]["current"]]
        b[split]["current_unit"] = "mA"
        b[split]["voltage"] = [x * 1000 for x in b[split]["voltage"]]
        b[split]["voltage_unit"] = "mV"
    assert evaluate(**a)["selected"] == evaluate(**b)["selected"] == "quadratic"


def test_order_does_not_break_ambiguity(monkeypatch):
    from benchmarks.rediscovery_l2 import run
    from benchmarks.rediscovery_l2.fixtures import build
    families = run.contracts()
    before = run.evaluate(**build("ambiguous"))
    monkeypatch.setattr(run, "contracts", lambda: dict(reversed(list(families.items()))))
    after = run.evaluate(**build("ambiguous"))
    assert before["selected"] == after["selected"] is None
    assert before["decision"] == after["decision"] == "AMBIGUOUS"


@pytest.mark.parametrize("resolution", [0, -1, float("inf"), float("nan")])
def test_invalid_resolution_is_refused(resolution):
    from benchmarks.rediscovery_l2.run import evaluate
    from benchmarks.rediscovery_l2.fixtures import build
    case = build("linear")
    case["resolution_volts"] = resolution
    with pytest.raises(ValueError, match="resolution"):
        evaluate(**case)


def test_zero_excitation_is_not_a_success():
    from benchmarks.rediscovery_l2.run import evaluate
    from benchmarks.rediscovery_l2.fixtures import build
    case = build("linear")
    for split in ("calibration", "selection"):
        case[split]["current"] = [0.] * len(case[split]["current"])
        case[split]["voltage"] = [0.] * len(case[split]["voltage"])
    result = evaluate(**case)
    assert result["selected"] is None
    assert result["decision"] == "UNASSESSED"


def test_cli_replay_and_tamper(tmp_path):
    output = tmp_path / "l2.json"
    command = [sys.executable, "-m", "benchmarks.rediscovery_l2.run"]
    created = subprocess.run(command + ["--output", str(output)], capture_output=True, text=True)
    assert created.returncode == 0, created.stderr
    telemetry = json.loads(created.stderr)
    assert telemetry["record_digest"]
    assert telemetry["telemetry"]["linear"]["linear"]["engine_seconds"] >= 0
    checked = subprocess.run(command + ["--replay", str(output)], capture_output=True, text=True)
    assert checked.returncode == 0, checked.stderr
    assert "EXACT" in checked.stdout
    record = json.loads(output.read_text())
    assert record["blindfold"] is False
    record["cases"]["linear"]["result"]["selected"] = "quadratic"
    output.write_text(json.dumps(record))
    tampered = subprocess.run(command + ["--replay", str(output)], capture_output=True, text=True)
    assert tampered.returncode != 0
    assert "ReplayMismatch" in tampered.stderr
