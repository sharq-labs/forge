"""Big Rock 2 -- the Blindfold escrow as a service: persistent budgets, authenticated requests, signed responses.

These run inside ONE security domain: they establish PROTOCOL_SECURITY_VERIFIED, never host isolation (that is
``test_escrow_isolation.py`` / :mod:`engcore.blindfold.isolation`).
"""

from __future__ import annotations

import json
import os

import pytest

from engcore.blindfold.escrow import (
    PROTOCOL,
    SECURITY_LABEL,
    EscrowRefused,
    EscrowService,
    EscrowStorage,
    InProcessTransport,
    ObserveClient,
    OperatorClient,
    ScoreClient,
    SubprocessTransport,
    call,
    mac_request,
    verify_log,
    verify_response,
)

CFG = "a" * 64


def storage(tmp_path, name="escrow"):
    return EscrowStorage(tmp_path / name, create=True)


def start(tmp_path, name="escrow"):
    t = InProcessTransport(EscrowService(storage=storage(tmp_path, name)))
    op = OperatorClient(t, t.operator_token)
    created = op.create("c1", {"discoverable": 2}, evaluator_config_digest=CFG)
    return t, op, created


def point(card):
    return {x["name"]: x["range"][0] for x in card["inputs"]}


def test_budgets_submissions_and_query_ids_survive_an_escrow_restart(tmp_path):
    t, op, created = start(tmp_path)
    card = created["cards"][0]
    obs = ObserveClient(t, "c1", created["tokens"]["observe"])
    first = obs.observe(card["universe_id"], point(card), query_id="a1")
    ScoreClient(t, "c1", created["tokens"]["score"]).score(created["cards"][1]["universe_id"], {"answer": "no_law"})
    before = op.log("c1")
    # --- restart: a NEW service from the same private storage
    t2 = InProcessTransport(EscrowService(storage=EscrowStorage(tmp_path / "escrow")))
    assert t2.operator_token == t.operator_token and t2.escrow_public == t.escrow_public
    after = OperatorClient(t2, t2.operator_token).log("c1")
    assert after["spent"] == before["spent"] and after["submitted"] == before["submitted"] and after["head"] == before["head"]
    assert verify_log(after["log"]) == after["head"]
    obs2 = ObserveClient(t2, "c1", created["tokens"]["observe"])              # the same capability works after restart
    again = obs2.observe(card["universe_id"], point(card), query_id="a2")
    assert again["budget_remaining"] == first["budget_remaining"] - again["budget_consumed"]   # NOT reset
    with pytest.raises(EscrowRefused, match="already used"):
        obs2.observe(card["universe_id"], point(card), query_id="a1")        # a pre-restart query id stays used
    with pytest.raises(EscrowRefused, match="one sealed submission"):
        ScoreClient(t2, "c1", created["tokens"]["score"]).score(created["cards"][1]["universe_id"], {"answer": "law", "law": {"c": 1.0}})
    with pytest.raises(EscrowRefused, match="exhausted"):
        for i in range(500):                                                   # over-querying stops at the persisted budget
            obs2.observe(card["universe_id"], point(card), query_id=f"x{i}")


def test_a_tampered_journal_refuses_to_start_and_a_truncated_one_is_caught_by_the_client(tmp_path):
    t, op, created = start(tmp_path)
    card = created["cards"][0]
    obs = ObserveClient(t, "c1", created["tokens"]["observe"])
    for i in range(3):
        obs.observe(card["universe_id"], point(card), query_id=f"q{i}")
    journal = tmp_path / "escrow" / "journal.jsonl"
    lines = journal.read_text().splitlines()
    rec = json.loads(lines[1])
    rec["record"]["state"]["cost"] = 0.0                                      # budget rollback by editing the journal
    journal.write_text("\n".join([lines[0], json.dumps(rec)] + lines[2:]) + "\n")
    with pytest.raises(EscrowRefused, match="keyed chain"):
        EscrowService(storage=EscrowStorage(tmp_path / "escrow"))
    journal.write_text("\n".join([lines[0], lines[2], lines[1]] + lines[3:]) + "\n")      # reordered
    with pytest.raises(EscrowRefused, match="keyed chain"):
        EscrowService(storage=EscrowStorage(tmp_path / "escrow"))
    journal.write_text("\n".join(lines[:2]) + "\n")                           # truncated tail: two observations "forgotten"
    t2 = InProcessTransport(EscrowService(storage=EscrowStorage(tmp_path / "escrow")))
    with pytest.raises(EscrowRefused, match="rolled back"):                   # the proposer saw sequence 3 before the restart
        call(t2, "observe", token=created["tokens"]["observe"], campaign_id="c1", universe_id=card["universe_id"],
             settings=point(card), last_sequence=3, query_id="q9")


