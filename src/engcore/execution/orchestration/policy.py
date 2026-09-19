from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class OrchestrationPolicy:
    require_convergence:bool=True
    allow_solver_fallback:bool=True
    require_checkpoint_for_resume:bool=True
