"""Genesis-lite v0.4 decision contract (owner decisions D9, D10, D13, D14 of 2026-10-30; ACTIVE_PLAN "Blindfold Step 1
gap closure"). DEVELOPMENT code until the v0.4 preregistration freezes it by digest.

v0.2 (``analysis.py``, hash-pinned) has the rule structure but an invalid bootstrap tail as its p-value (audit O-1);
v0.3 (``analysis_v3.py``) has valid inference but none of the structure. v0.4 joins them, in a new file:

* UNIT: a world set = one campaign (one hidden world of every kind) under one (presentation, seed) master root; the
  primary endpoint is the six-kind credit sum (in [-6, 6]); a paired difference lies in [-12, 12].
* INFERENCE (D9): the empirical-Bernstein bound of Maurer & Pontil (2009, Theorem 4) on independent-unit paired
  differences. It is finite-sample valid for independent identically distributed bounded units (independent but
  non-identical presentations: conservative per the 2026-10-30 review, not formally proven here) and adapts to the
  observed variance; the
  bootstrap tail and the sign-flip test are not used (the sign-flip test is anti-conservative under a skewed null:
  docs/work/proposals/BLINDFOLD_V04_POWER_AND_INFERENCE_DRAFT.md). Units must be INDEPENDENT (fresh worlds per
  (campaign, presentation, seed) and a stateless proposer per universe); presentations need not be identically
  distributed.
* COMPARATORS: every registered non-adversarial arm must have a VALID record on every world set of the grid. The
  superiority claim needs, against the pre-declared family, a Holm-adjusted rejection (``multiplicity="holm_family"``,
  the owner's D9 choice), or, as an alternative put to the owner, an intersection-union test at alpha against EVERY
  non-adversarial arm (``"iut_all"``).
* CAP (D10, FDA-06): in every law-credited kind (discoverable, spurious_correlate, confounded) whose true law no
  baseline family represents, the candidate's credit is capped at the comparator's: it can lose there, never gain.
  Out-of-family law credit is reported apart, uncapped, as a secondary endpoint.
* REPRESENTATION_LIMITED (as v0.2, with an exact Clopper-Pearson bound instead of a bootstrap): a (kind, presentation)
  cell where the representation arm earns full credit at a 95% lower bound >= 0.5 measures the representation; the
  candidate is capped there too.
* NON-INFERIORITY: per kind against the best non-adversarial arm of that kind (margin 0.10), and per presentation
  (margin 0.60), each an empirical-Bernstein lower bound at alpha. Every component must hold.
* STRATA (D13, G15): descriptive means per arm by kind, by region tell and by representation; the region tell is a
  disclosed property of the generator, never corrected here.

Every function refuses incomplete or inconsistent input; none drops a row because of its outcome. v0.4 has no
screening: a world set without a VALID record of every compared arm blocks the claim (stricter than v0.2).
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .analysis import CONTROL_KINDS, KINDS, AnalysisRefused, WorldSet
from .evaluator import score_v3

SCHEMA = "forge.genesis_lite.decision_contract/4"
ALPHA = 0.05
LAW_KINDS = ("confounded", "discoverable", "spurious_correlate")
UNIT_RANGE = 24.0                 # a paired difference of two six-kind totals lies in [-12, 12]
KIND_RANGE = 4.0                  # a paired difference of two per-kind credits lies in [-2, 2]
NONINFERIORITY_MARGIN = 0.10
PRESENTATION_MARGIN = NONINFERIORITY_MARGIN * len(KINDS)
PRESENTATIONS = ("anonymous", "renamed", "paraphrased", "trap")
NON_ADVERSARIAL_ROLES = ("competence", "floor", "sanity")
#: D9: the pre-declared Holm family (highest non-Mind, non-floor six-kind totals in both EXC-4 development pilots)
PRIMARY_FAMILY = ("careful", "grammar_enumeration", "space_filling")
MULTIPLICITY = ("holm_family", "iut_all")
REPRESENTATION_ARM = "grammar_enumeration"
REPRESENTATION_LIMIT = 0.5
FULL_CREDIT = 1.0


def expected_credit(kind: str, outcome: str) -> float:
    """The v0.3 evaluator's credit for (kind, outcome): the frozen v0.2 table, except that a bracketing-only pair
    (``indistinguishable_unresolved``) keeps only a non-positive penalty (``score_v3.score_universe``)."""
    table = score_v3.v2.CREDIT.get(kind)
    if table is None:
        raise AnalysisRefused(f"unknown universe kind {kind!r}")
    if outcome == "indistinguishable_unresolved":
        return min(0.0, float(table.get("indistinguishable_hit", 0.0)))
    return float(table.get(outcome, 0.0))


def _ws(r: Mapping[str, Any]) -> WorldSet:
    return (r["presentation"], r["campaign_id"], int(r["seed"]))


def world_credits(records: Iterable[Mapping[str, Any]]) -> dict[str, dict[WorldSet, dict[str, float]]]:
    """arm -> world set -> kind -> credit, VALID runs only. Refuses a missing or repeated kind, a non-finite credit, a
    credit that is not the v0.3 evaluator's value for the recorded outcome, a credit the independent evaluator did not
    agree with, and two VALID records of one arm on one world set."""
    out: dict[str, dict[WorldSet, dict[str, float]]] = {}
    for r in records:
        if r["status"] != "VALID":
            continue
        us = list(r["universes"])
        kinds = {u["kind"]: float(u["credit"]) for u in us}
        if set(kinds) != set(KINDS) or len(us) != len(KINDS):
            raise AnalysisRefused(f"run {r['arm']}/{r['campaign_id']} does not carry every kind once")
        for u in us:
            if not math.isfinite(float(u["credit"])) or "outcome" not in u:
                raise AnalysisRefused(f"run {r['arm']}/{r['campaign_id']}: non-finite credit or missing outcome")
            if expected_credit(u["kind"], str(u["outcome"])) != float(u["credit"]):
                raise AnalysisRefused(f"run {r['arm']}/{r['campaign_id']}: {u['kind']} credit is not the evaluator's "
                                      f"value for outcome {u['outcome']!r}")
            if u.get("independent_agrees") is not True:
                raise AnalysisRefused(f"run {r['arm']}/{r['campaign_id']}: the independent evaluator did not agree")
        ws = _ws(r)
        if ws in out.setdefault(r["arm"], {}):
            raise AnalysisRefused(f"arm {r['arm']} has two VALID records for world set {ws}")
        out[r["arm"]][ws] = kinds
    return out


def _moments(values: Sequence[float], value_range: float) -> tuple[int, float, float]:
    xs = tuple(float(x) for x in values)
    if len(xs) < 2:
        raise AnalysisRefused("the empirical-Bernstein bound needs at least two independent units")
    if not all(math.isfinite(x) for x in xs):
        raise AnalysisRefused("non-finite paired difference")
    if not (math.isfinite(value_range) and value_range > 0):
        raise AnalysisRefused("the value range must be finite and positive")
    if max(xs) - min(xs) > value_range * (1 + 1e-12):
        raise AnalysisRefused("observed values exceed the declared range")
    n = len(xs)
    mean = math.fsum(xs) / n
    return n, mean, math.fsum((x - mean) ** 2 for x in xs) / (n - 1)


def _bound(n: int, mean: float, var: float, delta: float, value_range: float) -> float:
    log_term = math.log(2 / delta)
    return mean - math.sqrt(2 * var * log_term / n) - 7 * value_range * log_term / (3 * (n - 1))


def bernstein_lower_bound(values: Sequence[float], delta: float, value_range: float) -> float:
    """A one-sided (1 - delta) lower confidence bound on E[X] for independent X of known range ``value_range``:
    mean - sqrt(2 V ln(2/delta) / n) - 7 R ln(2/delta) / (3 (n - 1)), V the unbiased sample variance."""
    if not (isinstance(delta, (int, float)) and math.isfinite(delta) and 0 < delta < 1):
        raise AnalysisRefused("delta must lie strictly between zero and one")
    return _bound(*_moments(values, value_range), delta, value_range)


def bernstein_p_value(values: Sequence[float], value_range: float, *, margin: float = 0.0) -> float:
    """The smallest delta at which the lower bound clears ``-margin`` (H0: E[X] <= -margin), found by bisection on
    log(delta) and reported from the conservative side. 1.0 when it never clears."""
    if not (math.isfinite(margin) and margin >= 0):
        raise AnalysisRefused("the margin must be finite and non-negative")
    n, mean, var = _moments(values, value_range)

    def clears(delta: float) -> bool:
        return _bound(n, mean, var, delta, value_range) > -margin

    if not clears(1 - 1e-12):
        return 1.0
    lo, hi = math.log(1e-300), math.log(1 - 1e-12)          # clears(exp(hi)) holds; find the boundary
    if clears(math.exp(lo)):
        return math.exp(lo)
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if clears(math.exp(mid)) else (mid, hi)
    return min(1.0, math.exp(hi))


def clopper_pearson_lower(successes: int, n: int, alpha: float = ALPHA) -> float:
    """Exact one-sided (1 - alpha) lower bound on a binomial rate (0 for zero successes)."""
    if n <= 0 or not 0 <= successes <= n:
        raise AnalysisRefused("a binomial bound needs 0 <= successes <= n and n > 0")
    if successes == 0:
        return 0.0

    def upper_tail(p: float) -> float:                     # P(X >= successes | p)
        logs = [math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
                + (k * math.log(p) if k else 0.0) + ((n - k) * math.log1p(-p) if n - k else 0.0)
                for k in range(successes, n + 1)]
        top = max(logs)
        return math.exp(top) * sum(math.exp(x - top) for x in logs)

    lo, hi = 0.0, 1.0
    for _ in range(100):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if upper_tail(mid) < alpha else (lo, mid)
    return lo


def _flags(records: Iterable[Mapping[str, Any]], represented: Mapping[str, bool]) -> dict[tuple[WorldSet, str], bool]:
    """(world set, kind) -> is the law-credited truth outside every baseline family? Every law-kind universe must have
    a representation verdict (from the sealed-root reveal); records that disagree on a world set's universes refuse."""
    out: dict[tuple[WorldSet, str], bool] = {}
    uids: dict[tuple[WorldSet, str], str] = {}
    for r in records:
        if r["status"] != "VALID":
            continue
        ws = _ws(r)
        for u in r["universes"]:
            if u["kind"] not in LAW_KINDS:
                continue
            uid = str(u.get("universe_id", ""))
            if uids.setdefault((ws, u["kind"]), uid) != uid:
                raise AnalysisRefused(f"world set {ws} pairs different {u['kind']} universes across arms")
            if not isinstance(represented.get(uid), bool):
                raise AnalysisRefused(f"no representation verdict for {u['kind']} universe {uid!r}")
            out[(ws, u["kind"])] = not represented[uid]
    return out


