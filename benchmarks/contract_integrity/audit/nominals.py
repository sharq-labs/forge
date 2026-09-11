"""Full, physically valid declarations — one per system.

Every optional field is present, so that dropping exactly one field is a
controlled experiment. Values sit in the deep interior of each model's declared
domain: Blind V2's own worst challenge-side defect was a generator that walked
an emissivity past 1 and a state of charge below 0, so every value here is
checked against its physical range before it is used (see `assert_physical`).
"""

from __future__ import annotations

import sys
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO / "src"))

from engcore.scientific.units.quantity import Quantity as Q  # noqa: E402
import engcore.domains.thermal_models.context as tc  # noqa: E402
import engcore.domains.electrical.material as em  # noqa: E402
import engcore.domains.battery.context as bc  # noqa: E402
import engcore.domains.kinetics.cstr.context as cc  # noqa: E402
import engcore.domains.electrical.dc.models as dm  # noqa: E402


def assert_physical() -> list[str]:
    """Guard the audit's own inputs. An invalid case is an audit defect."""
    problems = []
    if not 0.0 <= LUMPED_BASE[tc.SURFACE_EMISSIVITY].magnitude_in("dimensionless") <= 1.0:
        problems.append("surface_emissivity outside [0, 1]")
    for name in ("usable_soc_minimum", "usable_soc_maximum"):
        v = BATTERY_BASE[name].magnitude_in("dimensionless")
        if not 0.0 <= v <= 1.0:
            problems.append(f"{name} outside [0, 1]")
    if not 0.0 <= BATTERY_STATE["state_of_charge"].magnitude_in("dimensionless") <= 1.0:
        problems.append("state_of_charge outside [0, 1]")
    if BATTERY_BASE["coulombic_efficiency"].magnitude_in("dimensionless") > 1.0:
        problems.append("coulombic_efficiency above 1")
    if CSTR_BASE["activation_energy"].magnitude_in("joule / mole") < 0.0:
        problems.append("activation_energy negative")
    for label, q, unit in (
        ("heat_capacity", LUMPED_BASE["heat_capacity"], "joule / kelvin"),
        ("ambient_conductance", LUMPED_BASE["ambient_conductance"], "watt / kelvin"),
        ("reference_resistance", MATERIAL_BASE["reference_resistance"], "ohm"),
        ("nominal_capacity", BATTERY_BASE["nominal_capacity"], "ampere_hour"),
        ("internal_resistance", BATTERY_BASE["internal_resistance"], "ohm"),
        ("k0", CSTR_BASE["k0"], "1 / second"),
        ("residence_time", CSTR_BASE["residence_time"], "second"),
    ):
        if q.magnitude_in(unit) <= 0.0:
            problems.append(f"{label} not strictly positive")
    return problems


# ---- thermal.lumped ------------------------------------------------------
LUMPED_BASE = {
    "heat_capacity": Q(900.0, "joule / kelvin"),
    "ambient_conductance": Q(0.796, "watt / kelvin"),
    "duration": Q(5000.0, "second"),
    tc.CHARACTERISTIC_LENGTH: Q(1e-3, "meter"),
    tc.BODY_VOLUME: Q(2e-5, "meter ** 3"),
    tc.SURFACE_AREA: Q(0.02, "meter ** 2"),
    tc.BODY_CONDUCTIVITY: Q(200.0, "watt / kelvin / meter"),
    tc.SURFACE_EMISSIVITY: Q(0.05, "dimensionless"),
    tc.CONDUCTANCE_EXCURSION_BOUND: Q(40.0, "kelvin"),
    tc.CAPACITY_EXCURSION_BOUND: Q(60.0, "kelvin"),
    tc.MELTING_TEMPERATURE: Q(900.0, "kelvin"),
    tc.FLUID_CONDUCTIVITY: Q(0.026, "watt / kelvin / meter"),
    tc.FLUID_VISCOSITY: Q(1.5e-5, "meter ** 2 / second"),
    tc.FLUID_PRANDTL_NUMBER: Q(0.71, "dimensionless"),
    tc.FLUID_VELOCITY: Q(5.0, "meter / second"),
    tc.CONVECTION_LENGTH: Q(0.05, "meter"),
}
LUMPED_STATE = {
    "initial_temperature": Q(300.0, "kelvin"),
    "ambient_temperature": Q(295.0, "kelvin"),
    "heat_input": Q(6.37, "watt"),
}


