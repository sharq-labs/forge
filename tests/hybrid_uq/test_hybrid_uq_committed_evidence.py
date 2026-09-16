"""Static guards over the committed Core V2 evidence: the claims the round report makes are the ones the records hold.

These read JSON only; the runs themselves are benchmarks/core_v2_hybrid_uq/audit/*.py.

Audit stream "hybrid" (HUQ-01..14) changed what the V2 route will stand behind. The evidence that is cheap to
reproduce -- TCR.json, FAILURE_CASES.json, PERFORMANCE.json, WHEEL_V2.json -- was regenerated under the new rules and
these guards read the regenerated records. BATTERY_T41.json and KINETICS_K2.json were NOT regenerated (their full
runs are long multistart refits); their bytes are frozen as written, and the tests that asserted they are current now
assert, instead, that each carries a SUPERSEDED marker naming its exact bytes and the rules that changed. A record
that no longer reproduces must not be readable as a current claim.
"""

from __future__ import annotations

import hashlib
import json
import pathlib

import pytest

ROUND = pathlib.Path(__file__).resolve().parents[2] / "benchmarks" / "core_v2_hybrid_uq"
SUPERSEDED_STATUS = "superseded, not regenerated"


def _load(name):
    path = ROUND / name
    if not path.exists():
        pytest.fail(f"{name} is missing from {ROUND}")
    return json.loads(path.read_text(encoding="utf-8"))


def _superseded(name):
    """The marker beside an evidence file that was not regenerated, checked against the file's own bytes."""
    stem = name.rsplit(".", 1)[0]
    marker = _load(f"{stem}.SUPERSEDED.json")
    assert (ROUND / f"{stem}.SUPERSEDED.md").exists(), f"{stem}.SUPERSEDED.md is missing"
    assert marker["file"] == f"benchmarks/core_v2_hybrid_uq/{name}"
    assert marker["status"] == SUPERSEDED_STATUS
    assert marker["sha256"] == hashlib.sha256((ROUND / name).read_bytes()).hexdigest(), \
        f"{name} changed after it was marked superseded; regenerate it or re-mark it"
    return marker


def test_the_battery_t41_record_is_marked_superseded_by_the_minimum_multistart_rule():
    """Was: T41 LOCAL_GAUSSIAN SUPPORTED with MULTISTART_NO_SECOND_MODE, asserted as current. Under HUQ-01 the default
    6-start policy is below the minimum search for every model with p >= 3 (84 starts for T41), so that claim no longer
    reproduces; the test now asserts the marker, and that the frozen bytes still say what they said."""
    marker = _superseded("BATTERY_T41.json")
    assert "HUQ-01" in {rule["id"] for rule in marker["rules_changed"]}
    t41_now = marker["now_would_say"]["T41"]
    assert t41_now["claim"] == "DOWNGRADED" and "MULTISTART_INCOMPLETE" in t41_now["reasons"]
    t41 = _load("BATTERY_T41.json")["models"]["T41"]
    assert t41["claim"] == "SUPPORTED" and t41["uniqueness"] == "MULTISTART_NO_SECOND_MODE"
    # what the audited rules do not change, kept from the original guard: routed without a grid, the covariance within
    # the declared tolerance of B3's exact route, identifiability of identity-declared voltages, the three sources
    assert t41["p"] == 41 and t41["decision"] == "LOCAL_GAUSSIAN"
    assert t41["considered"][0]["reason"] == "GRID_NOT_SUPPLIED"
    assert t41["vs_b3_domain_route"]["within_declared_tolerance"] is True
    assert t41["identifiability"]["knot_or_node_voltages"] == "PARAMETERS_IDENTIFIABLE"
    assert t41["identifiability"]["successive_differences"] == "PARAMETERS_NOT_IDENTIFIABLE"
    assert t41["predictive"]["sources"] == ["PARAMETER_UNCERTAINTY", "MEASUREMENT_UNCERTAINTY", "MODEL_DISCREPANCY_NOT_MODELLED"]


def test_the_battery_models_that_miss_their_tolerance_are_still_named_in_the_historical_record():
    """The tolerance comparison is about the covariance, which the audited rules do not change; the claim beside it is
    superseded (see the marker)."""
    _superseded("BATTERY_T41.json")
    models = _load("BATTERY_T41.json")["models"]
    misses = sorted(m for m, r in models.items() if not r["vs_b3_domain_route"]["within_declared_tolerance"])
    assert misses == ["P9"], misses
    assert all(r.get("vs_committed_core_grid", {"within_declared_tolerance": True})["within_declared_tolerance"] for r in models.values())


def test_tcr_agrees_with_the_exact_posterior_in_both_designs():
    designs = _load("TCR.json")["designs"]
    for name in ("WIDE", "NARROW"):
        assert designs[name]["agreement"]["within_declared_tolerance"] is True, name
        # regenerated under HUQ-01/07/08: p = 2 with the canonical 6-start policy is at the minimum search, and the
        # diagonal probes keep the nonlinearity below the downgrade threshold
        assert designs[name]["v2_local"]["claim"] == "SUPPORTED", name
        assert designs[name]["v2_local"]["nonlinearity_index"] < 0.10, name
    assert designs["NARROW"]["router_given_the_41_node_grid"]["decision"] == "LOCAL_GAUSSIAN"
    assert designs["WIDE"]["router_given_the_41_node_grid"]["decision"] == "GRID_AS_SUPPLIED"


