"""Genesis-lite run harness: one campaign, one arm, one presentation -- then the reveal and the separate grade.

Order (the reveal protocol, preregistered):

1. the escrow creates the campaign from its master seed; the evaluator config digest is declared at creation;
2. each card is PRESENTED (name and id translation only, with a key private to this run), checked against the
   reviewed card schema, and handed with an observe client to the arm; the arm's proposal is translated back, stored
   content-addressed and sealed by one escrow score;
3. only after every universe is sealed, the operator exports the answer key from the master seed;
4. the separately implemented evaluator re-scores every sealed proposal from the key and must agree with the escrow on
   every universe (outcome, credit and every per-law fraction); the presented cards are audited for literal leaks;
   every trap world in which a law can earn credit is checked (the best-constant textbook law must FAIL there).

A run is ``VALID`` only when all of that holds. Any failure -- including an exception anywhere in the run -- makes it
``INVALID_BENCHMARK`` with the reason; its numbers are kept but never aggregated into a rate (review M4).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import tracemalloc
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from engcore.blindfold import EvaluatorConfig, EscrowService, InProcessTransport, run_campaign
from engcore.blindfold.expression import c, mul, pw, v

from . import evaluator as independent
from .answer_key import export_answer_key, key_digest
from .presentation import Presented, PresentationRefused, TranslatingClient, check_card, present, to_original_law

KINDS = ("confounded", "discoverable", "indistinguishable", "insufficient_evidence", "no_solution", "spurious_correlate")
MIX = {k: 1 for k in KINDS}
CONFIG = EvaluatorConfig("forge.genesis_lite.v0", "1")
#: kinds in which a proposed law can earn positive credit: a trap there must be verified
LAW_CREDIT_KINDS = tuple(k for k in KINDS if independent.CREDIT[k].get("law_pass", 0.0) > 0)


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def presentation_key(master_seed: bytes, arm: str, seed: int, presentation: str) -> bytes:
    """Private to one run: two runs over the same hidden world never share a universe pseudonym or a renaming."""
    return hmac.new(master_seed, f"forge.genesis_lite.presentation\n{arm}\n{seed}\n{presentation}".encode(), hashlib.sha256).digest()


@dataclass
class RunRecord:
    arm: str
    seed: int
    campaign_id: str
    presentation: str
    status: str = "VALID"
    reasons: list[str] = field(default_factory=list)
    wall_seconds: float = 0.0
    memory_instrumented: bool = False
    peak_traced_kib: float | None = None
    observe_calls: int = 0
    universes: list[dict[str, Any]] = field(default_factory=list)
    key_digest: str = ""
    report_digest: str = ""
    presented_card_digests: dict[str, str] = field(default_factory=dict)
    leakage_audit: str = "UNKNOWN"
    evaluator_status: str = "UNKNOWN"
    security_boundary: str = ""

    def invalid(self, reason: str) -> None:
        self.status = "INVALID_BENCHMARK"
        self.reasons.append(reason)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def run_one(arm_name: str, arm: Callable[..., Mapping[str, Any]], *, master_seed: bytes, campaign_id: str, presentation: str,
            seed: int = 0, measure_memory: bool = False, card_hook: Callable[[dict], dict] | None = None,
            config: EvaluatorConfig = CONFIG) -> RunRecord:
    """Run one campaign end to end. ``card_hook`` exists ONLY for adversarial tests (an injected leak)."""
    rec = RunRecord(arm_name, seed, campaign_id, presentation, memory_instrumented=measure_memory)
    try:
        _run(rec, arm, master_seed, campaign_id, presentation, seed, measure_memory, card_hook, config)
    except Exception as exc:  # noqa: BLE001 - every failure is a recorded benchmark-invalid run, never a lost record
        rec.invalid(f"run aborted: {type(exc).__name__}: {str(exc)[:300]}")
    return rec


def _run(rec: RunRecord, arm: Callable[..., Mapping[str, Any]], master_seed: bytes, campaign_id: str, presentation: str,
         seed: int, measure_memory: bool, card_hook: Callable[[dict], dict] | None, config: EvaluatorConfig) -> None:
    if config.digest != CONFIG.digest or independent.credit_digest(dict(config.credit)) != independent.CREDIT_DIGEST:
        rec.invalid("the evaluator configuration is not the preregistered one")
        return
    service = EscrowService(master_seed=master_seed, transport_label="in_process")
    inner = InProcessTransport(service)
    scored: dict[str, dict[str, Any]] = {}

    def transport(request: bytes) -> bytes:              # records the escrow's own score responses for the cross-check
        response = inner(request)
        body = json.loads(response)
        if body.get("ok") and "laws" in body and "universe_id" in body:
            scored[body["universe_id"]] = body
        return response

    transport.operator_token = inner.operator_token        # type: ignore[attr-defined]
    pkey = presentation_key(master_seed, rec.arm, seed, presentation)
    shown: dict[str, dict[str, Any]] = {}
    per_universe: dict[str, dict[str, Any]] = {}
    traps: dict[str, Presented] = {}
    tells: dict[str, str] = {}

    def proposer(card: Mapping[str, Any], client: Any) -> Mapping[str, Any]:
        uid = card["universe_id"]
        try:
            p = present(card, presentation, pkey)
            shown_card = p.card if card_hook is None else card_hook(dict(p.card))
            check_card(shown_card)
            tells[uid] = independent.region_tell(shown_card)
        except PresentationRefused as exc:
            rec.invalid(f"presentation refused before the proposer saw {uid}: {exc}")
            raise
        except Exception as exc:  # noqa: BLE001 - a presentation failure is the benchmark's, never the proposer's
            rec.invalid(f"presentation failed before the proposer saw {uid}: {type(exc).__name__}: {exc}")
            raise
        shown[uid] = shown_card
        if p.historical is not None:
            traps[uid] = p
        wrapped = TranslatingClient(client, p)
        t0 = time.perf_counter()
        proposal = dict(arm(shown_card, wrapped, seed=seed))
        per_universe[uid] = {"proposer_seconds": time.perf_counter() - t0, "observe_calls": wrapped.calls}
        if proposal.get("universe_id", shown_card["universe_id"]) != shown_card["universe_id"]:
            raise ValueError("the proposal names another universe than its card")    # scored inadmissible, the proposer's fault
        proposal["universe_id"] = uid                        # the pseudonym never reaches the escrow
        for k in ("law", "laws"):
            if k in proposal:
                proposal[k] = to_original_law(proposal[k], p.to_original)
        return proposal

    if measure_memory:
        tracemalloc.start()
    t0 = time.perf_counter()
    try:
        report, store = run_campaign(transport, campaign_id=campaign_id, mix=MIX, proposer=proposer,
                                     proposer_identity={"kind": "baseline", "id": rec.arm}, config=config,
                                     escrow_public=inner.escrow_public)
    finally:
        rec.wall_seconds = time.perf_counter() - t0
        if measure_memory:
            rec.peak_traced_kib = tracemalloc.get_traced_memory()[1] / 1024
            tracemalloc.stop()
    rec.report_digest = report.digest
    rec.observe_calls = report.queries
    rec.security_boundary = report.security_boundary
    if rec.status != "VALID":
        return
    # ---- the reveal: only now does the answer key exist
    card_ids = [a.universe_id for a in report.adjudications]
    key = export_answer_key(master_seed, campaign_id, MIX, card_ids)
    rec.key_digest = key_digest(key)
    if key["status"] != "DERIVED":
        rec.invalid("the exported answer key does not name the campaign's universes")
        return
    proposals = {a.universe_id: store.get(a.proposal_digest) for a in report.adjudications}
    escrow = {}
    for a in report.adjudications:
        row = {"kind": a.universe_kind, "outcome": a.outcome, "credit": a.credit}
        if a.universe_id in scored:
            row["fractions"] = [law["fraction_within_tolerance"] for law in scored[a.universe_id]["laws"]]
        escrow[a.universe_id] = row
    graded = independent.evaluate_campaign(proposals, key, escrow, expected_credit_digest=independent.CREDIT_DIGEST)
    rec.evaluator_status = graded["status"]
    if graded["status"] != "VALID":
        rec.invalid(f"separate evaluator: {graded['status']} {graded.get('disagreements')}")
    audit = independent.audit_presented_cards([{**cd, "universe_id": u} for u, cd in shown.items()], key)
    rec.leakage_audit = audit["status"]
    if audit["status"] != "NO_LITERAL_LEAK_FOUND":
        rec.invalid(f"leakage audit: {audit['findings'][:3]}")
    entries = {e["universe_id"]: e for e in key["universes"]}
    for uid, p in traps.items():                  # a trap whose textbook law passes is not a trap
        entry = entries[uid]
        if entry["kind"] in LAW_CREDIT_KINDS and entry["law"] is not None:
            hist_name, exponent = p.historical
            if _textbook_could_pass(mul(c(1.0), pw(v(p.to_original[hist_name]), exponent)), entry):
                rec.invalid(f"trap {uid} ({entry['kind']}): the textbook law fits the hidden world, the instance tests nothing")
    rec.presented_card_digests = {u: _digest(cd) for u, cd in shown.items()}
    by_uid = {r["universe_id"]: r for r in graded["results"]}
    for a in report.adjudications:
        entry = entries[a.universe_id]
        rec.universes.append({"universe_id": a.universe_id, "kind": a.universe_kind, "answer": a.answer, "outcome": a.outcome,
                              "credit": a.credit, "independent_agrees": bool(by_uid.get(a.universe_id, {}).get("agree")),
                              "trap": a.universe_id in traps, "region_tell": tells.get(a.universe_id),
                              "truth_in_searched_family": independent.in_monomial_family(entry["law"]),
                              **per_universe.get(a.universe_id, {})})


def _textbook_could_pass(textbook: Mapping[str, Any], entry: Mapping[str, Any]) -> bool:
    """Whether the textbook law with its BEST constant would pass on the hidden evaluation points (an upper bound on
    what a memorising proposer can earn). A point is within tolerance for constant k when |k r_i - t_i| <= tol |t_i|,
    i.e. k in [(1 - tol) t_i / r_i, (1 + tol) t_i / r_i]; the best k is the one inside the most such intervals, found
    exactly by sweeping the interval endpoints."""
    import math as _m

    from .evaluator.expr import value

    tol = float(entry["tolerance"])
    intervals, n = [], len(entry["evaluation"])
    for point, truth in entry["evaluation"]:
        pred = value(textbook, point)
        if truth and _m.isfinite(truth) and _m.isfinite(pred) and pred > 0 and truth > 0:
            intervals.append(((1 - tol) * truth / pred, (1 + tol) * truth / pred))
    if not intervals:
        return False
    events = sorted([(lo, 0) for lo, _ in intervals] + [(hi, 1) for _, hi in intervals])
    best = cur = 0
    for _, kind in events:                         # opens sort before closes at equal values: closed intervals
        cur += 1 if kind == 0 else -1
        best = max(best, cur)
    return best / n >= independent.score.PASS_FRACTION