def representation_limited(credits: Mapping[WorldSet, Mapping[str, float]]) -> set[tuple[str, str]]:
    cells = set()
    for kind in KINDS:
        for presentation in PRESENTATIONS:
            hits = [k[kind] >= FULL_CREDIT for w, k in credits.items() if w[0] == presentation]
            if hits and clopper_pearson_lower(sum(hits), len(hits)) >= REPRESENTATION_LIMIT:
                cells.add((kind, presentation))
    return cells


def capped(mine: Mapping[str, float], ref: Mapping[str, float], ws: WorldSet,
           off_family: Mapping[tuple[WorldSet, str], bool], limited: set[tuple[str, str]]) -> dict[str, float]:
    """The candidate's credits with every no-strong-baseline cell capped at the comparator's (lose, never gain)."""
    return {k: min(c, ref[k]) if (off_family.get((ws, k), False) or (k, ws[0]) in limited) else c
            for k, c in mine.items()}


def _test(diffs: Sequence[float], value_range: float, *, margin: float = 0.0, alpha: float = ALPHA) -> dict[str, Any]:
    return {"units": len(diffs), "mean_difference": statistics.fmean(diffs),
            "lower_bound": bernstein_lower_bound(diffs, alpha, value_range),
            "p_value": bernstein_p_value(diffs, value_range, margin=margin), "margin": margin, "alpha": alpha}


