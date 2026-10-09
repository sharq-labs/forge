"""The Blindfold escrow: hidden worlds behind a limited query/scoring protocol.

::

    DISCOVERY HOST                         ESCROW (this module's EscrowService)
    proposer --observe(token_O)-->  |  hidden generator seeds, hidden laws,
    evaluator --score(token_S)--->  |  hidden evaluation points, scoring
    operator  --create/log------->  |  budget + hash-chained query log

The service has ONE entry point, :meth:`EscrowService.handle`, bytes in and
bytes out.  The proposer side never receives a seed, a law, an evaluation
point or the scoring code's inputs: an observation returns one noisy
measurement at settings it chose inside the allowed box; a score returns an
aggregate verdict once per universe (a sealed, single submission -- no
adaptive probing of the hidden points), and only after it reveals the
universe's kind.

Capabilities: a campaign issues an OBSERVE token (for the proposer) and a
SCORE token (for the evaluator).  Each operation checks the token's
capability.  Every request is logged: campaign, query id, logical order,
query digest, response digest and budget consumed, in a hash chain.

SECURITY: the transports in this repository are a DEVELOPMENT SUBSTITUTE.
:class:`InProcessTransport` shares a process with the proposer; the
:class:`SubprocessTransport` keeps the secrets in a child process but under
the same OS account.  Neither is a proven security boundary, and every
response says so (``security_boundary: SECURITY_BOUNDARY_NOT_PROVEN``).
Filesystem or process separation under one account is not isolation.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import random
import secrets
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .expression import ExpressionRefused, evaluate, structure_digest, validate
from .universe import HiddenWorld, UniverseKind, generate_universe, observe, truth_at

PROTOCOL = "engcore.blindfold.escrow/1"
SECURITY_LABEL = "SECURITY_BOUNDARY_NOT_PROVEN"
ANSWERS = ("law", "no_law", "insufficient_evidence", "indistinguishable", "confounded")
_GENESIS = "0" * 64


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class EscrowRefused(RuntimeError):
    """The escrow refused a request (bad token, capability, budget, second submission, malformed proposal)."""


@dataclass
class _Campaign:
    campaign_id: str
    worlds: dict[str, HiddenWorld]
    order: list[str]
    tokens: dict[str, str]                 # capability -> token
    spent: dict[str, float]
    submitted: dict[str, str]              # universe_id -> proposal digest
    log: list[dict[str, Any]]
    seq: int = 0


class EscrowService:
    """Holds hidden worlds.  Construct it only on the escrow side of a transport."""

    def __init__(self, master_seed: bytes | None = None, *, transport_label: str = "in_process") -> None:
        self._master = master_seed if master_seed is not None else os.urandom(32)
        self._campaigns: dict[str, _Campaign] = {}
        self._transport_label = transport_label

    # -- the single entry point ---------------------------------------------------------------
    def handle(self, request: bytes) -> bytes:
        try:
            req = json.loads(request.decode("utf-8"))
            if req.get("protocol") != PROTOCOL:
                raise EscrowRefused(f"unsupported protocol {req.get('protocol')!r}")
            op = req.get("op")
            handler = {"create": self._create, "observe": self._observe, "score": self._score, "log": self._log}.get(op)
            if handler is None:
                raise EscrowRefused(f"unknown operation {op!r}")
            body = handler(req)
            resp = {"ok": True, **body}
        except EscrowRefused as exc:
            resp = {"ok": False, "refused": str(exc)}
        except (ValueError, KeyError, TypeError) as exc:
            resp = {"ok": False, "refused": f"malformed request: {type(exc).__name__}: {exc}"}
        resp.update(protocol=PROTOCOL, security_boundary=SECURITY_LABEL, transport=self._transport_label)
        return json.dumps(resp, sort_keys=True).encode("utf-8")

    # -- operations ----------------------------------------------------------------------------
    def _seed(self, *parts: str) -> str:
        return hmac.new(self._master, "\n".join(parts).encode(), hashlib.sha256).hexdigest()

    def _create(self, req: Mapping[str, Any]) -> dict[str, Any]:
        cid = str(req["campaign_id"]).strip()
        if not cid or cid in self._campaigns:
            raise EscrowRefused("a campaign id is new and non-empty")
        mix = {UniverseKind(k): int(n) for k, n in dict(req["mix"]).items()}
        if any(n < 0 for n in mix.values()) or sum(mix.values()) < 1:
            raise EscrowRefused("a campaign mix has at least one universe and no negative counts")
        kinds = [k for k, n in sorted(mix.items(), key=lambda kv: kv[0].value) for _ in range(n)]
        random.Random(self._seed(cid, "shuffle")).shuffle(kinds)           # which universe is which kind: hidden
        worlds = {}
        order = []
        for i, kind in enumerate(kinds):
            w = generate_universe(self._seed(cid, "universe", str(i)), kind)
            worlds[w.universe_id] = w
            order.append(w.universe_id)
        tokens = {"observe": secrets.token_hex(24), "score": secrets.token_hex(24)}
        camp = _Campaign(cid, worlds, order, tokens, {u: 0.0 for u in order}, {}, [])
        self._campaigns[cid] = camp
        cards = [worlds[u].public_card() for u in order]
        self._record(camp, "create", {"campaign_id": cid, "mix": {k.value: n for k, n in mix.items()}}, {"universes": order}, 0.0)
        return {"campaign_id": cid, "cards": cards, "tokens": tokens}

    def _campaign(self, req: Mapping[str, Any], capability: str) -> _Campaign:
        camp = self._campaigns.get(str(req.get("campaign_id")))
        if camp is None:
            raise EscrowRefused("unknown campaign")
        if not hmac.compare_digest(str(req.get("token", "")), camp.tokens[capability]):
            raise EscrowRefused(f"the token does not carry the {capability.upper()} capability for this campaign")
        return camp

    def _observe(self, req: Mapping[str, Any]) -> dict[str, Any]:
        camp = self._campaign(req, "observe")
        uid = str(req["universe_id"])
        world = camp.worlds.get(uid)
        if world is None:
            raise EscrowRefused("unknown universe")
        if uid in camp.submitted:
            raise EscrowRefused("this universe's answer is sealed; no further observation")
        if camp.spent[uid] + world.query_cost > world.budget + 1e-9:
            self._record(camp, "observe_refused", req_public(req), {"reason": "budget exhausted"}, 0.0)
            raise EscrowRefused(f"query budget {world.budget} exhausted for {uid}")
        rng = random.Random(self._seed(camp.campaign_id, uid, "obs", str(camp.seq)))
        try:
            obs = observe(world, dict(req["settings"]), rng)
        except ValueError as exc:
            raise EscrowRefused(str(exc)) from exc
        camp.spent[uid] += world.query_cost
        body = {"universe_id": uid, "observation": obs, "budget_remaining": world.budget - camp.spent[uid]}
        receipt = self._record(camp, "observe", req_public(req), body, world.query_cost)
        return {**body, "receipt": receipt}

    def _score(self, req: Mapping[str, Any]) -> dict[str, Any]:
        camp = self._campaign(req, "score")
        uid = str(req["universe_id"])
        world = camp.worlds.get(uid)
        if world is None:
            raise EscrowRefused("unknown universe")
        if uid in camp.submitted:
            raise EscrowRefused("one sealed submission per universe; this one is already scored")
        proposal = dict(req["proposal"])
        pdig = _digest(proposal)
        if str(req.get("proposal_digest")) != pdig:
            raise EscrowRefused("the proposal digest does not match the proposal: the evaluator scores what was stored")
        answer = proposal.get("answer")
        if answer not in ANSWERS:
            raise EscrowRefused(f"answer must be one of {ANSWERS}")
        result: dict[str, Any] = {"universe_id": uid, "answer": answer, "proposal_digest": pdig}
        allowed = {x.name for x in world.inputs} | set(world.covariates)
        laws = []
        if answer == "law":
            laws = [proposal["law"]]
        elif answer == "indistinguishable":
            laws = list(proposal.get("laws", ()))
            if len(laws) < 2:
                raise EscrowRefused("an INDISTINGUISHABLE answer names at least two observationally equivalent laws")
        for law in laws:
            try:
                used = validate(law)
            except ExpressionRefused as exc:
                raise EscrowRefused(f"proposal law refused: {exc}") from exc
            if used - allowed:
                raise EscrowRefused(f"proposal uses unknown variables {sorted(used - allowed)}")
        camp.submitted[uid] = pdig
        rng = random.Random(self._seed(camp.campaign_id, uid, "truth"))
        truths = [truth_at(world, p, rng) for p in world.evaluation_points]
        if laws:
            result["laws"] = [_assess(law, truths, world) for law in laws]
        result["universe_kind"] = world.kind.value                          # revealed only after the sealed submission
        result["tolerance"] = world.tolerance
        result["law_structure_hidden_digest"] = world.law_structure
        receipt = self._record(camp, "score", {"universe_id": uid, "proposal_digest": pdig}, result, 0.0)
        return {**result, "receipt": receipt}

    def _log(self, req: Mapping[str, Any]) -> dict[str, Any]:
        camp = self._campaigns.get(str(req.get("campaign_id")))
        if camp is None:
            raise EscrowRefused("unknown campaign")
        if not any(hmac.compare_digest(str(req.get("token", "")), t) for t in camp.tokens.values()):
            raise EscrowRefused("the log is read with a campaign token")
        return {"campaign_id": camp.campaign_id, "log": list(camp.log), "head": camp.log[-1]["digest"] if camp.log else _GENESIS,
                "spent": dict(camp.spent), "submitted": dict(camp.submitted)}

    def _record(self, camp: _Campaign, op: str, query: Mapping[str, Any], response: Mapping[str, Any], cost: float) -> dict[str, Any]:
        prev = camp.log[-1]["digest"] if camp.log else _GENESIS
        entry = {"campaign_id": camp.campaign_id, "sequence": camp.seq, "op": op, "query_id": str(query.get("query_id", "")),
                 "query_digest": _digest(query), "response_digest": _digest(response), "budget_consumed": cost, "previous": prev}
        entry["digest"] = _digest(entry)
        camp.log.append(entry)
        camp.seq += 1
        return entry


def req_public(req: Mapping[str, Any]) -> dict[str, Any]:
    """The request as logged: never the token."""
    return {k: val for k, val in req.items() if k != "token"}


def _assess(law: Mapping[str, Any], truths: list[tuple[dict[str, float], float]], world: HiddenWorld) -> dict[str, Any]:
    errs = []
    for point, truth in truths:
        if not math.isfinite(truth):
            errs.append(float("inf"))
            continue
        pred = evaluate(law, point)
        errs.append(abs(pred - truth) / abs(truth) if math.isfinite(pred) and truth != 0 else float("inf"))
    errs.sort()
    within = sum(e <= world.tolerance for e in errs) / len(errs)
    median = errs[len(errs) // 2]
    structure = structure_digest(law)
    return {"fraction_within_tolerance": within, "median_relative_error": median if math.isfinite(median) else None,
            "passed": within >= 0.9, "structure_matches_hidden_law": bool(world.law_structure) and structure == world.law_structure,
            "structure_digest": structure}


# ---------------------------------------------------------------------------- transports and clients


class InProcessTransport:
    """Development substitute: the service lives in the proposer's process.  NOT a security boundary."""

    def __init__(self, service: EscrowService | None = None) -> None:
        self._service = service or EscrowService(transport_label="in_process")

    def __call__(self, request: bytes) -> bytes:
        return self._service.handle(request)


