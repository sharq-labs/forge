"""Run the hardened-core assurance pipeline on a controlled local workstation.

This is the authoritative execution path when GitHub Actions is intentionally
not used for automatic CI.  It executes the same source gates as
recertify-hardened-core.yml, writes all evidence below .forge/ (ignored), binds
that evidence to the exact source commit, and builds the normal Core certificate.

Typical flow::

    python -m tools.certification.local_assurance prepare
    python -m tools.certification.local_assurance run
    git add certification/current_core_v2.json
    git commit -m "certification: recertify hardened core"
    python -m tools.certification.local_assurance verify

The final verify step is what prints SAFE_TO_PUSH=YES.  The runner never pushes.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import time
import threading
import tempfile
import traceback
import stat
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from typing import Any, Mapping, Sequence

from tools.certification import certificate_lineage, core_certificate
from tools.certification.performance_telemetry import PerformanceTelemetry, is_performance_document
from tools.certification.mutation_population import SHARD_COUNT, V4_SHARD_COUNT
from tools.certification.assert_clean_tree import tree_problems
from tools.certification.hardening_assurance import (
    EVIDENCE,
    AssuranceError,
    RunContext,
    _Evidence,
    assurance_problems,
    build_assurance,
    skip_admission_section,
)
from tools.certification.recertification_scope import (
    CERTIFICATE_PATH,
    CERTIFICATE_SELF_CHECKS,
    CERTIFICATE_CHILD_SUBJECT,
    junit_problems,
)

FAILURE_SCHEMA = "forge.local_assurance_failure/1"
RECEIPT_SCHEMA = "forge.local_assurance_receipt/1"
EVIDENCE_MANIFEST_SCHEMA = "forge.local_assurance_evidence_manifest/1"
DEFAULT_MUTATION_WORKERS = 2
#: pytest-xdist workers INSIDE one Formal mutation attempt (not --workers, not --mutation-workers).
#: One keeps the historical serial Formal command; more must be requested explicitly.
DEFAULT_FORMAL_PYTEST_WORKERS = 1
DEFAULT_ROOT = pathlib.Path(".forge")
INSTALL = ("-m", "pip", "install", "-e", ".[dev,mcp,oracles]")


class LocalAssuranceError(RuntimeError):
    pass


def _git(root: pathlib.Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True,
        encoding="utf-8", errors="surrogateescape",
    )
    if done.returncode:
        raise LocalAssuranceError(
            f"git {' '.join(args)} failed: {done.stderr.strip()}"
        )
    return done.stdout.strip()


def _sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _write_json(path: pathlib.Path, value: Mapping[str, Any]) -> str:
    payload = _json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        os.replace(temporary, path)
    finally:
        pathlib.Path(temporary).unlink(missing_ok=True)
    return hashlib.sha256(payload).hexdigest()


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _require_linux() -> None:
    if not sys.platform.startswith("linux"):
        raise LocalAssuranceError(
            "authoritative local assurance must run on Linux/WSL for parity with "
            "the certified execution environment; native Windows/macOS is refused"
        )


def _require_clean(root: pathlib.Path, phase: str) -> None:
    problems = tree_problems(root)
    if problems:
        shown = ", ".join(p.render().strip() for p in problems[:8])
        raise LocalAssuranceError(f"{phase}: checkout is dirty: {shown}")


def _require_head(root: pathlib.Path, source: str, phase: str) -> None:
    head = _git(root, "rev-parse", "HEAD")
    if head != source:
        raise LocalAssuranceError(
            f"{phase}: HEAD moved from measured source {source} to {head}"
        )


@contextmanager
def _assurance_lock(root):
    """One repository writer, including prepare and certificate-child verify."""
    import fcntl
    if any(key.startswith("GIT_") for key in os.environ):
        raise LocalAssuranceError("inherited Git overrides refused for assurance admission")
    forge = root / ".forge"
    if forge.is_symlink() or (forge.exists() and not forge.is_dir()):
        raise LocalAssuranceError("linked assurance lock directory refused")
    forge.mkdir(exist_ok=True)
    directory = forge / "locks"
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        raise LocalAssuranceError("linked assurance lock directory refused")
    directory.mkdir(exist_ok=True)
    for component in (root / ".forge", directory):
        if component.is_symlink() or not component.is_dir():
            raise LocalAssuranceError("linked assurance lock directory refused")
    path = directory / "local-assurance.lock"
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise LocalAssuranceError("linked assurance lock refused")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise LocalAssuranceError("another local assurance operation owns this repository") from exc
        yield
    finally:
        os.close(fd)
    # Keep the inode: unlinking a lock permits another invocation to bypass it.


def _resolve_python(explicit: str | None, env_dir: pathlib.Path, version: str) -> str:
    if explicit:
        candidate = pathlib.Path(explicit)
        if candidate.exists():
            return str(candidate)
        found = shutil.which(explicit)
        if found:
            return found
        raise LocalAssuranceError(f"Python {version} executable {explicit!r} was not found")

    posix = env_dir / version / "bin" / "python"
    windows = env_dir / version / "Scripts" / "python.exe"
    for candidate in (posix, windows):
        if candidate.exists():
            return str(candidate)
    found = shutil.which(f"python{version}")
    if found:
        return found
    raise LocalAssuranceError(
        f"Python {version} is required. Run local_assurance prepare with a "
        f"system Python {version} interpreter first."
    )


def _capture(argv: Sequence[str], *, root: pathlib.Path, env: Mapping[str, str] | None = None) -> str:
    done = subprocess.run(
        list(argv), cwd=root, capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=dict(env) if env else None,
    )
    if done.returncode:
        raise LocalAssuranceError(
            f"command failed ({done.returncode}): {' '.join(argv)}\n"
            f"{done.stdout}\n{done.stderr}"
        )
    return (done.stdout + done.stderr).strip()


def _run(
    argv: Sequence[str],
    *,
    root: pathlib.Path,
    env: Mapping[str, str] | None = None,
    log: pathlib.Path | None = None,
) -> None:
    shown = " ".join(argv)
    print(f"+ {shown}", flush=True)
    if log is None:
        done = subprocess.run(list(argv), cwd=root, env=dict(env) if env else None)
        if done.returncode:
            raise LocalAssuranceError(f"command failed ({done.returncode}): {shown}")
        return

    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8", newline="\n") as handle:
        process = subprocess.Popen(
            list(argv), cwd=root, env=dict(env) if env else None,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            start_new_session=True,
        )
        try:
            assert process.stdout is not None
            for line in process.stdout:
                sys.stdout.write(line)
                handle.write(line)
            code = process.wait()
        except BaseException:
            # Ask the dedicated shard to drain its own descendants. Its target
            # starts a different session: this parent's PGID is not tree ownership.
            # Never signal a numeric group after reaping its leader (PID reuse).
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                process.wait()
            # Scratch is retained on every abnormal parent/shard path.
            raise
        finally:
            if process.stdout is not None:
                process.stdout.close()
    if code:
        raise LocalAssuranceError(f"command failed ({code}): {shown}")


def _version(py: str, expected: str, root: pathlib.Path) -> str:
    line = _capture([py, "--version"], root=root).splitlines()[0].strip()
    if not line.startswith(f"Python {expected}."):
        raise LocalAssuranceError(
            f"{py} reports {line!r}; Python {expected}.x is required"
        )
    return line


def _gate_dir(base: pathlib.Path, source: str, gate: str) -> pathlib.Path:
    prefix, _ = EVIDENCE[gate]
    target = base / f"{prefix}-{source}"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _evidence_path(base: pathlib.Path, source: str, gate: str, key: str) -> pathlib.Path:
    directory = _gate_dir(base, source, gate)
    _, files = EVIDENCE[gate]
    return directory / files[key]


def _record_runtime(py: str, version_path: pathlib.Path, freeze_path: pathlib.Path, root: pathlib.Path) -> None:
    version_path.write_text(_capture([py, "--version"], root=root) + "\n", encoding="utf-8")
    freeze = _capture([py, "-m", "pip", "freeze"], root=root).splitlines()
    freeze_path.write_text("\n".join(sorted(freeze)) + "\n", encoding="utf-8")


def _probe_providers(py: str, target: pathlib.Path, root: pathlib.Path) -> None:
    """Optional provider availability, asked in the gate's own interpreter right after its suite."""
    _run([py, "-m", "tools.certification.skip_admission", "probe", "--out", str(target)], root=root)


