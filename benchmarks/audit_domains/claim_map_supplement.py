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
}
