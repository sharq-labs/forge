"""Measure the overhead of the Big Rocks authority / escrow layers (median and p95, milliseconds).

    python tools/authority_escrow_performance.py [--n 200] [--json PATH]

Timed operations (each on THIS machine, warm, single process; the escrow cases use a real private storage directory
with fsync'd journal appends where stated):

* ed25519 signature verification; ledger append (sign + verify + flock'd, fsync'd JSONL append); ledger open
  (re-verify every event); issuer/role registry lookup; issuer-bound evidence verification (``verify_evidence``);
* ``assess_credibility`` with and without the authority ledger (the same claim);
* durable falsifier sealing (``DurableCampaign.seal``: journaled attestation + head check);
* escrow request handling: authentication + budget check + signing, in memory and with fsync'd storage; client-side
  response verification.

These are timings, not a benchmark claim: nothing here is compared against a threshold.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import statistics
import sys
import tempfile
import time
from collections.abc import Callable
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "src"), str(REPO)]


def _stats(samples: list[float]) -> dict[str, float]:
    ms = sorted(x * 1e3 for x in samples)
    return {"n": len(ms), "median_ms": round(statistics.median(ms), 4), "p95_ms": round(ms[max(0, int(0.95 * len(ms)) - 1)], 4)}


def _time(fn: Callable[[int], Any], n: int) -> dict[str, float]:
    out = []
    for i in range(n):
        t0 = time.perf_counter()
        fn(i)
        out.append(time.perf_counter() - t0)
    return _stats(out)


def measure(n: int = 200) -> dict[str, Any]:
    from engcore.authority import (
        AuthorityLedger,
        EphemeralKeyProvider,
        FileLedgerStore,
        Role,
        verify_evidence,
        verify_signature,
    )
    from engcore.blindfold.escrow import (
        EscrowService,
        EscrowStorage,
        InProcessTransport,
        ObserveClient,
        OperatorClient,
        verify_response,
    )
    from engcore.claims.credibility_vector import record_digest
    from engcore.claims.durable_campaign import DurableCampaign
    from engcore.claims.falsification import CriterionKind, EvidenceSource, Falsifier
    from tests.authority_helpers import World
    from tests.foundations.test_authority_integrity import CONV, CTX, RESULT, assess

    res: dict[str, Any] = {}
    keys = EphemeralKeyProvider()
    s = keys.signer("x")
    msg = b"forge" * 40
    sig = s.sign(msg)
    res["signature_verify"] = _time(lambda _i: verify_signature(s.public_hex, sig, msg), n)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = pathlib.Path(tmp)
        root = keys.signer("root")
        led = AuthorityLedger.create(FileLedgerStore(tmp_p / "a.jsonl"), ledger_id="perf", profile="test", root=root)
        led.register_issuer(root, "exec", keys.signer("exec").possession("perf", "exec"), roles=[Role.EXECUTOR])
        w = World()
        w.attest(CONV, RESULT, CTX)
        receipt = w.receipt(RESULT, CTX)
        # ledger append: one signed receipt attestation per call (different subject each time)
        from engcore.claims.attestation import attest_receipt
        from tests.authority_helpers import receipt_for
        res["ledger_append_attest"] = _time(lambda i: attest_receipt(led, keys.signer("exec"), "exec",
                                                                     receipt_for(hashlib.sha256(str(i).encode()).hexdigest()),
                                                                     context_digest=CTX), n)
        anchor = led.anchor()
        res["ledger_open_reverify"] = {**_time(lambda _i: AuthorityLedger.open(FileLedgerStore(tmp_p / "a.jsonl"), anchor=anchor),
                                                max(5, n // 20)), "events": led.length}
        res["registry_role_lookup"] = _time(lambda i: led.role_at("exec", Role.EXECUTOR, i % led.length), n)
        rd = record_digest(CONV)
        res["issuer_bound_evidence_verify"] = _time(lambda _i: verify_evidence(
            w.ledger, record_kind="validation_check", record_digest=rd, subject_digest=RESULT, context_digest=CTX,
            roles=[Role.NUMERICAL_VERIFICATION]), n)
        assert receipt is not None
        res["assess_credibility_unattested"] = _time(lambda _i: assess(None), n)
        res["assess_credibility_issuer_bound"] = _time(lambda _i: assess(w), max(10, n // 4))

        # durable sealing
        from engcore.blindfold.expression import c, mul, pw, structure_digest, v
        from engcore.sria.decision import (
            Hypothesis,
            HypothesisKind,
            HypothesisPrediction,
        )
        led.register_issuer(root, "exposure", keys.signer("exposure").possession("perf", "exposure"), roles=[Role.EXPOSURE])
        camp = DurableCampaign.start(led, keys, issuer_id="exposure", campaign_id="perf", authority_id="lab", context_digest=CTX)
        law = mul(c(2.0), pw(v("x"), 1.37))
        hs = []
        for i in range(n):
            h = Hypothesis(hypothesis_id=f"h{i}", model_ref="m", kind=HypothesisKind.EQUATION, statement="s",
                           statement_payload={"expression": law}, structure_digest=structure_digest(law),
                           predictions=(HypothesisPrediction("y", "m", "c"),), falsifier_refs=(f"f{i}@v1",))
            hs.append((h, camp.register(h)))
        res["durable_falsifier_seal"] = _time(lambda i: camp.seal(Falsifier(
            f"f{i}", hs[i][0].hypothesis_id, hs[i][0].content_digest, "y", "m", {"x": 2.0}, EvidenceSource.MEASUREMENT_RECORD,
            CriterionKind.PREDICTION_DEVIATION, {"k": 3.0, "predicted": 5.17, "prediction_uncertainty": 0.01, "resolution": 0.2}),
            hs[i][1]), n)
        camp.close()

        # escrow
        for label, svc in (("memory", EscrowService()), ("storage_fsync", EscrowService(storage=EscrowStorage(tmp_p / "esc", create=True)))):
            t = InProcessTransport(svc)
            op = OperatorClient(t, t.operator_token, escrow_public=t.escrow_public)
            cr = op.create(f"perf-{label}", {"discoverable": 24}, evaluator_config_digest="a" * 64)
            obs = ObserveClient(t, f"perf-{label}", cr["tokens"]["observe"], escrow_public=t.escrow_public)
            slots = [(card["universe_id"], {x["name"]: x["range"][0] for x in card["inputs"]})
                     for card in cr["cards"] for _k in range(int(card["query_budget"]))]
            res[f"escrow_observe_roundtrip_{label}"] = _time(lambda i, o=obs, sl=slots: o.observe(*sl[i]), min(n, len(slots)))
        from engcore.blindfold.escrow import PROTOCOL, mac_request
        req = mac_request({"protocol": PROTOCOL, "op": "log", "query_id": "perf-x", "last_sequence": -1, "last_head": "0" * 64,
                           "campaign_id": f"perf-{label}"}, t.operator_token)
        resp = json.loads(t(json.dumps(req).encode()))
        res["escrow_response_verify_client"] = _time(lambda _i: verify_response(resp, escrow_public=t.escrow_public, request=req), n)
        bad = mac_request({**{k: v for k, v in req.items() if k != "mac"}, "query_id": "perf-bad"}, "forged")
        res["escrow_unauthenticated_refusal"] = _time(lambda _i: t(json.dumps(bad).encode()), n)
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    res = measure(a.n)
    text = json.dumps(res, indent=2, sort_keys=True)
    if a.json:
        pathlib.Path(a.json).write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
