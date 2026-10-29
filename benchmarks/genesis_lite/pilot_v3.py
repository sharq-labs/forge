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
from .mind_arm_v3 import MIND_ARMS
from .harness import code_identity
from .harness_v3 import development_identity, library_versions, run_one_v3

PRESENTATIONS = ("anonymous", "renamed", "paraphrased", "trap")
RUNG = 10
PILOT_SEEDS = (0, 1, 2)
FORMAL_CAMPAIGNS = 30 * len(PRESENTATIONS) * 20          # per arm: 30 campaigns x 4 presentations x 20 seeds (Genesis floor)
DEFAULT_DEADLINE = 28 * 60                               # inside the owner's 30-minute cap, leaving time to stop and write
GRACE_SECONDS = 60
DESCRIPTIVE = "DEVELOPMENT_DESCRIPTIVE: not a rate, a lift or a benchmark result"
#: one thread per worker process: with 4 unpinned workers torch/BLAS each grabbed every core and a BoTorch campaign took
#: 318 s instead of 1.6 s (smoke run 2026-10-28). Set before any numerical library is imported in the worker.
THREAD_LIMITS = {"OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1",
                 "JULIA_NUM_THREADS": "1"}


def _init_worker() -> None:
    os.environ.update(THREAD_LIMITS)


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
    return (arms_v2.ARMS.get(name) or ARMS_V3.get(name) or MIND_ARMS[name])[0]


def all_arms() -> list[str]:
    return sorted(arms_v2.ARMS) + sorted(ARMS_V3) + sorted(MIND_ARMS)


def arm_available(name: str) -> bool:
    if name in arms_v2.ARMS or name in MIND_ARMS:
        return True
    return availability_v3()[name]["status"] == "AVAILABLE_DEVELOPMENT"


def _threads_in_force() -> dict[str, Any]:
    """The numerical thread counts actually in force in this process (not the requested ones)."""
    out: dict[str, Any] = {"blas_max": None, "torch": None}
    try:
        from threadpoolctl import threadpool_info
        counts = [int(lib.get("num_threads", 0)) for lib in threadpool_info()]
        out["blas_max"] = max(counts) if counts else None
    except Exception:  # noqa: BLE001 - recorded as unknown, never assumed
        pass
    if "torch" in sys.modules:
        out["torch"] = sys.modules["torch"].get_num_threads()
    return out


def _work(task: Task, master_seed_hex: str) -> dict[str, Any]:
    """One campaign (runs in a worker process). The worker receives only this campaign's master seed, never the root."""
    rec = run_one_v3(task.arm, _arm(task.arm), master_seed=bytes.fromhex(master_seed_hex),
                     campaign_id=f"gl-v03-dev-{task.seed}-{task.campaign}-{task.presentation}", presentation=task.presentation,
                     seed=task.seed)
    try:
        import resource
        maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss   # KiB on Linux
    except ImportError:
        maxrss = None
    return {**rec.to_dict(), "task": asdict(task), "worker_pid": os.getpid(), "worker_maxrss_kib": maxrss,
            "threads_in_force": _threads_in_force()}


def _executor(workers: int) -> cf.Executor:
    return cf.ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"),
                                  initializer=_init_worker)


class _PinnedThreads:
    """THREAD_LIMITS in the parent while the spawned workers start (they inherit it before importing numpy: the initializer
    alone runs after unpickling has imported numpy, and measured 20 BLAS threads per worker at 5daaba81); restored after."""

    def __enter__(self) -> "_PinnedThreads":
        self.saved = {k: os.environ.get(k) for k in THREAD_LIMITS}
        os.environ.update(THREAD_LIMITS)
        return self

    def __exit__(self, *exc: Any) -> None:
        for k, value in self.saved.items():
            if value is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = value


def _failure_record(task: Task, exc: BaseException) -> dict[str, Any]:
    return {"arm": task.arm, "status": "WORKER_FAILED", "reasons": [f"{type(exc).__name__}: {str(exc)[:300]}"],
            "wall_seconds": None, "observe_calls": None, "worker_maxrss_kib": None, "v3_total_credit": None,
            "universes": [], "task": asdict(task), "threads_in_force": {}}


def _git_head() -> str:
    try:
        root = pathlib.Path(__file__).resolve().parents[2]
        head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, cwd=root).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=True, cwd=root).stdout
        return head + ("+dirty" if dirty.strip() else "")
    except Exception:  # noqa: BLE001 - provenance best effort; recorded as unknown
        return "UNKNOWN"


