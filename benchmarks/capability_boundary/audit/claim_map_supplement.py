"""Claim-map entries for the conditions this round added.

The Contract Integrity round's claim map is a result artifact of that round
and is not edited here. Its Contract Guard successor asserts that every
shipped condition appears in *a* claim map, and that guard fired the moment
this round added a condition -- which is exactly what it is for: a condition
nobody has mapped is a condition nobody checks.

So the mapping is supplied, in this round's own directory, in the same shape.
Two of the three conditions added here reuse a per-system key that already
existed (``electrical.material::linear_resistance_ratio`` and
``kinetics.cstr::adiabatic_ceiling_temperature`` were already mapped for the
sibling records that stated them first, and those readings apply unchanged).
Only the battery one is new.
"""

from __future__ import annotations

SUPPLEMENT: dict[tuple[str, str], dict] = {
    ("battery.cell", "cutoff_reachability_margin"): {
        "clause": (
            "UNKNOWN unless the starting state of charge and at least one "
            "cutoff are declared — with no cutoff there is no runtime to bound."
        ),
        # The two cutoffs are ALTERNATIVE routes to a binding cutoff, not two
        # requirements: z_stop is the higher of whichever are declared, so
        # either one alone still determines it. Dropping both leaves no cutoff
        # and therefore no runtime, which is UNKNOWN rather than unbounded.
        "one_of": [["cutoff_voltage", "cutoff_state_of_charge"]],
        "reading": (
            "The sibling cutoff_consistency_margin needs BOTH cutoffs, because "
            "it compares them with each other. This one needs only one, "
            "because it compares the binding cutoff with the start. The two "
            "shapes differ for a reason and the difference is the whole point "
            "of the condition."
        ),
    },
}
