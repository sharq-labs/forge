"""Process-tree resource accounting: CPU, memory, I/O -- and an honest UNSUPPORTED where none exists.

Every metric is a record ``{value, support, method, scope, unit}``. ``support`` is SUPPORTED when the
operating system accounts for the whole process tree exactly, PARTIAL when the number is real but
incomplete (sampled, or only reaped descendants, or one process), and UNSUPPORTED -- with ``value``
None, never zero -- when nothing reliable exists.

Per platform:

* Windows: the child is placed in a Job Object. The kernel then accounts CPU time, I/O transfer
  bytes, process count and peak committed memory for every descendant, including ones that have
  already exited. The job allows breakaway, so a child that asks to leave it still can (and is then
  not counted); no limit is set, so the child behaves exactly as it would unobserved.
* POSIX: ``getrusage(RUSAGE_CHILDREN)`` before and after the run. It covers descendants that were
  reaped by their parents; an orphan re-parented to init is lost, so CPU is PARTIAL.
* Anywhere ``psutil`` is installed: the tree is sampled for resident memory (peak and mean) and
  process counts. Sampling can miss a short spike, so those are PARTIAL.

Network and GPU usage have no reliable process-scoped source in v1 and are always UNSUPPORTED:
machine-wide counters would attribute other programs' traffic to this run.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading

try:  # optional: declared in the [benchmarks] extra
    import psutil
except ImportError:  # pragma: no cover - exercised by monkeypatching to None
    psutil = None

WINDOWS = sys.platform == "win32"
PROCESS_TREE = "PROCESS_TREE"


def record(value, support: str, method: str, *, unit: str, scope: str = PROCESS_TREE, note: str | None = None,
           **extra) -> dict:
    out = {"value": value if support != "UNSUPPORTED" else None, "support": support, "method": method,
           "scope": scope, "unit": unit}
    if note:
        out["note"] = note
    out.update(extra)
    return out


def unsupported(unit: str, note: str) -> dict:
    return record(None, "UNSUPPORTED", "NONE", unit=unit, note=note)


# ---------------------------------------------------------------------------
# Windows Job Object accounting


if WINDOWS:
    import ctypes
    from ctypes import wintypes

    class _IoCounters(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class _BasicAccounting(ctypes.Structure):
        _fields_ = [("TotalUserTime", ctypes.c_longlong), ("TotalKernelTime", ctypes.c_longlong),
                    ("ThisPeriodTotalUserTime", ctypes.c_longlong), ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
                    ("TotalPageFaultCount", wintypes.DWORD), ("TotalProcesses", wintypes.DWORD),
                    ("ActiveProcesses", wintypes.DWORD), ("TotalTerminatedProcesses", wintypes.DWORD)]

    class _BasicAndIoAccounting(ctypes.Structure):
        _fields_ = [("BasicInfo", _BasicAccounting), ("IoInfo", _IoCounters)]

    class _BasicLimit(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class _ExtendedLimit(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", _BasicLimit), ("IoInfo", _IoCounters),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    class _ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

    _JOB_BASIC_AND_IO_ACCOUNTING = 8
    _JOB_EXTENDED_LIMIT = 9
    _JOB_LIMIT_BREAKAWAY_OK = 0x00000800

    def _kernel32():
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        k32.AssignProcessToJobObject.restype = wintypes.BOOL
        k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
        k32.SetInformationJobObject.restype = wintypes.BOOL
        k32.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
                                                  wintypes.LPDWORD]
        k32.QueryInformationJobObject.restype = wintypes.BOOL
        k32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        k32.TerminateJobObject.restype = wintypes.BOOL
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        k32.CloseHandle.restype = wintypes.BOOL
        k32.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
        k32.K32GetProcessMemoryInfo.restype = wintypes.BOOL
        return k32

    class _WindowsJob:
        """An accounting-only Job Object around the child: no limits, breakaway still allowed."""

        def __init__(self) -> None:
            self._k32 = _kernel32()
            self.handle = self._k32.CreateJobObjectW(None, None)
            if not self.handle:
                raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
            limits = _ExtendedLimit()
            limits.BasicLimitInformation.LimitFlags = _JOB_LIMIT_BREAKAWAY_OK
            self._k32.SetInformationJobObject(self.handle, _JOB_EXTENDED_LIMIT, ctypes.byref(limits),
                                              ctypes.sizeof(limits))

        def assign(self, process_handle: int) -> None:
            if not self._k32.AssignProcessToJobObject(self.handle, process_handle):
                raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject failed")

        def accounting(self) -> tuple[_BasicAndIoAccounting, _ExtendedLimit]:
            basic, extended = _BasicAndIoAccounting(), _ExtendedLimit()
            for cls, buf in ((_JOB_BASIC_AND_IO_ACCOUNTING, basic), (_JOB_EXTENDED_LIMIT, extended)):
                if not self._k32.QueryInformationJobObject(self.handle, cls, ctypes.byref(buf), ctypes.sizeof(buf),
                                                           None):
                    raise OSError(ctypes.get_last_error(), "QueryInformationJobObject failed")
            return basic, extended

        def peak_working_set(self, process_handle: int) -> int | None:
            counters = _ProcessMemoryCounters(cb=ctypes.sizeof(_ProcessMemoryCounters))
            if self._k32.K32GetProcessMemoryInfo(process_handle, ctypes.byref(counters), counters.cb):
                return int(counters.PeakWorkingSetSize)
            return None

        def terminate(self, exit_code: int = 1) -> None:
            self._k32.TerminateJobObject(self.handle, exit_code)

        def close(self) -> None:
            if self.handle:
                self._k32.CloseHandle(self.handle)
                self.handle = None


# ---------------------------------------------------------------------------
# The monitor


class ProcessTreeMonitor:
    """Accounts for one child and all its descendants from just before start to just after exit."""

    def __init__(self, sample_interval: float = 0.1) -> None:
        self.sample_interval = sample_interval
        self._job = None
        self._job_error: str | None = None
        self._rusage_before = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._samples = 0
        self._rss_sum = 0
        self._rss_peak: int | None = None
        self._max_procs = 0
        self._pids: set[tuple[int, float]] = set()
        self._psutil = psutil

    def before_start(self) -> None:
        if not WINDOWS:
            import resource

            self._rusage_before = resource.getrusage(resource.RUSAGE_CHILDREN)

    def attach(self, proc: subprocess.Popen) -> None:
        self._proc = proc
        if WINDOWS:
            try:
                self._job = _WindowsJob()
                self._job.assign(int(proc._handle))  # noqa: SLF001 - Popen keeps the only process handle
            except (OSError, AttributeError) as exc:
                self._job_error = str(exc)
                if self._job is not None:
                    self._job.close()
                self._job = None
        if self._psutil is not None:
            self._sample()
            self._thread = threading.Thread(target=self._sample_loop, name="run-observatory-sampler", daemon=True)
            self._thread.start()

    def _sample_loop(self) -> None:
        while not self._stop.wait(self.sample_interval):
            self._sample()

    def _sample(self) -> None:
        try:
            root = self._psutil.Process(self._proc.pid)
            procs = [root, *root.children(recursive=True)]
        except Exception:  # noqa: BLE001 - the tree may vanish between any two calls
            return
        total, alive = 0, 0
        for proc in procs:
            try:
                total += proc.memory_info().rss
                self._pids.add((proc.pid, proc.create_time()))
                alive += 1
            except Exception:  # noqa: BLE001
                continue
        if alive:
            self._samples += 1
            self._rss_sum += total
            self._rss_peak = total if self._rss_peak is None else max(self._rss_peak, total)
            self._max_procs = max(self._max_procs, alive)

    def terminate_tree(self) -> None:
        """Stop the child and, where the OS can, every descendant with it."""
        if self._job is not None:
            self._job.terminate()
        elif self._proc.poll() is None:
            self._proc.kill()

    def finish(self) -> dict:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        try:
            return self._resources()
        finally:
            if self._job is not None:
                self._job.close()

    # -- assembly -----------------------------------------------------------

    def _resources(self) -> dict:
        cpu = io_read = io_write = processes = commit = None
        peaks: list[tuple[int, str]] = []
        if self._job is not None:
            try:
                basic, extended = self._job.accounting()
                user = basic.BasicInfo.TotalUserTime / 1e7
                system = basic.BasicInfo.TotalKernelTime / 1e7
                cpu = record(user + system, "SUPPORTED", "WINDOWS_JOB_OBJECT", unit="seconds",
                             user=user, system=system)
                note = "all I/O transfers of the tree: files, pipes and devices"
                io_read = record(int(basic.IoInfo.ReadTransferCount), "SUPPORTED", "WINDOWS_JOB_OBJECT",
                                 unit="bytes", note=note)
                io_write = record(int(basic.IoInfo.WriteTransferCount), "SUPPORTED", "WINDOWS_JOB_OBJECT",
                                  unit="bytes", note=note)
                processes = record(int(basic.BasicInfo.TotalProcesses), "SUPPORTED", "WINDOWS_JOB_OBJECT",
                                   unit="processes")
                commit = record(int(extended.PeakJobMemoryUsed), "SUPPORTED", "WINDOWS_JOB_OBJECT", unit="bytes",
                                note="peak committed (private) memory of the whole tree at once; not RSS")
                child_peak = self._job.peak_working_set(int(self._proc._handle))  # noqa: SLF001
                if child_peak is not None:
                    peaks.append((child_peak, "DIRECT_CHILD_PEAK_WORKING_SET"))
            except OSError as exc:
                self._job_error = str(exc)
        elif not WINDOWS and self._rusage_before is not None:
            import resource

            after = resource.getrusage(resource.RUSAGE_CHILDREN)
            before = self._rusage_before
            user, system = after.ru_utime - before.ru_utime, after.ru_stime - before.ru_stime
            orphan = "descendants re-parented to init before being reaped are not counted"
            cpu = record(user + system, "PARTIAL", "GETRUSAGE_CHILDREN_DELTA", unit="seconds", note=orphan,
                         user=user, system=system)
            blocks = "block-device I/O of reaped descendants in 512-byte blocks; page-cache hits are not counted"
            io_read = record((after.ru_inblock - before.ru_inblock) * 512, "PARTIAL", "GETRUSAGE_CHILDREN_DELTA",
                             unit="bytes", note=blocks)
            io_write = record((after.ru_oublock - before.ru_oublock) * 512, "PARTIAL", "GETRUSAGE_CHILDREN_DELTA",
                              unit="bytes", note=blocks)
            if after.ru_maxrss > before.ru_maxrss:
                scale = 1 if sys.platform == "darwin" else 1024
                peaks.append((after.ru_maxrss * scale, "GETRUSAGE_LARGEST_SINGLE_DESCENDANT"))

        if self._rss_peak is not None:
            peaks.append((self._rss_peak, "PSUTIL_SAMPLED_TREE_SUM"))
        sampling = {"samples": self._samples, "interval_seconds": self.sample_interval}
        resources = {
            "cpu_seconds": cpu or unsupported("seconds", self._why_unsupported()),
            "peak_rss_bytes": (record(max(v for v, _ in peaks), "PARTIAL", "+".join(m for _, m in peaks), unit="bytes",
                                      note="a sampled tree sum can miss a short spike; a single-process peak "
                                           "ignores the rest of the tree", **sampling)
                               if peaks else unsupported("bytes", self._why_unsupported())),
            "avg_rss_bytes": (record(self._rss_sum / self._samples, "PARTIAL", "PSUTIL_SAMPLED_TREE_SUM",
                                     unit="bytes", **sampling)
                              if self._samples else unsupported("bytes", "psutil is not installed; nothing sampled")),
            "peak_tree_commit_bytes": commit or unsupported("bytes", "only a Windows Job Object accounts it"),
            "io_read_bytes": io_read or unsupported("bytes", self._why_unsupported()),
            "io_write_bytes": io_write or unsupported("bytes", self._why_unsupported()),
            "process_count": processes or (
                record(len(self._pids), "PARTIAL", "PSUTIL_SAMPLED_DISTINCT_PIDS", unit="processes", **sampling)
                if self._pids else unsupported("processes", self._why_unsupported())),
            "network_bytes": unsupported("bytes", "no reliable process-scoped network accounting in v1; "
                                                  "machine-wide counters would misattribute other traffic"),
            "gpu_utilization": unsupported("fraction", "no reliable process-scoped GPU accounting in v1"),
        }
        if self._job_error:
            resources["cpu_seconds"].setdefault("note", f"job object unavailable: {self._job_error}")
        return resources

    def _why_unsupported(self) -> str:
        if WINDOWS and self._job_error:
            return f"Windows Job Object unavailable ({self._job_error})"
        return "no accounting source available on this platform"


def pid_alive(pid: int) -> bool:
    """Whether a process with this id is still running (used to leave live runs' pending receipts alone).

    On Windows a terminated process stays listed while anyone holds a handle to it, so its exit
    code is read instead of its presence.
    """
    if WINDOWS:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, wintypes.LPDWORD]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = wintypes.DWORD()
        k32.GetExitCodeProcess(handle, ctypes.byref(code))
        k32.CloseHandle(handle)
        return code.value == 259  # STILL_ACTIVE
    if psutil is not None:
        try:
            return psutil.pid_exists(pid) and psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
        except Exception:  # noqa: BLE001
            return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
