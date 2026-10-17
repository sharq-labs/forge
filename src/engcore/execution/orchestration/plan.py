from __future__ import annotations
from dataclasses import dataclass
import re
from .budget import ExecutionBudget

_SHA256=re.compile(r"^[0-9a-f]{64}$")

@dataclass(frozen=True)
class SimulationPlan:
    plan_id:str
    solver_candidates:tuple[str,...]
    budget:ExecutionBudget=ExecutionBudget()
    deterministic_seed:int|None=None
    #: Phase 2 BR10: the canonical problem every attempt solves (sha256); checkpoints are bound to it.
    #: Empty: not recorded -- a checkpoint that names its problem is then not resumed (ambiguous).
    problem_digest:str=""

    def __post_init__(self)->None:
        pid=str(self.plan_id).strip()
        candidates=tuple(str(x).strip() for x in self.solver_candidates)
        if not pid or not candidates or any(not x for x in candidates):
            raise ValueError("simulation plan requires id and solver candidates")
        if len(candidates)!=len(set(candidates)):
            raise ValueError("simulation plan contains duplicate solver candidates")
        if self.deterministic_seed is not None and isinstance(self.deterministic_seed,bool):
            raise ValueError("deterministic_seed must be int or None")
        problem=str(self.problem_digest).strip().lower()
        if problem and not _SHA256.fullmatch(problem):
            raise ValueError("simulation plan problem_digest must be a lowercase SHA-256 digest")
        object.__setattr__(self,"plan_id",pid)
        object.__setattr__(self,"solver_candidates",candidates)
        object.__setattr__(self,"problem_digest",problem)
