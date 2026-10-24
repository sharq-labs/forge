"""Execute one command under observation and seal its receipt.

The child is started from an argument list (never a reconstructed shell string), its exit code is
returned unchanged, its output is passed through and stored redacted, and a pending receipt exists
from just before it starts until the sealed one replaces it -- so an observer killed mid-run leaves
something ``recover`` can seal as a partial receipt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time
from typing import Mapping, Sequence
import uuid

from tools.run_observatory import (CLASSIFICATION, PENDING_SCHEMA, RECEIPT_SCHEMA, RUN_KINDS, adapters, compare,
                                   identity, metrics, receipt as receipt_mod)
from tools.run_observatory.ledger import Ledger, iter_pending, quarantine
from tools.run_observatory.redaction import Redactor, StreamRedactor

OBSERVER_VERSION = "1.0.0"
WINDOWS = sys.platform == "win32"

#: counter -> (derived rate, scale). Rates are derived from these and nothing else.
THROUGHPUT_COUNTERS = {
    "tests": ("tests_per_second", 1.0), "cases": ("cases_per_second", 1.0),
    "experiments": ("experiments_per_second", 1.0), "solver_calls": ("solver_calls_per_second", 1.0),
    "cards": ("cards_per_second", 1.0), "records": ("records_per_second", 1.0),
    "bytes_processed": ("GB_per_second", 1e-9),
}
DATA_EFFICIENCY_COUNTERS = ("dataset_available_bytes", "dataset_read_bytes", "derived_bytes_written",
                            "evidence_bytes", "cache_bytes", "decisions")
SCIENTIFIC_EFFICIENCY_COUNTERS = ("hypotheses_proposed", "hypotheses_falsified", "experiments_requested",
                                  "experiments_executed", "solver_calls", "evidence_records", "decisions")
_CATEGORY = {**{n: "scientific_efficiency" for n in SCIENTIFIC_EFFICIENCY_COUNTERS},
             **{n: "data_efficiency" for n in DATA_EFFICIENCY_COUNTERS},
             **{n: "throughput" for n in THROUGHPUT_COUNTERS}}
_COST_FIELDS = ("compute_cost_estimate", "storage_cost_estimate", "currency", "cost_model_id")
_STREAM_JOIN_SECONDS = 10.0

#: PREPARE: an interrupt aborts before anything starts. WAIT: it stops the child and seals an
#: INTERRUPTED receipt. SEAL: it is recorded and ignored, so a receipt is never half-written.
PHASE = {"value": "IDLE"}
LATE_SIGNALS: list[int] = []


class Interrupted(KeyboardInterrupt):
    def __init__(self, signum: int) -> None:
        super().__init__(signum)
        self.signum = signum


class RunRootInsideRepository(ValueError):
    """The run root must live outside the observed repository: ledgers are never committed."""


def counter_category(name: str) -> str:
    if name.startswith("custom.") and len(name) > len("custom."):
        return "custom"
    if name not in _CATEGORY:
        raise ValueError(f"undeclared counter {name!r}: use one of {', '.join(sorted(_CATEGORY))} or 'custom.<name>'")
    return _CATEGORY[name]


# ---------------------------------------------------------------------------
# Time


class SystemClock:
    @staticmethod
    def monotonic_ns() -> int:
        return time.perf_counter_ns()

    @staticmethod
    def utc_now() -> datetime:
        return datetime.now(timezone.utc)


def iso_utc(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class Stopwatch:
    """Elapsed time from the monotonic clock; the UTC stamps are labels, never subtracted."""

    def __init__(self, clock=None) -> None:
        self.clock = clock or SystemClock()
        self._t0: int | None = None
        self._start: datetime | None = None

    def start(self) -> None:
        self._t0 = self.clock.monotonic_ns()
        self._start = self.clock.utc_now()

    @property
    def started_utc(self) -> str | None:
        return iso_utc(self._start) if self._start else None

    def stop(self) -> dict:
        t1 = self.clock.monotonic_ns()
        end = self.clock.utc_now()
        return {"started_utc": iso_utc(self._start), "ended_utc": iso_utc(end), "wall_seconds": (t1 - self._t0) / 1e9,
                "monotonic_source": "time.perf_counter_ns"}


def new_run_id() -> str:
    return f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:16]}"


# ---------------------------------------------------------------------------
# Request / outcome / store


@dataclass
class RunRequest:
    argv: Sequence[str]
    run_root: Path
    cwd: Path | None = None
    repo: Path | None = None
    kind: str = "UTILITY"
    name: str | None = None
    tags: Sequence[str] = ()
    parent: str | None = None
    group: str | None = None
    adapter: str = "generic"
    inputs: Sequence[Path | str] = ()
    configs: Sequence[Path | str] = ()
    seeds: Sequence[str] = ()
    declared: Mapping[str, object] | None = None
    workload_env: Sequence[str] = ()
    counters: Mapping[str, float] | None = None
    artifacts: Sequence[Path | str] = ()
    output_identity: str | None = None
    trace_identity: str | None = None
    replay_of: str | None = None
    cost: Mapping[str, object] | None = None
    baseline: str = "auto"
    policy: dict | None = None
    sample_interval: float = 0.1
    persist_logs: bool = True
    env_cache: bool = True
    refresh_env_cache: bool = False
    quiet: bool = False
    grace_seconds: float = 10.0


@dataclass
class RunOutcome:
    run_id: str
    receipt: dict
    receipt_path: Path
    exit_code: int
    warnings: list[str] = field(default_factory=list)


class RunStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        for sub in ("receipts", "logs", "artifacts", "summaries"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)
        self.salt = receipt_mod.create_once(self.root / "host_salt", os.urandom(32))

    def receipt_path(self, run_id: str) -> Path:
        return self.root / "receipts" / f"{run_id}.json"

    def pending_path(self, run_id: str) -> Path:
        return self.root / "receipts" / f"{run_id}.pending.json"

    def log_path(self, run_id: str, stream: str) -> Path:
        return self.root / "logs" / f"{run_id}.{stream}.log"

    def artifacts_dir(self, run_id: str) -> Path:
        return self.root / "artifacts" / run_id

    def summary_path(self, run_id: str) -> Path:
        return self.root / "summaries" / f"{run_id}.txt"

    def relative(self, path: Path) -> str:
        try:
            return Path(path).resolve().relative_to(self.root.resolve()).as_posix()
        except ValueError:
            return str(path)


# ---------------------------------------------------------------------------
# Output capture


class _Pump(threading.Thread):
    """Copies one child stream: raw bytes hashed, passed through, and stored redacted."""

    def __init__(self, stream, sink, log_path: Path | None, redactor: Redactor) -> None:
        super().__init__(daemon=True, name="run-observatory-pump")
        self.stream, self.sink, self.log_path, self.redactor = stream, sink, log_path, redactor
        self.raw = hashlib.sha256()
        self.stored = hashlib.sha256()
        self.raw_bytes = self.stored_bytes = self.redactions = 0
        self.stream_redactor = StreamRedactor(redactor)

    def run(self) -> None:
        log = open(self.log_path, "wb") if self.log_path else None
        try:
            for chunk in iter(lambda: self.stream.readline(65536), b""):
                self.raw.update(chunk)
                self.raw_bytes += len(chunk)
                if self.sink is not None:
                    try:
                        self.sink.write(chunk)
                        self.sink.flush()
                    except (OSError, ValueError):
                        self.sink = None
                if log is not None:
                    clean, count = self.stream_redactor.feed(chunk)
                    log.write(clean)
                    self.stored.update(clean)
                    self.stored_bytes += len(clean)
                    self.redactions += count
        finally:
            if log is not None:
                clean, count = self.stream_redactor.feed(b"", final=True)
                log.write(clean)
                self.stored.update(clean)
                self.stored_bytes += len(clean)
                self.redactions += count
                log.close()
            self.stream.close()

    def record(self, store: RunStore) -> dict:
        complete = not self.is_alive()
        return {"raw_sha256": self.raw.hexdigest(), "raw_bytes": self.raw_bytes,
                "stored_path": store.relative(self.log_path) if self.log_path else None,
                "stored_sha256": self.stored.hexdigest() if self.log_path else None,
                "stored_bytes": self.stored_bytes if self.log_path else None,
                "redactions": self.redactions, "persisted": self.log_path is not None, "capture_complete": complete,
                "redaction_limit_omitted": self.stream_redactor.omitted}


def _sink(stream_name: str, quiet: bool):
    if quiet:
        return None
    return getattr(getattr(sys, stream_name), "buffer", None)


# ---------------------------------------------------------------------------
# Assembly helpers


def _resolve_executable(argv0: str, cwd: Path, environ: Mapping[str, str]) -> Path | None:
    if os.sep in argv0 or (os.altsep and os.altsep in argv0):
        candidate = Path(argv0) if Path(argv0).is_absolute() else cwd / argv0
        return candidate if candidate.is_file() else None
    found = shutil.which(argv0, path=environ.get("PATH"))
    return Path(found) if found else None


def _cost(cost: Mapping[str, object] | None) -> dict:
    cost = dict(cost or {})
    unknown = set(cost) - set(_COST_FIELDS)
    if unknown:
        raise ValueError(f"unknown cost fields: {sorted(unknown)}")
    record = {k: cost.get(k) for k in _COST_FIELDS}
    amounts = [record["compute_cost_estimate"], record["storage_cost_estimate"]]
    if all(a is None for a in amounts):
        return {**record, "label": "NOT_AVAILABLE"}
    if not record["currency"] or not record["cost_model_id"]:
        raise ValueError("a cost estimate needs both a currency and a cost_model_id")
    for amount in amounts:
        if amount is not None and float(amount) < 0:
            raise ValueError("a cost estimate cannot be negative")
    return {**record, "label": "ESTIMATED",
            "note": "caller-declared estimate; v1 has no authoritative billing source, so it never becomes MEASURED"}


def _validate(req: RunRequest) -> None:
    if not req.argv:
        raise ValueError("no command given")
    if req.kind not in RUN_KINDS:
        raise ValueError(f"unknown run kind {req.kind!r}; one of {', '.join(RUN_KINDS)}")
    adapters.get(req.adapter)
    for name, value in (req.counters or {}).items():
        counter_category(name)
        if not isinstance(value, (int, float)) or value < 0:
            raise ValueError(f"counter {name!r} must be a non-negative number")
    _cost(req.cost)


def _counters(sources: Sequence[tuple[str, Mapping[str, object]]], wall: float | None) -> dict:
    """Merge counter sources (later sources win) and derive rates only from what was declared."""
    values: dict[str, dict] = {}
    rejected, conflicts = [], []
    for source, mapping in sources:
        for name, value in (mapping or {}).items():
            try:
                category = counter_category(str(name))
            except ValueError:
                rejected.append({"name": str(name), "source": source, "reason": "undeclared counter name"})
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                rejected.append({"name": str(name), "source": source, "reason": "not a non-negative number"})
                continue
            if name in values and values[name]["value"] != value:
                conflicts.append({"name": name, "kept": source, "dropped": values[name]["source"],
                                  "dropped_value": values[name]["value"]})
            values[name] = {"value": value, "source": source, "category": category}
    derived: dict[str, dict] = {}
    if wall:
        for name, (rate, scale) in THROUGHPUT_COUNTERS.items():
            if name in values:
                derived[rate] = {"value": values[name]["value"] * scale / wall, "from": [name, "timing.wall_seconds"]}
    available = values.get("dataset_available_bytes", {}).get("value")
    read = values.get("dataset_read_bytes", {}).get("value")
    decisions = values.get("decisions", {}).get("value")
    if available and read is not None:
        derived["data_fraction_read"] = {"value": read / available,
                                         "from": ["dataset_read_bytes", "dataset_available_bytes"]}
    if decisions and read is not None:
        derived["bytes_per_decision"] = {"value": read / decisions, "from": ["dataset_read_bytes", "decisions"]}
    return {"values": values, "derived": derived, "rejected": rejected, "conflicts": conflicts}


def _read_child_report(path: Path) -> tuple[dict, list[str]]:
    if not path.is_file():
        return {}, []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("not a JSON object")
        return data, []
    except (OSError, ValueError) as exc:
        return {}, [f"child report file ignored: {exc}"]


def _artifacts(paths: Sequence[Path | str], cwd: Path) -> list[dict]:
    out = []
    for raw in paths:
        path = Path(raw) if Path(raw).is_absolute() else cwd / raw
        entry = {"path": str(raw), "exists": path.is_file(), "bytes": None, "sha256": None}
        if entry["exists"]:
            entry["bytes"] = path.stat().st_size
            entry["sha256"] = identity.sha256_file(path)
        out.append(entry)
    return out


def _replay(req: RunRequest, book: Ledger, child_report: Mapping[str, object]) -> dict:
    out_id = req.output_identity or child_report.get("output_identity")
    trace_id = req.trace_identity or child_report.get("trace_identity")
    section = {"replay_of": req.replay_of, "output_identity": out_id, "trace_identity": trace_id,
               "expected_output_identity": None, "expected_trace_identity": None,
               "status": "NOT_CHECKED", "reading": "NOT_CHECKED", "checked": [], "note": None}
    if not req.replay_of:
        return section
    original = book.load_receipt(req.replay_of)
    if original is None or not receipt_mod.verify(original):
        section["note"] = "original run's receipt is missing or does not verify"
        return section
    expected = original.get("replay") or {}
    section["expected_output_identity"] = expected.get("output_identity")
    section["expected_trace_identity"] = expected.get("trace_identity")
    matches = []
    for label, observed, wanted in (("output", out_id, section["expected_output_identity"]),
                                    ("trace", trace_id, section["expected_trace_identity"])):
        if observed is not None and wanted is not None:
            section["checked"].append(label)
            matches.append(observed == wanted)
    if matches:
        section["status"] = "EXACT" if all(matches) else "MISMATCH"
        section["reading"] = "REPLAY_EXACT" if all(matches) else "REPLAY_MISMATCH"
    return section


def _never_started_resources(note: str) -> dict:
    names = {"cpu_seconds": "seconds", "peak_rss_bytes": "bytes", "avg_rss_bytes": "bytes",
             "peak_tree_commit_bytes": "bytes", "io_read_bytes": "bytes", "io_write_bytes": "bytes",
             "process_count": "processes", "network_bytes": "bytes", "gpu_utilization": "fraction"}
    return {name: metrics.unsupported(unit, note) for name, unit in names.items()}


def _comparison(body: dict, req: RunRequest, book: Ledger, started: bool) -> dict:
    policy = req.policy or compare.DEFAULT_POLICY
    if req.baseline == "none":
        return compare.no_baseline(policy, "baseline_disabled")
    if not started or not body.get("workload"):
        return compare.no_baseline(policy, "run_did_not_start")
    row = book.find_baseline(body) if req.baseline == "auto" else book.get(req.baseline)
    if row is None:
        return compare.no_baseline(policy, "no_baseline_found" if req.baseline == "auto" else "baseline_not_found")
    base = book.load_receipt(row["run_id"])
    if base is None or book.verify_receipt(base) != "VALID":
        return compare.no_baseline(policy, "baseline_receipt_unverifiable")
    history = book.exact_history(base, before_utc=body["timing"].get("started_utc"),
                                 limit=compare.history_window(policy), exclude=body["run_id"])
    return compare.compare(body, base, policy, history)


def summary_text(rec: dict, receipt_path: Path) -> str:
    git, timing, result = rec["git"], rec["timing"], rec["result"]
    comparison, resources = rec["comparison"], rec["resources"]

    def metric(name: str) -> str:
        m = resources.get(name) or {}
        return "UNSUPPORTED" if m.get("value") is None else f"{m['value']:.6g} {m.get('unit', '')} ({m['support']})"

    tree = {True: "true", False: "false"}.get(git.get("tree_clean"), "unknown")
    wall = timing.get("wall_seconds")
    lines = [
        f"RUN_ID = {rec['run_id']}", f"RUN_KIND = {rec['run_kind']}", f"NAME = {rec.get('name') or ''}",
        f"RESULT = {result['status']} (exit {result.get('exit_code')})",
        f"GIT = {git.get('head_sha') or git.get('status')} ({git.get('branch') or 'detached'})",
        f"TREE_CLEAN = {tree}",
        f"WORKLOAD_ID = {(rec.get('workload') or {}).get('workload_id')}",
        f"ENVIRONMENT_ID = {rec['environment'].get('environment_id')}",
        f"WALL_TIME = {'UNKNOWN' if wall is None else f'{wall:.3f} s'}",
        f"CPU_TIME = {metric('cpu_seconds')}", f"PEAK_RSS = {metric('peak_rss_bytes')}",
        f"HOST_LOAD = {_load_text(rec.get('host_load') or {})}",
        f"COMPARABILITY = {comparison['comparability']}", f"BASELINE_RUN = {comparison.get('baseline_run_id')}",
    ]
    deltas = comparison.get("deltas") or {}
    for name in ("wall_seconds", "peak_rss_bytes", "cpu_seconds"):
        d = deltas.get(name)
        if d and d.get("pct") is not None:
            lines.append(f"{name.upper()}_DELTA = {d['pct']:+.1f}% ({d['comparability']})")
    policy = comparison.get("policy") or {}
    lines.append(f"PERFORMANCE = {comparison['performance']} (policy {policy.get('policy_id')} v{policy.get('version')})")
    noise = comparison.get("noise")
    if noise and noise["runs"]:
        lines.append(f"NOISE_BAND = {noise['runs']} earlier exact runs, {noise['min_seconds']:.3f}-"
                     f"{noise['max_seconds']:.3f} s (spread {noise['spread_pct']:.1f}%), "
                     f"within band: {str(noise['within_band']).lower()}")
    elif noise:
        lines.append(f"NOISE_BAND = no earlier exact runs (policy needs {noise['required']})")
    lines += [f"RESULT_DELTA = {comparison.get('result_delta')}", f"FAILURE_SET = {comparison.get('failure_set')}",
              f"REPLAY = {rec['replay']['reading']}", f"PARTIAL = {str(rec['partial']).lower()}",
              f"RECEIPT = {receipt_path}", f"RECEIPT_SHA256 = {rec['integrity']['receipt_sha256']}",
              f"CLASSIFICATION = {rec['classification']}"]
    return "\n".join(lines) + "\n"


def _load_text(load: dict) -> str:
    if load.get("other_busy_cores") is None:
        return "UNSUPPORTED (context only)"
    return (f"{load['other_busy_cores']:.1f} of {load['logical_cores']} cores busy outside this run, "
            f"machine {load['cpu_busy_fraction'] * 100:.0f}% busy (context only)")


def _publish(store: RunStore, book: Ledger, rec: dict, warnings: list[str]) -> Path:
    path = store.receipt_path(rec["run_id"])
    receipt_mod.write_sealed(path, rec)
    try:
        book.index(rec, path)
    except Exception as exc:  # noqa: BLE001 - the receipt is canonical; `reindex` repairs the index
        warnings.append(f"ledger index failed ({exc}); run `reindex`")
    try:
        store.summary_path(rec["run_id"]).write_text(summary_text(rec, path), encoding="utf-8")
    except OSError as exc:
        warnings.append(f"summary not written: {exc}")
    store.pending_path(rec["run_id"]).unlink(missing_ok=True)
    return path


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Execution


def execute(req: RunRequest, *, clock=None, environ: Mapping[str, str] | None = None) -> RunOutcome:
    """Run ``req.argv`` under observation and return its sealed receipt and the child's exit code."""
    PHASE["value"] = "PREPARE"
    try:
        return _execute(req, clock=clock, environ=environ)
    finally:
        PHASE["value"] = "IDLE"


