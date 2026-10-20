"""The Minimal Mind as Genesis-lite arms: same signature, same card, same observe client, same budget as every baseline.

``arm(card, client, *, seed) -> proposal``.  The arm sees exactly what a v0.2 baseline sees: the presented card and an
observe client whose budget the escrow enforces.  It translates the card into a name-free
:class:`engcore.mind.minimal.ExperimentalProblem`, runs the loop, and maps the conclusion onto the Blindfold answer
vocabulary:

=========================================  =====================================================
Mind conclusion                            Blindfold answer
=========================================  =====================================================
LAW                                        ``law`` (the fitted law in the expression grammar)
NO_DEPENDENCE                              ``no_law``
UNIDENTIFIABLE_PASSIVE_ASSOCIATION         ``confounded``
INDISTINGUISHABLE                          ``indistinguishable`` (the two preserved rivals)
INSUFFICIENT_EVIDENCE, REFUSED             ``insufficient_evidence``
=========================================  =====================================================

Trace export: when the operator sets ``TMPDIR`` to a directory holding a ``forge-mind-traces`` folder, the arm writes
its full trace there, named by the digest of the card it was shown (the operator pairs it with the run record's
``presented_card_digests``).  The trace never reaches scoring; it is read after the campaign for prediction scoring and
replay.  Nothing the arm writes can reach another proposer: every campaign runs in a fresh process.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import pathlib
from typing import Any, Mapping

from engcore.blindfold.escrow import EscrowRefused, is_budget_refusal
from engcore.blindfold.expression import c, mul, pw, v
from engcore.mind.minimal import (
    VARIANTS, ConclusionKind, ExperimentalProblem, FittedLaw, InputSpec, MindConfig, ObservationRefused, run_mind,
)

ARM_PREFIX = "mind_"
_SEARCHES: list[str] = []
TRACE_FOLDER = "forge-mind-traces"


def card_digest(card: Mapping[str, Any]) -> str:
    """The harness's own card digest (``harness._digest``), so a trace pairs with ``presented_card_digests``."""
    return hashlib.sha256(json.dumps(card, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def problem_from_card(card: Mapping[str, Any]) -> ExperimentalProblem:
    inputs = tuple(InputSpec(x["name"], x["range"][0], x["range"][1], x.get("unit", "1")) for x in card["inputs"]
                   if x.get("settable", True))
    region = {k: (float(lo), float(hi)) for k, (lo, hi) in card.get("assessment_region", {}).items()}
    return ExperimentalProblem(problem_id=str(card["universe_id"]), inputs=inputs,
                               covariates=tuple(card.get("observed_covariates", ())), observable=card["output"]["name"],
                               observable_unit=card["output"].get("unit", "1"), budget=int(card["query_budget"]),
                               query_cost=float(card.get("query_cost", 1.0)), region=region)


def law_expression(law: FittedLaw) -> dict:
    """exp(a) * prod x_i^b_i * prod exp(c_j ln(x_j)^2), in the Blindfold grammar."""
    factors: list[dict] = [c(math.exp(law.intercept))]
    factors += [pw(v(n), float(b)) for n, b in sorted(law.linear.items())]
    factors += [{"exp": mul(c(float(q)), {"log": v(n)}, {"log": v(n)})} for n, q in sorted(law.quadratic.items())]
    return factors[0] if len(factors) == 1 else mul(*factors)


def _proposal(card: Mapping[str, Any], kind: ConclusionKind, laws: tuple[FittedLaw, ...], reason: str) -> dict[str, Any]:
    uid = card["universe_id"]
    if kind is ConclusionKind.LAW:
        return {"universe_id": uid, "answer": "law", "law": law_expression(laws[0]), "rationale": reason}
    if kind is ConclusionKind.INDISTINGUISHABLE:
        return {"universe_id": uid, "answer": "indistinguishable", "laws": [law_expression(x) for x in laws[:2]],
                "rationale": reason}
    answer = {ConclusionKind.NO_DEPENDENCE: "no_law", ConclusionKind.UNIDENTIFIABLE_PASSIVE_ASSOCIATION: "confounded"}.get(
        kind, "insufficient_evidence")
    return {"universe_id": uid, "answer": answer, "rationale": reason}


def run_on_card(card: Mapping[str, Any], client: Any, *, seed: int, config: MindConfig) -> tuple[dict[str, Any], dict[str, Any]]:
    problem = problem_from_card(card)
    uid = card["universe_id"]

    def observe(settings: Mapping[str, float], query_ref: str) -> Mapping[str, float]:
        try:
            return client.observe(uid, dict(settings), query_id=query_ref)["observation"]
        except EscrowRefused as exc:
            raise ObservationRefused(str(exc), budget=is_budget_refusal(exc)) from None

    # one run is one declared search: a world searched twice in one process is a second search with its own ledger
    _SEARCHES.append(uid)
    ledger = f"mind:{config.variant}:{uid}:search{len(_SEARCHES)}"
    run = run_mind(problem, observe, seed=seed, config=config, ledger_campaign=ledger)
    con = run.conclusion
    proposal = _proposal(card, con.kind, con.laws, con.reason[:400])
    return proposal, run.trace


def _export(card: Mapping[str, Any], trace: Mapping[str, Any], variant: str, seed: int) -> None:
    root = os.environ.get("TMPDIR", "")
    folder = pathlib.Path(root) / TRACE_FOLDER if root else None
    if folder is None or not folder.is_dir():
        return
    name = f"{variant}-{seed}-{card_digest(card)}.json"
    blob = json.dumps({"card_digest": card_digest(card), "card": dict(card), "trace": trace}, sort_keys=True,
                      separators=(",", ":"), default=str).encode()
    (folder / name).write_bytes(blob)


def _arm(variant: str):
    config = VARIANTS[variant]

    def arm(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
        proposal, trace = run_on_card(card, client, seed=seed, config=config)
        _export(card, trace, variant, seed)
        return proposal

    arm.__name__ = f"{ARM_PREFIX}{variant}"
    return arm


mind_full = _arm("full")
mind_no_belief_update = _arm("no_belief_update")
mind_no_adaptive_selection = _arm("no_adaptive_selection")
mind_no_falsifier = _arm("no_falsifier")

#: candidate arm name -> (module:function spec for the isolated proposer process, Mind variant)
MIND_ARMS = {f"{ARM_PREFIX}{k}": (f"benchmarks.genesis_lite_mind.arm:{ARM_PREFIX}{k}", k) for k in VARIANTS}
