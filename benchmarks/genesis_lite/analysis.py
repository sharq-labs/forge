"""Genesis-lite v0.1 evaluation contract: the endpoints and decision rules, as code (preregistered by digest).

Pilot finding P-1 (v0): judged cell by cell, a floor arm that always proposes a law won the discoverable cell (0.70 vs
0.27) while scoring -1 on every control. A per-cell rule rewards a proposer that trades control failures for discovery
credit. v0.1 therefore makes the JOINT campaign credit the primary endpoint and forbids trading:

* UNIT: a world set = one campaign (one hidden world of every kind) under one (presentation, seed) master root. Every
  arm runs every world set exactly once; roots are never reused across seeds or presentations, so no proposer --
  stateful or not -- sees a world twice. Duplicate records for one (arm, world set) are refused.
* PRIMARY endpoint: per world set, the sum over the six kinds of the frozen DEFAULT_CREDIT. An arm's score is the mean
  over world sets.
* ROLES come from the frozen arm registry (``arms.ARMS``), never from the caller; a record of an unregistered arm other
  than the candidate is refused.
* STRONGEST BASELINE: the non-adversarial arm (competence, floor or sanity role) with the highest primary score.
* LIFT (for a future Mind; nothing here is claimed for one) requires ALL of:
  - COMPLETENESS against the PREREGISTERED world-set grid, for EVERY compared arm (the candidate, the strongest
    baseline and each per-kind reference): a VALID, proposer-process-isolated run on every world set of the grid, and
    the same escrow universes as its comparator on every shared world set (pairing is by content, not by label);
  - the paired pooled primary difference to the strongest baseline has a cluster-bootstrap 95% lower bound > 0 and is
    significant after Holm correction over the FIXED family PRIMARY_FAMILY;
  - per presentation, the paired primary difference has a lower bound > -PRESENTATION_MARGIN;
  - per control kind, against the BEST non-adversarial arm on that kind, the paired difference has a lower bound
    > -NONINFERIORITY_MARGIN.
* Every per-cell rate stays a descriptive secondary metric; no claim rests on a single cell.
"""

from __future__ import annotations

import math
import random
import statistics
from typing import Any, Iterable, Mapping, Sequence

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

WorldSet = tuple[str, str, int]          # (presentation, campaign_id, seed)


class AnalysisRefused(ValueError):
    """The records cannot be analysed as preregistered (duplicates, unregistered arms, non-finite credit, missing kind)."""


def _record(r: Any) -> Mapping[str, Any]:
    return r if isinstance(r, Mapping) else r.to_dict()


def formal_grid(campaign_ids: Sequence[str], presentations: Sequence[str], seeds: Sequence[int]) -> frozenset[WorldSet]:
    """The preregistered world-set grid every compared arm must cover."""
    return frozenset((p, c, int(s)) for p in presentations for c in campaign_ids for s in seeds)


def registered_roles() -> dict[str, str]:
    from .arms import ARMS  # noqa: PLC0415 - the frozen registry, never caller input

    return {name: entry[3] for name, entry in ARMS.items()}


def world_credits(records: Iterable[Any]) -> dict[str, dict[WorldSet, dict[str, float]]]:
    """arm -> world set -> kind -> credit, VALID runs only. Refuses a missing kind, a non-finite credit and a duplicate
    (arm, world set)."""
    out: dict[str, dict[WorldSet, dict[str, float]]] = {}
    for raw in records:
        r = _record(raw)
        if r["status"] != "VALID":
            continue
        kinds = {u["kind"]: float(u["credit"]) for u in r["universes"]}
        if set(kinds) != set(KINDS):
            raise AnalysisRefused(f"run {r['arm']}/{r['campaign_id']} does not carry every kind: {sorted(kinds)}")
        if not all(math.isfinite(v) for v in kinds.values()):
            raise AnalysisRefused(f"run {r['arm']}/{r['campaign_id']} carries a non-finite credit")
        ws = (r["presentation"], r["campaign_id"], int(r["seed"]))
        if ws in out.setdefault(r["arm"], {}):
            raise AnalysisRefused(f"arm {r['arm']} has two VALID records for world set {ws}: every arm runs it once")
        out[r["arm"]][ws] = kinds
    return out


def bootstrap_mean_ci(values: Sequence[float], resamples: int = BOOTSTRAP) -> tuple[float, float, float]:
    """(mean, 2.5% bound, achieved significance = fraction of resampled means <= 0), bootstrap over world sets."""
    if not values:
        return float("nan"), float("nan"), 1.0
    rng = random.Random(0)
    n = len(values)
    means = sorted(statistics.fmean(rng.choice(values) for _ in range(n)) for _ in range(resamples))
    return statistics.fmean(values), means[int(0.025 * resamples)], sum(m <= 0 for m in means) / resamples


def primary_scores(credits: Mapping[str, Mapping[WorldSet, Mapping[str, float]]]) -> dict[str, float]:
    return {arm: statistics.fmean(sum(k.values()) for k in sets.values()) for arm, sets in credits.items() if sets}


