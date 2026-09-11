"""Phase 2 category A — does `required` in the record mean required at runtime?

Each shipped model marks every declared input required or optional. The public
constructor is where that promise is either kept or not. A record that marks an
input required while the constructor happily builds without it is over-broad in
the direction that matters least (the condition will simply be UNKNOWN later);
a record that marks an input OPTIONAL while the constructor refuses without it
is over-broad in the direction a caller feels immediately.
"""

from __future__ import annotations

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROUND = HERE.parent
REPO = ROUND.parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(HERE))

from engcore.scientific.units.quantity import Quantity as Q  # noqa: E402


def battery_builder(omit: str | None):
    from engcore.domains.battery.cell import CellSpecification, DischargeLoad, build_battery_problem
    from engcore.domains.battery.context import CellLimits

    cell_fields = dict(
        cell_id="R", nominal_capacity=Q(2.5, "ampere_hour"),
        internal_resistance=Q(0.035, "ohm"),
        open_circuit_voltage_at_full=Q(4.2, "volt"),
        open_circuit_voltage_at_empty=Q(3.0, "volt"),
        coulombic_efficiency=Q(1.0, "dimensionless"),
        limits=CellLimits(),
    )
    load_fields = dict(
        load_id="L", current=Q(2.5, "ampere"),
        initial_state_of_charge=Q(0.9, "dimensionless"),
        cell_temperature=Q(298.15, "kelvin"), duration=Q(600.0, "second"),
    )
    mapping = {
        "nominal_capacity": ("cell", "nominal_capacity"),
        "internal_resistance": ("cell", "internal_resistance"),
        "open_circuit_voltage_at_full": ("cell", "open_circuit_voltage_at_full"),
        "open_circuit_voltage_at_empty": ("cell", "open_circuit_voltage_at_empty"),
        "coulombic_efficiency": ("cell", "coulombic_efficiency"),
        "discharge_current": ("load", "current"),
        "state_of_charge": ("load", "initial_state_of_charge"),
        "cell_temperature": ("load", "cell_temperature"),
        "duration": ("load", "duration"),
    }
    if omit is not None:
        if omit not in mapping:
            return "NOT_A_CONSTRUCTOR_FIELD"
        which, field = mapping[omit]
        (cell_fields if which == "cell" else load_fields)[field] = None
    cell = CellSpecification(**cell_fields)
    load = DischargeLoad(**load_fields)
    build_battery_problem(cell, load)
    return "ACCEPTED"


def lumped_builder(omit: str | None):
    from engcore.domains.thermal_models.lumped import ThermalBody, build_lumped_thermal_problem

    fields = dict(
        body_id="R", heat_capacity=Q(900.0, "joule / kelvin"),
        ambient_conductance=Q(0.8, "watt / kelvin"),
        ambient_temperature=Q(295.0, "kelvin"),
        initial_temperature=Q(300.0, "kelvin"), duration=Q(5000.0, "second"),
    )
    mapping = {
        "heat_capacity": "heat_capacity",
        "ambient_conductance": "ambient_conductance",
        "ambient_temperature": "ambient_temperature",
        "temperature": "initial_temperature",
        "duration": "duration",
    }
    if omit is not None:
        if omit not in mapping:
            return "NOT_A_CONSTRUCTOR_FIELD"
        fields[mapping[omit]] = None
    build_lumped_thermal_problem(ThermalBody(**fields))
    return "ACCEPTED"


def material_builder(omit: str | None):
    from engcore.domains.electrical.material import (
        MaterialLimits, TemperatureDependentConductor, build_resistance_problem,
    )

    fields = dict(
        component_id="R", reference_resistance=Q(100.0, "ohm"),
        temperature_coefficient=Q(0.00393, "1 / kelvin"),
        reference_temperature=Q(293.15, "kelvin"), limits=MaterialLimits(),
    )
    mapping = {
        "reference_resistance": "reference_resistance",
        "temperature_coefficient": "temperature_coefficient",
        "reference_temperature": "reference_temperature",
    }
    if omit is not None:
        if omit not in mapping:
            return "NOT_A_CONSTRUCTOR_FIELD"
        fields[mapping[omit]] = None
    build_resistance_problem(TemperatureDependentConductor(**fields))
    return "ACCEPTED"