def test_requests_are_capability_bound_and_never_carry_the_credential(tmp_path):
    t, op, created = start(tmp_path)
    other = op.create("c2", {"discoverable": 1}, evaluator_config_digest=CFG)
    card, card2 = created["cards"][0], other["cards"][0]
    with pytest.raises(EscrowRefused, match="OBSERVE capability for this campaign"):          # campaign id substitution
        call(t, "observe", token=created["tokens"]["observe"], campaign_id="c2", universe_id=card2["universe_id"], settings=point(card2))
    with pytest.raises(EscrowRefused, match="unknown universe"):                              # universe id substitution
        call(t, "observe", token=created["tokens"]["observe"], campaign_id="c1", universe_id=card2["universe_id"], settings=point(card2))
    with pytest.raises(EscrowRefused, match="SCORE capability"):                              # the proposer's token cannot score
        call(t, "score", token=created["tokens"]["observe"], campaign_id="c1", universe_id=card["universe_id"],
             proposal={"answer": "no_law"}, proposal_digest="0" * 64)
    raw = mac_request({"protocol": PROTOCOL, "op": "observe", "query_id": "cap-1", "last_sequence": -1, "campaign_id": "c1",
                       "universe_id": card["universe_id"], "settings": point(card)}, created["tokens"]["observe"])
    first = json.loads(t(json.dumps(raw).encode()))
    replay = json.loads(t(json.dumps(raw).encode()))                                          # credential replay
    assert first["ok"] and not replay["ok"] and "already used" in replay["refused"]
    leaked = dict(raw, token=created["tokens"]["observe"])
    assert "never sent" in json.loads(t(json.dumps(leaked).encode()))["refused"]
    for junk in (b"\xff\xfe", b"[]", b'{"protocol": "x"}', json.dumps({"protocol": PROTOCOL, "op": "observe"}).encode(),
                 json.dumps({"protocol": PROTOCOL, "op": "observe", "query_id": "../../etc", "last_sequence": -1}).encode()):
        assert json.loads(t(junk))["ok"] is False                                              # malformed: refused, not fatal
    assert OperatorClient(t, t.operator_token).log("c1")["campaign_id"] == "c1"               # still serving


def test_responses_are_signed_and_bound_to_their_request(tmp_path):
    t, op, created = start(tmp_path)
    card = created["cards"][0]
    req = mac_request({"protocol": PROTOCOL, "op": "observe", "query_id": "r1", "last_sequence": -1, "campaign_id": "c1",
                       "universe_id": card["universe_id"], "settings": point(card)}, created["tokens"]["observe"])
    resp = json.loads(t(json.dumps(req).encode()))
    verify_response(resp, escrow_public=t.escrow_public, request=req)
    assert resp["security_boundary"] == SECURITY_LABEL and resp["budget_consumed"] > 0 and isinstance(resp["sequence"], int)
    req2 = mac_request({**{k: v for k, v in req.items() if k != "mac"}, "query_id": "r2"}, created["tokens"]["observe"])
    with pytest.raises(EscrowRefused, match="another request"):                               # a replayed OLD response
        verify_response(resp, escrow_public=t.escrow_public, request=req2)
    forged = dict(resp, observation={**resp["observation"], "y": 0.0})
    with pytest.raises(EscrowRefused, match="not signed"):
        verify_response(forged, escrow_public=t.escrow_public, request=req)
    impostor = InProcessTransport(EscrowService(storage=storage(tmp_path, "impostor")))
    with pytest.raises(EscrowRefused, match="not signed"):                                    # another escrow answering
        ObserveClient(impostor, "c1", created["tokens"]["observe"], escrow_public=t.escrow_public).observe(card["universe_id"], point(card))


def test_storage_is_private_and_outside_the_repository(tmp_path):
    loose = tmp_path / "loose"
    storage(tmp_path, "loose")
    os.chmod(loose, 0o755)
    with pytest.raises(Exception, match="group/others"):
        EscrowStorage(loose)
    inside = os.path.join(os.path.dirname(__file__), "..", "..", "escrow-must-not-live-here")
    try:
        with pytest.raises(Exception, match="inside the repository"):
            EscrowStorage(inside, create=True)
    finally:
        if os.path.isdir(inside):
            for f in os.listdir(inside):
                os.remove(os.path.join(inside, f))
            os.rmdir(inside)


def test_the_subprocess_escrow_resumes_its_journal_but_stays_unproven(tmp_path):
    t = SubprocessTransport(storage=tmp_path / "sub")
    try:
        created = OperatorClient(t, t.operator_token).create("s1", {"discoverable": 1}, evaluator_config_digest=CFG)
        card = created["cards"][0]
        r = ObserveClient(t, "s1", created["tokens"]["observe"]).observe(card["universe_id"], point(card), query_id="s-q1")
        assert r["security_boundary"] == SECURITY_LABEL and r["transport"] == "subprocess"
    finally:
        t.close()
    t2 = SubprocessTransport(storage=tmp_path / "sub")
    try:
        log = OperatorClient(t2, t2.operator_token).log("s1")
        assert [e["op"] for e in log["log"]] == ["create", "observe"] and t2.escrow_public == t.escrow_public
    finally:
        t2.close()
