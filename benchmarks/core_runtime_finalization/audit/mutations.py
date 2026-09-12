"""Sprint 9 runtime mutations: break each guard once, watch it fail.

Separate from ``tests/mutation_guards.py`` for the reason every round since
Sprint 3 has kept its own: that runner is inside certified scope and pinned by
the Core certificate, so a guard written this round cannot join ``MUTATIONS``
without invalidating the snapshot. **These are NOT part of the certified 79 and
are never added to that count.**

On the PAR family. Sprint 9 DEFERS parallel execution, so three of the six
suggested PAR mutations target a process backend that does not exist. They are
recorded as NOT APPLICABLE with the reason rather than dropped: a denominator
that quietly shrinks to the mutations that happened to pass is the failure this
whole apparatus exists to prevent.

    python -X utf8 benchmarks/core_runtime_finalization/audit/mutations.py
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
BASETEMP = "D:/fbt_s9"

QUANTITY = "src/engcore/scientific/units/quantity.py"
SERIALIZATION = "src/engcore/scientific/serialization.py"
SWEEP = "src/engcore/execution/sweep.py"

T_CACHES = "tests/test_core_runtime_caches.py"
T_EXEC = "tests/test_core_runtime_execution.py"
T_API = "tests/test_core_runtime_api_surface.py"
T_GUARDS = "tests/test_core_guards.py"
T_FAST = "tests/test_core_runtime_fast_paths.py"
T_SWEEP = "tests/test_execution_sweep.py"

#: (id, file, [(old, new)], target, description)
MUTATIONS = (
    (
        "PERF-RT-1", QUANTITY,
        [("    return dimension_of(source) == dimension_of(target)",
          "    return dimension_of(source) == dimension_of(source)")],
        f"{T_CACHES}::test_the_memo_agrees_with_the_unmemoized_computation",
        "the compatibility memo ignores one identity and answers from the other "
        "-- a stale cached scientific input reused across different identities",
    ),
    (
        "PERF-RT-2", QUANTITY,
        [("    base_unit.cache_clear()\n    is_ratio_scale.cache_clear()",
          "    pass  # PERF-RT-2")],
        f"{T_CACHES}::test_clear_unit_caches_clears_every_memo_in_the_module",
        "cache invalidation skips two memos -- the Sprint 7 defect, restored",
    ),
    (
        "PERF-RT-3", SERIALIZATION,
        [("    if cls is dict:\n"
          "        return {str(k): encode(value[k]) for k in sorted(value, key=str)}",
          "    if cls is dict:\n"
          "        return {str(k): encode(value[k]) for k in value}")],
        f"{T_FAST}::test_encode_sorts_keys_whatever_order_they_were_inserted",
        "the fast path for dict drops canonical key ordering, so the same "
        "record serializes differently depending on insertion order",
    ),
    (
        "PERF-RT-4", SERIALIZATION,
        [("        if isinstance(value, float) and value != value:\n"
          "            return (path, \"float('nan')\")",
          "        if False:\n"
          "            return (path, \"float('nan')\")")],
        f"{T_FAST}::test_non_finite_values_are_refused_including_float_subclasses",
        "the non-finite refusal stops firing, so a NaN reaches a record and "
        "serializes to a token no conforming JSON reader accepts. Retargeted "
        "at the general-path check after the float fast path that had been "
        "shadowing it -- and blinding certified mutation G10c -- was removed",
    ),
    (
        "PAR-1", SWEEP,
        [('    return all(hasattr(value, verb) for verb in ("prepare", "solve"))',
          "    return False  # PAR-1")],
        f"{T_SWEEP}::test_a_solver_may_not_be_shared",
        "a solver may be shared across cases through SharedContext",
    ),
    (
        "PAR-2", SWEEP,
        [('                    "case_identity": o.case.identity,', "")],
        f"{T_EXEC}::test_the_summary_record_names_each_failed_case_identity",
        "a failed case loses its content identity in the summary record",
    ),
    (
        "PAR-3", SWEEP,
        [("        for position, case in enumerate(definition.cases):\n"
          "            outcome = _run_case(definition, case)\n"
          "            outcomes.append(outcome)",
          "        for position, case in enumerate(reversed(definition.cases)):\n"
          "            outcome = _run_case(definition, case)\n"
          "            outcomes.append(outcome)")],
        f"{T_EXEC}::test_output_order_is_declaration_order_whatever_finished_first",
        "outputs come back in an order the summary does not promise",
    ),
    (
        "PAR-4", SWEEP,
        [("        return SweepOutcome(\n"
          "            case=case,\n"
          "            status=CaseStatus.FAILED,",
          "        return SweepOutcome(\n"
          "            case=case,\n"
          "            status=CaseStatus.SUCCEEDED,")],
        f"{T_EXEC}::test_failures_are_isolated_and_siblings_survive",
        "a worker exception is swallowed and reported as success",
    ),
    (
        "PAR-7", SWEEP,
        [("def run_sweep(definition: SweepDefinition, *, workers: int = 1) -> SweepSummary:",
          "def run_sweep(definition: SweepDefinition, *, workers: int = 4) -> SweepSummary:")],
        f"{T_API}::test_the_experimental_parameters_exist_and_default_to_sequential",
        "the worker default stops being sequential, so every caller silently "
        "gets the slower path without asking",
    ),
)

#: Recorded, not hidden. Each names why no mutant could be written for it.
NOT_APPLICABLE = {
    "PAR-5": (
        "'reuse stale cached scientific input across different identities' in a "
        "PROCESS path. No process backend exists -- parallel execution is "
        "deferred this round. The same defect SHAPE is exercised against the "
        "code that does exist, as PERF-RT-1, which mutates the compatibility "
        "memo to answer from the wrong identity."
    ),
    "PAR-6": (
        "'return different provenance in the process path'. There is no process "
        "path to return different provenance from. Nothing was weakened to make "
        "this inapplicable: the backend was measured (2.58x with a persistent "
        "pool, 0.12x with a pool per sweep) and deliberately not built."
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

    print("CONTROL: every target must be GREEN before anything is mutated")
    targets = sorted({m[3].split("::")[0] for m in MUTATIONS})
    control_ok = True
    for target in targets:
        ok, summary = run_tests(target)
        print(f"  {'GREEN' if ok else 'RED  '}  {target} :: {summary}")
        control_ok &= ok
    if not control_ok:
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

        mutated = original.decode("utf-8")
        stale = False
        for old, new in edits:
            if mutated.count(old) != 1:
                print(f"{identifier:10} STALE  pattern x{mutated.count(old)} in {relative}")
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
        print(f"{identifier:10} {verdict:9} {description}")
        print(f"           {target}")
        print(f"           {summary}  ({time.monotonic()-started:.1f}s)")
        results.append({"id": identifier, "verdict": verdict, "file": relative,
                        "target": target, "description": description,
                        "summary": summary})

    killed = sum(1 for r in results if r["verdict"] == "KILLED")
    survived = [r for r in results if r["verdict"] == "SURVIVED"]
    stale_list = [r for r in results if r["verdict"] == "STALE"]

    print(f"\n{killed}/{len(results)} mutations killed by the guard they name.")
    print(f"{len(NOT_APPLICABLE)} recorded NOT APPLICABLE (not removed from the record):")
    for identifier, why in NOT_APPLICABLE.items():
        print(f"  {identifier}: {why.splitlines()[0]}")
    if survived:
        print("SURVIVORS -- each needs a written classification:")
        for r in survived:
            print(f"  {r['id']}: {r['description']}")

    out = ROOT / "benchmarks" / "core_runtime_finalization" / "MUTATIONS.json"
    out.write_bytes(json.dumps(
        {"control": "GREEN", "killed": killed, "total": len(results),
         "survivors": [r["id"] for r in survived],
         "stale": [r["id"] for r in stale_list],
         "not_applicable": NOT_APPLICABLE, "results": results},
        indent=2).encode("utf-8"))
    print(f"wrote {out}")
    return 0 if (not survived and not stale_list) else 1


if __name__ == "__main__":
    raise SystemExit(main())
