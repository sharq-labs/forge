"""Roadmap V2 R3/R4: FORGE Blindfold L5 universes, escrow boundary and evaluator isolation (incl. checkpoint-2 review)."""

from __future__ import annotations

import hashlib
import json
import math
import random

import numpy as np
import pytest

from engcore.blindfold import (
    LEVELS, NOVEL_DISCOVERY_LEVELS, SECURITY_LABEL, EscrowRefused, EvaluatorConfig, InProcessTransport, ProposalStore, RoleRefused,
    SubprocessTransport,
)
import dataclasses

from engcore.blindfold.baselines import always_insufficient, always_law, always_refuse, careful, single_setting
from engcore.blindfold.escrow import (
    PROTOCOL, EscrowService, ObserveClient, OperatorClient, ScoreClient, _assess, call, verify_log,
)
from engcore.blindfold.expression import ExpressionRefused, add, c, evaluate, mul, pw, structure_digest, v, validate
from engcore.blindfold.roles import admit, adjudicate
from engcore.blindfold.roles import run_campaign as _run_campaign


def run_campaign(transport, **kw):
    """The operator pins the escrow key it learned out of band (here: from the transport it built)."""
    return _run_campaign(transport, escrow_public=transport.escrow_public, **kw)
from engcore.blindfold.universe import (
    CONTROL_KINDS, COVARIATE, INBOX_MAX_SIGMAS, OUTSIDE_FRACTION, OUTSIDE_TOLERANCES, UniverseKind, _box, _corners, _sample,
    generate_universe, known_law_signature, observe, truth_at,
)

MIX = {"discoverable": 8, "no_solution": 3, "insufficient_evidence": 3, "indistinguishable": 3, "spurious_correlate": 3, "confounded": 3}
CFG = EvaluatorConfig("bf.default", "1")
ID = {"kind": "algorithm", "id": "t"}


def _campaign(t, cid, mix):
    op = OperatorClient(t, t.operator_token, escrow_public=t.escrow_public)
    return op, op.create(cid, mix, evaluator_config_digest=CFG.digest)


def test_levels_and_what_counts_as_discovery():
    assert set(LEVELS) == {f"L{i}" for i in range(7)}
    assert NOVEL_DISCOVERY_LEVELS == {"L4", "L5", "L6"}            # L0-L3 never count as novel discovery


def test_the_law_language_is_data_with_limits_and_a_canonical_structure():
    law = mul(c(2.0), pw(v("x"), 1.37))
    assert validate(law) == {"x"} and evaluate(law, {"x": 2.0}) == pytest.approx(2.0 * 2.0 ** 1.37)
    assert structure_digest(law) == structure_digest(mul(pw(v("x"), 1.37), c(9.0)))   # constants and order abstracted
    assert structure_digest(law) != structure_digest(mul(c(2.0), pw(v("x"), 1.5)))
    # algebraically identical power-law rewrites are ONE structure (review M5)
    assert structure_digest(law) == structure_digest(mul(pw(v("x"), 0.37), v("x"), c(5.0)))
    grouped = pw(mul(pw(v("a"), 2.0), pw(v("b"), -1.0)), 0.6)
    assert structure_digest(grouped) == structure_digest(mul(c(3.0), pw(v("a"), 1.2), pw(v("b"), -0.6)))
    assert structure_digest(add(v("x"), c(1.0))) != structure_digest(v("x"))
    assert math.isnan(evaluate({"log": v("x")}, {"x": -1.0}))                          # never a guessed value
    for bad in ({"call": "os.system"}, {"pow": [v("x"), v("y")]}, {"add": [v("x")]}, {"const": float("inf")}):
        with pytest.raises(ExpressionRefused):
            validate(bad)
    deep = v("x")
    for _ in range(20):
        deep = {"neg": deep}
    with pytest.raises(ExpressionRefused, match="depth"):
        validate(deep)


