"""Genesis-lite v0.3 DEVELOPMENT cost pilot (owner-approved 2026-10-28: 30-minute cap, 4 workers).

Every available arm -- the v0.2 arms and the v0.3 development baselines (PySR, PySINDy, BoTorch) -- runs development
campaigns through :func:`.harness_v3.run_one_v3`. World sets are paired across arms (one master seed per campaign,
presentation and seed, never reused) and scheduled world set by world set, so a deadline truncates every arm equally.
Unavailable arms are recorded, never substituted. Runs are written as they finish.

Measurement only. The summary reports cost (wall time, observations, worker memory), validity, evaluator disagreements,
library failures (inadmissible universes) and unresolved pairs per arm, plus an ESTIMATE of the formal tier's cost. Credit
appears only as DEVELOPMENT_DESCRIPTIVE output: not a rate, not a lift and not a benchmark result (no preregistration, no
custody, no statistics).
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import hashlib
import hmac
import json
import multiprocessing
import os
import pathlib
import platform
import secrets
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping, Sequence

from . import arms as arms_v2
from .arms_v3 import ARMS_V3, availability_v3
from .harness import code_identity
from .harness_v3 import development_identity, library_versions, run_one_v3

PRESENTATIONS = ("anonymous", "renamed", "paraphrased", "trap")
RUNG = 10
PILOT_SEEDS = (0, 1, 2)
FORMAL_CAMPAIGNS = 30 * len(PRESENTATIONS) * 20          # per arm: 30 campaigns x 4 presentations x 20 seeds (Genesis floor)
DEFAULT_DEADLINE = 28 * 60                               # inside the owner's 30-minute cap, leaving time to stop and write
GRACE_SECONDS = 60
DESCRIPTIVE = "DEVELOPMENT_DESCRIPTIVE: not a rate, a lift or a benchmark result"


@dataclass(frozen=True)
class Task:
    arm: str
    campaign: int
    presentation: str
    seed: int


def plan(arm_names: Sequence[str], *, campaigns: int, presentations: Iterable[str], seeds: Iterable[int]) -> list[Task]:
    presentations = tuple(presentations)
    return [Task(arm, i, pres, seed) for seed in seeds for i in range(campaigns) for pres in presentations for arm in arm_names]


def master_seed(root: bytes, campaign: int, presentation: str, seed: int) -> bytes:
    return hmac.new(root, f"forge.genesis_lite.v0_3.dev\n{campaign}\n{presentation}\n{seed}".encode(), hashlib.sha256).digest()


def _arm(name: str):
    return (arms_v2.ARMS.get(name) or ARMS_V3[name])[0]


def all_arms() -> list[str]:
    return sorted(arms_v2.ARMS) + sorted(ARMS_V3)


def arm_available(name: str) -> bool:
    if name in arms_v2.ARMS:
        return True
    return availability_v3()[name]["status"] == "AVAILABLE_DEVELOPMENT"


def _work(task: Task, root_hex: str) -> dict[str, Any]:
    """One campaign (runs in a worker process)."""
    rec = run_one_v3(task.arm, _arm(task.arm), master_seed=master_seed(bytes.fromhex(root_hex), task.campaign,
                                                                         task.presentation, task.seed),
                     campaign_id=f"gl-v03-dev-{task.seed}-{task.campaign}-{task.presentation}", presentation=task.presentation,
                     seed=task.seed)
    try:
        import resource
        maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss   # KiB on Linux
    except ImportError:
        maxrss = None
    return {**rec.to_dict(), "task": asdict(task), "worker_pid": os.getpid(), "worker_maxrss_kib": maxrss}


def _git_head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True,
                              cwd=pathlib.Path(__file__).resolve().parents[2]).stdout.strip()
    except Exception:  # noqa: BLE001 - provenance best effort; recorded as unknown
        return "UNKNOWN"


def run_pilot(arm_names: Sequence[str], *, out: pathlib.Path | str, campaigns: int = RUNG,
              presentations: Iterable[str] = PRESENTATIONS, seeds: Iterable[int] = PILOT_SEEDS, workers: int = 4,
              deadline_seconds: float = DEFAULT_DEADLINE, root: bytes | None = None) -> dict[str, Any]:
    out = pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    root = secrets.token_bytes(32) if root is None else root
    presentations, seeds = tuple(presentations), tuple(seeds)
    started_wall, t0 = time.strftime("%Y-%m-%dT%H:%M:%S%z"), time.monotonic()
    available = {name: arm_available(name) for name in arm_names}
    runnable = [name for name in arm_names if available[name]]
    tasks = plan(runnable, campaigns=campaigns, presentations=presentations, seeds=seeds)
    records: list[dict[str, Any]] = []
    not_run: list[Task] = []
    interrupted: list[Task] = []
    runs_path = out / "runs.jsonl"
    runs_path.write_text("")

    def keep(record: dict[str, Any]) -> None:
        records.append(record)
        with runs_path.open("a") as fh:
            fh.write(json.dumps(record, sort_keys=True, default=str) + "\n")

    if deadline_seconds <= 0:
        not_run = list(tasks)
    elif workers <= 1:
        for k, task in enumerate(tasks):
            if time.monotonic() - t0 >= deadline_seconds:
                not_run = tasks[k:]
                break
            keep(_work(task, root.hex()))
    else:
        executor = cf.ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"))
        futures = {executor.submit(_work, task, root.hex()): task for task in tasks}
        try:
            for fut in cf.as_completed(futures, timeout=max(0.0, deadline_seconds - (time.monotonic() - t0))):
                keep(fut.result())
        except cf.TimeoutError:
            pending = [f for f in futures if not f.done()]
            for f in pending:
                if f.cancel():
                    not_run.append(futures[f])
            running = [f for f in pending if not f.cancelled()]
            done, still = cf.wait(running, timeout=GRACE_SECONDS)
            for f in done:
                keep(f.result())
            interrupted = [futures[f] for f in still]
            for proc in list(getattr(executor, "_processes", {}).values()):
                proc.terminate()
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
    elapsed = time.monotonic() - t0
    summary = _summarize(arm_names, available, records, not_run, interrupted, presentations, seeds, campaigns, elapsed,
                         workers, deadline_seconds)
    identity, changed = development_identity()
    env = {"python": sys.version, "platform": platform.platform(), "cpu_count": os.cpu_count(), "workers": workers,
           "deadline_seconds": deadline_seconds, "started": started_wall, "elapsed_seconds": elapsed,
           "root_commitment_sha256": hashlib.sha256(root).hexdigest(), "git_head": _git_head(),
           "development_identity": identity, "v0_2_prereg_identity": code_identity()[0], "v0_2_pin_changed": changed,
           "library_versions": library_versions()}
    (out / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True))
    (out / "environment.json").write_text(json.dumps(env, indent=1, sort_keys=True))
    return json.loads(json.dumps(summary))


def _summarize(arm_names, available, records, not_run, interrupted, presentations, seeds, campaigns, elapsed, workers,
               deadline) -> dict[str, Any]:
    by_arm: dict[str, list[dict]] = collections.defaultdict(list)
    for r in records:
        by_arm[r["arm"]].append(r)
    arms_out = {}
    for name in arm_names:
        rs = by_arm.get(name, [])
        valid = [r for r in rs if r["status"] == "VALID"]
        walls = [r["wall_seconds"] for r in rs]
        universes = [u for r in valid for u in r["universes"]]
        per_kind = collections.defaultdict(list)
        for u in universes:
            per_kind[u["kind"]].append(u["credit"])
        reasons = collections.Counter(reason[:120] for r in rs for reason in r["reasons"])
        arms_out[name] = {
            "status": "AVAILABLE" if available[name] else "ARM_UNAVAILABLE",
            "family": (arms_v2.ARMS.get(name) or ARMS_V3.get(name) or (None, ""))[1],
            "runs": len(rs), "valid": len(valid), "invalid": len(rs) - len(valid),
            "evaluator_disagreement_invalid": sum(any("separate v0.3 evaluator" in x for x in r["reasons"]) for r in rs),
            "invalid_reasons_top": dict(reasons.most_common(5)),
            "not_run": sum(t.arm == name for t in not_run), "interrupted": sum(t.arm == name for t in interrupted),
            "wall_seconds_total": round(sum(walls), 3),
            "wall_seconds_mean": round(sum(walls) / len(walls), 4) if walls else None,
            "wall_seconds_max": round(max(walls), 3) if walls else None,
            "observe_calls_mean": round(sum(r["observe_calls"] for r in rs) / len(rs), 2) if rs else None,
            "worker_maxrss_kib_max": max((r["worker_maxrss_kib"] or 0 for r in rs), default=None),
            "inadmissible_universes": sum(u["answer"] == "inadmissible" for u in universes),
            "unresolved_universes": sum(u["outcome"] == "indistinguishable_unresolved" for u in universes),
            "descriptive_credit": {"label": DESCRIPTIVE,
                                   "mean_total_per_valid_run": (round(sum(r["v3_total_credit"] for r in valid) / len(valid), 4)
                                                                if valid else None),
                                   "mean_per_kind": {k: round(sum(v) / len(v), 4) for k, v in sorted(per_kind.items())}},
            "formal_cost_estimate_seconds": (round(FORMAL_CAMPAIGNS * sum(walls) / len(walls), 1) if walls else None),
        }
    world_sets = collections.defaultdict(set)
    for r in records:
        if r["status"] == "VALID":
            t = r["task"]
            world_sets[(t["campaign"], t["presentation"], t["seed"])].add(r["arm"])
    runnable = {name for name in arm_names if available[name]}
    estimates = [a["formal_cost_estimate_seconds"] for a in arms_out.values() if a["formal_cost_estimate_seconds"]]
    return {
        "readiness": "DEVELOPMENT_ONLY", "claims": "COST_MEASUREMENT_ONLY", "benchmark_id": "genesis_lite.blindfold_l5.v0_3",
        "design": {"campaigns_per_presentation_per_seed": campaigns, "presentations": list(presentations),
                   "seeds": list(seeds), "workers": workers, "deadline_seconds": deadline},
        "elapsed_seconds": round(elapsed, 2),
        "tasks": {"planned": len(records) + len(not_run) + len(interrupted), "completed": len(records),
                  "not_run": len(not_run), "interrupted": len(interrupted)},
        "paired_world_sets_complete": sum(1 for arms in world_sets.values() if runnable and runnable <= arms),
        "arms": arms_out,
        "formal_tier_estimate": {"label": "ESTIMATE from measured mean wall per campaign; single-worker seconds",
                                 "campaigns_per_arm": FORMAL_CAMPAIGNS, "sum_over_arms_seconds": round(sum(estimates), 1),
                                 "wall_hours_at_4_workers": round(sum(estimates) / 4 / 3600, 2)},
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genesis-lite v0.3 development cost pilot")
    parser.add_argument("--out", required=True)
    parser.add_argument("--arms", default="all")
    parser.add_argument("--campaigns", type=int, default=RUNG)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--deadline-seconds", type=float, default=DEFAULT_DEADLINE)
    args = parser.parse_args(argv)
    names = all_arms() if args.arms == "all" else args.arms.split(",")
    summary = run_pilot(names, out=args.out, campaigns=args.campaigns, workers=args.workers,
                        deadline_seconds=args.deadline_seconds)
    print(json.dumps({"tasks": summary["tasks"], "elapsed_seconds": summary["elapsed_seconds"],
                      "paired_world_sets_complete": summary["paired_world_sets_complete"]}))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
