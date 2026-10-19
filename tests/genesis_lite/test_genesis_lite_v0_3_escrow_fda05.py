"""FDA-05, escrow half (certified ``engcore.blindfold.pair_bound``; UNCERTIFIED until OD-3), and the v0.3 harness end to
end. Synthetic worlds only (the R-05 construction in ``v0_3/selfcheck.py``; generator seeds named here)."""

from __future__ import annotations

import hashlib
import json

import pytest

from benchmarks.genesis_lite import harness as v02_harness
from benchmarks.genesis_lite import pilot
from benchmarks.genesis_lite.evaluator.expr import value
from benchmarks.genesis_lite.v0_3 import environment, harness, readiness, selfcheck
from benchmarks.genesis_lite.v0_3 import evaluator as v03e
from benchmarks.genesis_lite.v0_3 import preregistration as v03p
from engcore.blindfold import escrow
from engcore.blindfold import pair_bound as pb
from engcore.blindfold.roles import EvaluatorConfig

MASTER = bytes(range(32))
TEST_BOUND = v03e.PairBound("tol_multiple", 5.0)
#: the v0.2 escrow configuration digest at origin/main 8ec97064 (harness.CONFIG); it must not move
V0_2_CONFIG_DIGEST = EvaluatorConfig("forge.genesis_lite.v0_2", "1").digest


def _assess(pair_name, truth=selfcheck.T_UP, alternative=selfcheck.T_DOWN, bound=None):
    laws = selfcheck.PAIRS[pair_name]
    truths = [(p, value(truth, p)) for p in selfcheck.EVAL_PTS]
    inbox = [(p, value(truth, p)) for p in selfcheck.INBOX_PTS]
    world = selfcheck._world(truth, alternative)
    if bound is None:
        return escrow._assess_pair(laws, truths, inbox, world)
    return pb.assess_pair_bounded(laws, truths, inbox, world, bound)


def test_escrow_fda05_v0_2_escrow_credits_the_vacuous_pair_for_both_truths():
    """Pinned defect (escrow._assess_pair is unchanged): R-05 reproduced in the escrow."""
    for truth, alt in ((selfcheck.T_UP, selfcheck.T_DOWN), (selfcheck.T_DOWN, selfcheck.T_UP)):
        assert _assess("vacuous", truth, alt)["hit"] is True


@pytest.mark.parametrize("bound", [pb.PairBound("tol_multiple", 5.0), pb.PairBound("absolute", 1.0),
                                   pb.PairBound("absolute", 1e6)])
def test_escrow_fda05_the_bounded_escrow_misses_the_vacuous_pair_for_both_truths(bound):
    for truth, alt in ((selfcheck.T_UP, selfcheck.T_DOWN), (selfcheck.T_DOWN, selfcheck.T_UP)):
        got = _assess("vacuous", truth, alt, bound)
        assert got["hit"] is False and got["unbounded_hit"] is True and got["pair_bound"] == bound.to_dict()


def test_escrow_fda05_controls_honest_hits_inbox_disagreement_misses_narrow_bracket_follows_w():
    assert _assess("honest", bound=pb.PairBound("tol_multiple", 0.5))["hit"] is True
    assert _assess("inbox_disagree", bound=pb.PairBound("absolute", 1e6))["hit"] is False
    assert _assess("narrow_0.1", bound=pb.PairBound("absolute", 0.25))["hit"] is True
    assert _assess("narrow_0.1", bound=pb.PairBound("absolute", 0.15))["hit"] is False


def test_escrow_fda05_evaluator_and_escrow_agree_on_every_selfcheck_case():
    cases = selfcheck.compare(pb)
    assert len(cases) == 2 * len(selfcheck.PAIRS) * len(selfcheck.BOUNDS)
    assert [c for c in cases if not c["agree"]] == []
    assert any(c["escrow_unbounded_hit"] and not c["escrow_hit"] for c in cases)      # the bound bites somewhere


def test_escrow_fda05_the_config_digest_seals_w_and_v0_2_is_unchanged():
    a = pb.BoundedEvaluatorConfig("forge.genesis_lite.v0_3", "1", pair_bound=pb.PairBound("tol_multiple", 5.0))
    b = pb.BoundedEvaluatorConfig("forge.genesis_lite.v0_3", "1", pair_bound=pb.PairBound("tol_multiple", 6.0))
    assert a.digest != b.digest and a.to_dict()["pair_bound"] == {"form": "tol_multiple", "value": 5.0}
    assert v02_harness.CONFIG.digest == V0_2_CONFIG_DIGEST
    with pytest.raises(escrow.EscrowRefused):
        pb.BoundedEvaluatorConfig("forge.genesis_lite.v0_3", "1")
    for bad in (("log_width", 1.0), ("absolute", 0.0), ("absolute", float("nan"))):
        with pytest.raises(escrow.EscrowRefused):
            pb.PairBound(*bad)


