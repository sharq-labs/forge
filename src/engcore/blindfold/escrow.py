"""The Blindfold escrow: hidden worlds behind a limited query/scoring protocol.

::

    DISCOVERY HOST                                ESCROW (this module's EscrowService)
    proposer  --observe(token_O)-------------> |  hidden generator seeds, hidden laws,
    evaluator --score(token_S)---------------> |  hidden evaluation points, scoring
    operator  --create/log(operator token)---> |  budget + hash-chained query log

The service has ONE entry point, :meth:`EscrowService.handle`, bytes in and
bytes out.  The proposer side never receives a seed, a law, an evaluation
point or the scoring code's inputs: an observation returns one noisy
measurement at settings it chose inside the allowed box; a score returns an
aggregate verdict once per universe (a sealed, single submission -- no
adaptive probing of the hidden points), and only after it reveals the
universe's kind.

Capabilities and authentication (protocol v4).  The OPERATOR credential and each campaign's OBSERVE (proposer) and
SCORE (evaluator) capabilities are DERIVED from the escrow's master secret, so they survive a restart.  A credential is
never sent: every request carries a MAC keyed by it over every other field -- campaign id, universe id, operation, a
single-use query id and the last log sequence AND head the sender saw -- and the escrow refuses an unauthenticated,
replayed (query id already used for that operation and universe, reads included) or rolled-back / replaced (the
sender saw a later sequence, or another head at that sequence) request.  A request is AUTHENTICATED before any
campaign state is consulted: an unauthenticated one gets one uniform refusal, carries no sequence or head, and is
counted service-wide (``auth_failures`` in the operator's log read), never written into a campaign's chain.  Every
response is SIGNED by the escrow's ed25519 identity and binds the request digest, the budget consumed, the log
sequence and head; every client PINS the escrow's public key (there is no unverified client), so a forged,
substituted or replayed response is an :class:`EscrowIntegrityError` -- never mistaken for a refusal.

Persistence.  With :class:`EscrowStorage` (an escrow-owned 0700 directory outside the repository: master secret,
signing key, journal) every logged request is journaled BEFORE it is answered, in a chain MAC-keyed by the master
secret, and a restart rebuilds campaigns, budgets spent, sealed submissions and used query ids from it: nothing
resets.  An edited, reordered or spliced journal refuses to start; so does a missing journal next to existing keys
(deleted), and a journal whose universes no longer re-derive to the digests journaled at creation (a generator change
or a replaced universe).  A truncated or restored-from-backup tail is NOT detectable by the escrow alone: it is caught
at the next request of any client holding a later signed checkpoint (:class:`EscrowCheckpoint`, which the operator
and evaluator keep); a client without one cannot detect it.  Observation noise in a stored escrow is seeded by the
log position AND the request digest, so a request re-asked after a rollback does not reproduce earlier noise.

Log.  Every authenticated request that names a known campaign is logged -- refusals included -- with campaign, query
id, logical order, query digest, response digest and budget consumed, in a hash chain.  Query and response digests are
HMAC-keyed by the escrow's secret, so a log reader cannot brute-force a campaign mix or confirm a guessed answer
against them; no credential is ever logged.  A log READ is not a chain entry, but its query id is spent durably.

SECURITY: :class:`InProcessTransport` shares a process (and so all memory) with the proposer, and
:class:`SubprocessTransport` keeps the secrets in a child process under the same OS account; neither is a security
boundary.  EVERY response says ``security_boundary: SECURITY_BOUNDARY_NOT_PROVEN``: the escrow cannot know its own
deployment, and no flag can make it say more.  A verified level is a property of a deployment, stated by the
isolation demo's record bound to this escrow's key id (:mod:`.isolation`: OS_ISOLATION_BOUNDARY_VERIFIED at most).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import random
import re
import secrets
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .expression import ExpressionRefused, evaluate, structure_digest, validate
from .universe import (
    GENERATOR_TAG,
    HiddenWorld,
    UniverseKind,
    generate_universe,
    observe,
    truth_at,
)

PROTOCOL = "engcore.blindfold.escrow/4"
SECURITY_LABEL = "SECURITY_BOUNDARY_NOT_PROVEN"
ANSWERS = ("law", "no_law", "insufficient_evidence", "indistinguishable", "confounded")
#: what the EVALUATOR may submit: a proposer answer, or the record that the proposal was inadmissible (no answer)
SCORED_ANSWERS = ANSWERS + ("inadmissible",)
MAX_UNIVERSES = 256
PASS_FRACTION = 0.9
PAIR_DIFFER_FRACTION = 0.5
_GENESIS = "0" * 64
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_QUERY_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")             # no ':' -- the query key is "op:universe:qid"
_CAMPAIGN_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_JOURNAL_TAG = b"forge.blindfold.escrow-journal/1\n"
_RESPONSE_TAG = b"forge.blindfold.escrow-response/4\n"
_UNAUTHENTICATED = "the request is not authenticated"
#: the request fields that authentication covers: everything except the MAC itself
_ROLE_OF_OP = {"create": "operator", "log": "operator", "observe": "observe", "score": "score"}


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def request_digest(req: Mapping[str, Any]) -> str:
    """What a request MAC and a response's ``request_digest`` bind: every field but the MAC."""
    return _digest({k: v for k, v in req.items() if k != "mac"})


