"""Genesis-lite v0.3 DRAFT: the evaluator half of FDA-05 (standard library only; never engcore).

FDA-05 (deep audit 2026-10-19, R-05 EXECUTED_REPRODUCED): under the v0.2 pair rule a pair whose two laws diverge
without limit outside the query box brackets every finite truth. One pair built only from an in-box fit and the public
box edge (A/B = 1.3e30 at the region edge) earned ``indistinguishable_hit`` (+1.0) for two mutually exclusive truths,
above the honest refusal (+0.5). UNKNOWN became knowledge.

v0.3 rule (ODC-05a option (i), proposed): the v0.2 conditions (a)-(d) are kept unchanged, and condition (d) becomes

    (d') one law passes, OR [the pair brackets the truth at PASS_FRACTION of the evaluation points AND at EVERY
         evaluation point outside the box both laws are finite, non-zero and of one sign, with
         max(|A|, |B|) / min(|A|, |B|) <= 1 + w].

The bound applies to the BRACKET route only. The pass route is left as v0.2 had it; note that it credits +1.0 to a
passing law paired with ANY in-box-agreeing, outside-diverging partner, where the law alone scores 0.0 in an
INDISTINGUISHABLE world (independent review 2026-10-19, finding 2; a v0.2 property, open as ODC-05d). The
generator's honest rival differs from the law by a factor ``1 + d (g / g_max)^m`` that grows WITHOUT LIMIT outside the
box (``engcore.blindfold.universe._rival``), so a bound on every hit would refuse correct answers. Whether the bound
should cover every hit instead is part of ODC-05a (see the decision record).

``w`` is an OWNER DECISION (ODC-05b) and has no default here. :data:`PAIR_BOUND` is the literal
``OWNER_DECISION_REQUIRED``, and scoring refuses without an explicit :class:`PairBound`. The owner's choice must be
justified from the rule's purpose and NEVER tuned on pilot or formal worlds. ``w <= tol`` is admissible and means
option (iii): condition (c) needs a ratio above ``1 + tol`` at half the outside points, so no pair can then hit through
the bracket.

The credit table is unchanged (same digest as v0.2); the rule, and hence the evaluator identity, changes. The certified
escrow (``engcore.blindfold.escrow._assess_pair``) must apply the same bound (the escrow half of FDA-05, Batch A,
OD-3). Until it does, a v0.3 run on such a pair is ``EVALUATOR_DISAGREEMENT``: invalid, never credited.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..evaluator.expr import ExpressionInvalid, check, value
from ..evaluator.score import (
    CREDIT, CREDIT_DIGEST, PASS_FRACTION, REFUSALS, EvaluatorRefused, _outside, _pair_hit, credit_digest, fraction_within,
)

EVALUATOR_SCHEMA = "forge.genesis_lite.independent_evaluator/3"
OWNER_DECISION_REQUIRED = "OWNER_DECISION_REQUIRED"
#: ODC-05b: the owner's w. Never defaulted; a v0.3 identity cannot be FROZEN while this is the literal below.
PAIR_BOUND: Any = OWNER_DECISION_REQUIRED
BOUND_FORMS = ("absolute", "tol_multiple")


@dataclass(frozen=True)
class PairBound:
    """The outside-box informativeness bound. ``absolute``: w = value. ``tol_multiple``: w = value x the universe's
    tolerance (ODC-05b offers both forms)."""

    form: str
    value: float

    def w(self, tol: float) -> float:
        return float(self.value) * (float(tol) if self.form == "tol_multiple" else 1.0)

    def to_dict(self) -> dict[str, Any]:
        return {"form": self.form, "value": float(self.value)}


def _checked(bound: Any) -> PairBound:
    if not isinstance(bound, PairBound):
        raise EvaluatorRefused(f"the pair bound w is an owner decision (ODC-05b) and has no default; got {bound!r}")
    if bound.form not in BOUND_FORMS:
        raise EvaluatorRefused(f"unknown pair-bound form {bound.form!r}; ODC-05a option (i) offers {BOUND_FORMS}")
    if isinstance(bound.value, bool) or not isinstance(bound.value, (int, float)) or not math.isfinite(bound.value) \
            or bound.value <= 0:
        raise EvaluatorRefused(f"the pair bound must be a finite positive number; got {bound.value!r}")
    return bound


def informative_outside(laws: Sequence[Mapping[str, Any]], entry: Mapping[str, Any], w: float) -> bool:
    """Whether the pair's spread is at most a factor 1 + w at every evaluation point outside the box."""
    a_law, b_law = laws
    outside = [p for p, _ in entry["evaluation"] if _outside(p, entry["box"])]
    if not outside:
        return False
    for p in outside:
        a, b = value(a_law, p), value(b_law, p)
        if not (math.isfinite(a) and math.isfinite(b)) or a == 0 or b == 0 or (a > 0) != (b > 0):
            return False
        if max(abs(a), abs(b)) / min(abs(a), abs(b)) > 1.0 + w:
            return False
    return True


