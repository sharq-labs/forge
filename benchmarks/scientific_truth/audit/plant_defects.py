"""ST-21: falsify the scientific auditor.

An oracle suite that has never caught anything is a suite nobody has tested,
and this round's checks are almost entirely green -- which is exactly when
falsification matters most. Each plant below is a defect of one of the classes
this round adjudicates, made in a COPY of the repository, with a named check
that must go from clean to disagreeing.

These are NOT contract mutations and NOT capability-boundary plants. Every
plant here leaves the published record, the validity conditions and the
software contract completely intact and changes only the MATHEMATICS. A record
check cannot see any of them; a capability-boundary check cannot see any of
them; they are visible only to an oracle that knows what the answer should be.
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

SIGN = "SIGN_CONVENTION_DEFECT"
COEFFICIENT = "COEFFICIENT_DEFECT"
UNIT = "UNIT_CONVERSION_DEFECT"
CONSERVATION = "CONSERVATION_DEFECT"
NUMERICAL = "NUMERICAL_METHOD_DEFECT"
INDEPENDENCE = "SOLVER_INDEPENDENCE_DEFECT"
ORACLE = "TEST_ORACLE_DEFECT"

#: id, class, file, anchor, replacement, what breaks, the check that must notice
PLANTS = [
    (
        "STP-1", SIGN,
        "src/engcore/domains/kinetics/cstr/problem.py",
        "        return -self.dh_j_per_mol / (self.rho_kg_per_m3 * self.cp_j_per_kg_k)",
        "        return self.dh_j_per_mol / (self.rho_kg_per_m3 * self.cp_j_per_kg_k)",
        "beta loses its minus sign, so an exothermic reaction COOLS the tank "
        "and an endothermic one heats it. Every record still says the same "
        "thing, every validity condition still holds, and the temperatures "
        "returned are entirely plausible",
        "cstr_limits_and_signs",
    ),
    (
        "STP-2", SIGN,
        "src/engcore/domains/thermal_models/lumped.py",
        "        final = steady + (body.initial_k - steady) * decay",
        "        final = steady - (body.initial_k - steady) * decay",
        "the approach to steady state is reflected: a cooling body overshoots "
        "past its ambient instead of settling on it",
        "lumped_rows",
    ),
    (
        "STP-3", COEFFICIENT,
        "src/engcore/domains/battery/solver.py",
        "    heat = current_a * current_a * resistance_ohm",
        "    heat = current_a * resistance_ohm * resistance_ohm",
        "Joule's law becomes I R^2 instead of I^2 R -- dimensionally wrong and "
        "numerically plausible at any operating point where I and R are close",
        "battery_rows",
    ),
    (
        "STP-4", UNIT,
        "src/engcore/domains/battery/solver.py",
        '    duration_h = load.duration.magnitude_in("hour")\n'
        "\n"
        "    charge_removed = current_a * duration_h / (efficiency * capacity_ah)",
        '    duration_h = load.duration.magnitude_in("hour") / 1000.0\n'
        "\n"
        "    charge_removed = current_a * duration_h / (efficiency * capacity_ah)",
        "the ampere-hour conversion is out by a thousand, so every state of "
        "charge falls a thousand times too slowly. Charge conservation is "
        "broken by exactly that factor",
        "battery_rows",
    ),
    (
        "STP-5", CONSERVATION,
        "src/engcore/domains/kinetics/cstr/solver.py",
        "        d_concentration = a * (caf - concentration) - reaction",
        "        d_concentration = a * (caf - concentration) - 0.97 * reaction",
        "three per cent of the reactant consumed by the energy balance is not "
        "removed from the species balance, so the exact invariant "
        "Z = T + beta C_A stops being invariant and the reactor creates "
        "energy from nothing",
        "cstr_rows",
    ),
    (
        "STP-6", NUMERICAL,
        "src/engcore/domains/thermal/conduction1d/solver.py",
        "    r = slab.alpha_m2_s * dt / (dx**2)",
        "    r = slab.alpha_m2_s * dt / (dx**2) * 1.02",
        "the Fourier number carries a two per cent error, which degrades the "
        "scheme's accuracy without making it unstable or non-convergent: the "
        "solve still converges, just to the wrong answer",
        "diffusion_rows",
    ),
    (
        "STP-7", COEFFICIENT,
        "src/engcore/domains/electrical/material.py",
        "        resistance = conductor.r_ref_ohm * (\n"
        "            1.0\n"
        "            + conductor.alpha_per_k * (evaluation.temperature_k - conductor.t_ref_k)\n"
        "        )",
        "        resistance = conductor.r_ref_ohm * (\n"
        "            1.0\n"
        "            + conductor.alpha_per_k * (evaluation.temperature_k - conductor.t_ref_k)\n"
        "            * 1.0000001\n"
        "        )",
        "a coefficient error of one part in ten million -- far too small for "
        "any reference value to notice, and seven orders of magnitude above "
        "the 50-digit arithmetic's resolution",
        "material_rows",
    ),
    (
        "STP-8", ORACLE,
        "benchmarks/scientific_truth/oracles/diffusion.py",
        "    return math.exp(-alpha_m2_s * (math.pi / length_m) ** 2 * time_s)",
        "    return math.exp(-alpha_m2_s * (2.0 * math.pi / length_m) ** 2 * time_s)",
        "THE ORACLE ITSELF is given the wrong eigenvalue -- the second mode "
        "instead of the first. The audit must not silently agree with a "
        "broken oracle, and its second, independent FTCS oracle is what "
        "catches this",
        "diffusion_rows",
    ),
    (
        "STP-9", INDEPENDENCE,
        "benchmarks/scientific_truth/oracles/dc.py",
        "def mesh_solve(",
        "def mesh_solve(  # noqa\n"
        "    *args, **kwargs):\n"
        "    from engcore.domains.electrical.dc.solver import solve_circuit  # noqa\n"
        "    raise RuntimeError('coupled oracle')\n"
        "\n"
        "def _unused_mesh_solve(",
        "an oracle is rewritten to import the very solver it checks. The "
        "independence tracer must see that the audit's own oracle has stopped "
        "being independent",
        "independence",
    ),
]

COPY = ("src", "tests", "benchmarks", "pyproject.toml")

CLEAN = {"AGREE", "PASS", "LIMIT_CORRECT", "SIGN_CORRECT", "HOLDS",
         "NO_MATERIAL_CANCELLATION", "CONVERGES_AT_EXPECTED_ORDER"}

PROBE = r'''
import json, sys
sys.path.insert(0, ".")
sys.path.insert(0, "src")
family = sys.argv[1]
CLEAN = %r
if family == "independence":
    from benchmarks.scientific_truth.audit.independence import survey
    report = survey()
    coupled = [
        row for row in report["this_audits_oracles"]
        if row["verdict"] != "INDEPENDENT_OF_CORE"
    ]
    print(json.dumps({"dirty": len(coupled), "detail": coupled}))
else:
    from benchmarks.scientific_truth.audit import checks
    rows = getattr(checks, family)()
    dirty = [r for r in rows if r.get("verdict") not in CLEAN]
    print(json.dumps({
        "dirty": len(dirty),
        "detail": [
            {k: v for k, v in row.items() if k in
             ("check", "model", "case", "verdict", "relative_error", "limit", "invariant")}
            for row in dirty[:6]
        ],
    }, default=str))
''' % (CLEAN,)


def _stage(work: pathlib.Path) -> None:
    work.mkdir(parents=True, exist_ok=True)
    for item in COPY:
        source = REPO / item
        target = work / item
        if source.is_dir():
            shutil.copytree(
                source, target,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".venv"),
            )
        else:
            shutil.copy2(source, target)


def _probe(work: pathlib.Path, family: str) -> dict:
    script = work / "_st_probe.py"
    script.write_text(PROBE, encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(script), family],
        cwd=work, capture_output=True, text=True, timeout=1800,
    )
    if completed.returncode != 0:
        # A plant that makes the check CRASH has still been detected: the
        # audit did not return a clean answer. Recorded distinctly so the
        # difference is visible rather than blurred into a pass.
        return {
            "dirty": -1, "crashed": True,
            "stderr": completed.stderr.strip().splitlines()[-1:] or [""],
        }
    return json.loads(completed.stdout.strip().splitlines()[-1])


def control() -> dict:
    with tempfile.TemporaryDirectory(prefix="sciencetruth") as tmp:
        work = pathlib.Path(tmp) / "repo"
        _stage(work)
        families = sorted({plant[6] for plant in PLANTS})
        results = {family: _probe(work, family) for family in families}
        clean = all(entry.get("dirty") == 0 for entry in results.values())
        return {
            "id": "CONTROL", "status": "GREEN" if clean else "RED (the audit is broken)",
            "green": clean, "per_family": results,
        }


def run(plant) -> dict:
    pid, klass, relative, old, new, breaks, family = plant
    with tempfile.TemporaryDirectory(prefix="sciencetruth") as tmp:
        work = pathlib.Path(tmp) / "repo"
        _stage(work)
        path = work / relative
        text = path.read_text(encoding="utf-8")
        occurrences = text.count(old)
        if occurrences != 1:
            return {
                "id": pid, "class": klass, "file": relative, "breaks": breaks,
                "detector": family, "status": "DID_NOT_APPLY", "caught": False,
                "detail": f"anchor appears {occurrences} times",
            }
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        outcome = _probe(work, family)
        caught = outcome.get("dirty", 0) != 0
        return {
            "id": pid, "class": klass, "file": relative, "breaks": breaks,
            "detector": family,
            "status": "DETECTED" if caught else "MISSED (the audit did not notice)",
            "caught": caught, "findings": outcome,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROUND / "PLANTED_DEFECTS.json"))
    args = parser.parse_args()

    control_result = control()
    results = [run(plant) for plant in PLANTS]
    caught = sum(1 for row in results if row["caught"])
    by_class: dict[str, dict[str, int]] = {}
    for row in results:
        bucket = by_class.setdefault(row["class"], {"total": 0, "caught": 0})
        bucket["total"] += 1
        bucket["caught"] += int(row["caught"])

    payload = {
        "schema": "scientific_truth_planted_defects/1",
        "what_this_is": (
            "Falsification of this round's own oracles. Each plant is a "
            "mathematical defect of one adjudicated class, made in a temporary "
            "copy of the repository and discarded with it."
        ),
        "why_these_are_not_the_earlier_rounds_plants": (
            "Every plant here leaves the published record, the validity "
            "conditions and the software contract completely intact and "
            "changes only the mathematics. Neither a record check nor a "
            "capability-boundary check can see any of them."
        ),
        "two_plants_target_the_audit_itself": (
            "STP-8 corrupts one of this audit's own oracles and STP-9 couples "
            "another to the code it checks. An audit that cannot catch its own "
            "oracles going wrong has no business reporting that the Core is "
            "right -- and this round has already had five audit defects."
        ),
        "control": control_result,
        "total": len(results),
        "caught": caught,
        "missed": [row["id"] for row in results if not row["caught"]],
        "by_class": by_class,
        "results": results,
    }
    pathlib.Path(args.out).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"control: {control_result['status']}")
    print(f"planted scientific defects: {caught}/{len(results)} detected")
    for row in results:
        print(f"  {row['id']:7s} {row['class']:28s} {row['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
