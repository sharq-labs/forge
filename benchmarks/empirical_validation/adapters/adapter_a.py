"""Branch A: raw fixture -> engcore declarations -> the Core's own answer.

This file is allowed to import engcore, and it does one thing: it states the
fixture's physical quantities to the Core in the fixture's own units and hands
back what the Core returned.

TWO DELIBERATE CHOICES.

First, the fixture's units are handed to engcore rather than converted before
handing them over. ``Quantity(2600.0, "milliampere_hour")`` is given to the cell
declaration as it stands. If the conversion were done here the Core's own unit
machinery would never run, and unit handling is a large part of what a caller
depends on.

Second, the derived quantities -- ``C = m c_p``, ``hA = h A``,
``alpha = k/(rho c_p)``, ``R_ref = rho L / A``, ``beta = -dH/(rho c_p)`` -- are
derived HERE, with engcore quantity arithmetic, and separately again in
adapter_b with plain floats. Neither side sees the other's result. A property
or geometry mix-up therefore produces a disagreement instead of being resolved
identically on both sides before either solver ran.

What this file does not do is any physics. Nothing here evaluates a model, and
nothing here is compared against anything. It builds a problem and reads a
result.
"""

from __future__ import annotations

from engcore.scientific.units.quantity import Quantity as Q


# ---------------------------------------------------------------------------
# Thermal: lumped body
# ---------------------------------------------------------------------------


def lumped(fixture: dict, **overrides) -> dict:
    from engcore.domains.thermal_models.lumped import (
        LumpedThermalSolver,
        ThermalBody,
        build_lumped_thermal_problem,
    )

    q = dict(fixture["quantities"]) | overrides
    # C = m c_p and hA = h A, in the fixture's units, through engcore's own
    # unit arithmetic.
    heat_capacity = Q(q["mass_g"], "gram") * Q(
        q["specific_heat_J_per_g_K"], "joule / gram / kelvin"
    )
    conductance = Q(
        q["convection_coefficient_W_per_m2_K"], "watt / meter ** 2 / kelvin"
    ) * Q(q["surface_area_cm2"], "centimeter ** 2")

    body = ThermalBody(
        body_id="EV-LUMPED",
        heat_capacity=heat_capacity,
        ambient_conductance=conductance,
        ambient_temperature=Q(q["ambient_degC"], "degC"),
        initial_temperature=Q(q["initial_degC"], "degC"),
        duration=Q(q["duration_min"], "minute"),
    )
    problem = build_lumped_thermal_problem(body)
    solver = LumpedThermalSolver()
    solver.bind_body(body, problem.problem_id, heat_input=Q(q["heat_input_mW"], "milliwatt"))
    prepared = solver.prepare(problem)
    raw = solver.solve(prepared)
    metrics = solver.extract_metrics(prepared, raw)
    return {
        "received": {
            "heat_capacity_j_per_k": body.heat_capacity.magnitude_in("joule / kelvin"),
            "ambient_conductance_w_per_k": body.ambient_conductance.magnitude_in(
                "watt / kelvin"
            ),
            "ambient_temperature_k": body.ambient_temperature.magnitude_in("kelvin"),
            "initial_temperature_k": body.initial_temperature.magnitude_in("kelvin"),
            "duration_s": body.duration.magnitude_in("second"),
            "heat_input_w": Q(q["heat_input_mW"], "milliwatt").magnitude_in("watt"),
        },
        "final_temperature_k": metrics["final_temperature"].magnitude_in("kelvin"),
        "steady_state_temperature_k": metrics["steady_state_temperature"].magnitude_in(
            "kelvin"
        ),
        "time_constant_s": metrics["time_constant"].magnitude_in("second"),
    }


# ---------------------------------------------------------------------------
# Thermal: 1-D slab
# ---------------------------------------------------------------------------


