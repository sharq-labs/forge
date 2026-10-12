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
    EscrowIntegrityError,
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
    op = OperatorClient(t, t.operator_token, escrow_public=t.escrow_public)
    created = op.create("c1", {"discoverable": 2}, evaluator_config_digest=CFG)
    return t, op, created


def point(card):
    return {x["name"]: x["range"][0] for x in card["inputs"]}


def test_budgets_submissions_and_query_ids_survive_an_escrow_restart(tmp_path):
    t, op, created = start(tmp_path)
    card = created["cards"][0]
    obs = ObserveClient(t, "c1", created["tokens"]["observe"], escrow_public=t.escrow_public)
    first = obs.observe(card["universe_id"], point(card), query_id="a1")
    ScoreClient(t, "c1", created["tokens"]["score"], escrow_public=t.escrow_public).score(created["cards"][1]["universe_id"], {"answer": "no_law"})
    before = op.log("c1")
    # --- restart: a NEW service from the same private storage
    t2 = InProcessTransport(EscrowService(storage=EscrowStorage(tmp_path / "escrow")))
    assert t2.operator_token == t.operator_token and t2.escrow_public == t.escrow_public
    after = OperatorClient(t2, t2.operator_token, escrow_public=t2.escrow_public).log("c1")
    assert after["spent"] == before["spent"] and after["submitted"] == before["submitted"] and after["head"] == before["head"]
    assert verify_log(after["log"]) == after["head"]
    obs2 = ObserveClient(t2, "c1", created["tokens"]["observe"], escrow_public=t2.escrow_public)              # the same capability works after restart
    again = obs2.observe(card["universe_id"], point(card), query_id="a2")
    assert again["budget_remaining"] == first["budget_remaining"] - again["budget_consumed"]   # NOT reset
    with pytest.raises(EscrowRefused, match="already used"):
        obs2.observe(card["universe_id"], point(card), query_id="a1")        # a pre-restart query id stays used
    with pytest.raises(EscrowRefused, match="one sealed submission"):
        ScoreClient(t2, "c1", created["tokens"]["score"], escrow_public=t2.escrow_public).score(created["cards"][1]["universe_id"], {"answer": "law", "law": {"c": 1.0}})
    with pytest.raises(EscrowRefused, match="exhausted"):
        for i in range(500):                                                   # over-querying stops at the persisted budget
            obs2.observe(card["universe_id"], point(card), query_id=f"x{i}")


def test_a_tampered_journal_refuses_to_start_and_a_truncated_one_is_caught_by_the_client(tmp_path):
    t, op, created = start(tmp_path)
    card = created["cards"][0]
    obs = ObserveClient(t, "c1", created["tokens"]["observe"], escrow_public=t.escrow_public)
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
    with pytest.raises(EscrowRefused, match="not authenticated"):          # campaign id substitution
        call(t, "observe", token=created["tokens"]["observe"], campaign_id="c2", universe_id=card2["universe_id"], settings=point(card2))
    with pytest.raises(EscrowRefused, match="unknown universe"):                              # universe id substitution
        call(t, "observe", token=created["tokens"]["observe"], campaign_id="c1", universe_id=card2["universe_id"], settings=point(card2))
    with pytest.raises(EscrowRefused, match="not authenticated"):                              # the proposer's token cannot score
        call(t, "score", token=created["tokens"]["observe"], campaign_id="c1", universe_id=card["universe_id"],
             proposal={"answer": "no_law"}, proposal_digest="0" * 64)
    raw = mac_request({"protocol": PROTOCOL, "op": "observe", "query_id": "cap-1", "last_sequence": -1, "last_head": "0" * 64, "campaign_id": "c1",
                       "universe_id": card["universe_id"], "settings": point(card)}, created["tokens"]["observe"])
    first = json.loads(t(json.dumps(raw).encode()))
    replay = json.loads(t(json.dumps(raw).encode()))                                          # credential replay
    assert first["ok"] and not replay["ok"] and "already used" in replay["refused"]
    leaked = dict(raw, token=created["tokens"]["observe"])
    assert "never sent" in json.loads(t(json.dumps(leaked).encode()))["refused"]
    for junk in (b"\xff\xfe", b"[]", b'{"protocol": "x"}', json.dumps({"protocol": PROTOCOL, "op": "observe"}).encode(),
                 json.dumps({"protocol": PROTOCOL, "op": "observe", "query_id": "../../etc", "last_sequence": -1}).encode()):
        assert json.loads(t(junk))["ok"] is False                                              # malformed: refused, not fatal
    assert OperatorClient(t, t.operator_token, escrow_public=t.escrow_public).log("c1")["campaign_id"] == "c1"               # still serving


