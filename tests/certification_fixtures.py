"""Synthetic repositories and evidence for the certification control-plane tests.

Not a test module. Every certification trust rule is exercised against a small
committed repository built in a temporary directory, never against the checkout:
the tests make commits, rewrite certificates and dirty trees on purpose, which is
exactly what a test must not do to the tree it runs in.

The synthetic repository has the same SHAPE as the real one -- a certified core,
a mutation harness with a ``MUTATIONS`` tuple, a trust-hardening runner, a
certification control plane with per-file reasons, and a dependency manifest --
and a small population, so a full source -> evidence -> assurance -> certificate
-> certificate-child cycle runs in well under a second.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
from typing import Any, Callable, Mapping, Sequence

from tools.certification import core_certificate, mutation_population
from tools.certification.assert_clean_tree import gate_record
from tools.certification.core_certificate import ScopeArea
from tools.certification.hardening_assurance import (
    EVIDENCE,
    Policy,
    RunContext,
    build_assurance,
)
from tools.certification.recertification_scope import (
    CERTIFICATE_CHILD_SUBJECT,
    CERTIFICATE_PATH,
    RECERTIFY_SOURCE_GATES,
)

FORMAL_IDS = ("G1a", "G1b", "G2a", "G2b", "G3a", "G3b", "G4a", "G4b")
TRUST_IDS = ("TRUST-X1", "TRUST-X2")
V4_IDS = ("V4X1", "V4X2", "V4X3", "V4X4", "V4X5", "V4X6", "V4X7", "V4X8")
POLICY = Policy(expected_formal_population=len(FORMAL_IDS), shard_count=4,
                expected_trust_population=len(TRUST_IDS),
                expected_v4_population=len(V4_IDS), v4_shard_count=4)
RUN = dict(repository="owner/repo", run_id=4242, run_attempt=1, pull_request=7)

CONTROL_REASONS = (
    (".github/workflows/recertify-hardened-core.yml", "runs the gates and the builder"),
    ("tools/certification/verifier.py", "decides what verifies"),
)

SCOPE = (
    ScopeArea("core", "CORE_CERTIFIED", ("src/engcore/scientific/**/*.py",), "core"),
    ScopeArea(
        "harness",
        "HARNESS",
        ("tests/mutation_guards.py", "tests/mutation_population_v4.py"),
        "harness",
    ),
    ScopeArea(
        "certification_control", "CERTIFICATION_CONTROL",
        (".github/workflows/recertify-hardened-core.yml", "tools/certification/*.py"),
        "control plane", file_reasons=CONTROL_REASONS,
    ),
    ScopeArea("runtime_dependencies", "RUNTIME_ENVIRONMENT", ("pyproject.toml",), "deps"),
)


def git(root: pathlib.Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t",
         "-c", "core.autocrlf=false", *args],
        cwd=root, check=True, capture_output=True, text=True,
    )
    return done.stdout.strip()


def write(root: pathlib.Path, relative: str, content: bytes | str) -> pathlib.Path:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
    return target


def commit(root: pathlib.Path, message: str) -> str:
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)
    return git(root, "rev-parse", "HEAD")


def make_repo(root: pathlib.Path) -> str:
    """A committed synthetic repository. Returns the first commit."""
    root.mkdir(parents=True, exist_ok=True)
    write(root, ".gitattributes", "* text=auto eol=lf\n")
    write(root, "pyproject.toml", "[project]\nname = 'synthetic'\n")
    write(root, "README.md", "synthetic\n")
    write(root, "src/engcore/scientific/__init__.py", "")
    write(root, "src/engcore/scientific/record.py", "VALUE = 1\n")
    write(root, "tools/certification/verifier.py", "def verify():\n    return True\n")
    write(root, ".github/workflows/recertify-hardened-core.yml", "name: Recertify\n")
    write(root, "tests/mutation_guards.py", "MUTATIONS = (\n" + "".join(
        f"    ({mid!r}, 'src/engcore/scientific/record.py', 'VALUE = 1', 'VALUE = 2', 'mutation {mid}'),\n"
        for mid in FORMAL_IDS
    ) + ")\n")
    write(root, "tests/mutation_population_v4.py", (
        "NOT_MUTATED = 'NOT_MUTATED'\n"
        "POPULATION_V4 = (\n"
        + "".join(
            f"    ({mid!r}, 'src/engcore/scientific/record.py', 'VALUE = 1', 'VALUE = 2', "
            f"'tests/test_v4.py::test_guard', 'KILLED', 'synthetic guard', (), 'synthetic'),\n"
            for mid in V4_IDS
        )
        + ")\n"
    ))
    write(root, "benchmarks/trust_hardening/audit/mutations.py", (
        "from __future__ import annotations\n\n"
        "from dataclasses import dataclass\n\n\n"
        "@dataclass(frozen=True)\n"
        "class Mutation:\n"
        "    mutation_id: str\n"
        "    property: str\n\n\n"
        "MUTATIONS = (\n"
        + "".join(f"    Mutation({mid!r}, 'guards something'),\n" for mid in TRUST_IDS)
        + ")\n"
    ))
    git(root, "init", "-q")
    return commit(root, "synthetic source")


# ---------------------------------------------------------------------------
# evidence, in the formats the real gates write
# ---------------------------------------------------------------------------
def harness_log(
    ids: Sequence[str],
    *,
    verdicts: Mapping[str, str] | None = None,
    control: str = "GREEN",
    tally: tuple[int, int] | None = None,
    extra_lines: Sequence[str] = (),
) -> bytes:
    """A transcript in ``tests/mutation_guards.py``'s exact print format."""
    verdicts = dict(verdicts or {})
    lines = [f"{'CONTROL':6} {control:20} unmutated copy, 18s -- a red result below is the mutation's doing",
             f"{'':26} 470 passed in 17.73s", ""]
    killed = 0
    for mid in ids:
        verdict = verdicts.get(mid, "RED")
        killed += verdict in ("RED", "RED (refused at import)")
        lines.append(f"{mid:5} {verdict:20} mutation {mid}")
        lines.append(f"{'':26} code 0123456789abcdef -> fedcba9876543210   CONTRACT_REFUSAL   20s")
        lines.append(f"{'':26} 1 failed, 469 passed in 18.00s")
    lines.extend(extra_lines)
    lines.append("")
    done, total = tally if tally is not None else (killed, len(ids))
    lines.append(f"{done}/{total} mutations were killed by the guard they name.")
    return ("\n".join(lines) + "\n").encode("utf-8")


