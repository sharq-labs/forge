"""Build the hardened-core assurance record from evidence, and validate one.

    python -m tools.certification.hardening_assurance check-executed-scope \\
        --executed <merge-preview sha> --source <sha>
    python -m tools.certification.hardening_assurance build \\
        --source-commit <sha> --evidence-dir DIR --out FILE \\
        --repository OWNER/REPO --run-id N --run-attempt N --pull-request N \\
        --executed-commit <merge-preview sha>

WHAT CHANGED FROM ``forge.core_hardening_assurance/2``
------------------------------------------------------
Version 2 was assembled in an inline workflow script from job OUTPUT STRINGS.
It wrote ``"passed": true`` for every functional gate whatever those jobs had
run, asserted ``"population": 13, "survived": 0`` for the trust mutations as
literals, and proved formal mutation coverage by checking that four integers
summed to 79. Version 3 means something different, so it has a new schema
rather than a reinterpretation of the old one:

* **Source identity** -- ``source_commit`` plus the source tree id.
* **Test execution evidence** -- per gate, the gate's own clean-tree record
  (which commit it measured, that it left the checkout byte-identical) and the
  JUnit counts of each suite it ran, with the report digests. Nothing says
  "passed" without the report it was read from.
* **Mutation population identity** -- the canonical ordered population, its
  digests, every shard's exact ids and transcript digest, and the coverage
  proof (see :mod:`tools.certification.mutation_population`).
* **Trust-hardening population identity** -- ids, counts and statuses read
  from the result file and checked against the runner's own ``MUTATIONS``.
* **Runtime identity** -- interpreter versions, pip-freeze digests and the
  ngspice version, read from the gates' artifacts, plus the digest of the
  dependency manifest they installed from.
* **Control-plane identity** -- the digest of the ``certification_control``
  scope area at the source commit, and proof that the merge-preview commit the
  workflow actually executed from carries the same certified bytes.
* **Lineage** -- the only parent a certificate child may have, and the exact
  workflow run and attempt that produced the certificate, which the child
  checks against GitHub (:mod:`tools.certification.certificate_lineage`).

Every value is derived from a downloaded artifact or from the tree at the
source commit. Job output strings are not read.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import platform
import re
import runpy
import subprocess
import sys
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from tools.certification import core_certificate
from tools.certification import mutation_population as formal
from tools.certification.assert_clean_tree import GATE_RECORD_SCHEMA
from tools.certification.recertification_scope import (
    CERTIFICATE_SELF_CHECKS,
    RECERTIFY_SOURCE_GATES,
    match,
)

ASSURANCE_SCHEMA = "forge.core_hardening_assurance/4"
ENVIRONMENT_SCHEMA = "forge.certification_environment/3"
WORKFLOW_PATH = ".github/workflows/recertify-hardened-core.yml"
CONTROL_AREA = "certification_control"
DEPENDENCY_MANIFEST = "pyproject.toml"
INSTALL_COMMAND = 'python -m pip install -e ".[dev,mcp,oracles]"'

TRUST_SCRIPT = "benchmarks/trust_hardening/audit/mutations.py"
TRUST_RESULT_SCHEMA = "forge.trust_mutation_assurance/1"
#: The trust-hardening population a certificate claims, read off the runner's own
#: ``MUTATIONS`` rather than asserted: 13 through PR #43, 20 from Round 1A, which
#: added TRUST-D1..D7 against per-dependency evidence integrity (coverage only
#: after byte verification, one verified artifact per dependency, canonical
#: bindings, the recorded binding). ``tests/test_hardening_assurance.py`` fails
#: if this and the runner ever disagree.
EXPECTED_TRUST_POPULATION = 20

#: Where each gate's evidence lands when certify downloads every artifact whose
#: name ends in the source commit: ``<evidence-dir>/<prefix>-<source>/<file>``.
#: The workflow uploads under exactly these names; a missing file fails the
#: build, so a renamed step cannot quietly drop evidence.
EVIDENCE: dict[str, tuple[str, dict[str, str]]] = {
    "fast311": ("core-fast-311", {
        "python": "python-3.11.txt",
        "pip_freeze": "pip-freeze-3.11.txt",
        "junit_dependency_guard": "junit-dependency-guard-3.11.xml",
        "junit_fast": "junit-fast-3.11.xml",
        "gate": "gate-fast311.json",
    }),
    "fast312": ("core-fast-312", {
        "python": "python-3.12.txt",
        "pip_freeze": "pip-freeze-3.12.txt",
        "junit_dependency_guard": "junit-dependency-guard-3.12.xml",
        "junit_fast": "junit-fast-3.12.xml",
        "gate": "gate-fast312.json",
    }),
    "scientific312": ("core-scientific", {
        "ngspice": "ngspice-version.txt",
        "junit_scientific": "junit-scientific-3.12.xml",
        "gate": "gate-scientific312.json",
    }),
    "campaign312": ("core-campaign", {
        "junit_campaign": "junit-campaign-3.12.xml",
        "gate": "gate-campaign312.json",
    }),
    "regression312": ("core-regression", {
        "junit_regression": "junit-regression-3.12.xml",
        "gate": "gate-regression312.json",
    }),
    **{
        f"formal_mutations_{index}": (f"core-formal-mutations-{index}", {
            "ids": f"formal-mutation-ids-{index}.txt",
            "log": f"formal-mutations-{index}.log",
            "record": f"formal-mutations-{index}.json",
            "gate": f"gate-formal_mutations_{index}.json",
        })
        for index in range(formal.SHARD_COUNT)
    },
    "trust_mutations": ("core-trust-mutations", {
        "result": "trust-mutations.json",
        "gate": "gate-trust_mutations.json",
    }),
}

FUNCTIONAL = (
    ("fast_python_3_11", "fast311", ("junit_dependency_guard", "junit_fast")),
    ("fast_python_3_12", "fast312", ("junit_dependency_guard", "junit_fast")),
    ("scientific_python_3_12", "scientific312", ("junit_scientific",)),
    ("campaign_python_3_12", "campaign312", ("junit_campaign",)),
    ("false_confidence_regression_python_3_12", "regression312", ("junit_regression",)),
)

#: The most skipped tests each functional suite may report and still count as a
#: gate. A gate used to require only "tests > 0, no failures, no errors", so a
#: trust test that started skipping -- a missing optional dependency, a new
#: skipif -- was accepted as silently as a passing one. These are the counts the
#: last certificate measured (FAST 19, SCIENTIFIC 5, dependency guard 0).
#: Raising one is a recorded decision in the same recertified change, never a
#: side effect.
SKIP_CEILING: Mapping[str, int] = {
    "junit_dependency_guard": 0,
    "junit_fast": 19,
    "junit_scientific": 5,
    "junit_campaign": 0,
    "junit_regression": 0,
}


def skip_problem(suite: str, counts: Mapping[str, Any]) -> str | None:
    """Why ``counts`` skips more than ``suite`` may, or ``None``."""
    ceiling = SKIP_CEILING.get(suite)
    if ceiling is None:
        return f"{suite}: no skip ceiling is declared; refusing to accept an unbounded skip count"
    skipped = int(counts.get("skipped") or 0)
    if skipped > ceiling:
        return (
            f"{suite}: {skipped} tests skipped, above the declared ceiling of {ceiling}; "
            "a skipped trust test is not a passing one"
        )
    return None


class AssuranceError(RuntimeError):
    """The evidence does not support an assurance record. Every reason is listed."""

    def __init__(self, problems: Sequence[str]):
        self.problems = list(problems)
        super().__init__("\n".join(f"- {p}" for p in self.problems))


@dataclass(frozen=True)
class Policy:
    """The numbers a certificate claims. Tests substitute a small synthetic policy."""

    expected_formal_population: int = formal.EXPECTED_FORMAL_POPULATION
    shard_count: int = formal.SHARD_COUNT
    expected_trust_population: int = EXPECTED_TRUST_POPULATION


@dataclass(frozen=True)
class RunContext:
    repository: str
    run_id: int
    run_attempt: int
    pull_request: int | None
    executed_commit: str
    event: str = "pull_request"
    runner_os: str = ""


def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _git(root: pathlib.Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          encoding="utf-8", errors="surrogateescape")
    if done.returncode != 0:
        raise AssuranceError([f"git {' '.join(args)} failed: {done.stderr.strip()}"])
    return done.stdout


# ---------------------------------------------------------------------------
# independent facts from the tree
# ---------------------------------------------------------------------------
def trust_population(root: pathlib.Path) -> tuple[str, ...]:
    """The trust-hardening runner's own ``MUTATIONS`` ids, in order."""
    namespace = runpy.run_path(str(root / TRUST_SCRIPT), run_name="_trust_population_probe")
    return tuple(str(mutation.mutation_id) for mutation in namespace["MUTATIONS"])


