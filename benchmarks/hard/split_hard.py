"""Deterministic 70/30 development / hold-out split of the hard case set.

Why this file exists
--------------------
The generator behind `cases_hard/` has been corrected four times in response to
what scoring it revealed. Every correction was justified on its merits, and
every one of them makes the same question sharper: is the benchmark measuring
the tool, or has the benchmark been fitted to it? A number produced from cases
the generator was tuned against cannot answer that. A number produced from
cases nobody looked at can.

So the 2000 cases are partitioned once, by a rule that is fixed in this file,
and 30 % of them are sealed. `score_hard.py` refuses to score the sealed
partition without an explicit flag, and records the date when it is opened.

The rule
--------
1. **Stratum** — a case belongs to the stratum named by `ground_truth.defect`.
   There are 144 of them. Stratifying on the defect tag is what preserves the
   composition: a hold-out that happened to draw all the `runaway` cases and
   none of the `band_out` cases would not be measuring the same benchmark.

2. **Order within a stratum** — cases are sorted by

       sha256(f"{SPLIT_SEED}:{case_id}").hexdigest()

   with the case id as tiebreak. This is a total order that depends on nothing
   but the seed and an id that was written to disk before this file existed.
   It is not a random draw: there is no generator state to advance and no
   sample to re-take. Running this script again gives the same answer, and
   getting a different answer requires changing `SPLIT_SEED`, which is a
   tracked constant published in the README.

3. **How many per stratum** — the hold-out takes exactly
   `round(HOLDOUT_FRACTION * total)` cases overall, allocated across strata by
   the largest-remainder (Hamilton) method: each stratum first gets
   `floor(0.30 * n_s)`, and the seats left over go one each to the strata with
   the largest fractional remainder, ties broken by stratum name. Every stratum
   therefore lands within one case of its exact 30 % share, and the shares sum
   to the target exactly. Five strata hold a single case; those are the only
   places the per-stratum proportion can be 0 % or 100 %, and the verification
   below reports them rather than hiding them.

4. **Which ones** — the hold-out is the first `k_s` cases in the stratum's hash
   order. The development set is the rest.

The seed
--------
`SPLIT_SEED` is the ISO date of the round that produced this split, as an
integer, which is the same convention `generate_hard.py` uses. It was fixed
before the split was computed and no other value was tried against a score.
`verify` below reports how the composition holds up under nine neighbouring
seeds, which is evidence that the rule — not the seed — is what preserves the
composition. Those are composition figures only; no seed sweep of *scores* was
run, because scoring alternative splits is the search this file exists to
prevent.

What the seal does and does not do
----------------------------------
It stops the hold-out **cases** from being scored, inspected case-by-case, or
diffed between runs. That is the mechanism by which a benchmark gets fitted to
a tool: you look at which cases were missed, and you change something.

It does not make the hold-out aggregate cryptographically unknowable. The
full-set figure is already published — it is the record of four rounds — so
hold-out ≈ (full − dev) is arithmetic anyone can do. Claiming otherwise would
be the same kind of unearned number this benchmark's README already warns
about. The seal is procedural, and the procedure is the part that matters.

Run
---
    python benchmarks/hard/split_hard.py --cases benchmarks/hard/cases_hard
    python benchmarks/hard/split_hard.py --cases benchmarks/hard/cases_hard --verify
"""

import argparse
import collections
import hashlib
import json
import math
import pathlib
import sys

# The ISO date of the evidence round, as an integer. See "The seed" above.
SPLIT_SEED = 20260906

# 30 % sealed, 70 % developed against.
HOLDOUT_FRACTION = 0.30

# Bumped if the rule in the module docstring ever changes. A split file
# carrying a different rule id was produced by different arithmetic and is not
# comparable to this one, even at the same seed.
RULE_ID = "stratified-hash-hamilton/1"

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_SPLIT_PATH = HERE / "split_hard.json"


