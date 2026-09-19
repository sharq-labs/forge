from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

class AttemptState(str,Enum):
    PLANNED="planned"
    RUNNING="running"
    CONVERGED="converged"
    FAILED="failed"
    DIVERGED="diverged"
    CANCELLED="cancelled"

@dataclass(frozen=True)
class SimulationAttempt:
    attempt_id:str
    state:AttemptState
    refinement_level:int=0
    failure_code:str=""

    def __post_init__(self)->None:
        aid=str(self.attempt_id).strip()
        if not aid or self.refinement_level<0:
            raise ValueError("simulation attempt requires id and non-negative refinement_level")
        object.__setattr__(self,"attempt_id",aid)
        object.__setattr__(self,"state",AttemptState(self.state))
        if self.state in {AttemptState.FAILED,AttemptState.DIVERGED} and not str(self.failure_code).strip():
            raise ValueError("failed/diverged attempt must state failure_code")
