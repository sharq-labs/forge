"""Run every arm on the pack and write one output per (arm, problem); or re-run them to check replay.

    python -m benchmarks.battery_rediscovery_v0.candidate.run --out <dir>
    python -m benchmarks.battery_rediscovery_v0.candidate.run --replay <dir with the sealed outputs> --out <dir>

Only the pack and this package are read.  The timing of each arm goes to TIMINGS.json, outside every digest.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import time

from . import baselines, mind_arm
from .common import PACK_DIR, digest, load_pack, write_json

ARM_ORDER = ("MIND", "FIXED_FIT", "CAREFUL_BASELINE", "ALWAYS_FIT", "ALWAYS_REFUSE")


def run_all(out: pathlib.Path, pack: pathlib.Path = PACK_DIR) -> dict[str, str]:
    problems = load_pack(pack)
    written, timings = {}, {}
    for pid, problem in problems.items():
        for arm in ARM_ORDER:
            t0 = time.perf_counter()
            if arm == "MIND":
                traces: dict = {}
                rec = mind_arm.mind(problem, traces=traces)
                written[f"MIND_TRACES__{pid}.json"] = write_json(out / f"MIND_TRACES__{pid}.json", traces)
            else:
                rec = baselines.ARMS[arm](problem)
            timings[f"{arm}__{pid}"] = round(time.perf_counter() - t0, 3)
            written[f"{arm}__{pid}.json"] = write_json(out / f"{arm}__{pid}.json", rec)
    write_json(out / "TIMINGS.json", timings)
    return written


def replay_all(sealed: pathlib.Path, out: pathlib.Path, pack: pathlib.Path = PACK_DIR) -> dict[str, object]:
    """Re-execute every arm from the sealed inputs and compare the content digests; replay every Mind trace."""
    problems = load_pack(pack)
    report: dict[str, object] = {"arms": {}, "mind_traces": {}}
    for pid, problem in problems.items():
        for arm in ARM_ORDER:
            name = f"{arm}__{pid}.json"
            before = json.loads((sealed / name).read_bytes())
            traces: dict = {}
            again = mind_arm.mind(problem, traces=traces) if arm == "MIND" else baselines.ARMS[arm](problem)
            again = json.loads(json.dumps(again))
            if arm == "MIND":
                tname = f"MIND_TRACES__{pid}.json"
                sealed_t = json.loads((sealed / tname).read_bytes())
                report["arms"][tname] = {"identical": digest(sealed_t) == digest(json.loads(json.dumps(traces))),
                                         "sealed_digest": digest(sealed_t)}
            report["arms"][name] = {"identical": digest(before) == digest(again), "sealed_digest": digest(before),
                                    "rerun_digest": digest(again)}
        sealed_traces = json.loads((sealed / f"MIND_TRACES__{pid}.json").read_bytes())
        report["mind_traces"][pid] = mind_arm.replay_traces(problem, sealed_traces)
    write_json(out / "REPLAY.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=pathlib.Path)
    ap.add_argument("--replay", type=pathlib.Path, default=None)
    ap.add_argument("--pack", type=pathlib.Path, default=PACK_DIR, help="a pack directory (default: the frozen pack)")
    a = ap.parse_args(argv)
    if a.replay is not None:
        replay_all(a.replay, a.out, a.pack)
    else:
        run_all(a.out, a.pack)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
