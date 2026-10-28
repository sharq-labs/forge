"""Public development integration; no hidden evaluation data."""
import copy
import json
import subprocess
import sys

import pytest


def test_development_bundle_and_replay():
    from benchmarks.rediscovery_development.run import build_bundle, replay_bundle
    bundle = build_bundle()
    assert bundle["scope"] == "PUBLIC_SYNTHETIC_L1_DEVELOPMENT"
    assert bundle["assumptions"]["data"] == "public synthetic noiseless controls"
    assert "no noise was generated" in bundle["assumptions"]["sigma"]
    assert bundle["assumptions"]["physical_validation"] == "NOT_RUN"
    assert replay_bundle(bundle) == "EXACT"
    good = bundle["cases"]["informative"]
    assert good["assessment"]["claims"]["IDENTIFIABILITY"]["disposition"] == "SUPPORTED"
    assert good["reference"]["resistance_ohm"] == pytest.approx(2.0)
    assert good["assessment"]["hypothesis"]["parameter_set"][0]["estimate"] == pytest.approx(good["reference"]["resistance_ohm"])
    assert good["reference"]["observations"] == 20
    assert bundle["cases"]["uninformative"]["reference"]["resistance_ohm"] is None
    assert bundle["cases"]["uninformative"]["assessment"]["claims"]["IDENTIFIABILITY"]["disposition"] != "SUPPORTED"
    assert bundle["cases"]["misspecified"]["assessment"]["claims"]["MODEL_ADEQUACY"]["disposition"] == "NOT_SUPPORTED"
    assert bundle["cases"]["unknown_noise"]["assessment"]["claims"]["IDENTIFIABILITY"]["disposition"] != "SUPPORTED"
    assert bundle["cases"]["unknown_noise"]["assessment"]["hypothesis"]["parameter_set"][0]["standard_error"] is None
    for case in bundle["cases"].values():
        assert case["assessment"]["claims"]["WITHIN_CELL_GENERALIZATION"]["disposition"] == "NOT_ASSESSABLE"
        assert case["assessment"]["claims"]["CROSS_CELL_TRANSFER"]["disposition"] == "NOT_ASSESSABLE"
    for name in ("informative", "milliamps", "misspecified"):
        case = bundle["cases"][name]
        # Smooth one-parameter fit; tolerate numerical optimization/12-digit serialization only.
        assert case["assessment"]["hypothesis"]["parameter_set"][0]["estimate"] == pytest.approx(case["reference"]["resistance_ohm"], rel=1e-9, abs=1e-12)


def test_units_and_truth_are_not_reported_as_discovery():
    from benchmarks.rediscovery_development.run import build_bundle
    bundle = build_bundle()
    a = bundle["cases"]["informative"]["assessment"]["hypothesis"]["parameter_set"]
    b = bundle["cases"]["milliamps"]["assessment"]["hypothesis"]["parameter_set"]
    assert a == b
    assert bundle["level"] == "L1_PARAMETER_ESTIMATION"
    assert bundle["blindfold"] is False


def test_tampered_bundle_is_rejected():
    from benchmarks.rediscovery_development.run import build_bundle, replay_bundle
    from engcore.mind.repsem.assess import ReplayMismatch
    bundle = copy.deepcopy(build_bundle())
    bundle["cases"]["informative"]["reference"]["resistance_ohm"] = 99
    with pytest.raises(ReplayMismatch):
        replay_bundle(bundle)


def test_reference_uses_scored_observations_not_public_truth():
    from benchmarks.rediscovery_development.fixtures import build
    from benchmarks.rediscovery_development.run import reference
    spec = build("informative")
    columns = spec["sets"]["calibration"][0]["columns"]
    columns["voltage"] = [9999.] + [3 * i for i in columns["current"][1:]]
    assert reference(spec)["resistance_ohm"] == pytest.approx(3.)


def test_cli_roundtrip(tmp_path):
    output = tmp_path / "development.json"
    command = [sys.executable, "-m", "benchmarks.rediscovery_development.run"]
    run = subprocess.run(command + ["--output", str(output)], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert json.loads(output.read_text())["blindfold"] is False
    replay = subprocess.run(command + ["--replay", str(output)], capture_output=True, text=True)
    assert replay.returncode == 0, replay.stderr
    assert "EXACT" in replay.stdout
    before = output.read_bytes()
    repeated = subprocess.run(command + ["--output", str(output)], capture_output=True, text=True)
    assert repeated.returncode != 0
    assert output.read_bytes() == before