def slab(fixture: dict, **overrides) -> dict:
    from engcore.domains.thermal.conduction1d.problem import (
        MIDPOINT_METRIC,
        ConductionSlab,
        SlabDiscretization,
    )
    from engcore.domains.thermal.conduction1d.solver import solve_slab

    q = dict(fixture["quantities"]) | overrides
    # alpha = k / (rho c_p)
    diffusivity = Q(q["thermal_conductivity_W_per_m_K"], "watt / meter / kelvin") / (
        Q(q["density_g_per_cm3"], "gram / centimeter ** 3")
        * Q(q["specific_heat_J_per_g_K"], "joule / gram / kelvin")
    )
    declared = ConductionSlab(
        slab_id="EV-SLAB",
        length=Q(q["length_mm"], "millimeter"),
        diffusivity=diffusivity,
        end_time=Q(q["end_time_min"], "minute"),
        discretization=SlabDiscretization(
            n_cells=int(q["n_cells"]), n_steps=int(q["n_steps"])
        ),
    )
    result = solve_slab(declared, run_id="ev-probe")
    return {
        "received": {
            "length_m": declared.length_m,
            "diffusivity_m2_per_s": declared.alpha_m2_s,
            "end_time_s": declared.end_time_s,
            "n_cells": declared.discretization.n_cells,
            "n_steps": declared.discretization.n_steps,
            "dx_m": declared.dx_m,
            "dt_s": declared.dt_s,
        },
        "midpoint": result.values[MIDPOINT_METRIC].magnitude_in("dimensionless"),
        "fourier_number": declared.fourier_number,
    }


# ---------------------------------------------------------------------------
# Battery cell
# ---------------------------------------------------------------------------


def battery(fixture: dict, **overrides) -> dict:
    from engcore.domains.battery.cell import CellSpecification, DischargeLoad
    from engcore.domains.battery.context import CellLimits
    from engcore.domains.battery.solver import evaluate_step

    q = dict(fixture["quantities"]) | overrides
    limits = CellLimits(
        peukert_exponent=Q(q["peukert_exponent"], "dimensionless"),
        peukert_reference_current=Q(q["peukert_reference_current_mA"], "milliampere"),
    )
    cell = CellSpecification(
        cell_id="EV-CELL",
        nominal_capacity=Q(q["nominal_capacity_mAh"], "milliampere_hour"),
        internal_resistance=Q(q["internal_resistance_mOhm"], "milliohm"),
        open_circuit_voltage_at_full=Q(q["open_circuit_voltage_at_full_mV"], "millivolt"),
        open_circuit_voltage_at_empty=Q(
            q["open_circuit_voltage_at_empty_mV"], "millivolt"
        ),
        coulombic_efficiency=Q(q["coulombic_efficiency"], "dimensionless"),
        limits=limits,
    )
    load = DischargeLoad(
        load_id="EV-LOAD",
        current=Q(q["discharge_current_mA"], "milliampere"),
        initial_state_of_charge=Q(q["initial_state_of_charge"], "dimensionless"),
        cell_temperature=Q(q["cell_temperature_degC"], "degC"),
        duration=Q(q["duration_min"], "minute"),
        cutoff_voltage=Q(q["cutoff_voltage_mV"], "millivolt"),
    )
    values = evaluate_step(cell, load)
    return {
        "received": {
            "nominal_capacity_c": cell.nominal_capacity.magnitude_in("coulomb"),
            "nominal_capacity_ah": cell.nominal_capacity.magnitude_in("ampere_hour"),
            "internal_resistance_ohm": cell.internal_resistance.magnitude_in("ohm"),
            "open_circuit_voltage_at_full_v": (
                cell.open_circuit_voltage_at_full.magnitude_in("volt")
            ),
            "open_circuit_voltage_at_empty_v": (
                cell.open_circuit_voltage_at_empty.magnitude_in("volt")
            ),
            "coulombic_efficiency": cell.coulombic_efficiency.magnitude_in(
                "dimensionless"
            ),
            "current_a": load.current.magnitude_in("ampere"),
            "initial_state_of_charge": load.initial_state_of_charge.magnitude_in(
                "dimensionless"
            ),
            "cell_temperature_k": load.cell_temperature.magnitude_in("kelvin"),
            "duration_s": load.duration.magnitude_in("second"),
            "cutoff_voltage_v": load.cutoff_voltage.magnitude_in("volt"),
            "peukert_exponent": limits.peukert_exponent.magnitude_in("dimensionless"),
            "peukert_reference_current_a": (
                limits.peukert_reference_current.magnitude_in("ampere")
            ),
        },
        "final_state_of_charge": values.final_state_of_charge,
        "open_circuit_voltage_v": values.open_circuit_voltage,
        "terminal_voltage_v": values.terminal_voltage,
        "heat_generation_w": values.heat_generation,
        "runtime_to_cutoff_s": values.runtime_to_cutoff,
        "binding_cutoff_state_of_charge": values.binding_cutoff_state_of_charge,
        "effective_capacity": values.effective_capacity,
    }


