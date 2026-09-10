"""Every UNKNOWN promise, read by hand and written down as a testable shape.

The shipped records write their preconditions in prose -- "unless both edges
are declared", "unless the operating point is supplied" -- so a regex cannot
turn them into an experiment. Each clause below was read and mapped to the
declarations it names, with the clause quoted beside the mapping so the
reading itself can be audited.

Two shapes:

``all_of``   dropping ANY one of these must make the condition UNKNOWN.
``one_of``   each group is a set of alternative routes: dropping the WHOLE
             group must make the condition UNKNOWN, and dropping a single
             member must NOT, because the record says the other route serves.

An entry with neither is a condition the record makes no UNKNOWN promise about.
"""

from __future__ import annotations

# (system, condition) -> mapping
CLAIMS: dict[tuple[str, str], dict] = {
    # ---- thermal.lumped -------------------------------------------------
    ("thermal.lumped", "biot_number"): {
        "clause": "UNKNOWN unless surface_area, body_conductivity and a characteristic length (declared, or derived from body_volume/surface_area) are supplied.",
        "all_of": ["surface_area", "body_conductivity"],
        "one_of": [["characteristic_length", "body_volume"]],
        "reading": "body_volume is an ALTERNATIVE route to the length, not a third requirement; the clause says so in parentheses.",
    },
    ("thermal.lumped", "conductance_excursion_ratio"): {
        "clause": "UNKNOWN unless conductance_excursion_bound is supplied and the operating point is known.",
        "all_of": ["conductance_excursion_bound", "heat_input", "ambient_temperature", "initial_temperature"],
        "reading": "'the operating point' is the heat input and the two temperatures the assessment is given.",
    },
    ("thermal.lumped", "capacity_excursion_ratio"): {
        "clause": "UNKNOWN unless capacity_excursion_bound is supplied.",
        "all_of": ["capacity_excursion_bound"],
    },
    ("thermal.lumped", "radiation_to_convection_ratio"): {
        "clause": "UNKNOWN unless surface_emissivity and surface_area are supplied.",
        "all_of": ["surface_emissivity", "surface_area"],
    },
    ("thermal.lumped", "convection_flow_range_utilization"): {
        "clause": "UNKNOWN unless the convection_length, the kinematic viscosity, the operating point and one of the two route declarations are supplied. THE PRANDTL NUMBER IS NEEDED ON THE NATURAL ROUTE ONLY.",
        "all_of": ["convection_length", "fluid_kinematic_viscosity"],
        "one_of": [["fluid_velocity"]],
        "reading": (
            "Post-CI-1. On the forced route Re = u L / nu carries no Prandtl "
            "number, so it is NOT in all_of here. The natural route is checked "
            "separately by the entry below, which is what makes the record's "
            "route asymmetry testable in both directions rather than asserted."
        ),
    },
    ("thermal.lumped.natural", "convection_flow_range_utilization"): {
        "clause": "THE PRANDTL NUMBER IS NEEDED ON THE NATURAL ROUTE ONLY: Ra = Gr Pr carries it.",
        "all_of": ["fluid_prandtl_number", "convection_length", "fluid_kinematic_viscosity"],
        "one_of": [["fluid_expansion_coefficient"]],
        "reading": "the mirror of the forced entry: on this route Prandtl IS required, and the record now says so.",
    },
    ("thermal.lumped", "convection_property_range_utilization"): {
        "clause": "UNKNOWN unless a Prandtl number and one resolved route are supplied.",
        "all_of": ["fluid_prandtl_number"],
        "one_of": [["fluid_velocity"]],
    },
    ("thermal.lumped", "convection_conductance_agreement_ratio"): {
        "clause": "UNKNOWN unless the surface area, the fluid conductivity and a resolved route are all supplied.",
        "all_of": ["surface_area", "fluid_conductivity"],
        "one_of": [["fluid_velocity"]],
    },
    ("thermal.lumped", "geometry_route_ratio"): {
        "clause": "UNKNOWN only when NEITHER route is available ...",
        "one_of": [["characteristic_length", "body_volume"]],
        "reading": "the post-CORE-1 record: one route is enough, neither is UNKNOWN. Dropping one must still answer; dropping both must refuse.",
    },
    ("thermal.lumped", "melting_temperature_utilization"): {
        "clause": "UNKNOWN unless melting_temperature is supplied.",
        "all_of": ["melting_temperature"],
    },
    ("thermal.lumped", "internal_fourier_number"): {"clause": None},
    ("thermal.lumped", "heat_capacity"): {"clause": None},
    ("thermal.lumped", "ambient_conductance"): {"clause": None},
    # ---- electrical.material --------------------------------------------
    ("electrical.material", "linearization_excursion_ratio"): {
        "clause": "UNKNOWN unless the material declares linearization_band.",
        "all_of": ["linearization_band"],
    },
    ("electrical.material", "operating_temperature_utilization"): {
        "clause": "UNKNOWN unless the material declares maximum_operating_temperature.",
        "all_of": ["maximum_operating_temperature"],
    },
    ("electrical.material", "reduced_debye_temperature"): {
        "clause": "UNKNOWN unless the material declares debye_temperature.",
        "all_of": ["debye_temperature"],
    },
    ("electrical.material", "reference_temperature_utilization"): {
        "clause": "UNKNOWN unless the material declares maximum_operating_temperature.",
        "all_of": ["maximum_operating_temperature"],
        "cross_limit": True,
        "reading": "a CrossLimitCondition: its inputs are read from the declared namespace, not assembled.",
    },
    ("electrical.material", "reference_reduced_debye_temperature"): {
        "clause": "UNKNOWN unless the material declares debye_temperature.",
        "all_of": ["debye_temperature"],
        "cross_limit": True,
    },
    ("electrical.material", "ceiling_reduced_debye_temperature"): {
        "clause": "UNKNOWN unless the material declares both maximum_operating_temperature and debye_temperature.",
        "all_of": ["maximum_operating_temperature", "debye_temperature"],
        "cross_limit": True,
    },
    ("electrical.material", "linear_resistance_ratio"): {
        "clause": "UNKNOWN unless a temperature is supplied.",
        "all_of": ["temperature"],
    },
    ("electrical.material", "temperature"): {"clause": None},
    ("electrical.material", "reference_resistance"): {"clause": None},
    # ---- battery.cell ----------------------------------------------------
    ("battery.cell", "cutoff_consistency_margin"): {
        "clause": "UNKNOWN unless both cutoffs are declared.",
        "all_of": ["cutoff_voltage", "cutoff_state_of_charge"],
    },
    ("battery.cell", "continuous_c_rate_utilization"): {
        "clause": "UNKNOWN unless the rating is declared.",
        "all_of": ["continuous_discharge_c_rate"],
    },
    ("battery.cell", "soc_window_margin"): {
        "clause": "UNKNOWN unless both edges are declared.",
        "all_of": ["usable_soc_minimum", "usable_soc_maximum"],
    },
    ("battery.cell", "soc_step_resolution_ratio"): {
        "clause": "UNKNOWN unless a resolution is declared.",
        "all_of": ["soc_step_resolution"],
    },
    ("battery.cell", "capacity_temperature_drift_ratio"): {
        "clause": "UNKNOWN unless both are declared.",
        "all_of": ["capacity_reference_temperature", "capacity_temperature_span"],
    },
    ("battery.cell", "peukert_extrapolation_ratio"): {
        "clause": "UNKNOWN unless the reference current and the declared reach are supplied.",
        "all_of": ["peukert_reference_current", "peukert_fit_decades"],
    },
    ("battery.cell", "peukert_capacity_ratio"): {
        "clause": "UNKNOWN unless the exponent and the reference current are declared.",
        "all_of": ["peukert_exponent", "peukert_reference_current"],
    },
    ("battery.cell", "peukert_temperature_drift_ratio"): {
        "clause": "UNKNOWN unless both are declared.",
        "all_of": ["peukert_reference_temperature", "peukert_temperature_span"],
    },
    ("battery.cell", "pulse_c_rate_utilization"): {
        "clause": "UNKNOWN unless the duty declares a pulse current and the cell declares a pulse rating.",
        "all_of": ["pulse_current", "pulse_discharge_c_rate"],
    },
    ("battery.cell", "pulse_duration_utilization"): {
        "clause": "UNKNOWN unless both durations are declared.",
        "all_of": ["pulse_duration", "rated_pulse_duration"],
    },
    ("battery.cell", "discharge_temperature_position"): {
        "clause": "UNKNOWN unless both edges are declared.",
        "all_of": ["minimum_discharge_temperature", "maximum_discharge_temperature"],
    },
    ("battery.cell", "internal_resistance_drift_ratio"): {
        "clause": "UNKNOWN unless both are declared.",
        "all_of": ["resistance_reference_temperature", "resistance_temperature_span"],
    },
    ("battery.cell", "self_heating_rise_ratio"): {
        "clause": "UNKNOWN unless both the conductance and the budget are declared.",
        "all_of": ["cell_thermal_conductance", "self_heating_rise_bound"],
    },
    ("battery.cell", "polarization_unmodelled_fraction"): {
        "clause": "UNKNOWN unless a polarization time constant is declared.",
        "all_of": ["polarization_time_constant"],
    },
    ("battery.cell", "terminal_voltage_ratio"): {
        "clause": "UNKNOWN unless the operating point is supplied.",
        "all_of": ["state_of_charge", "discharge_current"],
        "reading": "'the operating point' is the state and control the assessment is given.",
    },
    ("battery.cell", "nominal_capacity"): {"clause": None},
    ("battery.cell", "coulombic_efficiency"): {"clause": None},
    ("battery.cell", "internal_resistance"): {"clause": None},
    # ---- kinetics.cstr ---------------------------------------------------
    ("kinetics.cstr", "adiabatic_ceiling_temperature"): {
        "clause": "UNKNOWN unless the enthalpy, density, heat capacity, both concentrations and all three temperatures are declared.",
        "all_of": [
            "heat_of_reaction", "density", "heat_capacity",
            "feed_concentration", "concentration",
            "feed_temperature", "temperature", "coolant_temperature",
        ],
        "reading": "'both concentrations' is the feed and the initial charge; 'all three temperatures' the feed, the initial and the coolant. The initial pair carry the reserved names `concentration` and `temperature` in the assembled namespace.",
    },
    ("kinetics.cstr", "temperature"): {"clause": None},
    ("kinetics.cstr", "concentration"): {"clause": None},
    ("kinetics.cstr", "k0"): {"clause": None},
    ("kinetics.cstr", "k_const"): {"clause": None},
    ("kinetics.cstr", "activation_energy"): {"clause": None},
    ("kinetics.cstr", "residence_time"): {"clause": None},
    # ---- electrical.dc ---------------------------------------------------
    ("electrical.dc", "dissipated_power_utilization"): {
        "clause": "UNKNOWN unless a rated_power is declared, and also UNKNOWN when a derating line is declared without the ambient it must be evaluated at.",
        "all_of": ["rated_power", "ambient_temperature"],
        "context": "resistor",
        "reading": "the ambient is required BECAUSE the nominal declares the two derating-line temperatures; the clause's second half is exactly this case.",
    },
    ("electrical.dc", "working_voltage_utilization"): {
        "clause": "UNKNOWN unless a maximum_working_voltage is declared.",
        "all_of": ["maximum_working_voltage"],
        "context": "resistor",
    },
    ("electrical.dc", "source_current_utilization"): {
        "clause": "UNKNOWN unless a maximum_current is declared.",
        "all_of": ["maximum_current"],
        "context": "voltage_source",
    },
    ("electrical.dc", "compliance_voltage_utilization"): {
        "clause": "UNKNOWN unless a compliance_voltage is declared.",
        "all_of": ["compliance_voltage"],
        "context": "current_source",
    },
    ("electrical.dc", "source_regulation_utilization"): {
        "clause": "UNKNOWN unless both an output_resistance and a regulation_band are declared, and unless the solve supplied a current.",
        "all_of": ["output_resistance", "regulation_band", "source_current"],
        "context": "regulated_source",
    },
    ("electrical.dc", "element_hot_spot_utilization"): {
        "clause": "UNKNOWN unless both the thermal resistance and the permissible temperature are declared and the run supplied a body temperature and a dissipation.",
        "all_of": [
            "element_to_body_thermal_resistance", "permissible_element_temperature",
            "body_temperature", "dissipated_power",
        ],
        "context": "self_heated",
    },
    ("electrical.dc", "lumped_electrical_length"): {"clause": None, "context": "kcl"},
    ("electrical.dc", "resistance"): {"clause": None, "context": "declared"},
    # ---- thermal.conduction1d -------------------------------------------
    ("thermal.conduction1d", "alpha"): {"clause": None},
}