def pair_hit(laws: Sequence[Mapping[str, Any]], entry: Mapping[str, Any], bound: PairBound) -> bool:
    """v0.2 conditions (a)-(d) (reused, not re-implemented) restricted by (d'). Since v0.2's (d) is ``pass or
    bracket``, ``v0.2 hit and (pass or informative)`` equals ``(a)-(c) and (pass or (bracket and informative))``."""
    if not _pair_hit(laws, entry):
        return False
    tol = float(entry["tolerance"])
    if any(fraction_within(law, entry["evaluation"], tol) >= PASS_FRACTION for law in laws):
        return True
    return informative_outside(laws, entry, bound.w(tol))


def score_universe(proposal: Mapping[str, Any], entry: Mapping[str, Any], *, bound: Any,
                   table: Mapping[str, Mapping[str, float]] = CREDIT) -> dict[str, Any]:
    """v0.2's ``score_universe`` with the v0.3 pair rule. ``bound`` is required and never defaulted."""
    bound = _checked(bound)
    kind = str(entry["kind"])
    answer = proposal.get("answer")
    allowed = set(entry["variables"])
    tol = float(entry["tolerance"])
    fractions: list[float] = []
    try:
        if answer == "law":
            if not check(proposal["law"]) <= allowed:
                raise ExpressionInvalid("the law uses variables not in the universe")
            fractions = [fraction_within(proposal["law"], entry["evaluation"], tol)]
            outcome = "law_pass" if fractions[0] >= PASS_FRACTION else "law_fail"
        elif answer == "indistinguishable":
            laws = list(proposal.get("laws", ()))
            if len(laws) != 2 or not all(check(law) <= allowed for law in laws):
                raise ExpressionInvalid("an indistinguishable answer names two admissible laws")
            fractions = [fraction_within(law, entry["evaluation"], tol) for law in laws]
            outcome = "indistinguishable_hit" if pair_hit(laws, entry, bound) else "indistinguishable_miss"
        elif answer in REFUSALS or answer == "inadmissible":
            outcome = str(answer)
        else:
            raise ExpressionInvalid(f"unknown answer {answer!r}")
    except (ExpressionInvalid, KeyError, TypeError) as exc:
        raise EvaluatorRefused(f"universe {entry.get('universe_id')}: unscorable sealed proposal ({exc})") from exc
    return {"universe_id": entry["universe_id"], "kind": kind, "outcome": outcome, "fractions": fractions,
            "credit": float(table.get(kind, {}).get(outcome, 0.0))}


def evaluate_campaign(proposals: Mapping[str, Mapping[str, Any]], key: Mapping[str, Any],
                      escrow: Mapping[str, Mapping[str, Any]], *, expected_credit_digest: str,
                      bound: Any, expected_pair_bound: Any) -> dict[str, Any]:
    """v0.2's ``evaluate_campaign`` with the v0.3 rule: VALID only when outcome, credit and every per-law fraction agree
    with the escrow's adjudication of every universe. ``expected_pair_bound`` is the value the FROZEN preregistration
    records (``evaluator.pair_bound``): a caller-chosen w is never trusted (a huge w restores v0.2's credit)."""
    bound = _checked(bound)
    if credit_digest(CREDIT) != expected_credit_digest:
        raise EvaluatorRefused("the evaluator's credit table is not the preregistered one")
    if not isinstance(expected_pair_bound, Mapping) or dict(expected_pair_bound) != bound.to_dict():
        raise EvaluatorRefused(f"the pair bound {bound.to_dict()} is not the preregistered one ({expected_pair_bound!r})")
    entries = {e["universe_id"]: e for e in key["universes"]}
    if set(entries) != set(proposals) or set(entries) != set(escrow):
        return {"status": "KEY_MISMATCH", "results": [], "disagreements": [],
                "detail": "the answer key, the sealed proposals and the escrow adjudications name different universes"}
    results, disagreements = [], []
    for uid in sorted(entries):
        mine = score_universe(proposals[uid], entries[uid], bound=bound)
        theirs = escrow[uid]
        theirs_fr = list(theirs.get("fractions", []))
        agree = (mine["kind"] == theirs["kind"] and mine["outcome"] == theirs["outcome"]
                 and math.isclose(mine["credit"], float(theirs["credit"]), abs_tol=1e-12)
                 and len(theirs_fr) == len(mine["fractions"])
                 and all(math.isclose(a, b, abs_tol=1e-12) for a, b in zip(mine["fractions"], theirs_fr)))
        results.append({**mine, "escrow_outcome": theirs["outcome"], "agree": agree})
        if not agree:
            disagreements.append(uid)
    return {"status": "VALID" if not disagreements else "EVALUATOR_DISAGREEMENT", "results": results,
            "disagreements": disagreements, "schema": EVALUATOR_SCHEMA, "credit_digest": CREDIT_DIGEST,
            "pair_bound": bound.to_dict()}