def _execute(req: RunRequest, *, clock, environ) -> RunOutcome:
    _validate(req)
    environ = dict(os.environ if environ is None else environ)
    redactor = Redactor.from_environ(environ)
    adapter = adapters.get(req.adapter)
    run_root = Path(req.run_root).resolve()
    cwd = Path(req.cwd).resolve() if req.cwd else Path.cwd()
    git = identity.capture_git(req.repo or cwd)
    if git["status"] == "OK" and _inside(run_root, Path(git["repository_root"])):
        raise RunRootInsideRepository(f"run root {run_root} is inside the observed repository "
                                      f"{git['repository_root']}; keep ledgers out of Git")
    store = RunStore(run_root)
    book = Ledger(run_root)
    run_id = new_run_id()
    warnings: list[str] = []
    argv =[str(a) for a in req.argv]
    exe = _resolve_executable(argv[0], cwd, environ)
    artifacts_dir = store.artifacts_dir(run_id)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    report_file = artifacts_dir / "report.json"
    additions, context = adapter.prepare(argv, artifacts_dir)
    if context.get("junit"):
        report_path = Path(context["junit"])
        context["junit"] = str((cwd / report_path).resolve())

    body: dict = {
        "schema": RECEIPT_SCHEMA, "classification": CLASSIFICATION, "measurement_label": "MEASURED",
        "run_id": run_id, "run_kind": req.kind, "name": req.name, "tags": sorted(set(req.tags)), "partial": False,
        "parent": {"parent_run_id": req.parent, "replay_of": req.replay_of, "comparison_group": req.group},
        "git": git, "workload": None, "environment": {"environment_id": None, "facts": None},
        "command": {"adapter": adapter.name, "argv": redactor.redact_argv(argv),
                    "adapter_args": redactor.redact_argv(additions),
                    "executable": {"name": identity.executable_name(argv[0]),
                                   "resolved_path": str(exe) if exe else None,
                                   "sha256": None},
                    "cwd": str(cwd), "shell": False,
                    "child_env_added": ["FORGE_RUN_ID", "FORGE_RUN_REPORT_FILE", "FORGE_RUN_ARTIFACTS_DIR"]},
        "cost": _cost(req.cost),
        "observer": {"version": OBSERVER_VERSION, "python": sys.version.split()[0], "pid": os.getpid(),
                     "sample_interval_seconds": req.sample_interval},
    }
    start_error: BaseException | None = None
    try:
        if not cwd.is_dir():
            raise NotADirectoryError(f"working directory does not exist: {cwd}")
        if exe is not None:
            body["command"]["executable"]["sha256"] = identity.sha256_file(exe)
        repo_root = Path(git["repository_root"]) if git["status"] == "OK" else None
        resolve = (lambda p: Path(p) if Path(p).is_absolute() else cwd / p)
        body["workload"] = identity.workload_identity(
            argv=argv, cwd=cwd, repo_root=repo_root, run_root=run_root, adapter=adapter.name,
            inputs=[resolve(p) for p in req.inputs], configs=[resolve(p) for p in req.configs], seeds=req.seeds,
            declared=req.declared, workload_env=req.workload_env, environ=environ, redactor=redactor)
        facts, source = identity.cached_environment_facts(
            salt=store.salt, child_executable=exe, cache_dir=store.root / "cache" if req.env_cache else None,
            refresh=req.refresh_env_cache)
        body["environment"] = {"environment_id": identity.environment_identity(facts), "facts": facts,
                               "facts_source": source}
    except ValueError as exc:
        if "refusing to bind secret" in str(exc):
            raise
        start_error = exc
    except OSError as exc:
        start_error = exc

    stopwatch = Stopwatch(clock)
    monitor = metrics.ProcessTreeMonitor(req.sample_interval)
    host = metrics.HostLoad()
    pumps: list[_Pump] = []
    proc: subprocess.Popen | None = None
    rc: int | None = None
    interrupted = False
    timing: dict | None = None
    pending_path = store.pending_path(run_id)
    pending = {"schema": PENDING_SCHEMA, "run_id": run_id, "state": "RUNNING", "observer_pid": os.getpid(),
               "observer_create_time": _own_create_time(), "child_pid": None, "started_utc": None, "body": body}

    if start_error is None:
        receipt_mod.write_replace(pending_path, pending)
        child_env = dict(environ, FORGE_RUN_ID=run_id, FORGE_RUN_REPORT_FILE=str(report_file),
                         FORGE_RUN_ARTIFACTS_DIR=str(artifacts_dir))
        try:
            PHASE["value"] = "WAIT"
            stopwatch.start()
            monitor.before_start()
            host.start()
            try:
                proc = subprocess.Popen([*argv, *additions], cwd=cwd, env=child_env, stdin=None,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False,
                                        start_new_session=not WINDOWS)
            except OSError as exc:
                start_error = exc
            if proc is not None:
                monitor.attach(proc)
                for name, stream in (("stdout", proc.stdout), ("stderr", proc.stderr)):
                    log = store.log_path(run_id, name) if req.persist_logs else None
                    pump = _Pump(stream, _sink(name, req.quiet), log, redactor)
                    pump.start()
                    pumps.append(pump)
                receipt_mod.write_replace(pending_path, {**pending, "child_pid": proc.pid,
                                                         "started_utc": stopwatch.started_utc})
                rc = _wait(proc)
        except KeyboardInterrupt as exc:
            interrupted = True
            rc = _stop_child(proc, monitor, req.grace_seconds, getattr(exc, "signum", None))
        finally:
            PHASE["value"] = "SEAL"
            if stopwatch._t0 is not None:
                timing = stopwatch.stop()

    started = proc is not None
    if timing is None or not started:
        now = iso_utc(datetime.now(timezone.utc))
        timing = {"started_utc": (timing or {}).get("started_utc", now), "ended_utc": (timing or {}).get("ended_utc", now),
                  "wall_seconds": None, "monotonic_source": "time.perf_counter_ns",
                  "note": "the child never started"}
    for pump in pumps:
        pump.join(timeout=_STREAM_JOIN_SECONDS)
    resources = monitor.finish() if started else _never_started_resources("the child never started")
    host_load = (host.finish(resources["cpu_seconds"]["value"]) if started
                 else metrics.unsupported_host_load("the child never started"))
    timing["cpu_seconds"] = resources["cpu_seconds"]

    if started:
        result = adapter.classify(rc, interrupted=interrupted, context=context)
        result["started"] = True
        result["error"] = None
        if any(not p.record(store)["capture_complete"] for p in pumps):
            result["notes"].append("output capture did not finish: a descendant may still hold the pipes")
    else:
        message = redactor.redact_text(f"{type(start_error).__name__}: {start_error}")[0] if start_error else None
        not_found = isinstance(start_error, FileNotFoundError) and cwd.is_dir()
        result = {"status": "RUN_ERROR", "exit_code": 127 if not_found else 126, "raw_returncode": None,
                  "terminated_by_signal": None, "adapter_outcomes": None, "notes": [], "started": False,
                  "error": message}
        if interrupted:
            result["status"] = "RUN_INTERRUPTED"
    if LATE_SIGNALS:
        result["notes"].append(f"signals received while sealing were ignored: {sorted(set(LATE_SIGNALS))}")
        LATE_SIGNALS.clear()

    child_report, report_notes = _read_child_report(report_file) if started else ({}, [])
    result["notes"].extend(report_notes)
    body["partial"] = interrupted or result["status"] == "RUN_INTERRUPTED"
    body["timing"] = timing
    body["resources"] = resources
    body["host_load"] = host_load
    body["result"] = result
    body["counters"] = _counters([("DECLARED", req.counters or {}),
                                  ("CHILD_REPORTED", child_report.get("counters") or {}),
                                  (f"ADAPTER:{adapter.name}", adapter.counters(result) if started else {})],
                                 timing.get("wall_seconds"))
    body["outputs"] = {"stdout": pumps[0].record(store) if pumps else None,
                       "stderr": pumps[1].record(store) if len(pumps) > 1 else None,
                       "artifacts": _artifacts(req.artifacts, cwd) if started else [],
                       "adapter_report": store.relative(Path(context["junit"])) if context.get("junit") else None}
    body["replay"] = _replay(req, book, child_report)
    body["comparison"] = _comparison(body, req, book, started)

    sealed = receipt_mod.seal(body, sealed_by="RUNNER")
    path = _publish(store, book, sealed, warnings)
    return RunOutcome(run_id=run_id, receipt=sealed, receipt_path=path, exit_code=_exit_code(result, rc),
                      warnings=warnings)


