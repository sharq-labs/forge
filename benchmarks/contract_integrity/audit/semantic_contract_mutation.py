"""A semantic contract mutation layer, separate from the certified 79.

The certified harness mutates executable branches. Its ``_code_digest`` drops
STRING tokens and ``test_every_mutation_changes_executable_code`` refuses any
mutation whose only effect is prose, so a published record can be rewritten to
say the opposite of what the runtime does and the harness registers nothing.
That is by design, and it is why 79/79 does not speak to contract integrity.

This layer mutates the OTHER half: the text of a shipped record. Each mutation
below rewrites a published claim into something the runtime does not do, and
names the guard that must go RED. A mutation nothing catches is reported as a
SURVIVOR -- an honest coverage gap, not a failure to hide.

It does not touch, extend or renumber the certified suite. It copies the tree,
mutates the copy, and runs one targeted guard against it.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROUND = HERE.parent
REPO = ROUND.parent.parent

# id, file, old text, new text, what the lie is, guard that must notice
MUTATIONS = [
    (
        "SC1",
        "src/engcore/domains/thermal_models/lumped.py",
        'formulation for a single-phase solid). UNKNOWN unless "\n                    "melting_temperature is supplied."',
        'formulation for a single-phase solid). SATISFIED even when "\n                    "melting_temperature is absent."',
        "a published UNKNOWN promise is inverted: the record now claims the "
        "condition holds without the declaration the runtime needs",
        "tests/test_core_semantic_invariants.py::test_a_condition_that_says_unknown_unless_must_mean_it",
    ),
    (
        "SC2",
        "src/engcore/domains/thermal_models/lumped.py",
        '"model look applicable when it may not be. UNKNOWN only "',
        '"model look applicable when it may not be. UNKNOWN unless "',
        "the geometry record goes back to promising a cross-check the "
        "derivation deliberately does not perform (the CORE-1 defect)",
        "tests/test_core_semantic_invariants.py::test_a_condition_that_says_unknown_unless_must_mean_it",
    ),
    (
        "SC3",
        "src/engcore/domains/thermal_models/lumped.py",
        '"UNKNOWN unless the convection_length, the kinematic "\n                    "viscosity, the operating point and one of the two route "\n                    "declarations are supplied. THE PRANDTL NUMBER IS NEEDED "',
        '"UNKNOWN unless the convection_length, kinematic "\n                    "viscosity, Prandtl number, the operating point and one "\n                    "of the two route declarations are all supplied. UNUSED "',
        "the flow-range record goes back to requiring a Prandtl number on "
        "both routes, which is false on the forced one (the CI-1 defect)",
        "tests/test_core_semantic_invariants.py::test_the_flow_range_record_states_which_route_needs_a_prandtl_number",
    ),
    (
        "SC4",
        "src/engcore/domains/thermal_models/lumped.py",
        '"WITH ONE ROUTE THIS CONDITION IS SATISFIED AND NO "',
        '"WITH ONE ROUTE THE TWO ROUTES ARE COMPARED AND NO "',
        "the record claims a cross-check was performed where the runtime "
        "compares one route against nothing",
        "tests/test_core_semantic_invariants.py::test_a_condition_that_says_unknown_unless_must_mean_it",
    ),
    (
        "SC5",
        "src/engcore/domains/thermal_models/lumped.py",
        '"Strictly positive; zero capacity has no dynamics."',
        '"Any capacity, including zero, is supported."',
        "an applicability claim is widened past what the condition enforces: "
        "the bound still refuses zero, the record now advertises it",
        "(no guard known — expected SURVIVOR)",
    ),
]


def run(mutation) -> dict:
    mid, relative, old, new, lie, guard = mutation
    with tempfile.TemporaryDirectory(prefix="semcontract") as tmp:
        work = pathlib.Path(tmp) / "repo"
        work.mkdir()
        for item in ("src", "tests", "pyproject.toml"):
            source = REPO / item
            target = work / item
            if source.is_dir():
                shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
            else:
                shutil.copy2(source, target)
        path = work / relative
        text = path.read_text(encoding="utf-8")
        if text.count(old) != 1:
            return {"id": mid, "status": "DID_NOT_APPLY",
                    "detail": f"anchor appears {text.count(old)} times", "lie": lie}
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

        target_guard = guard.split("::")[-1] if "::" in guard else None
        selection = guard.split("::")[0] if "::" in guard else "tests/test_core_semantic_invariants.py"
        args = [sys.executable, "-m", "pytest", selection, "-q"]
        if target_guard:
            args = [sys.executable, "-m", "pytest", guard, "-q"]
        proc = subprocess.run(args, cwd=work, capture_output=True, text=True, timeout=600)
        caught = proc.returncode != 0
        return {
            "id": mid,
            "lie": lie,
            "guard": guard,
            "status": "RED (caught)" if caught else "SURVIVOR (nothing noticed)",
            "caught": caught,
            "tail": proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "",
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROUND / "SEMANTIC_CONTRACT_MUTATION.json"))
    args = parser.parse_args()
    results = [run(m) for m in MUTATIONS]
    caught = sum(1 for r in results if r.get("caught"))
    payload = {
        "schema": "semantic_contract_mutation/1",
        "what_this_is": (
            "A mutation layer for published record TEXT, separate from the "
            "certified 79-mutant suite, which it does not touch, extend or "
            "renumber. The certified harness excludes STRING-token-only "
            "changes from its code digest by design, so it cannot register any "
            "of the mutations below."
        ),
        "relationship_to_certified_suite": (
            "additive and independent. The certified suite remains 79/79 RED "
            "with CONTROL GREEN and is not modified by this round."
        ),
        "total": len(results),
        "caught": caught,
        "survivors": [r["id"] for r in results if not r.get("caught")],
        "results": results,
    }
    pathlib.Path(args.out).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"semantic contract mutations: {caught}/{len(results)} caught")
    for r in results:
        print(f"  {r['id']}  {r['status']:26s} {r['lie'][:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