def test_responses_are_signed_and_bound_to_their_request(tmp_path):
    t, op, created = start(tmp_path)
    card = created["cards"][0]
    req = mac_request({"protocol": PROTOCOL, "op": "observe", "query_id": "r1", "last_sequence": -1, "last_head": "0" * 64, "campaign_id": "c1",
                       "universe_id": card["universe_id"], "settings": point(card)}, created["tokens"]["observe"])
    resp = json.loads(t(json.dumps(req).encode()))
    verify_response(resp, escrow_public=t.escrow_public, request=req)
    assert resp["security_boundary"] == SECURITY_LABEL and resp["budget_consumed"] > 0 and isinstance(resp["sequence"], int)
    req2 = mac_request({**{k: v for k, v in req.items() if k != "mac"}, "query_id": "r2"}, created["tokens"]["observe"])
    with pytest.raises(EscrowIntegrityError, match="another request"):                               # a replayed OLD response
        verify_response(resp, escrow_public=t.escrow_public, request=req2)
    forged = dict(resp, observation={**resp["observation"], "y": 0.0})
    with pytest.raises(EscrowIntegrityError, match="not signed"):
        verify_response(forged, escrow_public=t.escrow_public, request=req)
    impostor = InProcessTransport(EscrowService(storage=storage(tmp_path, "impostor")))
    with pytest.raises(EscrowIntegrityError, match="not signed"):                                    # another escrow answering
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
        created = OperatorClient(t, t.operator_token, escrow_public=t.escrow_public).create("s1", {"discoverable": 1}, evaluator_config_digest=CFG)
        card = created["cards"][0]
        r = ObserveClient(t, "s1", created["tokens"]["observe"], escrow_public=t.escrow_public).observe(card["universe_id"], point(card), query_id="s-q1")
        assert r["security_boundary"] == SECURITY_LABEL and r["transport"] == "subprocess"
    finally:
        t.close()
    t2 = SubprocessTransport(storage=tmp_path / "sub")
    try:
        log = OperatorClient(t2, t2.operator_token, escrow_public=t2.escrow_public).log("s1")
        assert [e["op"] for e in log["log"]] == ["create", "observe"] and t2.escrow_public == t.escrow_public
    finally:
        t2.close()


# ---------------------------------------------------------------------------- checkpoint-B review


def _restart(tmp_path, name="escrow"):
    return InProcessTransport(EscrowService(storage=EscrowStorage(tmp_path / name)))


def test_a_rolled_back_or_restored_journal_is_caught_by_a_durable_client_checkpoint(tmp_path):     # B-H1
    from engcore.blindfold.escrow import EscrowCheckpoint
    t, op, created = start(tmp_path)
    journal = tmp_path / "escrow" / "journal.jsonl"
    backup = journal.read_bytes()                                          # the operator's "backup" right after create
    card, score_uid = created["cards"][0], created["cards"][1]["universe_id"]
    ck = EscrowCheckpoint(tmp_path / "evaluator.checkpoint")               # the evaluator's own file, not the escrow's
    ScoreClient(t, "c1", created["tokens"]["score"], escrow_public=t.escrow_public, checkpoint=ck).score(score_uid, {"answer": "no_law"})
    journal.write_bytes(backup)                                            # restore the old backup: the submission "never happened"
    t2 = _restart(tmp_path)
    fresh_ck = EscrowCheckpoint(tmp_path / "evaluator.checkpoint")         # a RESTARTED evaluator reads its checkpoint back
    with pytest.raises(EscrowIntegrityError, match="rolled back"):
        ScoreClient(t2, "c1", created["tokens"]["score"], escrow_public=t2.escrow_public, checkpoint=fresh_ck).score(
            score_uid, {"answer": "law", "law": {"c": 1.0}})
    # residual, stated: a client WITHOUT a checkpoint cannot tell (the escrow alone cannot detect a restored backup)
    ScoreClient(t2, "c1", created["tokens"]["score"], escrow_public=t2.escrow_public).score(score_uid, {"answer": "no_law"})


