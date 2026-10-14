"""Genesis-lite v0.1 evaluation contract: the endpoints and decision rules, as code (preregistered by digest).

Pilot finding P-1 (v0): judged cell by cell, a floor arm that always proposes a law won the discoverable cell (0.70 vs
0.27) while scoring -1 on every control. A per-cell rule rewards a proposer that trades control failures for discovery
credit. v0.1 therefore makes the JOINT campaign credit the primary endpoint and forbids trading:

* PRIMARY endpoint: per campaign (one hidden world of every kind = the unit), the sum over kinds of that world's credit
  (frozen DEFAULT_CREDIT), each world's credit averaged over seeds. An arm's score is the mean over campaigns.
* STRONGEST BASELINE: the non-adversarial arm (competence, floor or sanity role) with the highest primary score.
* LIFT (for a future Mind; nothing here is claimed for one): the paired per-campaign difference to the strongest
  baseline must have a cluster-bootstrap 95% lower bound > 0, AND for every control kind the paired mean difference must
  have a lower bound > -NONINFERIORITY_MARGIN, with Holm correction over the FIXED family PRIMARY_FAMILY.
* Every per-cell rate stays a descriptive secondary metric; no claim rests on a single cell.
"""

from __future__ import annotations

import random
import statistics
from typing import Any, Iterable, Mapping, Sequence

CONTROL_KINDS = ("confounded", "indistinguishable", "insufficient_evidence", "no_solution", "spurious_correlate")
NONINFERIORITY_MARGIN = 0.10
ALPHA = 0.05
BOOTSTRAP = 2000
#: the fixed Holm family: the pooled primary endpoint and one primary endpoint per presentation
PRIMARY_FAMILY = ("pooled", "anonymous", "renamed", "paraphrased", "trap")
NON_ADVERSARIAL_ROLES = ("competence", "floor", "sanity")


def _record(r: Any) -> Mapping[str, Any]:
    return r if isinstance(r, Mapping) else r.to_dict()


def world_credits(records: Iterable[Any]) -> dict[str, dict[tuple[str, str], dict[str, float]]]:
    """arm -> (presentation, campaign) -> kind -> credit averaged over that arm's VALID seeds on that campaign."""
    acc: dict[str, dict[tuple[str, str], dict[str, list[float]]]] = {}
    for raw in records:
        r = _record(raw)
        if r["status"] != "VALID":
            continue
        cell = acc.setdefault(r["arm"], {}).setdefault((r["presentation"], r["campaign_id"]), {})
        for u in r["universes"]:
            cell.setdefault(u["kind"], []).append(float(u["credit"]))
    return {arm: {c: {k: statistics.fmean(v) for k, v in kinds.items()} for c, kinds in camps.items()}
            for arm, camps in acc.items()}


def campaign_scores(credits: Mapping[tuple[str, str], Mapping[str, float]], presentation: str = "pooled") -> dict[tuple[str, str], float]:
    return {c: sum(kinds.values()) for c, kinds in credits.items() if presentation == "pooled" or c[0] == presentation}


def bootstrap_mean_ci(values: Sequence[float], resamples: int = BOOTSTRAP) -> tuple[float, float, float]:
    """(mean, 2.5% bound, fraction of resampled means <= 0): percentile bootstrap over the given units (campaigns)."""
    if not values:
        return float("nan"), float("nan"), 1.0
    rng = random.Random(0)
    n = len(values)
    means = sorted(statistics.fmean(rng.choice(values) for _ in range(n)) for _ in range(resamples))
    return statistics.fmean(values), means[int(0.025 * resamples)], sum(m <= 0 for m in means) / resamples


def strongest_baseline(credits: Mapping[str, Mapping[tuple[str, str], Mapping[str, float]]],
                       roles: Mapping[str, str]) -> tuple[str, dict[str, float]]:
    scores = {arm: statistics.fmean(campaign_scores(c).values()) for arm, c in credits.items()
              if roles.get(arm) in NON_ADVERSARIAL_ROLES and c}
    return max(sorted(scores), key=lambda a: scores[a]), scores


def lift_decision(credits: Mapping[str, Mapping[tuple[str, str], Mapping[str, float]]], candidate: str, baseline: str) -> dict[str, Any]:
    """The v0.1 lift rule, paired on the campaigns both arms ran (no pairing, no claim)."""
    mine, theirs = credits.get(candidate, {}), credits.get(baseline, {})
    shared = sorted(set(mine) & set(theirs))
    tests, raw_p = {}, {}
    for part in PRIMARY_FAMILY:
        diffs = [sum(mine[c].values()) - sum(theirs[c].values()) for c in shared if part == "pooled" or c[0] == part]
        mean, low, p = bootstrap_mean_ci(diffs)
        tests[part] = {"campaigns": len(diffs), "mean_difference": mean, "lower95": low}
        raw_p[part] = p
    order = sorted(PRIMARY_FAMILY, key=lambda k: raw_p[k])
    holm_ok = {}
    still = True
    for i, part in enumerate(order):                          # Holm step-down over the fixed family
        still = still and raw_p[part] <= ALPHA / (len(order) - i)
        holm_ok[part] = still
    noninf = {}
    for kind in CONTROL_KINDS:
        diffs = [mine[c].get(kind, 0.0) - theirs[c].get(kind, 0.0) for c in shared]
        mean, low, _ = bootstrap_mean_ci(diffs)
        noninf[kind] = {"mean_difference": mean, "lower95": low, "ok": low > -NONINFERIORITY_MARGIN}
    claim = bool(shared) and holm_ok["pooled"] and tests["pooled"]["lower95"] > 0 and all(v["ok"] for v in noninf.values())
    return {"candidate": candidate, "baseline": baseline, "shared_campaigns": len(shared), "primary": tests,
            "holm_significant": holm_ok, "control_noninferiority": noninf, "lift_claimed": claim}
