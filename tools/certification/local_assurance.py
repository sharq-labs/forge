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
from typing import Any, Mapping, Sequence

from tools.certification import certificate_lineage, core_certificate
from tools.certification.assert_clean_tree import tree_problems
from tools.certification.hardening_assurance import (
    EVIDENCE,
    RunContext,
    assurance_problems,
    build_assurance,
)
from tools.certification.recertification_scope import (
    CERTIFICATE_PATH,
    CERTIFICATE_SELF_CHECKS,
    CERTIFICATE_CHILD_SUBJECT,
    junit_problems,
)

RECEIPT_SCHEMA = "forge.local_assurance_receipt/1"
EVIDENCE_MANIFEST_SCHEMA = "forge.local_assurance_evidence_manifest/1"
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
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


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
        )
        assert process.stdout is not None
        for line in process.stdout:
            sys.stdout.write(line)
            handle.write(line)
        code = process.wait()
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


def _run_source_gates(
    root: pathlib.Path,
    source: str,
    evidence: pathlib.Path,
    py311: str,
    py312: str,
    workers: int,
) -> dict[str, float]:
    timings: dict[str, float] = {}

    def gate(name: str, fn) -> None:
        print(f"\n=== {name} ===", flush=True)
        _require_head(root, source, f"before {name}")
        _require_clean(root, f"before {name}")
        started = time.monotonic()
        fn()
        _require_head(root, source, f"after {name}")
        timings[name] = round(time.monotonic() - started, 3)

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

    for index in range(4):
        name = f"formal_mutations_{index}"

        def formal(index=index, name=name) -> None:
            directory = _gate_dir(evidence, source, name)
            _, files = EVIDENCE[name]
            ids = directory / files["ids"]
            log = directory / files["log"]
            record = directory / files["record"]
            _run(
                [py312, "-m", "tools.certification.mutation_population", "select",
                 "--index", str(index), "--count", "4", "--out", str(ids)],
                root=root,
            )
            selected = [line for line in ids.read_text(encoding="utf-8").splitlines() if line]
            _run(
                [py312, "-X", "utf8", "tests/mutation_guards.py",
                 str(directory / f"scratch-{index}"), *selected],
                root=root, log=log,
            )
            _run(
                [py312, "-m", "tools.certification.mutation_population", "record",
                 "--index", str(index), "--count", "4", "--ids", str(ids),
                 "--log", str(log), "--source-commit", source, "--out", str(record)],
                root=root,
            )
            _clean_record(py312, name, directory / EVIDENCE[name][1]["gate"], root)

        gate(name, formal)

    for index in range(8):
        name = f"v4_mutations_{index}"

        def v4(index=index, name=name) -> None:
            directory = _gate_dir(evidence, source, name)
            _, files = EVIDENCE[name]
            ids = directory / files["ids"]
            log = directory / files["log"]
            record = directory / files["record"]
            _run(
                [py312, "-m", "tools.certification.mutation_population", "v4-select",
                 "--index", str(index), "--count", "8", "--out", str(ids)],
                root=root,
            )
            _run(
                [py312, "-m", "tools.certification.mutation_v4_runner",
                 "--scratch", str(directory / f"scratch-{index}"),
                 "--ids", str(ids), "--log", str(log)],
                root=root,
            )
            _run(
                [py312, "-m", "tools.certification.mutation_population", "v4-record",
                 "--index", str(index), "--count", "8", "--ids", str(ids),
                 "--log", str(log), "--source-commit", source, "--out", str(record)],
                root=root,
            )
            _clean_record(py312, name, directory / EVIDENCE[name][1]["gate"], root)

        gate(name, v4)

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


def _build_evidence_manifest(root: pathlib.Path, source: str, evidence: pathlib.Path) -> tuple[pathlib.Path, str, int]:
    files: list[dict[str, Any]] = []
    for path in sorted(p for p in evidence.rglob("*") if p.is_file()):
        files.append({
            "path": path.relative_to(evidence).as_posix(),
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
        })
    if not files:
        raise LocalAssuranceError("no evidence files were produced")
    manifest = {
        "schema": EVIDENCE_MANIFEST_SCHEMA,
        "source_commit": source,
        "source_tree": _git(root, "rev-parse", "HEAD^{tree}"),
        "files": files,
        "file_count": len(files),
    }
    path = evidence.parent / "evidence-manifest.json"
    digest = _write_json(path, manifest)
    return path, digest, len(files)