def _clean_record(py: str, gate: str, target: pathlib.Path, root: pathlib.Path) -> None:
    _run(
        [py, "-m", "tools.certification.assert_clean_tree", "--gate", gate, "--record", str(target)],
        root=root,
    )


def _deselects(py: str, root: pathlib.Path) -> list[str]:
    text = _capture(
        [py, "-m", "tools.certification.recertification_scope", "self-checks", "--format", "deselect"],
        root=root,
    )
    return [line.strip() for line in text.splitlines() if line.strip()]


class _GateTracker:
    """Persist local diagnostics independently of certification evidence."""

    def __init__(self, path, source, source_tree, started_at):
        self.path = path
        self.lock = threading.Lock()
        self.timings = {}
        self.failures = {}
        self.failure_context = {}
        self.source = source
        self.source_tree = source_tree
        self.started_at = started_at

    def failure(self, name, exc):
        with self.lock:
            self.failures[name] = f"{type(exc).__name__}: {exc}"
            context = {"shard": getattr(exc, "shard", None),
                       "retained_storage": getattr(exc, "retained_storage", None)}
            details = getattr(exc, "details", None)
            if isinstance(details, dict) and details:
                context["details"] = details
            self.failure_context[name] = context
            self._persist()

    def completed(self, name, seconds):
        with self.lock:
            self.timings[name] = seconds
            if self.failures:
                self._persist()

    def _persist(self):
        names = sorted(self.failures)
        document = {
            "schema": FAILURE_SCHEMA, "status": "REFUSED",
            "provenance_mode": "local", "certifying": False,
            "safe_to_push": False, "source_commit": self.source,
            "source_tree": self.source_tree, "started_at": self.started_at,
            "recorded_at": _utc_now(), "failed_gate": names[0],
            "failed_gates": dict(sorted(self.failures.items())),
            "failure_context": dict(sorted(self.failure_context.items())),
            "failure_message": self.failures[names[0]],
            "completed_gates": sorted(self.timings),
            "gate_seconds": dict(sorted(self.timings.items())),
        }
        try:
            _write_json(self.path, document)
        except OSError:
            pass  # Diagnostic persistence cannot replace the refusal.