def control_plane_identity(root: pathlib.Path) -> dict[str, Any]:
    """The ``certification_control`` area as the current scope table enumerates it."""
    area = next((a for a in core_certificate.SCOPE if a.name == CONTROL_AREA), None)
    if area is None:
        raise AssuranceError([f"the scope table has no {CONTROL_AREA!r} area"])
    files = {rel: core_certificate.file_digest(root / rel)
             for rel in core_certificate.enumerate_area(root, area)}
    return {"area": CONTROL_AREA, "digest": core_certificate.area_digest(files),
            "file_count": len(files)}


def certified_blobs(root: pathlib.Path, commit: str) -> dict[str, str]:
    """``path -> blob id`` for every file at ``commit`` that a scope pattern certifies."""
    patterns = [p for area in core_certificate.SCOPE for p in area.patterns]
    blobs: dict[str, str] = {}
    for entry in _git(root, "ls-tree", "-r", "--full-tree", "-z", commit).split("\0"):
        if not entry:
            continue
        meta, _, path = entry.partition("\t")
        parts = pathlib.PurePosixPath(path)
        if "__pycache__" in parts.parts or parts.suffix in (".pyc", ".pyo"):
            continue
        if any(match(pattern, path) for pattern in patterns):
            blobs[path] = meta.split()[2]
    return blobs


