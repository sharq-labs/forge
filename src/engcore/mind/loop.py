"""Bounded investigation loop.

Select, dispatch, ingest, and repeat until STOP or the step bound. The loop
does not rank actions and does not fabricate a result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .handlers import dispatch
from .transition import (
    ActionResult,
    ActionType,
    MindRefusal,
    MindState,
    Selection,
    apply_result,
    select_next_action,
)


@dataclass(frozen=True)
class InvestigationRecord:
    steps: tuple[Selection, ...]
    results: tuple[ActionResult, ...]
    final_state: MindState

    @property
    def action_ids(self) -> tuple[str, ...]:
        return tuple(step.action_id for step in self.steps)


def run_investigation(
    state: MindState,
    catalog: Mapping[str, Any],
    *,
    max_steps: int = 6,
) -> InvestigationRecord:
    if type(max_steps) is not int or max_steps < 1:
        raise MindRefusal("investigation step bound must be a positive integer")
    current = state
    steps: list[Selection] = []
    results: list[ActionResult] = []
    for _ in range(max_steps):
        selection = select_next_action(current)
        steps.append(selection)
        if selection.action_type is ActionType.STOP:
            return InvestigationRecord(tuple(steps), tuple(results), current)
        action = current.action(selection.action_id)
        result = dispatch(current, action, catalog)
        results.append(result)
        current = apply_result(current, result)
    raise MindRefusal("investigation exceeded the step bound")