def test_every_kind_is_dimensionally_homogeneous_non_textbook_and_varies_per_instance():
    worlds = [generate_universe(f"seed-{i}", k) for k in UniverseKind for i in range(6)]
    disc = [w for w in worlds if w.kind is UniverseKind.DISCOVERABLE]
    assert len({w.law_structure for w in disc}) == len(disc) and len({w.universe_id for w in worlds}) == len(worlds)
    scales = set()
    for w in worlds:
        if w.law is None:
            assert w.kind is UniverseKind.NO_SOLUTION
            continue
        rng = random.Random(w.universe_id)
        pt = {**_sample(rng, _box(w.inputs)), COVARIATE: 1.3}                    # u1 is dimensionless
        lam = [1.7, 0.6, 2.3][: len(w.base_dimensions)]
        scaled = {**{x.name: pt[x.name] * math.prod(lb ** e for lb, e in zip(lam, x.dimension)) for x in w.inputs}, COVARIATE: 1.3}
        factor = math.prod(lb ** e for lb, e in zip(lam, w.output_dimension))
        for law in (w.law, w.alternative_law):                                   # the INDISTINGUISHABLE rival too (review H4)
            if law is not None:
                assert evaluate(law, scaled) == pytest.approx(evaluate(law, pt) * factor, rel=1e-9), w.kind
        scales.add(tuple(w.output_dimension))
    assert len(scales) > 3                                                       # output is not always inputs[0]^1 (review M4)
    assert known_law_signature((-2.0,)) and known_law_signature((0.75, 1.37)) and known_law_signature((1 / 3, 0.8))
    assert not known_law_signature((1.37, -0.87)) and known_law_signature((1.37, -0.81))     # 0.81 sits on 0.8


def test_the_public_card_has_one_shape_and_reveals_no_hidden_information():
    shapes = set()
    for kind in UniverseKind:
        for i in range(8):
            w = generate_universe(f"card-{i}", kind)
            card = w.public_card()
            assert card["level"] == "L5" and "confounded" in card["answers"]
            assert card["observed_covariates"] == [COVARIATE]                   # presence is never a tell (review M3)
            assert all(x["settable"] for x in card["inputs"])
            shapes.add(tuple(sorted(card)))
            text = json.dumps({k: val for k, val in card.items() if k != "answers"})
            for secret in ("law", "seed", "evaluation", "tolerance", kind.value, "spurious", "confound", "hidden", "noise",
                           "alternative", "role", "driver"):
                assert secret not in text, (kind, secret)
    assert len(shapes) == 1


def test_indistinguishable_is_verified_inside_and_outside_the_box():
    for i in range(10):
        w = generate_universe(f"ind-{i}", UniverseKind.INDISTINGUISHABLE)
        box = _box(w.inputs)
        rng = random.Random(i)
        grid = [{**p, COVARIATE: 1.0} for p in _corners(box) + [_sample(rng, box) for _ in range(300)]]
        rel = [abs(evaluate(w.alternative_law, p) - evaluate(w.law, p)) / abs(evaluate(w.law, p)) for p in grid]
        assert max(rel) <= INBOX_MAX_SIGMAS * w.noise_sigma * (1 + 1e-6)          # within noise in the box
        out = [abs(evaluate(w.alternative_law, p) - evaluate(w.law, p)) / abs(evaluate(w.law, p)) for p in w.evaluation_points]
        assert sum(x > OUTSIDE_TOLERANCES * w.tolerance for x in out) >= OUTSIDE_FRACTION * len(out)
        assert w.public_card()["assessment_region"] != {k: list(val) for k, val in box.items()}


def test_confounded_is_real_confounding_scored_on_the_interventional_truth():
    w = generate_universe("conf", UniverseKind.CONFOUNDED)
    rng = random.Random(1)
    rows = [observe(w, _sample(rng, _box(w.inputs)), rng) for _ in range(400)]
    names = [x.name for x in w.inputs] + [COVARIATE]
    X = np.column_stack([np.ones(len(rows))] + [np.log([r[n] for r in rows]) for n in names])
    coef, *_ = np.linalg.lstsq(X, np.log([r["y"] for r in rows]), rcond=None)
    passive = mul(c(math.exp(coef[0])), *[pw(v(n), float(a)) for n, a in zip(names, coef[1:])])
    truths = [truth_at(w, p, random.Random(7)) for p in w.evaluation_points]
    assert not _assess(passive, truths, w)["passed"]            # the passive association is biased ...
    # the interventional truth is a passable target (the hidden law passes against it); a PASSIVE proposer cannot learn it,
    # since only b + a/c is identifiable from observation -- so in practice CONFOUNDED is earned by refusing
    assert _assess(w.law, truths, w)["passed"]
    assert CFG.credit_for("confounded", "law_pass") > 0 and CFG.credit_for("confounded", "confounded") > 0
    assert CONTROL_KINDS == frozenset(UniverseKind) - {UniverseKind.DISCOVERABLE}