def run_pilot(arm_names: Sequence[str], *, out: pathlib.Path | str, campaigns: int = RUNG,
              presentations: Iterable[str] = PRESENTATIONS, seeds: Iterable[int] = PILOT_SEEDS, workers: int = 4,
              deadline_seconds: float = DEFAULT_DEADLINE, root: bytes | None = None) -> dict[str, Any]:
    if len(set(arm_names)) != len(arm_names):
        raise ValueError("an arm is named twice: its world sets would be reused")
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

    def seed_hex(task: Task) -> str:
        return master_seed(root, task.campaign, task.presentation, task.seed).hex()

    if deadline_seconds <= 0:
        not_run = list(tasks)
    elif workers <= 1:
        for k, task in enumerate(tasks):
            if time.monotonic() - t0 >= deadline_seconds:
                not_run = tasks[k:]
                break
            try:
                keep(_work(task, seed_hex(task)))
            except Exception as exc:  # noqa: BLE001 - a crashed campaign is recorded, never lost
                keep(_failure_record(task, exc))
    else:
        with _PinnedThreads():                 # workers are spawned during submit; the parent is restored afterwards
            executor = _executor(workers)
            futures = {executor.submit(_work, task, seed_hex(task)): task for task in tasks}
        collected: set = set()

        def collect(f: cf.Future) -> None:
            collected.add(f)
            try:
                keep(f.result())
            except Exception as exc:  # noqa: BLE001 - a dead worker (BrokenProcessPool) is recorded, never lost
                keep(_failure_record(futures[f], exc))

        try:
            for f in cf.as_completed(futures, timeout=max(0.0, deadline_seconds - (time.monotonic() - t0))):
                collect(f)
        except cf.TimeoutError:
            pass
        for f in futures:                      # finished while the last result was being written: still counted
            if f.done() and not f.cancelled() and f not in collected:
                collect(f)
        pending = [f for f in futures if not f.done()]
        for f in pending:
            if f.cancel():
                not_run.append(futures[f])
        running = [f for f in pending if not f.cancelled()]
        if running:
            done, still = cf.wait(running, timeout=GRACE_SECONDS)
            for f in done:
                collect(f)
            interrupted = [futures[f] for f in still]
            for proc in list(getattr(executor, "_processes", {}).values()):
                proc.terminate()
        executor.shutdown(wait=False, cancel_futures=True)
    elapsed = time.monotonic() - t0
    summary = _summarize(arm_names, available, records, not_run, interrupted, presentations, seeds, campaigns, elapsed,
                         workers, deadline_seconds, planned=len(tasks))
    identity, changed = development_identity()
    env = {"python": sys.version, "platform": platform.platform(), "cpu_count": os.cpu_count(), "workers": workers,
           "worker_thread_limits": THREAD_LIMITS if workers > 1 else {},
           "deadline_seconds": deadline_seconds, "started": started_wall, "elapsed_seconds": elapsed,
           "root_commitment_sha256": hashlib.sha256(root).hexdigest(), "git_head": _git_head(),
           "development_identity": identity, "v0_2_prereg_identity": code_identity()[0], "v0_2_pin_changed": changed,
           "run_identities": sorted({r.get("development_identity", "") for r in records}),
           "library_versions": library_versions()}
    (out / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True))
    (out / "environment.json").write_text(json.dumps(env, indent=1, sort_keys=True))
    return json.loads(json.dumps(summary))


def _world(r: Mapping[str, Any]) -> tuple:
    t = r["task"]
    return (t["campaign"], t["presentation"], t["seed"])


def _is_library_failure(u: Mapping[str, Any]) -> bool:
    head = str(u.get("rationale", "")).split(":", 1)[0]
    return u.get("answer") == "inadmissible" and (head.endswith("Error") or head.endswith("Exception"))


