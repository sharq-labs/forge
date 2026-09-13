"""Targeted mutations for the new trust-boundary mechanisms.

This campaign is intentionally separate from ``tests/mutation_guards.py``.
The formal 79-mutant certificate harness is byte-pinned evidence about an older
population; silently adding these mutations to that number would make the old
claim mean something it never measured.

Each mutant gets a private copy of ``src/``.  The repository tests themselves
stay untouched.  A replacement must match exactly once and the mutated file
must compile before the test result is classified.

Import isolation is load-bearing.  This repository's pytest configuration adds
``src`` and ``.`` to ``sys.path``; if ordinary ``python -m pytest`` were used,
a mutant could pass its pre-flight import check and then pytest could prepend
the checkout's original ``src`` again.  Every mutation therefore runs through
a small same-process wrapper which imports the mutated module *before* pytest,
overrides pytest's ``pythonpath`` option to the mutant source tree, and audits
all loaded ``engcore``/``src.engcore`` modules after the run.  The repository
root is present only so test-support modules under ``tests`` remain importable.
Any project module loaded from outside the mutant source tree makes the mutation
INVALID.

Pytest exit status is also interpreted conservatively: exit 0 means SURVIVED,
exit 1 (actual test failures) means KILLED, and collection/usage/internal-error
statuses are INVALID.  Infrastructure failures are never credited as mutation
kills.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import py_compile
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass

ROOT = pathlib.Path(__file__).resolve().parents[3]

TESTS = (
    "tests/test_execution_admission.py",
    "tests/test_execution_manifest.py",
    "tests/test_trusted_execution_runtime.py",
    "tests/test_independence_evidence.py",
    "tests/test_trusted_consensus_gate.py",
)


@dataclass(frozen=True)
class Mutation:
    mutation_id: str
    path: str
    old: str
    new: str
    property: str


MUTATIONS = (
    Mutation(
        "TRUST-A1",
        "src/engcore/scientific/realizations/admission.py",
        "if model.key not in requested_model_keys:",
        "if False and model.key not in requested_model_keys:",
        "the problem must request the exact selected model/version",
    ),
    Mutation(
        "TRUST-A2",
        "src/engcore/scientific/realizations/admission.py",
        "if realization.model_key != model.key:",
        "if False and realization.model_key != model.key:",
        "a realization cannot silently implement another model/version",
    ),
    Mutation(
        "TRUST-A3",
        "src/engcore/scientific/realizations/admission.py",
        "undeclared_by_problem = sorted(model_solver_requirements - problem_solver_requirements)",
        "undeclared_by_problem = []",
        "a problem cannot weaken the selected model's computational claim",
    ),
    Mutation(
        "TRUST-A4",
        "src/engcore/scientific/realizations/admission.py",
        "missing_solver = sorted(required_by_stack - solver_declared)",
        "missing_solver = []",
        "solver capabilities must cover model and realization requirements",
    ),
    Mutation(
        "TRUST-A5",
        "src/engcore/scientific/realizations/admission.py",
        "missing_science = sorted(\n        realization.required_capabilities - available_science,\n        key=lambda capability: capability.identifier,\n    )",
        "missing_science = []",
        "realization scientific dependencies must be explicitly available",
    ),
    Mutation(
        "TRUST-M1",
        "src/engcore/scientific/results/execution_manifest.py",
        "if missing or extra:",
        "if False and (missing or extra):",
        "artifact attestation covers exactly the artifacts the raw result declared",
    ),
    Mutation(
        "TRUST-M2",
        "src/engcore/scientific/results/execution_manifest.py",
        "if _hex_digest(claimed, label=\"manifest_digest\") != record.manifest_digest:",
        "if False and _hex_digest(claimed, label=\"manifest_digest\") != record.manifest_digest:",
        "a serialized manifest rejects post-attestation content changes",
    ),
    Mutation(
        "TRUST-R1",
        "src/engcore/execution/trusted.py",
        "if prepared_problem != expected_problem:",
        "if False and prepared_problem != expected_problem:",
        "prepare cannot swap the scientific problem admitted by the runtime",
    ),
    Mutation(
        "TRUST-R2",
        "src/engcore/execution/trusted.py",
        "if prepared.solver != solver.identity:",
        "if False and prepared.solver != solver.identity:",
        "prepare cannot switch solver identity after admission",
    ),
    Mutation(
        "TRUST-R3",
        "src/engcore/execution/trusted.py",
        "if not isinstance(value, Quantity):",
        "if False and not isinstance(value, Quantity):",
        "raw dimensionless numbers cannot cross the trusted metric boundary",
    ),
    Mutation(
        "TRUST-I1",
        "src/engcore/scientific/independence_evidence.py",
        "return not self.shared_artifacts",
        "return True",
        "shared artifact bytes defeat route independence regardless of labels",
    ),
    Mutation(
        "TRUST-I2",
        "src/engcore/scientific/independence_evidence.py",
        "return self.all_routes_verified and self.artifact_disjoint and len(self.route_findings) >= 2",
        "return self.artifact_disjoint and len(self.route_findings) >= 2",
        "missing or mismatched route evidence cannot be treated as strong independence",
    ),
    Mutation(
        "TRUST-C1",
        "src/engcore/execution/consensus.py",
        "trusted_earned = base_earned and independence.strongly_independent",
        "trusted_earned = base_earned",
        "CROSS_SOLVER_VALIDATED requires artifact-backed independence as well as agreement",
    ),
)


@dataclass
class Result:
    mutation_id: str
    status: str
    property: str
    returncode: int | None = None
    detail: str = ""


def _apply(root: pathlib.Path, mutation: Mutation) -> pathlib.Path:
    path = root / mutation.path
    text = path.read_text(encoding="utf-8")
    count = text.count(mutation.old)
    if count != 1:
        raise RuntimeError(
            f"expected exactly one target in {mutation.path}, found {count}"
        )
    path.write_text(text.replace(mutation.old, mutation.new, 1), encoding="utf-8")
    return path


def _module_name_for_path(path: str) -> str:
    relative = pathlib.PurePosixPath(path)
    parts = list(relative.parts)
    if not parts or parts[0] != "src" or len(parts) < 3:
        raise RuntimeError(f"mutation path is not a src Python module: {path}")
    module_parts = parts[1:]
    filename = module_parts[-1]
    if not filename.endswith(".py"):
        raise RuntimeError(f"mutation path is not a Python module: {path}")
    stem = filename[:-3]
    if stem == "__init__":
        module_parts = module_parts[:-1]
    else:
        module_parts[-1] = stem
    return ".".join(module_parts)


def _mutant_environment(src_copy: pathlib.Path) -> dict[str, str]:
    env = os.environ.copy()
    # mutant source must win; repository root is second only so tests.* helper
    # modules remain importable. ROOT/src is intentionally absent.
    env["PYTHONPATH"] = os.pathsep.join((str(src_copy), str(ROOT)))
    env["PYTHONNOUSERSITE"] = "1"
    return env


_PYTEST_WRAPPER = r'''
import importlib
import pathlib
import sys

module_name = sys.argv[1]
expected_path = pathlib.Path(sys.argv[2]).resolve()
mutant_src = pathlib.Path(sys.argv[3]).resolve()
pytest_args = sys.argv[4:]

module = importlib.import_module(module_name)
actual_path = pathlib.Path(module.__file__).resolve()
print(f"MUTANT_IMPORT {module_name} -> {actual_path}")
if actual_path != expected_path:
    print(f"IMPORT_ORIGIN_MISMATCH expected={expected_path} actual={actual_path}")
    raise SystemExit(86)

import pytest
returncode = pytest.main(pytest_args)

outside = []
for name, loaded in tuple(sys.modules.items()):
    if not (
        name == "engcore"
        or name.startswith("engcore.")
        or name == "src.engcore"
        or name.startswith("src.engcore.")
    ):
        continue
    filename = getattr(loaded, "__file__", None)
    if not filename:
        continue
    path = pathlib.Path(filename).resolve()
    try:
        path.relative_to(mutant_src)
    except ValueError:
        outside.append((name, str(path)))

if outside:
    print("MUTANT_SOURCE_CONTAMINATION")
    for name, path in sorted(outside):
        print(f"  {name}: {path}")
    raise SystemExit(87)

raise SystemExit(returncode)
'''


def _run_one(mutation: Mutation, scratch: pathlib.Path) -> Result:
    mutant = scratch / mutation.mutation_id
    src_copy = mutant / "src"
    shutil.copytree(ROOT / "src", src_copy)
    try:
        mutated_path = _apply(mutant, mutation)
        py_compile.compile(str(mutated_path), doraise=True)
        module_name = _module_name_for_path(mutation.path)
    except Exception as exc:
        return Result(
            mutation.mutation_id,
            "INVALID",
            mutation.property,
            detail=f"{type(exc).__name__}: {exc}",
        )

    env = _mutant_environment(src_copy)
    command = [
        sys.executable,
        "-c",
        _PYTEST_WRAPPER,
        module_name,
        str(mutated_path),
        str(src_copy),
        *(str(ROOT / test) for test in TESTS),
        "--rootdir",
        str(ROOT),
        # Override pyproject.toml's ["src", "."] so ROOT/src cannot overtake
        # the mutant source. ROOT itself arrives via the process PYTHONPATH for
        # tests.route_declarations_for_tests and other test helpers.
        "-o",
        f"pythonpath={src_copy}",
        "-q",
        "-p",
        "no:cacheprovider",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=mutant,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=180,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return Result(
            mutation.mutation_id,
            "INVALID",
            mutation.property,
            detail=f"test timeout after {exc.timeout}s",
        )

    if completed.returncode == 0:
        status = "SURVIVED"
    elif completed.returncode == 1:
        status = "KILLED"
    else:
        # pytest: 2 interrupted/collection, 3 internal error, 4 usage error,
        # 5 no tests. 86/87 are our origin/contamination guards. None of these
        # prove that a behavioural assertion detected the mutation.
        status = "INVALID"
    tail = "\n".join(completed.stdout.splitlines()[-30:])
    return Result(
        mutation.mutation_id,
        status,
        mutation.property,
        returncode=completed.returncode,
        detail=tail,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", dest="json_path")
    parser.add_argument("--scratch")
    args = parser.parse_args(argv)

    scratch_context = None
    if args.scratch:
        scratch = pathlib.Path(args.scratch).resolve()
        scratch.mkdir(parents=True, exist_ok=True)
    else:
        scratch_context = tempfile.TemporaryDirectory(prefix="forge-trust-mutations-")
        scratch = pathlib.Path(scratch_context.name)

    results: list[Result] = []
    try:
        for mutation in MUTATIONS:
            result = _run_one(mutation, scratch)
            results.append(result)
            print(f"{result.mutation_id}: {result.status} — {result.property}", flush=True)
            if result.status != "KILLED" and result.detail:
                print(result.detail, flush=True)
    finally:
        if scratch_context is not None:
            scratch_context.cleanup()

    summary = {
        "schema": "forge.trust_mutation_assurance/1",
        "population": len(results),
        "killed": sum(result.status == "KILLED" for result in results),
        "survived": sum(result.status == "SURVIVED" for result in results),
        "invalid": sum(result.status == "INVALID" for result in results),
        "tests": list(TESTS),
        "results": [asdict(result) for result in results],
    }
    encoded = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.json_path:
        pathlib.Path(args.json_path).write_text(encoded, encoding="utf-8")
    print(encoded, end="")

    return 0 if summary["survived"] == 0 and summary["invalid"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