def test_the_observe_client_api_sends_only_observe_and_every_query_is_logged():
    t = InProcessTransport()
    op, created = _campaign(t, "c1", {"discoverable": 1})
    card, tok = created["cards"][0], created["tokens"]
    obs = ObserveClient(t, "c1", tok["observe"], escrow_public=t.escrow_public)
    assert not hasattr(obs, "transport") and not hasattr(obs, "token") and not hasattr(obs, "__dict__")   # review H1
    # ... but this is construction, NOT isolation: the closure still reaches the transport (SECURITY_BOUNDARY_NOT_PROVEN)
    cells = [cell.cell_contents for cell in obs._send.__closure__]
    assert t in cells + [getattr(c, "_transport", None) for c in cells]
    with pytest.raises(EscrowRefused, match="evaluator-config digest"):
        call(t, "create", campaign_id="noconfig", mix={"discoverable": 1}, operator_token=t.operator_token)
    for token in (tok["observe"], tok["score"], "forged"):
        with pytest.raises(EscrowRefused, match="not authenticated"):
            call(t, "create", campaign_id="mine", mix={"confounded": 5}, operator_token=token)
        with pytest.raises(EscrowRefused, match="not authenticated"):
            call(t, "log", campaign_id="c1", operator_token=token)
    pt = {x["name"]: x["range"][0] for x in card["inputs"]}
    r = obs.observe(card["universe_id"], pt, query_id="q0")
    assert r["security_boundary"] == SECURITY_LABEL and set(r["observation"]) >= set(pt) | {"y", COVARIATE}
    assert "law" not in json.dumps(r) and "evaluation" not in json.dumps(r)
    with pytest.raises(EscrowRefused, match="not authenticated"):
        ScoreClient(t, "c1", tok["observe"], escrow_public=t.escrow_public).score(card["universe_id"], {"answer": "no_law"})
    with pytest.raises(EscrowRefused, match="outside the allowed query range"):
        obs.observe(card["universe_id"], {k: val * 1e6 for k, val in pt.items()})
    with pytest.raises(EscrowRefused, match="digest does not match"):
        call(t, "score", campaign_id="c1", token=tok["score"], universe_id=card["universe_id"], proposal={"answer": "no_law"},
             proposal_digest="0" * 64)
    sc = ScoreClient(t, "c1", tok["score"], escrow_public=t.escrow_public)
    res = sc.score(card["universe_id"], {"answer": "no_law"})
    assert res["universe_kind"] == "discoverable" and "law_structure_hidden_digest" not in res
    with pytest.raises(EscrowRefused, match="one sealed submission"):
        sc.score(card["universe_id"], {"answer": "law", "law": c(1.0)})
    with pytest.raises(EscrowRefused, match="sealed; no further observation"):
        obs.observe(card["universe_id"], pt)
    log = op.log("c1")["log"]
    ops = [e["op"] for e in log]
    # AUTHENTICATED refusals are logged (review M8): out-of-range observe, bad digest, second score, sealed observe.  Requests
    # with a forged or wrong capability are not: they are counted service-wide and never enter a campaign's chain (B-M1)
    assert ops[0] == "create" and ops.count("log_refused") == 0 and "observe" in ops
    assert ops.count("score_refused") >= 2 and ops.count("observe_refused") >= 2
    assert op.log("c1")["auth_failures"] >= 7
    assert verify_log(log) == log[-1]["digest"] and "token" not in json.dumps(log)
    # log digests are keyed: the create entry cannot be confirmed by hashing a guessed mix
    guess = hashlib.sha256(json.dumps({"campaign_id": "c1", "mix": {"discoverable": 1}}, sort_keys=True, separators=(",", ":")).encode())
    assert log[0]["query_digest"] != guess.hexdigest()