def _wait(proc: subprocess.Popen) -> int:
    """Wait in short slices so a console interrupt is delivered (Windows blocks it in an infinite wait)."""
    while True:
        try:
            return proc.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            continue


def _stop_child(proc: subprocess.Popen | None, monitor: metrics.ProcessTreeMonitor, grace: float,
                signum: int | None) -> int | None:
    """Give the child ``grace`` seconds to finish after an interrupt, then stop its whole tree."""
    if proc is None:
        return None
    if not WINDOWS:
        try:
            os.killpg(proc.pid, signum or signal.SIGINT)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        try:
            rc = proc.wait(timeout=0.2)
            # The parent may exit while workers ignore the forwarded signal.
            if not WINDOWS:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            return rc
        except subprocess.TimeoutExpired:
            continue
        except KeyboardInterrupt:
            break
    try:
        if not WINDOWS:
            # An interrupt can arrive between Popen and monitor.attach().
            os.killpg(proc.pid, signal.SIGKILL)
        elif getattr(monitor, "_proc", None) is not None:
            monitor.terminate_tree()
        else:
            proc.kill()
    except ProcessLookupError:
        pass
    try:
        return proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        return proc.wait()


def _exit_code(result: dict, rc: int | None) -> int:
    if not result.get("started"):
        return int(result["exit_code"])
    if rc is None:
        return 130
    return 128 - rc if rc < 0 else rc


