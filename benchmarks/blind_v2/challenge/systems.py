"""The six shipped scientific systems, as this challenge declares them.

For each system: the fields a caller declares, the unit spellings each field
legally accepts, which of those fields are *spans* (a difference, so an affine
unit cannot state one), a self-consistent deep-interior nominal state, the
lever that moves each declared condition, and the declarations whose absence
makes a condition UNKNOWN.

Every nominal is built so that every condition of its model is decidable and
satisfied -- the convection nominal solves the declared ``hA`` *from* the
correlation rather than choosing it and hoping. A nominal that left conditions
unknown would make "insufficient evidence" the default rather than a case
family, and the challenge would never learn whether the system can tell the
two apart.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

from .oracles import battery as battery_oracle
from .oracles import conduction1d as conduction_oracle
from .oracles import cstr as cstr_oracle
from .oracles import electrical_dc as dc_oracle
from .oracles import material_tcr as material_oracle
from .oracles import thermal_lumped as lumped_oracle

K = "kelvin"


@dataclass(frozen=True)
class SystemSpec:
    system_id: str
    model_id: str
    units: dict[str, tuple[str, ...]]
    span_fields: frozenset[str]
    nominal: Callable[[object], dict]
    oracle: Callable[[dict], dict]
    #: The same forward map with the expensive second route switched off. The
    #: lever search calls it thousands of times per case and needs only the
    #: quantities; the independence evidence is computed once, on the
    #: declaration that is actually kept.
    levers: dict[str, tuple[str, int]]
    evidence: dict[str, tuple[str, ...]]
    dual_conditions: frozenset[str] = frozenset()
    extra_models: tuple[str, ...] = ()
    #: The same forward map with the expensive second route switched off. The
    #: lever search calls it thousands of times per case and needs only the
    #: quantities; the independence evidence is computed once, on the
    #: declaration that is actually kept.
    cheap: Callable[[dict], dict] | None = None
    #: Declarations that are not physical quantities -- a mesh size, a step
    #: count. They carry no unit and are not converted, so they travel beside
    #: the declaration rather than inside it.
    extras: Callable[[object], dict] | None = None
    #: The physical outputs this system's oracles predict, with the tolerance
    #: the prediction is entitled to. Fixed before any run; never widened.
    metrics: Callable[[dict, dict], dict] | None = None
    #: What the two routes of this system actually are, on the registered
    #: scale. A -- an external executable against an in-challenge route.
    #: B -- an analytic closed form against an independent numerical solver.
    #: C -- two genuinely different numerical methods. D is the same equation
    #: relaid out and is never claimed here.
    independence_level: str = "C"


# =========================================================================
# 1. thermal.lumped
# =========================================================================
_LUMPED_UNITS = {
    "heat_capacity": ("joule / kelvin", "kilojoule / kelvin"),
    "ambient_conductance": ("watt / kelvin", "milliwatt / kelvin"),
    "duration": ("second", "minute", "hour"),
    "initial_temperature": (K, "degC", "degF"),
    "ambient_temperature": (K, "degC", "degF"),
    "heat_input": ("watt", "milliwatt", "kilowatt"),
    "characteristic_length": ("meter", "millimeter", "centimeter"),
    "body_volume": ("meter ** 3", "centimeter ** 3", "liter"),
    "surface_area": ("meter ** 2", "centimeter ** 2"),
    "body_conductivity": ("watt / kelvin / meter", "watt / meter / kelvin"),
    "surface_emissivity": ("dimensionless", "percent"),
    "conductance_excursion_bound": (K,),
    "capacity_excursion_bound": (K,),
    "melting_temperature": (K, "degC"),
    "fluid_conductivity": ("watt / kelvin / meter", "watt / meter / kelvin"),
    "fluid_kinematic_viscosity": ("meter ** 2 / second", "centimeter ** 2 / second"),
    "fluid_prandtl_number": ("dimensionless",),
    "fluid_velocity": ("meter / second", "centimeter / second"),
    "convection_length": ("meter", "millimeter", "centimeter"),
}


def _lumped_nominal(rng) -> dict:
    """A body whose declared hA is the one its own correlation predicts."""
    area = rng.choice([0.01, 0.02, 0.04])
    length_c = rng.choice([5e-4, 1e-3, 2e-3])
    volume = length_c * area
    conv_length = rng.choice([0.03, 0.05, 0.08])
    velocity = rng.choice([2.0, 5.0, 8.0])
    nu = 1.5e-5
    prandtl = 0.71
    k_fluid = 0.026
    reynolds = velocity * conv_length / nu
    nusselt = 0.664 * reynolds**0.5 * prandtl ** (1.0 / 3.0)
    h = nusselt * k_fluid / conv_length
    ha = h * area
    capacity = rng.choice([600.0, 900.0, 1500.0])
    tau = capacity / ha
    duration = tau * rng.choice([3.0, 4.0, 6.0])
    t_amb = rng.choice([288.15, 295.0, 300.0])
    rise = rng.choice([4.0, 8.0, 12.0])
    heat = rise * ha
    t0 = t_amb + rng.choice([1.0, 3.0, 5.0])
    return {
        "heat_capacity": capacity,
        "ambient_conductance": ha,
        "duration": duration,
        "initial_temperature": t0,
        "ambient_temperature": t_amb,
        "heat_input": heat,
        "characteristic_length": length_c,
        "body_volume": volume,
        "surface_area": area,
        "body_conductivity": rng.choice([50.0, 200.0, 400.0]),
        "surface_emissivity": rng.choice([0.03, 0.05, 0.08]),
        "conductance_excursion_bound": 40.0,
        "capacity_excursion_bound": 60.0,
        "melting_temperature": rng.choice([700.0, 900.0, 1300.0]),
        "fluid_conductivity": k_fluid,
        "fluid_kinematic_viscosity": nu,
        "fluid_prandtl_number": prandtl,
        "fluid_velocity": velocity,
        "convection_length": conv_length,
    }


LUMPED = SystemSpec(
    system_id="thermal.lumped",
    model_id="thermal.lumped.first_order_capacity",
    units=_LUMPED_UNITS,
    span_fields=frozenset({"conductance_excursion_bound", "capacity_excursion_bound"}),
    nominal=_lumped_nominal,
    oracle=lambda d: lumped_oracle.evaluate(d),
    cheap=lambda d: lumped_oracle.evaluate(d, with_routes=False),
    levers={
        "biot_number": ("body_conductivity", -1),
        "internal_fourier_number": ("duration", -1),
        "conductance_excursion_ratio": ("conductance_excursion_bound", -1),
        "capacity_excursion_ratio": ("capacity_excursion_bound", -1),
        "radiation_to_convection_ratio": ("surface_emissivity", +1),
        "melting_temperature_utilization": ("melting_temperature", -1),
        "geometry_route_ratio": ("characteristic_length", +1),
        "convection_flow_range_utilization": ("fluid_velocity", +1),
        "convection_conductance_agreement_ratio": ("ambient_conductance", +1),
        "heat_capacity": ("heat_capacity", +1),
        "ambient_conductance": ("ambient_conductance", +1),
    },
    evidence={
        "biot_number": ("body_conductivity", "surface_area", "characteristic_length"),
        "internal_fourier_number": ("body_conductivity",),
        "conductance_excursion_ratio": ("conductance_excursion_bound",),
        "capacity_excursion_ratio": ("capacity_excursion_bound",),
        "radiation_to_convection_ratio": ("surface_emissivity",),
        "melting_temperature_utilization": ("melting_temperature",),
        "geometry_route_ratio": ("body_volume",),
        "convection_flow_range_utilization": ("fluid_velocity", "convection_length"),
        "convection_property_range_utilization": ("fluid_prandtl_number",),
        "convection_conductance_agreement_ratio": ("fluid_conductivity",),
    },
    dual_conditions=frozenset(
        {
            "conductance_excursion_ratio",
            "capacity_excursion_ratio",
            "melting_temperature_utilization",
            "radiation_to_convection_ratio",
        }
    ),
    independence_level="B",
)


# =========================================================================
# 2. electrical.material  (rated linear-TCR conductor)
# =========================================================================
_MATERIAL_UNITS = {
    "reference_resistance": ("ohm", "milliohm", "kiloohm"),
    "temperature_coefficient": ("1 / kelvin",),
    "reference_temperature": (K, "degC", "degF"),
    "temperature": (K, "degC", "degF"),
    "linearization_band": (K,),
    "maximum_operating_temperature": (K, "degC"),
    "debye_temperature": (K,),
}


def _material_nominal(rng) -> dict:
    theta = rng.choice([225.0, 275.0, 343.0])  # Pb, Ag, Cu-like Debye temperatures
    reference = rng.choice([293.15, 298.15, 300.0])
    temperature = reference + rng.choice([-30.0, 0.0, 20.0, 45.0])
    return {
        "reference_resistance": rng.choice([1.0, 100.0, 4700.0]),
        "temperature_coefficient": rng.choice([0.00393, 0.0038, 0.0043]),
        "reference_temperature": reference,
        "temperature": temperature,
        "coldest_temperature": min(reference, temperature),
        "furthest_temperature": temperature,
        "linearization_band": rng.choice([80.0, 100.0, 150.0]),
        "maximum_operating_temperature": rng.choice([420.0, 440.0, 445.0]),
        "debye_temperature": theta,
    }


MATERIAL = SystemSpec(
    system_id="electrical.material",
    model_id="electrical.material.rated_linear_tcr_resistance",
    units=_MATERIAL_UNITS,
    span_fields=frozenset({"linearization_band"}),
    nominal=_material_nominal,
    oracle=lambda d: material_oracle.evaluate(d),
    cheap=lambda d: material_oracle.evaluate(d, with_routes=False),
    levers={
        "temperature": ("temperature", +1),
        "linearization_excursion_ratio": ("linearization_band", -1),
        "operating_temperature_utilization": ("maximum_operating_temperature", -1),
        "reduced_debye_temperature": ("debye_temperature", +1),
        "reference_temperature_utilization": ("reference_temperature", +1),
        "reference_reduced_debye_temperature": ("debye_temperature", +1),
        "ceiling_reduced_debye_temperature": ("debye_temperature", +1),
        "linear_resistance_ratio": ("temperature_coefficient", -1),
        "reference_resistance": ("reference_resistance", +1),
    },
    evidence={
        "linearization_excursion_ratio": ("linearization_band",),
        "operating_temperature_utilization": ("maximum_operating_temperature",),
        "reduced_debye_temperature": ("debye_temperature",),
        "reference_temperature_utilization": ("maximum_operating_temperature",),
        "reference_reduced_debye_temperature": ("debye_temperature",),
        "ceiling_reduced_debye_temperature": ("debye_temperature",),
    },
    dual_conditions=frozenset({"linear_resistance_ratio"}),
    extra_models=("electrical.material.linear_tcr_resistance",),
    independence_level="B",
)


# =========================================================================
# 3. battery.cell  (Rint / OCV)
# =========================================================================
_BATTERY_UNITS = {
    "nominal_capacity": ("ampere_hour", "milliampere_hour", "coulomb"),
    "internal_resistance": ("ohm", "milliohm"),
    "open_circuit_voltage_at_full": ("volt", "millivolt"),
    "open_circuit_voltage_at_empty": ("volt", "millivolt"),
    "coulombic_efficiency": ("dimensionless",),
    "duration": ("second", "minute", "hour"),
    "discharge_current": ("ampere", "milliampere"),
    "state_of_charge": ("dimensionless",),
    "cell_temperature": (K, "degC"),
    "pulse_current": ("ampere", "milliampere"),
    "pulse_duration": ("second",),
    "continuous_discharge_c_rate": ("1 / hour", "1 / second"),
    "pulse_discharge_c_rate": ("1 / hour", "1 / second"),
    "rated_pulse_duration": ("second",),
    "usable_soc_minimum": ("dimensionless",),
    "usable_soc_maximum": ("dimensionless",),
    "minimum_discharge_temperature": (K, "degC"),
    "maximum_discharge_temperature": (K, "degC"),
    "resistance_reference_temperature": (K, "degC"),
    "resistance_temperature_span": (K,),
    "cell_thermal_conductance": ("watt / kelvin",),
    "self_heating_rise_bound": (K,),
    "polarization_time_constant": ("second", "minute"),
}


def _battery_nominal(rng) -> dict:
    capacity_ah = rng.choice([2.0, 2.5, 5.0])
    capacity = capacity_ah * 3600.0
    current = capacity_ah * rng.choice([0.5, 1.0, 1.5])
    duration = rng.choice([300.0, 600.0, 900.0])
    z0 = rng.choice([0.85, 0.9, 0.95])
    resistance = rng.choice([0.02, 0.035, 0.05])
    temperature = rng.choice([288.15, 298.15, 308.15])
    return {
        "nominal_capacity": capacity,
        "internal_resistance": resistance,
        "open_circuit_voltage_at_full": 4.2,
        "open_circuit_voltage_at_empty": 3.0,
        "coulombic_efficiency": 1.0,
        "duration": duration,
        "discharge_current": current,
        "state_of_charge": z0,
        "cell_temperature": temperature,
        "pulse_current": current * 3.0,
        "pulse_duration": 10.0,
        "continuous_discharge_c_rate": 3.0 / 3600.0,
        "pulse_discharge_c_rate": 8.0 / 3600.0,
        "rated_pulse_duration": 30.0,
        "usable_soc_minimum": 0.05,
        "usable_soc_maximum": 1.0,
        "minimum_discharge_temperature": 253.15,
        "maximum_discharge_temperature": 333.15,
        "resistance_reference_temperature": temperature,
        "resistance_temperature_span": 25.0,
        "cell_thermal_conductance": 0.5,
        "self_heating_rise_bound": 6.0,
        "polarization_time_constant": 45.0,
    }


BATTERY = SystemSpec(
    system_id="battery.cell",
    model_id="battery.cell.rint_ocv",
    units=_BATTERY_UNITS,
    span_fields=frozenset({"resistance_temperature_span", "self_heating_rise_bound"}),
    nominal=_battery_nominal,
    oracle=lambda d: battery_oracle.evaluate(d),
    cheap=lambda d: battery_oracle.evaluate(d, with_routes=False),
    levers={
        "continuous_c_rate_utilization": ("continuous_discharge_c_rate", -1),
        "pulse_c_rate_utilization": ("pulse_discharge_c_rate", -1),
        "pulse_duration_utilization": ("rated_pulse_duration", -1),
        "soc_window_margin": ("usable_soc_minimum", +1),
        "discharge_temperature_position": ("maximum_discharge_temperature", -1),
        "internal_resistance_drift_ratio": ("resistance_temperature_span", -1),
        "self_heating_rise_ratio": ("self_heating_rise_bound", -1),
        "polarization_unmodelled_fraction": ("polarization_time_constant", +1),
        "terminal_voltage_ratio": ("internal_resistance", -1),
        "nominal_capacity": ("nominal_capacity", +1),
        "internal_resistance": ("internal_resistance", +1),
    },
    evidence={
        "continuous_c_rate_utilization": ("continuous_discharge_c_rate",),
        "pulse_c_rate_utilization": ("pulse_current", "pulse_discharge_c_rate"),
        "pulse_duration_utilization": ("rated_pulse_duration", "pulse_duration"),
        "soc_window_margin": ("usable_soc_minimum", "usable_soc_maximum"),
        "discharge_temperature_position": (
            "minimum_discharge_temperature",
            "maximum_discharge_temperature",
        ),
        "internal_resistance_drift_ratio": ("resistance_temperature_span",),
        "self_heating_rise_ratio": ("cell_thermal_conductance", "self_heating_rise_bound"),
        "polarization_unmodelled_fraction": ("polarization_time_constant",),
    },
    dual_conditions=frozenset({"soc_window_margin", "terminal_voltage_ratio"}),
    extra_models=(
        "battery.cell.coulomb_counting",
        "battery.cell.constant_current_runtime",
        "battery.cell.peukert_capacity_derating",
    ),
    independence_level="B",
)


# =========================================================================
# 4. kinetics.cstr
# =========================================================================
_CSTR_UNITS = {
    "k0": ("1 / second", "1 / minute"),
    "activation_energy": ("joule / mole", "kilojoule / mole"),
    "heat_of_reaction": ("joule / mole", "kilojoule / mole"),
    "density": ("kilogram / meter ** 3", "gram / centimeter ** 3"),
    "heat_capacity": ("joule / kelvin / kilogram", "joule / gram / kelvin"),
    "feed_concentration": ("mole / meter ** 3", "millimole / liter"),
    "initial_concentration": ("mole / meter ** 3", "millimole / liter"),
    "feed_temperature": (K, "degC"),
    "coolant_temperature": (K, "degC"),
    "initial_temperature": (K, "degC"),
    "ua": ("watt / kelvin",),
    "volume": ("meter ** 3", "liter"),
    "residence_time": ("second", "minute"),
    "end_time": ("second", "minute"),
}


def _cstr_nominal(rng) -> dict:
    volume = rng.choice([0.05, 0.1, 0.2])
    residence = rng.choice([40.0, 60.0, 120.0])
    feed_t = rng.choice([320.0, 340.0, 350.0])
    return {
        "k0": rng.choice([7.2e10, 3.0e10, 1.0e11]),
        "activation_energy": rng.choice([69000.0, 72750.0, 80000.0]),
        "heat_of_reaction": rng.choice([-3.0e4, -5.0e4, -7.0e4]),
        "density": 1000.0,
        "heat_capacity": rng.choice([239.0, 4180.0, 2000.0]),
        "feed_concentration": rng.choice([500.0, 1000.0, 2000.0]),
        "initial_concentration": rng.choice([0.0, 500.0, 1000.0]),
        "feed_temperature": feed_t,
        "coolant_temperature": feed_t - rng.choice([20.0, 40.0, 60.0]),
        "initial_temperature": feed_t,
        "ua": rng.choice([2.0e4, 5.0e4, 1.0e5]),
        "volume": volume,
        "residence_time": residence,
        "end_time": residence * rng.choice([5.0, 10.0]),
    }


CSTR = SystemSpec(
    system_id="kinetics.cstr",
    model_id="kinetics.cstr.nonisothermal_first_order",
    units=_CSTR_UNITS,
    span_fields=frozenset(),
    nominal=_cstr_nominal,
    oracle=lambda d: _cstr_quantities(d),
    cheap=lambda d: _cstr_quantities(d, with_routes=False),
    levers={
        "adiabatic_ceiling_temperature": ("heat_of_reaction", -1),
        "k0": ("k0", +1),
        "activation_energy": ("activation_energy", +1),
        "residence_time": ("residence_time", +1),
    },
    evidence={
        "adiabatic_ceiling_temperature": ("heat_of_reaction", "density", "heat_capacity"),
    },
    dual_conditions=frozenset({"adiabatic_ceiling_temperature"}),
    extra_models=("kinetics.cstr.nonisothermal_first_order_constant_rate",),
    independence_level="B",
)


def _cstr_quantities(decl: dict, *, with_routes: bool = True) -> dict:
    """The CSTR oracle, mapped onto the condition names.

    ``temperature`` and ``concentration`` are the model's reserved derived
    names and this challenge never guesses which declared value they resolve
    to. Every generated case keeps all three declared temperatures on the same
    side of the declared band and both concentrations on the same side of zero,
    so the reported value is the one that decides the condition under any
    aggregation -- the extreme nearest the bound in question.
    """
    result = cstr_oracle.evaluate(decl, with_routes=with_routes)
    q = dict(result["quantities"])
    t_min, t_max = q.pop("temperature_min"), q.pop("temperature_max")
    concentration = q.pop("concentration_min")
    if t_min is None or t_max is None:
        q["temperature"] = None
    elif t_min < 250.0:
        q["temperature"] = t_min
    else:
        q["temperature"] = t_max
    q["concentration"] = concentration
    result["quantities"] = q
    return result


# =========================================================================
# 5. thermal.conduction1d
# =========================================================================
_CONDUCTION_UNITS = {
    "alpha": ("meter ** 2 / second", "centimeter ** 2 / second"),
    "length": ("meter", "millimeter", "centimeter"),
    "end_time": ("second", "minute", "hour"),
}


def _conduction_nominal(rng) -> dict:
    length = rng.choice([0.02, 0.05, 0.1, 0.2])
    alpha = rng.choice([1e-6, 1e-5, 9.7e-5, 1.2e-4])
    fourier = rng.choice([0.02, 0.05, 0.1, 0.3])
    return {
        "alpha": alpha,
        "length": length,
        "end_time": fourier * length * length / alpha,
    }


def _conduction_extras(rng) -> dict:
    """The mesh the slab is solved on. A declaration, not a tolerance."""
    cells = rng.choice([40, 80, 120])
    return {"n_cells": cells, "n_steps": rng.choice([200, 400, 800])}


def _conduction_metrics(si: dict, extras: dict) -> dict:
    """The midpoint amplitude, and how far a discrete scheme may legitimately be.

    The expectation is the exact solution. The tolerance is this challenge's
    own Crank-Nicolson error **at the mesh the case declares**, multiplied by
    ten: a second-order scheme on that mesh cannot do much better, and a solver
    that is ten times worse is not paying its discretisation error, it is
    computing something else. Fixed here, before any run, and never widened.
    """
    alpha, length, end_time = si.get("alpha"), si.get("length"), si.get("end_time")
    if None in (alpha, length, end_time) or alpha <= 0.0 or length <= 0.0:
        return {}
    exact = conduction_oracle.analytic_decay(length=length, alpha=alpha, time=end_time)
    if exact == 0.0:
        return {}
    scheme = conduction_oracle.crank_nicolson_midpoint(
        length=length,
        alpha=alpha,
        time=end_time,
        cells=extras["n_cells"],
        steps=extras["n_steps"],
    )
    discretisation = abs(scheme - exact) / abs(exact)
    return {
        "midpoint_amplitude": {
            "expected": exact,
            "route_1": "separation of variables, exact for all time",
            "route_2": "Crank-Nicolson at the declared mesh, solved in-challenge",
            "route_2_value": scheme,
            "relative_tolerance": max(1e-9, 10.0 * discretisation),
            "own_discretisation_error": discretisation,
            "independence_level": "B",
        }
    }


CONDUCTION = SystemSpec(
    system_id="thermal.conduction1d",
    model_id="thermal.conduction1d.linear_diffusion",
    units=_CONDUCTION_UNITS,
    span_fields=frozenset(),
    nominal=_conduction_nominal,
    oracle=lambda d: conduction_oracle.evaluate(d),
    cheap=lambda d: conduction_oracle.evaluate(d, with_routes=False),
    levers={"alpha": ("alpha", +1)},
    evidence={"alpha": ("alpha",)},
    dual_conditions=frozenset({"alpha"}),
    extras=_conduction_extras,
    metrics=_conduction_metrics,
    independence_level="B",
)


# =========================================================================
# 6. electrical.dc
# =========================================================================
_DC_UNITS = {
    "resistance": ("ohm", "kiloohm", "milliohm"),
    "load_resistance": ("ohm", "kiloohm"),
    "source_voltage": ("volt", "millivolt", "kilovolt"),
    "rated_power": ("watt", "milliwatt", "kilowatt"),
    "rated_power_temperature": (K, "degC"),
    "zero_power_temperature": (K, "degC"),
    "maximum_working_voltage": ("volt", "kilovolt"),
    "maximum_current": ("ampere", "milliampere"),
    "derating_factor": ("dimensionless",),
    "ambient_temperature": (K, "degC"),
}


def _dc_nominal(rng) -> dict:
    return {
        "resistance": rng.choice([100.0, 1000.0, 4700.0]),
        "load_resistance": rng.choice([1000.0, 2200.0, 10000.0]),
        "source_voltage": rng.choice([5.0, 12.0, 24.0]),
        "rated_power": rng.choice([0.25, 0.5, 1.0]),
        "rated_power_temperature": 343.15,
        "zero_power_temperature": 428.15,
        "maximum_working_voltage": rng.choice([200.0, 250.0, 350.0]),
        "maximum_current": rng.choice([0.1, 0.5, 1.0]),
        "derating_factor": 1.0,
        "ambient_temperature": rng.choice([293.15, 298.15, 313.15]),
    }


def _dc_quantities(decl: dict, *, with_routes: bool = True) -> dict:
    """Solve the two-resistor divider, then form the resistor's conditions."""
    resistance = decl.get("resistance")
    load = decl.get("load_resistance")
    source = decl.get("source_voltage")
    out: dict[str, float | None] = {"resistance": resistance}
    routes: dict[str, dict] = {}
    intermediate: dict[str, object] = {}
    if None in (resistance, load, source) or resistance <= 0.0 or load <= 0.0:
        out["dissipated_power_utilization"] = None
        out["working_voltage_utilization"] = None
        return {"quantities": out, "routes": routes, "intermediate": intermediate}

    network = dc_oracle.Network(
        circuit_id="v2divider",
        resistors=(
            dc_oracle.Resistor("R1", "n1", "n2", resistance),
            dc_oracle.Resistor("R2", "n2", "0", load),
        ),
        sources=(dc_oracle.VoltageSource("V1", "n1", "0", source),),
    )
    solved = dc_oracle.solve(network, with_external=with_routes)
    analytic = solved["analytic"]
    if analytic is None:
        out["dissipated_power_utilization"] = None
        out["working_voltage_utilization"] = None
        return {"quantities": out, "routes": routes, "intermediate": intermediate}
    elements = dc_oracle.element_quantities(network, analytic)
    across = elements["R1"]["voltage_across"]
    power = elements["R1"]["dissipated_power"]
    current = elements["R1"]["current_through"]
    intermediate.update(
        {
            "voltage_across": across,
            "dissipated_power": power,
            "current_through": current,
            "ngspice": solved["external"],
            "worst_route_gap": solved["worst_gap"],
        }
    )
    if solved["dual_oracle"]:
        routes["operating_point"] = {
            "external": "ngspice",
            "analytic": "modified nodal analysis, solved in-challenge",
            "worst_gap": solved["worst_gap"],
            "independence_level": "A",
            "netlist_sha256": solved["external"].get("netlist_sha256"),
            "output_sha256": solved["external"].get("output_sha256"),
        }

    derating = decl.get("derating_factor", 1.0) or 1.0
    rated = decl.get("rated_power")
    rated_t = decl.get("rated_power_temperature")
    zero_t = decl.get("zero_power_temperature")
    ambient = decl.get("ambient_temperature")
    if rated in (None, 0.0):
        out["dissipated_power_utilization"] = None
    elif rated_t is not None and zero_t is not None:
        if ambient is None or zero_t == rated_t or zero_t == 0.0:
            out["dissipated_power_utilization"] = None
        else:
            implied = (zero_t - rated_t) / rated
            out["dissipated_power_utilization"] = (
                ambient + (power / derating) * implied
            ) / zero_t
    else:
        out["dissipated_power_utilization"] = power / (derating * rated)

    working = decl.get("maximum_working_voltage")
    out["working_voltage_utilization"] = (
        None if working in (None, 0.0) else abs(across) / (derating * working)
    )
    return {"quantities": out, "routes": routes, "intermediate": intermediate}