def test_escrow_fda05_v0_2_identity_is_untouched_by_the_escrow_half():
    assert v02_harness.code_identity()[1] == []
    assert pilot.prereg_matches_code()[0] is True


def test_escrow_fda05_the_bounded_escrow_refuses_a_campaign_sealed_under_another_config():
    config = pb.BoundedEvaluatorConfig("forge.genesis_lite.v0_3", "1", pair_bound=pb.PairBound("tol_multiple", 5.0))
    service = pb.PairBoundedEscrowService(MASTER, config=config)
    transport = escrow.InProcessTransport(service)
    operator = escrow.OperatorClient(transport, transport.operator_token, escrow_public=transport.escrow_public)
    with pytest.raises(escrow.EscrowRefused, match="sealed"):
        operator.create("gl-escrow-x", {"indistinguishable": 1}, evaluator_config_digest=V0_2_CONFIG_DIGEST)
    created = operator.create("gl-escrow-y", {"indistinguishable": 1}, evaluator_config_digest=config.digest)
    assert len(created["cards"]) == 1
    with pytest.raises(escrow.EscrowRefused):
        pb.PairBoundedEscrowService(MASTER, config=EvaluatorConfig("forge.genesis_lite.v0_2", "1"))


def test_escrow_fda05_the_bounded_escrow_runs_the_v0_2_score_procedure_unchanged():
    """No second scoring rule: the bounded _score IS escrow._score's code; only _assess_pair is replaced."""
    config = pb.BoundedEvaluatorConfig("forge.genesis_lite.v0_3", "1", pair_bound=pb.PairBound("tol_multiple", 5.0))
    service = pb.PairBoundedEscrowService(MASTER, config=config)
    assert service._bounded_score.__func__.__code__ is escrow.EscrowService._score.__code__
    replaced = {k for k, val in service._bounded_score.__func__.__globals__.items() if vars(escrow).get(k) is not val}
    assert replaced == {"_assess_pair"}


# ---- the v0.3 harness end to end (development tier: the owner's w is still open) --------------------------------------
def _binding():
    return harness.bind(v03p.PREREG_PATH.read_bytes(), tier="development", development_bound=TEST_BOUND)


def test_harness_binds_with_the_escrow_half_and_seals_w_in_the_config():
    b = _binding()
    assert b.config.pair_bound.to_dict() == TEST_BOUND.to_dict() and b.tier == "development"
    assert b.prereg_sha256 == hashlib.sha256(v03p.PREREG_PATH.read_bytes()).hexdigest()


def test_harness_an_honest_arm_runs_valid_with_agreement_and_records_its_binding():
    rec = harness.run_one("careful", binding=_binding(), master_seed=MASTER, campaign_id="gl-v03-e2e-0",
                          presentation="anonymous", isolation="in_process")
    assert rec.status == "VALID", rec.reasons
    assert all(u["independent_agrees"] for u in rec.universes)
    assert {u["kind"] for u in rec.universes if u["law_form"] is not None} >= {"discoverable", "indistinguishable"}
    d = rec.to_dict()
    assert d["harness"] == harness.HARNESS_ID and d["pair_bound"] == TEST_BOUND.to_dict()
    assert d["evaluator_status"] == "VALID"


@pytest.mark.parametrize("campaign", ["gl-v03-vac-0", "gl-v03-vac-1"])
def test_harness_the_vacuous_attack_never_earns_a_bracket_hit_and_both_sides_agree(campaign):
    rec = harness.run_one("vacuous_pair", binding=_binding(), master_seed=MASTER, campaign_id=campaign,
                          presentation="anonymous", arm_spec="tests.genesis_lite.vacuous_arm:vacuous_pair")
    assert rec.status == "VALID", rec.reasons                          # escrow and evaluator agree on every universe
    assert rec.proposer_processes == 6
    for u in rec.universes:
        if u["outcome"] == "indistinguishable_hit":
            pytest.fail(f"a vacuous pair was credited in {u['kind']}")