@contextmanager
def _mutation_scratch(root, name, performance_path=None):
    # TMPDIR itself may be repository-local: validate before any mutation runs.
    from tools.certification.mutation_workspace import OwnedRoot, require_isolated

    owner = OwnedRoot.create(prefix=f"forge-{name}-")
    temporary = owner.path
    scratch = temporary / "tree"
    try:
        require_isolated(root, scratch)
        yield scratch
    except BaseException as exc:
        exc.retained_storage = str(temporary)
        exc.shard = name
        raise
    finally:
        # Diagnostic metadata is archived beside evidence, never inside it.
        # No telemetry read/write failure can change a shard outcome.
        if performance_path is not None:
            try:
                owner.check()
                diagnostic = scratch / "performance.json"
                if diagnostic.is_symlink() or diagnostic.lstat().st_nlink != 1:
                    raise OSError("linked shard diagnostic refused")
                doc = json.loads(diagnostic.read_text(encoding="utf-8"))
                if is_performance_document(doc):
                    PerformanceTelemetry(performance_path, shard=name).write(doc)
            except Exception:
                pass
        # A runner keeps its workspace only when ownership/cleanup is unproven.
        # Do not defeat that refusal by deleting storage from the parent process.
        # An exception/hard-killed shard carries no orderly-release proof.
        # Retain the entire owned parent even if the shard removed/renamed its home.
        abnormal = sys.exc_info()[0] is not None
        owner.check()
        retained = list(scratch.glob("workspace-*")) if scratch.is_dir() else []
        if not abnormal and not retained:
            owner.remove()
        elif not abnormal:
            raise LocalAssuranceError(f"mutation workspace was not released: {retained}")


def _formal_command(py, scratch, selected, formal_pytest_workers=DEFAULT_FORMAL_PYTEST_WORKERS):
    """The Formal shard command; one pytest worker is the unchanged historical command."""
    if not isinstance(formal_pytest_workers, int) or isinstance(formal_pytest_workers, bool) \
            or formal_pytest_workers < 1:
        raise LocalAssuranceError("formal-pytest-workers must be at least 1")
    workers = (("--pytest-workers", str(formal_pytest_workers))
               if formal_pytest_workers != 1 else ())
    return [py, "-X", "utf8", "tests/mutation_guards.py", *workers, str(scratch), *selected]


def _mutation_group(jobs, workers):
    jobs = tuple(jobs)
    names = [name for name, _ in jobs]
    if len(set(names)) != len(names):
        raise LocalAssuranceError("duplicate mutation shard IDs would collide in evidence")
    if workers < 1:
        raise LocalAssuranceError("mutation-workers must be at least 1")
    if workers == 1:
        for name, job in jobs:
            job()
        return
    failures = []
    # Wait for all running shards before returning/refusing: no late evidence writes.
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(job): name for name, job in jobs}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as exc:
                failures.append((futures[future], exc))
    if failures:
        failures.sort(key=lambda row: row[0])
        raise LocalAssuranceError("mutation shards failed: " + "; ".join(
            f"{name}: {type(exc).__name__}: {exc}" for name, exc in failures
        )) from failures[0][1]