def case_set_digest(files):
    """A digest of the case set as bytes on disk.

    Named by filename and content, so a case set that gained, lost or edited a
    single case digests differently. `score_hard.py` writes this into its
    summary: a run against different cases is then visibly a different run
    rather than a silently different number.
    """
    lines = [f"{p.name} {hashlib.sha256(p.read_bytes()).hexdigest()}" for p in files]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def id_list_digest(ids):
    return hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()


def _order_key(seed, case_id):
    return hashlib.sha256(f"{seed}:{case_id}".encode("utf-8")).hexdigest()


def allocate(sizes, target):
    """Largest-remainder allocation of `target` seats across strata `sizes`.

    `sizes` maps stratum name to case count. Returns stratum name -> seats.
    Ties on the fractional remainder are broken by stratum name so the result
    does not depend on dict ordering.
    """
    total = sum(sizes.values())
    exact = {s: HOLDOUT_FRACTION * n for s, n in sizes.items()}
    seats = {s: math.floor(q) for s, q in exact.items()}
    remaining = target - sum(seats.values())
    order = sorted(sizes, key=lambda s: (-(exact[s] - seats[s]), s))
    for s in order[:remaining]:
        seats[s] += 1
    assert sum(seats.values()) == target, (sum(seats.values()), target, total)
    return seats


def build_split(cases, seed=SPLIT_SEED):
    """cases: list of (id, defect, label, expected_verdict). -> (dev, holdout)."""
    strata = collections.defaultdict(list)
    for cid, defect, _label, _verdict in cases:
        strata[defect].append(cid)

    sizes = {s: len(ids) for s, ids in strata.items()}
    target = round(HOLDOUT_FRACTION * len(cases))
    seats = allocate(sizes, target)

    holdout, dev = [], []
    for stratum in sorted(strata):
        ordered = sorted(strata[stratum], key=lambda c: (_order_key(seed, c), c))
        k = seats[stratum]
        holdout.extend(ordered[:k])
        dev.extend(ordered[k:])
    return sorted(dev), sorted(holdout)


def read_cases(case_dir):
    files = sorted(pathlib.Path(case_dir).glob("*.json"))
    rows = []
    for f in files:
        c = json.loads(f.read_text(encoding="utf-8"))
        g = c["ground_truth"]
        rows.append((c["id"], g["defect"], g["label"], g["expected_verdict"]))
    return files, rows


def composition(cases, ids):
    """Proportion of each defect tag, label and verdict within `ids`."""
    sel = [c for c in cases if c[0] in ids]
    n = len(sel)
    return {
        "n": n,
        "by_defect": dict(collections.Counter(c[1] for c in sel)),
        "by_label": dict(collections.Counter(c[2] for c in sel)),
        "by_expected_verdict": dict(collections.Counter(c[3] for c in sel)),
    }