def test_every_adversarial_case_met_its_declared_expectation():
    cases = _load("FAILURE_CASES.json")
    assert cases["all_met"] is True
    assert {"strong_nonlinearity", "parameter_at_bound", "nearly_singular_jacobian", "mirror_mode", "multimodal_two_parameter",
            "log_parameterization_of_a_linear_model", "weak_identification", "thin_correlated_ridge_with_aliased_bounds_grid",
            "mapped_non_tensor_point_set"} <= set(cases["cases"])
    # regenerated under HUQ-06: a grid over other parameters is refused outright when routed with a calibration
    mapped = cases["cases"]["mapped_non_tensor_point_set"]
    assert mapped["router_with_local_other_parameter_names"].startswith("HybridUQError")


def test_performance_labels_measured_and_projected_numbers():
    perf = _load("PERFORMANCE.json")
    assert set(perf["v2_measured"]) == {"2", "5", "10", "20", "41"}
    assert all(v["label"] == "MEASURED" for v in perf["v2_measured"].values())
    assert all("PROJECTED" in v["label"] for v in perf["v1_grid_projected"].values())


def test_performance_counts_the_audited_diagnostics_and_claims():
    """This asserted forward_evaluations == 4p + 1 before audit HUQ-08, a count that stopped being true when the
    Jacobian became convergence-checked (at least 4p + 1) and the chi-square probes became 2p^2: the diagnostics are
    O(p^2). Under HUQ-01 the default 6-start multistart is below the minimum search for p >= 3."""
    for p, v in _load("PERFORMANCE.json")["v2_measured"].items():
        p = int(p)
        diagnostics = v["diagnostics_and_jacobian_without_multistart"]
        assert diagnostics["forward_evaluations"] == diagnostics["route_recorded_evaluations"], p
        evaluated_probes = 2 * p * p - diagnostics["chi_square_probes_skipped"]
        assert diagnostics["forward_evaluations"] >= 4 * p + 1 + evaluated_probes, p
        assert v["claim_without_multistart"] != "SUPPORTED", p
        if p >= 3:
            assert v["claim"] != "SUPPORTED" and "MULTISTART_INCOMPLETE" in v["reasons_with_default_multistart"], p


def test_performance_records_that_the_coarse_knot_models_do_not_fit_the_b3_data():
    """Scientific core audit 2026-09-16, CORE-001, first measured on real evidence.

    The same uniform-knot LINEAR family on B3's calibration data: with 2, 5 and 10 knots the residuals are 24x, 13x and
    4.6x the declared noise variance, so the route refuses and emits no covariance. Before the goodness-of-fit rule these
    routes reported covariances built from a declared sigma the residuals contradict. With 20 and 41 knots the fit is
    within the declared noise and only the multistart minimum caps the claim. The V1 grid part of this record still
    reads PARAMETERS_IDENTIFIABLE at p = 2..4: the frozen V1 ``assess_identifiability`` takes no observations and applies
    no goodness of fit, which is why only the routed (V2) claims are held to it.
    """
    measured = _load("PERFORMANCE.json")["v2_measured"]
    for p in ("2", "5", "10"):
        v = measured[p]
        assert v["claim"] == "REFUSED" and "MODEL_MISFIT_BEYOND_DECLARED_NOISE" in v["reasons_with_default_multistart"], p
        assert v["goodness_of_fit"]["variance_ratio"] > 4.0, p
        assert "not_incurred" in v["linearized_predictive"], p
    for p in ("20", "41"):
        v = measured[p]
        assert v["claim"] == "DOWNGRADED" and v["goodness_of_fit"]["variance_ratio"] < 1.0, p
        assert not {"MODEL_MISFIT_BEYOND_DECLARED_NOISE", "RESIDUALS_EXCEED_DECLARED_NOISE"} & set(v["reasons_with_default_multistart"]), p


def test_the_hd_mutation_matrix_killed_everything_with_a_green_control():
    hd = _load("HD_MUTATIONS.json")
    assert hd["control"]["exit_code"] == 0
    assert len(hd["results"]) == 10 and all(r["verdict"] == "KILLED" for r in hd["results"].values())


def test_the_wheel_matches_both_frozen_surfaces_and_runs_the_route_isolated():
    wheel = _load("WHEEL_V2.json")
    assert wheel["v1_frozen_api_parity"] == "MATCH" and wheel["v2_frozen_api_parity"] == "MATCH"
    assert wheel["isolated_wheel_smoke"]["passed"] is True
    assert "engcore/hybrid_uq/router.py" in wheel["hybrid_uq_files_in_wheel"]


def test_the_k2_record_is_marked_superseded_and_its_errata_quantities_still_read_from_it():
    """Was: K2 MULTI routed LOCAL_GAUSSIAN SUPPORTED with MULTISTART_NO_SECOND_MODE, asserted as current. That claim was
    established with axis-only probes and total-sd predictive scaling (HUQ-07/08/11) and is superseded, not regenerated
    (the MULTI multistart alone is ~76 min of CSTR solves). The corrected covariance, determinant and predictive sd are
    properties of the covariance at the estimate, which the audited rules do not change, so the errata restatement
    still reads from the frozen record."""
    marker = _superseded("KINETICS_K2.json")
    assert {"HUQ-07", "HUQ-08", "HUQ-11"} <= {rule["id"] for rule in marker["rules_changed"]}
    k2 = _load("KINETICS_K2.json")
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
