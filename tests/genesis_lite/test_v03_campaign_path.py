"""Genesis-lite v0.3 development campaign path (owner-approved 2026-10-28).

The v0.2 benchmark is byte-pinned by its preregistration (harness, evaluator and blindfold substrate files), so v0.3 is a
separate path in new files: the FDA-05 rule is applied to the escrow's signed pair facts, an independent v0.3 evaluator
reconciles with it, and the v0.2 identity stays exactly as committed.
"""

from __future__ import annotations

import pytest

from benchmarks.genesis_lite import harness as h2
from engcore.blindfold import EvaluatorConfig
from engcore.blindfold.roles import Adjudication

V0_2_CONFIG_DIGEST = "c545d486b5918f589a807c9ba82a839b7c9875a7d42f629e54f3f412e815b39a"
V0_2_PREREG_IDENTITY = "878e6812a825fc85dc1f181b323d9a1c7a630b55e346612ca73d6a5b4e696b64"


# ---- v0.2 stays exactly as committed -----------------------------------------------------------------------------------
def test_the_v0_2_identity_is_untouched():
    identity, changed = h2.code_identity()
    assert changed == [] and identity == V0_2_PREREG_IDENTITY
    assert h2.CONFIG.digest == V0_2_CONFIG_DIGEST


# ---- adjudication: the FDA-05 rule over the escrow's own pair facts -----------------------------------------------------
def _adjudication(kind, answer, outcome, credit, config, receipt="r" * 64, proposal="p" * 64):
    return Adjudication("u1", proposal, "q" * 64, kind, answer, outcome, credit, False, config.digest, receipt,
                        "label", "in_process")


def _body(pair, receipt="r" * 64, proposal="p" * 64, answer="indistinguishable"):
    return {"universe_id": "u1", "proposal_digest": proposal, "answer": answer, "pair": pair,
            "receipt": {"digest": receipt}, "rule": "v0_3"}


@pytest.mark.parametrize("kind,hit_credit", [("indistinguishable", 1.0), ("discoverable", -0.5), ("confounded", -1.0)])
def test_bracketing_only_is_unresolved_and_keeps_only_penalties(kind, hit_credit):
    from benchmarks.genesis_lite.adjudication_v3 import CONFIG_V3, adjudicate_v3
    a = _adjudication(kind, "indistinguishable", "indistinguishable_hit", hit_credit, CONFIG_V3)
    out = adjudicate_v3(a, _body({"hit": True, "contains_truth": False, "brackets_truth": True}), CONFIG_V3)
    assert out.outcome == "indistinguishable_unresolved"
    assert out.credit == min(0.0, hit_credit)


def test_a_pair_containing_the_truth_is_still_a_hit():
    from benchmarks.genesis_lite.adjudication_v3 import CONFIG_V3, adjudicate_v3
    a = _adjudication("indistinguishable", "indistinguishable", "indistinguishable_hit", 1.0, CONFIG_V3)
    out = adjudicate_v3(a, _body({"hit": True, "contains_truth": True, "brackets_truth": True}), CONFIG_V3)
    assert (out.outcome, out.credit) == ("indistinguishable_hit", 1.0)


def test_a_miss_and_non_pair_answers_are_unchanged():
    from benchmarks.genesis_lite.adjudication_v3 import CONFIG_V3, adjudicate_v3
    miss = _adjudication("indistinguishable", "indistinguishable", "indistinguishable_miss", -1.0, CONFIG_V3)
    assert adjudicate_v3(miss, _body({"hit": False, "contains_truth": False, "brackets_truth": True}), CONFIG_V3) == miss
    law = _adjudication("discoverable", "law", "law_pass", 1.0, CONFIG_V3)
    assert adjudicate_v3(law, _body(None, answer="law"), CONFIG_V3) == law


@pytest.mark.parametrize("body_change", [{"receipt": {"digest": "x" * 64}}, {"proposal_digest": "y" * 64},
                                         {"universe_id": "u2"}])