def test_budget_mix_bounds_and_malformed_requests_are_refused_not_fatal():
    t = InProcessTransport()
    op, created = _campaign(t, "b", {"insufficient_evidence": 1})
    card, tok = created["cards"][0], created["tokens"]
    obs = ObserveClient(t, "b", tok["observe"], escrow_public=t.escrow_public)
    pt = {x["name"]: x["range"][0] for x in card["inputs"]}
    with pytest.raises(EscrowRefused, match="finite number"):               # float() overflow (re-review H-1)
        obs.observe(card["universe_id"], {name: 10 ** 400 for name in pt})
    assert op.log("b")["log"][-1]["op"] == "observe_refused"                # ... refused AND logged
    for _ in range(card["query_budget"]):
        obs.observe(card["universe_id"], pt)
    with pytest.raises(EscrowRefused, match="budget"):
        obs.observe(card["universe_id"], pt)
    with pytest.raises(EscrowRefused, match="1..256"):
        op.create("huge", {"discoverable": 10_000}, evaluator_config_digest=CFG.digest)
    with pytest.raises(EscrowRefused, match="integers"):
        op.create("float", {"discoverable": 1.5}, evaluator_config_digest=CFG.digest)
    deep = "[" * 100_000 + "]" * 100_000
    resp = json.loads(t(f'{{"protocol": "{PROTOCOL}", "op": "observe", "settings": {deep}}}'.encode()))
    assert resp["ok"] is False                                              # RecursionError is a refusal, not a crash



def test_indistinguishable_cannot_be_shotgunned_or_duplicated():
    w = generate_universe("adm", UniverseKind.DISCOVERABLE)
    card, store = w.public_card(), ProposalStore()
    law = mul(c(1.0), v(w.inputs[0].name))
    with pytest.raises(RoleRefused, match="exactly two"):
        admit({"universe_id": card["universe_id"], "answer": "indistinguishable", "laws": [law] * 3, "proposer": ID}, card, store)
    with pytest.raises(RoleRefused, match="carries no law"):
        admit({"universe_id": card["universe_id"], "answer": "no_law", "law": law, "proposer": ID}, card, store)
    t = InProcessTransport()
    _op, created = _campaign(t, "sh", {"indistinguishable": 1})
    uid, sc = created["cards"][0]["universe_id"], ScoreClient(t, "sh", created["tokens"]["score"], escrow_public=t.escrow_public)
    world = t._service._campaigns["sh"].worlds[uid]
    with pytest.raises(EscrowRefused, match="exactly two"):
        sc.score(uid, {"answer": "indistinguishable", "laws": [world.law, world.alternative_law, world.law]})
    dup = sc.score(uid, {"answer": "indistinguishable", "laws": [world.law, world.law]})   # even the TRUE law, twice
    assert dup["pair"]["contains_truth"] and not dup["pair"]["hit"]
    # re-review M1: a pair a tolerance apart is distinguishable in the box; a law that goes NaN outside is a miss
    s_ = 0.6 * world.tolerance
    _op, cr3 = _campaign(t, "sh3", {"indistinguishable": 2, "discoverable": 2})
    sc3 = ScoreClient(t, "sh3", cr3["tokens"]["score"], escrow_public=t.escrow_public)
    worlds3 = t._service._campaigns["sh3"].worlds
    u_a, u_b, *rest = cr3["cards"]
    for card3, pair in ((u_a, lambda w: [mul(c(1 + s_), w.law), mul(c(1 - s_), w.law)]),
                        (u_b, lambda w: [w.law, mul(w.law, {"log": mul(c(-1.0), v(w.inputs[0].name))})])):
        res3 = sc3.score(card3["universe_id"], {"answer": "indistinguishable", "laws": pair(worlds3[card3["universe_id"]])})
        assert not res3["pair"]["hit"], res3["pair"]
    for card3 in rest:                                                      # a box-region universe is never a hit
        w3 = worlds3[card3["universe_id"]]
        if w3.law is not None and not any(any(not (x.low <= p[x.name] <= x.high) for x in w3.inputs) for p in w3.evaluation_points):
            r3 = sc3.score(card3["universe_id"], {"answer": "indistinguishable", "laws": [w3.law, w3.law]})
            assert r3["pair"]["outside_points"] == 0 and not r3["pair"]["hit"]
    assert adjudicate(dup, CFG, sealed_config_digest=CFG.digest, proposer_digest="p").outcome == "indistinguishable_miss"
    _op, created = _campaign(t, "sh2", {"indistinguishable": 1})
    uid2 = created["cards"][0]["universe_id"]
    w2 = t._service._campaigns["sh2"].worlds[uid2]
    hit = ScoreClient(t, "sh2", created["tokens"]["score"], escrow_public=t.escrow_public).score(uid2, {"answer": "indistinguishable", "laws": [w2.alternative_law, w2.law]})
    assert hit["pair"]["hit"]                                               # the genuine pair is credited


