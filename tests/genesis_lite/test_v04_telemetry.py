"""The process walk includes children spawned by every thread, without Linux-only skips."""
from benchmarks.genesis_lite import telemetry_v4 as telemetry


def test_children_of_secondary_threads_are_walked(tmp_path, monkeypatch):
    for pid, tids in ((10, (10, 11)), (20, (20,)), (30, (30,))):
        for tid in tids:
            task = tmp_path / str(pid) / "task" / str(tid)
            task.mkdir(parents=True)
            (task / "children").write_text("20" if tid == 11 else "30" if tid == 20 else "")
    monkeypatch.setattr(telemetry, "PROC", tmp_path)
    assert set(telemetry.tree_pids(10)) == {10, 20, 30}