def test_the_escrow_facts_must_belong_to_the_adjudication(body_change):
    from benchmarks.genesis_lite.adjudication_v3 import CONFIG_V3, AdjudicationRefused, adjudicate_v3
    a = _adjudication("indistinguishable", "indistinguishable", "indistinguishable_hit", 1.0, CONFIG_V3)
    body = {**_body({"hit": True, "contains_truth": True, "brackets_truth": True}), **body_change}
    with pytest.raises(AdjudicationRefused):
        adjudicate_v3(a, body, CONFIG_V3)


def test_only_the_sealed_v0_3_config_adjudicates():
    from benchmarks.genesis_lite.adjudication_v3 import CONFIG_V3, AdjudicationRefused, adjudicate_v3
    assert CONFIG_V3.digest != V0_2_CONFIG_DIGEST
    a = _adjudication("indistinguishable", "indistinguishable", "indistinguishable_hit", 1.0, h2.CONFIG)
    with pytest.raises(AdjudicationRefused):
        adjudicate_v3(a, _body({"hit": True, "contains_truth": True, "brackets_truth": True}), h2.CONFIG)


# ---- the independent v0.3 evaluator reconciles with that adjudication ---------------------------------------------------
def _key():
    return {"universes": [{"universe_id": "u1"}]}


def test_the_v0_3_evaluator_refuses_another_credit_table():
    from benchmarks.genesis_lite.evaluator import score_v3
    with pytest.raises(score_v3.v2.EvaluatorRefused):
        score_v3.evaluate_campaign({"u1": {}}, _key(), {"u1": {}}, expected_credit_digest="0" * 64)


def test_the_v0_3_evaluator_flags_an_escrow_hit_it_finds_unresolved(monkeypatch):
    from benchmarks.genesis_lite.evaluator import score_v3
    mine = {"kind": "indistinguishable", "outcome": "indistinguishable_unresolved", "credit": 0.0, "fractions": [0.5, 0.5]}
    monkeypatch.setattr(score_v3, "score_universe", lambda proposal, entry: dict(mine))
    agreeing = {"u1": {"kind": "indistinguishable", "outcome": "indistinguishable_unresolved", "credit": 0.0,
                       "fractions": [0.5, 0.5]}}
    graded = score_v3.evaluate_campaign({"u1": {}}, _key(), agreeing, expected_credit_digest=score_v3.CREDIT_DIGEST)
    assert graded["status"] == "VALID" and graded["benchmark_id"] == score_v3.BENCHMARK_ID
    claimed_hit = {"u1": {**agreeing["u1"], "outcome": "indistinguishable_hit", "credit": 1.0}}
    graded = score_v3.evaluate_campaign({"u1": {}}, _key(), claimed_hit, expected_credit_digest=score_v3.CREDIT_DIGEST)
    assert graded["status"] == "EVALUATOR_DISAGREEMENT" and graded["disagreements"] == ["u1"]


def test_the_v0_3_evaluator_reports_a_key_mismatch():
    from benchmarks.genesis_lite.evaluator import score_v3
    graded = score_v3.evaluate_campaign({"u1": {}}, _key(), {"u9": {}}, expected_credit_digest=score_v3.CREDIT_DIGEST)
    assert graded["status"] == "KEY_MISMATCH"


# ---- end to end: one development campaign under the v0.3 identity -------------------------------------------------------
@pytest.mark.parametrize("arm_name", ["always_refuse", "extrapolation_pair"])
def test_a_v0_3_development_campaign_runs_valid_and_leaves_v0_2_untouched(arm_name):
    from benchmarks.genesis_lite import arms
    from benchmarks.genesis_lite.harness_v3 import CONFIG_V3, run_one_v3
    rec = run_one_v3(arm_name, arms.ARMS[arm_name][0], master_seed=bytes(range(32)), campaign_id="gl-v03-test",
                     presentation="anonymous")
    assert rec.status == "VALID", rec.reasons
    assert rec.evaluator_status == "VALID"
    assert rec.benchmark_id == "genesis_lite.blindfold_l5.v0_3" and rec.readiness == "DEVELOPMENT_ONLY"
    assert rec.config_digest == CONFIG_V3.digest and rec.prereg_sha256 == ""
    assert all(u["independent_agrees"] for u in rec.universes)
    assert h2.code_identity()[1] == []


