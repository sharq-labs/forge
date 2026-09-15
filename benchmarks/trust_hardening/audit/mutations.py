"""Targeted mutations for the new trust-boundary mechanisms.

This campaign is intentionally separate from ``tests/mutation_guards.py``.
The formal certificate harness is byte-pinned evidence about its own
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
all loaded canonical and checkout-alias project modules after the run.  The
repository root is present only so test-support modules under ``tests`` remain
importable. Any project module loaded from outside the mutant source tree makes
the mutation INVALID.

Pytest exit status is also interpreted conservatively: exit 0 means SURVIVED,
exit 1 (actual test failures) means KILLED, and collection/usage/internal-error
statuses are INVALID.  Infrastructure failures are never credited as mutation
kills.

An exit code alone is not attribution (main audit CERT-04).  Before any mutant
runs, the same suites run once against an UNMUTATED copy through the same
wrapper and environment; if that control is not green the whole round is
INVALID, because a suite that already fails would "kill" every mutant.  And a
mutant counts as KILLED only when pytest reports at least one FAILED test in
the declared suites and, where the mutation names the test that guards it
(``expect``), that test is among the failures.  Anything else is INVALID
("RED, NOT THE GUARD"), never a kill.
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
    # Round 1A: the dependency-evidence integrity matrix. TRUST-D* mutants are
    # killed by behavioural assertions in this file, so a runner without it
    # would credit nothing to the per-dependency property.
    "tests/test_independence_dependency_binding.py",
    "tests/test_trusted_consensus_gate.py",
)


@dataclass(frozen=True)
class Mutation:
    mutation_id: str
    path: str
    old: str
    new: str
    property: str
    #: Substring of the pytest node id of the test that guards this property.
    #: When set, a kill counts only if that test is among the failures.
    expect: str = ""


MUTATIONS = (
    Mutation(
        "TRUST-A1",
        "src/engcore/scientific/realizations/admission.py",
        "if model.key not in requested_model_keys:",
        "if False and model.key not in requested_model_keys:",
        "the problem must request the exact selected model/version",
        expect='test_problem_must_name_the_exact_model_version_selected',
    ),
    Mutation(
        "TRUST-A2",
        "src/engcore/scientific/realizations/admission.py",
        "if realization.model_key != model.key:",
        "if False and realization.model_key != model.key:",
        "a realization cannot silently implement another model/version",
        expect='test_realization_cannot_silently_compute_another_model_version',
    ),
    Mutation(
        "TRUST-A3",
        "src/engcore/scientific/realizations/admission.py",
        "undeclared_by_problem = sorted(model_solver_requirements - problem_solver_requirements)",
        "undeclared_by_problem = []",
        "a problem cannot weaken the selected model's computational claim",
        expect='test_problem_cannot_weaken_a_models_computational_requirements',
    ),
    Mutation(
        "TRUST-A4",
        "src/engcore/scientific/realizations/admission.py",
        "missing_solver = sorted(required_by_stack - solver_declared)",
        "missing_solver = []",
        "solver capabilities must cover model and realization requirements",
        expect='test_solver_must_cover_requirements_of_both_model_and_realization',
    ),
    Mutation(
        "TRUST-A5",
        "src/engcore/scientific/realizations/admission.py",
        "missing_science = sorted(\n        realization.required_capabilities - available_science,\n        key=lambda capability: capability.identifier,\n    )",
        "missing_science = []",
        "realization scientific dependencies must be explicitly available",
        expect='test_realization_scientific_dependencies_are_not_equated_with_solver_caps',
    ),
    Mutation(
        "TRUST-M1",
        "src/engcore/scientific/results/execution_manifest.py",
        "if missing or extra:",
        "if False and (missing or extra):",
        "artifact attestation covers exactly the artifacts the raw result declared",
        expect='test_declared_artifacts_must_be_covered_exactly_fail_closed',
    ),
    Mutation(
        "TRUST-M2",
        "src/engcore/scientific/results/execution_manifest.py",
        "if _hex_digest(claimed, label=\"manifest_digest\") != record.manifest_digest:",
        "if False and _hex_digest(claimed, label=\"manifest_digest\") != record.manifest_digest:",
        "a serialized manifest rejects post-attestation content changes",
        expect='test_serialized_manifest_verifies_its_own_content_digest',
    ),
    Mutation(
        "TRUST-R1",
        "src/engcore/execution/trusted.py",
        "if prepared_problem != expected_problem:",
        "if False and prepared_problem != expected_problem:",
        "prepare cannot swap the scientific problem admitted by the runtime",
        expect='test_prepare_cannot_switch_the_admitted_problem_before_solve',
    ),
    Mutation(
        "TRUST-R2",
        "src/engcore/execution/trusted.py",
        "if prepared.solver != solver.identity:",
        "if False and prepared.solver != solver.identity:",
        "prepare cannot switch solver identity after admission",
        expect='test_prepare_cannot_switch_solver_identity_before_solve',
    ),
    Mutation(
        "TRUST-R3",
        "src/engcore/execution/trusted.py",
        "if not isinstance(value, Quantity):",
        "if False and not isinstance(value, Quantity):",
        "raw dimensionless numbers cannot cross the trusted metric boundary",
        expect='test_raw_float_cannot_cross_the_metric_boundary_in_a_trusted_record',
    ),
    Mutation(
        "TRUST-I1",
        "src/engcore/scientific/independence_evidence.py",
        "return not self.shared_artifacts",
        "return True",
        "shared artifact bytes defeat route independence regardless of labels",
        expect='test_different_labels_on_same_verified_bytes_are_detected_as_shared_machinery',
    ),
    Mutation(
        "TRUST-I2",
        "src/engcore/scientific/independence_evidence.py",
        "return self.all_routes_verified and self.artifact_disjoint and len(self.route_findings) >= 2",
        "return self.artifact_disjoint and len(self.route_findings) >= 2",
        "missing or mismatched route evidence cannot be treated as strong independence",
        expect='test_missing_route_evidence_is_unverified_not_independent_by_silence',
    ),
    # ---- Round 1A: dependency evidence integrity -------------------------
    # Each targets the per-dependency mechanism in
    # RouteIndependenceEvidence.assess, not the older dimension-level gate.
    Mutation(
        "TRUST-D1",
        "src/engcore/scientific/independence_evidence.py",
        "for identity in sorted(declared_identities - covered_identities):",
        "for identity in sorted(frozenset()):",
        "every declared dependency identity must be covered by verified evidence of its own",
        expect='test_every_dependency_identity_requires_its_own_bound_artifact_evidence',
    ),
    Mutation(
        "TRUST-D2",
        "src/engcore/scientific/independence_evidence.py",
        "    if identity not in declared_identities:\n",
        "    if False:\n",
        "an artifact bound to an undeclared dependency identity is refused, never counted",
        expect='test_artifact_bound_to_an_undeclared_dependency_identity_is_rejected',
    ),
    Mutation(
        "TRUST-D3",
        "src/engcore/scientific/independence_evidence.py",
        "        if len(by_identity) > 1:\n",
        "        if False:\n",
        "one verified artifact cannot establish more than one declared dependency in a route",
        expect='test_C_one_blob_cannot_evidence_identities_in_two_dimensions_of_one_route',
    ),
    Mutation(
        "TRUST-D4",
        "src/engcore/scientific/independence_evidence.py",
        "                    if not _verified_against_bytes(artifact, dimension, dimension_bytes, reasons):\n"
        "                        continue\n",
        "                    _verified_against_bytes(artifact, dimension, dimension_bytes, reasons)\n",
        "a dependency is covered only after its artifact bytes re-hash to the fingerprint",
        expect='test_DEF_a_bound_artifact_whose_bytes_do_not_verify_covers_nothing',
    ),
    Mutation(
        "TRUST-D5",
        "src/engcore/scientific/independence_evidence.py",
        '    dependency_identity: str = field(default="")\n',
        '    dependency_identity: str = field(default="", compare=False)\n',
        "the dependency binding is part of fingerprint identity, so a double use stays visible",
        expect='test_same_bytes_bound_to_two_dependencies_remain_two_evidence_records',
    ),
    Mutation(
        "TRUST-D6",
        "src/engcore/scientific/independence_evidence.py",
        "        identity = canonical_component_identity(artifact.dependency_identity)\n",
        "        identity = artifact.dependency_identity\n",
        "bindings are compared as canonical identities, not as raw spellings",
        expect='test_alias_spellings_across_routes_do_not_make_one_implementation_two',
    ),
    Mutation(
        "TRUST-D7",
        "src/engcore/execution/consensus.py",
        '                    f"{_binding_label(artifact, dimension)}"\n',
        '                    ""\n',
        "the trusted check records which dependency every artifact evidences",
        expect='test_O_trusted_evidence_lines_record_the_exact_canonical_identity_of_every_artifact',
    ),
    Mutation(
        "TRUST-C1",
        "src/engcore/execution/consensus.py",
        "trusted_earned = base_earned and independence.strongly_independent",
        "trusted_earned = base_earned",
        "CROSS_SOLVER_VALIDATED requires artifact-backed independence as well as agreement",
        expect='test_forged_fingerprint_cannot_keep_cross_solver_level',
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
alias_name = "src" + ".engcore"
for name, loaded in tuple(sys.modules.items()):
    if not (
        name == "engcore"
        or name.startswith("engcore.")
        or name == alias_name
        or name.startswith(alias_name + ".")
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


#: The unmutated control. Run through the same wrapper, environment and suites.
CONTROL = Mutation(
    "CONTROL",
    "src/engcore/__init__.py",
    "",
    "",
    "the suites are green on an unmutated copy, so a red mutant is the mutation's doing",
)


def failed_tests(output: str) -> tuple[str, ...]:
    """Node ids pytest reported as FAILED in its short summary."""
    found = []
    for line in output.splitlines():
        if line.startswith("FAILED "):
            found.append(line[len("FAILED "):].split(" - ", 1)[0].strip())
    return tuple(found)


def classify(mutation: Mutation, returncode: int | None, output: str) -> tuple[str, str]:
    """(status, reason) for one mutant run. Only an attributed failure is a kill."""
    if returncode == 0:
        return "SURVIVED", ""
    if returncode != 1:
        # pytest: 2 interrupted/collection, 3 internal error, 4 usage error,
        # 5 no tests. 86/87 are our origin/contamination guards. None of these
        # prove that a behavioural assertion detected the mutation.
        return "INVALID", f"pytest exit {returncode} is not a test failure"
    failed = failed_tests(output)
    in_suites = [
        node for node in failed
        if any(node.replace("\\", "/").split("::", 1)[0].endswith(test) for test in TESTS)
    ]
    if not in_suites:
        return "INVALID", "exit 1 with no FAILED test in the declared suites"
    if mutation.expect and not any(mutation.expect in node for node in in_suites):
        return "INVALID", (
            f"RED, NOT THE GUARD: expected {mutation.expect!r} among the failures, "
            f"got {sorted(in_suites)[:5]}"
        )
    return "KILLED", ""


def _run_one(mutation: Mutation, scratch: pathlib.Path) -> Result:
    mutant = scratch / mutation.mutation_id
    src_copy = mutant / "src"
    shutil.copytree(ROOT / "src", src_copy)
    try:
        if mutation is CONTROL:
            mutated_path = src_copy / "engcore" / "__init__.py"
        else:
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
        "-rf",
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

    tail = "\n".join(completed.stdout.splitlines()[-30:])
    if mutation is CONTROL:
        status = "GREEN" if completed.returncode == 0 else "RED"
        reason = ""
    else:
        status, reason = classify(mutation, completed.returncode, completed.stdout)
    return Result(
        mutation.mutation_id,
        status,
        mutation.property,
        returncode=completed.returncode,
        detail=(f"{reason}\n{tail}" if reason else tail),
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
        control = _run_one(CONTROL, scratch)
        print(f"CONTROL: {control.status} — {control.property}", flush=True)
        if control.status != "GREEN":
            print(control.detail, flush=True)
            print("CONTROL RED: the round is void; no mutant result would be attributable.")
            return 1
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