# ---------------------------------------------------------------------------
# Conductor and platinum thermometer
# ---------------------------------------------------------------------------


def conductor(fixture: dict, **overrides) -> dict:
    from engcore.domains.electrical import material as M

    q = dict(fixture["quantities"]) | overrides
    # R_ref = rho L / A
    reference_resistance = (
        Q(q["resistivity_nOhm_m"], "nanoohm * meter") * Q(q["length_mm"], "millimeter")
    ) / Q(q["cross_section_mm2"], "millimeter ** 2")
    declared = M.TemperatureDependentConductor(
        component_id="EV-COND",
        reference_resistance=reference_resistance,
        temperature_coefficient=Q(
            q["temperature_coefficient_ppm_per_K"] * 1e-6, "1 / kelvin"
        ),
        reference_temperature=Q(q["reference_temperature_degC"], "degC"),
        limits=M.MaterialLimits(
            linearization_band=Q(q["linearization_band_K"], "kelvin"),
            maximum_operating_temperature=Q(
                q["maximum_operating_temperature_degC"], "degC"
            ),
        ),
    )
    return _resistance_at(
        declared, Q(q["operating_temperature_degC"], "degC")
    ) | {
        "received": {
            "reference_resistance_ohm": declared.reference_resistance.magnitude_in(
                "ohm"
            ),
            "temperature_coefficient_per_k": (
                declared.temperature_coefficient.magnitude_in("1 / kelvin")
            ),
            "reference_temperature_k": declared.reference_temperature.magnitude_in(
                "kelvin"
            ),
            "operating_temperature_k": Q(
                q["operating_temperature_degC"], "degC"
            ).magnitude_in("kelvin"),
            "linearization_band_k": declared.limits.linearization_band.magnitude_in(
                "kelvin"
            ),
            "maximum_operating_temperature_k": (
                declared.limits.maximum_operating_temperature.magnitude_in("kelvin")
            ),
        }
    }


def _resistance_at(declared, temperature) -> dict:
    from engcore.domains.electrical import material as M

    problem = M.build_resistance_problem(declared)
    solver = M.ResistancePropertySolver()
    solver.bind_conductor(declared, problem.problem_id, temperature=temperature)
    prepared = solver.prepare(problem)
    raw = solver.solve(prepared)
    metrics = solver.extract_metrics(prepared, raw)
    return {"resistance_ohm": metrics["resistance"].magnitude_in("ohm")}


def platinum(fixture: dict, **overrides) -> list[dict]:
    """The linear model declared with the standard's own R0, A and ice point."""
    from engcore.domains.electrical import material as M

    q = dict(fixture["quantities"]) | overrides
    declared = M.TemperatureDependentConductor(
        component_id="EV-PT100",
        reference_resistance=Q(q["r_zero_ohm"], "ohm"),
        temperature_coefficient=Q(q["coefficient_A_per_degC"], "1 / kelvin"),
        reference_temperature=Q(0.0, "degC"),
        limits=M.MaterialLimits(),
    )
    rows = []
    for celsius in q["comparison_temperatures_degC"]:
        rows.append(
            {"temperature_degC": celsius}
            | _resistance_at(declared, Q(celsius, "degC"))
        )
    return rows


# ---------------------------------------------------------------------------
# DC circuits
# ---------------------------------------------------------------------------