def _summarize(arm_names, available, records, not_run, interrupted, presentations, seeds, campaigns, elapsed, workers,
               deadline, *, planned: int, missing_records: int = 0) -> dict[str, Any]:
    runnable = [name for name in arm_names if available[name]]
    by_arm: dict[str, list[dict]] = collections.defaultdict(list)
    worlds: dict[tuple, dict[str, str]] = collections.defaultdict(dict)
    for r in records:
        by_arm[r["arm"]].append(r)
        worlds[_world(r)][r["arm"]] = r["status"]
    paired = {w for w, st in worlds.items() if runnable and all(st.get(a) == "VALID" for a in runnable)}
    excluded = [{"world_set": list(w), "invalid_arms": sorted(a for a, x in st.items() if x != "VALID"),
                 "missing_arms": sorted(set(runnable) - set(st))} for w, st in sorted(worlds.items()) if w not in paired]
    arms_out = {}
    for name in arm_names:
        rs = by_arm.get(name, [])
        valid = [r for r in rs if r["status"] == "VALID"]
        clean = [r for r in valid if not any(_is_library_failure(u) for u in r["universes"])]
        measured = [r for r in rs if r["status"] != "WORKER_FAILED"]       # a dead worker measured nothing
        walls = [r["wall_seconds"] for r in measured]
        rss = [r.get("worker_maxrss_kib") for r in measured]
        universes = [u for r in valid for u in r["universes"]]
        on_paired = [r for r in valid if _world(r) in paired]
        per_kind = collections.defaultdict(list)
        for r in on_paired:
            for u in r["universes"]:
                per_kind[u["kind"]].append(u["credit"])
        reasons = collections.Counter(reason[:120] for r in rs for reason in r["reasons"])
        wall_clean = (sum(r["wall_seconds"] for r in clean) / len(clean)) if clean else None
        arms_out[name] = {
            "status": "AVAILABLE" if available[name] else "ARM_UNAVAILABLE",
            "family": (arms_v2.ARMS.get(name) or ARMS_V3.get(name) or MIND_ARMS.get(name) or (None, ""))[1],
            "runs": len(rs), "valid": len(valid), "invalid": sum(r["status"] == "INVALID_BENCHMARK" for r in rs),
            "worker_failures": sum(r["status"] == "WORKER_FAILED" for r in rs),
            "evaluator_disagreement_invalid": sum(any("separate v0.3 evaluator" in x for x in r["reasons"]) for r in rs),
            "invalid_reasons_top": dict(reasons.most_common(5)),
            "not_run": sum(t.arm == name for t in not_run), "interrupted": sum(t.arm == name for t in interrupted),
            "wall_seconds_total": round(sum(walls), 3),
            "wall_seconds_mean_all": round(sum(walls) / len(walls), 4) if walls else None,
            "wall_seconds_max": round(max(walls), 3) if walls else None,
            "cost_basis_runs": len(clean),
            "wall_seconds_mean_clean": round(wall_clean, 4) if wall_clean is not None else None,
            "observe_calls_mean": (round(sum(r["observe_calls"] for r in measured) / len(measured), 2)
                                   if measured else None),
            #: whole-life high-water mark of the pooled workers that ran this arm: not a per-arm memory measurement
            "worker_rss_high_water_kib": ("UNMEASURED" if not rss or any(x is None for x in rss) else max(rss)),
            "inadmissible_universes": sum(u["answer"] == "inadmissible" for u in universes),
            "library_failure_universes": sum(_is_library_failure(u) for u in universes),
            "design_fallback_universes": sum("design fallback" in str(u.get("rationale", "")) for u in universes),
            "unresolved_universes": sum(u["outcome"] == "indistinguishable_unresolved" for u in universes),
            "descriptive_credit": {
                "label": DESCRIPTIVE + "; paired world sets only (every runnable arm VALID there)",
                "paired_world_sets": len({_world(r) for r in on_paired}),
                "paired_mean_total": (round(sum(r["v3_total_credit"] for r in on_paired) / len(on_paired), 4)
                                      if on_paired else None),
                "paired_mean_per_kind": {k: {"mean": round(sum(v) / len(v), 4), "n": len(v)}
                                         for k, v in sorted(per_kind.items())}},
            "formal_cost_estimate_seconds": (round(FORMAL_CAMPAIGNS * wall_clean, 1) if wall_clean is not None else None),
        }
    missing = sorted(name for name in runnable if arms_out[name]["cost_basis_runs"] == 0)
    estimates = [arms_out[n]["formal_cost_estimate_seconds"] for n in runnable
                 if arms_out[n]["formal_cost_estimate_seconds"] is not None]
    worker_failed = sum(r["status"] == "WORKER_FAILED" for r in records)
    pool_rss = [r.get("worker_maxrss_kib") for r in records if r["status"] != "WORKER_FAILED"]
    status = ("INCOMPLETE" if missing else
              "LOWER_BOUND" if (interrupted or worker_failed or missing_records) else "ESTIMATE")
    return {
        "readiness": "DEVELOPMENT_ONLY", "claims": "COST_MEASUREMENT_ONLY", "benchmark_id": "genesis_lite.blindfold_l5.v0_3",
        "design": {"campaigns_per_presentation_per_seed": campaigns, "presentations": list(presentations),
                   "seeds": list(seeds), "workers": workers, "deadline_seconds": deadline},
        "elapsed_seconds": round(elapsed, 2),
        "tasks": {"planned": planned, "completed": len(records) - worker_failed, "worker_failed": worker_failed,
                  "not_run": len(not_run), "interrupted": len(interrupted), "missing_records": missing_records},
        "worker_rss_high_water_kib_pool": ("UNMEASURED" if not pool_rss or any(x is None for x in pool_rss)
                                           else max(pool_rss)),
        "paired_world_sets_complete": len(paired),
        "excluded_world_sets": excluded,
        "arms": arms_out,
        "formal_tier_estimate": {"label": (f"ESTIMATE from the mean wall of clean VALID campaigns, each measured inside one of "
                                           f"{workers} concurrent workers"),
                                 "scope": ("baseline arms only (the arms planned here), in_process isolation; Mind arm UNMEASURED; "
                                           "proposer-process isolation overhead UNMEASURED"),
                                 "status": status, "arms_without_measurement": missing,
                                 "campaigns_per_arm": FORMAL_CAMPAIGNS,
                                 "sum_over_measured_arms_seconds": round(sum(estimates), 1),
                                 "wall_hours_at_4_workers": round(sum(estimates) / 4 / 3600, 2)},
    }


