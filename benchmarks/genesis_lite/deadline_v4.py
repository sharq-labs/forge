"""Bounded operator processes with atomic result retention at a hard deadline.

Every started task has its own process. Isolated hosts use a parent-death kill
chain, so killing a campaign also kills its namespace launcher and PID namespace.
Completed files are collected AFTER workers stop too: a deadline race never
silently discards a fully written record. Partial records cannot become VALID.
"""
from __future__ import annotations

import json
import math
import multiprocessing as mp
from multiprocessing.connection import wait
import pathlib
import time
from dataclasses import asdict


def _entry(function, arguments, destination):
    try:
        record = function(*arguments)
    except BaseException as exc:
        task = arguments[0]
        record = {"arm": task.arm, "status": "WORKER_FAILED", "task": asdict(task),
                  "reasons": [f"{type(exc).__name__}: {str(exc)[:300]}"]}
    path = pathlib.Path(destination)
    pending = path.with_suffix(".part")
    envelope = {"operator_finished_monotonic": time.monotonic(), "record": record}
    pending.write_text(json.dumps(envelope, sort_keys=True, default=str), encoding="utf-8")
    pending.replace(path)


def completed_record(envelope, cutoff):
    """Keep late output for audit; it cannot count as completed within budget."""
    record = dict(envelope["record"])
    finished = envelope["operator_finished_monotonic"]
    if not isinstance(finished, (float, int)) or not math.isfinite(finished):
        raise ValueError("missing/invalid operator completion time")
    record["completed_within_deadline"] = finished <= cutoff
    if finished > cutoff:
        record["status_before_deadline_classification"] = record["status"]
        record["status"] = "DEADLINE_COMPLETED"
    return record


def execute(function, arguments, *, directory, workers, deadline_seconds, keep):
    if isinstance(workers, bool) or not isinstance(workers, int) or workers < 1:
        raise ValueError("workers must be a positive integer")
    if not math.isfinite(deadline_seconds) or deadline_seconds <= 0:
        raise ValueError("deadline_seconds must be finite and positive")
    directory = pathlib.Path(directory)
    directory.mkdir(exist_ok=False)
    ctx = mp.get_context("spawn")
    start = time.monotonic()
    cutoff = start + deadline_seconds
    active, started, collected = {}, set(), set()
    timed_out = set()

    def collect(index, process):
        path = directory / f"{index}.json"
        if path.exists():
            keep(completed_record(json.loads(path.read_text(encoding="utf-8")), cutoff))
        else:
            task = arguments[index][0]
            keep({"arm": task.arm, "task": asdict(task),
                  "status": "DEADLINE_TERMINATED" if index in timed_out else "WORKER_FAILED",
                  "reasons": ["operator deadline" if index in timed_out else f"worker exit {process.exitcode}"]})
        collected.add(index)

    try:
        while len(collected) < len(arguments):
            for index, process in list(active.items()):
                if not process.is_alive():
                    process.join()
                    collect(index, process)
                    process.close()
                    del active[index]
            remaining = cutoff - time.monotonic()
            if remaining <= 0:
                break
            while len(active) < workers and len(started) < len(arguments) and time.monotonic() < cutoff:
                index = len(started)
                process = ctx.Process(target=_entry, args=(function, arguments[index], str(directory / f"{index}.json")))
                process.start()
                active[index] = process
                started.add(index)
            if not active:
                break
            wait([p.sentinel for p in active.values()], timeout=max(0, cutoff - time.monotonic()))
    finally:
        for index, process in active.items():
            if process.is_alive():
                timed_out.add(index)
                process.kill()
        for index, process in active.items():
            process.join(timeout=5)
            if process.is_alive():
                raise RuntimeError("campaign worker survived SIGKILL; cleanup unverified")
            collect(index, process)
            process.close()
    for index in sorted(set(range(len(arguments))) - started):
        task = arguments[index][0]
        keep({"arm": task.arm, "task": asdict(task), "status": "NOT_STARTED",
              "reasons": ["operator deadline before launch"]})
    return {"started": len(started), "not_run_at_deadline": len(arguments) - len(started),
            "deadline_killed_workers": len(timed_out), "elapsed_seconds": time.monotonic() - start,
            "deadline_seconds": deadline_seconds}
