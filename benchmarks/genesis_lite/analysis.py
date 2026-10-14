"""Genesis-lite v0.2 evaluation contract: the endpoints and decision rules, as code (preregistered by digest).

Pilot finding P-1 (v0): judged cell by cell, a floor arm that always proposes a law won the discoverable cell (0.70 vs
0.27) while scoring -1 on every control. v0.1 made the JOINT campaign credit the primary endpoint and forbade trading
controls for discovery. The G0/A1 final review (2026-10-14) found that v0.1's rule could still be weakened by its
inputs (D1-D7); v0.2 closes those channels. Every change makes a lift claim harder, never easier:

* UNIT: a world set = one campaign (one hidden world of every kind) under one (presentation, seed) master root. Every
  arm runs every world set exactly once and sees the same stimulus there (only its run-private pseudonym differs).
* GRID: the world sets are PREREGISTERED (FORMAL_GRID, digest-bound); a decision on any other grid, or with records
  outside it, is exploratory and claims nothing (D2).
* CREDIT: per universe, a value of the frozen DEFAULT_CREDIT table (anything else is refused) that the independent
  evaluator agreed with (otherwise no claim).
* PRIMARY endpoint: per world set, the sum over the six kinds. An arm's score is the mean over the grid.
* ROLES come from the frozen arm registry (``arms.ARMS``), never from the caller; a record of an unregistered arm other
  than the candidate is refused, and the candidate may not take a registered arm's name.
* COMPARISON SET: EVERY registered non-adversarial arm (competence, floor or sanity role) must have a VALID, isolated,
  content-paired record on every world set of the grid. A missing or invalid baseline blocks the claim; it never
  shrinks the comparison (D1, D5).
* STRONGEST BASELINE: the registered non-adversarial arm with the highest primary score on the grid.
* NO STRONG BASELINE, NO LIFT (D4, D6): in a discoverable world whose true law lies outside every run arm's searched
  family, and in every (kind, presentation) cell that the preregistered REPRESENTATION_LIMITED rule marks (the
  representation arm's full-credit rate has a bootstrap 95% lower bound >= 0.5), the candidate's credit is capped at its
  comparator's: it can lose there but never gain.
* LIFT (for a future Mind; nothing here is claimed for one) requires ALL of:
  - no coverage problem (above), and the code matching the committed preregistration;
  - the paired pooled primary difference to the strongest baseline has a cluster-bootstrap 95% lower bound > 0 and is
    significant after Holm correction over the FIXED family PRIMARY_FAMILY;
  - per presentation, the paired primary difference has a lower bound > -PRESENTATION_MARGIN;
  - per kind -- discovery included (D3) -- against the BEST registered non-adversarial arm on that kind, the paired
    difference has a lower bound > -NONINFERIORITY_MARGIN.
* Every per-cell rate stays a descriptive secondary metric; no claim rests on a single cell.
"""

from __future__ import annotations

import math
import random
import statistics
from typing import Any, Iterable, Mapping, Sequence

from engcore.blindfold.roles import DEFAULT_CREDIT

KINDS = ("confounded", "discoverable", "indistinguishable", "insufficient_evidence", "no_solution", "spurious_correlate")
CONTROL_KINDS = tuple(k for k in KINDS if k != "discoverable")
NONINFERIORITY_MARGIN = 0.10
PRESENTATION_MARGIN = NONINFERIORITY_MARGIN * len(KINDS)
ALPHA = 0.05
BOOTSTRAP = 2000
#: the fixed Holm family: the pooled primary endpoint and one primary endpoint per presentation
PRIMARY_FAMILY = ("pooled", "anonymous", "renamed", "paraphrased", "trap")
NON_ADVERSARIAL_ROLES = ("competence", "floor", "sanity")
REQUIRED_ISOLATION = "proposer_process"
#: the preregistered REPRESENTATION_LIMITED rule: this arm's full-credit rate per (kind, presentation) cell
REPRESENTATION_ARM = "monomial_enumeration"
REPRESENTATION_LIMIT = 0.5
FULL_CREDIT = 1.0
ALLOWED_CREDIT = {k: frozenset({0.0, *map(float, DEFAULT_CREDIT[k].values())}) for k in KINDS}

WorldSet = tuple[str, str, int]          # (presentation, campaign_id, seed)


