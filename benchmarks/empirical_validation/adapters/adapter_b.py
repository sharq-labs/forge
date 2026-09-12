"""Branch B: raw fixture -> plain SI numbers. No engcore anywhere.

This file imports nothing from engcore, nothing from adapter_a, and nothing
from the previous rounds. Its conversion factors are written out below, in this
file, as literals. That is not duplication for its own sake: if both branches
called one conversion helper, a wrong factor would move both answers together
and the comparison would pass while the physics was wrong.

Temperatures are the case that matters most. A temperature on the Celsius scale
and a temperature difference in kelvin are different things, and this file keeps
them apart explicitly: ``_absolute`` adds 273.15, ``_span`` does not.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# This file's unit factors. Written here, on purpose, and nowhere else.
# ---------------------------------------------------------------------------
GRAM_TO_KILOGRAM = 1.0e-3
CM2_TO_M2 = 1.0e-4
MM_TO_M = 1.0e-3
MM2_TO_M2 = 1.0e-6
MILLI = 1.0e-3
KILO = 1.0e3
NANO = 1.0e-9
PPM = 1.0e-6
MINUTE_TO_SECOND = 60.0
LITRE_TO_M3 = 1.0e-3
G_PER_CM3_TO_KG_PER_M3 = 1.0e3
J_PER_G_K_TO_J_PER_KG_K = 1.0e3
MOL_PER_L_TO_MOL_PER_M3 = 1.0e3
MAH_TO_COULOMB = 3.6  # 1 mAh = 1e-3 A * 3600 s
CELSIUS_OFFSET = 273.15


def _absolute(celsius: float) -> float:
    """A point on the Celsius scale as an absolute temperature."""
    return celsius + CELSIUS_OFFSET


def _span(kelvin: float) -> float:
    """A temperature DIFFERENCE. No offset. Present so the two never blur."""
    return kelvin


# ---------------------------------------------------------------------------
# Thermal: lumped body
# ---------------------------------------------------------------------------


def lumped(fixture: dict, **overrides) -> dict:
    q = dict(fixture["quantities"]) | overrides
    mass_kg = q["mass_g"] * GRAM_TO_KILOGRAM
    specific_heat = q["specific_heat_J_per_g_K"] * J_PER_G_K_TO_J_PER_KG_K
    area_m2 = q["surface_area_cm2"] * CM2_TO_M2
    return {
        # C = m c_p
        "heat_capacity_j_per_k": mass_kg * specific_heat,
        # hA = h A
        "ambient_conductance_w_per_k": q["convection_coefficient_W_per_m2_K"] * area_m2,
        "ambient_temperature_k": _absolute(q["ambient_degC"]),
        "initial_temperature_k": _absolute(q["initial_degC"]),
        "heat_input_w": q["heat_input_mW"] * MILLI,
        "duration_s": q["duration_min"] * MINUTE_TO_SECOND,
    }


# ---------------------------------------------------------------------------
# Thermal: 1-D slab
# ---------------------------------------------------------------------------


def slab(fixture: dict, **overrides) -> dict:
    q = dict(fixture["quantities"]) | overrides
    density = q["density_g_per_cm3"] * G_PER_CM3_TO_KG_PER_M3
    specific_heat = q["specific_heat_J_per_g_K"] * J_PER_G_K_TO_J_PER_KG_K
    return {
        "length_m": q["length_mm"] * MM_TO_M,
        # alpha = k / (rho c_p)
        "diffusivity_m2_per_s": q["thermal_conductivity_W_per_m_K"]
        / (density * specific_heat),
        "end_time_s": q["end_time_min"] * MINUTE_TO_SECOND,
        "n_cells": int(q["n_cells"]),
        "n_steps": int(q["n_steps"]),
    }


# ---------------------------------------------------------------------------
# Battery cell
# ---------------------------------------------------------------------------


def battery(fixture: dict, **overrides) -> dict:
    q = dict(fixture["quantities"]) | overrides
    return {
        "nominal_capacity_c": q["nominal_capacity_mAh"] * MAH_TO_COULOMB,
        "nominal_capacity_ah": q["nominal_capacity_mAh"] * MILLI,
        "internal_resistance_ohm": q["internal_resistance_mOhm"] * MILLI,
        "open_circuit_voltage_at_full_v": q["open_circuit_voltage_at_full_mV"] * MILLI,
        "open_circuit_voltage_at_empty_v": q["open_circuit_voltage_at_empty_mV"] * MILLI,
        "coulombic_efficiency": q["coulombic_efficiency"],
        "current_a": q["discharge_current_mA"] * MILLI,
        "initial_state_of_charge": q["initial_state_of_charge"],
        "cell_temperature_k": _absolute(q["cell_temperature_degC"]),
        "duration_s": q["duration_min"] * MINUTE_TO_SECOND,
        "cutoff_voltage_v": q["cutoff_voltage_mV"] * MILLI,
        "peukert_exponent": q["peukert_exponent"],
        "peukert_reference_current_a": q["peukert_reference_current_mA"] * MILLI,
    }


# ---------------------------------------------------------------------------
# Conductor
# ---------------------------------------------------------------------------


def conductor(fixture: dict, **overrides) -> dict:
    q = dict(fixture["quantities"]) | overrides
    resistivity = q["resistivity_nOhm_m"] * NANO
    length_m = q["length_mm"] * MM_TO_M
    area_m2 = q["cross_section_mm2"] * MM2_TO_M2
    return {
        # R_ref = rho L / A
        "reference_resistance_ohm": resistivity * length_m / area_m2,
        "temperature_coefficient_per_k": q["temperature_coefficient_ppm_per_K"] * PPM,
        "reference_temperature_k": _absolute(q["reference_temperature_degC"]),
        "operating_temperature_k": _absolute(q["operating_temperature_degC"]),
        # A band is a SPAN, so no offset is applied to it.
        "linearization_band_k": _span(q["linearization_band_K"]),
        "maximum_operating_temperature_k": _absolute(
            q["maximum_operating_temperature_degC"]
        ),
    }


def platinum(fixture: dict, **overrides) -> dict:
    q = dict(fixture["quantities"]) | overrides
    return {
        "r_zero_ohm": q["r_zero_ohm"],
        "coefficient_A_per_degC": q["coefficient_A_per_degC"],
        "coefficient_B_per_degC2": q["coefficient_B_per_degC2"],
        "published_W_100": q["published_W_100"],
        "comparison_temperatures_degC": list(q["comparison_temperatures_degC"]),
        # The linear model this is compared against is referred to 0 degC, so
        # its reference temperature is the ice point on the absolute scale and
        # its coefficient is A.
        "reference_resistance_ohm": q["r_zero_ohm"],
        "reference_temperature_k": CELSIUS_OFFSET,
        "temperature_coefficient_per_k": q["coefficient_A_per_degC"],
    }


# ---------------------------------------------------------------------------
# DC circuits
# ---------------------------------------------------------------------------


def circuit(raw: dict) -> dict:
    return {
        "circuit_id": raw["circuit_id"],
        "nodes": list(raw["nodes"]),
        "reference_node": raw["reference_node"],
        "resistors": [
            {
                "id": r["id"],
                "node_a": r["node_a"],
                "node_b": r["node_b"],
                "resistance_ohm": r["resistance_kohm"] * KILO,
            }
            for r in raw["resistors"]
        ],
        "voltage_sources": [
            {
                "id": s["id"],
                "positive_node": s["positive_node"],
                "negative_node": s["negative_node"],
                "voltage_v": s["voltage_mV"] * MILLI,
            }
            for s in raw["voltage_sources"]
        ],
        "current_sources": [
            {
                "id": s["id"],
                "from_node": s["from_node"],
                "to_node": s["to_node"],
                "current_a": s["current_mA"] * MILLI,
            }
            for s in raw["current_sources"]
        ],
    }


def applicability(raw: dict) -> dict:
    """The declared applicability numbers, in SI, for one circuit."""
    out = {}
    for component_id, declared in raw.get("applicability_declarations", {}).items():
        entry = {}
        if "output_resistance_mohm" in declared:
            entry["output_resistance_ohm"] = declared["output_resistance_mohm"] * MILLI
        if "regulation_band" in declared:
            entry["regulation_band"] = declared["regulation_band"]
        if "element_to_body_thermal_resistance_K_per_W" in declared:
            entry["element_to_body_thermal_resistance_k_per_w"] = declared[
                "element_to_body_thermal_resistance_K_per_W"
            ]
        if "permissible_element_temperature_degC" in declared:
            entry["permissible_element_temperature_k"] = _absolute(
                declared["permissible_element_temperature_degC"]
            )
        if "body_temperature_degC" in declared:
            entry["body_temperature_k"] = _absolute(declared["body_temperature_degC"])
        out[component_id] = entry
    return out


# ---------------------------------------------------------------------------
# CSTR
# ---------------------------------------------------------------------------
#
# The gas constant used by the reference branch is the CODATA 2022 value, taken
# from scipy.constants -- a data table, not a solver, and one the Core does not
# read. The Core's own stored value is compared against it separately rather
# than being adopted here.


def _molar_gas_constant() -> float:
    from scipy.constants import R  # data table only; no scipy solver is used

    return float(R)


def reactor(fixture: dict, *, constant_rate: bool = False, **overrides) -> dict:
    q = dict(fixture["quantities"])
    if constant_rate:
        variant = fixture["constant_rate_variant"]
        q["activation_energy_kJ_per_mol"] = variant["activation_energy_kJ_per_mol"]
        q["k0_per_min"] = variant["k_const_per_min"]
    q |= overrides

    volume_m3 = q["volume_L"] * LITRE_TO_M3
    flow_m3_per_s = q["feed_flow_L_per_min"] * LITRE_TO_M3 / MINUTE_TO_SECOND
    density = q["density_g_per_cm3"] * G_PER_CM3_TO_KG_PER_M3
    specific_heat = q["specific_heat_J_per_g_K"] * J_PER_G_K_TO_J_PER_KG_K
    heat_of_reaction = q["heat_of_reaction_kJ_per_mol"] * KILO
    ua_w_per_k = q["ua_kJ_per_min_per_K"] * KILO / MINUTE_TO_SECOND

    return {
        "volume_m3": volume_m3,
        "flow_m3_per_s": flow_m3_per_s,
        # a = q/V
        "dilution_rate_per_s": flow_m3_per_s / volume_m3,
        "density_kg_per_m3": density,
        "specific_heat_j_per_kg_k": specific_heat,
        "heat_of_reaction_j_per_mol": heat_of_reaction,
        # beta = (-dH)/(rho c_p)
        "beta_m3_k_per_mol": -heat_of_reaction / (density * specific_heat),
        "ua_w_per_k": ua_w_per_k,
        # gamma = UA/(V rho c_p)
        "gamma_per_s": ua_w_per_k / (volume_m3 * density * specific_heat),
        "k0_per_s": q["k0_per_min"] / MINUTE_TO_SECOND,
        "activation_energy_j_per_mol": q["activation_energy_kJ_per_mol"] * KILO,
        "feed_concentration_mol_per_m3": q["feed_concentration_mol_per_L"]
        * MOL_PER_L_TO_MOL_PER_M3,
        "feed_temperature_k": _absolute(q["feed_temperature_degC"]),
        "coolant_temperature_k": _absolute(q["coolant_temperature_degC"]),
        "end_time_s": q["end_time_min"] * MINUTE_TO_SECOND,
        "initial_concentration_mol_per_m3": q["initial_concentration_mol_per_L"]
        * MOL_PER_L_TO_MOL_PER_M3,
        "initial_temperature_k": _absolute(q["initial_temperature_degC"]),
        "molar_gas_constant_j_per_mol_k": _molar_gas_constant(),
    }
