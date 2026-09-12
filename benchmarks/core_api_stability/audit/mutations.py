"""Sprint 10 mutation matrix: break each API/serialization guard once.

Every requested candidate stays in the denominator. A mutation that cannot be
written against this codebase is recorded with the reason, not dropped -- a
denominator that quietly shrinks to the mutations that happened to pass is the
failure the whole apparatus exists to prevent.

Separate from the certified 79 for the standing reason: `tests/mutation_guards.py`
is inside certified scope and pinned, so a guard written this round cannot join
MUTATIONS without invalidating the snapshot.

    python -X utf8 benchmarks/core_api_stability/audit/mutations.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parents[3]
PYTHON = str(ROOT / ".venv" / "Scripts" / "python.exe")
BASETEMP = "D:/fbt_s10"

EXEC_INIT = "src/engcore/execution/__init__.py"
SWEEP = "src/engcore/execution/sweep.py"
PARAMS = "src/engcore/inference/parameters.py"
SNAPSHOT = "src/engcore/api_snapshot.py"
SERIAL = "src/engcore/scientific/serialization.py"
QUANTITY = "src/engcore/scientific/units/quantity.py"
ERRORS = "src/engcore/scientific/errors.py"
GRID = "src/engcore/inference/grid.py"
PYPROJECT = "pyproject.toml"

T_SNAP = "tests/test_core_api_snapshot.py"
T_CONTRACT = "tests/test_core_api_contracts.py"
T_SER = "tests/test_core_api_serialization.py"
T_LAYER = "tests/test_core_api_layering.py"
T_GUARDS = "tests/test_core_guards.py"

MUTATIONS = (
    # ---- API ----------------------------------------------------------
    ("API-1", EXEC_INIT,
     [('    "cases_from",\n', "")],
     f"{T_SNAP}::test_the_public_api_matches_the_pinned_snapshot",
     "a frozen export is removed from __all__"),

    ("API-2", SWEEP,
     [("def run_sweep(definition: SweepDefinition, *, workers: int = 1) -> SweepSummary:",
       "def run_sweep(definition: SweepDefinition, *, workers: int = 2) -> SweepSummary:")],
     f"{T_SNAP}::test_parameter_kinds_and_defaults_are_unchanged",
     "a frozen default is changed"),

    ("API-3", SWEEP,
     [("def run_sweep(definition: SweepDefinition, *, workers: int = 1) -> SweepSummary:",
       "def run_sweep(definition: SweepDefinition, workers: int = 1) -> SweepSummary:")],
     f"{T_SNAP}::test_parameter_kinds_and_defaults_are_unchanged",
     "a keyword-only argument becomes positional-or-keyword"),

    ("API-4", SWEEP,
     [('    NOT_RUN = "not_run"', "")],
     f"{T_SNAP}::test_enum_members_and_values_are_unchanged",
     "an enum member is removed"),

    ("API-5", PARAMS,
     [("    name: str\n    unit: str\n    model: ModelReference",
       "    unit: str\n    name: str\n    model: ModelReference")],
     f"{T_SNAP}::test_public_dataclass_fields_keep_their_order",
     "a public dataclass field order is changed"),

    # ---- SERIALIZATION ------------------------------------------------
    ("SER-1", SERIAL,
     [("    if cls is dict:\n"
       "        return {str(k): encode(value[k]) for k in sorted(value, key=str)}",
       "    if cls is dict:\n"
       "        return {str(k): encode(value[k]) for k in value}")],
     "tests/test_core_runtime_fast_paths.py::test_encode_sorts_keys_whatever_order_they_were_inserted",
     "canonical field ordering is dropped"),

    ("SER-2", "src/engcore/scientific/serialization.py",
     [("def require_schema(payload: Mapping[str, Any], expected: str) -> None:",
       "def require_schema(payload: Mapping[str, Any], expected: str) -> None:\n    return")],
     f"{T_SER}::test_an_unknown_schema_version_is_refused_explicitly",
     "a schema version mismatch is ignored"),

    ("SER-3", PARAMS,
     [('        return {\n            "name": self.name,\n            "unit": self.unit,',
       '        return {\n            "name": self.name,')],
     f"{T_SER}::test_material_a_different_unit_is_a_different_parameter",
     "a MATERIAL field is dropped from a scientific digest -- `unit` is removed "
     "from _canonical(), which is the dict digest() actually hashes. The first "
     "version of this mutation removed it from IDENTITY_FIELDS instead and "
     "SURVIVED, correctly: that tuple drives differences(), not the digest, so "
     "the mutation did not do what its own description claimed"),

    ("SER-4", "src/engcore/inference/field_observation.py",
     [('            "region_id": self.region_id,\n        }',
       '            "region_id": self.region_id,\n'
       '            "description": self.description,\n        }')],
     f"{T_SER}::test_non_material_a_display_description_does_not_move_a_field_operator_digest",
     "a NON-MATERIAL display label starts affecting a scientific digest"),

    # ---- DEPENDENCY / LAYERING ----------------------------------------
    ("DEP-1", "src/engcore/inference/calibration.py",
     [("from ..scientific.serialization import require_schema, schema_string",
       "from ..scientific.serialization import require_schema, schema_string\n"
       "from ..execution.sweep import run_sweep  # DEP-1")],
     f"{T_LAYER}::test_no_core_package_imports_one_above_it",
     "a forbidden upward dependency is introduced (inference -> execution)"),

    ("DEP-2", PYPROJECT,
     [('benchmarks = [\n  "jsonschema>=4.0",\n  "psutil>=5.9",\n]',
       'benchmarks = [\n  "psutil>=5.9",\n]')],
     f"{T_CONTRACT}::test_every_third_party_import_is_declared_somewhere",
     "a benchmark dependency becomes undeclared"),

    # ---- DETERMINISM / EXCEPTIONS -------------------------------------
    ("DET-1", SNAPSHOT,
     [("    symbols.sort(key=lambda entry: (entry[\"module\"], entry[\"name\"]))",
       "    pass  # DET-1")],
     f"{T_SNAP}::test_the_public_api_matches_the_pinned_snapshot",
     "nondeterministic ordering enters a canonical digest"),

    ("EXC-1", ERRORS,
     [("class UnitCompatibilityError(ScientificCoreError):",
       "class UnitCompatibilityError(ValueError):")],
     f"{T_CONTRACT}::test_the_exception_roots_are_exactly_the_seven_recorded",
     "a frozen public exception is reparented onto a raw builtin, so a "
     "caller's "
     "`except ScientificCoreError` silently stops catching it"),
)

#: Recorded with reasons, never dropped.
NOT_APPLICABLE = {
    "PKG-1": (
        "'exclude a frozen module from the wheel'. Packaging is DISCOVERED -- "
        "`[tool.setuptools.packages.find] where = [\"src\"]` -- so there is no "
        "per-module list to delete a line from, and a mutation would have to "
        "replace the discovery mechanism itself rather than break a guard. The "
        "property is covered directly instead: the wheel-parity run asserts "
        "SOURCE == WHEEL over all 197 frozen symbols, so a module missing from "
        "the wheel changes the wheel digest and fails."
    ),
    "PKG-2": (
        "'allow the source checkout to satisfy a missing wheel module'. This "
        "cannot be expressed as a source edit: it is a property of how the "
        "PROBE runs, not of the package. It is already proved positively -- the "
        "probe runs `python -S -E` so site.py never registers the editable "
        "hook, and the launcher asserts engcore.__file__ lives under the "
        "install target before importing anything else. Removing either is a "
        "change to the probe, which would be caught by the probe failing."
    ),
}


def run_tests(target: str) -> tuple[bool, str]:
    proc = subprocess.run(
        [PYTHON, "-X", "utf8", "-m", "pytest", target, "-q",
         "-p", "no:cacheprovider", "--basetemp", BASETEMP],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    lines = (proc.stdout + proc.stderr).strip().splitlines()
    return proc.returncode == 0, lines[-1] if lines else "(no output)"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="")
    args = parser.parse_args()
    wanted = {s.strip() for s in args.only.split(",") if s.strip()}

    print("CONTROL: every target GREEN before anything is mutated")
    targets = sorted({m[3].split("::")[0] for m in MUTATIONS})
    ok_all = True
    for target in targets:
        ok, summary = run_tests(target)
        print(f"  {'GREEN' if ok else 'RED  '}  {target} :: {summary}")
        ok_all &= ok
    if not ok_all:
        print("\nCONTROL RED -- a mutation result would say nothing. Stopping.")
        return 2
    print("CONTROL GREEN\n")

    results = []
    for identifier, relative, edits, target, description in MUTATIONS:
        if wanted and identifier not in wanted:
            continue
        path = ROOT / relative
        original = path.read_bytes()
        digest = hashlib.sha256(original).hexdigest()
        mutated, stale = original.decode("utf-8"), False
        for old, new in edits:
            if mutated.count(old) != 1:
                print(f"{identifier:8} STALE  pattern x{mutated.count(old)} in {relative}")
                results.append({"id": identifier, "verdict": "STALE",
                                "file": relative, "description": description})
                stale = True
                break
            mutated = mutated.replace(old, new, 1)
        if stale:
            continue

        started = time.monotonic()
        path.write_bytes(mutated.encode("utf-8"))
        try:
            green, summary = run_tests(target)
        finally:
            path.write_bytes(original)
            restored = hashlib.sha256(path.read_bytes()).hexdigest()
        if restored != digest:
            print(f"\n{identifier}: RESTORE FAILED for {relative}. Stopping.")
            return 3

        verdict = "SURVIVED" if green else "KILLED"
        print(f"{identifier:8} {verdict:9} {description}")
        print(f"         {target}")
        print(f"         {summary}  ({time.monotonic()-started:.1f}s)")
        results.append({"id": identifier, "verdict": verdict, "file": relative,
                        "target": target, "description": description,
                        "summary": summary})

    killed = sum(1 for r in results if r["verdict"] == "KILLED")
    survived = [r for r in results if r["verdict"] == "SURVIVED"]
    stale_list = [r for r in results if r["verdict"] == "STALE"]

    total_requested = len(results) + len(NOT_APPLICABLE)
    print(f"\n{killed}/{len(results)} written mutations killed.")
    print(f"denominator including the requested-but-unwritable: "
          f"{killed}/{total_requested} "
          f"({len(NOT_APPLICABLE)} classified INVALID_MUTATION, below)")
    for identifier, why in NOT_APPLICABLE.items():
        print(f"  {identifier}: INVALID_MUTATION -- {why.splitlines()[0]}")
    if survived:
        print("SURVIVORS -- each needs a written classification:")
        for r in survived:
            print(f"  {r['id']}: {r['description']}")

    out = ROOT / "benchmarks" / "core_api_stability" / "MUTATIONS.json"
    out.write_bytes(json.dumps(
        {"control": "GREEN", "killed": killed, "written": len(results),
         "requested_total": total_requested,
         "survivors": [r["id"] for r in survived],
         "stale": [r["id"] for r in stale_list],
         "not_applicable": NOT_APPLICABLE, "results": results},
        indent=2).encode("utf-8"))
    print(f"wrote {out}")
    return 0 if (not survived and not stale_list) else 1


if __name__ == "__main__":
    raise SystemExit(main())