def circuit(raw: dict) -> dict:
    from engcore.domains.electrical.dc.circuit import DCCircuit
    from engcore.domains.electrical.dc.components import (
        DCCurrentSource,
        DCVoltageSource,
        ElectricalNode,
        Resistor,
    )
    from engcore.domains.electrical.dc.solver import solve_circuit

    reference = raw["reference_node"]
    declared = DCCircuit(
        circuit_id=raw["circuit_id"],
        nodes=tuple(
            ElectricalNode(node_id=name, is_reference=(name == reference))
            for name in raw["nodes"]
        ),
        resistors=tuple(
            Resistor(
                component_id=r["id"],
                node_a=r["node_a"],
                node_b=r["node_b"],
                resistance=Q(r["resistance_kohm"], "kiloohm"),
            )
            for r in raw["resistors"]
        ),
        voltage_sources=tuple(
            DCVoltageSource(
                component_id=s["id"],
                positive_node=s["positive_node"],
                negative_node=s["negative_node"],
                voltage=Q(s["voltage_mV"], "millivolt"),
            )
            for s in raw["voltage_sources"]
        ),
        current_sources=tuple(
            DCCurrentSource(
                component_id=s["id"],
                from_node=s["from_node"],
                to_node=s["to_node"],
                current=Q(s["current_mA"], "milliampere"),
            )
            for s in raw["current_sources"]
        ),
    )
    result = solve_circuit(declared, run_id="ev-probe")
    return {
        "received": {
            "resistors_ohm": {
                r.component_id: r.resistance.magnitude_in("ohm")
                for r in declared.resistors
            },
            "voltage_sources_v": {
                s.component_id: s.voltage.magnitude_in("volt")
                for s in declared.voltage_sources
            },
            "current_sources_a": {
                s.component_id: s.current.magnitude_in("ampere")
                for s in declared.current_sources
            },
            "reference_node": next(
                n.node_id for n in declared.nodes if n.is_reference
            ),
            "nodes": [n.node_id for n in declared.nodes],
        },
        "values": {
            key: value.magnitude_in(value.units) for key, value in result.values.items()
        },
        "units": {key: value.units for key, value in result.values.items()},
        "convergence": result.convergence.value,
    }


def regulated_source(raw_declared: dict, *, source_current_a: float) -> dict:
    """The regulated-source companion record, declared from the raw fixture."""
    from engcore.domains.electrical import dc_applicability as A

    declared = {
        A.SOURCE_VOLTAGE: Q(raw_declared["voltage_mV"], "millivolt"),
        A.OUTPUT_RESISTANCE: Q(raw_declared["output_resistance_mohm"], "milliohm"),
        A.REGULATION_BAND: raw_declared["regulation_band"],
    }
    problem = A.regulated_source_problem("V1", declared)
    assessment = A.assess_regulated_source_validity(
        problem, source_current=Q(source_current_a, "ampere")
    )
    utilization = A.source_regulation_utilization(
        source_current=Q(source_current_a, "ampere"),
        source_voltage=Q(raw_declared["voltage_mV"], "millivolt"),
        output_resistance=Q(raw_declared["output_resistance_mohm"], "milliohm"),
        regulation_band=Q(raw_declared["regulation_band"], "dimensionless"),
    )
    return {
        "received": {
            "source_voltage_v": declared[A.SOURCE_VOLTAGE].magnitude_in("volt"),
            "output_resistance_ohm": declared[A.OUTPUT_RESISTANCE].magnitude_in("ohm"),
            "regulation_band": declared[A.REGULATION_BAND],
        },
        "utilization": utilization.magnitude_in("dimensionless"),
        "status": assessment.status.value,
    }


def self_heated_resistor(raw_declared: dict, *, dissipated_power_w: float) -> dict:
    """The self-heated element companion record, declared from the raw fixture."""
    from engcore.domains.electrical import dc_applicability as A

    declared = {
        A.ELEMENT_TO_BODY_THERMAL_RESISTANCE: Q(
            raw_declared["element_to_body_thermal_resistance_K_per_W"], "kelvin / watt"
        ),
        A.PERMISSIBLE_ELEMENT_TEMPERATURE: Q(
            raw_declared["permissible_element_temperature_degC"], "degC"
        ),
    }
    problem = A.self_heated_resistor_problem("R2", declared)
    body = Q(raw_declared["body_temperature_degC"], "degC")
    assessment = A.assess_self_heated_resistor_validity(
        problem,
        body_temperature=body,
        dissipated_power=Q(dissipated_power_w, "watt"),
    )
    utilization = A.element_hot_spot_utilization(
        body_temperature=body,
        dissipated_power=Q(dissipated_power_w, "watt"),
        element_to_body_thermal_resistance=declared[
            A.ELEMENT_TO_BODY_THERMAL_RESISTANCE
        ],
        permissible_element_temperature=declared[A.PERMISSIBLE_ELEMENT_TEMPERATURE],
    )
    return {
        "received": {
            "element_to_body_thermal_resistance_k_per_w": declared[
                A.ELEMENT_TO_BODY_THERMAL_RESISTANCE
            ].magnitude_in("kelvin / watt"),
            "permissible_element_temperature_k": declared[
                A.PERMISSIBLE_ELEMENT_TEMPERATURE
            ].magnitude_in("kelvin"),
            "body_temperature_k": body.magnitude_in("kelvin"),
        },
        "utilization": utilization.magnitude_in("dimensionless"),
        "status": assessment.status.value,
    }