def verify(cases, dev, holdout):
    """Evidence that the hold-out carries the same composition as the dev set.

    The check is on **proportions**, not counts: the two partitions are
    different sizes, so equal counts would be the wrong test. For every defect
    tag the hold-out's share of the hold-out is compared with the dev set's
    share of the dev set, and the largest gap is reported. Because allocation
    is per-stratum and largest-remainder, that gap is bounded by one case's
    worth of a stratum and the small strata are where it lands.
    """
    n_dev, n_hold = len(dev), len(holdout)
    cd, ch = composition(cases, set(dev)), composition(cases, set(holdout))

    rows = []
    for tag in sorted(set(cd["by_defect"]) | set(ch["by_defect"])):
        total = sum(1 for c in cases if c[1] == tag)
        d, h = cd["by_defect"].get(tag, 0), ch["by_defect"].get(tag, 0)
        rows.append({
            "defect": tag, "total": total, "dev": d, "holdout": h,
            "dev_share": d / n_dev, "holdout_share": h / n_hold,
            "abs_share_gap": abs(d / n_dev - h / n_hold),
            "holdout_fraction_of_tag": h / total,
        })
    worst = sorted(rows, key=lambda r: -r["abs_share_gap"])

    def dist_gap(key):
        a, b = cd[key], ch[key]
        keys = set(a) | set(b)
        return {k: {"dev_share": a.get(k, 0) / n_dev,
                    "holdout_share": b.get(k, 0) / n_hold,
                    "abs_share_gap": abs(a.get(k, 0) / n_dev - b.get(k, 0) / n_hold)}
                for k in sorted(keys)}

    # Strata too small to split at all. Reported, not hidden: a stratum of one
    # case is 100 % on one side of the split and 0 % on the other, and no
    # stratified rule can do otherwise.
    singletons = [r["defect"] for r in rows if r["total"] == 1]

    # The rule, not the seed. If neighbouring seeds give the same worst-case
    # gap, the composition is preserved by the stratification rather than by a
    # seed that happened to land well.
    seed_sweep = []
    for s in range(SPLIT_SEED - 4, SPLIT_SEED + 5):
        d2, h2 = build_split(cases, seed=s)
        c2d, c2h = composition(cases, set(d2)), composition(cases, set(h2))
        gap = max(abs(c2d["by_defect"].get(t, 0) / len(d2)
                      - c2h["by_defect"].get(t, 0) / len(h2))
                  for t in set(c2d["by_defect"]) | set(c2h["by_defect"]))
        seed_sweep.append({"seed": s, "max_abs_share_gap": gap,
                           "is_published_seed": s == SPLIT_SEED})

    return {
        "n_dev": n_dev, "n_holdout": n_hold,
        "holdout_fraction_actual": n_hold / (n_dev + n_hold),
        "distinct_defect_tags": {"total": len(rows),
                                 "present_in_dev": len(cd["by_defect"]),
                                 "present_in_holdout": len(ch["by_defect"])},
        "max_abs_share_gap_over_defect_tags": worst[0]["abs_share_gap"],
        "worst_five_defect_tags": worst[:5],
        "singleton_strata": singletons,
        "by_label": dist_gap("by_label"),
        "by_expected_verdict": dist_gap("by_expected_verdict"),
        "seed_sweep_composition_only": seed_sweep,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cases", default=str(HERE / "cases_hard"))
    ap.add_argument("--out", default=str(DEFAULT_SPLIT_PATH))
    ap.add_argument("--verify", action="store_true",
                    help="print the composition-preservation evidence and exit "
                         "without writing")
    a = ap.parse_args(argv)

    files, cases = read_cases(a.cases)
    if not cases:
        print(f"no cases under {a.cases}", file=sys.stderr)
        return 2
    dev, holdout = build_split(cases)
    report = verify(cases, dev, holdout)

    if a.verify:
        print(json.dumps(report, indent=2))
        return 0

    doc = {
        "rule_id": RULE_ID,
        "seed": SPLIT_SEED,
        "holdout_fraction": HOLDOUT_FRACTION,
        "rule": ("stratify on ground_truth.defect; order each stratum by "
                 "sha256(f'{seed}:{case_id}') with case_id as tiebreak; "
                 "allocate round(0.30*total) hold-out seats across strata by "
                 "largest remainder, ties broken by stratum name; the hold-out "
                 "is the first k_s of each stratum's order"),
        "cases_dir": pathlib.Path(a.cases).name,
        "case_set_digest": case_set_digest(files),
        "n_total": len(cases), "n_dev": len(dev), "n_holdout": len(holdout),
        "dev_digest": id_list_digest(dev),
        "holdout_digest": id_list_digest(holdout),
        "verification": report,
        "dev": dev,
        # The ids are listed so a third party can recompute the split and diff
        # it. Sealing means not SCORING them; hiding the list would only stop
        # the verification, not the tuning.
        "holdout": holdout,
    }
    pathlib.Path(a.out).write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"wrote {a.out}: {len(dev)} dev + {len(holdout)} hold-out "
          f"({len(cases)} total), case-set digest {doc['case_set_digest'][:16]}")
    print(f"max |share gap| over {report['distinct_defect_tags']['total']} "
          f"defect tags: {report['max_abs_share_gap_over_defect_tags']:.5f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