def test_readiness_with_the_escrow_half_has_no_technical_row_left():
    rows = readiness.blockers()
    assert rows["FDA-05 escrow half"][0] == rows["v0.3 harness end to end"][0] == readiness.FIXED
    required = {name for _s, names, _n in rows.values() for name in names}
    assert set(readiness.ESCROW_TESTS["FDA-05 escrow half"]) <= required
    evidence = {"head": readiness._head(), "clean": True, "tests": {name: "passed" for name in required}}
    out = readiness.check(evidence=evidence)
    assert out["agreement_cases"] == 40 and out["technical_blockers"] == []
    assert out["status"] == readiness.PENDING_OWNER
    assert any("pair_bound.py is certified scope" in r for r in out["owner_and_certification"])


def test_environment_manifest_of_this_tree_names_numpy_and_imports_every_probe_module():
    manifest = environment.build_manifest()
    assert "numpy" in manifest["distributions"] and manifest["absent_probe_modules"] == []
    assert json.loads(v03p.PREREG_PATH.read_bytes())["escrow_half"]["sha256"] != "NOT_IN_TREE"


# ---- the evaluator's post-reveal verification on real v0.3 records (review rounds 3-4) --------------------------------
def _v03_attempt(tmp_path, tag, presentation="paraphrased"):
    from benchmarks.genesis_lite.v0_3 import formal
    from benchmarks.genesis_lite.v0_3.registry import AttemptRegistry, EvaluatorInbox

    root, prereg = hashlib.sha256(b"e2e root " + tag.encode()).digest(), hashlib.sha256(b"e2e prereg").hexdigest()
    reg, inbox = AttemptRegistry(tmp_path / tag / "reg"), EvaluatorInbox(tmp_path / tag / "inbox.jsonl")
    admission = reg.admit(root_commitment_sha256=hashlib.sha256(root).hexdigest(), prereg_sha256=prereg,
                          campaign_set_sha256=prereg, tier="formal")
    inbox.receive(admission)
    binding = _binding()

    def runner(arm, *, master_seed, campaign_id, presentation, seed):
        return harness.run_one(arm, binding=binding, master_seed=master_seed, campaign_id=campaign_id,
                               presentation=presentation, seed=seed, isolation="in_process").to_dict()

    master = formal.master_for(root, prereg, admission["nonce"], presentation, "gl-formal-5", 2)
    records = [{**runner(arm, master_seed=master, campaign_id="gl-formal-5", presentation=presentation, seed=2),
                "attempt_sha256": admission["attempt_sha256"]} for arm in ("careful", "always_refuse")]

    def verify(recs):
        log = formal.SealedLog(tmp_path / tag / "runs.jsonl")
        for rec in recs:
            log(rec)
        log.close()
        inbox.receive_heads(admission["attempt_sha256"], run_log=log.head, registry=reg.head())
        return formal.verify_attempt(
            tmp_path / tag / "runs.jsonl", root, admission, inbox=inbox, prereg_sha256=prereg,
            pair_bound=TEST_BOUND.to_dict(), replay_runner=runner,
            runs={(arm, (presentation, "gl-formal-5", 2)) for arm in ("careful", "always_refuse")})

    return records, verify


@pytest.mark.parametrize("presentation", ["paraphrased", "trap"])
def test_harness_records_of_an_honest_attempt_verify_end_to_end(tmp_path, presentation):
    records, verify = _v03_attempt(tmp_path, f"honest-{presentation}", presentation)
    assert all(r["status"] == "VALID" for r in records)
    assert all(isinstance(u["proposal"], dict) for r in records for u in r["universes"])
    assert verify(records) == []


def test_harness_a_forged_credit_or_flag_does_not_verify(tmp_path):
    records, verify = _v03_attempt(tmp_path, "forged")
    forged = json.loads(json.dumps(records))
    u = forged[1]["universes"][0]
    u["credit"] = 1.0 if u["credit"] != 1.0 else -1.0
    assert any("re-scores to" in p or "replay does not reproduce" in p for p in verify(forged))


def test_harness_a_whole_record_swap_between_arms_does_not_verify(tmp_path):
    records, verify = _v03_attempt(tmp_path, "swap")
    careful, refuse = records
    swapped = [{**careful, "arm": "always_refuse", "presented_card_digests": refuse["presented_card_digests"],
                "universes": careful["universes"]},
               {**refuse, "arm": "careful", "presented_card_digests": careful["presented_card_digests"],
                "universes": refuse["universes"]}]
    problems = verify(swapped)
    assert any("replay does not reproduce" in p for p in problems)