def resummarize(out: pathlib.Path | str, arm_names: Sequence[str] | None = None, **_ignored: Any) -> dict[str, Any]:
    """Recompute a summary from an existing run into summary_resummarized.json; the original summary is kept.

    Design, arm list and availability come from the run's own summary.json, never from this machine or CLI defaults. A
    planned task without a record is ``missing_records`` (cancelled, interrupted and lost are not distinguishable here) and
    makes the estimate a LOWER_BOUND."""
    out = pathlib.Path(out)
    records = [json.loads(line) for line in (out / "runs.jsonl").read_text().splitlines() if line.strip()]
    env = json.loads((out / "environment.json").read_text())
    original = (out / "summary.json").read_bytes()
    recorded = json.loads(original)
    design = recorded["design"]
    names = list(recorded["arms"])
    available = {name: recorded["arms"][name]["status"] == "AVAILABLE" for name in names}
    presentations, seeds = tuple(design["presentations"]), tuple(design["seeds"])
    campaigns = int(design["campaigns_per_presentation_per_seed"])
    tasks = plan([n for n in names if available[n]], campaigns=campaigns, presentations=presentations, seeds=seeds)
    seen = {(r["task"]["arm"], r["task"]["campaign"], r["task"]["presentation"], r["task"]["seed"]) for r in records}
    missing = sum((t.arm, t.campaign, t.presentation, t.seed) not in seen for t in tasks)
    summary = _summarize(names, available, records, [], [], presentations, seeds, campaigns,
                         float(env["elapsed_seconds"]), int(env["workers"]), float(env["deadline_seconds"]),
                         planned=len(tasks), missing_records=missing)
    summary["resummarized_from"] = {
        "runs_jsonl_sha256": hashlib.sha256((out / "runs.jsonl").read_bytes()).hexdigest(),
        "original_summary_sha256": hashlib.sha256(original).hexdigest(),
        "run_git_head": env.get("git_head", "UNKNOWN"),
        "summarizer_git_head": _git_head(),
        "summarizer_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()}
    (out / "summary_resummarized.json").write_text(json.dumps(summary, indent=1, sort_keys=True))
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genesis-lite v0.3 development cost pilot")
    parser.add_argument("--out", required=True)
    parser.add_argument("--arms", default="all")
    parser.add_argument("--campaigns", type=int, default=RUNG)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--deadline-seconds", type=float, default=DEFAULT_DEADLINE)
    parser.add_argument("--resummarize", action="store_true", help="recompute the summary from an existing runs.jsonl")
    args = parser.parse_args(argv)
    names = all_arms() if args.arms == "all" else args.arms.split(",")
    if args.resummarize:
        summary = resummarize(args.out)
    else:
        summary = run_pilot(names, out=args.out, campaigns=args.campaigns, workers=args.workers,
                            deadline_seconds=args.deadline_seconds)
    print(json.dumps({"tasks": summary["tasks"], "elapsed_seconds": summary["elapsed_seconds"],
                      "paired_world_sets_complete": summary["paired_world_sets_complete"]}))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
