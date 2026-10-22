"""Failing-first tests of the v3 evaluation rules (written before stats.py, truth.py, diagnostics.py, conclusion.py).

Every test uses hand-built instance records or synthetic data only; no real pack is read and no truth is computed.
"""

from __future__ import annotations

import math

import pytest

from benchmarks.battery_rediscovery_v3.evaluator import conclusion as cr
from benchmarks.battery_rediscovery_v3.evaluator import diagnostics as dg
from benchmarks.battery_rediscovery_v3.evaluator import stats
from benchmarks.battery_rediscovery_v3.evaluator import truth as tr

S, NS, NA = "SUPPORTED", "NOT_SUPPORTED", "NOT_ASSESSABLE"
OLD, REPR, ROLES, COMB, CAREFUL = cr.OLD, cr.REPR, cr.ROLES, cr.COMB, cr.CAREFUL


# ---- stats ------------------------------------------------------------------------------------------------------------
def test_wilson_interval_known_values():
    lo, hi = stats.wilson(8, 10)
    assert lo == pytest.approx(0.4902, abs=2e-4) and hi == pytest.approx(0.9433, abs=2e-4)
    assert stats.wilson(0, 0) == (None, None)
    lo, hi = stats.wilson(0, 5)
    assert lo == 0.0 and 0 < hi < 1


def test_sign_test_two_sided_exact():
    assert stats.sign_test(0, 0) == 1.0
    assert stats.sign_test(6, 0) == pytest.approx(2 / 64)
    assert stats.sign_test(5, 0) == pytest.approx(2 / 32)
    assert stats.sign_test(3, 3) == 1.0
    assert stats.sign_test(9, 1) == pytest.approx(2 * (1 + 10) / 1024)


# ---- the A/B truth agreement ------------------------------------------------------------------------------------------
def test_agreeing_references_decide_and_disagreeing_ones_unscore():
    e = tr.combine_axis("MODEL_ADEQUACY", {"truth": S}, {"truth": S})
    assert e["truth"] == S and e["agreement"] and not e["implementation_correlated"]
    e = tr.combine_axis("MODEL_ADEQUACY", {"truth": S}, {"truth": NS})
    assert e["truth"] is None and e["basis_kind"] == "REFERENCE_DISAGREEMENT"
    e = tr.combine_axis("MODEL_ADEQUACY", {"truth": None}, {"truth": S})
    assert e["truth"] is None


def test_classifier_decided_identifiability_is_implementation_correlated():
    e = tr.combine_axis("IDENTIFIABILITY", {"truth": S}, {"truth": S, "classifier_shared": True, "near_structural": False,
                                                          "ambiguous": False})
    assert e["truth"] == S and e["implementation_correlated"]
    e = tr.combine_axis("IDENTIFIABILITY", {"truth": NS}, {"truth": NS, "classifier_shared": False,
                                                           "near_structural": True, "ambiguous": False})
    assert e["truth"] == NS and not e["implementation_correlated"]


def test_structural_not_assessable_is_a_declaration():
    e = tr.combine_axis("CROSS_CELL_TRANSFER", {"truth": NA, "basis": "no set supplied"},
                        {"truth": NA, "basis": "no set supplied"})
    assert e["truth"] == NA and e["basis_kind"] == "STRUCTURAL_DECLARATION"


# ---- degeneracy dimensions --------------------------------------------------------------------------------------------
def _b_diag(**kw):
    base = {"parameters": {"R0": 0.02, "R1": 0.01, "C1": 3000.0}, "tau": 30.0, "sse": 1.0,
            "bounds": {"R0": [0.001, 0.2], "R1": [0.0001, 0.2], "C1": [1.0, 1e6]},
            "profile": {"ln_tau_span_within_1pct": 0.2, "refined_minima": []},
            "information": {"singular": False, "reduced_singular": False, "unconstrained": [],
                            "requested_unconstrained": [], "condition_number": 10.0, "max_abs_correlation": 0.5},
            "horizon_s": 3900.0, "median_dt_s": 1.0}
    base.update(kw)
    return base


def _a_diag(cost=0.5, status=1, starts=()):
    return {"cost": cost, "parameters": {"R0": 0.02, "R1": 0.01, "C1": 3000.0},
            "starts_detail": list(starts), "best_status": status}


