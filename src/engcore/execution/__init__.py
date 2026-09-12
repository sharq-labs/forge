"""Executing many independent scientific evaluations.

Not part of the Scientific Core: this layer runs the core's operations, it
declares none of its own contracts.
"""

from .sweep import (
    CaseStatus,
    FailurePolicy,
    SharedContext,
    SweepCase,
    SweepDefinition,
    SweepError,
    SweepOutcome,
    SweepSummary,
    cases_from,
    rerun_failed,
    run_sweep,
)

__all__ = [
    "CaseStatus",
    "FailurePolicy",
    "SharedContext",
    "SweepCase",
    "SweepDefinition",
    "SweepError",
    "SweepOutcome",
    "SweepSummary",
    "cases_from",
    "rerun_failed",
    "run_sweep",
]