def _own_create_time() -> float | None:
    if metrics.psutil is None:
        return None
    try:
        return metrics.psutil.Process().create_time()
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Recovery


def _observer_alive(pending: dict) -> bool:
    pid = pending.get("observer_pid")
    if not isinstance(pid, int) or not metrics.pid_alive(pid):
        return False
    created = pending.get("observer_create_time")
    if created is not None and metrics.psutil is not None:
        try:
            return abs(metrics.psutil.Process(pid).create_time() - created) < 1.0
        except Exception:  # noqa: BLE001
            return False
    return True


def recover(run_root: Path, *, force: bool = False) -> dict:
    """Seal every pending receipt whose observer is gone as a partial RUN_INTERRUPTED receipt.

    A pending file that cannot be read is moved to ``receipts/quarantine/`` and never indexed. A
    pending file whose observer is still running is left alone unless ``force``.
    """
    store, book = RunStore(Path(run_root)), Ledger(Path(run_root))
    report: dict[str, list] = {"recovered": [], "quarantined": [], "running": [], "already_sealed": []}
    for path in iter_pending(store.root):
        try:
            pending = json.loads(path.read_text(encoding="utf-8"))
            body, run_id = pending["body"], pending["run_id"]
            if body["run_id"] != run_id or body["schema"] != RECEIPT_SCHEMA:
                raise ValueError("pending receipt is inconsistent")
        except (OSError, ValueError, KeyError, TypeError):
            quarantine(path)
            report["quarantined"].append(path.name)
            continue
        if not force and _observer_alive(pending):
            report["running"].append(run_id)
            continue
        if store.receipt_path(run_id).exists():
            path.unlink(missing_ok=True)
            report["already_sealed"].append(run_id)
            continue
        note = "the observer ended before the run finished; sealed by recovery"
        body["partial"] = True
        body["timing"] = {"started_utc": pending.get("started_utc"), "ended_utc": None, "wall_seconds": None,
                          "monotonic_source": "time.perf_counter_ns", "note": note}
        body["resources"] = _never_started_resources(note)
        body["host_load"] = metrics.unsupported_host_load(note)
        body["timing"]["cpu_seconds"] = body["resources"]["cpu_seconds"]
        body["result"] = {"status": "RUN_INTERRUPTED", "exit_code": None, "raw_returncode": None,
                          "terminated_by_signal": None, "adapter_outcomes": None, "started": bool(pending.get("child_pid")),
                          "error": note, "notes": [f"child pid was {pending.get('child_pid')}"]}
        body["counters"] = _counters([("DECLARED", {})], None)
        outputs = {}
        for stream in ("stdout", "stderr"):
            log = store.log_path(run_id, stream)
            outputs[stream] = ({"raw_sha256": None, "raw_bytes": None, "stored_path": store.relative(log),
                                "stored_sha256": identity.sha256_file(log), "stored_bytes": log.stat().st_size,
                                "redactions": None, "persisted": True, "capture_complete": False}
                               if log.is_file() else None)
        body["outputs"] = {**outputs, "artifacts": [], "adapter_report": None}
        body["replay"] = {"replay_of": (body.get("parent") or {}).get("replay_of"), "output_identity": None,
                          "trace_identity": None, "expected_output_identity": None, "expected_trace_identity": None,
                          "status": "NOT_CHECKED", "reading": "NOT_CHECKED", "checked": [], "note": note}
        body["comparison"] = compare.no_baseline(None, "partial_run")
        sealed = receipt_mod.seal(body, sealed_by="RECOVERY")
        _publish(store, book, sealed, [])
        report["recovered"].append(run_id)
    return report