def strongest_baseline(credits: Mapping[str, Mapping[WorldSet, Mapping[str, float]]],
                       roles: Mapping[str, str]) -> tuple[str, dict[str, float]]:
    scores = {arm: s for arm, s in primary_scores(credits).items() if roles.get(arm) in NON_ADVERSARIAL_ROLES}
    return max(sorted(scores), key=lambda a: scores[a]), scores


def best_per_kind(credits: Mapping[str, Mapping[WorldSet, Mapping[str, float]]], roles: Mapping[str, str],
                  exclude: str = "") -> dict[str, str]:
    out = {}
    for kind in KINDS:
        cands = {arm: statistics.fmean(k[kind] for k in sets.values()) for arm, sets in credits.items()
                 if arm != exclude and sets and roles.get(arm) in NON_ADVERSARIAL_ROLES}
        out[kind] = max(sorted(cands), key=lambda a: cands[a])
    return out


def _universes(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, WorldSet], frozenset[str]]:
    return {(r["arm"], (r["presentation"], r["campaign_id"], int(r["seed"]))): frozenset(u["universe_id"] for u in r["universes"])
            for r in rows if r["status"] == "VALID" and all("universe_id" in u for u in r["universes"])}


def coverage_problems(rows: Sequence[Mapping[str, Any]], arm: str, grid: frozenset[WorldSet],
                      comparator: str | None = None) -> list[str]:
    """Why ``arm``'s evidence does not cover the preregistered grid (and, with a comparator, the same universes)."""
    mine = [r for r in rows if r["arm"] == arm]
    problems = []
    invalid = [r for r in mine if r["status"] != "VALID"]
    if invalid:
        problems.append(f"{arm}: {len(invalid)} run(s) are not VALID; an invalid world set is never dropped silently")
    if any(r.get("isolation") != REQUIRED_ISOLATION for r in mine):
        problems.append(f"{arm}: run(s) were not proposer-process isolated")
    covered = {(r["presentation"], r["campaign_id"], int(r["seed"])) for r in mine if r["status"] == "VALID"}
    if not grid or not grid <= covered:
        problems.append(f"{arm}: no VALID run on {len(grid - covered)} of the {len(grid)} preregistered world sets")
    if comparator is not None:
        u = _universes(rows)
        mismatched = [ws for ws in grid if (arm, ws) in u and (comparator, ws) in u and u[(arm, ws)] != u[(comparator, ws)]]
        if mismatched:
            problems.append(f"{arm} vs {comparator}: {len(mismatched)} world set(s) pair different universes")
    return problems


def lift_decision(records: Iterable[Any], candidate: str, *, grid: frozenset[WorldSet]) -> dict[str, Any]:
    """The v0.1 lift rule. Claims nothing unless every condition in the module docstring holds."""
    rows = [_record(r) for r in records]
    roles = registered_roles()
    strangers = sorted({r["arm"] for r in rows} - set(roles) - {candidate})
    if strangers:
        raise AnalysisRefused(f"records of unregistered arms: {strangers}; roles come from the frozen registry only")
    roles = {**roles, candidate: "candidate"}
    credits = world_credits(rows)
    baseline, _scores = strongest_baseline({a: c for a, c in credits.items() if a != candidate}, roles)
    per_kind = best_per_kind(credits, roles, exclude=candidate)
    problems = coverage_problems(rows, candidate, grid, comparator=baseline)
    for arm in sorted({baseline, *per_kind.values()}):
        problems += coverage_problems(rows, arm, grid)
    mine, theirs = credits.get(candidate, {}), credits.get(baseline, {})
    shared = sorted(set(mine) & set(theirs) & grid)
    tests, raw_p = {}, {}
    for part in PRIMARY_FAMILY:
        diffs = [sum(mine[w].values()) - sum(theirs[w].values()) for w in shared if part == "pooled" or w[0] == part]
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
    for kind in CONTROL_KINDS:
        ref = credits.get(per_kind[kind], {})
        diffs = [mine[w][kind] - ref[w][kind] for w in sorted(set(mine) & set(ref) & grid)]
        mean, low, _ = bootstrap_mean_ci(diffs)
        noninf[kind] = {"reference_arm": per_kind[kind], "mean_difference": mean, "lower95": low,
                        "ok": bool(diffs) and low > -NONINFERIORITY_MARGIN}
    claim = (not problems and holm_ok["pooled"] and tests["pooled"]["lower95"] > 0 and all(presentations_ok.values())
             and all(v["ok"] for v in noninf.values()))
    return {"candidate": candidate, "strongest_baseline": baseline, "shared_world_sets": len(shared),
            "coverage_problems": problems, "primary": tests, "holm_significant": holm_ok,
            "presentation_noninferiority": presentations_ok, "control_noninferiority": noninf, "lift_claimed": claim}
