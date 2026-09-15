"""Regenerate the frozen K2 61x61 reference grid with K2's own code, for the Phase 6 regression.

    python -X utf8 benchmarks/core_gap_thin_ridge/audit/k2_grid.py --workers 12 --out <scratch>/k2_grid.npz

Nothing here changes K2. The table is built by experiments/kinetics_k2's frozen
builder (every row admitted through the CSTR inference adapter); the posterior
must reproduce the committed k2_report.md numbers before this grid is used as
the "trusted K2 case". The npz is a scratch artifact (points, predictions,
admission mask, and the admission refs needed to rebuild the frozen table).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    from experiments.kinetics_k2 import k2_config as C, k2_forward as F

    means = F.truth_means()
    observations = F.observation_set_from_truth_means(means, seed=C.PRIMARY_SEED, condition_ids=C.MULTI_CONDITION_IDS)
    points = C.parameter_grid()
    t0 = time.perf_counter()
    result = F.build_forward_table_with_stats(points, observations, condition_ids=C.MULTI_CONDITION_IDS, workers=args.workers)
    wall = time.perf_counter() - t0
    table = result.table
    np.savez_compressed(
        args.out, points=table.points, values=table.values, admissible_mask=table.admissible_mask,
        observation_keys=np.asarray(json.dumps(list(table.observation_keys))),
        admission_refs=np.asarray(json.dumps([list(r) for r in table.admission_refs])),
        rejection_reasons=np.asarray(json.dumps(list(table.rejection_reasons))),
        stats=np.asarray(json.dumps({**result.stats.to_dict(), "wall_seconds": wall})),
    )
    print("done", result.stats.to_dict(), round(wall, 1), "s", flush=True)


if __name__ == "__main__":
    main()
