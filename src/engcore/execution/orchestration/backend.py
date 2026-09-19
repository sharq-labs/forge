from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .attempt import AttemptState
from .checkpoint import CheckpointReference


@dataclass(frozen=True)
class BackendOutcome:
    state:AttemptState
    failure_code:str=""
    checkpoint:CheckpointReference|None=None

    def __post_init__(self)->None:
        object.__setattr__(self,"state",AttemptState(self.state))
        if self.state in {AttemptState.PLANNED,AttemptState.RUNNING}:
            raise ValueError("backend outcome must be terminal")
        if self.state in {AttemptState.FAILED,AttemptState.DIVERGED} and not str(self.failure_code).strip():
            raise ValueError("failed/diverged backend outcome must state failure_code")


class SimulationBackend(Protocol):
    solver_id:str

    def run(
        self,
        *,
        attempt_id:str,
        refinement_level:int,
        deterministic_seed:int|None,
        checkpoint:CheckpointReference|None,
    )->BackendOutcome: ...
