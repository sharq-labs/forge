"""Robust nonlinear solving on top of existing providers: a declared method chain and parameter continuation.

Both strategies only COMPOSE :meth:`NumericalProvider.execute`; they add no
algorithm and no acceptance rule of their own.  A result exists only when one
execution of the target problem converged by its own provider's criteria.

Method chain
    The declared methods are tried in order on the SAME problem: every attempt
    starts from the problem's declared initial values, never from a failed
    attempt's iterate (a non-converged execution exposes none).  Every attempt
    is recorded.  A refusal (unsupported method, unavailable provider) is a
    configuration error and propagates; only numerical non-convergence moves to
    the next method.

Parameter continuation
    The caller declares a family ``lam -> NumericalProblem`` from a problem it
    expects to be easy (``lam = 0``) to the target (``lam = 1``).  Each step
    warm-starts ONLY from the previous step's CONVERGED outputs; a failed step
    is retried with half the increment and is never used.  The run ends at
    ``lam = 1`` converged, or reports why not (minimum step, step budget, or
    an unsolved starting problem).  The accepted execution solves the target
    problem; it differs from the declared target only in its initial values,
    which is checked.

Neither strategy is evidence: an accepted execution carries the same
``numerical_execution_not_scientific_evidence`` classification as any other.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Any, Callable, Mapping, Sequence

from .core import (
    NumericalExecutionRecord,
    NumericalMethod,
    NumericalProblem,
    NumericalProvider,
    NumericalRefusal,
    ProblemKind,
)


@dataclass(frozen=True)
class NonlinearAttempt:
    """One execution the strategy made: which method, at which continuation parameter, with what result."""

    method: str
    lam: float | None
    record: NumericalExecutionRecord

    def to_dict(self) -> dict[str, Any]:
        return {"method": self.method, "lam": self.lam, "convergence": self.record.convergence.value,
                "execution_digest": self.record.digest, "reason": self.record.reason}


@dataclass(frozen=True)
class RobustSolveRecord:
    strategy: str
    target_problem_digest: str
    attempts: tuple[NonlinearAttempt, ...]
    accepted: NumericalExecutionRecord | None
    reason: str

    @property
    def succeeded(self) -> bool:
        return self.accepted is not None and self.accepted.succeeded

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification": "numerical_execution_not_scientific_evidence",
            "strategy": self.strategy,
            "target_problem_digest": self.target_problem_digest,
            "attempts": [a.to_dict() for a in self.attempts],
            "accepted_execution_digest": None if self.accepted is None else self.accepted.digest,
            "succeeded": self.succeeded,
            "reason": self.reason,
        }


def solve_with_method_chain(
    provider: NumericalProvider,
    problem: NumericalProblem,
    methods: Sequence[NumericalMethod],
) -> RobustSolveRecord:
    """Try the declared methods in order on the same problem; accept the first that converges."""
    methods = tuple(methods)
    if not 1 <= len(methods) <= 8 or any(not isinstance(m, NumericalMethod) for m in methods):
        raise NumericalRefusal("a method chain declares 1..8 NumericalMethod entries")
    keys = [repr(sorted(m.to_dict().items())) for m in methods]
    if len(set(keys)) != len(keys):
        raise NumericalRefusal("a method chain must not repeat an identical method")
    attempts: list[NonlinearAttempt] = []
    for method in methods:
        record = provider.execute(problem, method)  # refusals propagate: they are not numerical failures
        attempts.append(NonlinearAttempt(method.method, None, record))
        if record.succeeded:
            return RobustSolveRecord("method_chain", problem.digest, tuple(attempts), record,
                                     f"accepted method {method.method!r} after {len(attempts)} attempt(s)")
    reasons = "; ".join(f"{a.method}: {a.record.convergence.value} ({a.record.reason})" for a in attempts)
    return RobustSolveRecord("method_chain", problem.digest, tuple(attempts), None,
                             f"every declared method failed: {reasons}")


def _same_except_initial(a: NumericalProblem, b: NumericalProblem) -> bool:
    left, right = dict(a.identity()), dict(b.identity())
    left.pop("initial", None)
    right.pop("initial", None)
    return left == right


def solve_by_continuation(
    provider: NumericalProvider,
    family: Callable[[float], NumericalProblem],
    method: NumericalMethod,
    *,
    initial_step: float,
    minimum_step: float,
    max_steps: int,
) -> RobustSolveRecord:
    """Natural-parameter continuation from ``family(0)`` to ``family(1)`` (see the module docstring).

    Step control: a failed step halves the increment (never below
    ``minimum_step``); a converged step keeps it.  No step size, budget or
    starting problem is defaulted.  A turning point (fold) in the solution
    branch defeats natural-parameter continuation; it ends as a failure.
    """
    for label, value in (("initial_step", initial_step), ("minimum_step", minimum_step)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0.0 < value <= 1.0:
            raise NumericalRefusal(f"{label} must lie in (0, 1]")
    if minimum_step > initial_step:
        raise NumericalRefusal("minimum_step exceeds initial_step")
    if isinstance(max_steps, bool) or not isinstance(max_steps, int) or not 1 <= max_steps <= 10000:
        raise NumericalRefusal("max_steps must be an int in [1, 10000]")

    target = family(1.0)
    start = family(0.0)
    for name, item in (("family(1)", target), ("family(0)", start)):
        if not isinstance(item, NumericalProblem) or item.kind is not ProblemKind.NONLINEAR_ROOT:
            raise NumericalRefusal(f"{name} must be a NONLINEAR_ROOT NumericalProblem")
    if start.unknowns.to_dict() != target.unknowns.to_dict():
        raise NumericalRefusal("the continuation family changes its unknowns; a warm start would be meaningless")

    attempts: list[NonlinearAttempt] = []

    def done(accepted: NumericalExecutionRecord | None, reason: str) -> RobustSolveRecord:
        return RobustSolveRecord("continuation", target.digest, tuple(attempts), accepted, reason)

    first = provider.execute(start, method)
    attempts.append(NonlinearAttempt(method.method, 0.0, first))
    if not first.succeeded:
        return done(None, f"the declared starting problem (lam = 0) did not converge: {first.reason}")
    lam, previous, step = 0.0, first.outputs, float(initial_step)
    accepted: NumericalExecutionRecord | None = None
    while accepted is None:
        if len(attempts) > max_steps:
            return done(None, f"step budget {max_steps} exhausted at lam = {lam:.6g}")
        goal = 1.0 if lam + step >= 1.0 - 1e-12 else lam + step
        problem = family(goal)
        if not isinstance(problem, NumericalProblem) or problem.unknowns.to_dict() != target.unknowns.to_dict():
            raise NumericalRefusal(f"family({goal!r}) is not a problem over the same unknowns")
        warm = replace(problem, initial=dict(previous))  # re-validated: a converged iterate of the previous step only
        record = provider.execute(warm, method)
        attempts.append(NonlinearAttempt(method.method, goal, record))
        if record.succeeded:
            lam, previous = goal, record.outputs
            if goal == 1.0:
                accepted = record
                if not _same_except_initial(warm, target):
                    return done(None, "family(1) changed between calls; the accepted problem is not the declared target")
        else:
            step /= 2.0
            if step < minimum_step:
                return done(None, f"continuation step fell below the declared minimum {minimum_step:g} at lam = {lam:.6g}: "
                                  f"{record.reason}")
    return done(accepted, f"reached lam = 1 in {len(attempts)} execution(s)")


__all__ = [
    "NonlinearAttempt",
    "RobustSolveRecord",
    "solve_by_continuation",
    "solve_with_method_chain",
]
