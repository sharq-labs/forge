"""A deadline kills running work, retains completions and accounts for every task."""
import time
from dataclasses import asdict

import pytest

from benchmarks.genesis_lite.deadline_v4 import completed_record, execute
from benchmarks.genesis_lite.pilot_v4 import Task


def _sleep_task(task, seconds):
    time.sleep(seconds)
    return {"arm": task.arm, "task": asdict(task), "status": "VALID"}


def test_deadline_terminates_running_work_and_keeps_completed_and_pending(tmp_path):
    tasks = [(Task("careful", i, "anonymous", 0), 0.01 if i == 0 else 60) for i in range(3)]
    records = []
    before = time.monotonic()
    result = execute(_sleep_task, tasks, directory=tmp_path / "records", workers=1, deadline_seconds=3, keep=records.append)
    assert time.monotonic() - before < 8
    assert [r["status"] for r in records] == ["VALID", "DEADLINE_TERMINATED", "NOT_STARTED"]
    assert {r["task"]["campaign"] for r in records} == {0, 1, 2}
    assert result["deadline_killed_workers"] == 1
    assert result["not_run_at_deadline"] == 1


def test_no_record_is_dropped_when_all_finish(tmp_path):
    records = []
    tasks = [(Task("careful", i, "anonymous", 0), 0) for i in range(5)]
    result = execute(_sleep_task, tasks, directory=tmp_path / "records", workers=2, deadline_seconds=20, keep=records.append)
    assert len(records) == 5 and all(r["status"] == "VALID" for r in records)
    assert result["deadline_killed_workers"] == result["not_run_at_deadline"] == 0


@pytest.mark.parametrize("deadline", [0, -1, float("nan"), float("inf")])
def test_invalid_deadlines_refuse_before_starting(tmp_path, deadline):
    with pytest.raises(ValueError, match="finite and positive"):
        execute(_sleep_task, [], directory=tmp_path / "records", workers=1, deadline_seconds=deadline, keep=lambda r: None)


def test_a_completed_record_in_the_cutoff_race_is_retained_but_never_valid():
    original = {"status": "VALID", "total_credit": 6}
    late = completed_record({"record": original, "operator_finished_monotonic": 10.001}, 10.0)
    assert late["status"] == "DEADLINE_COMPLETED"
    assert late["total_credit"] == 6 and not late["completed_within_deadline"]
    assert late["status_before_deadline_classification"] == "VALID"
    on_time = completed_record({"record": original, "operator_finished_monotonic": 9.999}, 10.0)
    assert on_time["status"] == "VALID" and on_time["completed_within_deadline"]
