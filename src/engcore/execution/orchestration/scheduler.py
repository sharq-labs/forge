from __future__ import annotations
from .plan import SimulationPlan

def schedule_attempts(plan:SimulationPlan)->tuple[str,...]:
    """Deterministic solver ordering; selection policy is explicit in the plan."""
    return tuple(plan.solver_candidates[:plan.budget.max_attempts])
