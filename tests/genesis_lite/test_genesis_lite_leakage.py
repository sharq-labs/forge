"""Genesis-lite v0 (BR-16) leakage threat model: each channel is attacked; the result is what is claimed.

An attack that SUCCEEDS is recorded as such (the boundary stays SECURITY_BOUNDARY_NOT_PROVEN); nothing here claims
cryptographic or process-level isolation that it does not demonstrate.
"""

from __future__ import annotations

import gc
import json
import pathlib
import subprocess
import sys

import pytest

from benchmarks.genesis_lite import arms, evaluator, harness
from benchmarks.genesis_lite.answer_key import export_answer_key
from benchmarks.genesis_lite.presentation import PRESENTATIONS
from engcore.blindfold import EscrowRefused, EscrowService, InProcessTransport, run_campaign
from engcore.blindfold.escrow import OperatorClient, ObserveClient
from engcore.blindfold.universe import HiddenWorld

ROOT = pathlib.Path(__file__).resolve().parents[2]
MASTER = bytes(range(32))


def _run(arm, presentation="anonymous", i=0, **kw):
    return harness.run_one(arm, arms.ARMS[arm][0], master_seed=MASTER + bytes([i]), campaign_id=f"gl-leak-{i}",
                           presentation=presentation, **kw)


def _peek(card, client, *, seed=0):
    """Attack: find the hidden world anywhere in the proposer's process memory. The id is a run-private pseudonym, so
    the attack links by the PUBLIC ranges instead (a world is identifiable by them)."""
    ranges = sorted(tuple(x["range"]) for x in card["inputs"])
    for obj in gc.get_objects():
        if isinstance(obj, HiddenWorld) and obj.law is not None and sorted((x.low, x.high) for x in obj.inputs) == ranges:
            names = {(x.low, x.high): x.name for x in obj.inputs}
            shown = {names[tuple(x["range"])]: x["name"] for x in card["inputs"]}
            shown.update(dict(zip(sorted(obj.covariates), card.get("observed_covariates", ()))))

            def rename(node):
                if isinstance(node, dict):
                    return {"var": shown.get(node["var"], node["var"])} if set(node) == {"var"} else {k: rename(v) for k, v in node.items()}
                return [rename(v) for v in node] if isinstance(node, list) else node
            return {"universe_id": card["universe_id"], "answer": "law", "law": rename(obj.law), "rationale": "read from memory"}
    return {"universe_id": card["universe_id"], "answer": "no_law", "rationale": "nothing found in this process"}


def test_l2_in_process_the_hidden_answer_is_reachable_so_the_boundary_stays_not_proven(monkeypatch):
    monkeypatch.setitem(arms.ARMS, "peek", (_peek, "attack", False, "floor"))
    rec = _run("peek")
    disc = [u for u in rec.universes if u["kind"] == "discoverable"][0]
    assert disc["outcome"] == "law_pass"                       # the attack works in-process: this is the leak
    assert rec.security_boundary == "SECURITY_BOUNDARY_NOT_PROVEN"


class _ChildEscrow:
    """The escrow in a child process (this worktree's src, pinned), stdin/stdout JSON lines."""

    def __init__(self) -> None:
        code = (f"import sys; sys.path.insert(0, {str(ROOT / 'src')!r}); "
                "from engcore.blindfold.escrow_server import main; main([])")
        self._proc = subprocess.Popen([sys.executable, "-I", "-c", code], stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0)
        hello = json.loads(self._proc.stdout.readline())
        self.operator_token, self.escrow_public = hello["operator_token"], hello["escrow_public"]

    def __call__(self, request: bytes) -> bytes:
        self._proc.stdin.write(request.replace(b"\n", b" ") + b"\n")
        self._proc.stdin.flush()
        return self._proc.stdout.readline()

    def close(self) -> None:
        self._proc.stdin.close()
        self._proc.wait(timeout=20)


def test_l2_with_the_escrow_in_a_child_process_the_proposer_process_holds_no_hidden_world():
    gc.collect()
    before = {id(o) for o in gc.get_objects() if isinstance(o, HiddenWorld)}
    transport = _ChildEscrow()
    try:
        cfg = harness.CONFIG
        report, _ = run_campaign(transport, campaign_id="gl-child-0", mix=harness.MIX, proposer=lambda c, cl: _peek(c, cl),
                                 proposer_identity={"kind": "attack", "id": "peek"}, config=cfg,
                                 escrow_public=transport.escrow_public)
    finally:
        transport.close()
    assert all(a.answer == "no_law" for a in report.adjudications)     # nothing to read in this process
    gc.collect()
    assert {id(o) for o in gc.get_objects() if isinstance(o, HiddenWorld)} <= before
    assert report.security_boundary == "SECURITY_BOUNDARY_NOT_PROVEN"  # same OS account: still not a proven boundary