def v4_log(ids: Sequence[str], *, control: str = "GREEN") -> bytes:
    lines = [f"{mid} test_guard -> KILLED | synthetic" for mid in ids]
    lines.append(f"CONTROL (unmutated, 1 test(s)) {control} | synthetic")
    return ("\n".join(lines) + "\n").encode("utf-8")


JUNIT_OK = (b'<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest" '
            b'errors="0" failures="0" skipped="0" tests="3"><testcase classname="tests.t" name="a"/>'
            b'<testcase classname="tests.t" name="b"/><testcase classname="tests.t" name="c"/>'
            b'</testsuite></testsuites>')


def trust_result(ids: Sequence[str] = TRUST_IDS, status: Callable[[str], str] = lambda _: "KILLED") -> dict[str, Any]:
    rows = [{"mutation_id": mid, "status": status(mid), "property": "p", "returncode": 1, "detail": ""} for mid in ids]
    return {
        "schema": "forge.trust_mutation_assurance/1",
        "population": len(rows),
        "killed": sum(r["status"] == "KILLED" for r in rows),
        "survived": sum(r["status"] == "SURVIVED" for r in rows),
        "invalid": sum(r["status"] == "INVALID" for r in rows),
        "tests": [],
        "results": rows,
    }


def write_evidence(root: pathlib.Path, source: str, directory: pathlib.Path) -> pathlib.Path:
    """Every artifact certify downloads, for ``source`` checked out at ``root``."""
    def put(gate: str, key: str, blob: bytes) -> None:
        prefix, files = EVIDENCE[gate]
        target = directory / f"{prefix}-{source}" / files[key]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)

    for gate in RECERTIFY_SOURCE_GATES:
        put(gate, "gate", json.dumps(gate_record(root, gate)).encode())
    for gate, version in (("fast311", "3.11"), ("fast312", "3.12")):
        put(gate, "python", f"Python {version}.9\n".encode())
        put(gate, "pip_freeze", f"numpy==2.0.0\npytest==8.0.0 # {version}\n".encode())
        put(gate, "junit_dependency_guard", JUNIT_OK)
        put(gate, "junit_fast", JUNIT_OK)
    shared_312_freeze = b"numpy==2.0.0\npytest==8.0.0 # 3.12\n"
    put("scientific312", "python", b"Python 3.12.9\n")
    put("scientific312", "pip_freeze", shared_312_freeze)
    put("scientific312", "ngspice", b"******\n** ngspice-42 : Circuit level simulation program\n******\n")
    put("scientific312", "junit_scientific", JUNIT_OK)
    put("campaign312", "python", b"Python 3.12.9\n")
    put("campaign312", "pip_freeze", shared_312_freeze)
    put("campaign312", "junit_campaign", JUNIT_OK)
    put("regression312", "python", b"Python 3.12.9\n")
    put("regression312", "pip_freeze", shared_312_freeze)
    put("regression312", "junit_regression", JUNIT_OK)
    population = mutation_population.canonical_population(root)
    for index in range(POLICY.shard_count):
        gate = f"formal_mutations_{index}"
        ids = population.shard(index, POLICY.shard_count)
        ids_text = "\n".join(ids) + "\n"
        log = harness_log(ids)
        put(gate, "ids", ids_text.encode())
        put(gate, "log", log)
        record = mutation_population.build_shard_record(
            root, index=index, count=POLICY.shard_count, ids_text=ids_text,
            log_bytes=log, source_commit=source, expected_count=POLICY.expected_formal_population,
        )
        put(gate, "record", json.dumps(record).encode())
    v4_population = mutation_population.v4_population(root)
    for index in range(POLICY.v4_shard_count):
        gate = f"v4_mutations_{index}"
        ids = v4_population.shard(index, POLICY.v4_shard_count)
        ids_text = "\n".join(ids) + "\n"
        log = v4_log(ids)
        put(gate, "ids", ids_text.encode())
        put(gate, "log", log)
        record = mutation_population.build_v4_shard_record(
            root, index=index, count=POLICY.v4_shard_count, ids_text=ids_text,
            log_bytes=log, source_commit=source, expected_count=POLICY.expected_v4_population,
        )
        put(gate, "record", json.dumps(record).encode())
    put("trust_mutations", "result", json.dumps(trust_result()).encode())
    return directory


def certify(root: pathlib.Path, evidence_dir: pathlib.Path, *, executed: str | None = None) -> dict[str, Any]:
    """What the certify job does at ``HEAD``: assurance from evidence, then the builder."""
    source = git(root, "rev-parse", "HEAD")
    write_evidence(root, source, evidence_dir)
    assurance = build_assurance(
        root, source_commit=source, evidence_dir=evidence_dir,
        run=RunContext(executed_commit=executed or source, **RUN), policy=POLICY,
    )
    return core_certificate.build_certificate(root, assurance=assurance, certification_id="SYNTHETIC")


def commit_child(root: pathlib.Path, certificate: Mapping[str, Any] | bytes,
                 *, subject: str = CERTIFICATE_CHILD_SUBJECT) -> str:
    target = root / CERTIFICATE_PATH
    if isinstance(certificate, bytes):
        write(root, CERTIFICATE_PATH, certificate)
    else:
        core_certificate.write_certificate(target, certificate)
    git(root, "add", CERTIFICATE_PATH)
    git(root, "commit", "-q", "-m", subject)
    return git(root, "rev-parse", "HEAD")


def sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()
