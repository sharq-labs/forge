"""Genesis-lite v0.3 DEVELOPMENT campaign path (owner-approved 2026-10-28): FDA-05 over the unchanged v0.2 substrate.

The v0.2 harness, evaluator and blindfold substrate are byte-pinned by the v0.2 preregistration; a run here first requires
that pin to hold (so the shared code is exactly the reviewed code), then runs the same campaign flow under its own sealed
configuration (:data:`CONFIG_V3`), applies :func:`adjudicate_v3` to the escrow's signed score facts and requires the
independent v0.3 evaluator to agree. There is no v0.3 preregistration: ``prereg_sha256`` stays empty and the record carries
a ``development_identity`` over the v0.3 files instead. Not a formal benchmark identity and not evidence of lift.

EXC-3 (owner-approved 2026-10-29): ``budget_fraction`` caps the observations every arm makes on a universe below the
world's budget (:func:`query_cap`). The presented card states the cap and :class:`QueryCap` refuses past it with the
escrow's own budget-refusal text; the worlds, the escrow, the scoring and the credit table are unchanged, and at 1.0
nothing changes at all.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.metadata
import json
import math
import pathlib
import time
import tracemalloc
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from engcore.blindfold import EvaluatorConfig, InProcessTransport, run_campaign
from engcore.blindfold.escrow import EscrowRefused
from engcore.blindfold.escrow_v3 import RULE as ESCROW_RULE, EscrowServiceV3
from engcore.blindfold.expression import c, mul, pw, v

import engcore

from . import harness as h2
from .adjudication_v3 import BENCHMARK_ID, CONFIG_V3, READINESS, adjudicate_v3
from .answer_key import export_answer_key, key_digest
from .evaluator import score_v3
from .mind_arm_v3 import MIND_ARMS
from .presentation import Presented, PresentationRefused, TranslatingClient, check_card, present, to_original_law

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
V3_FILES = ("adjudication_v3.py", "arms_v3.py", "harness_v3.py", "mind_arm_v3.py", "pilot_v3.py", "evaluator/score_v3.py")


def engcore_closure(*modules: str) -> tuple[str, ...]:
    """Repository-relative files of every ``engcore`` module the given modules import (statements and literal
    ``import_module("engcore...")`` calls), transitively, with every parent
    package ``__init__`` (which runs on import). Static, from the source text: a computed lazy import is not followed, so
    tests/genesis_lite/test_v03_mind_arm.py checks that a Mind run loads nothing outside it. A change to any listed file
    changes the identity."""
    src = ROOT / "src"

    def file_of(mod: str) -> pathlib.Path | None:
        base = src.joinpath(*mod.split("."))
        return base / "__init__.py" if (base / "__init__.py").exists() else (
            base.with_suffix(".py") if base.with_suffix(".py").exists() else None)

    seen: set[pathlib.Path] = set()
    todo = [file_of(m) for m in modules]
    while todo:
        f = todo.pop()
        if f is None or f in seen:
            continue
        seen.add(f)
        parts = f.relative_to(src).with_suffix("").parts
        name = ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
        package = name if f.name == "__init__.py" else name.rpartition(".")[0]
        todo += [file_of(".".join(name.split(".")[:i])) for i in range(1, name.count(".") + 1)]
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                base = package.split(".")[: package.count(".") + 2 - node.level] if node.level else []
                mod = ".".join(base + ([node.module] if node.module else []))
                if mod.split(".")[0] == "engcore":
                    todo += [file_of(mod)] + [file_of(f"{mod}.{a.name}") for a in node.names]
            elif isinstance(node, ast.Import):
                todo += [file_of(a.name) for a in node.names if a.name.split(".")[0] == "engcore"]
            elif (isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant)
                  and str(node.args[0].value).startswith("engcore.")
                  and getattr(node.func, "id", getattr(node.func, "attr", "")).endswith("import_module")):
                todo.append(file_of(node.args[0].value))     # the compatibility shims' import_module("engcore...")
    return tuple(sorted(f.relative_to(ROOT).as_posix() for f in seen))


#: v0.3 substrate beside the pinned v0.2 escrow (repository-relative), plus (EXC-2) every engcore file the Minimal Mind
#: imports: it is measured read-only as an arm, so the code it runs binds the identity
SUBSTRATE_V3_FILES = ("src/engcore/blindfold/escrow_v3.py", *engcore_closure("engcore.mind.minimal"))
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
    files.update({name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SUBSTRATE_V3_FILES})
    return h2._digest({"v0_2_prereg": prereg, "v0_3_files": files, "benchmark_id": BENCHMARK_ID}), changed


def query_cap(card: Mapping[str, Any], fraction: Any) -> int:
    """EXC-3: the observations an arm may make on this card's universe: ``min(budget, max(d + 2, floor(f x budget)))``,
    d the number of inputs (the floor keeps a log-linear fit possible). A fraction below 1 needs a unit query cost."""
    if isinstance(fraction, bool) or not isinstance(fraction, (int, float)) or not 0 < fraction <= 1:
        raise ValueError(f"budget fraction {fraction!r} must be a number in (0, 1]")
    budget = int(card["query_budget"])
    if fraction == 1:
        return budget
    if float(card["query_cost"]) != 1.0:
        raise ValueError("a budget fraction below 1 needs a unit query cost: the cap counts queries")
    return min(budget, max(len(card["inputs"]) + 2, math.floor(fraction * budget)))


class QueryCap:
    """What an arm holds under a budget fraction: ``observe`` until ``cap`` observations have succeeded, then the escrow's
    own budget refusal. A refused query is not counted. ``budget_remaining`` is the cap's, never the world's."""

    __slots__ = ("_QueryCap__inner", "cap", "used")

    def __init__(self, inner: Any, cap: int) -> None:
        self.__inner = inner
        self.cap = int(cap)
        self.used = 0

    def observe(self, universe_id: str, settings: Mapping[str, float], query_id: str = "") -> dict[str, Any]:
        if self.used >= self.cap:
            raise EscrowRefused(f"query budget {self.cap} exhausted for {universe_id}")
        resp = self.__inner.observe(universe_id, settings, query_id=query_id)
        self.used += 1
        return {**resp, "budget_remaining": self.cap - self.used}


@dataclass
class RunRecordV3(h2.RunRecord):
    benchmark_id: str = BENCHMARK_ID
    readiness: str = READINESS
    config_digest: str = ""
    development_identity: str = ""
    v3_adjudication_digest: str = ""
    v3_total_credit: float = 0.0
    #: report_digest binds roles.run_campaign's report: v0.2 outcome mapping (a bracketing-only pair is a hit there)
    escrow_report_rule: str = "v0_2 outcome mapping over v0_3 escrow facts; v0.3 outcomes are in universes"
    #: the rule named by the escrow's own score bodies in this run (observed, never assumed)
    escrow_rule: str = ""
    agreement_scope: str = ("the evaluator independently re-implements the expression interpreter and the fraction, "
                            "outcome and credit plumbing; it agrees by construction on the pair/fraction rule text it "
                            "shares with escrow_v3, so agreement checks those parts, not the rule semantics")
    library_versions: dict = field(default_factory=dict)
    #: the proposer kind the campaign was submitted under ("baseline", or the Mind arms' "candidate" / "ablation")
    proposer_kind: str = ""
    #: EXC-3: the fraction of each world's budget the arm was allowed (1.0 = the world's own budget)
    budget_fraction: float = 1.0


def run_one_v3(arm_name: str, arm: Callable[..., Mapping[str, Any]], *, master_seed: bytes, campaign_id: str,
               presentation: str, seed: int = 0, measure_memory: bool = False, config: EvaluatorConfig = CONFIG_V3,
               isolation: str = "in_process", arm_spec: str | None = None,
               extra_paths: tuple[str, ...] = (), proposer_kind: str | None = None,
               budget_fraction: float = 1.0) -> RunRecordV3:
    """``proposer_kind`` defaults to the arm's role: a Mind arm's (``candidate`` / ``ablation``), else ``baseline``; any
    other kind invalidates the run."""
    rec = RunRecordV3(arm_name, seed, campaign_id, presentation, memory_instrumented=measure_memory, isolation=isolation)
    role = MIND_ARMS[arm_name][3] if arm_name in MIND_ARMS else "baseline"
    rec.proposer_kind = role if proposer_kind is None else str(proposer_kind)
    if rec.proposer_kind != role:
        rec.invalid(f"proposer kind {rec.proposer_kind!r} is not arm {arm_name}'s role {role!r}")
        return rec
    if isinstance(budget_fraction, bool) or not isinstance(budget_fraction, (int, float)) or not 0 < budget_fraction <= 1:
        rec.invalid(f"budget fraction {budget_fraction!r} is not in (0, 1]")
        return rec
    rec.budget_fraction = float(budget_fraction)
    if pathlib.Path(engcore.__file__).resolve() != (ROOT / "src" / "engcore" / "__init__.py").resolve():
        rec.invalid(f"this run's engcore ({engcore.__file__}) is not the tree the identity hashes")
        return rec
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
        _run_v3(rec, arm, master_seed, campaign_id, presentation, seed, measure_memory, config, rec.budget_fraction)
    except Exception as exc:  # noqa: BLE001 - every failure is a recorded benchmark-invalid run, never a lost record
        rec.invalid(f"run aborted: {type(exc).__name__}: {str(exc)[:300]}")
    finally:
        if host is not None:
            host.close()
    return rec


def _run_v3(rec: RunRecordV3, arm: Callable[..., Mapping[str, Any]], master_seed: bytes, campaign_id: str,
            presentation: str, seed: int, measure_memory: bool, config: EvaluatorConfig,
            budget_fraction: float = 1.0) -> None:
    if config.digest != CONFIG_V3.digest or score_v3.v2.credit_digest(dict(config.credit)) != score_v3.CREDIT_DIGEST:
        rec.invalid("the evaluator configuration is not the sealed v0.3 one")
        return
    rec.config_digest = config.digest
    service = EscrowServiceV3(master_seed=master_seed, transport_label="in_process")
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
        budget = int(shown_card["query_budget"])
        try:
            cap = query_cap(shown_card, budget_fraction)
        except ValueError as exc:                        # the benchmark's failure, never the proposer's
            rec.invalid(f"budget fraction cannot be applied to {uid}: {exc}")
            raise
        if cap != budget:
            shown_card = {**shown_card, "query_budget": cap}
        shown[uid] = shown_card
        if p.historical is not None:
            traps[uid] = p
        wrapped = TranslatingClient(client, p)
        t0 = time.perf_counter()
        proposal = dict(arm(shown_card, QueryCap(wrapped, cap), seed=seed))
        per_universe[uid] = {"proposer_seconds": time.perf_counter() - t0, "observe_calls": wrapped.calls,
                             "query_cap": cap, "query_budget": budget}
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
                                     proposer_identity={"kind": rec.proposer_kind, "id": rec.arm}, config=config,
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
    rules = sorted({str(body.get("rule")) for body in scored.values()})
    rec.escrow_rule = rules[0] if len(rules) == 1 else ("NO_SCORED_LAWS" if not rules else "MIXED:" + ",".join(rules))
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


__all__ = ["CONFIG_V3", "QueryCap", "RunRecordV3", "SUBSTRATE_V3_FILES", "V3_FILES", "development_identity",
           "engcore_closure", "query_cap", "run_one_v3"]