def assemble_lumped(base, state):
    return tc.derived_lumped_quantities(base, **state)


# ---- electrical.material -------------------------------------------------
MATERIAL_BASE = {
    "reference_resistance": Q(100.0, "ohm"),
    "temperature_coefficient": Q(0.00393, "1 / kelvin"),
    "reference_temperature": Q(293.15, "kelvin"),
    "linearization_band": Q(100.0, "kelvin"),
    "maximum_operating_temperature": Q(440.0, "kelvin"),
    "debye_temperature": Q(275.0, "kelvin"),
}
MATERIAL_STATE = {
    "temperature": Q(350.0, "kelvin"),
    "coldest_temperature": Q(293.15, "kelvin"),
    "furthest_temperature": Q(350.0, "kelvin"),
}


def assemble_material(base, state):
    return em.derived_material_quantities(base, **state)


# ---- battery.cell --------------------------------------------------------
BATTERY_BASE = {
    "nominal_capacity": Q(2.5, "ampere_hour"),
    "internal_resistance": Q(0.035, "ohm"),
    "open_circuit_voltage_at_full": Q(4.2, "volt"),
    "open_circuit_voltage_at_empty": Q(3.0, "volt"),
    "coulombic_efficiency": Q(1.0, "dimensionless"),
    "duration": Q(600.0, "second"),
    "pulse_current": Q(7.5, "ampere"),
    "pulse_duration": Q(10.0, "second"),
    "continuous_discharge_c_rate": Q(3.0, "1 / hour"),
    "pulse_discharge_c_rate": Q(8.0, "1 / hour"),
    "rated_pulse_duration": Q(30.0, "second"),
    "usable_soc_minimum": Q(0.05, "dimensionless"),
    "usable_soc_maximum": Q(1.0, "dimensionless"),
    "minimum_discharge_temperature": Q(253.15, "kelvin"),
    "maximum_discharge_temperature": Q(333.15, "kelvin"),
    "resistance_reference_temperature": Q(298.15, "kelvin"),
    "resistance_temperature_span": Q(25.0, "kelvin"),
    "cell_thermal_conductance": Q(0.5, "watt / kelvin"),
    "self_heating_rise_bound": Q(6.0, "kelvin"),
    "polarization_time_constant": Q(45.0, "second"),
    "soc_step_resolution": Q(0.5, "dimensionless"),
    "capacity_reference_temperature": Q(298.15, "kelvin"),
    "capacity_temperature_span": Q(20.0, "kelvin"),
    "peukert_exponent": Q(1.1, "dimensionless"),
    "peukert_reference_current": Q(2.5, "ampere"),
    "peukert_fit_decades": Q(1.0, "dimensionless"),
    "peukert_reference_temperature": Q(298.15, "kelvin"),
    "peukert_temperature_span": Q(15.0, "kelvin"),
    "cutoff_voltage": Q(3.0, "volt"),
    "cutoff_state_of_charge": Q(0.1, "dimensionless"),
}
BATTERY_STATE = {
    "state_of_charge": Q(0.9, "dimensionless"),
    "discharge_current": Q(2.5, "ampere"),
    "cell_temperature": Q(298.15, "kelvin"),
}


def assemble_battery(base, state):
    return bc.derived_cell_quantities(base, **state)


# ---- kinetics.cstr -------------------------------------------------------
CSTR_BASE = {
    "k0": Q(7.2e10, "1 / second"),
    "activation_energy": Q(72750.0, "joule / mole"),
    cc.HEAT_OF_REACTION: Q(-5.0e4, "joule / mole"),
    cc.DENSITY: Q(1000.0, "kilogram / meter ** 3"),
    cc.HEAT_CAPACITY: Q(239.0, "joule / kelvin / kilogram"),
    cc.FEED_CONCENTRATION: Q(1000.0, "mole / meter ** 3"),
    cc.INITIAL_CONCENTRATION: Q(500.0, "mole / meter ** 3"),
    cc.FEED_TEMPERATURE: Q(350.0, "kelvin"),
    cc.INITIAL_TEMPERATURE: Q(350.0, "kelvin"),
    cc.COOLANT_TEMPERATURE: Q(300.0, "kelvin"),
    "ua": Q(5.0e4, "watt / kelvin"),
    "residence_time": Q(60.0, "second"),
    "end_time": Q(600.0, "second"),
}
CSTR_STATE: dict = {}


