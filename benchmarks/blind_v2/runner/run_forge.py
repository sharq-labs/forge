"""Run the certified Core over the frozen Blind v2 corpus.

Written after the freeze commit, and deliberately kept to one job: turn a
frozen declaration into the call the public contract says to make, and record
what came back. It never reads ``truth/truth.jsonl`` -- the comparison is a
separate program -- and it never writes to the corpus.

Outcomes are kept apart on purpose:

``forge_verdict``
    the Core assessed the declaration and returned a status.
``construction_refusal`` / ``binding_refusal``
    the Core refused to build the record or bind the model. This is a result,
    not a failure: it is what a fail-closed boundary looks like.
``core_error``
    an exception out of the Core that is not one of its declared refusals.
``runner_error``
    a fault in *this* file. Never a finding about the Core.
``timeout``
    the call did not return inside its budget.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import time
import traceback

HERE = pathlib.Path(__file__).resolve().parent
BLIND = HERE.parent
REPO = BLIND.parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(BLIND))

from engcore.scientific.errors import ScientificCoreError  # noqa: E402
from engcore.scientific.units.quantity import Quantity  # noqa: E402
from engcore.scientific.units.validation import UnitCompatibilityError  # noqa: E402

FORGE_VERDICT = "forge_verdict"
CONSTRUCTION_REFUSAL = "construction_refusal"
BINDING_REFUSAL = "binding_refusal"
CORE_ERROR = "core_error"
RUNNER_ERROR = "runner_error"

STATUS_TO_OUTCOME = {
    "in_domain": "SUPPORTED",
    "outside_validated_domain": "NOT_SUPPORTED",
    "unknown": "INSUFFICIENT_EVIDENCE",
}


def core_tree_digest() -> str:
    root = REPO / "src/engcore/scientific"
    h = hashlib.sha256()
    for p in sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts):
        h.update(p.relative_to(root).as_posix().encode())
        h.update(b"\x00")
        h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()


class ConstructionRefused(Exception):
    """The Core would not accept the declaration. Carries the original."""

    def __init__(self, original: BaseException, stage: str):
        super().__init__(str(original))
        self.original = original
        self.stage = stage


def q(declaration: dict, name: str):
    """One declared field as a Quantity, or None when it was not declared.

    A unit the registry does not define, a magnitude that is not a number, a
    dimension that does not fit -- all of them surface here, and all of them
    are the Core refusing at its own boundary rather than this runner failing.
    """
    entry = declaration.get(name)
    if entry is None:
        return None
    try:
        return Quantity(float(entry["value"]), entry["unit"])
    except (UnitCompatibilityError, ScientificCoreError) as exc:
        raise ConstructionRefused(exc, "unit_compatibility") from exc
    except (TypeError, ValueError) as exc:
        raise ConstructionRefused(exc, "schema_type") from exc


# =========================================================================
# per-system invocation
# =========================================================================
def run_thermal_lumped(case: dict):
    from engcore.domains.thermal_models.context import LumpedApplicabilityDeclaration
    from engcore.domains.thermal_models.lumped import (
        ThermalBody,
        assess_lumped_validity,
        build_lumped_thermal_problem,
    )

    d = case["declaration"]
    applicability = LumpedApplicabilityDeclaration(
        characteristic_length=q(d, "characteristic_length"),
        volume=q(d, "body_volume"),
        surface_area=q(d, "surface_area"),
        body_conductivity=q(d, "body_conductivity"),
        surface_emissivity=q(d, "surface_emissivity"),
        conductance_excursion_bound=q(d, "conductance_excursion_bound"),
        capacity_excursion_bound=q(d, "capacity_excursion_bound"),
        melting_temperature=q(d, "melting_temperature"),
        fluid_conductivity=q(d, "fluid_conductivity"),
        fluid_kinematic_viscosity=q(d, "fluid_kinematic_viscosity"),
        fluid_prandtl_number=q(d, "fluid_prandtl_number"),
        fluid_expansion_coefficient=q(d, "fluid_expansion_coefficient"),
        fluid_velocity=q(d, "fluid_velocity"),
        convection_length=q(d, "convection_length"),
    )
    body = ThermalBody(
        body_id=case["case_id"],
        heat_capacity=q(d, "heat_capacity"),
        ambient_conductance=q(d, "ambient_conductance"),
        ambient_temperature=q(d, "ambient_temperature"),
        initial_temperature=q(d, "initial_temperature"),
        duration=q(d, "duration"),
        applicability=applicability,
    )
    problem = build_lumped_thermal_problem(body)
    return assess_lumped_validity(
        problem,
        initial_temperature=q(d, "initial_temperature"),
        ambient_temperature=q(d, "ambient_temperature"),
        heat_input=q(d, "heat_input"),
    ), {}


def run_electrical_material(case: dict):
    from engcore.domains.electrical.material import (
        MaterialLimits,
        TemperatureDependentConductor,
        assess_rated_resistance_validity,
        build_resistance_problem,
    )

    d = case["declaration"]
    conductor = TemperatureDependentConductor(
        component_id=case["case_id"],
        reference_resistance=q(d, "reference_resistance"),
        temperature_coefficient=q(d, "temperature_coefficient"),
        reference_temperature=q(d, "reference_temperature"),
        limits=MaterialLimits(
            linearization_band=q(d, "linearization_band"),
            maximum_operating_temperature=q(d, "maximum_operating_temperature"),
            debye_temperature=q(d, "debye_temperature"),
        ),
    )
    problem = build_resistance_problem(conductor)
    temperature = q(d, "temperature")
    reference = q(d, "reference_temperature")
    coldest = temperature
    if temperature is not None and reference is not None:
        coldest = temperature if temperature.to("kelvin").magnitude <= reference.to(
            "kelvin"
        ).magnitude else reference
    return assess_rated_resistance_validity(
        problem,
        temperature=temperature,
        coldest_temperature=coldest,
        furthest_temperature=temperature,
    ), {}


def run_battery_cell(case: dict):
    from engcore.domains.battery.cell import (
        CellSpecification,
        DischargeLoad,
        assess_rint_validity,
        build_battery_problem,
    )
    from engcore.domains.battery.context import CellLimits

    d = case["declaration"]
    cell = CellSpecification(
        cell_id=case["case_id"],
        nominal_capacity=q(d, "nominal_capacity"),
        internal_resistance=q(d, "internal_resistance"),
        open_circuit_voltage_at_full=q(d, "open_circuit_voltage_at_full"),
        open_circuit_voltage_at_empty=q(d, "open_circuit_voltage_at_empty"),
        coulombic_efficiency=q(d, "coulombic_efficiency"),
        limits=CellLimits(
            continuous_discharge_c_rate=q(d, "continuous_discharge_c_rate"),
            pulse_discharge_c_rate=q(d, "pulse_discharge_c_rate"),
            rated_pulse_duration=q(d, "rated_pulse_duration"),
            usable_soc_minimum=q(d, "usable_soc_minimum"),
            usable_soc_maximum=q(d, "usable_soc_maximum"),
            minimum_discharge_temperature=q(d, "minimum_discharge_temperature"),
            maximum_discharge_temperature=q(d, "maximum_discharge_temperature"),
            resistance_reference_temperature=q(d, "resistance_reference_temperature"),
            resistance_temperature_span=q(d, "resistance_temperature_span"),
            cell_thermal_conductance=q(d, "cell_thermal_conductance"),
            self_heating_rise_bound=q(d, "self_heating_rise_bound"),
            polarization_time_constant=q(d, "polarization_time_constant"),
        ),
    )
    load = DischargeLoad(
        load_id=case["case_id"] + "-load",
        current=q(d, "discharge_current"),
        initial_state_of_charge=q(d, "state_of_charge"),
        cell_temperature=q(d, "cell_temperature"),
        duration=q(d, "duration"),
        pulse_current=q(d, "pulse_current"),
        pulse_duration=q(d, "pulse_duration"),
    )
    problem = build_battery_problem(cell, load)
    return assess_rint_validity(
        problem,
        state_of_charge=q(d, "state_of_charge"),
        discharge_current=q(d, "discharge_current"),
        cell_temperature=q(d, "cell_temperature"),
    ), {}


def run_kinetics_cstr(case: dict):
    from engcore.domains.kinetics.cstr.problem import (
        CSTR_MODEL,
        ReactorChemistry,
        ReactorOperation,
        ReactorRun,
        build_cstr_problem,
    )

    d = case["declaration"]
    volume = q(d, "volume")
    residence = q(d, "residence_time")
    if volume is None or residence is None:
        raise ConstructionRefused(
            ValueError("a CSTR needs a volume and a residence time"), "construction"
        )
    try:
        flow_rate = volume / residence
    except Exception as exc:
        raise ConstructionRefused(exc, "construction") from exc
    run = ReactorRun(
        run_label=case["case_id"],
        chemistry=ReactorChemistry(
            k0=q(d, "k0"),
            activation_energy=q(d, "activation_energy"),
            heat_of_reaction=q(d, "heat_of_reaction"),
            density=q(d, "density"),
            heat_capacity=q(d, "heat_capacity"),
        ),
        operation=ReactorOperation(
            volume=volume,
            flow_rate=flow_rate,
            feed_concentration=q(d, "feed_concentration"),
            feed_temperature=q(d, "feed_temperature"),
            coolant_temperature=q(d, "coolant_temperature"),
            ua=q(d, "ua"),
            end_time=q(d, "end_time"),
        ),
        initial_concentration=q(d, "initial_concentration"),
        initial_temperature=q(d, "initial_temperature"),
    )
    # build_cstr_problem is still called, because a declaration the problem
    # builder will not accept is a refusal and has to surface as one. The
    # context itself comes from ReactorRun.validity_context, which is the
    # canonical path its own docstring names: assembling it by hand from the
    # problem's caller half left the reserved names -- temperature,
    # concentration and the ceiling -- absent, and every condition reading
    # them UNKNOWN. That was this file being wrong about the contract.
    build_cstr_problem(run)
    context = run.validity_context()
    return CSTR_MODEL.assess_validity(
        declared=context.declared, assembled=context.assembled
    ), {}


def run_thermal_conduction1d(case: dict):
    from engcore.domains.thermal.conduction1d.problem import (
        DIFFUSION_MODEL,
        ConductionSlab,
        SlabDiscretization,
        build_conduction_problem,
    )
    from engcore.domains.thermal.conduction1d.solver import solve_slab

    d = case["declaration"]
    extras = case.get("extras") or {}
    slab = ConductionSlab(
        slab_id=case["case_id"],
        length=q(d, "length"),
        diffusivity=q(d, "alpha"),
        end_time=q(d, "end_time"),
        discretization=SlabDiscretization(
            n_cells=int(extras.get("n_cells", 80)),
            n_steps=int(extras.get("n_steps", 200)),
        ),
    )
    problem = build_conduction_problem(slab)
    reserved = DIFFUSION_MODEL.validity.derived_quantities
    assessment = DIFFUSION_MODEL.assess_validity(
        declared=problem.validity_context(reserved=reserved), assembled={}
    )
    metrics: dict = {}
    if assessment.status.value == "in_domain":
        try:
            result = solve_slab(slab, run_id=case["case_id"])
            metrics = _extract_metrics(result, ("u_mid", "midpoint", "u_midpoint"))
        except Exception as exc:  # a solve failure is recorded, not swallowed
            metrics = {"solve_error": f"{type(exc).__name__}: {exc}"}
    return assessment, metrics


def run_electrical_dc(case: dict):
    from engcore.domains.electrical.dc.circuit import DCCircuit
    from engcore.domains.electrical.dc.components import (
        DCVoltageSource,
        ElectricalNode,
        Resistor,
    )
    from engcore.domains.electrical.dc.models import (
        ComponentRating,
        ambient_transfer_declaration,
        assess_resistor_validity,
    )
    from engcore.scientific.composition.transfer import QuantityTransfer
    from engcore.domains.electrical.dc.problem import resistor_relation_problem
    from engcore.domains.electrical.dc.solver import solve_circuit

    d = case["declaration"]
    resistor = Resistor(
        component_id="R1", node_a="n1", node_b="n2", resistance=q(d, "resistance")
    )
    load = Resistor(
        component_id="R2", node_a="n2", node_b="0", resistance=q(d, "load_resistance")
    )
    source = DCVoltageSource(
        component_id="V1", positive_node="n1", negative_node="0", voltage=q(d, "source_voltage")
    )
    circuit = DCCircuit(
        circuit_id=case["case_id"],
        nodes=(
            ElectricalNode(node_id="0", is_reference=True),
            ElectricalNode(node_id="n1"),
            ElectricalNode(node_id="n2"),
        ),
        resistors=(resistor, load),
        voltage_sources=(source,),
    )
    metrics: dict = {}
    across = power = None
    try:
        result = solve_circuit(circuit, run_id=case["case_id"])
        metrics = _extract_metrics(result, ("V(n2)", "v_n2", "node_voltage_n2"))
        across, power = _resistor_operating_point(result)
    except Exception as exc:
        metrics = {"solve_error": f"{type(exc).__name__}: {exc}"}
    rating = ComponentRating(
        rated_power=q(d, "rated_power"),
        rated_power_temperature=q(d, "rated_power_temperature"),
        zero_power_temperature=q(d, "zero_power_temperature"),
        maximum_working_voltage=q(d, "maximum_working_voltage"),
        maximum_current=q(d, "maximum_current"),
        derating_factor=float(d["derating_factor"]["value"]) if "derating_factor" in d else 1.0,
    )
    # The ambient is not a scalar this model will read. Its own contract says
    # so: a rated dissipation is stated against a reference ambient, the
    # ambient came from somewhere else, and this domain will not read a
    # crossed value that arrives without the record of its crossing. The case
    # declares the ambient; the runner's job is to hand it over by the route
    # the contract names, which is a declared dependency realized as a
    # transfer. Passing it as a bare Quantity -- which the first smoke run did
    # -- leaves the derating line unevaluated and every rating condition
    # UNKNOWN, and that would have been this file's answer, not the Core's.
    ambient = None
    ambient_quantity = q(d, "ambient_temperature")
    if ambient_quantity is not None:
        ambient = QuantityTransfer(
            dependency=ambient_transfer_declaration(
                source_problem_id=f"{case['case_id']}-ambient",
                source_quantity="ambient_temperature",
                component_id="R1",
            ),
            value=ambient_quantity,
            source_record_id=f"{case['case_id']}-ambient-run",
            instant="2026-09-10T00:00:00",
        )
    problem = resistor_relation_problem(resistor)
    assessment = assess_resistor_validity(
        problem,
        rating=rating,
        dissipated_power=power,
        voltage_across=across,
        ambient=ambient,
    )
    return assessment, metrics


def _published_values(result) -> dict:
    """Whatever the run object publishes, as a plain mapping.

    ``ScientificResult.values`` is a frozen mapping, not a dict, so an
    isinstance check against dict misses it entirely -- which is exactly what
    the first smoke run caught: the DC operating point never reached the
    rating conditions and every one of them read UNKNOWN. That was this file's
    fault, found on handwritten examples before a single frozen case ran.
    """
    values = getattr(result, "values", None)
    if values is None:
        return {}
    try:
        return dict(values)
    except Exception:
        return {}


def _extract_metrics(result, names) -> dict:
    return {str(k): _plain(v) for k, v in _published_values(result).items()}


def _resistor_operating_point(result):
    """Voltage across and power dissipated in R1, from the solved run."""
    values = _published_values(result)
    return values.get("resistor_voltage:R1"), values.get("resistor_power:R1")


def _plain(value):
    for attribute in ("magnitude",):
        if hasattr(value, attribute):
            try:
                return {"magnitude": float(value.magnitude), "units": str(value.units)}
            except Exception:
                return str(value)
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    return str(value)


RUNNERS = {
    "thermal.lumped": run_thermal_lumped,
    "electrical.material": run_electrical_material,
    "battery.cell": run_battery_cell,
    "kinetics.cstr": run_kinetics_cstr,
    "thermal.conduction1d": run_thermal_conduction1d,
    "electrical.dc": run_electrical_dc,
}

#: Exceptions the public contract declares. Anything else out of the Core is
#: recorded as a core_error and triaged separately.
DECLARED_REFUSALS = (ScientificCoreError, UnitCompatibilityError)


def run_case(case: dict) -> dict:
    started = time.perf_counter()
    # A shadow is addressed by its own id and carries its parent's. The runner
    # does not care which it is holding: it makes the call the declaration
    # asks for and records what came back.
    case = dict(case)
    case.setdefault("case_id", case.get("shadow_id"))
    record = {
        "case_id": case["case_id"],
        "parent_case_id": case.get("parent_case_id"),
        "transformation": case.get("transformation"),
        "system": case["system"],
        "model_id": case["model_id"],
    }
    runner = RUNNERS.get(case["system"])
    if runner is None:
        record.update(outcome_kind=RUNNER_ERROR, detail="no runner for this system")
        record["runtime_s"] = time.perf_counter() - started
        return record
    try:
        assessment, metrics = runner(case)
    except ConstructionRefused as refused:
        record.update(
            outcome_kind=CONSTRUCTION_REFUSAL,
            forge_outcome="REJECTED_AT_BOUNDARY",
            refusal_stage=refused.stage,
            exception_type=type(refused.original).__name__,
            detail=str(refused)[:400],
        )
        record["runtime_s"] = time.perf_counter() - started
        return record
    except DECLARED_REFUSALS as exc:
        stage = "unit_compatibility" if isinstance(exc, UnitCompatibilityError) else "construction"
        record.update(
            outcome_kind=CONSTRUCTION_REFUSAL,
            forge_outcome="REJECTED_AT_BOUNDARY",
            refusal_stage=stage,
            exception_type=type(exc).__name__,
            detail=str(exc)[:400],
        )
        record["runtime_s"] = time.perf_counter() - started
        return record
    except (TypeError, ValueError) as exc:
        # A type or value the Core would not take. Its own construction guards
        # raise these, so it is recorded as a refusal at the schema boundary
        # and the type is kept so triage can tell the two apart.
        record.update(
            outcome_kind=CONSTRUCTION_REFUSAL,
            forge_outcome="REJECTED_AT_BOUNDARY",
            refusal_stage="schema_type",
            exception_type=type(exc).__name__,
            detail=str(exc)[:400],
            traceback=traceback.format_exc()[-1200:],
        )
        record["runtime_s"] = time.perf_counter() - started
        return record
    except Exception as exc:
        record.update(
            outcome_kind=CORE_ERROR,
            forge_outcome="CORE_ERROR",
            exception_type=type(exc).__name__,
            detail=str(exc)[:400],
            traceback=traceback.format_exc()[-2000:],
        )
        record["runtime_s"] = time.perf_counter() - started
        return record

    record.update(
        outcome_kind=FORGE_VERDICT,
        forge_status=assessment.status.value,
        forge_outcome=STATUS_TO_OUTCOME.get(assessment.status.value, "CORE_ERROR"),
        satisfied=sorted(assessment.satisfied),
        violated=sorted(assessment.violated),
        unknown=sorted(assessment.unknown),
        unknown_reasons={
            str(getattr(u, "name", u)): str(
                getattr(getattr(u, "reason", None), "value", getattr(u, "reason", ""))
            )
            for u in assessment.unknown_reasons
        },
        metrics=metrics,
    )
    record["runtime_s"] = time.perf_counter() - started
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--label", default="primary")
    args = parser.parse_args()

    cases = [json.loads(line) for line in pathlib.Path(args.cases).read_text().splitlines()]
    started = time.time()
    records = [run_case(case) for case in cases]
    payload = {
        "schema": "blind_v2_run/1",
        "label": args.label,
        "cases_file": args.cases,
        "cases_file_sha256": hashlib.sha256(
            pathlib.Path(args.cases).read_bytes()
        ).hexdigest(),
        "core_tree_sha256": core_tree_digest(),
        "started_unix": started,
        "wall_seconds": time.time() - started,
        "python": sys.version.split()[0],
        "records": records,
    }
    pathlib.Path(args.out).write_text(
        json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    kinds: dict[str, int] = {}
    for record in records:
        kinds[record["outcome_kind"]] = kinds.get(record["outcome_kind"], 0) + 1
    print(f"{len(records)} records in {payload['wall_seconds']:.1f}s: {kinds}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
