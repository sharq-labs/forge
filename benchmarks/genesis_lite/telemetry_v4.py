"""Operator-side Linux process telemetry. Diagnostic only, never scoring/evidence.

Memory peaks are sampled lower bounds (RSS double-counts shared pages; PSS does
not). CPU/fault totals use wait-accounted RUSAGE_CHILDREN deltas in the exclusive
campaign worker. No proposer clock or resource claim is used.
"""
from __future__ import annotations

import pathlib
import threading

PROC = pathlib.Path("/proc")


def start_time(pid):
    return (PROC / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()[19]


def tree_pids(pid: int) -> list[int]:
    found, pending = [], [pid]
    while pending:
        current = pending.pop()
        if current in found:
            continue
        found.append(current)
        try:
            for task in (PROC / str(current) / "task").iterdir():
                pending.extend(int(p) for p in (task / "children").read_text().split())
        except (OSError, ValueError):
            pass
    return found


def usage():
    import resource
    r = resource.getrusage(resource.RUSAGE_CHILDREN)
    return {"cpu_user_seconds": r.ru_utime, "cpu_system_seconds": r.ru_stime,
            "minor_faults": r.ru_minflt, "major_faults": r.ru_majflt}


class ProcessSampler:
    def __init__(self, pid: int, interval: float = 0.1):
        self.pid, self.interval = pid, interval
        self.root_start_time = start_time(pid)
        self.peaks = dict.fromkeys(("rss_kib", "pss_kib", "threads", "processes"), 0)
        self.samples, self.incomplete = 0, 0
        self.pss_observations = 0
        self.sysimages: set[str] = set()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def sample(self):
        totals = dict.fromkeys(self.peaks, 0)
        try:
            if start_time(self.pid) != self.root_start_time:
                return  # PID reuse after the tracked root exits is not our tree
        except OSError:
            return
        for pid in tree_pids(self.pid):
            try:
                born = start_time(pid)
                status = dict(line.split(":", 1) for line in (PROC / str(pid) / "status").read_text().splitlines())
                rss, threads = int(status.get("VmRSS", "0 kB").split()[0]), int(status["Threads"])
                rollup = (PROC / str(pid) / "smaps_rollup").read_text().splitlines()
                pss = sum(int(line.split()[1]) for line in rollup if line.startswith("Pss:"))
                mapped = set()
                for line in (PROC / str(pid) / "maps").read_text().splitlines():
                    path = line.split()[-1]
                    if path.startswith("/") and (path.endswith("/sys.so") or "forge-sysimage" in path):
                        mapped.add(path)
                if start_time(pid) != born:
                    self.incomplete += 1
                    continue
                totals["rss_kib"] += rss
                totals["threads"] += threads
                totals["processes"] += 1
                totals["pss_kib"] += pss
                self.pss_observations += 1
                self.sysimages.update(mapped)
            except (OSError, ValueError, KeyError):
                self.incomplete += 1
        for k, v in totals.items():
            self.peaks[k] = max(self.peaks[k], v)
        self.samples += 1

    def _run(self):
        while not self.stop_event.is_set():
            self.sample()
            self.stop_event.wait(self.interval)

    def close(self):
        self.stop_event.set()
        self.thread.join(timeout=5)
        peaks = dict(self.peaks)
        if not self.pss_observations:
            peaks["pss_kib"] = None
        return {"sample_interval_seconds": self.interval, "sampled_peak": peaks,
                "samples": self.samples, "incomplete_process_samples": self.incomplete,
                "mapped_sysimages": sorted(self.sysimages), "memory_peak_is_lower_bound": True}