def executed_scope_problems(root: pathlib.Path, executed: str, source: str) -> list[str]:
    """Why the commit the workflow ran from does not carry the certified bytes.

    A ``pull_request`` workflow runs the YAML of the MERGE PREVIEW, not of the
    head. If the base moved and changed a workflow or any certified file, the
    control plane that executed is not the one the certificate would record,
    and the tree that would merge is not the tree that was measured.
    """
    left, right = certified_blobs(root, executed), certified_blobs(root, source)
    differing = sorted(p for p in set(left) | set(right) if left.get(p) != right.get(p))
    if not differing:
        return []
    return [
        f"the executed merge preview {executed[:12]} and the source {source[:12]} "
        f"differ in certified files {differing[:10]}"
        + (f" (+{len(differing) - 10} more)" if len(differing) > 10 else "")
        + ". Update the branch from its base and let recertification run again"
    ]


# ---------------------------------------------------------------------------
# reading evidence
# ---------------------------------------------------------------------------
def junit_counts(xml_bytes: bytes) -> dict[str, int]:
    """Totals over every ``testsuite`` in a JUnit report."""
    document = ElementTree.fromstring(xml_bytes)
    suites = [document] if document.tag == "testsuite" else list(document.iter("testsuite"))
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for key in totals:
            totals[key] += int(suite.get(key, "0"))
    return totals


class _Evidence:
    def __init__(self, directory: pathlib.Path, source: str):
        self.directory, self.source = directory, source
        self.problems: list[str] = []

    def path(self, gate: str, key: str) -> pathlib.Path:
        prefix, files = EVIDENCE[gate]
        return self.directory / f"{prefix}-{self.source}" / files[key]

    def read(self, gate: str, key: str) -> bytes | None:
        target = self.path(gate, key)
        if not target.is_file():
            self.problems.append(f"{gate}: missing evidence {target.relative_to(self.directory).as_posix()}")
            return None
        return target.read_bytes()

    def gate(self, gate: str) -> dict[str, Any] | None:
        blob = self.read(gate, "gate")
        if blob is None:
            return None
        record = json.loads(blob)
        if record.get("schema") != GATE_RECORD_SCHEMA:
            self.problems.append(f"{gate}: gate record schema {record.get('schema')!r}")
        if record.get("gate") != gate:
            self.problems.append(f"{gate}: gate record names gate {record.get('gate')!r}")
        if record.get("head_commit") != self.source:
            self.problems.append(f"{gate}: measured {record.get('head_commit')!r}, not the source {self.source}")
        if record.get("clean_tree_after_gate") is not True:
            self.problems.append(f"{gate}: did not prove a clean checkout after running")
        return {"record": record, "sha256": sha256_bytes(blob)}


