"""What a participant may assume about its own time steps inside a coupling window (Phase 3 BR15).

The runtime synchronizes participants only at window boundaries.  Inside a
window each participant advances on its own clock (it subcycles), and this
module states the contract that holds there, derived from the graph and the
plan -- it adds no mechanism:

* every coupled input is HELD CONSTANT over the window (zero-order hold): the
  runtime delivers one value per input per iteration, never a time-interpolated
  history, so a participant whose method needs interpolated inputs inside the
  window is outside what the runtime provides;
* outputs are exchanged at the window END only;
* a participant is told ``maximum_step = min(window, maximum_time_step,
  preferred_time_step)``; the number of internal steps it takes is its own,
  and at least ``ceil(window / maximum_time_step)`` when it declares a maximum;
* its reported end instant must equal the synchronization instant; a
  difference beyond the reporting tolerance is refused and one within it is
  recorded (``participant_clock_disagreement`` in ``_time_grid``);
* a steady participant has no clock: it is evaluated once per iteration at the
  window end.

:func:`subcycling_contract` makes these statements explicit for one plan, and
refuses a transient participant whose declared maximum step leaves it more
substeps per window than ``max_substeps`` (a declared budget, never a default).
The zero-order hold contributes a splitting error the runtime does not
measure unless window error control (``WindowErrorControl``) is declared.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from ...scientific.errors import InvalidScientificProblem
from ...scientific.multiphysics import CouplingPlan, PhysicsGraph
from ...scenarios.timeline import exact_seconds

INPUT_HOLD = "zero_order_hold_over_window"
OUTPUT_EXCHANGE = "window_end_only"


@dataclass(frozen=True)
class SubcyclingEntry:
    participant_id: str
    transient: bool
    maximum_time_step_s: float | None
    preferred_time_step_s: float | None
    minimum_substeps_per_nominal_window: int | None

    def to_dict(self) -> dict[str, Any]:
        return {"participant_id": self.participant_id, "transient": self.transient,
                "maximum_time_step_s": self.maximum_time_step_s, "preferred_time_step_s": self.preferred_time_step_s,
                "minimum_substeps_per_nominal_window": self.minimum_substeps_per_nominal_window,
                "input_hold": INPUT_HOLD if self.transient else "evaluated_at_window_end",
                "output_exchange": OUTPUT_EXCHANGE}


@dataclass(frozen=True)
class SubcyclingContract:
    nominal_window_s: float
    entries: tuple[SubcyclingEntry, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"classification": "execution_contract_not_evidence", "nominal_window_s": self.nominal_window_s,
                "participants": [entry.to_dict() for entry in self.entries],
                "notice": ("inputs are held constant over each window; the splitting error this introduces is not "
                           "measured unless window error control is declared")}


def subcycling_contract(graph: PhysicsGraph, plan: CouplingPlan, *, max_substeps: int) -> SubcyclingContract:
    """The per-participant subcycling statements for ``plan`` on ``graph`` (see the module docstring)."""
    if isinstance(max_substeps, bool) or not isinstance(max_substeps, int) or not 1 <= max_substeps <= 10_000_000:
        raise InvalidScientificProblem("max_substeps must be a declared int in [1, 10000000]")
    window = exact_seconds(plan.time.coupling_window)
    entries = []
    for spec in sorted(graph.participants, key=lambda item: item.participant_id):
        maximum = None if spec.maximum_time_step is None else exact_seconds(spec.maximum_time_step)
        preferred = None if spec.preferred_time_step is None else exact_seconds(spec.preferred_time_step)
        substeps = None
        if spec.transient and maximum is not None:
            substeps = math.ceil(window / maximum)
            if substeps > max_substeps:
                raise InvalidScientificProblem(
                    f"participant {spec.participant_id!r} needs at least {substeps} internal steps per coupling window "
                    f"(maximum_time_step {float(maximum):g} s); the declared budget is {max_substeps}"
                )
        entries.append(SubcyclingEntry(spec.participant_id, bool(spec.transient),
                                       None if maximum is None else float(maximum),
                                       None if preferred is None else float(preferred), substeps))
    return SubcyclingContract(float(window), tuple(entries))


__all__ = ["INPUT_HOLD", "OUTPUT_EXCHANGE", "SubcyclingContract", "SubcyclingEntry", "subcycling_contract"]
