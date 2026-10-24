"""Record battery_rediscovery_v0 exactly, as history (evaluator side).

    python -m benchmarks.battery_rediscovery_v1.v0_history     # writes V0_HISTORY.json

Nothing in v0 is modified.  The record binds every v0 artifact by sha256 and states its three readings.
"""

from __future__ import annotations

import hashlib
import pathlib

from .candidate.common import write_json

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
V0 = HERE.parent / "battery_rediscovery_v0"


def _sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def record() -> dict:
    groups = {
        "plan": ["PLAN.json", "PLAN.sha256"],
        "candidate_code_and_pack": sorted(str(p.relative_to(V0)).replace("\\", "/") for p in (V0 / "candidate").rglob("*")
                                          if p.is_file() and "__pycache__" not in p.parts),
        "candidate_outputs_and_traces": sorted(f"results/candidate/{p.name}" for p in (V0 / "results" / "candidate").glob("*.json")),
        "seal": ["results/SEAL.json", "results/ACCESS_LOG.json"],
        "leakage_audits": ["results/LEAKAGE_PRE_SEAL.json", "results/LEAKAGE_POST_SEAL.json"],
        "replay": ["results/replay/REPLAY.json", "results/ACCESS_LOG_REPLAY.json"],
        "preregistered_evaluation": ["results/EVALUATION.json", "results/EVALUATION.md"],
        "amendment_01": ["results/AMENDMENT_01.json", "results/EVALUATION_AMENDMENT_01.json",
                         "results/EVALUATION_AMENDMENT_01.md", "results/LEAKAGE_POST_SEAL_AMENDMENT_01.json"],
        "scoring_and_baselines": ["evaluator/score.py", "evaluator/truth.py", "candidate/baselines.py"],
        "leakage_scanner": ["leakage.py"],
    }
    return {"schema": "forge.battery_rediscovery.v0_history/1", "experiment": "battery_rediscovery_v0",
            "PREREGISTERED_RESULT": "LEAKAGE_INVALIDATED",
            "POST_SEAL_AMENDMENT_RESULT": "REPRESENTATION_BOTTLENECK",
            "CONFIRMED_RESULT": "NONE",
            "note": "AMENDMENT_01 is exploratory post-seal evidence only; v1 treats REPRESENTATION_BOTTLENECK as a "
                    "hypothesis (H1), never as a result. v0's leakage.py digest is its AMENDED bytes; its frozen bytes "
                    "are named in v0 results/AMENDMENT_01.json.",
            "commits": {"freeze": "085d9a7c", "seal": "e1be5910", "evaluation": "986cc43c", "amendment_01": "dbf1794c"},
            "files": {g: {f: _sha(V0 / f) for f in fs} for g, fs in groups.items()}}


def main() -> int:
    write_json(HERE / "V0_HISTORY.json", record())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
