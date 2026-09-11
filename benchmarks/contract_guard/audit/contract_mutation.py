"""Falsification for the contract guards: plant a drift, demand a RED.

A guard that has never failed is a guard nobody has tested. Every family of
check this round adds is exercised here by a mutation that makes the shipped
record and the guarded runtime disagree, and each mutation names the guard that
must notice. A mutation nothing catches is reported as a SURVIVOR rather than
quietly dropped.

Two properties this deliberately keeps:

* The certified 79-mutant code suite is not touched, extended or renumbered.
  These mutations are a separate layer with a separate count, and most of them
  change only record TEXT -- which the certified harness excludes from its code
  digest by design, and therefore cannot register at all.
* Nothing is mutated in the working tree. Each run copies the repository to a
  temporary directory, mutates the copy, and runs one targeted guard there. No
  planted defect can survive the process that planted it.
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

GUARDS = ROUND / "tests" / "test_contract_guard.py"
INVARIANTS = "tests/test_core_semantic_invariants.py"
GUARD_MODULE = "benchmarks/contract_guard/tests/test_contract_guard.py"

TOO_BROAD = "RECORD_TOO_BROAD"
TOO_NARROW = "RECORD_TOO_NARROW"
BOUND_DRIFT = "STRUCTURED_BOUND_DRIFT"
RUNTIME_DRIFT = "RUNTIME_ENFORCEMENT_DRIFT"
PROMISE_INVERSION = "UNKNOWN_PROMISE_INVERSION"
INPUT_OBLIGATION_DRIFT = "INPUT_OBLIGATION_DRIFT"
PREREQUISITE_DISSOLVED = "PREREQUISITE_DISSOLVED"
UNMAPPED_CONDITION = "UNMAPPED_CONDITION"
REFUSAL_SEMANTICS_DRIFT = "REFUSAL_SEMANTICS_DRIFT"
CAPABILITY_UNSERVED = "CAPABILITY_UNSERVED"

# id, class, file, anchor, replacement, what the drift is, guard that must go RED
MUTATIONS = [
    (
        "CGM-1",
        TOO_BROAD,
        "src/engcore/domains/thermal_models/lumped.py",
        'description="Strictly positive; zero capacity has no dynamics.",',
        'description="Any capacity, including zero, is supported.",',
        "the SC5 survivor itself: the heat-capacity record advertises a zero "
        "the bound still refuses",
        f"{GUARD_MODULE}::test_no_record_advertises_applicability_the_runtime_refuses",
    ),
    (
        "CGM-2",
        TOO_BROAD,
        "src/engcore/domains/electrical/dc/models.py",
        '"Strictly positive resistance; zero is a short and "',
        '"Any resistance, including zero, is supported. Also "',
        "the same lie in a different system: the resistance record advertises "
        "a zero the bound refuses",
        f"{GUARD_MODULE}::test_no_record_advertises_applicability_the_runtime_refuses",
    ),
    (
        "CGM-3",
        TOO_BROAD,
        "src/engcore/domains/kinetics/cstr/problem.py",
        'description="Strictly positive pre-exponential factor.",',
        'description="Any pre-exponential factor, including zero, is supported.",',
        "the same lie in a third system: the pre-exponential record advertises "
        "a zero the bound refuses",
        f"{GUARD_MODULE}::test_no_record_advertises_applicability_the_runtime_refuses",
    ),
    (
        "CGM-4",
        TOO_NARROW,
        "src/engcore/domains/thermal_models/lumped.py",
        '"Bi = h L_c / k <= 0.1. Bi compares the temperature drop "',
        '"Bi = h L_c / k <= 0.05. Bi compares the temperature drop "',
        "the Biot record disclaims an operating point the runtime accepts: "
        "prose tightened to 0.05 while the bound stays at 0.1",
        f"{GUARD_MODULE}::test_no_record_disclaims_applicability_the_runtime_grants",
    ),
    (
        "CGM-5",
        TOO_NARROW,
        "src/engcore/domains/thermal_models/lumped.py",
        '"Fo = (t/tau)/Bi >= 0.2: the horizon is long enough that "',
        '"Fo = (t/tau)/Bi >= 0.5: the horizon is long enough that "',
        "the same lie on a lower edge, and on the one conservatively screened "
        "condition: prose demands 0.5 where the runtime admits 0.2",
        f"{GUARD_MODULE}::test_no_record_disclaims_applicability_the_runtime_grants",
    ),
    (
        "CGM-6",
        TOO_NARROW,
        "src/engcore/domains/battery/models.py",
        '"(T - T_min)/(T_max - T_min) in [0, 1]: the cell sits "',
        '"(T - T_min)/(T_max - T_min) in (0, 1): the cell sits "',
        "an endpoint quietly reopened in prose: the record now excludes the "
        "two limits the runtime includes",
        f"{GUARD_MODULE}::test_no_record_disclaims_applicability_the_runtime_grants",
    ),
    (
        "CGM-7",
        BOUND_DRIFT,
        "src/engcore/domains/thermal_models/lumped.py",
        "LUMPED_BIOT_LIMIT = Quantity(0.1, DIMENSIONLESS)",
        "LUMPED_BIOT_LIMIT = Quantity(0.2, DIMENSIONLESS)",
        "the other direction of the same drift: a developer moves the "
        "structured bound and leaves the published sentence behind",
        f"{GUARD_MODULE}::test_a_record_that_restates_its_bound_in_prose_restates_the_right_number",
    ),
    (
        "CGM-8",
        RUNTIME_DRIFT,
        "src/engcore/scientific/models/definition.py",
        "            magnitude < minimum.magnitude\n"
        "            if minimum_inclusive\n"
        "            else magnitude <= minimum.magnitude",
        "            magnitude <= minimum.magnitude\n"
        "            if minimum_inclusive\n"
        "            else magnitude <= minimum.magnitude",
        "an endpoint defect in the shared range evaluator with no record "
        "change at all: every inclusive minimum silently becomes exclusive",
        f"{GUARD_MODULE}::test_every_structured_bound_is_enforced_by_the_runtime",
    ),
    (
        "CGM-9",
        PROMISE_INVERSION,
        "src/engcore/domains/thermal_models/lumped.py",
        'formulation for a single-phase solid). UNKNOWN unless "\n'
        '                    "melting_temperature is supplied."',
        'formulation for a single-phase solid). SATISFIED even when "\n'
        '                    "melting_temperature is absent."',
        "a published UNKNOWN promise inverted: the record claims the condition "
        "holds without the declaration the runtime needs (the SC1 shape)",
        f"{INVARIANTS}::test_a_condition_that_says_unknown_unless_must_mean_it",
    ),
    (
        "CGM-10",
        PROMISE_INVERSION,
        "src/engcore/domains/thermal_models/lumped.py",
        '"model look applicable when it may not be. UNKNOWN only "',
        '"model look applicable when it may not be. UNKNOWN unless "',
        "the geometry record goes back to promising a cross-check the "
        "derivation does not perform (the CORE-1 shape)",
        f"{INVARIANTS}::test_a_condition_that_says_unknown_unless_must_mean_it",
    ),
    (
        "CGM-11",
        INPUT_OBLIGATION_DRIFT,
        "src/engcore/domains/thermal_models/lumped.py",
        '            name=HEAT_CAPACITY,\n'
        "            source_kind=InputSourceKind.PARAMETER,\n"
        "            unit_exemplar=CAPACITY_UNIT,\n"
        '            description="Total heat capacity of the body; strictly positive.",',
        '            name=HEAT_CAPACITY,\n'
        "            source_kind=InputSourceKind.PARAMETER,\n"
        "            unit_exemplar=CAPACITY_UNIT,\n"
        "            required=False,\n"
        '            description="Total heat capacity of the body; strictly positive.",',
        "the record downgrades a required input to optional while the "
        "constructor still refuses without it: a caller told they may leave "
        "it out cannot build the problem",
        f"{GUARD_MODULE}::test_required_means_required_and_optional_means_optional",
    ),
    (
        "CGM-12",
        PREREQUISITE_DISSOLVED,
        "src/engcore/domains/thermal_models/context.py",
        "    ratio = _as_quantity(horizon_ratio, DIMENSIONLESS, TRANSIENT_HORIZON_RATIO)\n"
        "    number = _positive(\n"
        "        _as_quantity(biot, DIMENSIONLESS, BIOT_NUMBER), DIMENSIONLESS, BIOT_NUMBER\n"
        "    )\n"
        "    if ratio is None or number is None:\n"
        "        return None",
        "    ratio = _as_quantity(horizon_ratio, DIMENSIONLESS, TRANSIENT_HORIZON_RATIO)\n"
        "    number = _positive(\n"
        "        _as_quantity(biot, DIMENSIONLESS, BIOT_NUMBER), DIMENSIONLESS, BIOT_NUMBER\n"
        "    )\n"
        "    if ratio is None or number is None:\n"
        "        return Quantity(1.0, DIMENSIONLESS)",
        "a published UNKNOWN prerequisite quietly dissolves: the assembler "
        "starts inventing a Fourier number for a caller who declared none of "
        "what it is derived from, with the record unchanged",
        f"{GUARD_MODULE}::test_nothing_declared_derives_nothing_unless_the_record_says_so",
    ),
    (
        "CGM-13",
        UNMAPPED_CONDITION,
        "src/engcore/domains/thermal_models/lumped.py",
        "            RangeCondition(\n"
        "                name=BIOT_NUMBER,\n"
        "                maximum=LUMPED_BIOT_LIMIT,",
        "            RangeCondition(\n"
        '                name="guard_falsification_condition",\n'
        "                maximum=LUMPED_BIOT_LIMIT,\n"
        '                description="A newly shipped condition nobody mapped.",\n'
        "            ),\n"
        "            RangeCondition(\n"
        "                name=BIOT_NUMBER,\n"
        "                maximum=LUMPED_BIOT_LIMIT,",
        "a new condition ships with no entry in the claim map, which is how a "
        "model would otherwise join the surface with nothing checking it",
        f"{GUARD_MODULE}::test_no_shipped_condition_is_missing_from_the_claim_map",
    ),
    (
        "CGM-14",
        REFUSAL_SEMANTICS_DRIFT,
        "src/engcore/scientific/models/definition.py",
        "        if not isinstance(value, Quantity):\n"
        "            return ValidityStatus.UNKNOWN\n"
        "        return _within(\n"
        "            value,\n"
        "            minimum=self.minimum,",
        "        if not isinstance(value, Quantity):\n"
        "            return ValidityStatus.IN_DOMAIN\n"
        "        return _within(\n"
        "            value,\n"
        "            minimum=self.minimum,",
        "an absent declaration starts reading as a satisfied condition: every "
        "record's UNKNOWN becomes a silent IN_DOMAIN with no record changed",
        f"{GUARD_MODULE}::test_no_condition_is_satisfied_before_anything_is_declared",
    ),
    (
        "CGM-15",
        CAPABILITY_UNSERVED,
        "src/engcore/domains/thermal_models/lumped.py",
        "    serves_capabilities = frozenset({LUMPED_CAPACITY_TRANSIENT.name})",
        '    serves_capabilities = frozenset({LUMPED_CAPACITY_TRANSIENT.name + "_v2"})',
        "the only solver serving a published capability is renamed, leaving "
        "the record advertising something nothing in the repository executes",
        f"{GUARD_MODULE}::test_no_model_requires_a_capability_nothing_serves",
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
    """The guards must be GREEN on an unmutated copy, or every RED below is noise."""
    with tempfile.TemporaryDirectory(prefix="contractguard") as tmp:
        work = pathlib.Path(tmp) / "repo"
        _stage(work)
        proc = _pytest(work, GUARD_MODULE)
        return {
            "id": "CONTROL",
            "status": "GREEN" if proc.returncode == 0 else "RED (guards are broken)",
            "green": proc.returncode == 0,
            "tail": proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "",
        }


def run(mutation) -> dict:
    mid, klass, relative, old, new, drift, guard = mutation
    with tempfile.TemporaryDirectory(prefix="contractguard") as tmp:
        work = pathlib.Path(tmp) / "repo"
        _stage(work)
        path = work / relative
        text = path.read_text(encoding="utf-8")
        occurrences = text.count(old)
        if occurrences != 1:
            return {
                "id": mid,
                "class": klass,
                "drift": drift,
                "guard": guard,
                "status": "DID_NOT_APPLY",
                "caught": False,
                "detail": f"anchor appears {occurrences} times in {relative}",
            }
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        proc = _pytest(work, guard)
        caught = proc.returncode != 0
        return {
            "id": mid,
            "class": klass,
            "file": relative,
            "drift": drift,
            "guard": guard,
            "status": "RED (caught)" if caught else "SURVIVOR (nothing noticed)",
            "caught": caught,
            "tail": proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "",
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROUND / "CONTRACT_MUTATION.json"))
    args = parser.parse_args()

    control_result = control()
    results = [run(mutation) for mutation in MUTATIONS]
    caught = sum(1 for result in results if result["caught"])
    by_class: dict[str, dict[str, int]] = {}
    for result in results:
        bucket = by_class.setdefault(result["class"], {"total": 0, "caught": 0})
        bucket["total"] += 1
        bucket["caught"] += int(result["caught"])

    payload = {
        "schema": "contract_mutation/1",
        "what_this_is": (
            "Falsification for the record<->runtime contract guards added in "
            "this round. Each mutation plants one semantic drift in a copy of "
            "the repository and demands that a named guard go RED."
        ),
        "relationship_to_certified_suite": (
            "additive and independent. The certified 79-mutant code suite is "
            "not modified, extended or renumbered, and its digest is "
            "unchanged. These counts are never merged with it."
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
    print(f"contract mutations: {caught}/{len(results)} caught")
    for result in results:
        print(f"  {result['id']:7s} {result['class']:26s} {result['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