def _run_source_gates(
    root: pathlib.Path,
    source: str,
    evidence: pathlib.Path,
    py311: str,
    py312: str,
    workers: int,
    mutation_workers: int = DEFAULT_MUTATION_WORKERS,
    tracker: _GateTracker | None = None,
    formal_pytest_workers: int = DEFAULT_FORMAL_PYTEST_WORKERS,
) -> dict[str, float]:
    if tracker is None:
        tracker = _GateTracker(evidence.parent / "local-assurance-failure.json",
                               source, _git(root, "rev-parse", "HEAD^{tree}"), _utc_now())
    timings = tracker.timings

    def gate(name: str, fn) -> None:
        performance = PerformanceTelemetry(evidence.parent / "performance" / f"{name}-gate.json", shard=name)
        gate_started = performance.start()
        performance.stage("gate_started")
        print(f"\n=== {name} ===", flush=True)
        try:
            _require_head(root, source, f"before {name}")
            _require_clean(root, f"before {name}")
            started = time.monotonic()
            fn()
            _require_head(root, source, f"after {name}")
            _require_clean(root, f"after {name}")
            tracker.completed(name, round(time.monotonic() - started, 3))
        except BaseException as exc:
            tracker.failure(name, exc)
            performance.failure(exc, category="gate_failure")
            raise
        finally:
            performance.finish("gate_total", gate_started)
            performance.write()

    def fast(py: str, gate_name: str, version: str) -> None:
        directory = _gate_dir(evidence, source, gate_name)
        _, files = EVIDENCE[gate_name]
        _run(
            [py, "-m", "pytest",
             "tests/test_core_guards.py::test_every_dependency_the_tree_reaches_for_is_declared",
             "-q", "--junitxml", str(directory / files["junit_dependency_guard"])],
            root=root,
        )
        args = [
            py, "-m", "pytest", "-m", "not expensive", "-q",
            "-n", str(workers), "--dist", "loadfile",
            "--deselect", "tests/test_core_guards.py::test_every_dependency_the_tree_reaches_for_is_declared",
            *_deselects(py, root),
            "--junitxml", str(directory / files["junit_fast"]),
        ]
        _run(args, root=root)
        _probe_providers(py, directory / files["provider_availability"], root)
        _record_runtime(
            py, directory / files["python"], directory / files["pip_freeze"], root
        )
        _clean_record(py, gate_name, directory / files["gate"], root)

    gate("fast311", lambda: fast(py311, "fast311", "3.11"))
    gate("fast312", lambda: fast(py312, "fast312", "3.12"))

    def scientific() -> None:
        name = "scientific312"
        directory = _gate_dir(evidence, source, name)
        _, files = EVIDENCE[name]
        env = os.environ.copy()
        env["CRAFTY_NGSPICE_ARGV"] = "ngspice"
        args = [
            py312, "-m", "pytest", "-m", "not campaign", "-q",
            "-n", str(workers), "--dist", "loadfile",
            "--deselect", "tests/test_core_guards.py::test_every_dependency_the_tree_reaches_for_is_declared",
            "--deselect", "tests/test_heterogeneous_ngspice.py::test_a_the_provider_is_a_real_external_process",
            "--deselect", "tests/test_heterogeneous_ngspice.py::test_g2_a_genuine_non_zero_exit_is_a_provider_failure",
            "--deselect", "tests/test_heterogeneous_ngspice.py::test_j_relocating_the_provider_leaves_the_result_byte_identical",
            "--deselect", "benchmarks/model_measurement_validation/tests/test_model_measurement_validation.py::test_rebuilding_everything_reproduces_the_published_gates",
            "--deselect", "benchmarks/empirical_validation/tests/test_empirical_validation.py::test_rebuilding_everything_reproduces_the_published_gates",
            *_deselects(py312, root),
            "--junitxml", str(directory / files["junit_scientific"]),
        ]
        _run(args, root=root, env=env)
        _probe_providers(py312, directory / files["provider_availability"], root)
        _record_runtime(
            py312, directory / files["python"], directory / files["pip_freeze"], root
        )
        (directory / files["ngspice"]).write_text(
            _capture(["ngspice", "--version"], root=root) + "\n", encoding="utf-8"
        )
        _clean_record(py312, name, directory / files["gate"], root)

    gate("scientific312", scientific)

    def campaign() -> None:
        name = "campaign312"
        directory = _gate_dir(evidence, source, name)
        _, files = EVIDENCE[name]
        _run(
            [py312, "-m", "pytest", "--import-mode=importlib", "-m", "campaign", "-q",
             "--junitxml", str(directory / files["junit_campaign"])],
            root=root,
        )
        _record_runtime(
            py312, directory / files["python"], directory / files["pip_freeze"], root
        )
        _clean_record(py312, name, directory / files["gate"], root)

    gate("campaign312", campaign)

    def regression() -> None:
        name = "regression312"
        directory = _gate_dir(evidence, source, name)
        _, files = EVIDENCE[name]
        env = os.environ.copy()
        env["PYTEST_ADDOPTS"] = "--import-mode=importlib"
        _run(
            [py312, "tools/forge_check.py", "--regression", "--workers", str(workers),
             "--junitxml", str(directory / files["junit_regression"])],
            root=root, env=env,
        )
        _record_runtime(
            py312, directory / files["python"], directory / files["pip_freeze"], root
        )
        _clean_record(py312, name, directory / files["gate"], root)

    gate("regression312", regression)

    formal_jobs = []
    for index in range(SHARD_COUNT):
        name = f"formal_mutations_{index}"

        def formal(index=index, name=name) -> None:
            directory = _gate_dir(evidence, source, name)
            _, files = EVIDENCE[name]
            ids = directory / files["ids"]
            log = directory / files["log"]
            record = directory / files["record"]
            _run(
                [py312, "-m", "tools.certification.mutation_population", "select",
                 "--index", str(index), "--count", str(SHARD_COUNT), "--out", str(ids)],
                root=root,
            )
            selected = [line for line in ids.read_text(encoding="utf-8").splitlines() if line]
            with _mutation_scratch(root, name, evidence.parent / "performance" / f"{name}.json") as scratch:
                _run(
                    _formal_command(py312, scratch, selected, formal_pytest_workers),
                    root=root, log=log, env={**os.environ, "FORGE_MUTATION_SHARD": name, "FORGE_SOURCE_COMMIT": source,
                       "FORGE_SOURCE_TREE": tracker.source_tree,
                       "FORGE_ASSURANCE_EXECUTION": tracker.started_at},
                )
            _run(
                [py312, "-m", "tools.certification.mutation_population", "record",
                 "--index", str(index), "--count", str(SHARD_COUNT), "--ids", str(ids),
                 "--log", str(log), "--source-commit", source, "--out", str(record)],
                root=root,
            )
            _clean_record(py312, name, directory / EVIDENCE[name][1]["gate"], root)

        formal_jobs.append((name, lambda name=name, fn=formal: gate(name, fn)))

    _mutation_group(formal_jobs, mutation_workers)
    v4_jobs = []
    for index in range(V4_SHARD_COUNT):
        name = f"v4_mutations_{index}"

        def v4(index=index, name=name) -> None:
            directory = _gate_dir(evidence, source, name)
            _, files = EVIDENCE[name]
            ids = directory / files["ids"]
            log = directory / files["log"]
            record = directory / files["record"]
            _run(
                [py312, "-m", "tools.certification.mutation_population", "v4-select",
                 "--index", str(index), "--count", str(V4_SHARD_COUNT), "--out", str(ids)],
                root=root,
            )
            with _mutation_scratch(root, name, evidence.parent / "performance" / f"{name}.json") as scratch:
                _run(
                    [py312, "-m", "tools.certification.mutation_v4_runner",
                     "--scratch", str(scratch),
                     "--ids", str(ids), "--log", str(log)],
                    root=root, env={**os.environ, "FORGE_MUTATION_SHARD": name, "FORGE_SOURCE_COMMIT": source,
                       "FORGE_SOURCE_TREE": tracker.source_tree,
                       "FORGE_ASSURANCE_EXECUTION": tracker.started_at},
                )
            _run(
                [py312, "-m", "tools.certification.mutation_population", "v4-record",
                 "--index", str(index), "--count", str(V4_SHARD_COUNT), "--ids", str(ids),
                 "--log", str(log), "--source-commit", source, "--out", str(record)],
                root=root,
            )
            _clean_record(py312, name, directory / EVIDENCE[name][1]["gate"], root)

        v4_jobs.append((name, lambda name=name, fn=v4: gate(name, fn)))

    _mutation_group(v4_jobs, mutation_workers)

    def trust() -> None:
        name = "trust_mutations"
        directory = _gate_dir(evidence, source, name)
        _, files = EVIDENCE[name]
        _run(
            [py312, "benchmarks/trust_hardening/audit/mutations.py",
             "--json", str(directory / files["result"])],
            root=root,
        )
        _clean_record(py312, name, directory / files["gate"], root)

    gate("trust_mutations", trust)
    return timings


