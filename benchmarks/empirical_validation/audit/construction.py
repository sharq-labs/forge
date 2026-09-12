"""EV-4: did the Core receive the problem the fixture describes?

For every quantity in every fixture, two numbers exist: what adapter B computed
in SI from the raw values, and what the engcore declaration reports when asked
for the same quantity in the same SI unit. This module puts them side by side.

The question is narrower than "does the answer agree" and is asked first on
purpose. A solver can be perfect and still be handed a reactor a thousand times
too large, and a round that only compared answers would see the two branches
disagree without being able to say whether the fault was in the physics or in
the statement of the problem.

CLASSIFICATION.

  EXACT                 the two are bit-identical
  TRANSFORMED_CORRECTLY they agree to within unit-conversion round-off
  ALTERED               they differ by more than that
  LOST                  branch B has the quantity and the declaration does not
  AMBIGUOUS             the declaration exposes it in a form that does not
                        settle what it means

The round-off band is 1e-12 relative. It is not a physics tolerance: it is the
size of the error a chain of decimal unit factors can leave in a double, and a
real construction fault -- a factor of 10, 60, 1000, or 273.15 -- is many orders
of magnitude outside it.
"""

from __future__ import annotations

ROUND_OFF_BAND = 1e-12


def classify(core_value, reference_value) -> dict:
    if core_value is None:
        return {"classification": "LOST", "relative_difference": None}
    if isinstance(core_value, bool) or isinstance(reference_value, bool):
        return {
            "classification": "EXACT" if core_value == reference_value else "ALTERED",
            "relative_difference": None,
        }
    if isinstance(reference_value, int) and isinstance(core_value, int):
        return {
            "classification": "EXACT" if core_value == reference_value else "ALTERED",
            "relative_difference": None,
        }
    if not isinstance(core_value, (int, float)) or not isinstance(
        reference_value, (int, float)
    ):
        return {
            "classification": "EXACT" if core_value == reference_value else "AMBIGUOUS",
            "relative_difference": None,
        }
    if core_value == reference_value:
        return {"classification": "EXACT", "relative_difference": 0.0}
    scale = abs(reference_value)
    if scale == 0.0:
        difference = abs(core_value)
        return {
            "classification": "ALTERED" if difference > 0.0 else "EXACT",
            "relative_difference": difference,
        }
    difference = abs(core_value - reference_value) / scale
    return {
        "classification": (
            "TRANSFORMED_CORRECTLY" if difference <= ROUND_OFF_BAND else "ALTERED"
        ),
        "relative_difference": difference,
    }


def compare(case_id: str, received: dict, reference: dict) -> list[dict]:
    """One row per quantity branch B produced."""
    rows = []
    for field, reference_value in sorted(reference.items()):
        core_value = received.get(field)
        rows.append(
            {
                "case": case_id,
                "field": field,
                "reference_branch_value": reference_value,
                "core_received_value": core_value,
                **classify(core_value, reference_value),
            }
        )
    return rows