def test_the_v0_3_path_refuses_the_v0_2_config():
    from benchmarks.genesis_lite import arms
    from benchmarks.genesis_lite.harness_v3 import run_one_v3
    rec = run_one_v3("always_refuse", arms.ARMS["always_refuse"][0], master_seed=bytes(range(32)),
                     campaign_id="gl-v03-test", presentation="anonymous", config=h2.CONFIG)
    assert rec.status == "INVALID_BENCHMARK"


def test_a_real_bracketing_only_pair_is_unresolved_end_to_end_and_the_evaluator_agrees():
    # found by a 600-campaign development probe (2026-10-28): world set 3, anonymous presentation
    from benchmarks.genesis_lite import arms
    from benchmarks.genesis_lite.harness_v3 import run_one_v3
    rec = run_one_v3("extrapolation_pair", arms.ARMS["extrapolation_pair"][0], master_seed=(3).to_bytes(4, "big") * 8,
                     campaign_id="gl-v03-probe-3", presentation="anonymous")
    assert rec.status == "VALID" and rec.evaluator_status == "VALID", rec.reasons
    unresolved = [u for u in rec.universes if u["outcome"] == "indistinguishable_unresolved"]
    assert unresolved and all(u["independent_agrees"] and u["credit"] <= 0.0 for u in unresolved)


# ---- review of cb1dfe44 (2026-10-29): the rule is observed, not asserted -------------------------------------------------
@pytest.mark.parametrize("rule", [None, "v0_2"])
def test_a_score_body_not_scored_under_the_v0_3_rule_is_refused(rule):
    from benchmarks.genesis_lite.adjudication_v3 import CONFIG_V3, AdjudicationRefused, adjudicate_v3
    a = _adjudication("indistinguishable", "indistinguishable", "indistinguishable_hit", 1.0, CONFIG_V3)
    body = _body({"hit": True, "contains_truth": True, "brackets_truth": True})
    if rule is None:
        body.pop("rule")
    else:
        body["rule"] = rule
    with pytest.raises(AdjudicationRefused, match="rule"):
        adjudicate_v3(a, body, CONFIG_V3)


def test_the_v0_3_path_on_a_v0_2_escrow_is_invalid_not_relabelled(monkeypatch):
    from benchmarks.genesis_lite import arms, harness_v3
    from engcore.blindfold import EscrowService
    monkeypatch.setattr(harness_v3, "EscrowServiceV3", EscrowService)
    rec = harness_v3.run_one_v3("extrapolation_pair", arms.ARMS["extrapolation_pair"][0],
                                master_seed=(3).to_bytes(4, "big") * 8, campaign_id="gl-v03-probe-3",
                                presentation="anonymous")
    # the world set of this campaign id has scored pair answers (a refusal-only campaign scores no law)
    assert rec.status == "INVALID_BENCHMARK" and rec.escrow_rule != "v0_3"


def test_the_record_states_what_evaluator_agreement_does_and_does_not_check():
    from benchmarks.genesis_lite import arms
    from benchmarks.genesis_lite.harness_v3 import run_one_v3
    rec = run_one_v3("always_refuse", arms.ARMS["always_refuse"][0], master_seed=bytes(range(32)),
                     campaign_id="gl-v03-scope", presentation="anonymous")
    assert "interpreter" in rec.agreement_scope and "not the rule semantics" in rec.agreement_scope


def test_the_v0_3_escrow_refuses_persistent_storage_until_the_rule_is_journaled():
    from engcore.blindfold.escrow import EscrowRefused
    from engcore.blindfold.escrow_v3 import EscrowServiceV3
    with pytest.raises(EscrowRefused, match="storage"):
        EscrowServiceV3(storage=object())