def _expected_evidence(source):
    return {f"{prefix}-{source}/{name}"
            for prefix, files in EVIDENCE.values() for name in files.values()}


def _evidence_file(evidence, relative):
    if not isinstance(relative, str):
        raise LocalAssuranceError("evidence path must be text")
    parts = relative.split("/")
    if not parts or any(part in {"", ".", ".."} or "\\" in part or ":" in part for part in parts):
        raise LocalAssuranceError("unsafe evidence path")
    current = evidence
    for part in parts:
        if current.is_symlink() or not current.is_dir():
            raise LocalAssuranceError("linked evidence parent refused")
        current = current / part
    metadata = current.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise LocalAssuranceError("linked or nonregular evidence refused")
    return current


def _evidence_names(evidence):
    names = set()
    for directory, dirs, files in os.walk(evidence, followlinks=False):
        base = pathlib.Path(directory)
        if base.is_symlink() or any((base / name).is_symlink() for name in dirs):
            raise LocalAssuranceError("linked evidence directory refused")
        for name in files:
            relative = (base / name).relative_to(evidence).as_posix()
            _evidence_file(evidence, relative)
            names.add(relative)
    return names


def _build_evidence_manifest(root, source, evidence, *, strict=False):
    names = _evidence_names(evidence)
    if not names or (strict and names != _expected_evidence(source)):
        raise LocalAssuranceError("evidence closure is incomplete or contains unexpected files")
    files = [{"path": name, "sha256": _sha256(_evidence_file(evidence, name)),
              "bytes": _evidence_file(evidence, name).stat().st_size} for name in sorted(names)]
    manifest = {"schema": EVIDENCE_MANIFEST_SCHEMA, "source_commit": source,
                "source_tree": _git(root, "rev-parse", "HEAD^{tree}"),
                "files": files, "file_count": len(files)}
    path = evidence.parent / "evidence-manifest.json"
    return path, _write_json(path, manifest), len(files)