def ngspice_version(blob: bytes | None) -> str:
    """The identifying line of ``ngspice --version`` output, or ``""``.

    The first line ngspice prints is a row of asterisks. Version 2 recorded
    that line, so every certificate said its scientific provider was
    ``******``. The line that names the build is the one carrying
    ``ngspice-<version>``.
    """
    for line in (blob or b"").decode("utf-8", "replace").splitlines():
        if re.search(r"ngspice-\d", line):
            return line.strip(" *	")
    return ""


def _first_line(blob: bytes | None) -> str:
    return blob.decode("utf-8", "replace").strip().splitlines()[0].strip() if blob and blob.strip() else ""


def build_assurance(
    root: pathlib.Path,
    *,
    source_commit: str,
    evidence_dir: pathlib.Path,
    run: RunContext,
    policy: Policy = Policy(),
) -> dict[str, Any]:
    """The assurance record for ``source_commit``. Raises with every problem found."""
    evidence = _Evidence(evidence_dir, source_commit)
    problems = evidence.problems
    head = _git(root, "rev-parse", "HEAD").strip()
    if head != source_commit:
        problems.append(f"certify is running on {head}, not the source {source_commit}")
    problems += executed_scope_problems(root, run.executed_commit, source_commit)

    gates = {gate: evidence.gate(gate) for gate in RECERTIFY_SOURCE_GATES}

    functional: dict[str, Any] = {}
    for label, gate, suites in FUNCTIONAL:
        entry: dict[str, Any] = {"gate": gate, "suites": {}}
        if gates.get(gate):
            entry.update(result="success", head_commit=source_commit,
                         clean_tree_after_gate=True, gate_record_sha256=gates[gate]["sha256"])
        for suite in suites:
            blob = evidence.read(gate, suite)
            if blob is None:
                continue
            try:
                counts = junit_counts(blob)
            except ElementTree.ParseError as exc:
                problems.append(f"{gate}: {suite} is not a JUnit report ({exc})")
                continue
            if counts["tests"] <= 0 or counts["failures"] or counts["errors"]:
                problems.append(f"{gate}: {suite} reports {counts}; a gate needs tests and no failures or errors")
            skipped = skip_problem(suite, counts)
            if skipped:
                problems.append(f"{gate}: {skipped}")
            entry["suites"][suite.removeprefix("junit_")] = {**counts, "junit_sha256": sha256_bytes(blob)}
        functional[label] = entry
    functional["deferred_self_checks"] = list(CERTIFICATE_SELF_CHECKS)
    functional["note"] = (
        "Each functional gate ran on the source commit in its own job and proved "
        "its checkout byte-identical to that commit afterwards. The listed "
        "self-checks read the previous certificate on a source commit, so they are "
        "deselected there and run -- and must each be reported PASSED -- on the "
        "certificate-only child."
    )

    # formal guard mutations: population from the tree, verdicts from transcripts
    population = formal.canonical_population(root)
    records: list[dict[str, Any]] = []
    logs: dict[int, bytes] = {}
    for index in range(policy.shard_count):
        gate = f"formal_mutations_{index}"
        record_blob, log_blob, ids_blob = (evidence.read(gate, k) for k in ("record", "log", "ids"))
        if record_blob is None or log_blob is None or ids_blob is None:
            continue
        record = json.loads(record_blob)
        listed = tuple(line for line in ids_blob.decode("utf-8").splitlines() if line)
        if listed != tuple(record.get("selected_ids") or ()):
            problems.append(f"{gate}: its id file and its record disagree about what it ran")
        records.append(record)
        logs[index] = log_blob
    problems += formal.coverage_problems(
        population, records, shard_count=policy.shard_count,
        expected_count=policy.expected_formal_population, logs=logs,
        source_commit=source_commit,
    )

    # trust-hardening mutations: statuses from the result, population from the runner
    trust_blob = evidence.read("trust_mutations", "result")
    trust_ids = trust_population(root)
    trust_section: dict[str, Any] = {}
    if trust_blob is not None:
        result = json.loads(trust_blob)
        problems += trust_result_problems(result, trust_ids, policy)
        trust_section = {
            "script": TRUST_SCRIPT,
            "result_schema": result.get("schema"),
            "population": len(trust_ids),
            "expected_population": policy.expected_trust_population,
            "population_sha256": formal.sha256_lines(trust_ids),
            "ids": list(trust_ids),
            "killed": result.get("killed"),
            "survived": result.get("survived"),
            "invalid": result.get("invalid"),
            "result_sha256": sha256_bytes(trust_blob),
            "claim": (
                "Fresh trust-boundary mutation population on the source commit in "
                "an independent gate; ids and statuses read from its result file "
                "and checked against the runner's own MUTATIONS"
            ),
        }

    python_311 = _first_line(evidence.read("fast311", "python"))
    python_312 = _first_line(evidence.read("fast312", "python"))
    freeze_311 = evidence.read("fast311", "pip_freeze")
    freeze_312 = evidence.read("fast312", "pip_freeze")
    ngspice_blob = evidence.read("scientific312", "ngspice")
    ngspice = ngspice_version(ngspice_blob)
    if python_311 and not python_311.startswith("Python 3.11."):
        problems.append(f"fast311 ran under {python_311!r}")
    if python_312 and not python_312.startswith("Python 3.12."):
        problems.append(f"fast312 ran under {python_312!r}")
    if ngspice_blob is not None and not ngspice:
        problems.append("scientific312 recorded no ngspice-<version> line in its provider evidence")

    if problems:
        raise AssuranceError(problems)

    return {
        "schema": ASSURANCE_SCHEMA,
        "source_commit": source_commit,
        "source_tree": _git(root, "rev-parse", f"{source_commit}^{{tree}}").strip(),
        "execution_model": "parallel_gates_then_certificate",
        "functional": functional,
        "formal_guard_mutations": formal.assurance_section(population, records, shard_count=policy.shard_count),
        "trust_hardening_mutations": trust_section,
        "environment": {
            "schema": ENVIRONMENT_SCHEMA,
            "source_commit": source_commit,
            "execution_model": "parallel_github_actions_jobs",
            "runner_os": run.runner_os,
            "certificate_builder_platform": platform.platform(),
            "python_3_11": python_311,
            "python_3_12": python_312,
            "pip_freeze_3_11_sha256": sha256_bytes(freeze_311 or b""),
            "pip_freeze_3_12_sha256": sha256_bytes(freeze_312 or b""),
            "ngspice": ngspice,
            "install": INSTALL_COMMAND,
            "dependency_manifest": {
                "path": DEPENDENCY_MANIFEST,
                "sha256": core_certificate.file_digest(root / DEPENDENCY_MANIFEST),
            },
            "workflow": WORKFLOW_PATH,
        },
        "control_plane": {
            **control_plane_identity(root),
            "executed_merge_preview_commit": run.executed_commit,
            "executed_certified_bytes_match_source": True,
        },
        "lineage": {
            "source_commit": source_commit,
            "certificate_parent": source_commit,
            "rule": (
                "the certificate-only child that commits this certificate has "
                "exactly one parent, and it is source_commit"
            ),
            "repository": run.repository,
            "workflow": WORKFLOW_PATH,
            "workflow_run_id": run.run_id,
            "workflow_run_attempt": run.run_attempt,
            "event": run.event,
            "pull_request": run.pull_request,
            "certify_job": "certify",
            "source_gates": list(RECERTIFY_SOURCE_GATES),
            "certificate_artifact": f"hardened-core-assurance-{source_commit}",
        },
        "policy": (
            "Built by tools/certification/hardening_assurance.py from the evidence "
            "artifacts of every source gate for this source commit, after all of "
            "them succeeded, and embedded by the official certificate builder."
        ),
    }


