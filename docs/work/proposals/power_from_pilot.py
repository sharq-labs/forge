"""A3 power analysis from the EXC-4b development pilot records (read-only, development planning input).

Usage: python3 power_from_pilot.py <runs.jsonl>
Prints the campaign-id structure, per-arm unit totals, paired-difference spreads and required independent units
under several valid one-sided tests. No repository file is read or written.
"""
import collections
import json
import math
import statistics
import sys

R = 24.0          # range of a paired difference of two six-kind totals in [-6, 6]
ALPHA = 0.05


def load(path):
    rows = [json.loads(line) for line in open(path, encoding="utf-8")]
    return rows


def hoeffding_n(mean, k):
    a = ALPHA / k
    return math.inf if mean <= 0 else math.ceil(R * R * math.log(1 / a) / (2 * mean * mean))


def bernstein_n(mean, sd, k):
    """Smallest n with mean > sqrt(2 V ln(2/d)/n) + 7 R ln(2/d) / (3 (n-1)) (Maurer & Pontil 2009, one-sided form
    with ln(1/d) used conservatively as ln(2/d))."""
    if mean <= 0:
        return math.inf
    d = ALPHA / k
    L = math.log(2 / d)
    for n in range(2, 10_000_000):
        if mean > math.sqrt(2 * sd * sd * L / n) + 7 * R * L / (3 * (n - 1)):
            return n
    return math.inf


def normal_n(mean, sd, k, power=0.8):
    """Large-sample paired z/t approximation (NOT finite-sample valid; reference only)."""
    if mean <= 0:
        return math.inf
    from statistics import NormalDist
    z = NormalDist().inv_cdf
    return math.ceil(((z(1 - ALPHA / k) + z(power)) * sd / mean) ** 2)


def main(path):
    rows = load(path)
    ids = collections.Counter(r["campaign_id"].rsplit("-", 1)[0] for r in rows)
    print("campaigns", len(rows), "distinct campaign-id stems", len(ids))
    print("example ids", sorted({r["campaign_id"] for r in rows})[:6])
    print("presentations", collections.Counter(r["presentation"] for r in rows))
    print("seeds per arm sample", sorted({r["seed"] for r in rows if r["arm"] == "careful"})[:10])
    by = collections.defaultdict(dict)
    for r in rows:
        by[r["arm"]][r["campaign_id"]] = float(r["v3_total_credit"])
    arms = sorted(by)
    print("arms", len(arms))
    for a in arms:
        v = list(by[a].values())
        print(f"  {a:28s} n={len(v):4d} mean_total={statistics.fmean(v):+.3f} sd={statistics.pstdev(v):.3f}")
    for cand in ("mind_full", "grammar_enumeration"):
        print(f"\npaired differences, candidate {cand} (unit = campaign; 6 universes each)")
        for b in arms:
            if b == cand:
                continue
            common = sorted(set(by[cand]) & set(by[b]))
            d = [by[cand][u] - by[b][u] for u in common]
            m, s = statistics.fmean(d), statistics.stdev(d)
            print(f"  vs {b:26s} n={len(d)} mean={m:+.3f} sd={s:.3f}")
    print("\nrequired independent units for a hypothetical lift (sd taken as the median observed paired sd)")
    sds = []
    for b in arms:
        if b != "grammar_enumeration":
            common = sorted(set(by["grammar_enumeration"]) & set(by[b]))
            sds.append(statistics.stdev([by["grammar_enumeration"][u] - by[b][u] for u in common]))
    sd = statistics.median(sds)
    print(f"median paired sd = {sd:.3f}")
    print(f"{'lift/unit':>9} {'k':>3} {'hoeffding':>10} {'emp-bernstein':>14} {'normal(ref,80%)':>16}")
    for lift in (0.25, 0.5, 1.0, 2.0):
        for k in (1, 3, 20):
            print(f"{lift:9.2f} {k:3d} {hoeffding_n(lift, k):10} {bernstein_n(lift, sd, k):14} {normal_n(lift, sd, k):16}")


if __name__ == "__main__":
    main(sys.argv[1])