class AnalysisRefused(ValueError):
    """The records cannot be analysed as preregistered (duplicates, unregistered arms, credit outside the frozen table,
    non-finite credit, a missing kind or family flag)."""


def _record(r: Any) -> Mapping[str, Any]:
    return r if isinstance(r, Mapping) else r.to_dict()


def formal_grid(campaign_ids: Sequence[str], presentations: Sequence[str], seeds: Sequence[int]) -> frozenset[WorldSet]:
    """A world-set grid (the preregistered one is FORMAL_GRID)."""
    return frozenset((p, c, int(s)) for p in presentations for c in campaign_ids for s in seeds)


FORMAL_CAMPAIGNS = tuple(f"gl-formal-{i}" for i in range(30))
FORMAL_SEEDS = tuple(range(20))
FORMAL_GRID = formal_grid(FORMAL_CAMPAIGNS, PRIMARY_FAMILY[1:], FORMAL_SEEDS)


def registered_roles() -> dict[str, str]:
    from .arms import ARMS  # noqa: PLC0415 - the frozen registry, never caller input

    return {name: entry[3] for name, entry in ARMS.items()}


def _ws(r: Mapping[str, Any]) -> WorldSet:
    return (r["presentation"], r["campaign_id"], int(r["seed"]))


def world_credits(records: Iterable[Any]) -> dict[str, dict[WorldSet, dict[str, float]]]:
    """arm -> world set -> kind -> credit, VALID runs only. Refuses a missing kind, a non-finite credit, a credit that is
    not a value of the frozen DEFAULT_CREDIT table, and a duplicate (arm, world set)."""
    out: dict[str, dict[WorldSet, dict[str, float]]] = {}
    for raw in records:
        r = _record(raw)
        if r["status"] != "VALID":
            continue
        kinds = {u["kind"]: float(u["credit"]) for u in r["universes"]}
        if set(kinds) != set(KINDS) or len(r["universes"]) != len(KINDS):
            raise AnalysisRefused(f"run {r['arm']}/{r['campaign_id']} does not carry every kind once: {sorted(kinds)}")
        if not all(math.isfinite(v) for v in kinds.values()):
            raise AnalysisRefused(f"run {r['arm']}/{r['campaign_id']} carries a non-finite credit")
        bad = sorted(k for k, v in kinds.items() if v not in ALLOWED_CREDIT[k])
        if bad:
            raise AnalysisRefused(f"run {r['arm']}/{r['campaign_id']} carries a credit outside the frozen DEFAULT_CREDIT "
                                  f"table for {bad}")
        ws = _ws(r)
        if ws in out.setdefault(r["arm"], {}):
            raise AnalysisRefused(f"arm {r['arm']} has two VALID records for world set {ws}: every arm runs it once")
        out[r["arm"]][ws] = kinds
    return out


def out_of_family(records: Iterable[Any]) -> dict[WorldSet, bool]:
    """world set -> is its discoverable world's true law outside the searched family? Refuses a VALID record without the
    flag and two records that disagree about one world set (they would not be the same world)."""
    out: dict[WorldSet, bool] = {}
    for raw in records:
        r = _record(raw)
        if r["status"] != "VALID":
            continue
        (u,) = [u for u in r["universes"] if u["kind"] == "discoverable"] or [None]
        if u is None or not isinstance(u.get("truth_in_searched_family"), bool):
            raise AnalysisRefused(f"run {r['arm']}/{r['campaign_id']} does not state truth_in_searched_family")
        flag, ws = not u["truth_in_searched_family"], _ws(r)
        if out.setdefault(ws, flag) != flag:
            raise AnalysisRefused(f"records disagree whether world set {ws}'s discoverable truth is in the searched family")
    return out


def bootstrap_mean_ci(values: Sequence[float], resamples: int | None = None) -> tuple[float, float, float]:
    """(mean, conservative 2.5% bound, achieved significance = fraction of resampled means <= 0), bootstrap over world
    sets. The bound is the floor order statistic (never the next one up)."""
    resamples = BOOTSTRAP if resamples is None else resamples
    if not values:
        return float("nan"), float("nan"), 1.0
    rng = random.Random(0)
    n = len(values)
    means = sorted(statistics.fmean(rng.choice(values) for _ in range(n)) for _ in range(resamples))
    return statistics.fmean(values), means[max(int(0.025 * resamples) - 1, 0)], sum(m <= 0 for m in means) / resamples


