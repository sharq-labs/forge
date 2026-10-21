"""Genesis-lite v0.3: the D7 timing pilot (owner, 2026-10-20: measure before the formal budget is approved).

NON-FORMAL, development tier. A fresh synthetic root (never the formal one, which does not exist before the freeze) and
campaign ids of their own (``gl-pilot-<i>``), so no formal world is derived. Every registered v0.3 arm runs every pilot
world set, every card in its own D5 namespace (``isolation.formal_launcher``), exactly as a formal card would.

Before any world set the pilot runs the formal pre-admission check (:func:`.isolation.verify_containers`, the N-1
container evidence with the STATELESS_DEVICE verdicts) and refuses to time anything unless it PASSES: the timing is of
the final container policy only. The check's own duration is MEASURED and reported separately (it runs once per
attempt, before admission).

MEASURED here: seconds per arm per world set on the D7 machine. ESTIMATED from it: the formal attempt's cost =
2,400 world sets x (the run + the evaluator's replay of every record, which re-runs it), with a 95 % interval from the
spread over pilot world sets. The candidate's own cost is NOT included (D4 names it).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import platform
import secrets
import statistics
import subprocess
import sys
import time
from typing import Any

from .. import analysis as v02_analysis
from . import arms as v03_arms
from . import formal, harness, isolation
from .preregistration import DEPLOYMENT_EVIDENCE_SHA256, PREREG_PATH

SCHEMA = "forge.genesis_lite.v0_3/timing_pilot/2"
PRESENTATION = "paraphrased"
REPLAY_FACTOR = 2.0          # the evaluator's verify_attempt re-runs every record once (ASSUMED equal to the run)


def _provenance() -> dict[str, Any]:
    here = pathlib.Path(__file__).resolve().parent

    def git(*args: str) -> str:
        try:
            return subprocess.run(["git", *args], cwd=here, capture_output=True, text=True, check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return "UNKNOWN"

    code = {n: hashlib.sha256((here / n).read_bytes()).hexdigest()
            for n in ("timing_pilot.py", "harness.py", "isolation.py", "arms.py", "container_evidence.py",
                      "container_probe.py", "device_contract.py")}
    return {"head": git("rev-parse", "HEAD"), "tree_clean": git("status", "--porcelain") == "", "code_sha256": code,
            "python": sys.version.split()[0], "platform": platform.platform(), "kernel": platform.release()}


class PilotRefused(RuntimeError):
    """The final container policy did not pass its pre-admission check here: nothing is timed."""


def run(campaigns: int, arms: list[str] | None = None) -> dict[str, Any]:
    launcher = isolation.formal_launcher()
    t_check = time.perf_counter()
    check = isolation.verify_containers(launcher)["validation"]
    check_seconds = time.perf_counter() - t_check
    if check["status"] != "PASS":
        raise PilotRefused(f"the pre-admission container check did not pass: {check['reasons']}")
    doc_bytes = PREREG_PATH.read_bytes()
    binding = harness.bind(doc_bytes, tier="development")
    prereg = hashlib.sha256(doc_bytes).hexdigest()
    root, nonce = secrets.token_bytes(32), secrets.token_hex(16)        # synthetic, never the formal root
    names = arms or sorted(v03_arms.ARMS)
    seconds: dict[str, list[float]] = {a: [] for a in names}
    statuses: dict[str, list[str]] = {a: [] for a in names}
    cards: list[int] = []
    started = time.time()
    for i in range(campaigns):
        cid = f"gl-pilot-{i}"
        master = formal.master_for(root, prereg, nonce, PRESENTATION, cid, 0)
        for arm in names:
            t0 = time.perf_counter()
            rec = harness.run_one(arm, binding=binding, master_seed=master, campaign_id=cid, presentation=PRESENTATION,
                                  seed=0, isolation="proposer_process", launcher=launcher)
            seconds[arm].append(time.perf_counter() - t0)
            statuses[arm].append(rec.status)
            cards.append(len(rec.universes))
            print(f"{cid} {arm} {seconds[arm][-1]:.1f}s {rec.status}", flush=True)
    per_ws = [sum(seconds[a][i] for a in names) for i in range(campaigns)]
    mean = statistics.fmean(per_ws)
    half = 1.96 * statistics.stdev(per_ws) / math.sqrt(campaigns) if campaigns > 1 else float("nan")
    n_ws = len(v02_analysis.FORMAL_GRID)
    return {"schema": SCHEMA, "status": "NON_FORMAL_TIMING_PILOT", "provenance": _provenance(),
            "deployment": launcher.describe(), "deployment_evidence_sha256": DEPLOYMENT_EVIDENCE_SHA256,
            "pre_admission": {"status": check["status"], "devices": check["devices"]},
            "presentation": PRESENTATION, "campaigns": campaigns,
            "arms": names, "cards_per_world_set": sorted(set(cards)),
            "MEASURED": {"seconds_per_arm_per_world_set": {a: {"mean": statistics.fmean(v), "max": max(v)}
                                                           for a, v in seconds.items()},
                         "seconds_per_world_set_all_arms": {"mean": mean, "ci95_half_width": half, "values": per_ws},
                         "statuses": {a: sorted(set(v)) for a, v in statuses.items()},
                         "pre_admission_seconds": round(check_seconds, 1),
                         "wall_seconds": round(time.time() - started, 1)},
            "ESTIMATED": {"formal_world_sets": n_ws, "replay_factor": REPLAY_FACTOR,
                          "formal_hours": mean * n_ws * REPLAY_FACTOR / 3600,
                          "formal_hours_ci95": [(mean - half) * n_ws * REPLAY_FACTOR / 3600,
                                                (mean + half) * n_ws * REPLAY_FACTOR / 3600],
                          "operator_run_hours": mean * n_ws / 3600 + check_seconds / 3600,
                          "pre_admission_hours": check_seconds / 3600,
                          "excludes": "the candidate's own cost (D4); evaluator review time; restarts"}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genesis-lite v0.3 D7 timing pilot (non-formal, development tier)")
    parser.add_argument("--out", type=pathlib.Path, required=True)
    parser.add_argument("--campaigns", type=int, default=10)
    parser.add_argument("--arms", nargs="*", default=None)
    args = parser.parse_args(argv)
    doc = run(args.campaigns, args.arms)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes((json.dumps(doc, indent=1, sort_keys=True) + "\n").encode())
    print(json.dumps({"ESTIMATED": doc["ESTIMATED"], "per_world_set": doc["MEASURED"]["seconds_per_world_set_all_arms"]["mean"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
