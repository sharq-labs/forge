"""EXC-2 (owner-approved 2026-10-29): the existing Minimal Mind as a measurement arm of the v0.3 development pilot.

The adapter only translates; ``engcore.mind.minimal`` (MIND_VERSION 1.0.0) is used as it is, with no AI proposals:

* the presented card becomes an :class:`ExperimentalProblem`: every card input (all are settable) with its box and unit,
  the observed covariates, the output and its unit, the budget and query cost, and the assessment region restricted to
  the inputs;
* the Mind observes through the escrow's client; a budget refusal reaches it as ``ObservationRefused(budget=True)``,
  any other escrow refusal as ``ObservationRefused(budget=False)``;
* its conclusion becomes a Blindfold answer by :data:`TRANSLATION`, frozen here before any run. A fitted law
  ln y = a + sum b_i ln x_i + sum c_j (ln x_j)^2 is written exactly as exp(a) * prod x_i^b_i * prod exp(c_j (ln x_j)^2).
  A REFUSED conclusion (the Mind's model is inapplicable, e.g. a non-positive observable) is answered
  ``insufficient_evidence``; an INDISTINGUISHABLE conclusion without exactly two laws is answered the same way.

Any exception inside the Mind propagates, so the campaign scores the universe ``inadmissible`` (never a credited
refusal). Four arms: the full Mind and its three ablations (``engcore.mind.minimal.runner.VARIANTS``); the
no_adaptive_selection arm replaces the Mind's experiment choice with a matched fixed space-filling design.
DEVELOPMENT_ONLY: no A2, lift or superiority claim (EXC-2).
"""

from __future__ import annotations

import math
import secrets
from typing import Any, Callable, Mapping

from engcore.blindfold.escrow import EscrowRefused, is_budget_refusal
from engcore.blindfold.expression import c, mul, pw, v
from engcore.mind.minimal.problem import ExperimentalProblem, InputSpec
from engcore.mind.minimal.runner import (FULL, NO_ADAPTIVE_SELECTION, NO_BELIEF_UPDATE, NO_FALSIFIER, ConclusionKind,
                                         FittedLaw, MindConclusion, MindConfig, ObservationRefused, run_mind)

#: Mind conclusion kind -> Blindfold answer (frozen before any run; EXC-2 forbids changing it on pilot results)
TRANSLATION = {
    ConclusionKind.LAW.value: "law",
    ConclusionKind.NO_DEPENDENCE.value: "no_law",
    ConclusionKind.INSUFFICIENT_EVIDENCE.value: "insufficient_evidence",
    ConclusionKind.UNIDENTIFIABLE_PASSIVE_ASSOCIATION.value: "confounded",
    ConclusionKind.INDISTINGUISHABLE.value: "indistinguishable",
    ConclusionKind.REFUSED.value: "insufficient_evidence",
}


def problem_from_card(card: Mapping[str, Any]) -> ExperimentalProblem:
    inputs = tuple(InputSpec(x["name"], float(x["range"][0]), float(x["range"][1]), str(x.get("unit", "1")))
                   for x in card["inputs"] if x["settable"])
    names = {x.name for x in inputs}
    region = {k: (float(lo), float(hi)) for k, (lo, hi) in card.get("assessment_region", {}).items() if k in names}
    return ExperimentalProblem(str(card["universe_id"]), inputs, tuple(card.get("observed_covariates", ())),
                               card["output"]["name"], str(card["output"].get("unit", "1")), int(card["query_budget"]),
                               float(card["query_cost"]), region)


def observer(card: Mapping[str, Any], client: Any) -> Callable[[Mapping[str, float], str], Mapping[str, float]]:
    uid = card["universe_id"]

    def observe(settings: Mapping[str, float], query_ref: str) -> Mapping[str, float]:
        try:
            return client.observe(uid, dict(settings), query_id=f"m{query_ref}-{secrets.token_hex(6)}")["observation"]
        except EscrowRefused as exc:
            raise ObservationRefused(str(exc), budget=is_budget_refusal(exc)) from exc

    return observe


def law_expression(law: FittedLaw) -> dict:
    factors = [c(math.exp(law.intercept))]
    factors += [pw(v(name), float(b)) for name, b in sorted(law.linear.items())]
    factors += [{"exp": mul(c(float(cq)), pw({"log": v(name)}, 2.0))} for name, cq in sorted(law.quadratic.items())]
    return factors[0] if len(factors) == 1 else mul(*factors)


def proposal_from(card: Mapping[str, Any], conclusion: MindConclusion) -> dict[str, Any]:
    uid, kind = card["universe_id"], conclusion.kind.value
    rationale = f"Mind {kind}: {conclusion.reason}"[:300]
    answer = TRANSLATION[kind]
    if answer == "law" and conclusion.laws:
        return {"universe_id": uid, "answer": "law", "law": law_expression(conclusion.laws[0]), "rationale": rationale}
    if answer == "indistinguishable" and len(conclusion.laws) == 2:
        return {"universe_id": uid, "answer": "indistinguishable",
                "laws": [law_expression(law) for law in conclusion.laws], "rationale": rationale}
    if answer in ("law", "indistinguishable"):
        return {"universe_id": uid, "answer": "insufficient_evidence",
                "rationale": f"Mind {kind} without its law(s): answered insufficient_evidence"}
    return {"universe_id": uid, "answer": answer, "rationale": rationale}


def _mind_arm(config: MindConfig) -> Callable[..., dict[str, Any]]:
    def arm(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
        run = run_mind(problem_from_card(card), observer(card, client), seed=seed, config=config)
        return proposal_from(card, run.conclusion)

    arm.__name__ = f"mind_{config.variant}"
    return arm


#: name -> (callable, family, stochastic, role), the arms.ARMS layout
MIND_ARMS: dict[str, tuple[Callable[..., dict[str, Any]], str, bool, str]] = {
    "mind_full": (_mind_arm(FULL), "Minimal Mind 1.0.0: adaptive selection, belief update, falsifier", True, "candidate"),
    "mind_no_adaptive_selection": (_mind_arm(NO_ADAPTIVE_SELECTION),
                                   "Mind ablation: fixed space-filling design instead of adaptive selection", True,
                                   "ablation"),
    "mind_no_belief_update": (_mind_arm(NO_BELIEF_UPDATE), "Mind ablation: prior weights only", True, "ablation"),
    "mind_no_falsifier": (_mind_arm(NO_FALSIFIER), "Mind ablation: no falsifier", True, "ablation"),
}


__all__ = ["MIND_ARMS", "TRANSLATION", "law_expression", "observer", "problem_from_card", "proposal_from"]