def test_clean_fit_has_no_degeneracy_flags():
    d = dg.evidence_dimensions(_a_diag(), _b_diag(), {"IDENTIFIABILITY": {"truth": NA}, "MODEL_DISCREPANCY": {"truth": NA}},
                               requested=("R0", "R1", "C1"))
    assert d["FIT_OK"]["value"] == "YES"
    assert d["PARAMETER_DEGENERACY"]["value"] == "NO"
    assert d["IDENTIFIABILITY_LIMIT"]["value"] == "NOT_ESTABLISHED_NO_SIGMA"
    assert d["MODEL_DISCREPANCY"]["value"] == NA


def test_bound_pinned_and_extreme_tau_are_degenerate_even_with_a_good_fit():
    b = _b_diag(parameters={"R0": 0.02, "R1": 0.2, "C1": 26000.0}, tau=5200.0, horizon_s=3900.0)
    d = dg.evidence_dimensions(_a_diag(), b, {"IDENTIFIABILITY": {"truth": NA}, "MODEL_DISCREPANCY": {"truth": NA}},
                               requested=("R0", "R1", "C1"))
    flags = d["PARAMETER_DEGENERACY"]["flags"]
    assert d["PARAMETER_DEGENERACY"]["value"] == "YES"
    assert "PINNED_TO_BOUND:R1" in flags and "TAU_EXCEEDS_HORIZON" in flags


def test_flat_profile_and_ill_conditioning_are_flagged_separately():
    b = _b_diag(profile={"ln_tau_span_within_1pct": 3.0, "refined_minima": []},
                information={"singular": False, "reduced_singular": False, "unconstrained": ["ocv_k0"],
                             "requested_unconstrained": [], "condition_number": 5e6, "max_abs_correlation": 0.99})
    d = dg.evidence_dimensions(_a_diag(), b, {"IDENTIFIABILITY": {"truth": NA}, "MODEL_DISCREPANCY": {"truth": NA}},
                               requested=("R0", "R1", "C1"))
    assert "EQUIVALENT_TAU_SET" in d["PARAMETER_DEGENERACY"]["flags"]
    assert d["IDENTIFIABILITY_LIMIT"]["value"] == "YES"
    assert {"ILL_CONDITIONED", "HIGH_CORRELATION"} <= set(d["IDENTIFIABILITY_LIMIT"]["flags"])
    assert d["PARAMETER_DEGENERACY"]["unconstrained_nuisance"] == ["ocv_k0"]


def test_reference_cost_disagreement_is_not_fit_ok():
    d = dg.evidence_dimensions(_a_diag(cost=0.6), _b_diag(sse=1.0), {"IDENTIFIABILITY": {"truth": NA},
                                                                     "MODEL_DISCREPANCY": {"truth": NA}},
                               requested=("R0", "R1", "C1"))
    assert d["FIT_OK"]["value"] == "NO"


def test_candidate_degeneracy_reads_the_sealed_parameter_set():
    pset = [{"name": "R0", "estimate": 0.1, "low": 1e-4, "high": 1.0}, {"name": "R1", "estimate": 1.0, "low": 1e-5, "high": 1.0},
            {"name": "C1", "estimate": 5000.0, "low": 1.0, "high": 1e6}]
    c = dg.candidate_degeneracy(pset, horizon_s=3000.0, median_dt_s=10.0)
    assert c["value"] == "YES" and "PINNED_TO_BOUND:R1" in c["flags"] and "TAU_EXCEEDS_HORIZON" in c["flags"]
    assert dg.candidate_degeneracy(None, horizon_s=1.0, median_dt_s=1.0)["value"] == "NOT_AVAILABLE"


# ---- the conclusion rule and the single-instance robustness check -----------------------------------------------------
def _inst(key, truth, heldout, answers):
    return {"key": key, "truth": truth, "heldout": heldout, "answers": answers}


def _all(comb, old=NA, repr_=NA, roles=NA, careful=None):
    return {OLD: old, REPR: repr_, ROLES: roles, COMB: comb, CAREFUL: comb if careful is None else careful}


