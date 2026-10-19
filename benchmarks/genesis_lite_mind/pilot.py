"""BR-MIND-01 Stage 2: the matched Minimal Mind pilot on Genesis-lite v0.2 (measurement, never a formal claim).

Protocol (frozen by :func:`plan` and committed BEFORE the pilot root exists):

1. The Mind's code (``src/engcore/mind/minimal``, this package) and the v0.2 benchmark identity are bound by digest in
   the plan; the driver refuses to run when either differs.
2. A FRESH root secret is drawn by the operator outside the repository; only its sha256 is committed in the plan.  The
   development worlds the Mind was built on came from other seeds; no pilot world existed while the Mind was changed.
3. Every arm -- the 13 registered v0.2 arms and the 4 Mind variants -- runs every world set of the pilot grid exactly
   once, in an isolated proposer process, through the unchanged v0.2 harness: same card, same observe client, same
   budget, same paired stimulus (``harness.stimulus_key``), same separate evaluator and leakage audit.
4. After every run: the root is revealed in the summary; traces are paired to runs by presented-card digest; each FULL
   trace is replayed; pre-result predictions are scored; ablations are compared paired by world set.

What this pilot can and cannot say: the grid is not the preregistered formal grid, the escrow boundary is
SECURITY_BOUNDARY_NOT_PROVEN (B-LEAK open), the scoring defects FDA-05/FDA-06 and the O-1 significance procedure are not
repaired, and Genesis A1 has not passed.  ``analysis.lift_decision`` therefore returns "exploratory, no claim" by
construction; its numbers are reported as indicative.  Statistical semantics under adaptive search: the world set is
the unit and every arm (the Mind included) is frozen before any pilot world exists, so across-world comparisons do not
depend on the Mind's within-world adaptivity; the Mind's own within-world posteriors and falsifier verdicts carry no
frequentist error guarantee and are not used as evidence of lift.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import platform
import random
import statistics
import sys
import time
from multiprocessing import Pool
from typing import Any, Iterable

from benchmarks.genesis_lite import analysis
from benchmarks.genesis_lite import arms as arm_module
from benchmarks.genesis_lite import pilot as gl_pilot
from benchmarks.genesis_lite.harness import code_identity, run_one
from benchmarks.genesis_lite.presentation import PRESENTATIONS

from . import arm as marm

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
PLAN_PATH = HERE / "MIND_PILOT_PLAN.json"
PLAN_SCHEMA = "forge.genesis_lite.mind_pilot_plan/1"
CAMPAIGNS = 10
SEEDS = (0, 1, 2)
BOOTSTRAP = 2000
SIGN_FLIPS = 20000
MIND_SOURCES = sorted([*(ROOT / "src" / "engcore" / "mind" / "minimal").glob("*.py"), HERE / "arm.py", HERE / "pilot.py",
                       HERE / "__init__.py"])


def _file_digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mind_identity() -> dict[str, str]:
    return {p.relative_to(ROOT).as_posix(): _file_digest(p) for p in MIND_SOURCES}


def campaign_ids() -> list[str]:
    return [f"gl-mind-pilot-{i}" for i in range(CAMPAIGNS)]


def plan(root_commitment: str) -> dict[str, Any]:
    prereg, changed = code_identity()
    if changed:
        raise SystemExit(f"REFUSED: the v0.2 benchmark code differs from its preregistration: {changed}")
    return {
        "schema": PLAN_SCHEMA, "identity": "br_mind_01.minimal_mind_pilot.v1", "status": "FROZEN_BEFORE_ROOT",
        "benchmark": {"identity": "genesis_lite.blindfold_l5.v0_2", "preregistration_sha256": prereg},
        "mind_sources": mind_identity(),
        "root_commitment_sha256": root_commitment,
        "grid": {"campaigns": campaign_ids(), "presentations": list(PRESENTATIONS), "seeds": list(SEEDS),
                 "world_sets": CAMPAIGNS * len(PRESENTATIONS) * len(SEEDS),
                 "master": "benchmarks.genesis_lite.pilot.master_for(root, i, presentation, seed) -- one master per world "
                           "set, shared by every arm"},
        "arms": {"registered_v0_2": sorted(arm_module.ARMS), "mind": sorted(marm.MIND_ARMS)},
        "isolation": "proposer_process (every arm)",
        "analysis": {
            "primary": "mean campaign credit over world sets (v0.2 PRIMARY endpoint), per arm",
            "lift": "analysis.lift_decision(records, candidate, grid=pilot grid) per Mind variant -- exploratory by "
                    "construction (not the formal grid); reported as indicative, never as a claim",
            "ablations": "paired by world set: FULL minus each ablation; mean, cluster-bootstrap 95% interval (2000, seed 0) "
                         "and an exact-in-distribution paired sign-flip randomization p (20000 flips, seed 0), per kind "
                         "and pooled; no multiplicity correction is claimed (exploratory)",
            "ablation_rule": "a capability whose ablation is not worse than FULL (bootstrap interval of FULL - ablation "
                             "includes or lies below 0) is reported UNJUSTIFIED_ON_THIS_PILOT",
            "predictions": "every executed query with a sealed mixture prediction: mean log predictive density of ln y, "
                           "PIT-based 90% central-interval coverage; reported per variant and kind, apart from credit",
            "replay": "every FULL trace replayed from its recorded observations; status VERIFIED required",
            "fda05_exposure": "count of Mind 'indistinguishable' answers (the vacuous-pair defect FDA-05 is unrepaired)",
            "no_strong_baseline": "discoverable credit split by truth_in_searched_family; out-of-family worlds are "
                                  "NO_STRONG_BASELINE (capped in lift_decision)"},
        "limits": ["not the preregistered formal grid; no formal or maturity claim",
                   "escrow SECURITY_BOUNDARY_NOT_PROVEN (B-LEAK open, OD-20)",
                   "FDA-05 / FDA-06 / O-1 unrepaired (scoring cannot be frozen)",
                   "Genesis A1 not passed; this pilot runs under owner exception EXC-MIND-1",
                   "the Mind was developed on development worlds from the same generator (other seeds)"],
    }


def canonical(doc: dict[str, Any]) -> bytes:
    return json.dumps(doc, sort_keys=True, indent=1).encode() + b"\n"


# ------------------------------------------------------------------------------------------------------------- running
def _init_worker(trace_root: str) -> None:
    os.environ["TMPDIR"] = trace_root
    os.environ["TEMP"] = trace_root
    os.environ["TMP"] = trace_root


def _job(args: tuple[str, str, bytes, str, int, str]) -> dict[str, Any]:
    name, spec, master, presentation, seed, campaign = args
    fn = arm_module.ARMS[name][0] if name in arm_module.ARMS else None
    rec = run_one(name, fn, master_seed=master, campaign_id=campaign, presentation=presentation, seed=seed,
                  isolation="proposer_process", arm_spec=spec)
    return rec.to_dict()


def run(root: bytes, out: pathlib.Path, workers: int, arms: Iterable[str]) -> list[dict[str, Any]]:
    trace_root = out / "tmp"
    (trace_root / marm.TRACE_FOLDER).mkdir(parents=True, exist_ok=True)
    jobs = []
    for name in arms:
        spec = marm.MIND_ARMS[name][0] if name in marm.MIND_ARMS else name
        for seed in SEEDS:
            for presentation in PRESENTATIONS:
                for i, cid in enumerate(campaign_ids()):
                    jobs.append((name, spec, gl_pilot.master_for(root, i, presentation, seed), presentation, seed, cid))
    records = []
    with (out / "runs.jsonl").open("wb") as sink, Pool(workers, initializer=_init_worker, initargs=(str(trace_root),)) as pool:
        for rec in pool.imap_unordered(_job, jobs, chunksize=1):
            records.append(rec)
            sink.write(json.dumps(rec, sort_keys=True).encode() + b"\n")
            sink.flush()
    return records


# ------------------------------------------------------------------------------------------------------------ analysis
def sign_flip_p(diffs: list[float], flips: int = SIGN_FLIPS) -> float | None:
    """Two-sided paired sign-flip randomization p of the mean difference (Monte Carlo, seed 0, +1 correction)."""
    if not diffs:
        return None
    rng = random.Random(0)
    obs = abs(statistics.fmean(diffs))
    hits = 0
    for _ in range(flips):
        m = abs(statistics.fmean(d if rng.random() < 0.5 else -d for d in diffs))
        hits += m >= obs - 1e-12
    return (hits + 1) / (flips + 1)


def paired(credits: dict, a: str, b: str, kind: str | None = None) -> dict[str, Any]:
    shared = sorted(set(credits.get(a, {})) & set(credits.get(b, {})))
    diffs = [(credits[a][w][kind] if kind else sum(credits[a][w].values()))
             - (credits[b][w][kind] if kind else sum(credits[b][w].values())) for w in shared]
    mean, low, _ = analysis.bootstrap_mean_ci(diffs)
    hi = _upper(diffs)
    return {"world_sets": len(diffs), "mean_difference": None if not diffs else round(mean, 4),
            "ci95": None if not diffs else [round(low, 4), round(hi, 4)], "sign_flip_p": sign_flip_p(diffs)}


def _upper(values: list[float]) -> float:
    if not values:
        return float("nan")
    rng = random.Random(0)
    n = len(values)
    means = sorted(statistics.fmean(rng.choice(values) for _ in range(n)) for _ in range(BOOTSTRAP))
    return means[min(int(0.975 * BOOTSTRAP), BOOTSTRAP - 1)]


def traces_by_run(trace_dir: pathlib.Path) -> dict[str, dict[str, Any]]:
    out = {}
    for f in sorted(trace_dir.glob("*.json")):
        blob = json.loads(f.read_bytes())
        out[f"{f.name.split('-', 1)[0]}|{blob['card_digest']}"] = blob
    return out


def analyse(records: list[dict[str, Any]], trace_dir: pathlib.Path, *, replay_all: bool = True) -> dict[str, Any]:
    from engcore.mind.minimal import replay  # noqa: PLC0415

    grid = analysis.formal_grid(campaign_ids(), PRESENTATIONS, SEEDS)
    credits = analysis.world_credits(records)
    roles = analysis.registered_roles()
    required = sorted(a for a, r in roles.items() if r in analysis.NON_ADVERSARIAL_ROLES)
    primary = analysis.primary_scores(credits)
    best, base_scores = analysis.strongest_baseline({a: credits[a] for a in required if a in credits}, roles)
    out: dict[str, Any] = {"label": "MEASURED (Stage 2 pilot; indicative only; no formal, maturity or lift claim)"}
    out["primary_mean_campaign_credit"] = {a: round(s, 4) for a, s in sorted(primary.items())}
    out["strongest_registered_baseline"] = best
    out["per_kind_mean_credit"] = {a: {k: round(statistics.fmean(c[w][k] for w in c), 4) for k in analysis.KINDS}
                                   for a, c in sorted(credits.items())}
    out["validity"] = {a: {"runs": sum(r["arm"] == a for r in records),
                           "valid": sum(r["arm"] == a and r["status"] == "VALID" for r in records),
                           "isolated": sum(r["arm"] == a and r.get("isolation") == "proposer_process" for r in records),
                           "leakage_audit_clean": sum(r["arm"] == a and r.get("leakage_audit") == "NO_LITERAL_LEAK_FOUND" for r in records),
                           "evaluator_agrees": sum(r["arm"] == a and r.get("evaluator_status") == "VALID" for r in records),
                           "inadmissible": sum(u["outcome"] == "inadmissible" for r in records if r["arm"] == a for u in r["universes"])}
                       for a in sorted({r["arm"] for r in records})}
    out["invalid_reasons"] = sorted({x for r in records for x in r.get("reasons", [])})[:20]
    mind = sorted(marm.MIND_ARMS)
    out["lift_decision_exploratory"] = {}
    for cand in mind:
        rows = [r for r in records if r["arm"] in set(required) | {cand}]
        try:
            d = analysis.lift_decision(rows, cand, grid=grid)
            out["lift_decision_exploratory"][cand] = {k: d[k] for k in ("strongest_baseline", "shared_world_sets", "primary",
                                                                       "kind_noninferiority", "presentation_noninferiority",
                                                                       "holm_significant", "lift_claimed", "coverage_problems",
                                                                       "out_of_family_world_sets", "representation_limited_cells")}
        except analysis.AnalysisRefused as exc:
            out["lift_decision_exploratory"][cand] = {"refused": str(exc)}
    out["mind_vs_strongest_baseline"] = {c: paired(credits, c, best) for c in mind if best}
    out["mind_vs_best_arm_per_kind"] = {}
    per_kind_best = analysis.best_per_kind({a: credits[a] for a in required if a in credits}, roles)
    for c in mind:
        out["mind_vs_best_arm_per_kind"][c] = {k: {"reference": per_kind_best[k], **paired(credits, c, per_kind_best[k], k)}
                                               for k in analysis.KINDS if per_kind_best[k]}
    abl = {}
    for variant in ("mind_no_belief_update", "mind_no_adaptive_selection", "mind_no_falsifier"):
        if variant in credits and "mind_full" in credits:
            pooled = paired(credits, "mind_full", variant)
            abl[variant] = {"pooled": pooled, "per_kind": {k: paired(credits, "mind_full", variant, k) for k in analysis.KINDS},
                            "verdict": ("LIFT_MEASURED" if pooled["ci95"] and pooled["ci95"][0] > 0 else
                                        "UNJUSTIFIED_ON_THIS_PILOT")}
    out["ablations_full_minus_variant"] = abl
    off = analysis.out_of_family(records)
    split = {}
    for a, c in sorted(credits.items()):
        inside = [c[w]["discoverable"] for w in c if not off.get(w, True)]
        outside = [c[w]["discoverable"] for w in c if off.get(w, False)]
        split[a] = {"in_family_mean": round(statistics.fmean(inside), 4) if inside else None, "in_family_n": len(inside),
                    "out_of_family_mean_NO_STRONG_BASELINE": round(statistics.fmean(outside), 4) if outside else None,
                    "out_of_family_n": len(outside)}
    out["discoverable_family_split"] = split
    # ---- traces: prediction scores, refutations, replay, FDA-05 exposure
    traces = traces_by_run(trace_dir)
    pred: dict[str, dict[str, list]] = {}
    refuted: dict[str, list[int]] = {}
    sealed: dict[str, list[int]] = {}
    replays = {"VERIFIED": 0, "other": []}
    missing = 0
    by_outcome: dict[str, dict[str, list[float]]] = {}
    for r in records:
        if r["arm"] not in marm.MIND_ARMS or r["status"] != "VALID":
            continue
        variant = marm.MIND_ARMS[r["arm"]][1]
        for u in r["universes"]:
            key = f"{variant}|{r['presented_card_digests'][u['universe_id']]}"
            blob = traces.get(key)
            if blob is None:
                missing += 1
                continue
            t = blob["trace"]
            scores = [s["prediction_score"] for s in t["steps"] if s["prediction_score"].get("available")]
            cell = pred.setdefault(r["arm"], {}).setdefault(u["kind"], [])
            cell += [(s["log_score"], s["covered90"]) for s in scores]
            if scores:
                by_outcome.setdefault(r["arm"], {}).setdefault("full_credit" if u["credit"] >= 1 else "not_full_credit",
                                                               []).append(statistics.fmean(s["log_score"] for s in scores))
            refuted.setdefault(r["arm"], []).append(len(t["conclusion"]["diagnostics"].get("refuted", [])))
            sealed.setdefault(r["arm"], []).append(sum(1 for s in t["steps"] for f in s["pre_result"]["falsifiers"] if f.get("sealed")))
            if replay_all and variant == "full":
                rep = replay(t, marm.problem_from_card(blob["card"]))
                if rep["status"] == "VERIFIED":
                    replays["VERIFIED"] += 1
                else:
                    replays["other"].append({"run": f"{r['campaign_id']}/{r['presentation']}/{r['seed']}", **rep})
    out["prediction_scores"] = {a: {k: {"queries": len(v), "mean_log_score_ln_y": round(statistics.fmean(x for x, _ in v), 4) if v else None,
                                        "coverage90": round(statistics.fmean(1.0 if c else 0.0 for _, c in v), 4) if v else None}
                                    for k, v in sorted(cells.items())} for a, cells in sorted(pred.items())}
    out["prediction_score_by_final_credit"] = {a: {k: {"worlds": len(v), "mean_of_world_mean_log_score": round(statistics.fmean(v), 4)}
                                                   for k, v in sorted(d.items())} for a, d in sorted(by_outcome.items())}
    out["falsification"] = {a: {"worlds": len(v), "mean_refuted_rivals": round(statistics.fmean(v), 3),
                                "worlds_with_a_refutation": sum(x > 0 for x in v),
                                "mean_sealed_falsifiers": round(statistics.fmean(sealed[a]), 3)} for a, v in sorted(refuted.items())}
    out["replay_full_traces"] = {"verified": replays["VERIFIED"], "not_verified": replays["other"][:10],
                                 "not_verified_count": len(replays["other"])}
    out["traces_missing"] = missing
    out["fda05_exposure_indistinguishable_answers"] = {a: sum(u["answer"] == "indistinguishable" for r in records if r["arm"] == a
                                                             for u in r["universes"]) for a in mind}
    out["cost"] = {a: {"wall_seconds_per_campaign_mean": round(statistics.fmean(r["wall_seconds"] + r["host_start_seconds"]
                                                                                   for r in records if r["arm"] == a), 3),
                       "observe_calls_per_campaign": round(statistics.fmean(r["observe_calls"] for r in records if r["arm"] == a), 2)}
                   for a in sorted({r["arm"] for r in records})}
    formal_runs = analysis.FORMAL_GRID.__len__()
    out["stage3_formal_cost_ESTIMATE"] = {
        "label": "ESTIMATE from pilot wall times (single machine, sequential equivalent); not measured",
        "formal_world_sets": formal_runs,
        "seconds_by_arm": {a: round(formal_runs * c["wall_seconds_per_campaign_mean"], 1) for a, c in out["cost"].items()},
        "total_seconds_all_arms": round(sum(formal_runs * c["wall_seconds_per_campaign_mean"] for c in out["cost"].values()), 1)}
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="BR-MIND-01 Stage 2 Minimal Mind pilot")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("freeze", help="draw a fresh root (kept outside the repo) and write the frozen plan")
    f.add_argument("--root-file", required=True)
    r = sub.add_parser("run")
    r.add_argument("--root-file", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--workers", type=int, default=4)
    r.add_argument("--arms", default="all")
    a = sub.add_parser("analyse")
    a.add_argument("--root-file", required=True)
    a.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "freeze":
        path = pathlib.Path(args.root_file)
        if path.exists():
            print("REFUSED: a root file exists; a pilot root is drawn once", file=sys.stderr)
            return 2
        root = os.urandom(32)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(root.hex().encode())
        PLAN_PATH.write_bytes(canonical(plan(hashlib.sha256(root).hexdigest())))
        print(json.dumps({"plan": str(PLAN_PATH), "plan_sha256": hashlib.sha256(PLAN_PATH.read_bytes()).hexdigest()}))
        return 0
    committed = json.loads(PLAN_PATH.read_bytes())
    root = bytes.fromhex(pathlib.Path(args.root_file).read_bytes().decode().strip())
    if hashlib.sha256(root).hexdigest() != committed["root_commitment_sha256"]:
        print("REFUSED: the root does not match the plan's commitment", file=sys.stderr)
        return 2
    if committed["mind_sources"] != mind_identity():
        changed = sorted(k for k, v in mind_identity().items() if committed["mind_sources"].get(k) != v)
        print(f"REFUSED: the Mind's code changed after the plan was frozen: {changed}", file=sys.stderr)
        return 2
    prereg, changed = code_identity()
    if changed or prereg != committed["benchmark"]["preregistration_sha256"]:
        print("REFUSED: the v0.2 benchmark identity differs from the plan", file=sys.stderr)
        return 2
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.cmd == "run":
        names = sorted(arm_module.ARMS) + sorted(marm.MIND_ARMS) if args.arms == "all" else args.arms.split(",")
        t0 = time.perf_counter()
        records = run(root, out, args.workers, names)
        print(json.dumps({"runs": len(records), "invalid": sum(r["status"] != "VALID" for r in records),
                          "elapsed_seconds": round(time.perf_counter() - t0, 1)}))
        return 0
    records = [json.loads(line) for line in (out / "runs.jsonl").read_bytes().splitlines() if line.strip()]
    summary = analyse(records, out / "tmp" / marm.TRACE_FOLDER)
    summary["plan_sha256"] = hashlib.sha256(PLAN_PATH.read_bytes()).hexdigest()
    summary["pilot_root_revealed_hex"] = root.hex()
    summary["environment"] = {"python": sys.version, "platform": platform.platform(), "cpu_count": os.cpu_count()}
    (out / "summary.json").write_bytes(json.dumps(summary, sort_keys=True, indent=1).encode() + b"\n")
    print(json.dumps({k: summary[k] for k in ("primary_mean_campaign_credit", "strongest_registered_baseline")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