def _verify_evidence_manifest(path: pathlib.Path, evidence: pathlib.Path) -> tuple[str, int]:
    if not path.is_file():
        raise LocalAssuranceError(f"evidence manifest is missing: {path}")
    digest = _sha256(path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("schema") != EVIDENCE_MANIFEST_SCHEMA:
        raise LocalAssuranceError(f"unsupported evidence manifest schema {doc.get('schema')!r}")
    rows = list(doc.get("files") or ())
    if doc.get("file_count") != len(rows) or not rows:
        raise LocalAssuranceError("evidence manifest file count is invalid")
    for row in rows:
        target = evidence / str(row.get("path") or "")
        if not target.is_file():
            raise LocalAssuranceError(f"evidence file is missing: {target}")
        if _sha256(target) != row.get("sha256") or target.stat().st_size != row.get("bytes"):
            raise LocalAssuranceError(f"evidence file changed after the manifest was frozen: {target}")
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


def run(args: argparse.Namespace) -> int:
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
    if run_root.exists() and not args.reuse:
        shutil.rmtree(run_root)
    evidence = run_root / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    started_at = _utc_now()
    started = time.monotonic()

    timings = _run_source_gates(
        root, source, evidence, py311, py312, max(1, args.workers)
    )
    _require_head(root, source, "after source gates")
    _require_clean(root, "after source gates")

    manifest_path, manifest_sha, manifest_count = _build_evidence_manifest(
        root, source, evidence
    )
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

    certificate = core_certificate.build_certificate(root, assurance=assurance)
    certificate_path = root / CERTIFICATE_PATH
    core_certificate.write_certificate(certificate_path, certificate)
    certificate_sha = _sha256(certificate_path)

    result = core_certificate.verify_certificate(
        root, certificate, require_clean=False, require_commit=True, require_current_scope=True
    )
    if not result.ok:
        raise LocalAssuranceError("generated certificate does not verify: " + "; ".join(result.problems))

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
        "ngspice": _capture(["ngspice", "--version"], root=root).splitlines()[-1],
        "gate_seconds": timings,
        "evidence_manifest": manifest_path.name,
        "evidence_manifest_sha256": manifest_sha,
        "evidence_file_count": manifest_count,
        "assurance_file": assurance_path.name,
        "assurance_sha256": assurance_sha,
        "certificate_path": CERTIFICATE_PATH,
        "certificate_sha256": certificate_sha,
        "required_certificate_child_subject": CERTIFICATE_CHILD_SUBJECT,
    }
    receipt_path = run_root / "local-assurance-receipt.json"
    receipt_sha = _write_json(receipt_path, receipt)

    print("\nLOCAL_ASSURANCE: SOURCE_PASS")
    print(f"SOURCE_SHA: {source}")
    print(f"RECEIPT_SHA256: {receipt_sha}")
    print("READY_TO_COMMIT_CERTIFICATE: YES")
    print(f'NEXT: git add {CERTIFICATE_PATH} && git commit -m "{CERTIFICATE_CHILD_SUBJECT}"')
    print("SAFE_TO_PUSH: NO (run local_assurance verify after the certificate child commit)")
    return 0


def verify(args: argparse.Namespace) -> int:
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
    if receipt.get("schema") != RECEIPT_SCHEMA or receipt.get("source_commit") != source:
        raise LocalAssuranceError("local receipt does not bind to the certificate parent")

    evidence = run_root / "evidence"
    manifest_path = run_root / str(receipt.get("evidence_manifest") or "")
    manifest_sha, manifest_count = _verify_evidence_manifest(manifest_path, evidence)
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

    self_check = run_root / "certificate-self-checks.xml"
    _run(
        [py312, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         *CERTIFICATE_SELF_CHECKS, "--junitxml", str(self_check)],
        root=root,
    )
    junit = junit_problems(self_check.read_bytes())
    if junit:
        raise LocalAssuranceError("certificate self-checks are incomplete: " + "; ".join(junit))
    _require_clean(root, "verify end")

    receipt["status"] = "PASS"
    receipt["certificate_child_commit"] = head
    receipt["verified_at"] = _utc_now()
    receipt["certificate_self_checks_sha256"] = _sha256(self_check)
    receipt_sha = _write_json(receipt_path, receipt)

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
    except (LocalAssuranceError, core_certificate.CertificationError) as exc:
        print(f"LOCAL_ASSURANCE: REFUSED\n{exc}\nSAFE_TO_PUSH: NO", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
