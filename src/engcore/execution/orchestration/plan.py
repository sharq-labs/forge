from __future__ import annotations
from dataclasses import dataclass
from .budget import ExecutionBudget

@dataclass(frozen=True)
class SimulationPlan:
    plan_id:str
    solver_candidates:tuple[str,...]
    budget:ExecutionBudget=ExecutionBudget()
    deterministic_seed:int|None=None

    def __post_init__(self)->None:
        pid=str(self.plan_id).strip()
        candidates=tuple(str(x).strip() for x in self.solver_candidates)
        if not pid or not candidates or any(not x for x in candidates):
            raise ValueError("simulation plan requires id and solver candidates")
        if len(candidates)!=len(set(candidates)):
            raise ValueError("simulation plan contains duplicate solver candidates")
        if self.deterministic_seed is not None and isinstance(self.deterministic_seed,bool):
            raise ValueError("deterministic_seed must be int or None")
        object.__setattr__(self,"plan_id",pid)
        object.__setattr__(self,"solver_candidates",candidates)