def primary_scores(credits: Mapping[str, Mapping[WorldSet, Mapping[str, float]]]) -> dict[str, float]:
    return {arm: statistics.fmean(sum(k.values()) for k in sets.values()) for arm, sets in credits.items() if sets}


def strongest_baseline(credits: Mapping[str, Mapping[WorldSet, Mapping[str, float]]],
                       roles: Mapping[str, str]) -> tuple[str | None, dict[str, float]]:
    scores = {arm: s for arm, s in primary_scores(credits).items() if roles.get(arm) in NON_ADVERSARIAL_ROLES}
    return (max(sorted(scores), key=lambda a: scores[a]) if scores else None), scores


def best_per_kind(credits: Mapping[str, Mapping[WorldSet, Mapping[str, float]]], roles: Mapping[str, str],
                  exclude: str = "") -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for kind in KINDS:
        cands = {arm: statistics.fmean(k[kind] for k in sets.values()) for arm, sets in credits.items()
                 if arm != exclude and sets and roles.get(arm) in NON_ADVERSARIAL_ROLES}
        out[kind] = max(sorted(cands), key=lambda a: cands[a]) if cands else None
    return out


def representation_limited(credits: Mapping[WorldSet, Mapping[str, float]]) -> set[tuple[str, str]]:
    """(kind, presentation) cells in which the representation arm alone earns full credit at a bootstrap 95% lower bound
    >= REPRESENTATION_LIMIT: they measure the representation, so no lift there is credited as reasoning."""
    cells = set()
    for kind in KINDS:
        for presentation in PRIMARY_FAMILY[1:]:
            hits = [1.0 if k[kind] >= FULL_CREDIT else 0.0 for w, k in credits.items() if w[0] == presentation]
            if hits and bootstrap_mean_ci(hits)[1] >= REPRESENTATION_LIMIT:
                cells.add((kind, presentation))
    return cells


def _capped(mine: Mapping[str, float], ref: Mapping[str, float], ws: WorldSet, limited: set[tuple[str, str]],
            off_family: Mapping[WorldSet, bool]) -> dict[str, float]:
    """The candidate's credits with every no-strong-baseline cell capped at the comparator's (lose, never gain)."""
    return {k: min(c, ref[k]) if ((k == "discoverable" and off_family.get(ws, True)) or (k, ws[0]) in limited) else c
            for k, c in mine.items()}


def coverage_problems(rows: Sequence[Mapping[str, Any]], arm: str, grid: frozenset[WorldSet],
                      comparator: str | None = None) -> list[str]:
    """Why ``arm``'s evidence does not cover the preregistered grid (and, with a comparator, the same universes)."""
    mine = [r for r in rows if r["arm"] == arm]
    problems = []
    if not mine:
        return [f"{arm}: no records at all; a registered arm never leaves the comparison silently"]
    invalid = [r for r in mine if r["status"] != "VALID"]
    if invalid:
        problems.append(f"{arm}: {len(invalid)} run(s) are not VALID; an invalid world set is never dropped silently")
    if any(r.get("isolation") != REQUIRED_ISOLATION for r in mine):
        problems.append(f"{arm}: run(s) were not proposer-process isolated")
    off = [r for r in mine if _ws(r) not in grid]
    if off:
        problems.append(f"{arm}: {len(off)} run(s) lie outside the preregistered grid")
    if any("universe_id" not in u for r in mine for u in r["universes"]):
        problems.append(f"{arm}: universe(s) without an id cannot be paired by content")
    if any(u.get("independent_agrees") is not True for r in mine if r["status"] == "VALID" for u in r["universes"]):
        problems.append(f"{arm}: credit(s) the independent evaluator did not agree with")
    covered = {_ws(r) for r in mine if r["status"] == "VALID"}
    if not grid or not grid <= covered:
        problems.append(f"{arm}: no VALID run on {len(grid - covered)} of the {len(grid)} preregistered world sets")
    if comparator is not None:
        u = {(r["arm"], _ws(r)): frozenset(x.get("universe_id") for x in r["universes"])
             for r in rows if r["status"] == "VALID" and r["arm"] in (arm, comparator)}
        mismatched = [ws for ws in grid if (arm, ws) in u and (comparator, ws) in u and u[(arm, ws)] != u[(comparator, ws)]]
        if mismatched:
            problems.append(f"{arm} vs {comparator}: {len(mismatched)} world set(s) pair different universes")
    return problems