class SubprocessTransport:
    """The service in a child process (secrets generated there).  Same OS account: still NOT a proven boundary."""

    def __init__(self) -> None:
        self._proc = subprocess.Popen([sys.executable, "-I", "-m", "engcore.blindfold.escrow_server"], stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, bufsize=0)

    def __call__(self, request: bytes) -> bytes:
        assert self._proc.stdin is not None and self._proc.stdout is not None
        self._proc.stdin.write(request.replace(b"\n", b" ") + b"\n")
        self._proc.stdin.flush()
        line = self._proc.stdout.readline()
        if not line:
            raise EscrowRefused("the escrow process is gone")
        return line

    def close(self) -> None:
        if self._proc.poll() is None:
            self._proc.stdin.close()  # type: ignore[union-attr]
            self._proc.wait(timeout=10)


def call(transport: Callable[[bytes], bytes], op: str, **fields: Any) -> dict[str, Any]:
    resp = json.loads(transport(json.dumps({"protocol": PROTOCOL, "op": op, **fields}, sort_keys=True).encode("utf-8")))
    if not resp.get("ok"):
        raise EscrowRefused(resp.get("refused", "refused"))
    return resp


@dataclass(frozen=True)
class ObserveClient:
    """What a proposer holds: observe within budget.  It cannot score and holds no evaluator token."""

    transport: Callable[[bytes], bytes]
    campaign_id: str
    token: str

    def observe(self, universe_id: str, settings: Mapping[str, float], query_id: str = "") -> dict[str, Any]:
        return call(self.transport, "observe", campaign_id=self.campaign_id, token=self.token, universe_id=universe_id,
                    settings=dict(settings), query_id=query_id)


@dataclass(frozen=True)
class ScoreClient:
    """What the evaluator holds: one sealed submission per universe."""

    transport: Callable[[bytes], bytes]
    campaign_id: str
    token: str

    def score(self, universe_id: str, proposal: Mapping[str, Any]) -> dict[str, Any]:
        return call(self.transport, "score", campaign_id=self.campaign_id, token=self.token, universe_id=universe_id,
                    proposal=dict(proposal), proposal_digest=_digest(dict(proposal)))


__all__ = ["ANSWERS", "EscrowRefused", "EscrowService", "InProcessTransport", "ObserveClient", "PROTOCOL", "SECURITY_LABEL",
           "ScoreClient", "SubprocessTransport", "call"]