def test_l3_refusals_and_errors_carry_no_hidden_information():
    service = EscrowService(master_seed=MASTER, transport_label="in_process")
    t = InProcessTransport(service)
    op = OperatorClient(t, t.operator_token, escrow_public=t.escrow_public)
    created = op.create("gl-err", harness.MIX, evaluator_config_digest=harness.CONFIG.digest)
    client = ObserveClient(t, "gl-err", created["tokens"]["observe"], escrow_public=t.escrow_public)
    messages = []
    for card in created["cards"]:
        uid, xs = card["universe_id"], card["inputs"]
        attempts = [{x["name"]: x["range"][1] * 10 for x in xs},          # outside the box
                    {**{x["name"]: x["range"][0] for x in xs}, "u1": 1.0},  # set a passive covariate
                    {x["name"]: x["range"][0] for x in xs[1:]}]              # leave an input unset
        for i, settings in enumerate(attempts):
            with pytest.raises(EscrowRefused) as exc:
                client.observe(uid, settings, query_id=f"e{i}")
            messages.append((uid, str(exc.value)))
    key = export_answer_key(MASTER, "gl-err", harness.MIX, [c["universe_id"] for c in created["cards"]])
    entries = {e["universe_id"]: e for e in key["universes"]}
    for uid, text in messages:
        e = entries[uid]
        assert e["kind"] not in text
        assert repr(e["tolerance"]) not in text and repr(e["noise_sigma"]) not in text
        audit = evaluator.audit_presented_cards([{"universe_id": uid, "task_text": text}], key)
        assert audit["status"] == "NO_LITERAL_LEAK_FOUND", audit


def test_l4_identifiers_and_card_order_do_not_encode_the_kind():
    orders = set()
    for i in range(12):
        service = EscrowService(master_seed=MASTER + bytes([i]))
        t = InProcessTransport(service)
        op = OperatorClient(t, t.operator_token, escrow_public=t.escrow_public)
        created = op.create(f"gl-ord-{i}", harness.MIX, evaluator_config_digest=harness.CONFIG.digest)
        key = export_answer_key(MASTER + bytes([i]), f"gl-ord-{i}", harness.MIX, [c["universe_id"] for c in created["cards"]])
        assert key["status"] == "DERIVED"
        orders.add(tuple(e["kind"] for e in key["universes"]))
        assert all(e["kind"] not in e["universe_id"] for e in key["universes"])
    assert len(orders) > 1                      # card order is shuffled per campaign, not sorted by kind


def test_l5_no_shared_files_and_no_state_carried_between_runs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    first = _run("monomial_enumeration", "renamed")
    second = _run("monomial_enumeration", "renamed")
    assert [u["outcome"] for u in first.universes] == [u["outcome"] for u in second.universes]
    assert list(tmp_path.iterdir()) == []       # a run writes nothing: no shared temp file or cache to read from


def test_l6_vocabulary_is_assigned_per_campaign_never_per_kind():
    seen = []

    def spy(card, client, *, seed=0):
        seen.append(card)
        return {"universe_id": card["universe_id"], "answer": "no_law"}

    arms.ARMS["_spy"] = (spy, "t", False, "floor")
    try:
        rec = _run("_spy", "trap")
    finally:
        del arms.ARMS["_spy"]
    assert rec.status == "VALID" and len(seen) == len(harness.KINDS)
    outputs = {card["output"]["name"] for card in seen}
    texts = {card["task_text"].replace(card["output"]["name"], "") for card in seen}
    assert len(texts) == 1                        # one wording for every kind in the campaign
    assert outputs <= {"metabolic_rate", "orbital_period", "drag_force", "swing_period"}   # every kind wears trap vocabulary


def test_l7_no_answer_key_or_pilot_root_is_committed():
    gl = ROOT / "benchmarks" / "genesis_lite"
    assert not [p for p in gl.rglob("*") if p.is_file() and ("answer_key" in p.name and p.suffix == ".json")]
    for name in ("genesis_lite_v0.json", "genesis_lite_v0_1.json", "genesis_lite_v0_2.json"):
        prereg = json.loads((gl / "preregistration" / name).read_bytes())
        assert "pilot_root_revealed_hex" not in prereg and len(prereg["pilot_root_commitment_sha256"]) == 64


def test_l8_a_sealed_universe_takes_no_further_observation_and_others_cannot_be_addressed():
    held = {}

    def late(card, client, *, seed=0):
        for uid in held.get("previous", []):     # earlier universes are known only by run-private pseudonyms
            with pytest.raises(EscrowRefused, match="unknown universe"):
                client.observe(uid, {x["name"]: x["range"][0] for x in card["inputs"]},
                               query_id=f"late{len(held['previous'])}")
        held.setdefault("previous", []).append(card["universe_id"])
        return {"universe_id": card["universe_id"], "answer": "no_law"}

    arms.ARMS["_late"] = (late, "t", False, "floor")
    try:
        rec = _run("_late")
    finally:
        del arms.ARMS["_late"]
    assert rec.status == "VALID" and len(held["previous"]) == len(harness.KINDS)
    # and at the escrow itself: after the sealed score, no observation of that universe is answered
    service = EscrowService(master_seed=MASTER)
    t = InProcessTransport(service)
    op = OperatorClient(t, t.operator_token, escrow_public=t.escrow_public)
    created = op.create("gl-seal", harness.MIX, evaluator_config_digest=harness.CONFIG.digest)
    from engcore.blindfold.escrow import ScoreClient
    card = created["cards"][0]
    ScoreClient(t, "gl-seal", created["tokens"]["score"], escrow_public=t.escrow_public).score(card["universe_id"], {"answer": "no_law"})
    with pytest.raises(EscrowRefused, match="sealed"):
        ObserveClient(t, "gl-seal", created["tokens"]["observe"], escrow_public=t.escrow_public).observe(
            card["universe_id"], {x["name"]: x["range"][0] for x in card["inputs"]}, query_id="after")