def test_an_inadmissible_proposal_is_kept_and_costs_credit_never_a_refusal():
    def garbage(card, client):
        return {"universe_id": "wrong", "answer": "law"}

    def law_without_law(card, client):
        return {"answer": "law"}                                            # was a KeyError crash (review LOW)

    def not_a_mapping(card, client):
        return 42

    def raises(card, client):
        raise RuntimeError("proposer crashed")                             # re-review M2: never a non-result

    def huge_const(card, client):
        return {"answer": "law", "law": {"const": 10 ** 400}}

    def deep_repr(card, client):
        deep: list = []
        for _ in range(100_000):
            deep = [deep]
        return {"answer": "no_law", "rationale": deep}

    for proposer in (garbage, law_without_law, not_a_mapping, raises, huge_const, deep_repr):
        rep, store = run_campaign(InProcessTransport(), campaign_id="g", mix=MIX, proposer=proposer, proposer_identity=ID, config=CFG)
        s = rep.summary()
        assert s["inadmissible"] == s["universes"] and s["total_credit"] == -s["universes"]       # review H2
        assert s["correct_refusal_rate_on_controls"] == 0.0
        a = rep.adjudications[0]
        record = store.get(a.proposal_digest)
        assert record["answer"] == "inadmissible" and store.get(record["original_digest"])     # the original is kept


def test_credit_is_reported_over_the_best_constant_answer():
    reports = {}
    for name, proposer in (("refuse", always_refuse), ("insufficient", always_insufficient), ("law", always_law), ("careful", careful),
                           ("single", single_setting)):
        # a fixed master seed: the assertions below held on all of 20 seeds (scan recorded in docs/work/PROGRESS.md)
        reports[name], _ = run_campaign(InProcessTransport(EscrowService(b"\x07" * 32)), campaign_id=f"cmp-{name}", mix=MIX, proposer=proposer,
                                        proposer_identity={"kind": "algorithm", "id": name}, config=CFG)
    s = {k: r.summary() for k, r in reports.items()}
    assert s["insufficient"]["credit_over_best_constant_answer"] == 0.0     # a blanket refusal earns nothing (review M1)
    assert s["refuse"]["credit_over_best_constant_answer"] <= 0.0
    assert s["law"]["total_credit"] < 0 and s["law"]["correct_refusal_rate_on_controls"] == 0.0
    assert s["careful"]["credit_over_best_constant_answer"] > 0
    # re-review M3: a non-discoverer can earn control credit; discovery credit is reported apart and it has none
    assert s["single"]["discovery_credit"] <= 0 and s["single"]["discovery_success_rate"] == 0.0
    assert all(r.summary()["discovery_credit"] + r.summary()["control_credit"] == r.summary()["total_credit"] for r in reports.values())
    assert s["careful"]["false_discovery_rate"] in (None, 0.0) or s["careful"]["false_discovery_rate"] < s["law"]["false_discovery_rate"]
    for r in reports.values():
        d = r.to_dict()
        assert d["security_boundary"] == SECURITY_LABEL and d["transport"] == "in_process"
        assert all(a.transport == "in_process" for a in r.adjudications)
        assert d["summary"]["level_eligible_for_novel_discovery"] is True
        assert d["summary"]["counts_as_novel_discovery"] is False           # never while the boundary is unproven (review H6)
        forged = dataclasses.replace(r, security_boundary="definitely-isolated")    # re-review M4: fails closed
        assert forged.summary()["counts_as_novel_discovery"] is False


