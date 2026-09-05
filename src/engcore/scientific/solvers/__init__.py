"""Solver contracts. No backend adapters are implemented in the core."""

from .capability import (
    CoreCapabilities,
    SolverCapability,
    SolverCapabilityId,
    capability_names,
    solver_capability_identifiers,
    solver_capability_ids,
)
from .protocol import (
    ConvergenceState,
    PreparedSolve,
    RawSolverOutput,
    ScientificSolver,
    SolverIdentity,
    SolverSettings,
    capability_gap,
)
from .registry import SolverRegistry

__all__ = [
    "CoreCapabilities",
    "SolverCapability",
    "SolverCapabilityId",
    "capability_names",
    "solver_capability_ids",
    "solver_capability_identifiers",
    "ConvergenceState",
    "PreparedSolve",
    "RawSolverOutput",
    "ScientificSolver",
    "SolverIdentity",
    "SolverSettings",
    "capability_gap",
    "SolverRegistry",
]