def decision(records: Iterable[Mapping[str, Any]], candidate: str, roles: Mapping[str, str],
             represented: Mapping[str, bool], grid: Iterable[WorldSet], *,
             multiplicity: str = "holm_family") -> dict[str, Any]:
    """The v0.4 superiority decision for ``candidate`` on the preregistered ``grid``. Claims nothing unless every
    component holds and the coverage list is empty."""
    if multiplicity not in MULTIPLICITY:
        raise AnalysisRefused(f"multiplicity must be one of {MULTIPLICITY}")
    rows = [dict(r) for r in records]
    grid = frozenset(grid)
    presentations = {w[0] for w in grid}
    if presentations != set(PRESENTATIONS):
        raise AnalysisRefused(f"the grid must cover exactly the presentations {PRESENTATIONS}: {sorted(presentations)}")
    if candidate in roles:
        raise AnalysisRefused(f"candidate {candidate!r} takes a registered arm's name")
    strangers = sorted({r["arm"] for r in rows} - set(roles) - {candidate})
    if strangers:
        raise AnalysisRefused(f"records of unregistered arms: {strangers}")
    required = sorted(a for a, role in roles.items() if role in NON_ADVERSARIAL_ROLES)
    missing_family = sorted(set(PRIMARY_FAMILY) - set(required))
    if missing_family:
        raise AnalysisRefused(f"the pre-declared family names unregistered or adversarial arms: {missing_family}")
    credits = world_credits(rows)
    problems = []
    for arm in [candidate, *required]:
        have = set(credits.get(arm, {}))
        if not grid or not grid <= have:
            problems.append(f"{arm}: no VALID record on {len(grid - have)} of {len(grid)} grid world sets")
        if have - grid:
            problems.append(f"{arm}: {len(have - grid)} VALID record(s) outside the grid")
    off_family = _flags(rows, represented)
    on = {a: {w: k for w, k in credits.get(a, {}).items() if w in grid} for a in [candidate, *required]}
    limited = representation_limited(on.get(REPRESENTATION_ARM, {}))
    shared = sorted(grid)
    result: dict[str, Any] = {"schema": SCHEMA, "candidate": candidate, "multiplicity": multiplicity,
                              "coverage_problems": problems, "representation_limited_cells": sorted(limited),
                              "lift_claimed": False}
    if problems:
        return result

    def primary(arm: str, subset: Sequence[WorldSet]) -> list[float]:
        return [sum(capped(on[candidate][w], on[arm][w], w, off_family, limited).values()) - sum(on[arm][w].values())
                for w in subset]

    comparators = list(PRIMARY_FAMILY) if multiplicity == "holm_family" else required
    tests = {arm: _test(primary(arm, shared), UNIT_RANGE) for arm in comparators}
    if multiplicity == "holm_family":
        order = sorted(tests, key=lambda a: tests[a]["p_value"])
        still = True
        for i, arm in enumerate(order):
            still = still and tests[arm]["p_value"] <= ALPHA / (len(order) - i)
            tests[arm]["reject"] = still
    else:
        for arm in tests:
            tests[arm]["reject"] = tests[arm]["p_value"] <= ALPHA
    strongest = max(required, key=lambda a: (statistics.fmean(sum(on[a][w].values()) for w in shared), a))
    # Non-inferiority is an intersection-union test against EVERY non-adversarial arm (review finding 2): a single
    # data-chosen reference arm would let a candidate correlated with it pass while losing to an equally strong arm.
    presentation_ok = {}
    for p in PRESENTATIONS:
        subset = [w for w in shared if w[0] == p]
        per_arm = {a: _test(primary(a, subset), UNIT_RANGE, margin=PRESENTATION_MARGIN) for a in required}
        worst = min(per_arm, key=lambda a: (per_arm[a]["lower_bound"], a))
        presentation_ok[p] = {**per_arm[worst], "worst_arm": worst,
                              "ok": all(t["lower_bound"] > -PRESENTATION_MARGIN for t in per_arm.values())}
    kind_ok = {}
    for kind in KINDS:
        per_arm = {}
        for a in required:
            diffs = [capped(on[candidate][w], on[a][w], w, off_family, limited)[kind] - on[a][w][kind] for w in shared]
            per_arm[a] = _test(diffs, KIND_RANGE, margin=NONINFERIORITY_MARGIN)
        worst = min(per_arm, key=lambda a: (per_arm[a]["lower_bound"], a))
        kind_ok[kind] = {**per_arm[worst], "worst_arm": worst,
                         "ok": all(t["lower_bound"] > -NONINFERIORITY_MARGIN for t in per_arm.values())}
    result.update({
        "world_sets": len(shared), "strongest_baseline": strongest, "superiority": tests,
        "presentation_noninferiority": presentation_ok, "kind_noninferiority": kind_ok,
        "control_noninferiority": {k: kind_ok[k] for k in CONTROL_KINDS},
        "out_of_family_world_cells": sum(off_family.get((w, k), False) for w in shared for k in LAW_KINDS),
        "lift_claimed": (all(t["reject"] for t in tests.values()) and all(v["ok"] for v in presentation_ok.values())
                         and all(v["ok"] for v in kind_ok.values())),
    })
    return result