def assemble_cstr(base, state):
    return cc.derived_cstr_quantities(base)


# ---- electrical.dc -------------------------------------------------------
DC_RATING_FIELDS = {
    "rated_power": Q(0.25, "watt"),
    "rated_power_temperature": Q(343.15, "kelvin"),
    "zero_power_temperature": Q(428.15, "kelvin"),
    "maximum_working_voltage": Q(200.0, "volt"),
    "maximum_current": Q(0.1, "ampere"),
    "compliance_voltage": Q(50.0, "volt"),
}
DC_BASE = dict(DC_RATING_FIELDS, ambient_temperature=Q(298.15, "kelvin"))
DC_STATE = {
    "dissipated_power": Q(0.014, "watt"),
    "voltage_across": Q(3.75, "volt"),
    "source_current": Q(0.00375, "ampere"),
    "terminal_voltage": Q(3.75, "volt"),
}


def assemble_dc(base, state):
    """All three rated DC contexts plus KCL, merged into one namespace."""
    rating = dm.ComponentRating(
        **{k: base.get(k) for k in DC_RATING_FIELDS}, derating_factor=1.0
    )
    out: dict = {}
    out.update(
        dm.resistor_rating_context(
            rating=rating,
            dissipated_power=state.get("dissipated_power"),
            voltage_across=state.get("voltage_across"),
            ambient_temperature=base.get("ambient_temperature"),
        )
    )
    out.update(
        dm.voltage_source_rating_context(
            rating=rating, source_current=state.get("source_current")
        )
    )
    out.update(
        dm.current_source_rating_context(
            rating=rating, terminal_voltage=state.get("terminal_voltage")
        )
    )
    out.update(dm.kcl_validity_context())
    return out


SYSTEMS = {
    "thermal.lumped": (LUMPED_BASE, LUMPED_STATE, assemble_lumped),
    "electrical.material": (MATERIAL_BASE, MATERIAL_STATE, assemble_material),
    "battery.cell": (BATTERY_BASE, BATTERY_STATE, assemble_battery),
    "kinetics.cstr": (CSTR_BASE, CSTR_STATE, assemble_cstr),
    "electrical.dc": (DC_BASE, DC_STATE, assemble_dc),
}


# =========================================================================
# Isolated contexts. One assembler per namespace, so a refusal in one cannot
# empty another -- merging them made every DC condition look as though it
# depended on rated_power, which was an artefact of this file and not a
# finding about the Core.
# =========================================================================
import engcore.domains.electrical.dc_applicability as da  # noqa: E402


def _rating(d):
    return dm.ComponentRating(
        **{k: d.get(k) for k in DC_RATING_FIELDS}, derating_factor=1.0
    )


def _dc_resistor(d):
    return set(
        dm.resistor_rating_context(
            rating=_rating(d),
            dissipated_power=d.get("dissipated_power"),
            voltage_across=d.get("voltage_across"),
            ambient_temperature=d.get("ambient_temperature"),
        )
    )


def _dc_voltage_source(d):
    return set(
        dm.voltage_source_rating_context(
            rating=_rating(d), source_current=d.get("source_current")
        )
    )


def _dc_current_source(d):
    return set(
        dm.current_source_rating_context(
            rating=_rating(d), terminal_voltage=d.get("terminal_voltage")
        )
    )


def _dc_kcl(d):
    return set(dm.kcl_validity_context())


def _dc_regulated(d):
    declared = {
        k: d[k]
        for k in ("source_voltage", "output_resistance", "regulation_band")
        if d.get(k) is not None
    }
    problem = da.regulated_source_problem("V1", declared)
    return set(
        da.regulated_source_validity_context(
            problem, source_current=d.get("source_current")
        ).assembled
    )


def _dc_self_heated(d):
    declared = {
        k: d[k]
        for k in (
            "resistance",
            "element_to_body_thermal_resistance",
            "permissible_element_temperature",
        )
        if d.get(k) is not None
    }
    problem = da.self_heated_resistor_problem("R1", declared)
    return set(
        da.self_heated_resistor_validity_context(
            problem,
            body_temperature=d.get("body_temperature"),
            dissipated_power=d.get("dissipated_power"),
        ).assembled
    )


