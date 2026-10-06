"""Authoritative workstation assurance. No network dispatch, commit or push.

Run inside the controlled Linux/WSL environment, with native 3.11/3.12 venvs:
    python -m tools.certification.local_assurance run --python311 /path/to/python --python312 /path/to/python
    python -m tools.certification.local_assurance write-certificate
    # Human commits only certification/current_core_v2.json, with exactly one parent.
    python -m tools.certification.local_assurance verify

Canonical JSON is deterministic for the recorded measurements; timestamps and
durations describe an actual run and therefore differ across executions.
The workstation is the trust root, not an independent third-party executor.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from tools.certification import core_certificate as cc
from tools.certification import hardening_assurance as ha
from tools.certification import mutation_population as mp
from tools.certification import recertification_scope as rs
from tools.certification.assert_clean_tree import gate_record, tree_problems

RECEIPT_SCHEMA = "forge.local_assurance_receipt/1"
PROMOTION_SCHEMA = "forge.local_assurance_promotion/1"
REQUIRED_PYTHONS = ("3.11", "3.12")
DEPENDENCY_GUARD = "tests/test_core_guards.py::test_every_dependency_the_tree_reaches_for_is_declared"
# These exclusions are inherited from the hardened workflow. Campaign remains
# serial; regression and broad tiers retain the same test selectors.
SCIENTIFIC_EXCLUSIONS = (
    "tests/test_heterogeneous_ngspice.py::test_a_the_provider_is_a_real_external_process",
    "tests/test_heterogeneous_ngspice.py::test_g2_a_genuine_non_zero_exit_is_a_provider_failure",
    "tests/test_heterogeneous_ngspice.py::test_j_relocating_the_provider_leaves_the_result_byte_identical",
    "benchmarks/model_measurement_validation/tests/test_model_measurement_validation.py::test_rebuilding_everything_reproduces_the_published_gates",
    "benchmarks/empirical_validation/tests/test_empirical_validation.py::test_rebuilding_everything_reproduces_the_published_gates",
)


class Refused(RuntimeError):
    """Missing/failed evidence, never a partial PASS."""


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def write(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))


def git(root: pathlib.Path, *args: str) -> str:
    p = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if p.returncode:
        raise Refused(p.stderr.strip())
    return p.stdout.strip()


def assert_source(root: pathlib.Path, source: str) -> None:
    if git(root, "rev-parse", "HEAD") != source:
        raise Refused("HEAD changed during execution")
    dirty = tree_problems(root)
    if dirty:
        raise Refused("dirty source tree: " + "; ".join(d.render() for d in dirty[:8]))


def repository(root: pathlib.Path) -> str:
    origin = git(root, "remote", "get-url", "origin")
    if not origin:
        raise Refused("repository has no origin identity")
    return origin


def evidence_directory(root: pathlib.Path, source: str) -> pathlib.Path:
    base = pathlib.Path(os.environ.get("FORGE_LOCAL_EVIDENCE_DIR", str(root / ".forge" / "assurance")))
    return base / source


def evidence_path(directory: pathlib.Path, source: str, gate: str, key: str) -> pathlib.Path:
    prefix, files = ha.EVIDENCE[gate]
    return directory / f"{prefix}-{source}" / files[key]


def safe_file(directory: pathlib.Path, relative: str) -> pathlib.Path:
    p = pathlib.PurePosixPath(relative)
    if p.is_absolute() or ".." in p.parts or "\\" in relative or ":" in relative:
        raise Refused("unsafe evidence path")
    target = directory / p
    if not target.resolve().is_relative_to(directory.resolve()) or any(
        parent.is_symlink() for parent in (target, *target.parents) if parent != directory.parent
    ):
        raise Refused("evidence symlink/path escape")
    if not target.is_file():
        raise Refused(f"missing evidence: {relative}")
    return target


PROBE = r'''
import hashlib, importlib.metadata as md, json, pathlib, platform, subprocess, sys, tomllib
from packaging.requirements import Requirement
p = subprocess.run([sys.executable, '-m', 'pip', 'check'], capture_output=True, text=True)
if p.returncode: raise RuntimeError(p.stdout + p.stderr)
project = tomllib.loads(pathlib.Path('pyproject.toml').read_text())['project']
requirements = list(project['dependencies'])
for extra in ('dev', 'mcp', 'oracles'):
    requirements.extend(project['optional-dependencies'][extra])
for text in requirements:
    r = Requirement(text)
    if r.marker and not r.marker.evaluate(): continue
    if md.version(r.name) not in r.specifier: raise RuntimeError('dependency version: ' + text)
freeze = subprocess.check_output([sys.executable, '-m', 'pip', 'freeze'], text=True)
freeze = chr(10).join(sorted(freeze.splitlines())) + chr(10)
exe = pathlib.Path(sys.executable).resolve()
print(json.dumps({'version': platform.python_version(), 'executable': str(exe),
 'executable_sha256': hashlib.sha256(exe.read_bytes()).hexdigest(), 'os': platform.platform(),
 'implementation': platform.python_implementation(), 'pip_freeze': freeze}))
'''


def probe_runtime(root: pathlib.Path, argv: Sequence[str], version: str) -> dict[str, Any]:
    try:
        p = subprocess.run([*argv, "-c", PROBE], cwd=root, env=clean_environment(), capture_output=True, text=True, timeout=120)
        if p.returncode:
            raise Refused(f"Python {version} or dependencies unavailable: {p.stderr.strip()}")
        result = json.loads(p.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        raise Refused(f"Python {version} unavailable: {exc}") from exc
    if not result["version"].startswith(version + "."):
        raise Refused(f"Python {version} required; got {result['version']}")
    result["argv"] = list(argv)
    result["pip_freeze_sha256"] = digest(result["pip_freeze"].encode())
    return result


def clean_environment() -> dict[str, str]:
    env = dict(os.environ)
    # Caller switches must not filter tests, inject code, or mask plugins.
    for key in ("PYTEST_ADDOPTS", "PYTEST_DISABLE_PLUGIN_AUTOLOAD", "PYTHONPATH", "PYTHONHOME"):
        env.pop(key, None)
    env["PYTHONUTF8"] = "1"
    env["CRAFTY_NGSPICE_ARGV"] = "ngspice"
    return env


def execute(root: pathlib.Path, argv: Sequence[str], log: pathlib.Path) -> dict[str, Any]:
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with log.open("wb") as stream:
        result = subprocess.run(list(argv), cwd=root, env=clean_environment(), stdout=stream,
                                stderr=subprocess.STDOUT)
    elapsed = time.monotonic() - started
    measurement = {"argv": list(argv), "exit_code": result.returncode,
                   "duration_seconds": elapsed, "log": log.name}
    write(log.with_name(log.name + ".result.json"), measurement)
    if result.returncode:
        raise Refused(f"gate command failed ({result.returncode}): {list(argv)}; log: {log}")
    return measurement


def gate_commands(root: pathlib.Path, directory: pathlib.Path, source: str, gate: str,
                  python: Sequence[str], scratch: pathlib.Path, workers: int) -> list[list[str]]:
    path = lambda key: str(evidence_path(directory, source, gate, key))
    pytest = [*python, "-m", "pytest", "-q", "-p", "no:cacheprovider",
              "--basetemp", str(scratch / gate / "pytest")]
    deferred = [arg for node in rs.CERTIFICATE_SELF_CHECKS for arg in ("--deselect", node)]
    if gate in ("fast311", "fast312"):
        return [pytest + [DEPENDENCY_GUARD, "--junitxml", path("junit_dependency_guard")],
                pytest + ["-m", "not expensive", "-n", str(workers), "--dist", "loadfile",
                          "--deselect", DEPENDENCY_GUARD, *deferred, "--junitxml", path("junit_fast")]]
    if gate == "scientific312":
        exclusions = [arg for node in SCIENTIFIC_EXCLUSIONS for arg in ("--deselect", node)]
        return [pytest + ["-m", "not campaign", "-n", str(workers), "--dist", "loadfile",
                          "--deselect", DEPENDENCY_GUARD, *deferred, *exclusions,
                          "--junitxml", path("junit_scientific")]]
    if gate == "campaign312":
        return [pytest + ["--import-mode=importlib", "-m", "campaign",
                          "--junitxml", path("junit_campaign")]]
    if gate == "regression312":
        return [[*python, "-m", "tools.forge_check", "--regression", "--workers", str(workers),
                 "--junitxml", path("junit_regression")]]
    if gate.startswith(("formal_mutations_", "v4_mutations_")):
        index = int(gate.rsplit("_", 1)[1])
        v4 = gate.startswith("v4_")
        count = mp.V4_SHARD_COUNT if v4 else mp.SHARD_COUNT
        population = mp.v4_population(root) if v4 else mp.canonical_population(root)
        ids = population.shard(index, count)
        if v4:
            runner = [*python, "-m", "tools.certification.mutation_v4_runner", "--scratch",
                      str(scratch / gate), "--ids", path("ids"), "--log", path("log")]
        else:
            runner = [*python, "-X", "utf8", "tests/mutation_guards.py", str(scratch / gate), *ids]
        record = [*python, "-m", "tools.certification.mutation_population",
                  "v4-record" if v4 else "record", "--index", str(index), "--count", str(count),
                  "--ids", path("ids"), "--log", path("log"), "--source-commit", source,
                  "--out", path("record")]
        return [runner, record]
    if gate == "trust_mutations":
        return [[*python, ha.TRUST_SCRIPT, "--json", path("result")]]
    raise Refused(f"unknown required gate {gate}")


def inventory(directory: pathlib.Path) -> dict[str, str]:
    return {p.relative_to(directory).as_posix(): digest(p.read_bytes())
            for p in sorted(directory.rglob("*")) if p.is_file() and p.name != "receipt.json"}


def make_receipt(root: pathlib.Path, source: str, directory: pathlib.Path, *,
                 runtimes: Mapping[str, Any], gates: Mapping[str, Any], started: str,
                 ended: str, duration: float, scratch: pathlib.Path, workers: int,
                 policy: ha.Policy = ha.Policy()) -> dict[str, Any]:
    assert_source(root, source)
    identity = repository(root)
    assurance = ha.build_assurance(root, source_commit=source, evidence_dir=directory,
        run=ha.LocalRunContext(identity, source, platform.platform()), policy=policy)
    receipt = {"schema": RECEIPT_SCHEMA, "provenance_mode": "local", "result": "PASS",
               "source_commit": source, "source_tree": git(root, "rev-parse", f"{source}^{{tree}}"),
               "repository": identity, "started_at": started, "ended_at": ended,
               "duration_seconds": duration, "os": platform.platform(), "runtimes": dict(runtimes),
               "dependency_manifest_sha256": cc.file_digest(root / "pyproject.toml"),
               "control_plane": ha.control_plane_identity(root), "gates": dict(gates),
               "scratch_directory": str(scratch), "workers": workers,
               "evidence_files": inventory(directory), "assurance": assurance}
    problems = receipt_problems(root, receipt, directory, source_commit=source, policy=policy)
    if problems:
        raise Refused("; ".join(problems))
    assert_source(root, source)
    return receipt


def receipt_problems(root: pathlib.Path, receipt: Mapping[str, Any], directory: pathlib.Path,
                     *, source_commit: str, policy: ha.Policy = ha.Policy()) -> list[str]:
    problems: list[str] = []
    try:
        if receipt.get("schema") != RECEIPT_SCHEMA or receipt.get("provenance_mode") != "local" or receipt.get("result") != "PASS":
            problems.append("receipt has no supported complete local PASS")
        if receipt.get("source_commit") != source_commit or receipt.get("source_tree") != git(root, "rev-parse", f"{source_commit}^{{tree}}"):
            problems.append("receipt source SHA/tree mismatch")
        if receipt.get("repository") != repository(root):
            problems.append("receipt repository mismatch")
        for key in ("started_at", "ended_at"):
            parsed = datetime.fromisoformat(receipt[key])
            if parsed.tzinfo is None:
                problems.append(f"receipt {key} needs timezone")
        if datetime.fromisoformat(receipt["ended_at"]) < datetime.fromisoformat(receipt["started_at"]) or not isinstance(receipt.get("duration_seconds"), (int, float)) or receipt["duration_seconds"] < 0:
            problems.append("receipt timing invalid")
        if not receipt.get("os"):
            problems.append("receipt OS identity missing")
        for version in REQUIRED_PYTHONS:
            runtime = receipt.get("runtimes", {}).get(version, {})
            if not str(runtime.get("version", "")).startswith(version + "."):
                problems.append(f"Python {version} identity missing")
            if not all(runtime.get(k) for k in ("executable", "executable_sha256", "os", "implementation", "argv")):
                problems.append(f"Python {version} runtime identity incomplete")
            freeze = runtime.get("pip_freeze", "")
            if not freeze or digest(freeze.encode()) != runtime.get("pip_freeze_sha256"):
                problems.append(f"Python {version} pip-freeze digest invalid")
        gates = receipt.get("gates", {})
        if set(gates) != set(rs.RECERTIFY_SOURCE_GATES):
            problems.append("incomplete gate evidence")
        files = receipt.get("evidence_files", {})
        expected_files = {evidence_path(directory, source_commit, g, k).relative_to(directory).as_posix()
                          for g in rs.RECERTIFY_SOURCE_GATES for k in ha.EVIDENCE[g][1]}
        if not expected_files.issubset(files):
            problems.append("incomplete evidence file inventory")
        for relative, sha in files.items():
            if digest(safe_file(directory, relative).read_bytes()) != sha:
                problems.append(f"altered evidence: {relative}")
        for gate, record in gates.items():
            runtime = "3.11" if gate == "fast311" else "3.12"
            if (record.get("result") != "success" or record.get("source_commit") != source_commit
                    or record.get("clean_before") is not True or record.get("clean_after") is not True
                    or record.get("runtime") != runtime or not record.get("commands")
                    or any(c.get("exit_code") != 0 for c in record["commands"])
                    or not isinstance(record.get("duration_seconds"), (int, float))):
                problems.append(f"{gate}: failed/incomplete gate record")
            scratch = pathlib.Path(receipt["scratch_directory"])
            if not scratch.is_absolute() or scratch.resolve().is_relative_to(root.resolve()):
                problems.append("scratch must be isolated outside source repository")
            workers = receipt["workers"]
            if type(workers) is not int or workers < 1:
                problems.append("invalid workers")
            expected = gate_commands(root, directory, source_commit, gate,
                receipt["runtimes"][runtime]["argv"], scratch, workers)
            if [c.get("argv") for c in record.get("commands", [])] != expected:
                problems.append(f"{gate}: executed commands differ from mandatory gate plan")
            for index, command in enumerate(record.get("commands", [])):
                name = (ha.EVIDENCE[gate][1]["log"] if gate.startswith("formal_mutations_") and index == 0
                        else f"command-{index}.log")
                log = evidence_path(directory, source_commit, gate, "gate").parent / name
                if command.get("log") != name or log.relative_to(directory).as_posix() not in files:
                    problems.append(f"{gate}: missing command transcript binding")
                if not isinstance(command.get("duration_seconds"), (int, float)) or command["duration_seconds"] < 0:
                    problems.append(f"{gate}: invalid command duration")
            gate_evidence = json.loads(evidence_path(directory, source_commit, gate, "gate").read_bytes())
            if gate_evidence.get("head_tree") != receipt.get("source_tree") or not gate_evidence.get("tracked_files_byte_verified"):
                problems.append(f"{gate}: clean-tree evidence does not bind source tree bytes")
        derived = ha.build_assurance(root, source_commit=source_commit, evidence_dir=directory,
            run=ha.LocalRunContext(repository(root), source_commit, receipt.get("os", "")), policy=policy)
        # Platform of the verifier is descriptive, not the measured runtime.
        derived["environment"]["certificate_builder_platform"] = receipt.get("assurance", {}).get("environment", {}).get("certificate_builder_platform")
        if derived != receipt.get("assurance"):
            problems.append("receipt assurance does not rederive from evidence")
        if receipt.get("control_plane") != ha.control_plane_identity(root):
            problems.append("receipt certification-control digest mismatch")
        if receipt.get("dependency_manifest_sha256") != cc.file_digest(root / "pyproject.toml"):
            problems.append("receipt pyproject digest mismatch")
        for version, gate in (("3.11", "fast311"), ("3.12", "fast312")):
            freeze = evidence_path(directory, source_commit, gate, "pip_freeze").read_bytes()
            if digest(freeze) != receipt.get("runtimes", {}).get(version, {}).get("pip_freeze_sha256"):
                problems.append(f"Python {version} runtime disagrees with gate evidence")
    except (KeyError, TypeError, ValueError, AttributeError, IndexError, OSError, ha.AssuranceError, Refused) as exc:
        problems.append(f"receipt refused: {exc}")
    return problems


def bound_assurance(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {**receipt["assurance"], "local_provenance": {
        "receipt_sha256": digest(canonical(receipt)), "receipt": dict(receipt)}}


def local_provenance_problems(root: pathlib.Path, assurance: Mapping[str, Any], *,
                              source_commit: str, certificate: Mapping[str, Any] | None = None,
                              policy: ha.Policy = ha.Policy()) -> list[str]:
    try:
        return _local_provenance_problems(root, assurance, source_commit=source_commit,
                                          certificate=certificate, policy=policy)
    except (KeyError, TypeError, ValueError, AttributeError, IndexError, OSError, ha.AssuranceError, Refused) as exc:
        return [f"malformed/incomplete local provenance: {exc}"]


def _local_provenance_problems(root: pathlib.Path, assurance: Mapping[str, Any], *,
                              source_commit: str, certificate: Mapping[str, Any] | None,
                              policy: ha.Policy) -> list[str]:
    binding = assurance.get("local_provenance") or {}
    receipt = binding.get("receipt") or {}
    if assurance.get("provenance_mode") != "local" or binding.get("receipt_sha256") != digest(canonical(receipt)):
        return ["local receipt provenance digest/mode mismatch"]
    directory = evidence_directory(root, source_commit)
    problems = receipt_problems(root, receipt, directory, source_commit=source_commit, policy=policy)
    if bound_assurance(receipt) != assurance:
        problems.append("certificate assurance differs from bound local receipt")
    if certificate is not None:
        if certificate.get("repository", {}).get("commit") != source_commit:
            problems.append("certificate claims a different source commit")
        area = certificate.get("manifest", {}).get("areas", {}).get(ha.CONTROL_AREA, {})
        if area.get("digest") != receipt.get("control_plane", {}).get("digest"):
            problems.append("certificate control-plane digest differs from receipt")
    return problems


def run(root: pathlib.Path, python311: Sequence[str], python312: Sequence[str], workers: int) -> pathlib.Path:
    source = git(root, "rev-parse", "HEAD")
    assert_source(root, source)
    if workers < 1:
        raise Refused("workers must be positive")
    repository(root)
    runtimes = {v: probe_runtime(root, argv, v) for v, argv in
                (("3.11", python311), ("3.12", python312))}
    require_supported_checkout(root)
    ngspice = subprocess.run(["ngspice", "--version"], capture_output=True)
    ngspice_blob = ngspice.stdout + ngspice.stderr
    if ngspice.returncode or not ha.ngspice_version(ngspice_blob):
        raise Refused("required ngspice runtime unavailable")
    directory = evidence_directory(root, source)
    if directory.exists() and any(directory.iterdir()):
        raise Refused("evidence directory already exists; preserve it or select another FORGE_LOCAL_EVIDENCE_DIR")
    directory.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    clock = time.monotonic()
    gates: dict[str, Any] = {}
    # Broad suites share a checkout and are sequential. Mutant runners already
    # isolate their edits. Never overlap serial/order-dependent campaigns.
    with tempfile.TemporaryDirectory(prefix="forge-assurance-") as temporary:
        scratch = pathlib.Path(temporary)
        for gate in rs.RECERTIFY_SOURCE_GATES:
            assert_source(root, source)
            gate_clock = time.monotonic()
            version = "3.11" if gate == "fast311" else "3.12"
            runtime = runtimes[version]
            location = evidence_path(directory, source, gate, "gate").parent
            location.mkdir(parents=True, exist_ok=True)
            layout = ha.EVIDENCE[gate][1]
            if "python" in layout:
                evidence_path(directory, source, gate, "python").write_bytes(("Python " + runtime["version"] + "\n").encode())
                evidence_path(directory, source, gate, "pip_freeze").write_bytes(runtime["pip_freeze"].encode())
            if "ngspice" in layout:
                evidence_path(directory, source, gate, "ngspice").write_bytes(ngspice_blob)
            commands = gate_commands(root, directory, source, gate, runtime["argv"], scratch, workers)
            if gate.startswith(("formal_mutations_", "v4_mutations_")):
                v4 = gate.startswith("v4_")
                population = mp.v4_population(root) if v4 else mp.canonical_population(root)
                ids = population.shard(int(gate.rsplit("_", 1)[1]), mp.V4_SHARD_COUNT if v4 else mp.SHARD_COUNT)
                evidence_path(directory, source, gate, "ids").write_bytes(("\n".join(ids) + "\n").encode())
            results = []
            print(f"LOCAL_GATE: {gate}", flush=True)
            for index, argv in enumerate(commands):
                log = (evidence_path(directory, source, gate, "log") if gate.startswith("formal_mutations_") and index == 0
                       else location / f"command-{index}.log")
                results.append(execute(root, argv, log))
                assert_source(root, source)
            current = probe_runtime(root, runtime["argv"], version)
            if current != runtime:
                raise Refused(f"{gate}: runtime changed during execution")
            assert_source(root, source)
            write(evidence_path(directory, source, gate, "gate"), gate_record(root, gate))
            gates[gate] = {"result": "success", "source_commit": source, "runtime": version,
                           "clean_before": True, "clean_after": True, "commands": results,
                           "duration_seconds": time.monotonic() - gate_clock}
            write(directory / "execution.json", {"gates": gates, "runtimes": runtimes})
    receipt = make_receipt(root, source, directory, runtimes=runtimes, gates=gates, started=started,
                           ended=datetime.now(timezone.utc).isoformat(), duration=time.monotonic() - clock,
                           scratch=scratch, workers=workers)
    assert_runtimes(root, runtimes)
    write(directory / "receipt.json", receipt)
    assert_source(root, source)
    return directory / "receipt.json"


def load_receipt(root: pathlib.Path, source: str) -> tuple[pathlib.Path, dict[str, Any]]:
    directory = evidence_directory(root, source)
    path = safe_file(directory, "receipt.json")
    receipt = json.loads(path.read_bytes())
    if canonical(receipt) != path.read_bytes():
        raise Refused("receipt serialization is not canonical")
    problems = receipt_problems(root, receipt, directory, source_commit=source)
    if problems:
        raise Refused("; ".join(problems))
    return directory, receipt


def verify(root: pathlib.Path) -> str:
    from tools.certification.certificate_lineage import verify_certificate_child
    head = git(root, "rev-parse", "HEAD")
    shape = rs.certificate_child_problems(root, head)
    if shape:
        raise Refused("; ".join(shape))
    assert_source(root, head)
    source = git(root, "rev-parse", f"{head}^")
    directory, receipt = load_receipt(root, source)
    certificate = json.loads((root / rs.CERTIFICATE_PATH).read_bytes())
    if certificate.get("assurance") != bound_assurance(receipt):
        raise Refused("child certificate does not bind the local receipt")
    lineage = verify_certificate_child(root)
    if not lineage.ok:
        raise Refused(lineage.render())
    runtime = receipt["runtimes"]["3.12"]
    assert_runtimes(root, receipt["runtimes"])
    # These checks are necessarily after generation. Their report is a separate
    # child-bound record, avoiding a receipt/certificate digest cycle.
    with tempfile.TemporaryDirectory(prefix="forge-child-") as temp:
        report = pathlib.Path(temp) / "self-checks.xml"
        log = pathlib.Path(temp) / "self-checks.log"
        measured = execute(root, [*runtime["argv"], "-m", "pytest", "-q", "-p", "no:cacheprovider",
                                 *rs.CERTIFICATE_SELF_CHECKS, "--junitxml", str(report)], log)
        problems = rs.junit_problems(report.read_bytes())
        if problems:
            raise Refused("; ".join(problems))
        assert_source(root, head)
        assert_runtimes(root, receipt["runtimes"])
        _, final_receipt = load_receipt(root, source)
        if canonical(final_receipt) != canonical(receipt):
            raise Refused("receipt changed during self-check execution")
        child_dir = directory / "children" / head
        child_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(report, child_dir / "self-checks.xml")
        shutil.copyfile(log, child_dir / "self-checks.log")
        write(child_dir / "promotion.json", {"schema": PROMOTION_SCHEMA, "source_commit": source,
             "child_commit": head, "receipt_sha256": digest(canonical(receipt)), "command": measured,
             "self_checks_sha256": digest(report.read_bytes()), "log_sha256": digest(log.read_bytes()),
             "clean_tree_after_gate": gate_record(root, "local_certificate_child")})
        assert_source(root, head)
    return digest(canonical(receipt))


def assert_runtimes(root: pathlib.Path, runtimes: Mapping[str, Any]) -> None:
    for version in REQUIRED_PYTHONS:
        runtime = runtimes[version]
        if probe_runtime(root, runtime["argv"], version) != runtime:
            raise Refused(f"Python {version}: runtime changed since measurement")


def require_supported_checkout(root: pathlib.Path) -> None:
    # The existing certified V4 copier copies .git as a directory. A linked
    # worktree cannot be substituted for that without changing its semantics.
    if not (root / ".git").is_dir() or (root / ".git").is_symlink():
        raise Refused("certified mutation harness requires a standalone Git clone, not a linked worktree")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("run", "verify", "write-certificate"), nargs="?", default="run")
    parser.add_argument("--python311", default="python3.11")
    parser.add_argument("--python312", default="python3.12")
    parser.add_argument("--workers", type=int, default=max(1, min(os.cpu_count() or 1, 8)))
    args = parser.parse_args(argv)
    try:
        root = cc.repo_root(pathlib.Path.cwd() / "x")
        if args.command == "run":
            path = run(root, [args.python311], [args.python312], args.workers)
            print(f"SOURCE_RECEIPT: {path}\nSOURCE_GATES: PASS\nCERTIFICATE_CHILD: REQUIRED")
            print("LOCAL_ASSURANCE: REFUSED\nSAFE_TO_PUSH: NO")
            return 0  # source phase complete; final promotion still refuses
        if args.command == "write-certificate":
            source = git(root, "rev-parse", "HEAD")
            assert_source(root, source)
            _, receipt = load_receipt(root, source)
            cert = cc.build_certificate(root, assurance=bound_assurance(receipt))
            assert_source(root, source)
            cc.write_certificate(root / rs.CERTIFICATE_PATH, cert)
            print(f"CERTIFICATE_CHILD_SUBJECT: {rs.CERTIFICATE_CHILD_SUBJECT}")
            print("CERTIFICATE_CHILD: commit only certification/current_core_v2.json, then run verify")
            print("LOCAL_ASSURANCE: REFUSED\nSAFE_TO_PUSH: NO")
            return 0
        sha = verify(root)
        print(f"LOCAL_ASSURANCE: PASS\nSOURCE_SHA: {git(root, 'rev-parse', 'HEAD^')}\nRECEIPT_SHA256: {sha}\nSAFE_TO_PUSH: YES")
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        print(f"REASON: {exc}\nLOCAL_ASSURANCE: REFUSED\nSAFE_TO_PUSH: NO")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
