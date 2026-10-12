"""``forge_check --workers safe-auto``: a developer-only worker count from this machine's resources.

Developer convenience, never policy. CI keeps ``-n 4``; nothing here decides what
runs, only how many pytest-xdist workers run it, and an explicit ``--workers N``
always wins. The choice is from a bounded ladder, never every logical CPU and
never ``-n auto``.

Where the numbers come from (Windows 11, 24 logical / 16 physical CPUs, 31.7 GB,
CPython 3.14, FAST ``-m "not expensive" --dist loadfile``, 2026-10-13, whole
process tree sampled every 0.5 s):

* ``-n 4``: 158.5 s, peak 2,577 MB for the tree (644 MB per worker);
  ``-n 8``: 105.6 s, peak 4,043 MB (505 MB per worker); same failure set.
  :data:`MB_PER_WORKER` takes the larger per-worker figure.
* the largest single process reached 1.2 - 1.3 GB, and ``-n auto`` (24 workers)
  was recorded exhausting memory (``MemoryError`` in ``json.encoder``);
  :data:`HEADROOM_MB` keeps one such worker's spike plus the rest of the machine.
* ``-n 8`` is the largest count measured (scaling 1 / 2 / 4 / 6 / 8: 589 / 303 /
  177 - 196 / 151 / 140 s before the test-loop round); 12 was never measured, so
  it is not offered.
"""

from __future__ import annotations

import os

LADDER = (8, 6, 4, 2, 1)
MB_PER_WORKER = 650
HEADROOM_MB = 2048
FALLBACK = 4


def _available_mb() -> int | None:
    """Available physical memory in MB, or ``None`` when it cannot be read reliably."""
    try:
        import psutil  # declared in the dev extra; absent in a bare install
    except ImportError:
        return None
    try:
        return int(psutil.virtual_memory().available // 2**20)
    except Exception:  # pragma: no cover - platform failure: say unknown rather than guess
        return None


def choose(logical_cpus: int | None = None, available_mb: int | None = -1) -> tuple[int, str]:
    """``(workers, reason)``; 0 means serial. ``available_mb=-1`` reads the machine; ``None`` means unknown."""
    cpus = os.cpu_count() if logical_cpus is None else logical_cpus
    cpus = max(1, int(cpus or 1))
    memory = _available_mb() if available_mb == -1 else available_mb
    # never more than half the logical CPUs: on an SMT machine that is about the physical cores
    cpu_cap = max(1, cpus // 2)
    by_cpu = next(n for n in LADDER if n <= cpu_cap)
    if memory is None:
        n = min(FALLBACK, by_cpu)
        return n, f"{cpus} logical CPUs, available memory unknown: the CI-compatible {n}"
    for n in LADDER:
        if n <= by_cpu and memory >= n * MB_PER_WORKER + HEADROOM_MB:
            limit = ("the largest measured count" if n == LADDER[0] else "limited by CPU" if n == by_cpu
                     else "limited by available memory")
            return n, (f"{cpus} logical CPUs, {memory / 1024:.1f} GB available "
                       f"(needs {n} x {MB_PER_WORKER} MB + {HEADROOM_MB} MB headroom): {limit}")
    return 0, (f"{cpus} logical CPUs, {memory / 1024:.1f} GB available: below the "
               f"{MB_PER_WORKER + HEADROOM_MB} MB one worker needs, running serially (no xdist)")
