"""Claim-map entries for the conditions the domains audit-fix stream added.

Registered in ``benchmarks/contract_guard/guard/prerequisites.py`` beside the
capability-boundary round's supplement, for the same reason that one exists:
the Contract Integrity claim map is an earlier round's result artifact and is
not edited, and a shipped condition in no claim map fails the contract guard.
Each clause is quoted from the record that states it.
"""

from __future__ import annotations

SUPPLEMENT: dict[tuple[str, str], dict] = {
    # ---- kinetics.cstr: the single-liquid-phase claim (audit CAP-01) -------
    ("kinetics.cstr", "declared_temperature_to_boiling_ratio"): {
        "clause": "UNKNOWN unless the fluid declares boiling_temperature.",
        "all_of": ["boiling_temperature"],
        "reading": (
            "The three declared temperatures are also read, but they are "
            "required inputs of every reactor; the promise the record makes "
            "is about the optional fluid property."
        ),
    },
    ("kinetics.cstr", "adiabatic_ceiling_to_boiling_ratio"): {
        "clause": "UNKNOWN unless the fluid declares boiling_temperature.",
        "all_of": ["boiling_temperature"],
    },
    ("kinetics.cstr", "adiabatic_floor_to_freezing_ratio"): {
        "clause": "UNKNOWN unless the fluid declares freezing_temperature.",
        "all_of": ["freezing_temperature"],
    },
    # ---- battery.cell: the declared pulse, screened (audit CAP-02) ---------
    ("battery.cell", "pulse_polarization_unmodelled_fraction"): {
        "clause": "UNKNOWN unless pulse_duration and polarization_time_constant are declared.",
        "all_of": ["pulse_duration", "polarization_time_constant"],
        "reading": "A conservative screen: past its bound it is also UNKNOWN, with the screen reason.",
    },
    ("battery.cell", "pulse_terminal_voltage_ratio"): {
        "clause": "UNKNOWN unless a pulse current and the operating point are declared.",
        "all_of": ["pulse_current", "state_of_charge", "discharge_current"],
        "reading": "'the operating point' is the state and control, as for terminal_voltage_ratio.",
    },
    ("battery.cell", "pulse_cutoff_state_of_charge_shift"): {
        "clause": "UNKNOWN unless a voltage cutoff and a discharge current are declared.",
        "all_of": ["cutoff_voltage", "discharge_current"],
        "reading": (
            "Zero and satisfied when no pulse is declared: the pulse is not a "
            "prerequisite, because a constant load cannot shift its own cutoff."
        ),
    },
    # ---- electrical.material: the Debye floor is elemental-metal physics ---
    # (audit CAP-05). The Contract Integrity map's entries read "UNKNOWN
    # unless the material declares debye_temperature", which still holds; the
    # records now add the class, and these entries say so.
    ("electrical.material", "reduced_debye_temperature"): {
        "clause": "UNKNOWN unless the material declares debye_temperature and conductor_class elemental_metal.",
        "all_of": ["debye_temperature", "conductor_class"],
    },
    ("electrical.material", "reference_reduced_debye_temperature"): {
        "clause": "UNKNOWN unless the material declares debye_temperature and conductor_class elemental_metal.",
        "all_of": ["debye_temperature", "conductor_class"],
        "cross_limit": True,
    },
    ("electrical.material", "ceiling_reduced_debye_temperature"): {
        "clause": "UNKNOWN unless the material declares maximum_operating_temperature, debye_temperature and conductor_class elemental_metal.",
        "all_of": ["maximum_operating_temperature", "debye_temperature", "conductor_class"],
        "cross_limit": True,
    },
    # ---- electrical.dc: one resistance over the interval (audit CAP-03) ----
    ("electrical.dc", "resistance_variation_utilization"): {
        "clause": "UNKNOWN unless the budget is declared and the run supplied the coefficient and both body temperatures.",
        "all_of": ["resistance_variation_budget"],
        "context": "dc.self_heated",
        "reading": (
            "The coefficient and the two body temperatures are supplied by "
            "the coupled run, never by the caller; the caller's prerequisite "
            "is the budget."
        ),
    },
}
