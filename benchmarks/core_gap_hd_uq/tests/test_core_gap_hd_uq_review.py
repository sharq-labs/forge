"""Core Gap Review (high-dimensional UQ): the committed measurements say what the review claims."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
ROUND = ROOT / "benchmarks" / "core_gap_hd_uq"


def _json(name):
    return json.loads((ROUND / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def probe():
    spec = importlib.util.spec_from_file_location("_hd_probe_test", ROUND / "audit" / "local_gaussian_probe.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["_hd_probe_test"] = module
    spec.loader.exec_module(module)
    return module


# ---- the approximation never calls itself exact ------------------------------

def test_every_probe_result_names_its_approximation_class_and_claims_no_exact_posterior():
    for case in _json("FAILURE_CASES.json")["cases"].values():
        assert case["probe"]["posterior_class"] == "LOCAL_GAUSSIAN_APPROXIMATION"
        assert case["probe"]["predictive_class"] == "LINEARIZED_PREDICTIVE_UQ"
        assert case["probe"]["exact_posterior_claimed"] is False


def test_the_identifiability_thresholds_are_read_from_the_frozen_core_not_copied(probe):
    import inspect
    from engcore.inference import assess_identifiability
    defaults = inspect.signature(assess_identifiability).parameters
    assert probe.THRESHOLDS == {"correlation": defaults["correlation_threshold"].default,
                                "condition_number": defaults["condition_threshold"].default,
                                "relative_width": defaults["width_threshold"].default}


# ---- Phase 10: refusal where the assumptions fail ------------------------------

@pytest.mark.parametrize("case, claim, reason", [
    ("F1_strong_nonlinearity", "REFUSED", "NONLINEAR_BEYOND_LOCAL_GAUSSIAN"),
    ("F2_parameter_at_bound", "REFUSED", "PARAMETER_AT_BOUND"),
    ("F3_nearly_singular_jacobian", "REFUSED", "NUMERICALLY_SINGULAR_JACOBIAN"),
    ("F4_multimodal_with_multistart", "REFUSED", "SECOND_MODE_FOUND"),
    ("F6_log_parameter_logk", "REFUSED", "NONLINEAR_BEYOND_LOCAL_GAUSSIAN"),
])
def test_the_route_refuses_where_local_gaussian_assumptions_fail(case, claim, reason):
    result = _json("FAILURE_CASES.json")["cases"][case]["probe"]
    assert result["claim"] == claim and reason in result["refusals"]


def test_a_mirror_mode_is_invisible_to_every_local_diagnostic_without_multistart():
    case = _json("FAILURE_CASES.json")["cases"]["F4_multimodal_no_multistart"]
    assert case["probe"]["claim"] == "DOWNGRADED" and "GLOBAL_UNIQUENESS_NOT_ASSESSED" in case["probe"]["downgrades"]
    assert case["importance_check"]["ess_fraction"] > 0.99          # importance sampling does not see it
    assert case["grid_reference"]["sd"][0] > 100 * case["probe"]["posterior"]["sd"][0]  # the grid does


def test_route_validity_and_identifiability_are_separate_verdicts():
    case = _json("FAILURE_CASES.json")["cases"]["F5_weak_identifiability"]
    assert case["probe"]["claim"] != "REFUSED"
    assert case["probe"]["identifiability"]["status"] == "PARAMETERS_NOT_IDENTIFIABLE"


def test_the_same_physics_changes_verdict_with_its_parameterization():
    cases = _json("FAILURE_CASES.json")["cases"]
    assert cases["F6_linear_parameter_k"]["probe"]["claim"] == "SUPPORTED"
    assert cases["F6_log_parameter_logk"]["probe"]["claim"] == "REFUSED"


def test_the_frozen_grid_thin_ridge_finding_is_recorded_with_its_evidence():
    study = _json("FAILURE_CASES.json")["cases"]["F5_weak_identifiability"]["grid_resolution_study"]["study"]
    bounds = [r for r in study if r["window"] == "declared_bounds"]
    local = [r for r in study if r["window"] == "estimate_pm_6_gaussian_sd"]
    assert all(np.allclose(r["mean"], bounds[0]["mean"]) for r in bounds)          # resolution-stable
    assert all(r["effective_sample_size"] >= 8 and max(r["spacing_to_std"]) < 1 for r in bounds)  # no refusal
    assert not np.allclose(bounds[0]["mean"], local[0]["mean"], atol=0.5)          # and wrong


# ---- Phase 9: B3 reproduction ------------------------------------------------------

def test_the_probe_reproduces_the_committed_b3_linear_gaussian_results_and_the_one_miss_is_explained():
    """12 of 13 within the DECLARED tolerance; P9's chi-square misses it and the tolerance is not moved.

    The two routes are centred at different estimates (frozen calibrate vs closed-form WLS, 2.7e-7 V apart
    for P9). Re-centred at the WLS estimate every model agrees to <= 1e-9, so the miss is the centre, not the route.
    """
    battery = _json("BATTERY_B3_REFERENCE.json")
    assert set(battery["models"]) == {"P1", "P2", "P3", "P4", "P5", "P7", "P9", "T3", "T5", "T6", "T11", "T21", "T41"}
    missed = {k for k, m in battery["models"].items() if not m["vs_b3_domain_route"]["within_tolerance"]}
    assert missed == {"P9"}
    assert battery["models"]["P9"]["vs_b3_domain_route"]["max_mean_diff_in_sd"] <= battery["tolerances"]["vs_b3_domain_route"]["mean_in_sd"]
    explained = battery["centre_explanation"]["models"]
    assert all(v["chi_square_relative_at_wls_centre"] <= 1e-9 for v in explained.values())
    assert battery["models"]["T41"]["vs_b3_domain_route"]["within_tolerance"]


def test_the_probe_agrees_with_the_frozen_core_grid_on_every_low_dimensional_b3_model():
    battery = _json("BATTERY_B3_REFERENCE.json")
    grid = {k: m["vs_core_grid"] for k, m in battery["models"].items() if "vs_core_grid" in m}
    assert set(grid) == {"P1", "P2", "P3", "P4", "T3", "T5"}
    assert all(g["within_tolerance"] for g in grid.values())


def test_t41_is_supported_and_its_verification_tiers_agree():
    battery = _json("BATTERY_B3_REFERENCE.json")
    t41 = battery["models"]["T41"]
    assert t41["probe_claim"] == "SUPPORTED" and t41["probe_identifiability"] == "PARAMETERS_IDENTIFIABLE"
    assert t41["reparameterizations"]["successive_differences"] == "PARAMETERS_NOT_IDENTIFIABLE"
    tiers = battery["t41_verification_tiers"]
    assert tiers["importance_sampling_option_C"]["ess_fraction"] > 0.99
    lo, hi = tiers["full_hessian_laplace_option_A"]["sd_ratio_range"]
    assert abs(lo - 1) < 1e-6 and abs(hi - 1) < 1e-6


def test_parameterization_verdicts_match_between_grid_and_probe():
    for model, statuses in _json("BATTERY_B3_REFERENCE.json")["parameterization_on_core_grid"].items():
        for name, entry in statuses.items():
            assert entry["core_grid"] == entry["local_gaussian"], (model, name, entry)


# ---- Phase 7: three domains ----------------------------------------------------------

def test_tcr_grid_and_probe_agree_on_both_designs():
    tcr = _json("DOMAIN_TCR.json")
    for design in ("WIDE_SPAN", "NARROW_SPAN"):
        agreement = tcr[design]["agreement"]
        assert agreement["identifiability_equal"]
        assert max(agreement["mean_shift_in_grid_sd"]) < 0.1
        assert all(0.95 < r < 1.05 for r in agreement["sd_ratio_local_over_grid"])


def test_kinetics_is_a_real_second_need_and_the_weak_design_is_refused():
    k = _json("DOMAIN_KINETICS.json")
    multi = k["MULTI"]
    assert multi["local_gaussian"]["claim"] == "SUPPORTED"
    assert multi["local_gaussian"]["global_uniqueness"] == "MULTISTART_NO_SECOND_MODE"
    assert multi["calibration"]["condition_solves"] + multi["local_condition_solves"] < 11163 / 50
    assert all(0.85 < r < 1.15 for r in multi["vs_committed_k2_grid"]["sd_ratio_local_over_grid"])
    assert multi["local_gaussian"]["identifiability"]["status"] != multi["local_gaussian"]["reparameterizations"]["log_k_at_350K_and_e_over_r"]["status"]
    assert k["WEAK_C2"]["local_gaussian"]["claim"] == "REFUSED"


# ---- Phases 1 and 11: scaling -----------------------------------------------------------

def test_scaling_is_linear_for_the_probe_and_exponential_for_the_grid():
    s = _json("SCALING.json")
    for p, row in s["local"].items():
        assert row["forward_calls"]["forward"] == 4 * int(p) + 1
    assert s["grid_projected"]["6"]["calibration_table_gib"] > 8
    assert s["grid_projected"]["6"]["label"].startswith("PROJECTED")


# ---- Phase 8: compatibility --------------------------------------------------------------

def test_the_compatibility_verdict_is_recorded_with_its_binding_checks():
    c = _json("COMPATIBILITY.json")["phase8_compatibility"]
    assert c["verdict"] == "CORE_FREEZE_V2_REQUIRED"
    assert c["live_api"]["frozen_count"] == 194 and c["live_api"]["total_public"] == 205
    assert {"contract.api", "bytes.pinned_contract_files", "certificate.verifies"} <= set(c["binding_checks_in_descendant_mode"])
    patterns = {p for area in c["certificate_scope"] for p in area["patterns"]}
    assert "src/engcore/inference/**/*.py" in patterns and "src/engcore/adequacy/**/*.py" in patterns
