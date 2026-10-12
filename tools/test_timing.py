"""Developer test-timing telemetry, and a guard against large slowdowns.

    python -m pytest ... -p tools.test_timing --timing-report=PATH     # record one run
    python -m tools.test_timing compare OLD.json NEW.json             # what got much slower
    python -m tools.test_timing history [DIR]                         # list recorded runs

A report is **developer performance telemetry**: machine-specific, noisy, never
scientific evidence and never part of certification. Nothing reads it to decide
a result; ``forge_check --dev`` writes one per run under
``~/.cache/forge/timing/`` (outside the repository) and prints the comparison
with the previous run as a warning, never as a failure.

The comparison flags only large changes, with thresholds taken from repeated
measurement on the reference machine (Windows 11, 24 logical CPUs, CPython 3.14,
FAST at ``-n 4 --dist loadfile``, 2026-10-13): see :data:`DEFAULTS`.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import pathlib
import platform
import sys
import time
from typing import Any, Mapping

SCHEMA = "forge.test_timing/1"
CLASSIFICATION = "developer performance telemetry; not scientific evidence; not certification"

#: Flag a change only when it clears both an absolute and a relative bar. Measured noise between two
#: identical warm FAST runs (-n 4, 2026-10-13): modules differed by at most 2.5 s (ratio <= 1.12 for
#: modules over 1 s), tests by at most 1.8 s; whole runs of identical code have differed by x1.25
#: (135.6 s vs 168.9 s, 2026-10-13). Each bar sits clearly above what noise produced.
DEFAULTS = {
    "module_ratio": 2.0,
    "module_min_seconds": 5.0,
    "test_ratio": 2.0,
    "test_min_seconds": 3.0,
    "wall_ratio": 1.4,
}

_TEST_KEEP_SECONDS = 0.25  # per-test durations below this are summed into their module only


def default_history_dir() -> pathlib.Path:
    override = os.environ.get("FORGE_TIMING_DIR")
    return pathlib.Path(override) if override else pathlib.Path.home() / ".cache" / "forge" / "timing"


# ---------------------------------------------------------------------------
# pytest plugin
# ---------------------------------------------------------------------------


def pytest_addoption(parser) -> None:
    parser.getgroup("forge").addoption(
        "--timing-report", default=None, help="write a developer timing report (telemetry, not evidence) to this path")


class _Recorder:
    def __init__(self, config) -> None:
        self.config = config
        self.start = time.time()
        self.tests: dict[str, float] = collections.defaultdict(float)
        self.outcomes: dict[str, str] = {}
        self.workers: dict[str, list[float]] = {}
        self.first_start: float | None = None

    def pytest_runtest_logreport(self, report) -> None:
        worker = getattr(getattr(getattr(report, "node", None), "gateway", None), "id", None) or "main"
        self.tests[report.nodeid] += report.duration
        if self.first_start is None or report.start < self.first_start:
            self.first_start = report.start
        span = self.workers.setdefault(worker, [report.start, report.stop, 0.0])
        span[0], span[1], span[2] = min(span[0], report.start), max(span[1], report.stop), span[2] + report.duration
        if report.when == "call" or report.outcome != "passed":
            previous = self.outcomes.get(report.nodeid)
            if previous in (None, "passed") or report.outcome == "failed":
                self.outcomes[report.nodeid] = "error" if report.when != "call" and report.outcome == "failed" else report.outcome

    def pytest_sessionfinish(self, session, exitstatus) -> None:
        if hasattr(self.config, "workerinput"):  # an xdist worker: the controller writes the report
            return
        path = self.config.getoption("--timing-report")
        end = time.time()
        modules: dict[str, float] = collections.defaultdict(float)
        for nodeid, seconds in self.tests.items():
            modules[nodeid.split("::", 1)[0]] += seconds
        counts = collections.Counter(self.outcomes.values())
        report = {
            "schema": SCHEMA,
            "classification": CLASSIFICATION,
            "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(end)),
            "machine": _machine(),
            "python": sys.version.split()[0],
            "args": list(self.config.invocation_params.args),
            "workers": _workers(self.config),
            "wall_seconds": round(end - self.start, 3),
            "startup_seconds": round((self.first_start or end) - self.start, 3),
            "tests_reported": len(self.outcomes),
            "outcomes": dict(sorted(counts.items())),
            "failed": sorted(n for n, o in self.outcomes.items() if o in ("failed", "error")),
            "modules": {m: round(s, 3) for m, s in sorted(modules.items())},
            "tests": {n: round(s, 3) for n, s in sorted(self.tests.items()) if s >= _TEST_KEEP_SECONDS},
            "worker_spans": {w: {"busy": round(v[2], 3), "ends_after_start": round(v[1] - self.start, 3)}
                             for w, v in sorted(self.workers.items())},
        }
        out = pathlib.Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def pytest_configure(config) -> None:
    if config.getoption("--timing-report", default=None):
        config.pluginmanager.register(_Recorder(config), "forge-test-timing-recorder")


def _workers(config) -> int:
    try:
        n = config.getoption("numprocesses")
    except ValueError:
        return 0
    return int(n or 0) if not isinstance(n, str) else -1


def _machine() -> dict[str, Any]:
    info: dict[str, Any] = {"platform": platform.platform(), "logical_cpus": os.cpu_count()}
    try:
        import psutil

        vm = psutil.virtual_memory()
        info.update(physical_cpus=psutil.cpu_count(logical=False), ram_total_gb=round(vm.total / 2**30, 1),
                    ram_available_gb=round(vm.available / 2**30, 1))
    except Exception:  # psutil is optional: absent context is recorded as absent, never guessed
        pass
    return info


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def compare(old: Mapping[str, Any], new: Mapping[str, Any], **limits: float) -> list[str]:
    """Large slowdowns from ``old`` to ``new``; empty when none clears both bars.

    Modules and tests are compared only where both runs measured them. The whole-run
    wall is compared only between runs of the same worker count and tests reported.
    """
    lim = {**DEFAULTS, **limits}
    found = []
    same_shape = old.get("workers") == new.get("workers") and old.get("tests_reported") == new.get("tests_reported")
    if same_shape and old.get("wall_seconds") and new["wall_seconds"] >= lim["wall_ratio"] * old["wall_seconds"]:
        found.append(f"wall {old['wall_seconds']:.1f}s -> {new['wall_seconds']:.1f}s "
                     f"(x{new['wall_seconds'] / old['wall_seconds']:.2f}, limit x{lim['wall_ratio']})")
    for kind, ratio, floor in (("modules", lim["module_ratio"], lim["module_min_seconds"]),
                               ("tests", lim["test_ratio"], lim["test_min_seconds"])):
        before, after = old.get(kind, {}), new.get(kind, {})
        for name in sorted(set(before) & set(after)):
            b, a = before[name], after[name]
            if a - b >= floor and a >= ratio * max(b, 1e-9):
                found.append(f"{kind[:-1]} {name}: {b:.1f}s -> {a:.1f}s (+{a - b:.1f}s, x{a / max(b, 1e-9):.1f})")
    return found


def _load(path: str | os.PathLike) -> dict[str, Any]:
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if data.get("schema") != SCHEMA:
        raise SystemExit(f"{path}: not a {SCHEMA} report")
    return data


def history(directory: pathlib.Path) -> list[pathlib.Path]:
    return sorted(directory.glob("*.json")) if directory.is_dir() else []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    cmp_ = sub.add_parser("compare", help="report large slowdowns from OLD to NEW (exit 1 if any)")
    cmp_.add_argument("old")
    cmp_.add_argument("new")
    for key, value in DEFAULTS.items():
        cmp_.add_argument(f"--{key.replace('_', '-')}", type=float, default=value)
    hist = sub.add_parser("history", help="list recorded reports")
    hist.add_argument("directory", nargs="?", default=None)
    args = parser.parse_args(argv)
    if args.command == "history":
        for path in history(pathlib.Path(args.directory) if args.directory else default_history_dir()):
            r = _load(path)
            print(f"{path.name}  wall {r['wall_seconds']:7.1f}s  workers {r['workers']}  tests {r['tests_reported']}  "
                  f"failed {len(r['failed'])}  python {r['python']}")
        return 0
    found = compare(_load(args.old), _load(args.new), **{k: getattr(args, k) for k in DEFAULTS})
    for line in found:
        print("SLOWER:", line)
    print(f"{len(found)} large slowdown(s) ({CLASSIFICATION})")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
