"""Separately implemented scoring of sealed Genesis-lite proposals against a revealed answer key (standard library only).

Independence here is CODE independence (another implementation, no import path into engcore, written by the same team).
It is a port of the preregistered rule text below; where that text leaves a choice open (denominators, guards), the
choice is spelled out here and in the preregistration, and the escrow's per-law ``fraction_within_tolerance`` is
compared with this module's value for every law, not only the discrete outcome (review M3). A bug shared through the
generator or the truth function (``engcore.blindfold.universe``) is a COMMON-MODE risk that this check cannot see.

Preregistered rules:

* LAW: relative error |pred - truth| / |truth| at each hidden evaluation point (infinite where the truth is zero or
  non-finite, or the prediction is not finite). The law PASSES when at least ``PASS_FRACTION`` of the points are within
  the universe's tolerance.
* INDISTINGUISHABLE pair (laws A, B): a HIT only when (a) both laws are finite at every in-box and evaluation point;
  (b) max over in-box points with B != 0 of |A - B| / |B| <= the noise sigma, and each law passes on the in-box truths;
  (c) at least ``PAIR_DIFFER_FRACTION`` of the evaluation points OUTSIDE the box (none: no hit) have B != 0 and
  |A - B| / |B| > tolerance; (d) one law passes, or min(A,B)(1 - tol) <= truth <= max(A,B)(1 + tol) at PASS_FRACTION of
  the evaluation points (points with a non-finite truth count as not bracketed).
* A refusal scores as itself; an inadmissible record scores as ``inadmissible``. Credit comes from the frozen table
  ``CREDIT``; unlisted outcomes score 0.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Mapping, Sequence

from .expr import ExpressionInvalid, check, value

EVALUATOR_SCHEMA = "forge.genesis_lite.independent_evaluator/2"
PASS_FRACTION = 0.9
PAIR_DIFFER_FRACTION = 0.5
REFUSALS = ("no_law", "insufficient_evidence", "confounded")

#: credit[kind][outcome]. Frozen in the preregistration by digest; a different table is a different benchmark.
CREDIT: Mapping[str, Mapping[str, float]] = {
    "discoverable": {"law_pass": 1.0, "law_fail": -1.0, "indistinguishable_hit": -0.5, "indistinguishable_miss": -1.0,
                     "inadmissible": -1.0},
    "no_solution": {"no_law": 1.0, "law_pass": -1.0, "law_fail": -1.0, "indistinguishable_hit": -1.0,
                    "indistinguishable_miss": -1.0, "inadmissible": -1.0},
    "insufficient_evidence": {"insufficient_evidence": 1.0, "law_pass": 0.0, "law_fail": -1.0, "indistinguishable_hit": -1.0,
                              "indistinguishable_miss": -1.0, "inadmissible": -1.0},
    "indistinguishable": {"indistinguishable_hit": 1.0, "insufficient_evidence": 0.5, "law_pass": 0.0, "law_fail": -1.0,
                          "indistinguishable_miss": -1.0, "inadmissible": -1.0},
    "spurious_correlate": {"law_pass": 1.0, "law_fail": -1.0, "indistinguishable_hit": -0.5, "indistinguishable_miss": -1.0,
                           "inadmissible": -1.0},
    "confounded": {"confounded": 1.0, "law_pass": 1.0, "law_fail": -1.0, "indistinguishable_hit": -1.0,
                   "indistinguishable_miss": -1.0, "inadmissible": -1.0},
}


class EvaluatorRefused(RuntimeError):
    """The evaluation cannot be performed as preregistered (changed table, key mismatch, malformed input)."""


def _canonical(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def credit_digest(table: Mapping[str, Mapping[str, float]]) -> str:
    return hashlib.sha256(_canonical({k: dict(sorted(v.items())) for k, v in sorted(table.items())})).hexdigest()


CREDIT_DIGEST = credit_digest(CREDIT)


def _rel_errors(law: Mapping[str, Any], truths: Sequence[Sequence[Any]]) -> list[float]:
    out = []
    for point, truth in truths:
        if truth is None or not math.isfinite(truth) or truth == 0:
            out.append(math.inf)
            continue
        pred = value(law, point)
        out.append(abs(pred - truth) / abs(truth) if math.isfinite(pred) else math.inf)
    return out


def fraction_within(law: Mapping[str, Any], truths: Sequence[Sequence[Any]], tol: float) -> float:
    errs = _rel_errors(law, truths)
    return sum(e <= tol for e in errs) / len(errs) if errs else 0.0


def _outside(point: Mapping[str, float], box: Mapping[str, Sequence[float]]) -> bool:
    return any(not (lo <= point[name] <= hi) for name, (lo, hi) in box.items())


def _pair_hit(laws: Sequence[Mapping[str, Any]], entry: Mapping[str, Any]) -> bool:
    tol, sigma, box = float(entry["tolerance"]), float(entry["noise_sigma"]), entry["box"]
    truths, inbox = entry["evaluation"], entry["inbox"]
    points = [p for p, _ in inbox] + [p for p, _ in truths]
    if not all(math.isfinite(value(law, p)) for law in laws for p in points):
        return False
    a_law, b_law = laws
    mutual = max((abs(value(a_law, p) - value(b_law, p)) / abs(value(b_law, p)) for p, _ in inbox if value(b_law, p) != 0),
                 default=math.inf)
    if not mutual <= sigma:
        return False
    if not all(fraction_within(law, inbox, tol) >= PASS_FRACTION for law in laws):
        return False
    outside = [(p, t) for p, t in truths if _outside(p, box)]
    if not outside:
        return False
    differ = bracket = 0
    for p, t in truths:
        if t is None or not math.isfinite(t):
            continue
        a, b = value(a_law, p), value(b_law, p)
        if min(a, b) * (1 - tol) <= t <= max(a, b) * (1 + tol):
            bracket += 1
        if _outside(p, box) and b != 0 and abs(a - b) / abs(b) > tol:
            differ += 1
    if differ / len(outside) < PAIR_DIFFER_FRACTION:
        return False
    return any(fraction_within(law, truths, tol) >= PASS_FRACTION for law in laws) or bracket / len(truths) >= PASS_FRACTION


def score_universe(proposal: Mapping[str, Any], entry: Mapping[str, Any], *,
                   table: Mapping[str, Mapping[str, float]] = CREDIT) -> dict[str, Any]:
    """Outcome, credit and per-law fraction within tolerance of one sealed proposal under the preregistered rules."""
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
            outcome = "indistinguishable_hit" if _pair_hit(laws, entry) else "indistinguishable_miss"
        elif answer in REFUSALS or answer == "inadmissible":
            outcome = str(answer)
        else:
            raise ExpressionInvalid(f"unknown answer {answer!r}")
    except (ExpressionInvalid, KeyError, TypeError) as exc:
        raise EvaluatorRefused(f"universe {entry.get('universe_id')}: unscorable sealed proposal ({exc})") from exc
    return {"universe_id": entry["universe_id"], "kind": kind, "outcome": outcome, "fractions": fractions,
            "credit": float(table.get(kind, {}).get(outcome, 0.0))}


def evaluate_campaign(proposals: Mapping[str, Mapping[str, Any]], key: Mapping[str, Any],
                      escrow: Mapping[str, Mapping[str, Any]], *, expected_credit_digest: str) -> dict[str, Any]:
    """Score every sealed proposal; compare with the escrow's adjudication. Status is VALID only on full agreement.

    ``escrow`` maps universe_id -> {"kind", "outcome", "credit"} and, when the escrow scored laws, "fractions" (its
    ``fraction_within_tolerance`` per law, in order). Outcomes, credits and every fraction must agree.
    """
    if credit_digest(CREDIT) != expected_credit_digest:
        raise EvaluatorRefused("the evaluator's credit table is not the preregistered one")
    entries = {e["universe_id"]: e for e in key["universes"]}
    if set(entries) != set(proposals) or set(entries) != set(escrow):
        return {"status": "KEY_MISMATCH", "results": [], "disagreements": [],
                "detail": "the answer key, the sealed proposals and the escrow adjudications name different universes"}
    results, disagreements = [], []
    for uid in sorted(entries):
        mine = score_universe(proposals[uid], entries[uid])
        theirs = escrow[uid]
        theirs_fr = list(theirs.get("fractions", []))       # a scored law the escrow reported no fraction for: disagreement
        agree = (mine["kind"] == theirs["kind"] and mine["outcome"] == theirs["outcome"]
                 and math.isclose(mine["credit"], float(theirs["credit"]), abs_tol=1e-12)
                 and len(theirs_fr) == len(mine["fractions"])
                 and all(math.isclose(a, b, abs_tol=1e-12) for a, b in zip(mine["fractions"], theirs_fr)))
        results.append({**mine, "escrow_outcome": theirs["outcome"], "agree": agree})
        if not agree:
            disagreements.append(uid)
    return {"status": "VALID" if not disagreements else "EVALUATOR_DISAGREEMENT", "results": results,
            "disagreements": disagreements, "schema": EVALUATOR_SCHEMA, "credit_digest": CREDIT_DIGEST}


def in_monomial_family(law: Any) -> bool:
    """Whether a hidden law lies inside the v0 searched family: a constant times powers of variables only."""
    if law is None:
        return False
    if not isinstance(law, Mapping) or len(law) != 1:
        return False
    ((op, arg),) = law.items()
    if op in ("const", "var"):
        return True
    if op == "mul":
        return all(in_monomial_family(a) for a in arg)
    if op == "pow":
        return in_monomial_family(arg[0])
    return False


def region_tell(card: Mapping[str, Any]) -> str:
    """The KNOWN structural tell of the Blindfold generator, computed from a card only (review M2): a box-shaped
    assessment region rules out INDISTINGUISHABLE; an extended region pushed further than an ordinary one
    (near > 0.5 or far > 1.3 box spans) can only be INDISTINGUISHABLE. Returns 'box', 'ordinary_extension' or
    'pushed_extension'."""
    box = {x["name"]: x["range"] for x in card["inputs"]}
    pushed = extended = False
    for name, (lo, hi) in card.get("assessment_region", {}).items():
        b_lo, b_hi = box[name]
        span = math.log(b_hi / b_lo)
        if hi > b_hi * (1 + 1e-9):
            near, far = math.log(lo / b_hi) / span, math.log(hi / b_hi) / span
        elif lo < b_lo * (1 - 1e-9):
            near, far = math.log(b_lo / hi) / span, math.log(b_lo / lo) / span
        else:
            continue
        extended = True
        pushed = pushed or near > 0.5 + 1e-6 or far > 1.3 + 1e-6
    return "pushed_extension" if pushed else ("ordinary_extension" if extended else "box")


#: keys a presented card may carry; anything else is a leak channel until it is reviewed and added
CARD_KEYS = frozenset({"universe_id", "level", "base_dimensions", "inputs", "observed_covariates", "covariate_units", "output",
                       "assessment_region", "query_budget", "query_cost", "answers", "task_text"})
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def _numbers(node: Any) -> list[float]:
    if isinstance(node, bool):
        return []
    if isinstance(node, (int, float)):
        return [float(node)]
    if isinstance(node, str):
        return [float(m) for m in _NUMBER.findall(node)]
    if isinstance(node, Mapping):
        return [x for k, v in node.items() for x in _numbers(k) + _numbers(v)]
    if isinstance(node, (list, tuple)):
        return [x for v in node for x in _numbers(v)]
    return []


def _informative(x: float) -> bool:
    """A hidden number specific enough that its appearance on a card is evidence of a leak, not a coincidence."""
    return math.isfinite(x) and not float(x).is_integer() and abs(x * 4 - round(x * 4)) > 1e-9


def _sig(x: float, digits: int = 6) -> float:
    return float(f"{x:.{digits}g}")


def audit_presented_cards(cards: Sequence[Mapping[str, Any]], key: Mapping[str, Any]) -> dict[str, Any]:
    """Post-reveal LITERAL leakage audit of exactly what each proposer was shown (Genesis §10.1, §12).

    ``LITERAL_LEAK_FOUND`` when a card carries a key outside CARD_KEYS, names its universe's kind outside the fixed
    ``answers`` list, or contains (anywhere, strings included) a hidden number of its own universe: a law or rival-law
    constant or exponent, the tolerance or the noise sigma (also when rounded to 6 significant digits), or an evaluation
    or in-box coordinate (exact). ``NO_LITERAL_LEAK_FOUND`` is NOT a proof of no leakage: structural tells (see
    :func:`region_tell`) are measured separately, never by this audit.
    """
    entries = {e["universe_id"]: e for e in key["universes"]}
    findings = []
    for card in cards:
        uid = card.get("universe_id")
        entry = entries.get(uid)
        if entry is None:
            findings.append({"universe_id": uid, "leak": "card for a universe the key does not contain"})
            continue
        extra = sorted(set(card) - CARD_KEYS)
        if extra:
            findings.append({"universe_id": uid, "leak": f"card keys outside the reviewed schema: {extra}"})
        visible = {k: v for k, v in card.items() if k not in ("answers", "universe_id")}
        if entry["kind"] in json.dumps(visible, sort_keys=True).lower():
            findings.append({"universe_id": uid, "leak": "the card names its universe kind"})
        rounded = [float(entry["tolerance"]), float(entry["noise_sigma"])] + _numbers(entry.get("law")) \
            + _numbers(entry.get("alternative_law"))
        exact = [x for p, _ in entry["evaluation"] for x in p.values()] + [x for p, _ in entry["inbox"] for x in p.values()]
        shown = _numbers(visible)
        shown_exact, shown_sig = set(shown), {_sig(x) for x in shown}
        hits = sorted({x for x in rounded if _informative(x) and (x in shown_exact or _sig(x) in shown_sig)}
                      | {x for x in exact if _informative(x) and x in shown_exact})
        if hits:
            findings.append({"universe_id": uid, "leak": f"hidden numbers appear on the card: {hits[:5]}"})
    return {"status": "LITERAL_LEAK_FOUND" if findings else "NO_LITERAL_LEAK_FOUND", "cards": len(cards), "findings": findings}
