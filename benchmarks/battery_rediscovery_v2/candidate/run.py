"""Run every arm on the pack and write one output per (arm, problem); or re-execute them to check replay.

    python -m benchmarks.battery_rediscovery_v2.candidate.run --out <dir>
    python -m benchmarks.battery_rediscovery_v2.candidate.run --replay <dir with the sealed outputs> --out <dir>

Only the pack and the candidate code are read.  Outputs are opened for WRITING only during a run (the runtime audit
refuses any read of an output path), so no arm can see another arm's answers.  The timing of each arm goes to
TIMINGS.json, outside every digest.

Replay re-executes every arm from the pack and compares content digests; it also replays every OLD_MIND trace through
v1's ``replay_traces`` and every repsem assessment through ``engcore.mind.repsem.replay`` (which re-assesses under the
recorded roles and requires byte identity).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import time
from typing import Any

from benchmarks.battery_rediscovery_v1.candidate import mind_arm as v1
from engcore.mind.repsem import ReplayMismatch, replay

from . import arms
from .common import PACK_DIR, digest, load_pack, write_json
from .views import v1_problem

REPSEM_ARMS = ("REPRESENTATION_ONLY", "REPRESENTATION_PLUS_ROLES")


def _execute(arm: str, spec: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if arm == "OLD_MIND":
        traces: dict[str, Any] = {}
        return arms.old_mind(spec, traces=traces), traces
    return arms.RUN[arm](spec), None


def run_all(out: pathlib.Path, pack: pathlib.Path = PACK_DIR) -> dict[str, str]:
    problems = load_pack(pack)
    written, timings = {}, {}
    for pid, spec in problems.items():
        for arm in arms.ALL_ARMS:
            t0 = time.perf_counter()
            rec, traces = _execute(arm, spec)
            timings[f"{arm}__{pid}"] = round(time.perf_counter() - t0, 3)
            if traces is not None:
                written[f"OLD_MIND_TRACES__{pid}.json"] = write_json(out / f"OLD_MIND_TRACES__{pid}.json", traces)
            written[f"{arm}__{pid}.json"] = write_json(out / f"{arm}__{pid}.json", rec)
            print(f"{pid} {arm:26s} {timings[f'{arm}__{pid}']:9.1f}s", flush=True)
    write_json(out / "TIMINGS.json", timings)
    return written


def replay_all(sealed: pathlib.Path, out: pathlib.Path, pack: pathlib.Path = PACK_DIR) -> dict[str, Any]:
    problems = load_pack(pack)
    report: dict[str, Any] = {"arms": {}, "old_mind_traces": {}, "repsem_assessments": {}}
    for pid, spec in problems.items():
        for arm in arms.ALL_ARMS:
            name = f"{arm}__{pid}.json"
            before = json.loads((sealed / name).read_bytes())
            if arm in REPSEM_ARMS:
                # one re-execution: repsem.replay re-assesses under the recorded roles and compares bytes; the arm's
                # answers are then re-derived from that byte-identical record
                try:
                    status = replay(before["assessment"], spec, arms.families_for(spec))
                except ReplayMismatch as exc:
                    status = {"status": "MISMATCH", "why": str(exc)}
                report["repsem_assessments"][name] = status
                rebuilt = arms._record(arm, spec, {a: arms._claim_answer(c) for a, c in _claims(before).items()},
                                       roles=before["roles"], assessment=before["assessment"])
                again = json.loads(json.dumps(rebuilt)) if status.get("status") == "EXACT" else {"replay": "MISMATCH"}
            else:
                again, traces = _execute(arm, spec)
                again = json.loads(json.dumps(again))
                if traces is not None:
                    tname = f"OLD_MIND_TRACES__{pid}.json"
                    sealed_t = json.loads((sealed / tname).read_bytes())
                    report["arms"][tname] = {"identical": digest(sealed_t) == digest(json.loads(json.dumps(traces))),
                                             "sealed_digest": digest(sealed_t)}
                    report["old_mind_traces"][pid] = v1.replay_traces(v1_problem(spec), sealed_t)
            report["arms"][name] = {"identical": digest(before) == digest(again), "sealed_digest": digest(before),
                                    "rerun_digest": digest(again)}
            print(f"replay {pid} {arm:26s} {report['arms'][name]['identical']}", flush=True)
    write_json(out / "REPLAY.json", report)
    return report


def _claims(record: dict[str, Any]) -> dict[str, Any]:
    from engcore.mind.repsem.claims import ScopedClaim  # noqa: PLC0415

    return {k: ScopedClaim.from_dict(v) for k, v in record["assessment"]["claims"].items()}


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
