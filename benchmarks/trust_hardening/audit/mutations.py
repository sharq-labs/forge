"""Targeted mutations for the new trust-boundary mechanisms.

This campaign is intentionally separate from ``tests/mutation_guards.py``.
The formal 79-mutant certificate harness is byte-pinned evidence about an older
population; silently adding these mutations to that number would make the old
claim mean something it never measured.

Each mutant gets a private copy of ``src/``.  The repository tests themselves
stay untouched and are executed with ``PYTHONPATH`` pointing at the mutant
source tree.  A replacement must match exactly once and the mutated file must
compile before the test result is classified.  Syntax/targeting failures are
INVALID, never counted as killed.
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


def _run_one(mutation: Mutation, scratch: pathlib.Path) -> Result:
    mutant = scratch / mutation.mutation_id
    src_copy = mutant / "src"
    shutil.copytree(ROOT / "src", src_copy)
    try:
        mutated_path = _apply(mutant, mutation)
        py_compile.compile(str(mutated_path), doraise=True)
    except Exception as exc:
        return Result(
            mutation.mutation_id,
            "INVALID",
            mutation.property,
            detail=f"{type(exc).__name__}: {exc}",
        )

    env = os.environ.copy()
    inherited = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(src_copy), str(ROOT), inherited) if part
    )
    command = [
        sys.executable,
        "-m",
        "pytest",
        *TESTS,
        "-q",
        "-p",
        "no:cacheprovider",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
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

    status = "SURVIVED" if completed.returncode == 0 else "KILLED"
    tail = "\n".join(completed.stdout.splitlines()[-20:])
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
