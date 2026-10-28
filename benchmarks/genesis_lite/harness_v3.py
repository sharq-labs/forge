"""Genesis-lite v0.3 DEVELOPMENT campaign path (owner-approved 2026-10-28): FDA-05 over the unchanged v0.2 substrate.

The v0.2 harness, evaluator and blindfold substrate are byte-pinned by the v0.2 preregistration; a run here first requires
that pin to hold (so the shared code is exactly the reviewed code), then runs the same campaign flow under its own sealed
configuration (:data:`CONFIG_V3`), applies :func:`adjudicate_v3` to the escrow's signed score facts and requires the
independent v0.3 evaluator to agree. There is no v0.3 preregistration: ``prereg_sha256`` stays empty and the record carries
a ``development_identity`` over the v0.3 files instead. Not a formal benchmark identity and not evidence of lift.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import pathlib
import time
import tracemalloc
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from engcore.blindfold import EscrowService, EvaluatorConfig, InProcessTransport, run_campaign
from engcore.blindfold.expression import c, mul, pw, v

from . import harness as h2
from .adjudication_v3 import BENCHMARK_ID, CONFIG_V3, READINESS, adjudicate_v3
from .answer_key import export_answer_key, key_digest
from .evaluator import score_v3
from .presentation import Presented, PresentationRefused, TranslatingClient, check_card, present, to_original_law

HERE = pathlib.Path(__file__).resolve().parent
V3_FILES = ("adjudication_v3.py", "arms_v3.py", "harness_v3.py", "pilot_v3.py", "evaluator/score_v3.py")
LIBRARIES = ("numpy", "sympy", "pysr", "pysindy", "botorch", "gpytorch", "torch")


def library_versions() -> dict[str, str]:
    out = {}
    for name in LIBRARIES:
        try:
            out[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            out[name] = "NOT_INSTALLED"
    return out


def development_identity() -> tuple[str, list[str]]:
    """(identity, v0.2-pinned files that changed). The identity binds the v0.2 preregistration and the v0.3 files."""
    prereg, changed = h2.code_identity()
    files = {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in V3_FILES}
    return h2._digest({"v0_2_prereg": prereg, "v0_3_files": files, "benchmark_id": BENCHMARK_ID}), changed


@dataclass
class RunRecordV3(h2.RunRecord):
    benchmark_id: str = BENCHMARK_ID
    readiness: str = READINESS
    config_digest: str = ""
    development_identity: str = ""
    v3_adjudication_digest: str = ""
    v3_total_credit: float = 0.0
    #: report_digest binds the escrow report built by roles.run_campaign, whose outcomes follow the v0.2 rule
    escrow_report_rule: str = "v0_2 outcomes (bracketing-only pairs credited); v0.3 outcomes are in universes"
    library_versions: dict = field(default_factory=dict)


def run_one_v3(arm_name: str, arm: Callable[..., Mapping[str, Any]], *, master_seed: bytes, campaign_id: str,
               presentation: str, seed: int = 0, measure_memory: bool = False, config: EvaluatorConfig = CONFIG_V3,
               isolation: str = "in_process", arm_spec: str | None = None,
               extra_paths: tuple[str, ...] = ()) -> RunRecordV3:
    rec = RunRecordV3(arm_name, seed, campaign_id, presentation, memory_instrumented=measure_memory, isolation=isolation)
    identity, changed = development_identity()
    if changed:
        rec.invalid(f"the shared v0.2 code differs from its preregistration: {changed[:5]}")
        return rec
    rec.development_identity = identity
    rec.library_versions = library_versions()
    if isolation not in h2.ISOLATIONS:
        rec.invalid(f"unknown isolation {isolation!r}")
        return rec
    host = None
    try:
        if isolation == "proposer_process":
            started = time.perf_counter()
            host = h2.ProposerHost(extra_paths)
            rec.host_start_seconds = time.perf_counter() - started
            spec = arm_spec or arm_name
            arm = lambda card, client, *, seed=0: host.propose(spec, card, seed, client)  # noqa: E731
        _run_v3(rec, arm, master_seed, campaign_id, presentation, seed, measure_memory, config)
    except Exception as exc:  # noqa: BLE001 - every failure is a recorded benchmark-invalid run, never a lost record
        rec.invalid(f"run aborted: {type(exc).__name__}: {str(exc)[:300]}")
    finally:
        if host is not None:
            host.close()
    return rec


def _run_v3(rec: RunRecordV3, arm: Callable[..., Mapping[str, Any]], master_seed: bytes, campaign_id: str,
            presentation: str, seed: int, measure_memory: bool, config: EvaluatorConfig) -> None:
    if config.digest != CONFIG_V3.digest or score_v3.v2.credit_digest(dict(config.credit)) != score_v3.CREDIT_DIGEST:
        rec.invalid("the evaluator configuration is not the sealed v0.3 one")
        return
    rec.config_digest = config.digest
    service = EscrowService(master_seed=master_seed, transport_label="in_process")
    inner = InProcessTransport(service)
    scored: dict[str, dict[str, Any]] = {}

    def transport(request: bytes) -> bytes:              # keeps the escrow's own signed score bodies for adjudication
        response = inner(request)
        body = json.loads(response)
        if body.get("ok") and "laws" in body and "universe_id" in body:
            scored[body["universe_id"]] = body
        return response

    transport.operator_token = inner.operator_token        # type: ignore[attr-defined]
    pkey = h2.presentation_key(master_seed, rec.arm, seed, presentation)
    skey = h2.stimulus_key(master_seed, seed, presentation)
    shown: dict[str, dict[str, Any]] = {}
    per_universe: dict[str, dict[str, Any]] = {}
    traps: dict[str, Presented] = {}
    tells: dict[str, str] = {}

    def proposer(card: Mapping[str, Any], client: Any) -> Mapping[str, Any]:
        uid = card["universe_id"]
        try:
            p = present(card, presentation, pkey, skey)
            shown_card = p.card
            check_card(shown_card)
            tells[uid] = score_v3.v2.region_tell(shown_card)
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
            raise ValueError("the proposal names another universe than its card")
        proposal["universe_id"] = uid
        for k in ("law", "laws"):
            if k in proposal:
                proposal[k] = to_original_law(proposal[k], p.to_original)
        return proposal

    if measure_memory:
        tracemalloc.start()
    t0 = time.perf_counter()
    try:
        report, store = run_campaign(transport, campaign_id=campaign_id, mix=h2.MIX, proposer=proposer,
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
    # ---- v0.3 adjudication over the escrow's signed pair facts (every pair answer must have its score body)
    adjudications = []
    for a in report.adjudications:
        if a.answer == "indistinguishable" and a.universe_id not in scored:
            rec.invalid(f"no escrow score body for the pair answer on {a.universe_id}")
            return
        adjudications.append(adjudicate_v3(a, scored[a.universe_id], config) if a.universe_id in scored else a)
    rec.v3_adjudication_digest = h2._digest([a.to_dict() for a in adjudications])
    # ---- the reveal: only now does the answer key exist
    card_ids = [a.universe_id for a in adjudications]
    key = export_answer_key(master_seed, campaign_id, h2.MIX, card_ids)
    rec.key_digest = key_digest(key)
    if key["status"] != "DERIVED":
        rec.invalid("the exported answer key does not name the campaign's universes")
        return
    proposals = {a.universe_id: store.get(a.proposal_digest) for a in adjudications}
    escrow = {}
    for a in adjudications:
        row = {"kind": a.universe_kind, "outcome": a.outcome, "credit": a.credit}
        if a.universe_id in scored:
            row["fractions"] = [law["fraction_within_tolerance"] for law in scored[a.universe_id]["laws"]]
        escrow[a.universe_id] = row
    graded = score_v3.evaluate_campaign(proposals, key, escrow, expected_credit_digest=score_v3.CREDIT_DIGEST)
    rec.evaluator_status = graded["status"]
    if graded["status"] != "VALID":
        rec.invalid(f"separate v0.3 evaluator: {graded['status']} {graded.get('disagreements')}")
    audit = score_v3.v2.audit_presented_cards([{**cd, "universe_id": u} for u, cd in shown.items()], key)
    rec.leakage_audit = audit["status"]
    if audit["status"] != "NO_LITERAL_LEAK_FOUND":
        rec.invalid(f"leakage audit: {audit['findings'][:3]}")
    entries = {e["universe_id"]: e for e in key["universes"]}
    for uid, p in traps.items():                  # a trap whose textbook law passes is not a trap
        entry = entries[uid]
        if entry["kind"] in h2.LAW_CREDIT_KINDS and entry["law"] is not None:
            hist_name, exponent = p.historical
            if h2._textbook_could_pass(mul(c(1.0), pw(v(p.to_original[hist_name]), exponent)), entry):
                rec.invalid(f"trap {uid} ({entry['kind']}): the textbook law fits the hidden world, the instance tests nothing")
    rec.presented_card_digests = {u: h2._digest(cd) for u, cd in shown.items()}
    by_uid = {r["universe_id"]: r for r in graded["results"]}
    for a in adjudications:
        entry = entries[a.universe_id]
        rec.universes.append({"universe_id": a.universe_id, "kind": a.universe_kind, "answer": a.answer, "outcome": a.outcome,
                              "credit": a.credit, "independent_agrees": bool(by_uid.get(a.universe_id, {}).get("agree")),
                              "trap": a.universe_id in traps, "region_tell": tells.get(a.universe_id),
                              "truth_in_searched_family": score_v3.v2.in_monomial_family(entry["law"]),
                              "rationale": str((proposals.get(a.universe_id) or {}).get("rationale")
                                               or (proposals.get(a.universe_id) or {}).get("reason") or ""),
                              **per_universe.get(a.universe_id, {})})
    rec.v3_total_credit = sum(u["credit"] for u in rec.universes)


__all__ = ["CONFIG_V3", "RunRecordV3", "V3_FILES", "development_identity", "run_one_v3"]