def _strong(n_cal=14, n_ho=14):
    out = [_inst(f"P{k:02d}/MODEL_ADEQUACY", S if k % 2 else NS, False, _all(S if k % 2 else NS)) for k in range(n_cal)]
    out += [_inst(f"H{k:02d}/WITHIN_CELL_GENERALIZATION", S if k % 3 else NS, True, _all(S if k % 3 else NS))
            for k in range(n_ho)]
    out += [_inst(f"R{k:02d}/MODEL_DISCREPANCY", NA, False, _all(NA)) for k in range(6)]
    return out


GATES = {"seal_ok": True, "leakage_ok": True, "replay_exact": True, "reference_disagreement_fraction": 0.0}


def test_strong_robust_advantage_confirms():
    c = cr.conclude(instances=_strong(), **GATES)
    assert c["verdict"] == "GEN1_REAL_DATA_ADVANTAGE_CONFIRMED", c["why"]
    assert c["robustness"]["robust"] is True
    assert c["hypotheses"]["H4"]["holds"] is True


def test_a_thin_advantage_that_one_instance_reverses_is_underpowered():
    inst = _strong(n_cal=3, n_ho=10)
    # make the paired comparison rest on few discordant pairs: OLD correct on most decided instances
    for x in inst[:-6]:
        x["answers"][OLD] = x["truth"]
    for x in inst[3:9]:
        x["answers"][OLD] = NA
    c = cr.conclude(instances=inst, **GATES)
    assert c["criteria"]["C1_primary_comparison"]["holds"] is True
    assert c["verdict"] == "BENCHMARK_UNDERPOWERED", c["why"]
    assert c["robustness"]["breaking"], "a breaking perturbation must be named"


def test_false_support_increase_blocks_confirmation():
    inst = _strong()
    for x in inst[:4]:
        if x["truth"] == NS:
            x["answers"][COMB] = S
    c = cr.conclude(instances=inst, **GATES)
    assert c["criteria"]["C2_false_support_not_material"]["holds"] is False
    assert c["verdict"] != "GEN1_REAL_DATA_ADVANTAGE_CONFIRMED"


def test_gates_are_checked_first():
    assert cr.conclude(instances=_strong(), **{**GATES, "leakage_ok": False})["verdict"] == "LEAKAGE_INVALIDATED"
    assert cr.conclude(instances=_strong(), **{**GATES, "replay_exact": False})["verdict"] == "INCONCLUSIVE"
    assert cr.conclude(instances=_strong(n_cal=4, n_ho=4), **GATES)["verdict"] == "TRUTH_INSUFFICIENT"
    assert cr.conclude(instances=_strong(), **{**GATES, "reference_disagreement_fraction": 0.5})["verdict"] == "TRUTH_INSUFFICIENT"


def test_no_advantage_when_combined_equals_old():
    inst = _strong()
    for x in inst:
        x["answers"][OLD] = x["answers"][COMB]
        x["answers"][REPR] = x["answers"][COMB]
        x["answers"][ROLES] = x["answers"][COMB]
    c = cr.conclude(instances=inst, **GATES)
    assert c["verdict"] == "NO_GEN1_REAL_DATA_ADVANTAGE", c["why"]


def test_verdict_vocabulary_is_exactly_the_preregistered_one():
    assert set(cr.VERDICTS) == {"GEN1_REAL_DATA_ADVANTAGE_CONFIRMED", "GEN1_REAL_DATA_ADVANTAGE_PARTIAL",
                                "NO_GEN1_REAL_DATA_ADVANTAGE", "BENCHMARK_UNDERPOWERED", "TRUTH_INSUFFICIENT",
                                "LEAKAGE_INVALIDATED", "INCONCLUSIVE"}


def test_report_has_per_arm_statistics_and_paired_counts():
    c = cr.conclude(instances=_strong(), **GATES)
    s = c["statistics"][COMB]
    for k in ("decided_n", "correct_n", "incorrect_n", "false_support_n", "false_refuse_n", "unassessable_n",
              "unscored_n", "by_axis", "correct_decided_wilson95"):
        assert k in s
    p = c["paired"][COMB]
    assert set(p) == {"vs_OLD_MIND", "vs_CAREFUL_BASELINE"} and set(p["vs_OLD_MIND"]) == {"win", "loss", "tie", "p_sign"}
    assert not math.isnan(p["vs_OLD_MIND"]["p_sign"])