def _verify_evidence_manifest(path, evidence, *, source=None, source_tree=None):
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise LocalAssuranceError("evidence manifest is missing or linked")
    digest = _sha256(path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("schema") != EVIDENCE_MANIFEST_SCHEMA:
        raise LocalAssuranceError("unsupported evidence manifest schema")
    if source is not None and (doc.get("source_commit") != source or doc.get("source_tree") != source_tree):
        raise LocalAssuranceError("evidence manifest source identity mismatch")
    rows = doc.get("files")
    if not isinstance(rows, list) or not rows or doc.get("file_count") != len(rows):
        raise LocalAssuranceError("evidence manifest file count is invalid")
    names = set()
    for row in rows:
        if not isinstance(row, dict):
            raise LocalAssuranceError("invalid evidence row")
        name = row.get("path")
        target = _evidence_file(evidence, name)
        if name in names:
            raise LocalAssuranceError("duplicate evidence row")
        names.add(name)
        if _sha256(target) != row.get("sha256") or target.stat().st_size != row.get("bytes"):
            raise LocalAssuranceError(f"evidence file changed after the manifest was frozen: {target}")
    if names != _evidence_names(evidence) or (source is not None and names != _expected_evidence(source)):
        raise LocalAssuranceError("evidence closure mismatch")
    return digest, len(rows)


def _repository_slug(root: pathlib.Path, explicit: str | None) -> str:
    if explicit:
        return explicit
    remote = _git(root, "config", "--get", "remote.origin.url")
    match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", remote)
    if not match:
        raise LocalAssuranceError("cannot infer OWNER/REPO from remote.origin.url; pass --repository")
    return f"{match.group(1)}/{match.group(2)}"


def prepare(args: argparse.Namespace) -> int:
    _require_linux()
    root = core_certificate.repo_root(pathlib.Path.cwd() / "x")
    with _assurance_lock(root):
        return _prepare_locked(args)


def _prepare_locked(args: argparse.Namespace) -> int:
    root = core_certificate.repo_root(pathlib.Path.cwd() / "x")
    assurance_root = root / args.local_root
    env_root = assurance_root / "venvs"
    _require_clean(root, "prepare")

    for version, executable in (("3.11", args.python311), ("3.12", args.python312)):
        system = _resolve_python(executable, pathlib.Path("/nonexistent"), version)
        _version(system, version, root)
        target = env_root / version
        if not target.exists():
            _run([system, "-m", "venv", str(target)], root=root)
        py = _resolve_python(None, env_root, version)
        _run([py, "-m", "pip", "install", "--upgrade", "pip"], root=root)
        _run([py, *INSTALL], root=root)
        _version(py, version, root)

    if not shutil.which("ngspice"):
        raise LocalAssuranceError("ngspice is required and was not found on PATH")
    print("LOCAL_ASSURANCE_PREPARE: PASS")
    return 0


def _quarantine_prior_run(run_root):
    """Discard admission to old evidence without deleting caller-selected data."""
    from tools.certification.mutation_workspace import OwnedRoot
    if run_root.is_symlink() or not run_root.is_dir():
        raise LocalAssuranceError("existing assurance root is linked or not a directory")
    quarantine = OwnedRoot.create(prefix=f"{run_root.name}-discarded-", parent=run_root.parent)
    quarantine.check()
    run_root.rename(quarantine.path / "previous-run")
    return quarantine.path


def run(args: argparse.Namespace) -> int:
    _require_linux()
    root = core_certificate.repo_root(pathlib.Path.cwd() / "x")
    with _assurance_lock(root):
        return _run_locked(args)


def _run_locked(args: argparse.Namespace) -> int:
    if args.mutation_workers < 1:
        raise LocalAssuranceError("mutation-workers must be at least 1")
    if args.formal_pytest_workers < 1:
        raise LocalAssuranceError("formal-pytest-workers must be at least 1")
    root = core_certificate.repo_root(pathlib.Path.cwd() / "x")
    _require_clean(root, "start")
    source = _git(root, "rev-parse", "HEAD")
    source_tree = _git(root, "rev-parse", "HEAD^{tree}")
    repository = _repository_slug(root, args.repository)
    local_root = root / args.local_root
    env_root = local_root / "venvs"
    py311 = _resolve_python(args.python311, env_root, "3.11")
    py312 = _resolve_python(args.python312, env_root, "3.12")
    _version(py311, "3.11", root)
    _version(py312, "3.12", root)
    if not shutil.which("ngspice"):
        raise LocalAssuranceError("ngspice is required and was not found on PATH")

    run_root = local_root / "assurance" / source
    if run_root.exists():
        if not args.reuse:
            raise LocalAssuranceError(
                f"local assurance directory already exists for {source}; "
                "pass --reuse to discard it and run the source gates again"
            )
        # --reuse discards evidence from this run without recursively deleting
        # a caller-selected existing directory whose ownership cannot be proven.
        # Keep its bytes in a unique quarantine sibling; never reuse gate results.
        _quarantine_prior_run(run_root)
    evidence = run_root / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    started_at = _utc_now()
    started = time.monotonic()

    tracker = _GateTracker(run_root / "local-assurance-failure.json",
                           source, source_tree, started_at)
    phase = "source_gates"
    try:
        timings = _run_source_gates(
            root, source, evidence, py311, py312, max(1, args.workers),
            args.mutation_workers, tracker, formal_pytest_workers=args.formal_pytest_workers,
        )
        _require_head(root, source, "after source gates")
        _require_clean(root, "after source gates")

        phase = "evidence_manifest"
        manifest_path, manifest_sha, manifest_count = _build_evidence_manifest(
            root, source, evidence, strict=True
        )
        _require_head(root, source, "manifest frozen")
        _require_clean(root, "manifest frozen")
        phase = "assurance_build"
        assurance = build_assurance(
            root,
            source_commit=source,
            evidence_dir=evidence,
            run=RunContext(
                repository=repository,
                run_id=None,
                run_attempt=None,
                pull_request=None,
                executed_commit=source,
                event="local",
                runner_os=platform.platform(),
                provenance_mode="local",
                evidence_manifest_sha256=manifest_sha,
                evidence_file_count=manifest_count,
            ),
        )
        assurance_path = run_root / "core-hardening-assurance.json"
        assurance_sha = _write_json(assurance_path, assurance)

        _require_head(root, source, "before certificate")
        _require_clean(root, "before certificate")
        phase = "certificate_generation"
        certificate = core_certificate.build_certificate(root, assurance=assurance)
        certificate_path = root / CERTIFICATE_PATH
        core_certificate.write_certificate(certificate_path, certificate)
        certificate_sha = _sha256(certificate_path)

        result = core_certificate.verify_certificate(
            root, certificate, require_clean=False, require_commit=True, require_current_scope=True
        )
        if not result.ok:
            raise LocalAssuranceError("generated certificate does not verify: " + "; ".join(result.problems))

        _require_head(root, source, "after certificate")
        status = _git(root, "status", "--porcelain", "--untracked-files=all")
        expected_suffix = CERTIFICATE_PATH
        rows = [line for line in status.splitlines() if line.strip()]
        if len(rows) != 1 or not rows[0].endswith(expected_suffix):
            raise LocalAssuranceError(
                f"certificate generation changed unexpected repository paths: {rows}"
            )

        finished_at = _utc_now()
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "status": "SOURCE_PASS",
            "repository": repository,
            "source_commit": source,
            "source_tree": source_tree,
            "started_at": started_at,
            "finished_at": finished_at,
            "wall_seconds": round(time.monotonic() - started, 3),
            "runner_os": platform.platform(),
            "python_3_11": _capture([py311, "--version"], root=root),
            "python_3_12": _capture([py312, "--version"], root=root),
            "ngspice": _capture(["ngspice", "--version"], root=root),
            "gate_seconds": timings,
            "evidence_manifest": manifest_path.name,
            "evidence_manifest_sha256": manifest_sha,
            "evidence_file_count": manifest_count,
            "assurance_file": assurance_path.name,
            "assurance_sha256": assurance_sha,
            "certificate_path": CERTIFICATE_PATH,
            "certificate_sha256": certificate_sha,
            "required_certificate_child_subject": CERTIFICATE_CHILD_SUBJECT,
            "skip_admission": {
                "claim": assurance["skip_admission"]["claim"],
                "totals": assurance["skip_admission"]["totals"],
                "unavailable_optional_providers": assurance["skip_admission"]["unavailable_optional_providers"],
            },
        }
        phase = "source_receipt"
        receipt_path = run_root / "local-assurance-receipt.json"
        _require_head(root, source, "before source receipt")
        receipt_sha = _write_json(receipt_path, receipt)
        _require_head(root, source, "after source receipt")

    except BaseException as exc:
        if not tracker.failures:
            tracker.failure(phase, exc)
        try:
            exc.failure_record = str(tracker.path)
        except AttributeError:
            pass
        raise

    skips = receipt["skip_admission"]
    print("\nLOCAL_ASSURANCE: SOURCE_PASS")
    print(f"SOURCE_SHA: {source}")
    print(f"SKIP_ADMISSION: skipped {skips['totals']['skipped']}, accepted {skips['totals']['accepted']}, "
          f"unexpected {skips['totals']['unexpected']}")
    print(f"CLAIM: {skips['claim']}")
    print(f"RECEIPT_SHA256: {receipt_sha}")
    print("READY_TO_COMMIT_CERTIFICATE: YES")
    print(f'NEXT: git add {CERTIFICATE_PATH} && git commit -m "{CERTIFICATE_CHILD_SUBJECT}"')
    print("SAFE_TO_PUSH: NO (run local_assurance verify after the certificate child commit)")
    return 0


