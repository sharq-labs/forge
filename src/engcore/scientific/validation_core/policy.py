from __future__ import annotations

from dataclasses import dataclass

from ..errors import InvalidScientificProblem
from .stage import ValidationStage


@dataclass(frozen=True)
class ValidationPolicy:
    required_stages: tuple[ValidationStage, ...] = tuple(ValidationStage)
    refuse_warnings: bool = False

    def __post_init__(self) -> None:
        stages = tuple(ValidationStage(s) for s in self.required_stages)
        if len(set(stages)) != len(stages):
            raise InvalidScientificProblem("validation policy contains duplicate required stages")
        object.__setattr__(self, "required_stages", stages)
        if not isinstance(self.refuse_warnings, bool):
            raise InvalidScientificProblem("refuse_warnings must be bool")