def _dc_metrics(si: dict, extras: dict) -> dict:
    """Node voltages and element dissipation, with ngspice as the first route.

    A resistive DC network has an exact rational answer, so the two routes have
    no discretisation to disagree over and the tolerance is tight. Where
    ngspice did not run the metric records that and is not offered as dual.
    """
    resistance, load, source = (
        si.get("resistance"),
        si.get("load_resistance"),
        si.get("source_voltage"),
    )
    if None in (resistance, load, source) or resistance <= 0.0 or load <= 0.0:
        return {}
    network = dc_oracle.Network(
        circuit_id="v2divider",
        resistors=(
            dc_oracle.Resistor("R1", "n1", "n2", resistance),
            dc_oracle.Resistor("R2", "n2", "0", load),
        ),
        sources=(dc_oracle.VoltageSource("V1", "n1", "0", source),),
    )
    solved = dc_oracle.solve(network)
    if solved["analytic"] is None:
        return {}
    elements = dc_oracle.element_quantities(network, solved["analytic"])
    external = solved["external"] or {}
    return {
        "node_voltage_n2": {
            "expected": solved["analytic"]["node_voltages"]["n2"],
            "route_1": "ngspice, external process",
            "route_2": "modified nodal analysis, solved in-challenge",
            "route_1_value": (external.get("node_voltages") or {}).get("n2"),
            "relative_tolerance": 1e-9,
            "independence_level": "A" if solved["dual_oracle"] else None,
            "netlist_sha256": external.get("netlist_sha256"),
            "output_sha256": external.get("output_sha256"),
            "ngspice_exit_code": external.get("exit_code"),
        },
        "dissipated_power_R1": {
            "expected": elements["R1"]["dissipated_power"],
            "route_1": "ngspice operating point, P = V*I",
            "route_2": "modified nodal analysis, solved in-challenge",
            "relative_tolerance": 1e-9,
            "independence_level": "A" if solved["dual_oracle"] else None,
        },
    }


DC = SystemSpec(
    system_id="electrical.dc",
    model_id="electrical.dc.resistor_ohm",
    units=_DC_UNITS,
    span_fields=frozenset(),
    nominal=_dc_nominal,
    oracle=_dc_quantities,
    cheap=lambda d: _dc_quantities(d, with_routes=False),
    levers={
        "dissipated_power_utilization": ("rated_power", -1),
        "working_voltage_utilization": ("maximum_working_voltage", -1),
        "resistance": ("resistance", +1),
    },
    evidence={
        "dissipated_power_utilization": ("rated_power", "ambient_temperature"),
        "working_voltage_utilization": ("maximum_working_voltage",),
    },
    dual_conditions=frozenset(
        {"dissipated_power_utilization", "working_voltage_utilization"}
    ),
    extra_models=(
        "electrical.dc.ideal_voltage_source",
        "electrical.dc.kcl",
    ),
    metrics=_dc_metrics,
    independence_level="A",
)


SYSTEMS: tuple[SystemSpec, ...] = (LUMPED, MATERIAL, BATTERY, CSTR, CONDUCTION, DC)
BY_ID = {spec.system_id: spec for spec in SYSTEMS}