def _code_problems() -> list[str]:
    from .pilot import prereg_matches_code  # noqa: PLC0415 - pilot imports this module

    ok, digest = prereg_matches_code()
    return [] if ok else [f"the code does not rebuild the committed preregistration ({digest[:12]}...)"]


def lift_decision(records: Iterable[Any], candidate: str, *, grid: Iterable[WorldSet] | None = None) -> dict[str, Any]:
    """The v0.2 lift rule. Claims nothing unless every condition in the module docstring holds."""
    rows = [_record(r) for r in records]
    grid = FORMAL_GRID if grid is None else frozenset(grid)
    roles = registered_roles()
    if candidate in roles:
        raise AnalysisRefused(f"candidate {candidate!r} takes a registered arm's name; it would leave the comparison")
    strangers = sorted({r["arm"] for r in rows} - set(roles) - {candidate})
    if strangers:
        raise AnalysisRefused(f"records of unregistered arms: {strangers}; roles come from the frozen registry only")
    required = sorted(a for a, role in roles.items() if role in NON_ADVERSARIAL_ROLES)
    problems = [] if grid == FORMAL_GRID else ["the grid is not the preregistered formal grid: exploratory, no claim"]
    problems += _code_problems()
    credits = world_credits(rows)
    off_family = out_of_family(rows)
    on_grid = {a: {w: k for w, k in sets.items() if w in grid} for a, sets in credits.items()}
    baseline, _scores = strongest_baseline({a: on_grid[a] for a in required if on_grid.get(a)}, roles)
    per_kind = best_per_kind({a: on_grid[a] for a in required if on_grid.get(a)}, roles)
    limited = representation_limited(on_grid.get(REPRESENTATION_ARM, {}))
    problems += coverage_problems(rows, candidate, grid)
    for arm in required:
        problems += coverage_problems(rows, arm, grid, comparator=candidate)
    mine = on_grid.get(candidate, {})
    theirs = on_grid.get(baseline, {}) if baseline else {}
    shared = sorted(set(mine) & set(theirs))
    tests, raw_p = {}, {}
    for part in PRIMARY_FAMILY:
        diffs = [sum(_capped(mine[w], theirs[w], w, limited, off_family).values()) - sum(theirs[w].values())
                 for w in shared if part == "pooled" or w[0] == part]
        mean, low, p = bootstrap_mean_ci(diffs)
        tests[part] = {"world_sets": len(diffs), "mean_difference": mean, "lower95": low}
        raw_p[part] = p
    order = sorted(PRIMARY_FAMILY, key=lambda k: raw_p[k])
    holm_ok, still = {}, True
    for i, part in enumerate(order):                          # Holm step-down over the fixed family
        still = still and raw_p[part] <= ALPHA / (len(order) - i)
        holm_ok[part] = still
    presentations_ok = {part: tests[part]["world_sets"] > 0 and tests[part]["lower95"] > -PRESENTATION_MARGIN
                        for part in PRIMARY_FAMILY if part != "pooled"}
    noninf = {}
    for kind in KINDS:
        ref = on_grid.get(per_kind[kind], {}) if per_kind[kind] else {}
        diffs = [_capped(mine[w], ref[w], w, limited, off_family)[kind] - ref[w][kind] for w in sorted(set(mine) & set(ref))]
        mean, low, _ = bootstrap_mean_ci(diffs)
        noninf[kind] = {"reference_arm": per_kind[kind], "mean_difference": mean, "lower95": low,
                        "ok": bool(diffs) and low > -NONINFERIORITY_MARGIN}
    claim = (not problems and baseline is not None and holm_ok["pooled"] and tests["pooled"]["lower95"] > 0
             and all(presentations_ok.values()) and all(v["ok"] for v in noninf.values()))
    return {"candidate": candidate, "strongest_baseline": baseline, "shared_world_sets": len(shared),
            "coverage_problems": problems, "representation_limited_cells": sorted(limited),
            "out_of_family_world_sets": sum(off_family.get(w, False) for w in shared),
            "primary": tests, "holm_significant": holm_ok, "presentation_noninferiority": presentations_ok,
            "kind_noninferiority": noninf, "control_noninferiority": {k: noninf[k] for k in CONTROL_KINDS},
            "lift_claimed": claim}
