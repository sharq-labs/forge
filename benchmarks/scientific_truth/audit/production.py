"""Thin adapters onto the production solvers.

The only job here is to call each domain's own entry point and hand back plain
floats. No arithmetic is done in this file: anything computed here would be
arithmetic the oracles could accidentally be compared against instead of the
Core.
"""

from __future__ import annotations

from engcore.scientific.units.quantity import Quantity as Q


def lumped(*, capacity, conductance, ambient, initial, heat_w, duration_s) -> dict:
    from engcore.domains.thermal_models.lumped import (
        LumpedThermalSolver,
        ThermalBody,
        build_lumped_thermal_problem,
    )

    body = ThermalBody(
        body_id="ST",
        heat_capacity=Q(capacity, "joule / kelvin"),
        ambient_conductance=Q(conductance, "watt / kelvin"),
        ambient_temperature=Q(ambient, "kelvin"),
        initial_temperature=Q(initial, "kelvin"),
        duration=Q(duration_s, "second"),
    )
    problem = build_lumped_thermal_problem(body)
    solver = LumpedThermalSolver()
    solver.bind_body(body, problem.problem_id, heat_input=Q(heat_w, "watt"))
    prepared = solver.prepare(problem)
    raw = solver.solve(prepared)
    metrics = solver.extract_metrics(prepared, raw)
    return {
        key: value.magnitude_in(value.units) for key, value in metrics.items()
    } | {"_raw": dict(raw.values)}


def conduction(*, length, alpha, end_time, n_cells, n_steps) -> dict:
    from engcore.domains.thermal.conduction1d.problem import (
        MIDPOINT_METRIC,
        ConductionSlab,
        SlabDiscretization,
    )
    from engcore.domains.thermal.conduction1d.solver import solve_slab

    slab = ConductionSlab(
        slab_id="ST",
        length=Q(length, "meter"),
        diffusivity=Q(alpha, "meter ** 2 / second"),
        end_time=Q(end_time, "second"),
        discretization=SlabDiscretization(n_cells=n_cells, n_steps=n_steps),
    )
    result = solve_slab(slab, run_id="st-probe")
    return {
        "midpoint": result.values[MIDPOINT_METRIC].magnitude_in("dimensionless"),
        "fourier_number": slab.fourier_number,
        "dx": slab.dx_m,
        "dt": slab.dt_s,
    }


def battery_step(
    *, capacity_ah, resistance, v_full, v_empty, efficiency, current_a, z0,
    temperature_k, duration_s, cutoff_soc=None, cutoff_voltage=None, limits=None,
) -> dict:
    from engcore.domains.battery.cell import CellSpecification, DischargeLoad
    from engcore.domains.battery.context import CellLimits
    from engcore.domains.battery.solver import evaluate_step

    cell = CellSpecification(
        cell_id="ST",
        nominal_capacity=Q(capacity_ah, "ampere_hour"),
        internal_resistance=Q(resistance, "ohm"),
        open_circuit_voltage_at_full=Q(v_full, "volt"),
        open_circuit_voltage_at_empty=Q(v_empty, "volt"),
        coulombic_efficiency=Q(efficiency, "dimensionless"),
        limits=limits or CellLimits(),
    )
    load = DischargeLoad(
        load_id="ST",
        current=Q(current_a, "ampere"),
        initial_state_of_charge=Q(z0, "dimensionless"),
        cell_temperature=Q(temperature_k, "kelvin"),
        duration=Q(duration_s, "second"),
        cutoff_state_of_charge=None if cutoff_soc is None else Q(cutoff_soc, "dimensionless"),
        cutoff_voltage=None if cutoff_voltage is None else Q(cutoff_voltage, "volt"),
    )
    values = evaluate_step(cell, load)
    return {
        "final_state_of_charge": values.final_state_of_charge,
        "open_circuit_voltage": values.open_circuit_voltage,
        "terminal_voltage": values.terminal_voltage,
        "heat_generation": values.heat_generation,
        "runtime_to_cutoff": values.runtime_to_cutoff,
        "binding_cutoff": values.binding_cutoff_state_of_charge,
        "effective_capacity": values.effective_capacity,
    }