def strata(records: Iterable[Mapping[str, Any]], represented: Mapping[str, bool]) -> dict[str, Any]:
    """Descriptive per-arm mean credit by kind, by region tell and, for law kinds, by representation (D13, G15).
    Uncapped; out-of-family law credit is the secondary endpoint of D10."""
    acc: dict[str, dict[str, list[float]]] = {}
    for r in records:
        if r["status"] != "VALID":
            continue
        cells = acc.setdefault(r["arm"], {})
        for u in r["universes"]:
            credit = float(u["credit"])
            cells.setdefault(f"kind:{u['kind']}", []).append(credit)
            cells.setdefault(f"region:{u.get('region_tell', 'UNRECORDED')}|kind:{u['kind']}", []).append(credit)
            if u["kind"] in LAW_KINDS:
                rep = represented.get(str(u.get("universe_id", "")))
                label = "UNKNOWN" if not isinstance(rep, bool) else ("represented" if rep else "out_of_family")
                cells.setdefault(f"representation:{label}|kind:{u['kind']}", []).append(credit)
    return {"schema": SCHEMA, "descriptive_only": True,
            "arms": {a: {c: {"n": len(v), "mean": statistics.fmean(v)} for c, v in sorted(cells.items())}
                     for a, cells in sorted(acc.items())}}


__all__ = ["ALPHA", "LAW_KINDS", "MULTIPLICITY", "PRIMARY_FAMILY", "SCHEMA", "bernstein_lower_bound",
           "bernstein_p_value", "capped", "clopper_pearson_lower", "decision", "representation_limited", "strata"]