def mac_request(req: dict[str, Any], key: str) -> dict[str, Any]:
    req["mac"] = hmac.new(str(key).encode(), request_digest(req).encode(), hashlib.sha256).hexdigest()
    return req


def response_signed_bytes(resp: Mapping[str, Any]) -> bytes:
    return _RESPONSE_TAG + json.dumps({k: v for k, v in resp.items() if k != "signature"}, sort_keys=True,
                                      separators=(",", ":")).encode()


class EscrowRefused(RuntimeError):
    """The escrow refused a request (bad token, capability, budget, second submission, malformed proposal)."""


class EscrowIntegrityError(RuntimeError):
    """The ANSWER cannot be trusted: a response not signed by the pinned escrow, answering another request, or an
    escrow whose log went backwards / was replaced.  Deliberately NOT an EscrowRefused: a caller that stops on a
    refusal (an exhausted budget) must never treat a forged or rolled-back escrow as one."""


def is_budget_refusal(exc: BaseException) -> bool:
    return isinstance(exc, EscrowRefused) and str(exc).startswith("query budget ") and " exhausted for " in str(exc)


@dataclass
class _Campaign:
    campaign_id: str
    worlds: dict[str, HiddenWorld]
    order: list[str]
    tokens: dict[str, str]                 # capability -> token (DERIVED from the master secret: survives restart)
    spent: dict[str, float]
    submitted: dict[str, str]              # universe_id -> proposal digest
    log: list[dict[str, Any]]
    seq: int = 0
    query_ids: set[str] | None = None


class EscrowStorage:
    """Escrow-OWNED private storage: one directory (mode 0700, outside the repository checkout) holding

    * ``escrow.secret`` -- the master secret (hidden generator seeds, capability tokens and log keys derive from it);
    * ``escrow.ed25519.pem`` -- the escrow's signing identity (every response is signed);
    * ``journal.jsonl`` -- every logged request, with the state change it made, in a chain MAC-keyed by the master
      secret, so the escrow detects an edited, reordered or spliced journal on restart.

    The journal begins with a GENESIS record (schema, a random canary the isolation demo searches for); keys without a
    journal refuse to start (the journal was deleted).  The Discovery side never mounts or reads this directory (see
    :mod:`.isolation`).  Truncation of the journal TAIL or a restored backup is caught by a CLIENT holding a later
    signed checkpoint (:class:`EscrowCheckpoint`), not by the escrow."""

    def __init__(self, directory: str | os.PathLike[str], *, create: bool = False) -> None:
        import pathlib

        from ..authority import DirectoryKeyProvider, generate_key_files
        d = pathlib.Path(directory)
        fresh = create and not (d / "escrow.ed25519.pem").exists()
        if fresh:
            generate_key_files(d, "escrow", secret=True)
        self._keys = DirectoryKeyProvider(d)                # 0700 directory, 0600 files, outside the repository
        self.directory = d.resolve()
        self.master = self._keys.secret("escrow")
        self.identity = self._keys.signer("escrow")
        self.journal_path = self.directory / "journal.jsonl"
        self.canary = ""
        if fresh:
            self.append({"genesis": {"schema": "forge.blindfold.escrow-storage/1", "canary": secrets.token_hex(32)}})
        if not self.journal_path.exists():
            raise EscrowRefused("the escrow's keys exist but its journal does not: the journal was deleted; refusing to start "
                                "a fresh history under the same identity")
        self.read()

    def _mac(self, previous: str, record: Mapping[str, Any]) -> str:
        blob = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str).encode()
        return hmac.new(self.master, _JOURNAL_TAG + previous.encode() + b"\n" + blob, hashlib.sha256).hexdigest()

    def read(self) -> list[dict[str, Any]]:
        if not self.journal_path.exists():
            return []
        out, prev = [], _GENESIS
        for n, line in enumerate(ln for ln in self.journal_path.read_text(encoding="utf-8").splitlines() if ln.strip()):
            try:
                row = json.loads(line)
            except ValueError as exc:
                raise EscrowRefused(f"escrow journal line {n} is not a record (torn or edited): refusing to start") from exc
            if not isinstance(row, dict) or set(row) != {"record", "mac"} \
                    or not hmac.compare_digest(str(row["mac"]), self._mac(prev, row["record"])):
                raise EscrowRefused(f"escrow journal line {n} fails its keyed chain: the journal was edited, reordered or spliced")
            if n == 0:
                if not isinstance(row["record"], dict) or "genesis" not in row["record"]:
                    raise EscrowRefused("the escrow journal does not begin with its genesis record")
                self.canary = str(row["record"]["genesis"].get("canary", ""))
            else:
                out.append(row["record"])
            prev = row["mac"]
        self._head = prev
        return out

    def append(self, record: Mapping[str, Any]) -> None:
        prev = getattr(self, "_head", None)
        if prev is None:
            self.read()
            prev = getattr(self, "_head", _GENESIS)
        mac = self._mac(prev, record)
        fd = os.open(self.journal_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"record": record, "mac": mac}, sort_keys=True, default=str) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        self._head = mac


