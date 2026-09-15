"""Core Gap Review 2 (thin-ridge resolution): the committed measurements say what the review claims."""

from __future__ import annotations

import json
import math
import pathlib

import pytest

ROUND = pathlib.Path(__file__).resolve().parents[1]


def _json(name):
    return json.loads((ROUND / name).read_text(encoding="utf-8"))


# ---- Phase 1 -------------------------------------------------------------------

def test_grid_stable_but_wrong_is_proven_on_the_exact_hd_uq_case():
    p1 = _json("PHASE1_REPRODUCTION.json")
    assert p1["GRID_STABLE_BUT_WRONG"] == {"stable_under_refinement": True, "all_accepted_by_guard": True,
                                           "all_materially_wrong": True, "occurs": True}
    ref = p1["trusted_reference"]
    quad = ref["independent_quadrature_in_principal_coordinates_truncated_to_box"]
    assert all(abs(a - b) < 1e-9 for a, b in zip(ref["analytic_gaussian"]["mean"], quad["mean"]))
    assert ref["principal_axes"]["condition_number"] > 1e7


def test_the_grid_error_is_false_precision_and_the_windowed_grid_is_right_in_its_marginals():
    rows = _json("PHASE1_REPRODUCTION.json")["grids"]
    bounds = [r for r in rows if r["window"] == "declared_bounds"]
    assert all(r["comparison"]["false_precision"] and r["comparison"]["max_mean_error_in_true_sd"] > 1.0 for r in bounds)
    windowed = [r for r in rows if r["window"] == "estimate_pm_6_marginal_sd"]
    assert all(not r["comparison"]["material"] for r in windowed)


def test_a_diagonal_half_step_offset_reproduces_the_same_wrong_answer():
    rows = _json("PHASE1_REPRODUCTION.json")["grids"]
    for per in (201, 401, 801):
        base = next(r for r in rows if r["per_axis"] == per and r["window"] == "declared_bounds")
        off = next(r for r in rows if r["per_axis"] == per and r["window"] == "declared_bounds_offset_half_step")
        assert all(abs(a - b) < 1e-6 for a, b in zip(base["grid_mean"], off["grid_mean"]))


def test_the_aliasing_number_from_the_grids_own_log_likelihood_matches_the_true_covariance():
    p1 = _json("PHASE1_REPRODUCTION.json")
    d = p1["candidates_on_declared_bounds_801"]["D"]["value"]
    assert d == pytest.approx(p1["aliasing_number_with_true_sigma"], rel=1e-6) and d < 1


# ---- Phase 3 -------------------------------------------------------------------

def test_the_current_guard_falsely_accepts_and_candidate_d_never_does():
    fam = _json("PHASE3_FAMILY.json")
    conf = fam["candidate_confusion"]
    assert conf["declared:GUARD"]["false_negative"] > 0 and conf["post_hoc_thin:GUARD"]["false_negative"] > 100
    assert conf["declared:D"]["false_negative"] == 0 and conf["post_hoc_thin:D"]["false_negative"] == 0
    assert conf["post_hoc_thin:F"]["false_negative"] > conf["post_hoc_thin:GUARD"]["false_negative"]


def test_failures_need_an_oblique_ridge():
    rows = [r for r in _json("PHASE3_FAMILY.json")["rows"] if r["family"] == "rotation"]
    for r in rows:
        if r["angle_deg"] in (0.0, 90.0):
            assert r["classification_post_hoc_thin"] == "A_CORRECT_ACCEPT"


# ---- Phase 4 -------------------------------------------------------------------

def test_the_guard_accepts_every_parameterization_while_candidate_d_refuses_every_one():
    systems = _json("PHASE4_PARAMETERIZATION.json")["systems"]
    assert {s["guard"]["verdict"] for s in systems.values()} == {"ACCEPT"}
    assert all(s["candidates"]["D"]["flag"] for s in systems.values())
    assert systems["original"]["classification"] == "C_FALSE_ACCEPT"
    assert systems["principal_axes_rotated"]["classification"] == "A_CORRECT_ACCEPT"
    assert systems["principal_axes_rotated"]["classification_post_hoc_thin"] == "C_FALSE_ACCEPT"


# ---- Phase 6 -------------------------------------------------------------------

def test_healthy_existing_grids_pass_candidate_d():
    cases = _json("PHASE6_REGRESSION.json")["cases"]
    for name in ("TCR_WIDE", "BATTERY_P2", "BATTERY_P3"):
        assert cases[name]["guard"]["verdict"] == "ACCEPT"
        assert cases[name]["candidates"]["D"]["flag"] is False, name


def test_the_existing_k2_scored_grid_is_reproduced_and_is_thin_direction_aliased():
    doc = _json("PHASE6_REGRESSION.json")
    k2 = doc["cases"]["KINETICS_K2_MULTI"]
    assert k2["reproduces_k2_report"] is True and doc["cases"]["KINETICS_K2_WEAK_C2"]["reproduces_k2_report"] is True
    assert k2["guard"]["verdict"] == "ACCEPT" and k2["guard"]["effective_sample_size"] < 2
    assert k2["candidates"]["D"]["flag"] is True
    assert k2["thin_direction_vs_local_gaussian_proxy"]["ratio_grid_over_proxy"] < 0.2
    c2 = doc["predictive_impact_of_thin_direction"]["KINETICS_K2_MULTI"]["observables"]["C2:C_A:final"]
    assert c2["ratio"] < 0.2


def test_the_tcr_narrow_fixture_grid_is_right_in_marginals_and_wrong_in_its_thin_direction():
    doc = _json("PHASE6_REGRESSION.json")
    t = doc["tcr_thin_direction_truth"]["TCR_NARROW"]
    assert t["frozen_41x41_grid_vs_truth"]["material"] is False
    assert t["frozen_41x41_grid_vs_truth"]["post_hoc_thin_direction"]["sd_ratio_grid_over_true"] < 0.8
    assert t["D_flag"] is True
    assert doc["tcr_thin_direction_truth"]["TCR_WIDE"]["D_flag"] is False
    assert doc["predictive_impact_of_thin_direction"]["TCR_NARROW"]["ratio"] < 0.8


def test_scale_dependent_candidates_raise_a_false_alarm_on_a_healthy_grid():
    wide = _json("PHASE6_REGRESSION.json")["cases"]["TCR_WIDE"]["candidates"]
    assert wide["A"]["flag"] and wide["B"]["flag"] and wide["C"]["flag"]
    assert not wide["D"]["flag"] and not wide["E"]["flag"]
