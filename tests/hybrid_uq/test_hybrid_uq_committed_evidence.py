"""Static guards over the committed Core V2 evidence: the claims the round report makes are the ones the records hold.

These read JSON only; the runs themselves are benchmarks/core_v2_hybrid_uq/audit/*.py.
"""

from __future__ import annotations

import json
import pathlib

import pytest

ROUND = pathlib.Path(__file__).resolve().parents[2] / "benchmarks" / "core_v2_hybrid_uq"


def _load(name):
    path = ROUND / name
    if not path.exists():
        pytest.fail(f"{name} is missing from {ROUND}")
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_battery_t41_flagship_is_routed_without_a_grid_and_matches_b3():
    t41 = _load("BATTERY_T41.json")["models"]["T41"]
    assert t41["p"] == 41 and t41["decision"] == "LOCAL_GAUSSIAN" and t41["claim"] == "SUPPORTED"
    assert t41["considered"][0]["reason"] == "GRID_NOT_SUPPLIED"
    assert t41["vs_b3_domain_route"]["within_declared_tolerance"] is True
    assert t41["identifiability"]["knot_or_node_voltages"] == "PARAMETERS_IDENTIFIABLE"
    assert t41["identifiability"]["successive_differences"] == "PARAMETERS_NOT_IDENTIFIABLE"
    assert t41["predictive"]["sources"] == ["PARAMETER_UNCERTAINTY", "MEASUREMENT_UNCERTAINTY", "MODEL_DISCREPANCY_NOT_MODELLED"]


def test_every_battery_model_that_misses_its_tolerance_is_named():
    models = _load("BATTERY_T41.json")["models"]
    misses = sorted(m for m, r in models.items() if not r["vs_b3_domain_route"]["within_declared_tolerance"])
    assert misses == ["P9"], misses
    assert all(r.get("vs_committed_core_grid", {"within_declared_tolerance": True})["within_declared_tolerance"] for r in models.values())


def test_tcr_agrees_with_the_exact_posterior_in_both_designs():
    designs = _load("TCR.json")["designs"]
    for name in ("WIDE", "NARROW"):
        assert designs[name]["agreement"]["within_declared_tolerance"] is True, name
    assert designs["NARROW"]["router_given_the_41_node_grid"]["decision"] == "LOCAL_GAUSSIAN"
    assert designs["WIDE"]["router_given_the_41_node_grid"]["decision"] == "GRID_AS_SUPPLIED"


def test_every_adversarial_case_met_its_declared_expectation():
    cases = _load("FAILURE_CASES.json")
    assert cases["all_met"] is True
    assert {"strong_nonlinearity", "parameter_at_bound", "nearly_singular_jacobian", "mirror_mode", "multimodal_two_parameter",
            "log_parameterization_of_a_linear_model", "weak_identification", "thin_correlated_ridge_with_aliased_bounds_grid",
            "mapped_non_tensor_point_set"} <= set(cases["cases"])


def test_performance_labels_measured_and_projected_numbers():
    perf = _load("PERFORMANCE.json")
    assert set(perf["v2_measured"]) == {"2", "5", "10", "20", "41"}
    assert all(v["label"] == "MEASURED" for v in perf["v2_measured"].values())
    assert all("PROJECTED" in v["label"] for v in perf["v1_grid_projected"].values())
    assert all(v["diagnostics_and_jacobian_without_multistart"]["forward_evaluations"] == 4 * int(p) + 1 for p, v in perf["v2_measured"].items())


def test_the_hd_mutation_matrix_killed_everything_with_a_green_control():
    hd = _load("HD_MUTATIONS.json")
    assert hd["control"]["exit_code"] == 0
    assert len(hd["results"]) == 10 and all(r["verdict"] == "KILLED" for r in hd["results"].values())


def test_the_wheel_matches_both_frozen_surfaces_and_runs_the_route_isolated():
    wheel = _load("WHEEL_V2.json")
    assert wheel["v1_frozen_api_parity"] == "MATCH" and wheel["v2_frozen_api_parity"] == "MATCH"
    assert wheel["isolated_wheel_smoke"]["passed"] is True
    assert "engcore/hybrid_uq/router.py" in wheel["hybrid_uq_files_in_wheel"]


def test_k2_is_routed_and_its_errata_quantities_are_restated_against_converged_references():
    k2 = _load("KINETICS_K2.json")
    multi = k2["MULTI_v2"]
    assert multi["route"]["decision"] == "LOCAL_GAUSSIAN" and multi["route"]["claim"] == "SUPPORTED"
    assert multi["route"]["uniqueness"] == "MULTISTART_NO_SECOND_MODE"
    corrected = k2["CORRECTED"]
    assert corrected["reference_grids_converged"] is True
    assert abs(corrected["MULTI_determinant_v2"] / corrected["MULTI_determinant_reference"] - 1.0) < 0.01
    assert corrected["MULTI_determinant_reference"] > 50 * corrected["MULTI_determinant_committed"]
    for key, sd in corrected["C2_predictive_parameter_sd_v2"].items():
        assert abs(sd / corrected["C2_predictive_reference"][key]["parameter_sd"] - 1.0) < 0.01, key
    assert corrected["A5_passes_reference"] is True
    assert 50.0 < corrected["A5_gain_weak_over_multi_reference"] < 100.0
    assert k2["WEAK_C2_v2"]["decision"] == "REFUSED" and "NO_RESIDUAL_DEGREES_OF_FREEDOM" in k2["WEAK_C2_v2"]["reasons"]
    assert k2["parameterizations"]["natural_k0_identity"]["claim"] == "REFUSED"
