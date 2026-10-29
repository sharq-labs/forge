"""EXC-2 (owner-approved 2026-10-29): the existing Minimal Mind as a measurement arm of the v0.3 development pilot.

The adapter only translates; ``engcore.mind.minimal`` (MIND_VERSION 1.0.0) is used as it is, with no AI proposals:

* the presented card becomes an :class:`ExperimentalProblem` only when the Mind can state it exactly: every input
  settable, an assessment region over exactly the inputs, and a unit query cost (the Mind counts its budget in queries).
  Anything else raises :class:`MindAdapterError`;
* the Mind observes through the escrow's client; a budget refusal reaches it as ``ObservationRefused(budget=True)``. Any
  other escrow refusal is re-raised as it is, exactly as the baselines' ``arms._collect`` does. An observation must name
  exactly the card's inputs, covariates and output with finite values (a non-positive output is the Mind's to judge);
  anything else raises, so a malformed observation never becomes the Mind's model refusal;
* its conclusion becomes a Blindfold answer by :data:`TRANSLATION`, frozen here before any run. A fitted law
  ln y = a + sum b_i ln x_i + sum c_j (ln x_j)^2 is written exactly as exp(a) * prod x_i^b_i * prod exp(c_j (ln x_j)^2).
  A REFUSED conclusion (the Mind's model is inapplicable, e.g. a non-positive observable) is answered
  ``insufficient_evidence`` with a rationale starting ``Mind refused`` so it can be reported apart. A LAW or
  INDISTINGUISHABLE conclusion without its law(s) cannot happen in MIND_VERSION 1.0.0 and raises.

Every failure (an adapter error, a non-budget refusal, any exception inside the Mind) propagates, so the campaign scores
the universe ``inadmissible`` (-1), never a credited refusal. Four arms: the full Mind and its three ablations
(``engcore.mind.minimal.runner.VARIANTS``); see :data:`MIND_ARMS` for exactly what each ablation removes.
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


class MindAdapterError(RuntimeError):
    """The card or the Mind's conclusion cannot be translated exactly; the universe is scored inadmissible."""


def problem_from_card(card: Mapping[str, Any]) -> ExperimentalProblem:
    if not all(x.get("settable") is True for x in card["inputs"]):
        raise MindAdapterError("a non-settable input: the Mind's problem has settable inputs and covariates only")
    inputs = tuple(InputSpec(x["name"], float(x["range"][0]), float(x["range"][1]), str(x.get("unit", "1")))
                   for x in card["inputs"])
    names = {x.name for x in inputs}
    stated = card.get("assessment_region")
    if not isinstance(stated, Mapping) or set(stated) != names:
        raise MindAdapterError("the assessment region must name exactly the card's inputs")
    if float(card["query_cost"]) != 1.0:
        raise MindAdapterError("the Mind counts its budget in queries: a query cost other than 1 is not stated exactly")
    region = {k: (float(lo), float(hi)) for k, (lo, hi) in stated.items()}
    return ExperimentalProblem(str(card["universe_id"]), inputs, tuple(card.get("observed_covariates", ())),
                               card["output"]["name"], str(card["output"].get("unit", "1")), int(card["query_budget"]),
                               float(card["query_cost"]), region)


def observer(card: Mapping[str, Any], client: Any) -> Callable[[Mapping[str, float], str], Mapping[str, float]]:
    uid = card["universe_id"]
    expected = ({x["name"] for x in card["inputs"]} | set(card.get("observed_covariates", ()))
                | {card["output"]["name"]})

    def observe(settings: Mapping[str, float], query_ref: str) -> Mapping[str, float]:
        try:
            obs = client.observe(uid, dict(settings), query_id=f"m{query_ref}-{secrets.token_hex(6)}")["observation"]
        except EscrowRefused as exc:
            if not is_budget_refusal(exc):
                raise                               # a malformed query is the arm's failure, never a refusal to answer
            raise ObservationRefused(str(exc), budget=True) from exc
        if set(obs) != expected or not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
                                           for x in obs.values()):
            raise MindAdapterError(f"an observation must name exactly {sorted(expected)} with finite values")
        return obs

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
    if answer == "law":
        if not conclusion.laws:
            raise MindAdapterError("a LAW conclusion without its law")
        return {"universe_id": uid, "answer": "law", "law": law_expression(conclusion.laws[0]), "rationale": rationale}
    if answer == "indistinguishable":
        if len(conclusion.laws) != 2:
            raise MindAdapterError(f"an INDISTINGUISHABLE conclusion with {len(conclusion.laws)} laws, not two")
        return {"universe_id": uid, "answer": "indistinguishable",
                "laws": [law_expression(law) for law in conclusion.laws], "rationale": rationale}
    return {"universe_id": uid, "answer": answer, "rationale": rationale}


def _mind_arm(config: MindConfig) -> Callable[..., dict[str, Any]]:
    def arm(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
        run = run_mind(problem_from_card(card), observer(card, client), seed=seed, config=config)
        refusal = run.trace.get("refusal")
        if refusal is not None and not refusal["budget"]:    # unreachable while observer re-raises; kept fail-closed
            raise MindAdapterError(f"the Mind stopped on a non-budget refusal: {refusal['message']}")
        return proposal_from(card, run.conclusion)

    arm.__name__ = f"mind_{config.variant}"
    return arm


#: name -> (callable, family, stochastic, role), the arms.ARMS layout
MIND_ARMS: dict[str, tuple[Callable[..., dict[str, Any]], str, bool, str]] = {
    "mind_full": (_mind_arm(FULL), "Minimal Mind 1.0.0: adaptive selection, belief update, falsifier", True, "candidate"),
    # same initial design, seed and budget as the full Mind; after it a preset space-filling design replaces adaptive
    # selection, which also removes the falsifier-targeted experiments and the early stop once the leader is decided
    "mind_no_adaptive_selection": (_mind_arm(NO_ADAPTIVE_SELECTION),
                                   "Mind ablation: fixed space-filling design after the shared initial design (no "
                                   "adaptive selection, no falsifier-targeted experiments, no early stop on a decided "
                                   "leader)", True, "ablation"),
    # prior weights steer experiment selection only; the conclusion still uses the posterior
    "mind_no_belief_update": (_mind_arm(NO_BELIEF_UPDATE), "Mind ablation: prior weights in experiment selection only "
                              "(the conclusion still uses the posterior)", True, "ablation"),
    "mind_no_falsifier": (_mind_arm(NO_FALSIFIER), "Mind ablation: no falsifier", True, "ablation"),
}


__all__ = ["MIND_ARMS", "MindAdapterError", "TRANSLATION", "law_expression", "observer", "problem_from_card", "proposal_from"]
