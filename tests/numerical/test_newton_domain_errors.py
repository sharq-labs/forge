"""A residual evaluated outside its domain: the same event whether it returns NaN or raises.

``F(x) = log(x) - 1`` has its root at ``e``. From ``x0 = 10`` the full Newton
step lands at a negative ``x``. ``numpy.log`` returns NaN there and
``newton_armijo`` backtracks; ``math.log`` raises ``ValueError`` for the same
input, and that used to escape the provider uncaught (only ``ArithmeticError``
was classified), so the same mathematics crashed or converged depending on
which library the caller's residual used.
"""

from __future__ import annotations

import hashlib
import math

import numpy as np
import pytest

from engcore.numerical.core import (
    NumericalMethod, NumericalProblem, OperatorIdentity, ProblemKind, UnitBoundary, VariableSpec,
)
from engcore.numerical.health import NumericalFailureClass
from engcore.numerical.nonlinear import DampedNewtonProvider
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.solvers.protocol import ConvergenceState, SolverSettings
from engcore.scientific.units.quantity import Quantity


def _problem(residual, jacobian, x0=10.0):
    return NumericalProblem(
        problem_id="log_root",
        kind=ProblemKind.NONLINEAR_ROOT,
        operator=OperatorIdentity("log_root", "1", hashlib.sha256(b"log_root").hexdigest(), "declared"),
        unknowns=UnitBoundary((VariableSpec("x", "m", 1.0, 1),)),
        operands={"residual": residual, "jacobian": jacobian},
        initial={"x": Quantity(x0, "m")},
    )


def _method(name):
    options = {"max_iterations": 50}
    if name == "newton_armijo":
        options.update({"armijo_c1": 1e-4, "backtrack_factor": 0.5, "max_backtracks": 40})
    return NumericalMethod(name, SolverSettings(tolerances={"residual_atol": 1e-10, "step_rtol": 1e-14}, options=options))


def _math_log(x):
    return np.array([math.log(x[0]) - 1.0])


def _numpy_log(x):
    return np.log(x) - 1.0


def _jacobian(x):
    return np.array([[1.0 / x[0]]])


@pytest.mark.parametrize("residual", [_numpy_log, _math_log], ids=["numpy_nan", "math_raises"])
def test_newton_armijo_backtracks_from_a_trial_point_outside_the_domain(residual):
    record = DampedNewtonProvider().execute(_problem(residual, _jacobian), _method("newton_armijo"))
    assert record.convergence is ConvergenceState.CONVERGED
    assert record.outputs["x"].magnitude_in("m") == pytest.approx(math.e, rel=1e-9)
    assert min(record.diagnostics.step_lengths) < 1.0  # the first full step was backtracked


def test_the_backtracked_domain_error_is_noted_in_the_record():
    record = DampedNewtonProvider().execute(_problem(_math_log, _jacobian), _method("newton_armijo"))
    notes = [w for w in record.diagnostics.warnings if "could not be evaluated" in w]
    assert len(notes) == 1 and "ValueError" in notes[0]


def test_plain_newton_classifies_the_domain_error_instead_of_raising_it():
    record = DampedNewtonProvider().execute(_problem(_math_log, _jacobian), _method("newton"))
    assert record.convergence is ConvergenceState.DIVERGED
    assert record.diagnostics.failure_class == NumericalFailureClass.NON_FINITE.value
    assert "ValueError" in record.reason


def test_a_refusal_raised_by_the_residual_still_propagates():
    def refusing(_x):
        raise InvalidScientificProblem("the residual refuses this state")

    with pytest.raises(InvalidScientificProblem, match="refuses this state"):
        DampedNewtonProvider().execute(_problem(refusing, _jacobian), _method("newton_armijo"))
