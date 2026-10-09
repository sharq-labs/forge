"""Roadmap V2 R3/R4: FORGE Blindfold L5 universes, escrow boundary and evaluator isolation."""

from __future__ import annotations

import json
import math
import random

import pytest

from engcore.blindfold import (
    LEVELS, NOVEL_DISCOVERY_LEVELS, SECURITY_LABEL, EscrowRefused, EvaluatorConfig, InProcessTransport, ProposalStore, RoleRefused,
    SubprocessTransport, run_campaign,
)
from engcore.blindfold.baselines import always_law, always_refuse, careful
from engcore.blindfold.escrow import EscrowService, ObserveClient, ScoreClient, call
from engcore.blindfold.expression import ExpressionRefused, c, evaluate, mul, pw, structure_digest, v, validate
from engcore.blindfold.roles import admit, adjudicate
from engcore.blindfold.universe import CONTROL_KINDS, UniverseKind, generate_universe, known_law_signature, observe

MIX = {"discoverable": 8, "no_solution": 3, "insufficient_evidence": 3, "indistinguishable": 3, "spurious_correlate": 3, "confounded": 3}
CFG = EvaluatorConfig("bf.default", "1")


def test_levels_and_what_counts_as_discovery():
    assert set(LEVELS) == {f"L{i}" for i in range(7)}
    assert NOVEL_DISCOVERY_LEVELS == {"L4", "L5", "L6"}            # L0-L3 never count as novel discovery


def test_the_law_language_is_data_with_limits():
    law = mul(c(2.0), pw(v("x"), 1.37))
    assert validate(law) == {"x"} and evaluate(law, {"x": 2.0}) == pytest.approx(2.0 * 2.0 ** 1.37)
    assert structure_digest(law) == structure_digest(mul(pw(v("x"), 1.37), c(9.0)))   # constants and order abstracted
    assert structure_digest(law) != structure_digest(mul(c(2.0), pw(v("x"), 1.5)))
    assert math.isnan(evaluate({"log": v("x")}, {"x": -1.0}))                          # never a guessed value
    for bad in ({"call": "os.system"}, {"pow": [v("x"), v("y")]}, {"add": [v("x")]}, {"const": float("inf")}):
        with pytest.raises(ExpressionRefused):
            validate(bad)
    deep = v("x")
    for _ in range(20):
        deep = {"neg": deep}
    with pytest.raises(ExpressionRefused, match="depth"):
        validate(deep)


def test_universes_are_dimensionally_consistent_novel_and_vary_per_instance():
    worlds = [generate_universe(f"seed-{i}") for i in range(12)]
    assert len({w.law_structure for w in worlds}) >= 10 and len({w.universe_id for w in worlds}) == 12
    for w in worlds:
        # rescale every invented base unit by lambda: the law must rescale by lambda^dim(output) (dimensional homogeneity)
        rng = random.Random(w.universe_id)
        pt = {x.name: math.exp(rng.uniform(math.log(x.low), math.log(x.high))) for x in w.inputs}
        lam = [1.7, 0.6, 2.3][: len(w.base_dimensions)]
        scaled = {x.name: pt[x.name] * math.prod(lb ** e for lb, e in zip(lam, x.dimension)) for x in w.inputs}
        factor = math.prod(lb ** e for lb, e in zip(lam, w.output_dimension))
        assert evaluate(w.law, scaled) == pytest.approx(evaluate(w.law, pt) * factor, rel=1e-9)
    assert known_law_signature((-2.0,)) and known_law_signature((1.0, 0.5)) and not known_law_signature((1.37, -0.81))


def test_the_public_card_reveals_no_hidden_information():
    for kind in UniverseKind:
        w = generate_universe("card", kind)
        card = w.public_card()
        assert card["level"] == "L5" and "confounded" in card["answers"]
        text = json.dumps({k: val for k, val in card.items() if k != "answers"})   # the answer menu is public by design
        for secret in ("law", "seed", "evaluation", "tolerance", kind.value, "spurious", "confound", "hidden", "noise", "alternative"):
            assert secret not in text, (kind, secret)


