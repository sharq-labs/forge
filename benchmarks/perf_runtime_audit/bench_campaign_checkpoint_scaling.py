"""PERF-0 — how campaign checkpoint cost scales with campaign length.

The suspicion under test: ``CampaignCheckpoint`` carries a whole
``CampaignEventLog``, and ``CheckpointStore`` keeps every checkpoint, so the
store holds history 1..N1, 1..N2, 1..N3 ... and both serialization and
hash-chain verification become quadratic in the number of checkpoints.

Nothing scientific runs here. The campaign state is synthetic, deterministic and
built directly, so this measures the *storage and verification machinery* rather
than any solver.

    python benchmarks/perf_runtime_audit/bench_campaign_checkpoint_scaling.py
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.engcore.sria.campaign.budget import BudgetLedger  # noqa: E402
from src.engcore.sria.campaign.checkpoint import (  # noqa: E402
    CampaignCheckpoint,
    CheckpointStore,
    EffectLedger,
)
from src.engcore.sria.campaign.events import (  # noqa: E402
    CampaignEventLog,
    CampaignEventType,
)
from src.engcore.sria.campaign.state import CampaignRun, ExecutionState  # noqa: E402

RUN_ID = "perf-campaign"

#: Events appended per simulated iteration. The runner writes many events per
#: iteration; four keeps the synthetic log honest about growing faster than the
#: checkpoint count without pretending to reproduce the runner exactly.
EVENTS_PER_CHECKPOINT = 4


def _run_state(iteration: int, max_iterations: int) -> CampaignRun:
    return CampaignRun(
        run_id=RUN_ID,
        campaign_id="perf-campaign-id",
        charter_version="perf-1",
        state=ExecutionState.UPDATING,
        iteration=iteration,
        max_iterations=max_iterations,
    )


def build_store(n_checkpoints: int) -> tuple[CheckpointStore, dict[str, float]]:
    """Append ``n_checkpoints`` checkpoints, timing each save individually."""
    log = CampaignEventLog(run_id=RUN_ID)
    store = CheckpointStore()
    save_times: list[float] = []
    first_save = 0.0
    last_save = 0.0

    for index in range(n_checkpoints):
        for kind in range(EVENTS_PER_CHECKPOINT):
            log.append(
                CampaignEventType.ITERATION_COMPLETED,
                iteration=index,
                payload={"iteration": index, "slot": kind},
                at="",
            )
        started = time.perf_counter()
        checkpoint = CampaignCheckpoint(
            run=_run_state(index, max(n_checkpoints, 1)),
            events=CampaignEventLog(run_id=RUN_ID, events=log.events),
            budget=BudgetLedger(total_budget=1000.0),
            effects=EffectLedger(),
        )
        store.save(checkpoint)
        elapsed = time.perf_counter() - started
        save_times.append(elapsed)
        if index == 0:
            first_save = elapsed
        last_save = elapsed

    return store, {
        "total_build_s": sum(save_times),
        "first_save_s": first_save,
        "last_save_s": last_save,
        "median_save_s": statistics.median(save_times),
    }


def measure(
    n_checkpoints: int, tmpdir: Path, *, full_serialize: bool = True
) -> dict[str, Any]:
    """Measure one campaign length.

    ``full_serialize=False`` skips whole-store serialization and reload. At a
    thousand checkpoints the store's JSON is most of a gigabyte, and
    materializing it measures this machine's memory pressure rather than the
    scaling law. The per-checkpoint save latency and the stored-record count
    are still exact, and they are what establish the law.
    """
    store, build = build_store(n_checkpoints)

    if not full_serialize:
        latest = store.latest()
        head_blob = json.dumps(latest.to_dict(), sort_keys=True, indent=2)
        started = time.perf_counter()
        latest.events.verify_chain()
        verify_head_s = time.perf_counter() - started
        return {
            "checkpoints": n_checkpoints,
            "events_in_head_log": len(latest.events),
            "total_event_records_stored": sum(
                len(c.events) for c in store.history
            ),
            "head_checkpoint_bytes": len(head_blob.encode("utf-8")),
            "serialized_bytes": None,
            "on_disk_bytes": None,
            "build_and_save_s": build,
            "to_dict_s": None,
            "json_dumps_s": None,
            "save_to_path_s": None,
            "load_from_path_s": None,
            "verify_chain_head_s": verify_head_s,
            "verify_chain_all_checkpoints_s": None,
            "full_serialize_skipped": True,
        }

    started = time.perf_counter()
    payload = store.to_dict()
    to_dict_s = time.perf_counter() - started

    started = time.perf_counter()
    blob = json.dumps(payload, sort_keys=True, indent=2)
    dumps_s = time.perf_counter() - started

    target = tmpdir / f"store-{n_checkpoints}.json"
    started = time.perf_counter()
    store.save_to_path(target)
    save_to_path_s = time.perf_counter() - started

    started = time.perf_counter()
    reloaded = CheckpointStore.load_from_path(target)
    load_s = time.perf_counter() - started

    latest = reloaded.latest()
    started = time.perf_counter()
    latest.events.verify_chain()
    verify_head_s = time.perf_counter() - started

    started = time.perf_counter()
    for checkpoint in reloaded.history:
        checkpoint.events.verify_chain()
    verify_all_s = time.perf_counter() - started

    total_events_stored = sum(len(c.events) for c in reloaded.history)

    return {
        "checkpoints": n_checkpoints,
        "events_in_head_log": len(latest.events),
        "total_event_records_stored": total_events_stored,
        "serialized_bytes": len(blob.encode("utf-8")),
        "on_disk_bytes": target.stat().st_size,
        "build_and_save_s": build,
        "to_dict_s": to_dict_s,
        "json_dumps_s": dumps_s,
        "save_to_path_s": save_to_path_s,
        "load_from_path_s": load_s,
        "verify_chain_head_s": verify_head_s,
        "verify_chain_all_checkpoints_s": verify_all_s,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sizes", type=int, nargs="+", default=[10, 100, 300]
    )
    parser.add_argument(
        "--light-sizes",
        type=int,
        nargs="*",
        default=[1000],
        help="sizes measured without whole-store serialization",
    )
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        for size in args.sizes:
            row = measure(size, tmpdir, full_serialize=True)
            rows.append(row)
            print(
                f"n={size:5d} "
                f"head_events={row['events_in_head_log']:6d} "
                f"stored_records={row['total_event_records_stored']:9d} "
                f"bytes={row['serialized_bytes']:11d} "
                f"build={row['build_and_save_s']['total_build_s']:8.3f}s "
                f"last_save={row['build_and_save_s']['last_save_s']:7.4f}s "
                f"to_dict={row['to_dict_s']:7.3f}s "
                f"load={row['load_from_path_s']:7.3f}s",
                flush=True,
            )
        for size in args.light_sizes or ():
            row = measure(size, tmpdir, full_serialize=False)
            rows.append(row)
            print(
                f"n={size:5d} "
                f"head_events={row['events_in_head_log']:6d} "
                f"stored_records={row['total_event_records_stored']:9d} "
                f"head_bytes={row['head_checkpoint_bytes']:11d} "
                f"build={row['build_and_save_s']['total_build_s']:8.3f}s "
                f"last_save={row['build_and_save_s']['last_save_s']:7.4f}s "
                f"(whole-store serialization skipped)",
                flush=True,
            )

    payload = {"events_per_checkpoint": EVENTS_PER_CHECKPOINT, "rows": rows}
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
