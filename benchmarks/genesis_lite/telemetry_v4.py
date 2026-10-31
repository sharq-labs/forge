"""Operator-side Linux process telemetry. Diagnostic only, never scoring/evidence.

Memory peaks are sampled lower bounds (RSS double-counts shared pages; PSS does
not). CPU/fault totals use wait-accounted RUSAGE_CHILDREN deltas in the exclusive
campaign worker. No proposer clock or resource claim is used.
"""
from __future__ import annotations

import pathlib
import threading
import time


def tree_pids(pid: int) -> list[int]:
    found, pending = [], [pid]
    while pending:
        current = pending.pop()
        if current in found:
            continue
        found.append(current)
        try:
            pending.extend(int(p) for p in pathlib.Path(f"/proc/{current}/task/{current}/children").read_text().split())
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
        self.peaks = dict.fromkeys(("rss_kib", "pss_kib", "threads", "processes"), 0)
        self.samples, self.incomplete = 0, 0
        self.sysimages: set[str] = set()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def sample(self):
        totals = dict.fromkeys(self.peaks, 0)
        for pid in tree_pids(self.pid):
            try:
                status = dict(line.split(":", 1) for line in pathlib.Path(f"/proc/{pid}/status").read_text().splitlines())
                totals["rss_kib"] += int(status.get("VmRSS", "0 kB").split()[0])
                totals["threads"] += int(status["Threads"])
                totals["processes"] += 1
                rollup = pathlib.Path(f"/proc/{pid}/smaps_rollup").read_text().splitlines()
                totals["pss_kib"] += sum(int(line.split()[1]) for line in rollup if line.startswith("Pss:"))
                for line in pathlib.Path(f"/proc/{pid}/maps").read_text().splitlines():
                    path = line.split()[-1]
                    if path.startswith("/") and (path.endswith("/sys.so") or "forge-sysimage" in path):
                        self.sysimages.add(path)
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
        return {"sample_interval_seconds": self.interval, "sampled_peak": self.peaks,
                "samples": self.samples, "incomplete_process_samples": self.incomplete,
                "mapped_sysimages": sorted(self.sysimages), "memory_peak_is_lower_bound": True}