# ---------------------------------------------------------------------------
# CSTR
# ---------------------------------------------------------------------------


def reactor(fixture: dict, *, constant_rate: bool = False, **overrides) -> dict:
    from engcore.domains.kinetics.cstr.problem import (
        ReactorChemistry,
        ReactorOperation,
        ReactorRun,
    )
    from engcore.domains.kinetics.cstr.solver import solve_reactor

    q = dict(fixture["quantities"])
    if constant_rate:
        variant = fixture["constant_rate_variant"]
        q["activation_energy_kJ_per_mol"] = variant["activation_energy_kJ_per_mol"]
        q["k0_per_min"] = variant["k_const_per_min"]
    q |= overrides

    chemistry = ReactorChemistry(
        k0=Q(q["k0_per_min"], "1 / minute"),
        activation_energy=Q(q["activation_energy_kJ_per_mol"], "kilojoule / mole"),
        heat_of_reaction=Q(q["heat_of_reaction_kJ_per_mol"], "kilojoule / mole"),
        density=Q(q["density_g_per_cm3"], "gram / centimeter ** 3"),
        heat_capacity=Q(q["specific_heat_J_per_g_K"], "joule / gram / kelvin"),
    )
    operation = ReactorOperation(
        volume=Q(q["volume_L"], "liter"),
        flow_rate=Q(q["feed_flow_L_per_min"], "liter / minute"),
        feed_concentration=Q(q["feed_concentration_mol_per_L"], "mole / liter"),
        feed_temperature=Q(q["feed_temperature_degC"], "degC"),
        coolant_temperature=Q(q["coolant_temperature_degC"], "degC"),
        ua=Q(q["ua_kJ_per_min_per_K"], "kilojoule / minute / kelvin"),
        end_time=Q(q["end_time_min"], "minute"),
    )
    run = ReactorRun(
        run_label="EV-CSTR",
        chemistry=chemistry,
        operation=operation,
        initial_concentration=Q(
            q["initial_concentration_mol_per_L"], "mole / liter"
        ),
        initial_temperature=Q(q["initial_temperature_degC"], "degC"),
    )
    result = solve_reactor(run, run_id="ev-probe")
    return {
        "received": {
            "volume_m3": operation.volume.magnitude_in("meter ** 3"),
            "flow_m3_per_s": operation.flow_rate.magnitude_in("meter ** 3 / second"),
            "dilution_rate_per_s": operation.dilution_rate_per_s,
            "density_kg_per_m3": chemistry.density.magnitude_in(
                "kilogram / meter ** 3"
            ),
            "specific_heat_j_per_kg_k": chemistry.heat_capacity.magnitude_in(
                "joule / kelvin / kilogram"
            ),
            "heat_of_reaction_j_per_mol": chemistry.heat_of_reaction.magnitude_in(
                "joule / mole"
            ),
            "beta_m3_k_per_mol": chemistry.beta_m3_k_per_mol,
            "ua_w_per_k": operation.ua.magnitude_in("watt / kelvin"),
            "gamma_per_s": run.gamma_per_s,
            "k0_per_s": chemistry.k0.magnitude_in("1 / second"),
            "activation_energy_j_per_mol": chemistry.activation_energy.magnitude_in(
                "joule / mole"
            ),
            "feed_concentration_mol_per_m3": operation.feed_concentration.magnitude_in(
                "mole / meter ** 3"
            ),
            "feed_temperature_k": operation.feed_temperature.magnitude_in("kelvin"),
            "coolant_temperature_k": operation.coolant_temperature.magnitude_in(
                "kelvin"
            ),
            "end_time_s": operation.end_time.magnitude_in("second"),
            "initial_concentration_mol_per_m3": (
                run.initial_concentration.magnitude_in("mole / meter ** 3")
            ),
            "initial_temperature_k": run.initial_temperature.magnitude_in("kelvin"),
        },
        "values": {
            key: value.magnitude_in(value.units) for key, value in result.values.items()
        },
        "units": {key: value.units for key, value in result.values.items()},
        "convergence": result.convergence.value,
    }