def test_replay_is_complete_identity_bound_and_never_calls_the_proposer():
    calls = []

    def counting(card, client):
        calls.append(card["universe_id"])
        return careful(card, client)

    rep, store = run_campaign(InProcessTransport(EscrowService(b"k" * 32)), campaign_id="r", mix={"discoverable": 2, "confounded": 1},
                              proposer=counting, proposer_identity={"kind": "algorithm", "id": "careful"}, config=CFG)
    assert len(calls) == 3
    replay = {a.universe_id: a.proposal_digest for a in rep.adjudications}

    def forbidden(card, client):  # pragma: no cover - must never run
        raise AssertionError("replay called the proposer")

    def again(**kw):
        return run_campaign(InProcessTransport(EscrowService(kw.pop("seed", b"k" * 32))), campaign_id="r",
                            mix={"discoverable": 2, "confounded": 1}, proposer=forbidden, config=CFG, store=store, **kw)

    rep2, _ = again(proposer_identity={"kind": "algorithm", "id": "careful"}, replay=replay, replay_of=rep)
    assert rep2.outcome_digest == rep.outcome_digest and rep2.replay_of == rep.outcome_digest and rep.replay_of == ""
    partial = dict(list(replay.items())[:2])
    with pytest.raises(RoleRefused, match="every universe"):                # review H7: never a silent re-generation
        again(proposer_identity={"kind": "algorithm", "id": "careful"}, replay=partial)
    with pytest.raises(RoleRefused, match="every universe"):
        again(proposer_identity={"kind": "algorithm", "id": "careful"}, replay=replay, seed=b"z" * 32)
    with pytest.raises(RoleRefused, match="cannot be reassigned"):
        again(proposer_identity={"kind": "language_model", "id": "someone-else"}, replay=replay)


def test_the_evaluator_config_is_sealed_and_admission_sees_only_the_card():
    w = generate_universe("adm")
    card = w.public_card()
    store = ProposalStore()
    with pytest.raises(RoleRefused, match="not on the card"):
        admit({"universe_id": card["universe_id"], "answer": "law", "law": v("__hidden_cause"), "proposer": ID}, card, store)
    with pytest.raises(RoleRefused, match="names its proposer"):
        admit({"universe_id": card["universe_id"], "answer": "no_law"}, card, store)
    score = {"universe_id": "u", "answer": "no_law", "universe_kind": "no_solution", "proposal_digest": "d", "receipt": {"digest": "r"}}
    tampered = EvaluatorConfig("bf.default", "1", {"no_solution": {"no_law": 100.0}})
    with pytest.raises(RoleRefused, match="changed after it was sealed"):
        adjudicate(score, tampered, sealed_config_digest=CFG.digest, proposer_digest="p")


def test_the_subprocess_escrow_keeps_its_secrets_in_the_child():
    t = SubprocessTransport()
    try:
        with pytest.raises(EscrowRefused, match="not authenticated"):
            call(t, "create", campaign_id="sp", mix={"discoverable": 1})
        created = OperatorClient(t, t.operator_token, escrow_public=t.escrow_public).create("sp", {"discoverable": 1}, evaluator_config_digest=CFG.digest)
        assert created["transport"] == "subprocess" and created["security_boundary"] == SECURITY_LABEL
        card, tok = created["cards"][0], created["tokens"]
        r = ObserveClient(t, "sp", tok["observe"], escrow_public=t.escrow_public).observe(card["universe_id"], {x["name"]: x["range"][1] for x in card["inputs"]})
        assert r["observation"]["y"] > 0
        with pytest.raises(EscrowRefused, match="finite number"):           # re-review H-1: the child survives an overflow
            ObserveClient(t, "sp", tok["observe"], escrow_public=t.escrow_public).observe(card["universe_id"], {x["name"]: 10 ** 400 for x in card["inputs"]})
        assert ObserveClient(t, "sp", tok["observe"], escrow_public=t.escrow_public).observe(card["universe_id"], {x["name"]: x["range"][1] for x in card["inputs"]})
    finally:
        t.close()