def trust_result_problems(result: Mapping[str, Any], ids: Sequence[str], policy: Policy) -> list[str]:
    problems: list[str] = []
    if result.get("schema") != TRUST_RESULT_SCHEMA:
        problems.append(f"trust mutations: result schema {result.get('schema')!r}")
    if len(ids) != policy.expected_trust_population:
        problems.append(f"trust mutations: the runner declares {len(ids)} mutations, the certificate claims {policy.expected_trust_population}")
    rows = list(result.get("results") or ())
    reported = tuple(str(row.get("mutation_id")) for row in rows)
    if reported != tuple(ids):
        problems.append(f"trust mutations: result ids {list(reported)} are not the runner's population {list(ids)}")
    not_killed = sorted(f"{row.get('mutation_id')}={row.get('status')}" for row in rows if row.get("status") != "KILLED")
    if not_killed:
        problems.append(f"trust mutations: not killed {not_killed}")
    counts = (result.get("population"), result.get("killed"), result.get("survived"), result.get("invalid"))
    if counts != (len(ids), len(ids), 0, 0):
        problems.append(f"trust mutations: population/killed/survived/invalid {counts}, expected {(len(ids), len(ids), 0, 0)}")
    return problems


# ---------------------------------------------------------------------------
# validating a stored record -- on the certificate child, against the tree
# ---------------------------------------------------------------------------
def assurance_problems(
    root: pathlib.Path,
    assurance: Mapping[str, Any],
    *,
    source_commit: str,
    certificate: Mapping[str, Any] | None = None,
    policy: Policy = Policy(),
) -> list[str]:
    """Why a stored assurance record does not support its certificate at ``root``.

    Every population and digest is recomputed from the tree; nothing the record
    says about itself is used to check itself.
    """
    problems: list[str] = []
    if assurance.get("schema") != ASSURANCE_SCHEMA:
        return [f"assurance schema is {assurance.get('schema')!r}; a certificate child requires {ASSURANCE_SCHEMA!r}"]

    functional = assurance.get("functional") or {}
    for label, gate, suites in FUNCTIONAL:
        entry = functional.get(label) or {}
        if entry.get("gate") != gate or entry.get("result") != "success":
            problems.append(f"functional.{label}: no successful {gate} result")
        if entry.get("head_commit") != source_commit or entry.get("clean_tree_after_gate") is not True:
            problems.append(f"functional.{label}: not proved on a clean checkout of {source_commit}")
        for suite in suites:
            counts = (entry.get("suites") or {}).get(suite.removeprefix("junit_")) or {}
            if not counts.get("tests") or counts.get("failures") != 0 or counts.get("errors") != 0:
                problems.append(f"functional.{label}.{suite}: {counts or 'absent'}")
            elif skip_problem(suite, counts):
                problems.append(f"functional.{label}.{skip_problem(suite, counts)}")
    if list(functional.get("deferred_self_checks") or ()) != list(CERTIFICATE_SELF_CHECKS):
        problems.append("functional.deferred_self_checks is not the self-check list this verifier runs")

    section = assurance.get("formal_guard_mutations") or {}
    population = formal.canonical_population(root)
    if section.get("population_sha256") != population.sha256 or list(section.get("ids") or ()) != list(population.ids):
        problems.append("formal_guard_mutations: the recorded population is not tests/mutation_guards.py's MUTATIONS")
    if section.get("definitions_sha256") != population.definitions_sha256:
        problems.append("formal_guard_mutations: the recorded mutation definitions differ from the harness")
    if section.get("population") != policy.expected_formal_population or section.get("shard_count") != policy.shard_count:
        problems.append(f"formal_guard_mutations: population {section.get('population')} in {section.get('shard_count')} shards, expected {policy.expected_formal_population} in {policy.shard_count}")
    records = []
    for key, shard in sorted((section.get("shards") or {}).items()):
        if shard.get("killed_count") != shard.get("selected_count") or shard.get("control") != "GREEN":
            problems.append(f"formal_guard_mutations: shard {key} does not record every selected mutation killed after a green control")
        records.append({
            "schema": formal.SHARD_RECORD_SCHEMA, "shard_index": int(key), "shard_count": section.get("shard_count"),
            "population_sha256": section.get("population_sha256"), "definitions_sha256": section.get("definitions_sha256"),
            "population_count": section.get("population"), **shard,
        })
    problems += formal.coverage_problems(population, records, shard_count=policy.shard_count,
                                         expected_count=policy.expected_formal_population)

    trust = assurance.get("trust_hardening_mutations") or {}
    ids = trust_population(root)
    if list(trust.get("ids") or ()) != list(ids) or trust.get("population_sha256") != formal.sha256_lines(ids):
        problems.append("trust_hardening_mutations: the recorded population is not the runner's MUTATIONS")
    if (trust.get("population"), trust.get("killed"), trust.get("survived"), trust.get("invalid")) != (
        policy.expected_trust_population, policy.expected_trust_population, 0, 0
    ):
        problems.append(f"trust_hardening_mutations: {trust.get('population')}/{trust.get('killed')} killed, "
                        f"{trust.get('survived')} survived, {trust.get('invalid')} invalid")

    environment = assurance.get("environment") or {}
    if environment.get("schema") != ENVIRONMENT_SCHEMA:
        problems.append(f"environment schema {environment.get('schema')!r}")
    manifest = environment.get("dependency_manifest") or {}
    if manifest.get("path") != DEPENDENCY_MANIFEST or manifest.get("sha256") != core_certificate.file_digest(root / DEPENDENCY_MANIFEST):
        problems.append("environment.dependency_manifest does not match pyproject.toml in this tree")
    for key in ("python_3_11", "python_3_12", "ngspice", "pip_freeze_3_11_sha256", "pip_freeze_3_12_sha256"):
        if not environment.get(key):
            problems.append(f"environment.{key} is absent")

    control = assurance.get("control_plane") or {}
    identity = control_plane_identity(root)
    if {k: control.get(k) for k in identity} != identity:
        problems.append(f"control_plane {({k: control.get(k) for k in identity})} is not this tree's {identity}")
    if control.get("executed_certified_bytes_match_source") is not True:
        problems.append("control_plane does not record that the executed workflow carried the certified bytes")
    if certificate is not None:
        stored = ((certificate.get("manifest") or {}).get("areas") or {}).get(CONTROL_AREA) or {}
        if stored.get("digest") != control.get("digest"):
            problems.append("control_plane digest disagrees with the certificate's certification_control area")

    lineage = assurance.get("lineage") or {}
    if lineage.get("workflow") != WORKFLOW_PATH or lineage.get("certify_job") != "certify":
        problems.append("lineage does not name the recertify workflow's certify job")
    if not isinstance(lineage.get("workflow_run_id"), int) or lineage.get("workflow_run_id", 0) <= 0:
        problems.append("lineage.workflow_run_id is absent")
    if not isinstance(lineage.get("workflow_run_attempt"), int) or lineage.get("workflow_run_attempt", 0) < 1:
        problems.append("lineage.workflow_run_attempt is absent")
    if not lineage.get("repository"):
        problems.append("lineage.repository is absent")
    if list(lineage.get("source_gates") or ()) != list(RECERTIFY_SOURCE_GATES):
        problems.append("lineage.source_gates is not the gate list this verifier requires")
    return problems