def test_controls_behave_as_declared():
    ns = generate_universe("ctl", UniverseKind.NO_SOLUTION)
    assert ns.law is None
    sp = generate_universe("ctl", UniverseKind.SPURIOUS_CORRELATE)
    rng = random.Random(0)
    pts = [{x.name: math.exp(rng.uniform(math.log(x.low), math.log(x.high))) for x in sp.inputs} for _ in range(30)]
    obs = [observe(sp, p, rng) for p in pts]
    driver = sp.covariates["u1"]["driver"]
    corr = float(__import__("numpy").corrcoef([math.log(o[driver]) for o in obs], [math.log(o["u1"]) for o in obs])[0, 1])
    assert corr > 0.95                                         # in observation the covariate tracks its driver ...
    ind = generate_universe("ctl", UniverseKind.INDISTINGUISHABLE)
    assert ind.alternative_law is not None and all(any(p[x.name] > x.high for x in ind.inputs) for p in ind.evaluation_points)
    assert CONTROL_KINDS == frozenset(UniverseKind) - {UniverseKind.DISCOVERABLE}


def test_escrow_capabilities_budget_single_submission_and_log():
    t = InProcessTransport()
    created = call(t, "create", campaign_id="c1", mix={"discoverable": 1})
    card, tok = created["cards"][0], created["tokens"]
    obs = ObserveClient(t, "c1", tok["observe"])
    pt = {x["name"]: x["range"][0] for x in card["inputs"] if x["settable"]}
    r = obs.observe(card["universe_id"], pt, query_id="q0")
    assert r["security_boundary"] == SECURITY_LABEL and set(r["observation"]) >= set(pt) | {"y"}
    assert "law" not in json.dumps(r) and "evaluation" not in json.dumps(r)
    with pytest.raises(EscrowRefused, match="SCORE capability"):          # the proposer's token cannot score
        ScoreClient(t, "c1", tok["observe"]).score(card["universe_id"], {"answer": "no_law"})
    with pytest.raises(EscrowRefused, match="OBSERVE capability"):
        ObserveClient(t, "c1", "forged").observe(card["universe_id"], pt)
    with pytest.raises(EscrowRefused, match="outside the allowed query range"):
        obs.observe(card["universe_id"], {k: val * 1e6 for k, val in pt.items()})
    with pytest.raises(EscrowRefused, match="digest does not match"):
        call(t, "score", campaign_id="c1", token=tok["score"], universe_id=card["universe_id"], proposal={"answer": "no_law"},
             proposal_digest="0" * 64)
    sc = ScoreClient(t, "c1", tok["score"])
    res = sc.score(card["universe_id"], {"answer": "no_law"})
    assert res["universe_kind"] == "discoverable"                         # revealed only after the sealed submission
    with pytest.raises(EscrowRefused, match="one sealed submission"):
        sc.score(card["universe_id"], {"answer": "law", "law": c(1.0)})
    with pytest.raises(EscrowRefused, match="sealed; no further observation"):
        obs.observe(card["universe_id"], pt)
    log = call(t, "log", campaign_id="c1", token=tok["observe"])["log"]
    assert [e["op"] for e in log][:2] == ["create", "observe"]
    prev = "0" * 64
    for e in log:                                                          # hash chain, and the token is never logged
        assert e["previous"] == prev and "token" not in json.dumps(e)
        prev = e["digest"]


def test_budget_is_enforced():
    t = InProcessTransport()
    created = call(t, "create", campaign_id="b", mix={"insufficient_evidence": 1})
    card, tok = created["cards"][0], created["tokens"]
    obs = ObserveClient(t, "b", tok["observe"])
    pt = {x["name"]: x["range"][0] for x in card["inputs"] if x["settable"]}
    for _ in range(card["query_budget"]):
        obs.observe(card["universe_id"], pt)
    with pytest.raises(EscrowRefused, match="budget"):
        obs.observe(card["universe_id"], pt)


