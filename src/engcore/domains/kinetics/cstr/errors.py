"""Domain-local errors.

All inherit one base so a caller can catch the whole domain without catching
the core, and the core never learns these names exist.
"""

from __future__ import annotations


class KineticsCSTRError(Exception):
    """Base for every error raised by the CSTR domain."""


class ReactorConfigurationError(KineticsCSTRError):
    """A declaration is outside the model's validity envelope, or malformed.

    Raised BEFORE any integration is attempted. An input that violates the
    envelope is not a solve that failed; it is a solve that must never run.
    """


class ReactorBindingError(KineticsCSTRError):
    """A problem id was rebound to different physics."""


class IntegrationBudgetExceeded(KineticsCSTRError):
    """The preregistered right-hand-side evaluation budget was exhausted.

    Raised from inside the RHS closure so it propagates out of ``solve_ivp``.
    This is an *explicit computational limit*, not a numerical failure: the
    integration was still making progress when it was stopped. The solver
    adapter catches it and reports MAX_ITERATIONS, which is the existing
    convergence state that means exactly "stopped at a work cap".

    TWO COUNTS, BECAUSE THEY ARE DIFFERENT NUMBERS
    -----------------------------------------------
    ``completed``  evaluations the budget admitted and which were carried out.
                   This is the work the result actually rests on, and it never
                   exceeds ``budget``.
    ``attempted``  ``completed + 1`` — the call that was refused. It is
                   recorded because "the integrator asked for one more" is the
                   evidence that the run was stopped rather than finished, but
                   it is not work that happened.

    Reporting a single number here was a real defect: a budget of 500 used to
    be reported as 501 evaluations, which is a count of work that was never
    done. Callers that want "how much did this cost" want ``completed``.
    """

    def __init__(
        self,
        message: str,
        *,
        completed: int,
        attempted: int,
        budget: int,
        t: float,
    ):
        super().__init__(message)
        self.completed = int(completed)
        self.attempted = int(attempted)
        self.budget = int(budget)
        self.t = float(t)
