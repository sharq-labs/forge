"""Battery Flagship B2: the committed result, re-derived and held to what it says."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
ROUND = ROOT / "benchmarks" / "battery_flagship_b2"
B1_ROUND = ROOT / "benchmarks" / "battery_flagship_b1"


def _json(name, round_=ROUND):
    return json.loads((round_ / name).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def harness():
    spec = importlib.util.spec_from_file_location("_b2_harness", ROUND / "audit" / "run_b2.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def results():
    return _json("RESULTS.json")


@pytest.fixture(scope="module")
def comparison():
    return _json("COMPARISON.json")


@pytest.fixture(scope="module")
def secondary():
    return _json("SECONDARY.json")


@pytest.fixture(scope="module")
def rerun(harness):
    discharge = harness.B1.traces(harness.B1.DISCHARGE_SHEET)
    source, _ = harness.B1.build_source(discharge, (0.2, 0.5, 0.8), (0.0, 0.4, 0.6), "S-OCV.BATT_001.discharge")
    return harness.run_curve(harness.POLY2, source, (0.0, 0.4, 0.6), label="B2-POLY2")


# ---- same evidence, same protocol ---------------------------------------------

def test_the_evidence_is_b1s_preregistered_file(results):
    prereg = _json("PREREGISTRATION.json")
    path = ROOT / prereg["phase3_same_measured_data"]["file"]
    assert sha(path) == prereg["phase3_same_measured_data"]["file_sha256"] == results["evidence_sha256_after"]


def test_b1_artifacts_are_the_ones_b2_compared_against(results):
    assert sha(B1_ROUND / "RESULTS.json") == results["b1_results_sha256"]


def test_the_held_out_evidence_identities_are_b1s(comparison):
    assert comparison["same_evidence_as_b1"] and all(comparison["same_evidence_as_b1"].values())


def test_the_split_is_disjoint_by_identity_and_content(results):
    for key in ("primary", "secondary"):
        assert results[key]["split"]["intersection_by_identity"] == []
        assert results[key]["split"]["intersection_by_material_content"] == []


def test_no_calibration_sigma_came_from_a_held_out_trace(results):
    for cid in results["primary"]["split"]["calibration"]:
        assert not set(results["observation_budgets"][cid]["sigma_computed_from"]) & {0.0, 0.4, 0.6}


# ---- the primary result reproduces ----------------------------------------------

def test_the_primary_result_reproduces_from_the_raw_file(rerun, results):
    committed = results["primary"]
    assert rerun["calibration"]["status"] == "CALIBRATION_CONVERGED"
    assert rerun["identifiability"]["status"] == "PARAMETERS_IDENTIFIABLE"
    assert rerun["adequacy_verdict"] == "inadequate_for_declared_study"
    for key in ("rmse_v", "mae_v", "max_abs_error_v", "chi_square"):
        assert rerun["metrics"][key] == pytest.approx(committed["metrics"][key], rel=1e-9), key


def test_zero_residual_dof_is_recorded_as_no_internal_check(results):
    run = results["primary"]
    assert run["free_parameters"] == run["calibration_observations"] == 3
    assert run["residual_degrees_of_freedom"] == 0
    assert all(abs(r) < 1e-9 for r in run["calibration"]["standardized_calibration_residuals"])
    assert "NO internal check" in run["calibration"]["zero_residual_dof_note"]


def test_the_calibration_agrees_with_the_closed_form(results):
    assert results["primary"]["calibration"]["max_abs_disagreement_with_closed_form_v"] < 1e-9


# ---- the comparison and the verdict ------------------------------------------------

def test_the_verdict_follows_the_preregistered_mapping(results, comparison, secondary):
    p = results["primary"]["metrics"]["chi_square_p_value"]
    reduction = comparison["rmse_reduction_fraction"]
    assert p < 0.01
    assert reduction < comparison["material_threshold_fraction"] == 0.20
    assert secondary["flexibility_guard"]["jacobian_rank"] == 3 < 5
    assert comparison["verdict"] == "BATTERY B2 BLOCKED -- DATA LIMIT UNDER THE BINDING SPLIT"


def test_the_chi_square_drop_is_wider_uncertainty_not_better_prediction(results, comparison):
    """chi-square fell ~49 % while RMSE fell ~1 %: the extra parameter widened the
    predictive spread at the extrapolated point; it did not move the prediction."""
    b1 = _json("RESULTS.json", B1_ROUND)["held_out"]
    b2 = results["primary"]["held_out"]
    assert comparison["rmse_reduction_fraction"] < 0.02
    assert b2[0]["parameter_standard_uncertainty_v"] > 2 * b1[0]["parameter_standard_uncertainty_v"]


def test_convergence_is_not_identifiability(secondary):
    guard = secondary["flexibility_guard"]
    assert guard["frozen_calibrate_outcome"]["status"] == "CALIBRATION_CONVERGED"
    assert guard["null_space_dimension"] == 2 and not guard["structurally_identifiable"]


# ---- phases 12-15 ---------------------------------------------------------------

def test_applicable_with_no_violation_yet_empirically_inadequate(secondary):
    for name in ("B1_chord", "B2_curve"):
        row = secondary["empirical_adequacy_batt_001_held_out"][name]
        assert row["applicability_violated"] == []
        assert row["status"] == "MODEL_EMPIRICALLY_INADEQUATE"


def test_the_curve_refuses_a_cutoff_the_chord_answers_with_nonsense(secondary):
    cutoff = secondary["cutoff_on_curve"]
    assert cutoff["b1_chord_state_of_charge"] < 0.0
    assert cutoff["b2_curve_status"] == "outside_validated_domain"
    assert cutoff["b2_curve_state_of_charge"] is None


def test_hysteresis_is_comparable_to_the_plateau_residual_but_not_to_the_knee(secondary, results):
    held = {row["state_of_charge"]: row for row in secondary["hysteresis"] if row["partition"] == "held_out"}
    for z in (0.4, 0.6):
        assert 0.5 < held[z]["ratio_to_b2_residual"] < 1.0
    knee = abs(results["primary"]["held_out"][0]["error_v"]) * 1e3
    assert max(abs(r["charge_minus_discharge_mv"]) for r in secondary["hysteresis"]) < 0.05 * knee


def test_neither_representation_generalizes_to_batt_002(secondary):
    g = secondary["generalization_batt_002"]
    assert g["B1_chord"]["status"] == g["B2_curve"]["status"] == "MODEL_EMPIRICALLY_INADEQUATE"
    assert "DATA_LIMIT" in g["other_chemistries"]
