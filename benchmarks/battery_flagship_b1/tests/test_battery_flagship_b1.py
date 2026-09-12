"""Battery Flagship B1: the committed result, held to what it says.

These re-derive the verdict rather than trusting the JSON. If the measured
evidence, the adapter, the frozen Core machinery or the preregistered protocol
changed in a way that moves the scientific result, a test here fails -- which
is the difference between a round report and a claim that can go stale
silently.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
ROUND = ROOT / "benchmarks" / "battery_flagship_b1"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def harness():
    return _load("_b1_harness", ROUND / "audit" / "run_b1.py")


@pytest.fixture(scope="module")
def committed():
    return json.loads((ROUND / "RESULTS.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def secondary():
    return json.loads((ROUND / "SECONDARY.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rerun(harness):
    discharge = harness.traces(harness.DISCHARGE_SHEET)
    prereg = harness.PREREG
    cal = tuple(prereg["split"]["calibration_state_of_charge"])
    held = tuple(prereg["split"]["held_out_state_of_charge"])
    source, _ = harness.build_source(discharge, cal, held, "S-OCV.BATT_001.discharge")
    return harness.run(source, held, label="PRIMARY", seed=prereg["calibration"]["seed"])


def test_the_measured_evidence_is_the_preregistered_file():
    prereg = json.loads((ROUND / "PREREGISTRATION.json").read_text(encoding="utf-8"))
    path = ROOT / prereg["experiment"]["file"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == prereg["experiment"]["file_sha256"]


def test_the_raw_data_passed_integrity_before_anything_was_fitted():
    report = json.loads((ROUND / "DATA_INTEGRITY.json").read_text(encoding="utf-8"))
    assert report["passed"], report["problems"]
    for sheet in report["sheets"].values():
        assert sheet["missing_cells"] == 0
        assert sheet["physically_impossible_values"] == 0
        assert sheet["labels_match_published_inventory"]


def test_calibration_and_held_out_are_disjoint_by_identity_and_content(rerun):
    assert rerun["split"]["intersection_by_identity"] == []
    assert rerun["split"]["intersection_by_material_content"] == []


def test_no_calibration_sigma_was_computed_from_a_held_out_trace(committed):
    """Amendment A2, checked on the committed record."""
    held = {h["state_of_charge"] for h in committed["held_out"]}
    for cid in committed["split"]["calibration"]:
        pool = set(committed["observation_budgets"][cid]["sigma_computed_from"])
        assert not (pool & held), (cid, pool & held)


def test_the_central_result_reproduces(rerun, committed):
    """CONVERGED + IDENTIFIABLE + INADEQUATE, re-run from the raw file."""
    assert rerun["calibration"]["status"] == "CALIBRATION_CONVERGED"
    assert rerun["identifiability"]["status"] == "PARAMETERS_IDENTIFIABLE"
    assert rerun["adequacy_verdict"] == "inadequate_for_declared_study"
    for key in ("rmse_v", "mae_v", "max_abs_error_v", "chi_square"):
        assert rerun["metrics"][key] == pytest.approx(committed["metrics"][key], rel=1e-9), key


def test_the_verdict_follows_from_the_preregistered_rule(committed):
    m = committed["metrics"]
    statistic = sum(h["standardized_residual"] ** 2 for h in committed["held_out"])
    assert statistic == pytest.approx(m["chi_square"], rel=1e-12)
    assert m["alpha"] == 0.01 and m["chi_square_df"] == len(committed["held_out"]) == 3
    assert (m["chi_square_p_value"] < m["alpha"]) == (
        committed["adequacy_verdict"] == "inadequate_for_declared_study"
    )


def test_the_calibration_agrees_with_an_independent_closed_form(committed):
    oracle = committed["posterior"]["wls_oracle"]
    for name, value in committed["calibration"]["estimates_v"].items():
        assert value == pytest.approx(oracle[name], abs=1e-9)


def test_the_posterior_was_resolved_not_collapsed(committed):
    diagnostics = committed["posterior"]["diagnostics"]
    assert diagnostics["effective_sample_size"] > 8.0
    assert max(diagnostics["spacing_to_std"]) < 1.0
    assert "grid_refusals" not in committed["posterior"]


def test_uncertainty_is_decomposed_and_discrepancy_is_named_not_invented(committed):
    assert committed["model_discrepancy"] == "MODEL_DISCREPANCY_NOT_MODELLED"
    for h in committed["held_out"]:
        total = h["total_standard_uncertainty_v"]
        assert total == pytest.approx(
            math.hypot(h["parameter_standard_uncertainty_v"], h["measurement_standard_uncertainty_v"]),
            rel=1e-6,
        )


def test_the_residual_is_structured_and_not_a_state_of_charge_scale_error(committed):
    """A capacity or SOC-scale error moves every chord prediction the same way.

    The two plateau interpolations miss in OPPOSITE directions, which such an
    error cannot produce -- and the knee misses by two orders of magnitude more.
    """
    by_z = {h["state_of_charge"]: h["error_v"] for h in committed["held_out"]}
    assert by_z[0.4] > 0 > by_z[0.6]
    assert abs(by_z[0.0]) > 10 * max(abs(by_z[0.4]), abs(by_z[0.6]))


def test_no_state_of_charge_outside_calibration_is_consistent(secondary):
    """S1: not even the plateau core predicts its neighbours at measurement precision."""
    assert all(not row["consistent_at_alpha_0.01"] for row in secondary["S1_applicability_boundary"])


def test_the_conditioning_current_does_not_enter_the_compared_value(secondary):
    assert all(row["identical"] for row in secondary["S5_conditioning_current_invariance"])


def test_the_models_own_validity_machinery_gave_no_warning(secondary):
    """Phase 15: the finding is also that nothing in the record would have flagged it."""
    for row in secondary["applicability_assessment_of_calibrated_cell"]:
        assert row["violated"] == []
