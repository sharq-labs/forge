"""Genesis-lite Tier 1: the bounded cost pilot (Genesis §10.6 step 1). Measurement, never a rate claim.

For every arm, every presentation and the preregistered seeds, run the 10-campaign rung. Each campaign holds one universe
of every kind. v0.1: each world set (campaign, presentation, seed) has its own master seed, shared by every arm (paired
worlds, as in the formal tier) and never reused; every arm runs in an isolated proposer process, and run-private keys
pseudonymise ids and names.

Rates are analysed with the WORLD as the unit (review H5): per world, the fraction of seeds with full credit; the cell
rate is the mean over worlds; its interval is a percentile bootstrap over worlds (2000 resamples, seed 0).

Outputs (``--out`` directory): ``runs.jsonl`` (written as runs finish), ``summary.json`` (MEASURED aggregates and a
separately labelled ESTIMATE for the formal tier) and ``environment.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import os
import pathlib
import platform
import random
import statistics
import sys
import time
from typing import Any, Callable, Iterable

from . import analysis
from . import arms as arm_module
from .harness import RunRecord, run_one
from .presentation import PRESENTATIONS

RUNG = 10
PILOT_SEEDS = (0, 1, 2)
FORMAL_CAMPAIGNS_PER_PRESENTATION = 30
FORMAL_SEEDS = 20
BOOTSTRAP = 2000


def master_for(root: bytes, i: int, presentation: str, seed: int) -> bytes:
    """v0.1: one master per world set (campaign, presentation, seed), shared by every arm (paired comparisons) and never
    reused across seeds or presentations, so no proposer sees a world twice (review: cross-seed pooling)."""
    return hmac.new(root, f"forge.genesis_lite.v0_1/{presentation}/{seed}/{i}".encode(), hashlib.sha256).digest()


def run_pilot(root: bytes, arms: Iterable[str], *, campaigns: int = RUNG, seeds: Iterable[int] = PILOT_SEEDS,
              presentations: Iterable[str] = PRESENTATIONS, sink: Callable[[RunRecord], None] | None = None,
              isolation: str = "proposer_process") -> list[RunRecord]:
    records = []
    for name in arms:
        fn, _family, _stochastic, _role = arm_module.ARMS[name]
        for seed in tuple(seeds):                              # every arm runs every world set once
            for presentation in presentations:
                for i in range(campaigns):
                    rec = run_one(name, fn, master_seed=master_for(root, i, presentation, seed), campaign_id=f"gl-pilot-{i}",
                                  presentation=presentation, seed=seed, isolation=isolation,
                                  measure_memory=(i == 0 and presentation == "anonymous" and seed == 0
                                                  and isolation == "in_process"))
                    records.append(rec)
                    if sink is not None:
                        sink(rec)
    return records


def cluster_bootstrap(per_world: list[float], resamples: int = BOOTSTRAP) -> list[float] | None:
    if not per_world:
        return None
    rng = random.Random(0)
    n = len(per_world)
    means = sorted(statistics.fmean(rng.choice(per_world) for _ in range(n)) for _ in range(resamples))
    return [round(means[int(0.025 * resamples)], 4), round(means[int(0.975 * resamples) - 1], 4)]


def summarize(records: list[RunRecord]) -> dict[str, Any]:
    valid = [r for r in records if r.status == "VALID"]
    worlds: dict[str, dict[str, list[float]]] = {}
    credits: dict[str, dict[str, list[float]]] = {}
    for r in valid:
        for u in r.universes:
            cell = f"{r.arm}|{u['kind']}|{r.presentation}"
            # the world is keyed by its escrow universe id (seed- and kind-derived, unique per world), never by campaign id
            worlds.setdefault(cell, {}).setdefault(u["universe_id"], []).append(1.0 if u["credit"] >= 1.0 else 0.0)
            credits.setdefault(cell, {}).setdefault(u["universe_id"], []).append(u["credit"])
    invalid_cells: dict[str, int] = {}
    for r in records:
        if r.status != "VALID":
            key = f"{r.arm}|*|{r.presentation}"
            invalid_cells[key] = invalid_cells.get(key, 0) + 1
    table = {}
    for cell in sorted(worlds):
        per_world = [statistics.fmean(v) for v in worlds[cell].values()]
        per_world_credit = [statistics.fmean(v) for v in credits[cell].values()]
        table[cell] = {"worlds": len(per_world), "runs": sum(len(v) for v in worlds[cell].values()),
                       "full_credit_rate": round(statistics.fmean(per_world), 4),
                       "full_credit_ci95_cluster_bootstrap": cluster_bootstrap(per_world),
                       "mean_credit": round(statistics.fmean(per_world_credit), 4),
                       "mean_credit_ci95_cluster_bootstrap": cluster_bootstrap(per_world_credit)}
    indicative_rl = sorted(k.split("|", 1)[1] for k, t in table.items()
                           if k.startswith("monomial_enumeration|") and t["full_credit_ci95_cluster_bootstrap"]
                           and t["full_credit_ci95_cluster_bootstrap"][0] >= 0.5)
    family = {}
    for kind in ("discoverable", "spurious_correlate", "confounded"):
        flags = {(r.campaign_id, u["universe_id"]): u["truth_in_searched_family"] for r in valid for u in r.universes
                 if u["kind"] == kind}
        family[kind] = None if not flags else round(sum(flags.values()) / len(flags), 4)
    tell_rows = [(u["region_tell"], u["kind"]) for r in valid if r.presentation == "anonymous" and r.arm == "always_refuse"
                 for u in r.universes]
    tells = {t: sorted({k for tt, k in tell_rows if tt == t}) for t in ("box", "ordinary_extension", "pushed_extension")}
    pushed = [k for t, k in tell_rows if t == "pushed_extension"]
    indist = [t for t, k in tell_rows if k == "indistinguishable"]
    cost: dict[str, Any] = {}
    for name in sorted({r.arm for r in records}):
        mine = [r for r in records if r.arm == name]
        timed = [r.wall_seconds + r.host_start_seconds for r in mine if not r.memory_instrumented]
        per_kind: dict[str, list[float]] = {}
        for r in mine:
            for u in r.universes:
                per_kind.setdefault(u["kind"], []).append(u.get("proposer_seconds", 0.0))
        seed_credit: dict[int, list[float]] = {}
        for r in mine:
            if r.status == "VALID":
                seed_credit.setdefault(r.seed, []).append(sum(u["credit"] for u in r.universes))
        cost[name] = {
            "campaign_runs": len(mine), "valid_runs": sum(r.status == "VALID" for r in mine),
            "invalid_runs": sum(r.status != "VALID" for r in mine),
            "inadmissible_proposals": sum(u["outcome"] == "inadmissible" for r in mine for u in r.universes),
            "wall_seconds_per_campaign": {"mean": statistics.fmean(timed), "sd": statistics.pstdev(timed), "max": max(timed),
                                          "n": len(timed), "includes": "proposer-process start-up",
                                          "excludes": "the memory-instrumented run"},
            "observe_calls_per_campaign": statistics.fmean(r.observe_calls for r in mine),
            "peak_traced_kib": max((r.peak_traced_kib for r in mine if r.peak_traced_kib is not None), default=None),
            "proposer_seconds_per_universe_by_kind": {k: statistics.fmean(v) for k, v in sorted(per_kind.items())},
            "mean_campaign_credit_by_seed": {str(s): round(statistics.fmean(v), 4) for s, v in sorted(seed_credit.items())},
            "sd_of_seed_means": (round(statistics.pstdev([statistics.fmean(v) for v in seed_credit.values()]), 4)
                                 if len(seed_credit) > 1 else None),
        }
    invariance: dict[str, Any] = {}
    credits = analysis.world_credits(records)
    roles = {name: arm_module.ARMS[name][3] for name in credits if name in arm_module.ARMS}
    best, primary = analysis.strongest_baseline(credits, roles) if credits else (None, {})
    per_kind_best = analysis.best_per_kind(credits, roles) if credits else {}
    split = {}
    for name, camps in credits.items():
        disc = [k.get("discoverable", 0.0) for k in camps.values()]
        ctrl = [sum(v for kind, v in k.items() if kind != "discoverable") for k in camps.values()]
        family = {True: [], False: []}
        for r in valid:
            if r.arm == name:
                for u in r.universes:
                    if u["kind"] == "discoverable":
                        family[bool(u["truth_in_searched_family"])].append(u["credit"])
        split[name] = {"discovery_credit_per_campaign": round(statistics.fmean(disc), 4),
                       "control_credit_per_campaign": round(statistics.fmean(ctrl), 4),
                       "discovery_credit_in_family": round(statistics.fmean(family[True]), 4) if family[True] else None,
                       "discovery_credit_out_of_family_NO_STRONG_BASELINE":
                           round(statistics.fmean(family[False]), 4) if family[False] else None}
    for name in sorted({r.arm for r in valid}):
        outcome = {(r.seed, r.presentation, r.campaign_id, u["kind"]): u["outcome"] for r in valid if r.arm == name
                   for u in r.universes}
        pairs = [(o, outcome[(s, "anonymous", cid, k)]) for (s, p, cid, k), o in outcome.items()
                 if p != "anonymous" and (s, "anonymous", cid, k) in outcome]
        invariance[name] = None if not pairs else round(sum(a == b for a, b in pairs) / len(pairs), 4)
    return {"label": "MEASURED (pilot tier; cost and variance only; not a rate claim)",
            "primary_endpoint_indicative": {"mean_campaign_credit": {k: round(v, 4) for k, v in sorted(primary.items())},
                                            "strongest_non_adversarial_arm": best, "best_arm_per_kind": per_kind_best,
                                            "credit_split": split,
                                            "note": "pilot scale (10 campaigns per presentation): indicative only"},
            "cells": table,
            "invalid_runs_by_arm_presentation": invalid_cells,
            "representation_limited_indicative": indicative_rl,
            "truth_in_searched_family_fraction": family,
            "region_tell": {"kinds_by_tell": tells,
                            "pushed_extension_is_indistinguishable": None if not pushed else round(
                                sum(k == "indistinguishable" for k in pushed) / len(pushed), 4),
                            "indistinguishable_flagged_by_pushed_extension": None if not indist else round(
                                sum(t == "pushed_extension" for t in indist) / len(indist), 4)},
            "outcome_agreement_with_anonymous": {"note": "same worlds; differs by presentation AND by run-private design "
                                                 "randomness (pseudonymous ids seed the arms)", "by_arm": invariance},
            "cost": cost, "estimate": estimate(cost),
            "invalid_reasons": sorted({x for r in records for x in r.reasons})}


def estimate(cost: dict[str, Any]) -> dict[str, Any]:
    """Formal-tier ESTIMATE: runs x measured per-campaign wall time, with a 95% interval from the measured spread."""
    rows, total_mean, total_var = {}, 0.0, 0.0
    for name, c in cost.items():
        runs = FORMAL_CAMPAIGNS_PER_PRESENTATION * len(PRESENTATIONS) * FORMAL_SEEDS   # every arm, every world set
        mean, sd = c["wall_seconds_per_campaign"]["mean"], c["wall_seconds_per_campaign"]["sd"]
        rows[name] = {"campaign_runs": runs, "seconds": round(runs * mean, 1)}
        total_mean += runs * mean
        total_var += runs * sd * sd
    half = 1.96 * math.sqrt(total_var)
    return {"label": "ESTIMATE (derived from pilot measurements; not measured)", "per_arm": rows,
            "total_campaign_runs": sum(r["campaign_runs"] for r in rows.values()),
            "baseline_arms_total_seconds": round(total_mean, 1),
            "interval95_seconds": [round(max(0.0, total_mean - half), 1), round(total_mean + half, 1)],
            "excludes": "Mind, LLM-ablation and model-swap arms (do not exist; their cost is UNMEASURED); a full-grammar "
                        "enumerator, PySR, BoTorch (not integrated); an isolated escrow transport (UNMEASURED)",
            "assumes": "one process on the pilot machine, in-process escrow, distinct master roots do not change cost"}


def prereg_matches_code() -> tuple[bool, str]:
    """Rebuild the preregistration from the code and byte-compare it with the committed one (review M1)."""
    from .preregistration import PREREG_PATH, build, canonical

    committed = PREREG_PATH.read_bytes()
    doc = json.loads(committed)
    rebuilt = canonical(build(doc["pilot_root_commitment_sha256"]))
    return rebuilt == committed, hashlib.sha256(committed).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genesis-lite Tier 1 cost pilot")
    parser.add_argument("--root-file", required=True, help="file holding the pilot root secret (hex), committed in the prereg")
    parser.add_argument("--out", required=True)
    parser.add_argument("--arms", default="all")
    parser.add_argument("--campaigns", type=int, default=RUNG)
    args = parser.parse_args(argv)
    from .preregistration import PREREG_PATH

    ok, prereg_sha = prereg_matches_code()
    if not ok:
        print("REFUSED: the code no longer rebuilds the committed preregistration (a changed benchmark is a new identity)",
              file=sys.stderr)
        return 2
    root = bytes.fromhex(pathlib.Path(args.root_file).read_text().strip())
    prereg = json.loads(PREREG_PATH.read_bytes())
    if hashlib.sha256(root).hexdigest() != prereg["pilot_root_commitment_sha256"]:
        print("REFUSED: the pilot root does not match the preregistered commitment", file=sys.stderr)
        return 2
    names = sorted(arm_module.ARMS) if args.arms == "all" else args.arms.split(",")
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    runs = (out / "runs.jsonl").open("wb")

    def sink(rec: RunRecord) -> None:
        runs.write(json.dumps(rec.to_dict(), sort_keys=True).encode() + b"\n")
        runs.flush()

    t0 = time.perf_counter()
    try:
        records = run_pilot(root, names, campaigns=args.campaigns, sink=sink)
    finally:
        runs.close()
    elapsed = time.perf_counter() - t0
    summary = summarize(records)
    summary["elapsed_seconds"] = round(elapsed, 2)
    summary["arm_availability"] = arm_module.availability()
    summary["pilot_root_revealed_hex"] = root.hex()
    summary["prereg_sha256"] = prereg_sha
    (out / "summary.json").write_bytes(json.dumps(summary, sort_keys=True, indent=1).encode() + b"\n")
    env = {"python": sys.version, "platform": platform.platform(), "cpu_count": os.cpu_count(), "prereg_sha256": prereg_sha}
    (out / "environment.json").write_bytes(json.dumps(env, sort_keys=True, indent=1).encode() + b"\n")
    print(json.dumps({"runs": len(records), "invalid": summary["invalid_reasons"][:5], "elapsed_seconds": round(elapsed, 2)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