def verify(args: argparse.Namespace) -> int:
    _require_linux()
    root = core_certificate.repo_root(pathlib.Path.cwd() / "x")
    with _assurance_lock(root):
        return _verify_locked(args)


def _verify_locked(args: argparse.Namespace) -> int:
    root = core_certificate.repo_root(pathlib.Path.cwd() / "x")
    _require_clean(root, "verify start")
    head = _git(root, "rev-parse", "HEAD")
    parents = _git(root, "rev-list", "--parents", "-n", "1", head).split()[1:]
    if len(parents) != 1:
        raise LocalAssuranceError("certificate child must have exactly one parent")
    source = parents[0]

    local_root = root / args.local_root
    env_root = local_root / "venvs"
    py312 = _resolve_python(args.python312, env_root, "3.12")
    _version(py312, "3.12", root)

    run_root = local_root / "assurance" / source
    receipt_path = run_root / "local-assurance-receipt.json"
    if not receipt_path.is_file():
        raise LocalAssuranceError(f"local receipt not found for source {source}")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("schema") != RECEIPT_SCHEMA or receipt.get("status") not in {"SOURCE_PASS", "PASS"} or receipt.get("source_commit") != source:
        raise LocalAssuranceError("local receipt does not bind to the certificate parent")

    evidence = run_root / "evidence"
    if receipt.get("evidence_manifest") != "evidence-manifest.json":
        raise LocalAssuranceError("receipt manifest path is invalid")
    manifest_path = run_root / "evidence-manifest.json"
    source_tree = _git(root, "rev-parse", f"{source}^{{tree}}")
    if receipt.get("source_tree") != source_tree:
        raise LocalAssuranceError("receipt source tree mismatch")
    manifest_sha, manifest_count = _verify_evidence_manifest(
        manifest_path, evidence, source=source, source_tree=source_tree)
    if manifest_sha != receipt.get("evidence_manifest_sha256") or manifest_count != receipt.get("evidence_file_count"):
        raise LocalAssuranceError("receipt and evidence manifest disagree")

    certificate_path = root / CERTIFICATE_PATH
    if _sha256(certificate_path) != receipt.get("certificate_sha256"):
        raise LocalAssuranceError("committed certificate differs from the locally produced certificate")
    certificate = json.loads(certificate_path.read_text(encoding="utf-8"))
    assurance = certificate.get("assurance") or {}
    lineage = assurance.get("lineage") or {}
    if lineage.get("provenance_mode") != "local":
        raise LocalAssuranceError("certificate does not declare local provenance")
    if lineage.get("local_evidence_manifest_sha256") != manifest_sha:
        raise LocalAssuranceError("certificate does not bind the frozen local evidence manifest")
    if lineage.get("local_evidence_file_count") != manifest_count:
        raise LocalAssuranceError("certificate evidence file count differs from the local manifest")

    child = certificate_lineage.verify_certificate_child(root)
    if not child.ok:
        raise LocalAssuranceError("certificate child verification failed:\n" + child.render())

    problems = assurance_problems(
        root, assurance, source_commit=source, certificate=certificate
    )
    if problems:
        raise LocalAssuranceError("assurance revalidation failed: " + "; ".join(problems))
    # The skip inventory is re-derived from the frozen JUnit and provider-availability evidence,
    # not read from the certificate: a hand-built or stale admission section cannot verify.
    frozen = _Evidence(evidence, source)
    derived, skip_problems = skip_admission_section(root, frozen)
    skip_problems = frozen.problems + skip_problems
    if skip_problems:
        raise LocalAssuranceError("skip admission re-derivation failed: " + "; ".join(skip_problems[:20]))
    for block in derived["gates"].values():
        for suite in block["suites"].values():
            suite.pop("unexpected_skips", None)
    if derived != assurance.get("skip_admission"):
        raise LocalAssuranceError("the certificate's skip admission is not the one the frozen evidence yields")

    _require_head(root, head, "before self checks")
    self_check = run_root / "certificate-self-checks.xml"
    self_check.unlink(missing_ok=True)
    _run(
        [py312, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         *CERTIFICATE_SELF_CHECKS, "--junitxml", str(self_check)],
        root=root,
    )
    _evidence_file(run_root, self_check.name)
    junit = junit_problems(self_check.read_bytes())
    if junit:
        raise LocalAssuranceError("certificate self-checks are incomplete: " + "; ".join(junit))
    _require_head(root, head, "verify end")
    _require_clean(root, "verify end")

    receipt["status"] = "PASS"
    receipt["certificate_child_commit"] = head
    receipt["verified_at"] = _utc_now()
    receipt["certificate_self_checks_sha256"] = _sha256(self_check)
    receipt_sha = _write_json(receipt_path, receipt)
    _require_head(root, head, "after verified receipt")

    print("\nLOCAL_ASSURANCE: PASS")
    print(f"SOURCE_SHA: {source}")
    print(f"CERTIFICATE_CHILD_SHA: {head}")
    print(f"RECEIPT_SHA256: {receipt_sha}")
    print("SAFE_TO_PUSH: YES")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--local-root", default=str(DEFAULT_ROOT))
    sub = parser.add_subparsers(dest="command", required=True)

    prep = sub.add_parser("prepare")
    prep.add_argument("--python311")
    prep.add_argument("--python312")

    execute = sub.add_parser("run")
    execute.add_argument("--python311")
    execute.add_argument("--python312")
    execute.add_argument("--repository")
    execute.add_argument("--workers", type=int, default=4)
    execute.add_argument("--mutation-workers", type=int, default=DEFAULT_MUTATION_WORKERS)
    execute.add_argument("--formal-pytest-workers", type=int, default=DEFAULT_FORMAL_PYTEST_WORKERS,
                         help="pytest-xdist workers inside one Formal mutation attempt (default 1)")
    execute.add_argument("--reuse", action="store_true")

    check = sub.add_parser("verify")
    check.add_argument("--python312")

    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            return prepare(args)
        if args.command == "run":
            return run(args)
        return verify(args)
    except (LocalAssuranceError, core_certificate.CertificationError, AssuranceError) as exc:
        # An expected refusal: the evidence, tree or environment does not support assurance.
        lines = ["", "LOCAL_ASSURANCE: REFUSED", "REFUSAL_KIND: EXPECTED_ASSURANCE_REFUSAL",
                 f"REFUSED_BY: {type(exc).__name__}", str(exc), *_failure_record_lines(exc),
                 "SAFE_TO_PUSH: NO"]
        print("\n".join(lines), file=sys.stderr, flush=True)
        return 1
    except Exception as exc:
        # A defect in the runner itself. Never swallowed and never SAFE_TO_PUSH: the traceback is
        # printed and the exit code differs from a refusal's so that the two cannot be confused.
        print("\nLOCAL_ASSURANCE: INTERNAL_ERROR\nREFUSAL_KIND: UNEXPECTED_INTERNAL_ERROR",
              file=sys.stderr, flush=True)
        traceback.print_exc()
        print("\n".join([*_failure_record_lines(exc), "SAFE_TO_PUSH: NO"]), file=sys.stderr, flush=True)
        return 2


def _failure_record_lines(exc: BaseException) -> list[str]:
    """The failure record's path and digest, when the run wrote one."""
    path = getattr(exc, "failure_record", None)
    if not path:
        return []
    target = pathlib.Path(path)
    try:
        return [f"FAILURE_RECORD: {target}", f"FAILURE_RECORD_SHA256: {_sha256(target)}"]
    except OSError:
        return [f"FAILURE_RECORD: {target} (not readable)"]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