def cstr_builder(omit: str | None):
    from engcore.domains.kinetics.cstr.problem import (
        ReactorChemistry, ReactorOperation, ReactorRun, build_cstr_problem,
    )

    chem = dict(k0=Q(7.2e10, "1 / second"), activation_energy=Q(72750.0, "joule / mole"),
                heat_of_reaction=Q(-5.0e4, "joule / mole"),
                density=Q(1000.0, "kilogram / meter ** 3"),
                heat_capacity=Q(239.0, "joule / kelvin / kilogram"))
    op = dict(volume=Q(0.1, "meter ** 3"), flow_rate=Q(0.1 / 60.0, "meter ** 3 / second"),
              feed_concentration=Q(1000.0, "mole / meter ** 3"),
              feed_temperature=Q(350.0, "kelvin"), coolant_temperature=Q(300.0, "kelvin"),
              ua=Q(5.0e4, "watt / kelvin"), end_time=Q(600.0, "second"))
    run = dict(initial_concentration=Q(500.0, "mole / meter ** 3"),
               initial_temperature=Q(350.0, "kelvin"))
    if omit is not None:
        if omit in chem:
            chem[omit] = None
        elif omit in op:
            op[omit] = None
        elif omit in run:
            run[omit] = None
        elif omit == "residence_time":
            return "NOT_A_CONSTRUCTOR_FIELD"
        else:
            return "NOT_A_CONSTRUCTOR_FIELD"
    build_cstr_problem(
        ReactorRun(run_label="R", chemistry=ReactorChemistry(**chem),
                   operation=ReactorOperation(**op), **run)
    )
    return "ACCEPTED"


def conduction_builder(omit: str | None):
    from engcore.domains.thermal.conduction1d.problem import (
        ConductionSlab, SlabDiscretization, build_conduction_problem,
    )

    fields = dict(slab_id="R", length=Q(0.1, "meter"),
                  diffusivity=Q(1e-5, "meter ** 2 / second"),
                  end_time=Q(60.0, "second"),
                  discretization=SlabDiscretization(n_cells=80, n_steps=200))
    mapping = {"alpha": "diffusivity", "length": "length", "end_time": "end_time"}
    if omit is not None:
        if omit not in mapping:
            return "NOT_A_CONSTRUCTOR_FIELD"
        fields[mapping[omit]] = None
    build_conduction_problem(ConductionSlab(**fields))
    return "ACCEPTED"


BUILDERS = {
    "battery.cell": battery_builder,
    "thermal.lumped": lumped_builder,
    "electrical.material": material_builder,
    "kinetics.cstr": cstr_builder,
    "thermal.conduction1d": conduction_builder,
}


def probe(system: str, field: str | None) -> str:
    builder = BUILDERS.get(system)
    if builder is None:
        return "NO_BUILDER"
    try:
        return builder(field)
    except Exception as exc:
        return f"REFUSED:{type(exc).__name__}"


def main() -> int:
    surface = json.loads((ROUND / "CONTRACT_SURFACE.json").read_text(encoding="utf-8"))
    rows = []
    baseline: dict[str, str] = {}
    for system in BUILDERS:
        baseline[system] = probe(system, None)

    seen: set[tuple[str, str]] = set()
    for model in surface["models"]:
        system = model["system"]
        if system not in BUILDERS:
            continue
        for field in model["required_inputs_per_record"]:
            key = (system, field)
            if key in seen:
                continue
            seen.add(key)
            outcome = probe(system, field)
            if outcome == "NOT_A_CONSTRUCTOR_FIELD":
                result = "NOT_CONSTRUCTOR_ADDRESSABLE"
                note = ("the record marks this required, and it reaches the model "
                        "through a route the public constructor does not expose as "
                        "an omittable field")
            elif outcome.startswith("REFUSED"):
                result = "MATCH"
                note = f"the constructor refuses without it ({outcome})"
            else:
                result = "RECORD_TOO_BROAD"
                note = ("the record marks this REQUIRED and the public constructor "
                        "builds a problem without it")
            rows.append({
                "system": system, "model_id": model["model_id"], "input": field,
                "record_says": "required", "runtime": outcome,
                "result": result, "note": note,
            })
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["result"]] = counts.get(row["result"], 0) + 1
    payload = {
        "schema": "contract_integrity_required_inputs/1",
        "baseline_construction": baseline,
        "checks_run": len(rows),
        "result_counts": dict(sorted(counts.items())),
        "rows": rows,
    }
    (ROUND / "REQUIRED_INPUTS.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("baseline:", baseline)
    print("checks:", len(rows), json.dumps(payload["result_counts"]))
    for row in rows:
        if row["result"] != "MATCH":
            print(f"  {row['result']:28s} {row['system']}::{row['input']} -> {row['runtime']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