def test_refusing_correctly_earns_credit_and_always_proposing_performs_badly():
    reports = {}
    for name, proposer in (("refuse", always_refuse), ("law", always_law), ("careful", careful)):
        reports[name], _ = run_campaign(InProcessTransport(), campaign_id=f"cmp-{name}", mix=MIX, proposer=proposer,
                                        proposer_identity={"kind": "algorithm", "id": name}, config=CFG)
    s = {k: r.summary() for k, r in reports.items()}
    assert s["law"]["total_credit"] < 0 and s["law"]["correct_refusal_rate_on_controls"] == 0.0
    assert s["refuse"]["discovery_success_rate"] == 0.0
    assert s["careful"]["total_credit"] > s["refuse"]["total_credit"] > s["law"]["total_credit"]
    assert s["careful"]["false_discovery_rate"] < s["law"]["false_discovery_rate"]
    assert all(r.to_dict()["security_boundary"] == SECURITY_LABEL for r in reports.values())


def test_replay_reuses_stored_proposals_and_never_calls_the_proposer():
    calls = []

    def counting(card, client):
        calls.append(card["universe_id"])
        return careful(card, client)

    rep, store = run_campaign(InProcessTransport(EscrowService(b"k" * 32)), campaign_id="r", mix={"discoverable": 2},
                              proposer=counting, proposer_identity={"kind": "algorithm", "id": "careful"}, config=CFG)
    assert len(calls) == 2
    replay = {a.universe_id: a.proposal_digest for a in rep.adjudications}

    def forbidden(card, client):  # pragma: no cover - must never run
        raise AssertionError("replay called the proposer")

    rep2, _ = run_campaign(InProcessTransport(EscrowService(b"k" * 32)), campaign_id="r", mix={"discoverable": 2},
                           proposer=forbidden, proposer_identity={"kind": "algorithm", "id": "careful"}, config=CFG,
                           store=store, replay=replay)
    assert [a.proposal_digest for a in rep2.adjudications] == [a.proposal_digest for a in rep.adjudications]
    assert [a.credit for a in rep2.adjudications] == [a.credit for a in rep.adjudications]


def test_the_evaluator_config_is_sealed_and_admission_sees_only_the_card():
    w = generate_universe("adm")
    card = w.public_card()
    store = ProposalStore()
    with pytest.raises(RoleRefused, match="not on the card"):
        admit({"universe_id": card["universe_id"], "answer": "law", "law": v("__hidden_cause"), "proposer": {"kind": "a", "id": "b"}},
              card, store)
    with pytest.raises(RoleRefused, match="names its proposer"):
        admit({"universe_id": card["universe_id"], "answer": "no_law"}, card, store)
    score = {"universe_id": "u", "answer": "no_law", "universe_kind": "no_solution", "proposal_digest": "d", "receipt": {"digest": "r"}}
    tampered = EvaluatorConfig("bf.default", "1", {"no_solution": {"no_law": 100.0}})
    with pytest.raises(RoleRefused, match="changed after it was sealed"):
        adjudicate(score, tampered, sealed_config_digest=CFG.digest)


def test_the_subprocess_escrow_keeps_its_secrets_in_the_child():
    t = SubprocessTransport()
    try:
        created = call(t, "create", campaign_id="sp", mix={"discoverable": 1})
        assert created["transport"] == "subprocess" and created["security_boundary"] == SECURITY_LABEL
        card, tok = created["cards"][0], created["tokens"]
        r = ObserveClient(t, "sp", tok["observe"]).observe(card["universe_id"],
                                                          {x["name"]: x["range"][1] for x in card["inputs"] if x["settable"]})
        assert r["observation"]["y"] > 0
    finally:
        t.close()