class EscrowService:
    """Holds hidden worlds.  Construct it only on the escrow side of a transport.

    With ``storage`` (an :class:`EscrowStorage`) the master secret and the signing identity are the storage's, and the
    whole state -- campaigns, budgets spent, sealed submissions, used query ids, the log -- is REBUILT from the journal
    on construction: a restart resets nothing.  Without it (development) the secret is random and the identity is a
    test key; nothing survives the process.  ``security_boundary`` must be ``SECURITY_BOUNDARY_NOT_PROVEN``: the escrow
    states what it can know about itself, and a verified level is never a flag (:mod:`.isolation`)."""

    def __init__(self, master_seed: bytes | None = None, *, transport_label: str = "in_process", storage: EscrowStorage | None = None,
                 security_boundary: str = SECURITY_LABEL) -> None:
        if storage is not None:
            if master_seed is not None:
                raise EscrowRefused("a stored escrow's secret is its storage's; no seed is supplied beside it")
            self._master, self._identity = storage.master, storage.identity
        else:
            from ..authority import EphemeralKeyProvider
            self._master = master_seed if master_seed is not None else os.urandom(32)
            self._identity = EphemeralKeyProvider().signer("escrow")
        if security_boundary != SECURITY_LABEL:
            raise EscrowRefused("an escrow states SECURITY_BOUNDARY_NOT_PROVEN about itself; a verified boundary is the "
                                "isolation demo's record bound to this escrow's key id, never a flag")
        self._storage = storage
        self._operator = self._seed("operator")[:48]
        self._campaigns: dict[str, _Campaign] = {}
        self._transport_label = transport_label
        self._security_boundary = security_boundary
        self.auth_failures = 0                    # service-wide, never written into a campaign's chain
        if storage is not None:
            self._restore(storage.read())

    @property
    def operator_token(self) -> str:
        """The operator credential (derived from the master secret).  Only the escrow side and its operator hold it."""
        return self._operator

    @property
    def identity_public(self) -> str:
        """The escrow's public verification key (hex): what a client pins to verify responses."""
        return self._identity.public_hex

    # -- the single entry point ---------------------------------------------------------------
    def handle(self, request: bytes) -> bytes:
        req: Any = None
        camp: _Campaign | None = None
        authed = False
        logged = False
        self._query_key = ""
        self._request_digest = ""
        try:
            req = json.loads(request.decode("utf-8"))
            if not isinstance(req, dict) or req.get("protocol") != PROTOCOL:
                raise EscrowRefused(f"unsupported protocol {req.get('protocol') if isinstance(req, dict) else None!r}")
            op = req.get("op")
            if op not in _ROLE_OF_OP:
                raise EscrowRefused(f"unknown operation {op!r}")
            qid = str(req.get("query_id", ""))
            if not _QUERY_ID.match(qid):
                raise EscrowRefused("every request carries a fresh query id ([A-Za-z0-9._-]{1,128})")
            last, last_head = req.get("last_sequence"), req.get("last_head")
            if isinstance(last, bool) or not isinstance(last, int) or last < -1 or not _HEX64.match(str(last_head)):
                raise EscrowRefused("every request states the last log sequence and head its sender saw (-1 and the genesis for none)")
            named = self._campaigns.get(str(req.get("campaign_id"))) if op != "create" else None
            self._authenticate(req, op, named)                     # BEFORE any campaign state is consulted
            authed, camp = True, named
            self._request_digest = request_digest(req)
            self._query_key = f"{op}:{req.get('universe_id', '')}:{qid}"      # single use per operation and universe
            if camp is not None:
                if self._query_key in camp.query_ids:
                    raise EscrowRefused(f"query id {qid!r} was already used in this campaign: a replayed request is refused")
                if last > camp.seq - 1:
                    raise EscrowRefused(f"the sender saw log sequence {last} but the escrow is at {camp.seq - 1}: its state was "
                                        "rolled back; nothing is answered from a rolled-back escrow")
                if last >= 0 and camp.log[last]["digest"] != last_head:
                    raise EscrowRefused(f"the sender saw another head at log sequence {last}: the escrow's history was replaced")
            handler = {"create": self._create, "observe": self._observe, "score": self._score, "log": self._log}[op]
            resp = {"ok": True, **handler(req)}
            logged = op != "log"
        except EscrowRefused as exc:
            resp = {"ok": False, "refused": str(exc) if authed or str(exc) != _UNAUTHENTICATED else _UNAUTHENTICATED}
        except (ValueError, KeyError, TypeError, AttributeError, RecursionError, ArithmeticError, ExpressionRefused) as exc:
            resp = {"ok": False, "refused": f"malformed request: {type(exc).__name__}: {str(exc)[:200]}"}
        except Exception as exc:  # noqa: BLE001 - last resort: no request may take the escrow down
            resp = {"ok": False, "refused": f"request failed: {type(exc).__name__}"}
        if not authed and isinstance(req, dict) and req.get("op") in _ROLE_OF_OP and resp.get("refused") == _UNAUTHENTICATED:
            self.auth_failures += 1
        if not resp["ok"] and authed and camp is not None:   # every AUTHENTICATED query that names a campaign is logged
            try:
                self._record(camp, f"{req.get('op')}_refused", req_public(req), {"refused": resp["refused"]}, 0.0)
            except Exception:  # noqa: BLE001 - an unloggable request is still logged, as unloggable
                self._record(camp, f"{req.get('op')}_refused", {"unloggable": True}, {"unloggable": True}, 0.0)
            logged = True
        target = None
        if authed:
            target = camp if camp is not None else self._campaigns.get(str(req.get("campaign_id")))
        resp.update(protocol=PROTOCOL, security_boundary=self._security_boundary, transport=self._transport_label,
                    request_digest=request_digest(req) if isinstance(req, dict) else _digest(None),
                    escrow_key_id=hashlib.sha256(bytes.fromhex(self._identity.public_hex)).hexdigest())
        if target is not None and (logged or resp.get("ok")):
            resp.update(sequence=target.seq - 1, head=target.log[-1]["digest"] if target.log else _GENESIS)
        resp["signature"] = self._identity.sign(response_signed_bytes(resp))
        return json.dumps(resp, sort_keys=True).encode("utf-8")

    # -- operations ----------------------------------------------------------------------------
    def _seed(self, *parts: str) -> str:
        return hmac.new(self._master, "\n".join(parts).encode(), hashlib.sha256).hexdigest()

    def _keyed(self, camp: _Campaign, payload: Any) -> str:
        """Log digests are HMAC-keyed: a log reader cannot test guesses (a mix, an answer) against them."""
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hmac.new(self._master, f"log\n{camp.campaign_id}\n{blob}".encode(), hashlib.sha256).hexdigest()

    def _authenticate(self, req: Mapping[str, Any], op: str, camp: _Campaign | None) -> None:
        role = _ROLE_OF_OP[op]
        if role == "operator":
            key = self._operator
        else:
            if camp is None:
                raise EscrowRefused(_UNAUTHENTICATED)
            key = camp.tokens[role]
        if "token" in req or "operator_token" in req:
            raise EscrowRefused("a credential is never sent: the request is authenticated by its MAC")
        expected = hmac.new(key.encode(), request_digest(req).encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(str(req.get("mac", "")), expected):
            raise EscrowRefused(_UNAUTHENTICATED)                  # one text: unknown campaign and bad MAC look alike

    def _world_digests(self, camp: _Campaign) -> dict[str, str]:
        """A keyed digest of every hidden world's FULL content (law, points, budget, cost, tolerance, ...) and of the
        generator: journaled at creation and re-checked on restore, so a replaced universe cannot pass as the same one."""
        import dataclasses
        return {u: hmac.new(self._master, b"forge.blindfold.world/1\n" + json.dumps(
            {"generator": GENERATOR_TAG, "world": dataclasses.asdict(camp.worlds[u])}, sort_keys=True, separators=(",", ":"),
            default=str).encode(), hashlib.sha256).hexdigest() for u in camp.order}

    def _new_campaign(self, cid: str, mix: Mapping[UniverseKind, int]) -> _Campaign:
        kinds = [k for k, n in sorted(mix.items(), key=lambda kv: kv[0].value) for _ in range(n)]
        random.Random(self._seed(cid, "shuffle")).shuffle(kinds)           # which universe is which kind: hidden
        worlds = {}
        order = []
        for i, kind in enumerate(kinds):
            w = generate_universe(self._seed(cid, "universe", str(i)), kind)
            worlds[w.universe_id] = w
            order.append(w.universe_id)
        tokens = {"observe": self._seed(cid, "token", "observe")[:48], "score": self._seed(cid, "token", "score")[:48]}
        return _Campaign(cid, worlds, order, tokens, {u: 0.0 for u in order}, {}, [], 0, set())

    def _create(self, req: Mapping[str, Any]) -> dict[str, Any]:
        cid = str(req["campaign_id"])
        if not _CAMPAIGN_ID.match(cid) or cid in self._campaigns:
            raise EscrowRefused("a campaign id is new and matches [A-Za-z0-9._-]{1,128}")
        raw = dict(req["mix"])
        if any(isinstance(n, bool) or not isinstance(n, int) for n in raw.values()):
            raise EscrowRefused("campaign mix counts are integers")
        mix = {UniverseKind(k): n for k, n in raw.items()}
        if any(n < 0 for n in mix.values()) or not 1 <= sum(mix.values()) <= MAX_UNIVERSES:
            raise EscrowRefused(f"a campaign mix has 1..{MAX_UNIVERSES} universes and no negative counts")
        declared = str(req.get("evaluator_config_digest", ""))
        if not _HEX64.match(declared):
            raise EscrowRefused("a campaign declares its sealed evaluator-config digest at creation (before any kind is revealed)")
        camp = self._new_campaign(cid, mix)
        self._campaigns[cid] = camp
        cards = [camp.worlds[u].public_card() for u in camp.order]
        mix_rec = {k.value: n for k, n in mix.items()}
        self._record(camp, "create", {"campaign_id": cid, "mix": mix_rec, "query_id": req["query_id"]}, {"universes": camp.order}, 0.0,
                     public={"evaluator_config_digest": declared}, state={"mix": mix_rec, "worlds": self._world_digests(camp)})
        return {"campaign_id": cid, "cards": cards, "tokens": dict(camp.tokens)}

    def _observe(self, req: Mapping[str, Any]) -> dict[str, Any]:
        camp = self._campaigns[str(req["campaign_id"])]
        uid = str(req["universe_id"])
        world = camp.worlds.get(uid)
        if world is None:
            raise EscrowRefused("unknown universe")
        if uid in camp.submitted:
            raise EscrowRefused("this universe's answer is sealed; no further observation")
        if camp.spent[uid] + world.query_cost > world.budget + 1e-9:
            raise EscrowRefused(f"query budget {world.budget} exhausted for {uid}")
        # a STORED escrow also seeds by the request digest: a request re-asked after a rollback gets fresh noise
        parts = (camp.campaign_id, uid, "obs", str(camp.seq)) + ((self._request_digest,) if self._storage is not None else ())
        rng = random.Random(self._seed(*parts))
        try:
            obs = observe(world, dict(req["settings"]), rng)
        except ValueError as exc:
            raise EscrowRefused(str(exc)) from exc
        camp.spent[uid] += world.query_cost
        body = {"universe_id": uid, "observation": obs, "budget_remaining": world.budget - camp.spent[uid]}
        receipt = self._record(camp, "observe", req_public(req), body, world.query_cost,
                               state={"universe_id": uid, "cost": world.query_cost})
        return {**body, "receipt": receipt, "budget_consumed": world.query_cost}

    def _score(self, req: Mapping[str, Any]) -> dict[str, Any]:
        camp = self._campaigns[str(req["campaign_id"])]
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
        if answer not in SCORED_ANSWERS:
            raise EscrowRefused(f"answer must be one of {SCORED_ANSWERS}")
        result: dict[str, Any] = {"universe_id": uid, "answer": answer, "proposal_digest": pdig}
        allowed = {x.name for x in world.inputs} | set(world.covariates)
        laws: list[Mapping[str, Any]] = []
        if answer == "inadmissible":
            if not _HEX64.match(str(proposal.get("original_digest", ""))) or "law" in proposal or "laws" in proposal:
                raise EscrowRefused("an inadmissible record names the stored original by digest and carries no law")
        elif answer == "law":
            laws = [proposal["law"]]
        elif answer == "indistinguishable":
            laws = list(proposal.get("laws", ()))
            if len(laws) != 2:
                raise EscrowRefused("an INDISTINGUISHABLE answer names exactly two laws that agree in the box and differ outside")
        elif "law" in proposal or "laws" in proposal:
            raise EscrowRefused("a refusal carries no law")
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
        if answer == "law":
            result["laws"] = [_assess(laws[0], truths, world)]
        elif answer == "indistinguishable":
            inbox = [truth_at(world, p, rng) for p in world.inbox_points]
            result["laws"] = [_assess(law, truths, world) for law in laws]
            result["pair"] = _assess_pair(laws, truths, inbox, world)
        result["universe_kind"] = world.kind.value                          # revealed only after the sealed submission
        result["tolerance"] = world.tolerance
        receipt = self._record(camp, "score", {"universe_id": uid, "proposal_digest": pdig, "query_id": req["query_id"]}, result, 0.0,
                               state={"universe_id": uid, "proposal_digest": pdig})
        return {**result, "receipt": receipt, "budget_consumed": 0.0}

    def _log(self, req: Mapping[str, Any]) -> dict[str, Any]:
        camp = self._campaigns.get(str(req.get("campaign_id")))
        if camp is None:
            raise EscrowRefused("unknown campaign")
        if self._storage is not None:                      # a read spends its query id durably (no chain entry)
            self._storage.append({"read": {"campaign_id": camp.campaign_id, "query_key": self._query_key}})
        camp.query_ids.add(self._query_key)
        return {"campaign_id": camp.campaign_id, "log": list(camp.log), "head": camp.log[-1]["digest"] if camp.log else _GENESIS,
                "spent": dict(camp.spent), "submitted": dict(camp.submitted), "auth_failures": self.auth_failures}

    def _record(self, camp: _Campaign, op: str, query: Mapping[str, Any], response: Mapping[str, Any], cost: float,
                public: Mapping[str, Any] | None = None, state: Mapping[str, Any] | None = None) -> dict[str, Any]:
        prev = camp.log[-1]["digest"] if camp.log else _GENESIS
        qid = str(query.get("query_id", ""))[:128]
        qkey = getattr(self, "_query_key", "")
        state = {**dict(state or {}), "query_key": qkey}
        entry = {"campaign_id": camp.campaign_id, "sequence": camp.seq, "op": op, "query_id": qid,
                 "query_digest": self._keyed(camp, query), "response_digest": self._keyed(camp, response), "budget_consumed": cost,
                 "previous": prev, "public": dict(public or {})}
        entry["digest"] = _digest(entry)
        if self._storage is not None:                 # durable BEFORE it is answered: a crash never loses a spent query
            self._storage.append({"entry": entry, "state": state})
        camp.log.append(entry)
        camp.seq += 1
        if qkey:
            camp.query_ids.add(qkey)
        return entry

    def _restore(self, records: list[Mapping[str, Any]]) -> None:
        """Rebuild every campaign from the (keyed-chain verified) journal: worlds re-derived from the master secret,
        budgets, submissions, used query ids and the log replayed entry by entry and re-checked."""
        for n, rec in enumerate(records):
            if "read" in rec:
                camp = self._campaigns.get(str(rec["read"].get("campaign_id")))
                if camp is None:
                    raise EscrowRefused(f"journal record {n} reads campaign {rec['read'].get('campaign_id')!r} before its creation")
                camp.query_ids.add(str(rec["read"]["query_key"]))
                continue
            entry, state = dict(rec["entry"]), dict(rec["state"])
            cid = entry["campaign_id"]
            if entry["op"] == "create":
                if cid in self._campaigns:
                    raise EscrowRefused(f"journal record {n} creates campaign {cid!r} twice")
                self._campaigns[cid] = self._new_campaign(cid, {UniverseKind(k): v for k, v in state["mix"].items()})
                if self._world_digests(self._campaigns[cid]) != state.get("worlds"):
                    raise EscrowRefused(f"journal record {n}: campaign {cid!r}'s universes no longer re-derive to the digests "
                                        "journaled at creation (a generator change or a replaced universe): refusing to start")
            camp = self._campaigns.get(cid)
            if camp is None:
                raise EscrowRefused(f"journal record {n} names campaign {cid!r} before its creation")
            body = {k: v for k, v in entry.items() if k != "digest"}
            prev = camp.log[-1]["digest"] if camp.log else _GENESIS
            if entry["sequence"] != camp.seq or entry["previous"] != prev or _digest(body) != entry["digest"]:
                raise EscrowRefused(f"journal record {n} breaks campaign {cid!r}'s log chain")
            if entry["op"] == "observe":
                uid = state["universe_id"]
                if uid not in camp.worlds or uid in camp.submitted:
                    raise EscrowRefused(f"journal record {n} observes a universe that is unknown or already sealed")
                camp.spent[uid] += float(state["cost"])
            elif entry["op"] == "score":
                uid = state["universe_id"]
                if uid not in camp.worlds or uid in camp.submitted:
                    raise EscrowRefused(f"journal record {n} scores a universe that is unknown or already sealed")
                camp.submitted[uid] = state["proposal_digest"]
            camp.log.append(entry)
            camp.seq += 1
            if state.get("query_key"):
                camp.query_ids.add(state["query_key"])


def req_public(req: Mapping[str, Any]) -> dict[str, Any]:
    """The request as logged: never a token or credential."""
    return {k: val for k, val in req.items() if k not in ("token", "operator_token", "mac")}


def verify_log(log: list[Mapping[str, Any]]) -> str:
    """Recompute the hash chain; return its head.  Raises on any break."""
    prev = _GENESIS
    for i, e in enumerate(log):
        body = {k: val for k, val in e.items() if k != "digest"}
        if e.get("previous") != prev or e.get("sequence") != i or _digest(body) != e.get("digest"):
            raise EscrowIntegrityError(f"the escrow log chain is broken at entry {i}")
        prev = e["digest"]
    return prev


def _errors(law: Mapping[str, Any], truths: list[tuple[dict[str, float], float]]) -> list[float]:
    errs = []
    for point, truth in truths:
        if not math.isfinite(truth) or truth == 0:
            errs.append(float("inf"))
            continue
        pred = evaluate(law, point)
        errs.append(abs(pred - truth) / abs(truth) if math.isfinite(pred) else float("inf"))
    return sorted(errs)


def _assess(law: Mapping[str, Any], truths: list[tuple[dict[str, float], float]], world: HiddenWorld) -> dict[str, Any]:
    errs = _errors(law, truths)
    within = sum(e <= world.tolerance for e in errs) / len(errs)
    median = errs[len(errs) // 2]
    structure = structure_digest(law)
    return {"fraction_within_tolerance": within, "median_relative_error": median if math.isfinite(median) else None,
            "passed": within >= PASS_FRACTION,
            "structure_matches_hidden_law": bool(world.law_structure) and structure == world.law_structure,
            "structure_digest": structure}


def _outside_box(point: Mapping[str, float], world: HiddenWorld) -> bool:
    return any(not (x.low <= point[x.name] <= x.high) for x in world.inputs)


def _assess_pair(laws: list[Mapping[str, Any]], truths: list[tuple[dict[str, float], float]],
                 inbox: list[tuple[dict[str, float], float]], world: HiddenWorld) -> dict[str, Any]:
    """An INDISTINGUISHABLE claim -- "inside the box the data cannot tell these two laws apart; outside they diverge, and
    the truth lies between them" -- is a HIT only when all of it is so:

    * both laws are finite at every in-box and evaluation point (a law that goes NaN outside is a miss);
    * the two laws agree WITH EACH OTHER within one noise sigma at every hidden in-box point (indistinguishable by the
      allowed queries -- two laws a tolerance apart in the box are distinguishable) and each fits the truth in the box;
    * they differ by more than the tolerance at half or more of the evaluation points that lie OUTSIDE the box (a
      box-region universe cannot be a hit: nothing is extrapolated);
    * the pair contains the truth (one law passes) or brackets it at >= 90% of the evaluation points.

    Crediting a bracketing pair is a scientific design decision: it rewards an honest statement of the extrapolation
    spread without requiring the proposer to know which branch is true (which, by construction, it cannot)."""
    tol, sigma = world.tolerance, world.noise_sigma
    pts_in = [p for p, _t in inbox]
    finite = all(math.isfinite(evaluate(law, p)) for law in laws for p in pts_in + [p for p, _t in truths])
    mutual = max((abs(evaluate(laws[0], p) - evaluate(laws[1], p)) / abs(evaluate(laws[1], p)) for p in pts_in
                  if evaluate(laws[1], p) != 0), default=float("inf")) if finite else float("inf")
    fit_in = finite and all(sum(e <= tol for e in _errors(law, inbox)) / len(inbox) >= PASS_FRACTION for law in laws)
    outside = [(p, t) for p, t in truths if _outside_box(p, world)]
    differ = 0
    bracket = 0
    for point, truth in truths:
        a, b = evaluate(laws[0], point), evaluate(laws[1], point)
        if not (finite and math.isfinite(truth)):
            continue
        lo, hi = min(a, b), max(a, b)
        if lo * (1 - tol) <= truth <= hi * (1 + tol):
            bracket += 1
        if _outside_box(point, world) and b != 0 and abs(a - b) / abs(b) > tol:
            differ += 1
    differ_fraction = differ / len(outside) if outside else 0.0
    contains_truth = finite and any(sum(e <= tol for e in _errors(law, truths)) / len(truths) >= PASS_FRACTION for law in laws)
    brackets = finite and bracket / len(truths) >= PASS_FRACTION
    hit = bool(finite and mutual <= sigma and fit_in and outside and differ_fraction >= PAIR_DIFFER_FRACTION
               and (contains_truth or brackets))
    return {"finite": finite, "mutual_in_box": mutual if math.isfinite(mutual) else None, "both_fit_in_box": fit_in,
            "outside_points": len(outside), "differ_fraction_outside": differ_fraction, "contains_truth": contains_truth,
            "brackets_truth": brackets, "hit": hit}


# ---------------------------------------------------------------------------- transports and clients


class InProcessTransport:
    """Development substitute: the service lives in the proposer's process.  NOT a security boundary."""

    def __init__(self, service: EscrowService | None = None) -> None:
        self._service = service or EscrowService(transport_label="in_process")
        self.operator_token = self._service.operator_token
        self.escrow_public = self._service.identity_public

    def __call__(self, request: bytes) -> bytes:
        return self._service.handle(request)


class SubprocessTransport:
    """The service in a child process (secrets generated -- or, with ``storage``, read -- there).  Same OS account: still
    NOT a proven boundary.  The child's first line is a handshake carrying the operator credential and the escrow's
    public key to the parent that started it."""

    def __init__(self, storage: str | os.PathLike[str] | None = None) -> None:
        args = [sys.executable, "-I", "-m", "engcore.blindfold.escrow_server"] + (["--storage", str(storage)] if storage else [])
        self._proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0)
        assert self._proc.stdout is not None
        hello = json.loads(self._proc.stdout.readline() or b"{}")
        if hello.get("protocol") != PROTOCOL or not hello.get("operator_token") or not hello.get("escrow_public"):
            raise EscrowRefused("the escrow process did not complete its handshake")
        self.operator_token = str(hello["operator_token"])
        self.escrow_public = str(hello["escrow_public"])

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


def verify_response(resp: Mapping[str, Any], *, escrow_public: str, request: Mapping[str, Any]) -> None:
    """A response is the escrow's (signature by the pinned key) answer to THIS request (its digest)."""
    from ..authority import verify_signature
    if not escrow_public or not verify_signature(escrow_public, str(resp.get("signature", "")), response_signed_bytes(resp)):
        raise EscrowIntegrityError("the response is not signed by the pinned escrow identity")
    if resp.get("request_digest") != request_digest(request):
        raise EscrowIntegrityError("the response answers another request (a replayed or substituted response)")


def call(transport: Callable[[bytes], bytes], op: str, *, token: str | None = None, operator_token: str | None = None,
         query_id: str | None = None, last_sequence: int = -1, last_head: str = _GENESIS, escrow_public: str | None = None,
         **fields: Any) -> dict[str, Any]:
    """Send one AUTHENTICATED request: the MAC is keyed by ``operator_token`` (create/log) or the campaign ``token``
    (observe/score); the credential itself is never sent.  With ``escrow_public`` the response is verified (the clients
    below always pin it; a bare ``call`` without it is a low-level probe and trusts nothing it returns)."""
    req: dict[str, Any] = {"protocol": PROTOCOL, "op": op, "query_id": query_id or f"q-{secrets.token_hex(8)}",
                           "last_sequence": last_sequence, "last_head": last_head, **fields}
    mac_request(req, operator_token if operator_token is not None else (token or ""))
    resp = json.loads(transport(json.dumps(req, sort_keys=True).encode("utf-8")))
    if escrow_public is not None:
        verify_response(resp, escrow_public=escrow_public, request=req)
    if not resp.get("ok"):
        raise EscrowRefused(resp.get("refused", "refused"))
    return resp


class EscrowCheckpoint:
    """A CLIENT's durable record of the latest SIGNED (sequence, head) it saw per campaign, in its own file (0600, never in
    the escrow's storage).  Sessions start from it and refuse an escrow behind it or with another head at that sequence:
    this is how a truncated journal or a restored backup is detected (the escrow cannot detect it alone)."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        import pathlib
        self._path = pathlib.Path(path)
        self._state: dict[str, list[Any]] = json.loads(self._path.read_text()) if self._path.exists() else {}

    def get(self, campaign_id: str) -> tuple[int, str]:
        seq, head = self._state.get(campaign_id, (-1, _GENESIS))
        return int(seq), str(head)

    def advance(self, campaign_id: str, sequence: int, head: str) -> None:
        seq, known = self.get(campaign_id)
        if sequence < seq or (sequence == seq and head != known):
            raise EscrowIntegrityError(f"campaign {campaign_id!r}: the escrow is at ({sequence}, {head[:12]}) behind or beside this "
                                       f"client's signed checkpoint ({seq}, {known[:12]}): rolled back or replaced")
        if (sequence, head) == (seq, known):
            return
        self._state[campaign_id] = [sequence, head]
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(json.dumps(self._state, sort_keys=True))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self._path)


class _Session:
    """One capability's view of one campaign: authenticates requests, verifies every signed response against the PINNED
    escrow key, and refuses an escrow whose log went backwards or was replaced -- against the checkpoint it keeps in
    memory and, with ``checkpoint``, durably across client restarts."""

    __slots__ = ("_campaign", "_checkpoint", "_key", "_public", "_transport", "last_head", "last_sequence")

    def __init__(self, transport: Callable[[bytes], bytes], key: str, escrow_public: str | None, *, campaign_id: str,
                 checkpoint: EscrowCheckpoint | None = None) -> None:
        if not escrow_public:
            raise EscrowIntegrityError("a client pins the escrow's public key (out of band); it never trusts an unverified escrow")
        self._transport, self._key, self._public = transport, key, escrow_public
        self._campaign, self._checkpoint = campaign_id, checkpoint
        self.last_sequence, self.last_head = checkpoint.get(campaign_id) if checkpoint is not None else (-1, _GENESIS)

    def send(self, op: str, **fields: Any) -> dict[str, Any]:
        try:
            resp = call(self._transport, op, operator_token=self._key if op in ("create", "log") else None,
                        token=None if op in ("create", "log") else self._key, last_sequence=self.last_sequence,
                        last_head=self.last_head, escrow_public=self._public, **fields)
        except EscrowRefused as exc:
            if "rolled back" in str(exc) or "history was replaced" in str(exc):
                raise EscrowIntegrityError(str(exc)) from exc
            raise
        seq, head = resp.get("sequence"), resp.get("head")
        if isinstance(seq, int) and isinstance(head, str):
            if seq < self.last_sequence or (seq == self.last_sequence and head != self.last_head):
                raise EscrowIntegrityError("the escrow's log went backwards or was replaced: its state was rolled back")
            if self._checkpoint is not None:
                self._checkpoint.advance(self._campaign, seq, head)
            self.last_sequence, self.last_head = seq, head
        return resp


class ObserveClient:
    """What a proposer holds: observe within budget, for one campaign.  Its public API sends only ``observe``; it has no
    transport, score-token or operator-credential ATTRIBUTE.  That is construction, not isolation: its closure still
    references the transport, which introspection can reach -- unless the proposer runs in another security domain
    (:mod:`.isolation`), where the closure holds only a socket to the escrow."""

    __slots__ = ("_send", "campaign_id")

    def __init__(self, transport: Callable[[bytes], bytes], campaign_id: str, token: str, *, escrow_public: str,
                 checkpoint: EscrowCheckpoint | None = None) -> None:
        session = _Session(transport, token, escrow_public, campaign_id=campaign_id, checkpoint=checkpoint)

        def send(universe_id: str, settings: Mapping[str, float], query_id: str) -> dict[str, Any]:
            return session.send("observe", campaign_id=campaign_id, universe_id=universe_id, settings=dict(settings),
                                **({"query_id": query_id} if query_id else {}))
        self._send = send
        self.campaign_id = campaign_id

    def observe(self, universe_id: str, settings: Mapping[str, float], query_id: str = "") -> dict[str, Any]:
        return self._send(universe_id, settings, query_id)


class ScoreClient:
    """What the evaluator holds: one sealed submission per universe."""

    def __init__(self, transport: Callable[[bytes], bytes], campaign_id: str, token: str, *, escrow_public: str,
                 checkpoint: EscrowCheckpoint | None = None) -> None:
        self.campaign_id = campaign_id
        self._session = _Session(transport, token, escrow_public, campaign_id=campaign_id, checkpoint=checkpoint)

    def score(self, universe_id: str, proposal: Mapping[str, Any]) -> dict[str, Any]:
        return self._session.send("score", campaign_id=self.campaign_id, universe_id=universe_id, proposal=dict(proposal),
                                  proposal_digest=_digest(dict(proposal)))


class OperatorClient:
    """What the operator holds: create campaigns and read their logs."""

    def __init__(self, transport: Callable[[bytes], bytes], operator_token: str, *, escrow_public: str,
                 checkpoint: EscrowCheckpoint | None = None) -> None:
        if not escrow_public:
            raise EscrowIntegrityError("a client pins the escrow's public key (out of band); it never trusts an unverified escrow")
        self._transport = transport
        self._token = operator_token
        self._public = escrow_public
        self._checkpoint = checkpoint
        self._sessions: dict[str, _Session] = {}

    def _session(self, campaign_id: str) -> _Session:
        if campaign_id not in self._sessions:
            self._sessions[campaign_id] = _Session(self._transport, self._token, self._public, campaign_id=campaign_id,
                                                   checkpoint=self._checkpoint)
        return self._sessions[campaign_id]

    def create(self, campaign_id: str, mix: Mapping[str, int], *, evaluator_config_digest: str) -> dict[str, Any]:
        return self._session(campaign_id).send("create", campaign_id=campaign_id, mix=dict(mix),
                                               evaluator_config_digest=evaluator_config_digest)

    def log(self, campaign_id: str) -> dict[str, Any]:
        return self._session(campaign_id).send("log", campaign_id=campaign_id)


__all__ = [
    "ANSWERS",
    "MAX_UNIVERSES",
    "PROTOCOL",
    "SCORED_ANSWERS",
    "SECURITY_LABEL",
    "EscrowCheckpoint",
    "EscrowIntegrityError",
    "EscrowRefused",
    "EscrowService",
    "EscrowStorage",
    "InProcessTransport",
    "ObserveClient",
    "OperatorClient",
    "ScoreClient",
    "SubprocessTransport",
    "call",
    "is_budget_refusal",
    "mac_request",
    "request_digest",
    "verify_log",
    "verify_response",
]
