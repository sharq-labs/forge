"""The v0.3 escrow scoring rules (owner decision 2026-10-29, option B), beside the byte-pinned v0.2 ``escrow.py``.

``escrow.py`` is pinned by the Genesis-lite v0.2 preregistration and stays unchanged. :class:`EscrowServiceV3` is the same
service with one difference: it scores with the rules the independent v0.3 evaluator uses, so the escrow's facts and that
evaluator agree by construction instead of failing a campaign on every disagreement:

1. in-box agreement and 2. outside divergence use |a-b|/max(|a|,|b|) -- symmetric in the two laws, zero for two zeros
   (owner-approved v3 pair distance);
3. a pair brackets a truth when lo - tol|lo| <= truth <= hi + tol|hi| (sign-correct for negative values);
4. outside divergence counts every outside point, whatever its truth (the two laws' divergence needs no truth);
5. an exact zero prediction of a zero truth is within tolerance (owner-approved S-05; no new absolute tolerance).

A law that cannot be evaluated at a point (an arithmetic or domain error, or a non-finite value) is non-finite there, as
in the evaluator, never a crash. Score bodies keep the v0.2 keys (``hit`` still means "eligible and contains or brackets
the truth"; the v0.3 adjudication turns a bracketing-only hit into ``indistinguishable_unresolved``) and add
``"rule": "v0_3"``. Same-process code is trusted; this module is no isolation boundary.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from typing import Any

from .escrow import (_HEX64, PAIR_DIFFER_FRACTION, PASS_FRACTION, SCORED_ANSWERS, EscrowRefused, EscrowService,
                     _digest)
from .expression import ExpressionRefused, evaluate, structure_digest, validate
from .universe import truth_at

RULE = "v0_3"


def value_v3(law: Mapping[str, Any], point: Mapping[str, float]) -> float:
    try:
        out = evaluate(law, point)
    except (ArithmeticError, ValueError, KeyError):
        return float("nan")
    return out if math.isfinite(out) else float("nan")


def _relative_error(prediction: float, truth: float | None) -> float:
    if not math.isfinite(prediction) or truth is None or not math.isfinite(truth):
        return math.inf
    if prediction == truth:
        return 0.0
    return abs(prediction - truth) / abs(truth) if truth != 0 else math.inf


def _errors_v3(law: Mapping[str, Any], truths: Sequence[tuple[Mapping[str, float], float]]) -> list[float]:
    return [_relative_error(value_v3(law, p), t) for p, t in truths]


def fraction_v3(law: Mapping[str, Any], truths: Sequence[tuple[Mapping[str, float], float]], tolerance: float) -> float:
    if not math.isfinite(tolerance) or tolerance < 0:
        raise EscrowRefused("finite non-negative tolerance required")
    if not truths:
        return 0.0
    return sum(e <= tolerance for e in _errors_v3(law, truths)) / len(truths)


def pair_distance_v3(a: float, b: float) -> float:
    if not math.isfinite(a) or not math.isfinite(b):
        return math.inf
    scale = max(abs(a), abs(b))
    if scale == 0:
        return 0.0
    difference = abs(a - b)
    return difference / scale if math.isfinite(difference) else abs(a / scale - b / scale)


def _outside_box(point: Mapping[str, float], world: Any) -> bool:
    return any(not (x.low <= point[x.name] <= x.high) for x in world.inputs)


def assess_v3(law: Mapping[str, Any], truths: list[tuple[dict[str, float], float]], world: Any) -> dict[str, Any]:
    errs = sorted(_errors_v3(law, truths))
    within = fraction_v3(law, truths, world.tolerance)
    median = errs[len(errs) // 2]
    structure = structure_digest(law)
    return {"fraction_within_tolerance": within, "median_relative_error": median if math.isfinite(median) else None,
            "passed": within >= PASS_FRACTION,
            "structure_matches_hidden_law": bool(world.law_structure) and structure == world.law_structure,
            "structure_digest": structure}


def assess_pair_v3(laws: list[Mapping[str, Any]], truths: list[tuple[dict[str, float], float]],
                   inbox: list[tuple[dict[str, float], float]], world: Any) -> dict[str, Any]:
    tol, sigma = world.tolerance, world.noise_sigma
    if not math.isfinite(tol) or tol < 0 or not math.isfinite(sigma) or sigma < 0:
        raise EscrowRefused("finite non-negative tolerance and noise sigma required")
    a, b = laws
    points = [p for p, _t in inbox] + [p for p, _t in truths]
    finite = bool(inbox) and bool(truths) and all(math.isfinite(value_v3(law, p)) for law in laws for p in points)
    mutual = (max(pair_distance_v3(value_v3(a, p), value_v3(b, p)) for p, _t in inbox) if finite else math.inf)
    fit_in = finite and all(fraction_v3(law, inbox, tol) >= PASS_FRACTION for law in laws)
    outside = [p for p, _t in truths if _outside_box(p, world)]
    differ = sum(pair_distance_v3(value_v3(a, p), value_v3(b, p)) > tol for p in outside) if finite else 0
    differ_fraction = differ / len(outside) if outside else 0.0
    contains_truth = finite and any(fraction_v3(law, truths, tol) >= PASS_FRACTION for law in laws)
    bracket = 0
    if finite:
        for point, truth in truths:
            if truth is None or not math.isfinite(truth):
                continue
            lo, hi = sorted((value_v3(a, point), value_v3(b, point)))
            bracket += lo - tol * abs(lo) <= truth <= hi + tol * abs(hi)
    brackets = finite and bracket / len(truths) >= PASS_FRACTION
    hit = bool(finite and mutual <= sigma and fit_in and outside and differ_fraction >= PAIR_DIFFER_FRACTION
               and (contains_truth or brackets))
    return {"finite": finite, "mutual_in_box": mutual if math.isfinite(mutual) else None, "both_fit_in_box": fit_in,
            "outside_points": len(outside), "differ_fraction_outside": differ_fraction, "contains_truth": contains_truth,
            "brackets_truth": brackets, "hit": hit, "rule": RULE}


class EscrowServiceV3(EscrowService):
    """The v0.2 escrow service, scoring with the v0.3 rules (every other behaviour, journal and signature unchanged)."""

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
        result: dict[str, Any] = {"universe_id": uid, "answer": answer, "proposal_digest": pdig, "rule": RULE}
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
            result["laws"] = [assess_v3(laws[0], truths, world)]
        elif answer == "indistinguishable":
            inbox = [truth_at(world, p, rng) for p in world.inbox_points]
            result["laws"] = [assess_v3(law, truths, world) for law in laws]
            result["pair"] = assess_pair_v3(laws, truths, inbox, world)
        result["universe_kind"] = world.kind.value                          # revealed only after the sealed submission
        result["tolerance"] = world.tolerance
        receipt = self._record(camp, "score", {"universe_id": uid, "proposal_digest": pdig, "query_id": req["query_id"]},
                               result, 0.0, state={"universe_id": uid, "proposal_digest": pdig})
        return {**result, "receipt": receipt, "budget_consumed": 0.0}


__all__ = ["EscrowServiceV3", "RULE", "assess_pair_v3", "assess_v3", "fraction_v3", "pair_distance_v3", "value_v3"]