# ---------------------------------------------------------------------------
def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    executed = commands.add_parser("check-executed-scope")
    executed.add_argument("--executed", required=True)
    executed.add_argument("--source", required=True)
    build = commands.add_parser("build")
    build.add_argument("--source-commit", required=True)
    build.add_argument("--evidence-dir", required=True)
    build.add_argument("--out", required=True)
    build.add_argument("--repository", required=True)
    build.add_argument("--run-id", type=int, required=True)
    build.add_argument("--run-attempt", type=int, required=True)
    build.add_argument("--pull-request", type=int)
    build.add_argument(
        "--event",
        choices=("pull_request", "workflow_dispatch"),
        default="pull_request",
    )
    build.add_argument("--executed-commit", required=True)
    args = parser.parse_args(argv)
    root = core_certificate.repo_root(pathlib.Path.cwd() / "x")

    try:
        if args.command == "check-executed-scope":
            problems = executed_scope_problems(root, args.executed, args.source)
            if problems:
                raise AssuranceError(problems)
            print(f"the executed merge preview carries the source's certified bytes")
            return 0
        record = build_assurance(
            root,
            source_commit=args.source_commit,
            evidence_dir=pathlib.Path(args.evidence_dir),
            run=RunContext(
                repository=args.repository, run_id=args.run_id,
                run_attempt=args.run_attempt, pull_request=args.pull_request,
                executed_commit=args.executed_commit, event=args.event,
                runner_os=os.environ.get("RUNNER_OS", ""),
            ),
        )
    except AssuranceError as exc:
        print("ASSURANCE REFUSED:\n" + str(exc), file=sys.stderr)
        return 1
    target = pathlib.Path(args.out)
    target.write_bytes((json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    formal_section = record["formal_guard_mutations"]
    print(f"wrote {target}")
    print(f"  formal population {formal_section['population']} {formal_section['population_sha256'][:16]}")
    print(f"  trust population  {record['trust_hardening_mutations']['population']}")
    print(f"  control plane     {record['control_plane']['digest'][:16]}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