def dc_circuit(
    *, nodes, reference, resistors, voltage_sources, current_sources
) -> dict:
    from engcore.domains.electrical.dc.circuit import DCCircuit
    from engcore.domains.electrical.dc.components import (
        DCCurrentSource,
        DCVoltageSource,
        ElectricalNode,
        Resistor,
    )
    from engcore.domains.electrical.dc.solver import solve_circuit

    circuit = DCCircuit(
        circuit_id="ST",
        nodes=tuple(
            ElectricalNode(node_id=name, is_reference=(name == reference))
            for name in nodes
        ),
        resistors=tuple(
            Resistor(component_id=cid, node_a=a, node_b=b, resistance=Q(r, "ohm"))
            for cid, a, b, r in resistors
        ),
        voltage_sources=tuple(
            DCVoltageSource(
                component_id=cid, positive_node=p, negative_node=n,
                voltage=Q(v, "volt"),
            )
            for cid, p, n, v in voltage_sources
        ),
        current_sources=tuple(
            DCCurrentSource(
                component_id=cid, from_node=f, to_node=t, current=Q(i, "ampere")
            )
            for cid, f, t, i in current_sources
        ),
    )
    result = solve_circuit(circuit, run_id="st-probe")
    values = {key: value.magnitude_in(value.units) for key, value in result.values.items()}
    return {"values": values, "convergence": result.convergence.value}


def material_resistance(*, r_ref, alpha, t_ref, temperature) -> float:
    from engcore.domains.electrical import material as M

    conductor = M.TemperatureDependentConductor(
        component_id="ST",
        reference_resistance=Q(r_ref, "ohm"),
        temperature_coefficient=Q(alpha, "1 / kelvin"),
        reference_temperature=Q(t_ref, "kelvin"),
        limits=M.MaterialLimits(),
    )
    problem = M.build_resistance_problem(conductor)
    solver = M.ResistancePropertySolver()
    solver.bind_conductor(conductor, problem.problem_id, temperature=Q(temperature, "kelvin"))
    prepared = solver.prepare(problem)
    raw = solver.solve(prepared)
    return solver.extract_metrics(prepared, raw)["resistance"].magnitude_in("ohm")


def cstr(
    *, k0, energy, dh, rho, cp, volume, flow, caf, tf, tc, ua, end_time, c0, t0,
    n_output_points=None,
) -> dict:
    from engcore.domains.kinetics.cstr.problem import (
        ReactorChemistry,
        ReactorOperation,
        ReactorRun,
    )
    from engcore.domains.kinetics.cstr.solver import solve_reactor

    chemistry = ReactorChemistry(
        k0=Q(k0, "1 / second"),
        activation_energy=Q(energy, "joule / mole"),
        heat_of_reaction=Q(dh, "joule / mole"),
        density=Q(rho, "kilogram / meter ** 3"),
        heat_capacity=Q(cp, "joule / kelvin / kilogram"),
    )
    operation = ReactorOperation(
        volume=Q(volume, "meter ** 3"),
        flow_rate=Q(flow, "meter ** 3 / second"),
        feed_concentration=Q(caf, "mole / meter ** 3"),
        feed_temperature=Q(tf, "kelvin"),
        coolant_temperature=Q(tc, "kelvin"),
        ua=Q(ua, "watt / kelvin"),
        end_time=Q(end_time, "second"),
    )
    run = ReactorRun(
        run_label="ST",
        chemistry=chemistry,
        operation=operation,
        initial_concentration=Q(c0, "mole / meter ** 3"),
        initial_temperature=Q(t0, "kelvin"),
    )
    result = solve_reactor(run, run_id="st-probe")
    values = {key: value.magnitude_in(value.units) for key, value in result.values.items()}
    return {
        "values": values,
        "convergence": result.convergence.value,
        "a_per_s": operation.dilution_rate_per_s,
        "beta": chemistry.beta_m3_k_per_mol,
        "gamma": run.gamma_per_s,
    }