#: The same body on the buoyancy-driven route: no velocity, an expansion
#: coefficient instead. The record's Prandtl claim is route-dependent, so the
#: audit has to be able to stand on both routes.
LUMPED_NATURAL_BASE = {
    k: v for k, v in LUMPED_BASE.items() if k != tc.FLUID_VELOCITY
}
LUMPED_NATURAL_BASE[tc.FLUID_EXPANSION_COEFFICIENT] = Q(1.0 / 300.0, "1 / kelvin")


CONTEXTS = {
    "thermal.lumped.natural": (
        dict(LUMPED_NATURAL_BASE, **LUMPED_STATE),
        lambda d: set(
            tc.derived_lumped_quantities(
                {k: v for k, v in d.items() if k not in LUMPED_STATE},
                initial_temperature=d.get("initial_temperature"),
                ambient_temperature=d.get("ambient_temperature"),
                heat_input=d.get("heat_input"),
            )
        ),
    ),
    "thermal.lumped": (
        dict(LUMPED_BASE, **LUMPED_STATE),
        lambda d: set(
            tc.derived_lumped_quantities(
                {k: v for k, v in d.items() if k not in LUMPED_STATE},
                initial_temperature=d.get("initial_temperature"),
                ambient_temperature=d.get("ambient_temperature"),
                heat_input=d.get("heat_input"),
            )
        ),
    ),
    "electrical.material": (
        dict(MATERIAL_BASE, **MATERIAL_STATE),
        lambda d: set(
            em.derived_material_quantities(
                {k: v for k, v in d.items() if k not in MATERIAL_STATE},
                temperature=d.get("temperature"),
                coldest_temperature=d.get("coldest_temperature"),
                furthest_temperature=d.get("furthest_temperature"),
            )
        )
        | ({"temperature"} if d.get("temperature") is not None else set()),
    ),
    "battery.cell": (
        dict(BATTERY_BASE, **BATTERY_STATE),
        lambda d: set(
            bc.derived_cell_quantities(
                {k: v for k, v in d.items() if k not in BATTERY_STATE},
                state_of_charge=d.get("state_of_charge"),
                discharge_current=d.get("discharge_current"),
                cell_temperature=d.get("cell_temperature"),
            )
        ),
    ),
    "kinetics.cstr": (dict(CSTR_BASE), lambda d: set(cc.derived_cstr_quantities(d))),
    "dc.resistor": (dict(DC_BASE, **{k: DC_STATE[k] for k in ("dissipated_power", "voltage_across")}), _dc_resistor),
    "dc.voltage_source": (dict(DC_BASE, source_current=DC_STATE["source_current"]), _dc_voltage_source),
    "dc.current_source": (dict(DC_BASE, terminal_voltage=DC_STATE["terminal_voltage"]), _dc_current_source),
    "dc.kcl": ({}, _dc_kcl),
    "dc.regulated_source": (
        {
            "source_voltage": Q(12.0, "volt"),
            "output_resistance": Q(0.05, "ohm"),
            "regulation_band": Q(0.02, "dimensionless"),
            "source_current": Q(0.5, "ampere"),
        },
        _dc_regulated,
    ),
    "dc.self_heated": (
        {
            "resistance": Q(1000.0, "ohm"),
            "element_to_body_thermal_resistance": Q(20.0, "kelvin / watt"),
            "permissible_element_temperature": Q(428.15, "kelvin"),
            "body_temperature": Q(320.0, "kelvin"),
            "dissipated_power": Q(0.1, "watt"),
        },
        _dc_self_heated,
    ),
}

#: Which namespace each condition actually lives in.
CONTEXT_OF = {
    ("electrical.dc", "dissipated_power_utilization"): "dc.resistor",
    ("electrical.dc", "working_voltage_utilization"): "dc.resistor",
    ("electrical.dc", "source_current_utilization"): "dc.voltage_source",
    ("electrical.dc", "compliance_voltage_utilization"): "dc.current_source",
    ("electrical.dc", "lumped_electrical_length"): "dc.kcl",
    ("electrical.dc", "source_regulation_utilization"): "dc.regulated_source",
    ("electrical.dc", "element_hot_spot_utilization"): "dc.self_heated",
}
