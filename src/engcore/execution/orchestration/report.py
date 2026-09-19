from __future__ import annotations
from dataclasses import dataclass
from .attempt import AttemptState, SimulationAttempt

@dataclass(frozen=True)
class OrchestrationReport:
    attempts:tuple[SimulationAttempt,...]

    def __post_init__(self)->None:
        object.__setattr__(self,"attempts",tuple(self.attempts))
        ids=[a.attempt_id for a in self.attempts]
        if len(ids)!=len(set(ids)):
            raise ValueError("orchestration report contains duplicate attempt ids")

    @property
    def converged(self)->bool:
        return any(a.state is AttemptState.CONVERGED for a in self.attempts)

    @property
    def terminal_attempt(self)->SimulationAttempt|None:
        return self.attempts[-1] if self.attempts else None