def test_a_replaced_history_at_the_same_length_is_refused(tmp_path):                              # B-H1
    from engcore.blindfold.escrow import EscrowCheckpoint
    t, op, created = start(tmp_path)
    card = created["cards"][0]
    ck = EscrowCheckpoint(tmp_path / "proposer.checkpoint")
    obs = ObserveClient(t, "c1", created["tokens"]["observe"], escrow_public=t.escrow_public, checkpoint=ck)
    journal = tmp_path / "escrow" / "journal.jsonl"
    backup = journal.read_bytes()
    obs.observe(card["universe_id"], point(card), query_id="h1")
    journal.write_bytes(backup)
    t2 = _restart(tmp_path)
    other = ObserveClient(t2, "c1", created["tokens"]["observe"], escrow_public=t2.escrow_public)
    other.observe(card["universe_id"], {k: v * 1.01 for k, v in point(card).items()}, query_id="h2")   # same length, other entry
    with pytest.raises(EscrowIntegrityError, match="replaced|rolled back"):
        ObserveClient(t2, "c1", created["tokens"]["observe"], escrow_public=t2.escrow_public,
                      checkpoint=EscrowCheckpoint(tmp_path / "proposer.checkpoint")).observe(card["universe_id"], point(card), query_id="h3")


def test_a_deleted_journal_refuses_to_start(tmp_path):                                              # B-H1
    start(tmp_path)
    (tmp_path / "escrow" / "journal.jsonl").unlink()
    with pytest.raises(EscrowRefused, match="journal was deleted"):
        EscrowStorage(tmp_path / "escrow", create=True)
    (tmp_path / "escrow" / "journal.jsonl").write_text("{torn\n")
    with pytest.raises(EscrowRefused, match="torn or edited"):
        EscrowStorage(tmp_path / "escrow")


def test_noise_after_a_rollback_is_not_reproduced_for_another_request(tmp_path):                  # B-H1
    t, op, created = start(tmp_path)
    card = created["cards"][0]
    journal = tmp_path / "escrow" / "journal.jsonl"
    backup = journal.read_bytes()
    a = ObserveClient(t, "c1", created["tokens"]["observe"], escrow_public=t.escrow_public).observe(card["universe_id"], point(card))
    journal.write_bytes(backup)
    t2 = _restart(tmp_path)
    b = ObserveClient(t2, "c1", created["tokens"]["observe"], escrow_public=t2.escrow_public).observe(card["universe_id"], point(card))
    assert a["sequence"] == b["sequence"] and a["observation"]["y"] != b["observation"]["y"]


def test_a_replaced_universe_refuses_to_start(tmp_path, monkeypatch):                              # B-H2
    start(tmp_path)
    import dataclasses

    import engcore.blindfold.escrow as esc
    real = esc.generate_universe
    monkeypatch.setattr(esc, "generate_universe", lambda seed, kind: dataclasses.replace(real(seed, kind), budget=10 ** 6))
    with pytest.raises(EscrowRefused, match="no longer re-derive"):
        _restart(tmp_path)


def test_unauthenticated_requests_never_touch_a_campaign(tmp_path):                                # B-M1
    t, op, created = start(tmp_path)
    card = created["cards"][0]
    head = op.log("c1")["head"]
    replies = []
    for cid in ("c1", "no-such-campaign"):
        req = mac_request({"protocol": PROTOCOL, "op": "observe", "query_id": "u1", "last_sequence": -1, "last_head": "0" * 64,
                           "campaign_id": cid, "universe_id": card["universe_id"], "settings": point(card)}, "forged")
        replies.append(json.loads(t(json.dumps(req).encode())))
    assert all(r["refused"] == "the request is not authenticated" for r in replies)          # known and unknown look alike
    assert all("sequence" not in r and "head" not in r for r in replies)
    after = op.log("c1")
    assert after["head"] == head and after["auth_failures"] == 2


