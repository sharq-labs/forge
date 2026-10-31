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


def test_reused_pid_cannot_contribute_memory_threads_or_loaded_images(tmp_path, monkeypatch):
    process = tmp_path / "10"
    process.mkdir()
    (process / "status").write_text("VmRSS: 999999 kB\nThreads: 99\n")
    (process / "smaps_rollup").write_text("Pss: 888888 kB\n")
    (process / "maps").write_text("0-1 r-x 0 0 0 /opt/forge-sysimage-unrelated.so\n")
    monkeypatch.setattr(telemetry, "PROC", tmp_path)
    starts = iter(("root", "old", "new"))
    monkeypatch.setattr(telemetry, "start_time", lambda pid: next(starts))
    monkeypatch.setattr(telemetry, "tree_pids", lambda pid: [10])
    sampler = object.__new__(telemetry.ProcessSampler)
    sampler.pid, sampler.root_start_time = 10, "root"
    sampler.peaks = dict.fromkeys(("rss_kib", "pss_kib", "threads", "processes"), 0)
    sampler.samples = sampler.incomplete = sampler.pss_observations = 0
    sampler.sysimages = set()
    sampler.sample()
    assert not any(sampler.peaks.values()) and not sampler.sysimages
    assert sampler.pss_observations == 0 and sampler.incomplete == 1
