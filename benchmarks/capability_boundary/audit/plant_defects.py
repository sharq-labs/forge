"""Falsification for the capability-boundary guards.

A guard that has never failed is a guard nobody has tested, and that is truer
here than for a contract check: a boundary condition sits quietly in a record
and a reader cannot tell by looking whether anything would notice its removal.

Each plant below is one of the five capability-overclaim classes the round
names, made in a COPY of the repository, with a named guard that must go RED.
Nothing is mutated in the working tree, so no planted defect can survive the
process that planted it.

These are NOT contract mutations. A contract mutation makes a record disagree
with its runtime; every plant here leaves record and runtime in perfect
agreement and breaks only the scientific boundary between them. That is the
distinction the round exists to draw, and it is why these guards live in a
separate suite with a separate count.
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

GUARDS = "benchmarks/capability_boundary/tests/test_capability_boundary.py"

CLAIM_BROADENED = "CLAIM_BROADENED_BEYOND_EQUATIONS"
LIMIT_REMOVED = "VALIDITY_LIMIT_REMOVED"
OUT_OF_REGIME_SUPPORTED = "OUT_OF_REGIME_MARKED_SUPPORTED"
APPROXIMATION_HIDDEN = "REQUIRED_APPROXIMATION_HIDDEN"
UNSUPPORTED_REGIME_ACCEPTED = "UNSUPPORTED_REGIME_ACCEPTED"

# id, class, file, anchor, replacement, what the overclaim is, guard that must go RED
PLANTS = [
    (
        "CBP-1",
        LIMIT_REMOVED,
        "src/engcore/domains/electrical/material.py",
        "            # caller asks before deciding to run at all.\n"
        "            RangeCondition(\n"
        "                name=LINEAR_RESISTANCE_RATIO,\n"
        "                minimum=MINIMUM_LINEAR_RESISTANCE_RATIO,\n"
        "                minimum_inclusive=False,",
        "            # caller asks before deciding to run at all.\n"
        "            RangeCondition(\n"
        "                name=LINEAR_RESISTANCE_RATIO,\n"
        "                minimum=Quantity(-1.0e9, DIMENSIONLESS),\n"
        "                minimum_inclusive=False,",
        "the positivity bound on the linear TCR form is loosened until it "
        "cannot bite: the record still states a bound and the runtime still "
        "enforces it, so record and runtime agree perfectly, and a negative "
        "resistance is applicable again",
        f"{GUARDS}::test_the_linear_tcr_model_refuses_a_line_that_has_crossed_zero",
    ),
    (
        "CBP-2",
        UNSUPPORTED_REGIME_ACCEPTED,
        "src/engcore/domains/electrical/material.py",
        "            # caller asks before deciding to run at all.\n"
        "            RangeCondition(\n"
        "                name=LINEAR_RESISTANCE_RATIO,\n"
        "                minimum=MINIMUM_LINEAR_RESISTANCE_RATIO,\n"
        "                minimum_inclusive=False,",
        "            # caller asks before deciding to run at all.\n"
        "            RangeCondition(\n"
        "                name=LINEAR_RESISTANCE_RATIO,\n"
        "                minimum=MINIMUM_LINEAR_RESISTANCE_RATIO,\n"
        "                minimum_inclusive=True,",
        "the endpoint is reopened: a resistance of exactly zero -- a short, "
        "not a conductor -- becomes applicable, from a one-word edit that no "
        "record-versus-runtime check can see",
        f"{GUARDS}::test_the_linear_tcr_model_refuses_a_line_that_has_crossed_zero",
    ),
    (
        "CBP-3",
        LIMIT_REMOVED,
        "src/engcore/domains/kinetics/cstr/alternatives.py",
        '            RangeCondition(\n'
        "                ADIABATIC_CEILING_TEMPERATURE,\n"
        "                maximum=Quantity(MAX_VALID_TEMPERATURE_K, TEMPERATURE_UNIT),",
        '            RangeCondition(\n'
        "                ADIABATIC_CEILING_TEMPERATURE,\n"
        "                maximum=Quantity(1.0e9, TEMPERATURE_UNIT),",
        "the constant-rate CSTR's envelope ceiling is raised past any reachable "
        "temperature, so the record claims the same single-phase envelope as "
        "its sibling while checking nothing",
        f"{GUARDS}::test_both_cstr_models_refuse_a_declaration_whose_ceiling_leaves_the_envelope",
    ),
    (
        "CBP-4",
        CLAIM_BROADENED,
        "src/engcore/domains/kinetics/cstr/problem.py",
        "MAX_VALID_TEMPERATURE_K = 1000.0",
        "MAX_VALID_TEMPERATURE_K = 3000.0",
        "the single-phase liquid envelope is broadened to 3000 K, where no "
        "ordinary solvent is a liquid at all: the equations are untouched and "
        "every record still agrees with every runtime, and the claim now "
        "covers a regime the constant-property balances cannot represent",
        f"{GUARDS}::test_both_cstr_models_refuse_a_declaration_whose_ceiling_leaves_the_envelope",
    ),
    (
        "CBP-5",
        LIMIT_REMOVED,
        "src/engcore/domains/battery/models.py",
        "                name=CUTOFF_REACHABILITY_MARGIN,\n"
        "                minimum=CUTOFF_CONSISTENCY_FLOOR,",
        "                name=CUTOFF_REACHABILITY_MARGIN,\n"
        "                minimum=Quantity(-1.0e9, DIMENSIONLESS),",
        "the runtime model's reachability floor is loosened until a cutoff "
        "behind the start passes it, restoring a negative runtime reported as "
        "applicable",
        f"{GUARDS}::test_the_runtime_model_refuses_a_cutoff_above_where_the_discharge_starts",
    ),
    (
        "CBP-6",
        OUT_OF_REGIME_SUPPORTED,
        "src/engcore/domains/thermal/conduction1d/validation.py",
        '            name="discretization_convergence",\n'
        "            outcome=ValidationOutcome.NOT_RUN,",
        '            name="discretization_convergence",\n'
        "            outcome=ValidationOutcome.PASS,",
        "a single solve starts reporting discretization convergence it cannot "
        "have established, so a 25x-wrong answer carries a passing accuracy "
        "check instead of an honest NOT_RUN",
        f"{GUARDS}::test_a_coarse_diffusion_solve_claims_no_accuracy_it_has_not_earned",
    ),
    (
        "CBP-7",
        APPROXIMATION_HIDDEN,
        "src/engcore/domains/thermal_models/lumped.py",
        "                name=MELTING_TEMPERATURE_UTILIZATION,\n"
        "                maximum=PHASE_CHANGE_UTILIZATION_LIMIT,",
        "                name=MELTING_TEMPERATURE_UTILIZATION,\n"
        "                maximum=Quantity(1.0e9, DIMENSIONLESS),",
        "the lumped model's phase-change limit stops binding, so a body the "
        "run carries past its melting point is applicable -- the approximation "
        "'no phase change' is still declared in the record and is no longer "
        "checked anywhere",
        f"{GUARDS}::test_the_lumped_model_refuses_a_body_its_own_run_would_melt",
    ),
]

COPY = ("src", "tests", "benchmarks", "pyproject.toml")


def _stage(work: pathlib.Path) -> None:
    work.mkdir(parents=True, exist_ok=True)
    for item in COPY:
        source = REPO / item
        target = work / item
        if source.is_dir():
            shutil.copytree(
                source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
            )
        else:
            shutil.copy2(source, target)


def _pytest(work: pathlib.Path, selection: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pytest", selection, "-q", "-p", "no:cacheprovider"],
        cwd=work,
        capture_output=True,
        text=True,
        timeout=900,
    )


def control() -> dict:
    with tempfile.TemporaryDirectory(prefix="capboundary") as tmp:
        work = pathlib.Path(tmp) / "repo"
        _stage(work)
        proc = _pytest(work, GUARDS)
        return {
            "id": "CONTROL",
            "status": "GREEN" if proc.returncode == 0 else "RED (guards are broken)",
            "green": proc.returncode == 0,
            "tail": proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "",
        }


def run(plant) -> dict:
    pid, klass, relative, old, new, overclaim, guard = plant
    with tempfile.TemporaryDirectory(prefix="capboundary") as tmp:
        work = pathlib.Path(tmp) / "repo"
        _stage(work)
        path = work / relative
        text = path.read_text(encoding="utf-8")
        occurrences = text.count(old)
        if occurrences != 1:
            return {
                "id": pid,
                "class": klass,
                "file": relative,
                "overclaim": overclaim,
                "guard": guard,
                "status": "DID_NOT_APPLY",
                "caught": False,
                "detail": f"anchor appears {occurrences} times in {relative}",
            }
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        proc = _pytest(work, guard)
        caught = proc.returncode != 0
        return {
            "id": pid,
            "class": klass,
            "file": relative,
            "overclaim": overclaim,
            "guard": guard,
            "status": "RED (caught)" if caught else "SURVIVOR (nothing noticed)",
            "caught": caught,
            "tail": proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "",
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROUND / "PLANTED_DEFECTS.json"))
    args = parser.parse_args()

    control_result = control()
    results = [run(plant) for plant in PLANTS]
    caught = sum(1 for result in results if result["caught"])
    by_class: dict[str, dict[str, int]] = {}
    for result in results:
        bucket = by_class.setdefault(result["class"], {"total": 0, "caught": 0})
        bucket["total"] += 1
        bucket["caught"] += int(result["caught"])

    payload = {
        "schema": "capability_boundary_planted_defects/1",
        "what_this_is": (
            "Falsification for this round's scientific boundary guards. Each "
            "plant is one capability-overclaim class, made in a temporary copy "
            "of the repository, with a named guard that must go RED."
        ),
        "why_this_is_not_a_contract_mutation": (
            "Every plant here leaves the published record and the guarded "
            "runtime in perfect agreement and breaks only the scientific "
            "boundary between them. A record-versus-runtime check cannot see "
            "any of them, which is the whole reason this round exists."
        ),
        "relationship_to_earlier_rounds": (
            "additive and independent. The certified 79-mutant code suite and "
            "the 15-mutant contract suite are not modified, extended or "
            "renumbered, and these counts are never merged with either."
        ),
        "control": control_result,
        "total": len(results),
        "caught": caught,
        "survivors": [r["id"] for r in results if not r["caught"]],
        "by_class": by_class,
        "results": results,
    }
    pathlib.Path(args.out).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"control: {control_result['status']}")
    print(f"planted capability defects: {caught}/{len(results)} caught")
    for result in results:
        print(f"  {result['id']:7s} {result['class']:33s} {result['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