def test_a_log_read_is_single_use_across_restarts(tmp_path):                                       # B-M2
    t, op, created = start(tmp_path)
    req = mac_request({"protocol": PROTOCOL, "op": "log", "query_id": "L1", "last_sequence": -1, "last_head": "0" * 64,
                       "campaign_id": "c1"}, t.operator_token)
    assert json.loads(t(json.dumps(req).encode()))["ok"]
    assert "already used" in json.loads(t(json.dumps(req).encode()))["refused"]
    t2 = _restart(tmp_path)
    assert "already used" in json.loads(t2(json.dumps(req).encode()))["refused"]


def test_clients_always_pin_the_escrow_key_and_integrity_is_not_a_refusal(tmp_path):              # B-M3, B-M7
    from engcore.blindfold import EvaluatorConfig, RoleRefused
    from engcore.blindfold.baselines import always_law
    from engcore.blindfold.roles import run_campaign
    t, op, created = start(tmp_path)
    for make in (lambda: OperatorClient(t, t.operator_token, escrow_public=""),
                 lambda: ObserveClient(t, "c1", created["tokens"]["observe"], escrow_public=None)):
        with pytest.raises(EscrowIntegrityError, match="pins the escrow"):
            make()
    with pytest.raises(RoleRefused, match="pins the escrow"):
        run_campaign(t, campaign_id="x", mix={"discoverable": 1}, proposer=always_law, proposer_identity={"id": "a"},
                     config=EvaluatorConfig("e", "1"))
    assert not issubclass(EscrowIntegrityError, EscrowRefused)
    impostor = InProcessTransport(EscrowService(storage=storage(tmp_path, "impostor")))
    card = created["cards"][0]
    with pytest.raises(EscrowIntegrityError):              # a substituted escrow ends collection loudly, never as "budget spent"
        always_law(card, ObserveClient(impostor, "c1", created["tokens"]["observe"], escrow_public=t.escrow_public))


def test_the_escrow_never_asserts_a_verified_boundary_and_query_keys_are_unambiguous(tmp_path):    # B-M4, B-L2
    with pytest.raises(EscrowRefused, match="never a flag"):
        EscrowService(security_boundary="OS_ISOLATION_BOUNDARY_VERIFIED")
    t, op, created = start(tmp_path)
    card = created["cards"][0]
    with pytest.raises(EscrowRefused, match="fresh query id"):
        call(t, "observe", token=created["tokens"]["observe"], campaign_id="c1", universe_id=card["universe_id"], settings=point(card),
             query_id="a:b", escrow_public=t.escrow_public)
    with pytest.raises(EscrowRefused, match="campaign id"):
        op.create("bad\nid", {"discoverable": 1}, evaluator_config_digest=CFG)



class _StubbornProcess:
    """A child that ignores the graceful request: its first wait times out."""

    def __init__(self) -> None:
        import io

        self.stdin = io.BytesIO()
        self.killed = False
        self.waits = 0

    def poll(self):
        return None if not self.killed else -9

    def terminate(self) -> None:
        pass

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout=None):
        import subprocess

        self.waits += 1
        if not self.killed:
            raise subprocess.TimeoutExpired("escrow_server", timeout)
        return -9


def test_closing_a_transport_whose_process_ignores_eof_kills_it():
    from engcore.blindfold.escrow import SubprocessTransport

    transport = object.__new__(SubprocessTransport)
    transport._proc = _StubbornProcess()
    transport.close()  # used to raise TimeoutExpired and leave the process running
    assert transport._proc.killed and transport._proc.stdin.closed


def test_stopping_an_isolated_escrow_whose_process_ignores_sigterm_kills_it():
    import socket

    from engcore.blindfold.isolation import IsolatedEscrow

    escrow = object.__new__(IsolatedEscrow)
    escrow._proc = _StubbornProcess()
    escrow._discovery_end, other = socket.socketpair()
    try:
        escrow.stop()
    finally:
        other.close()
    assert escrow._proc.killed
