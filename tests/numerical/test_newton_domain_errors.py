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


# ---- 2026-10-18 remediation C1: only a domain error is classified; a programming error propagates ----------------
#
# Every exception below is produced by the real interpreter / numpy call, never by a hand-written message, so the
# classification is checked against the texts this Python actually emits (3.14 changed most ``math`` texts).


def _no_jacobian_needed(_x):
    return np.array([[1.0]])


@pytest.mark.parametrize(
    ("residual", "x0", "exception"),
    [
        (lambda x: np.array([math.sqrt(x[0]) - 1.0]), -1.0, "ValueError"),
        (lambda x: np.array([math.acos(x[0]) - 1.0]), 2.0, "ValueError"),
        (lambda x: np.array([math.acosh(x[0]) - 1.0]), 0.5, "ValueError"),
        (lambda x: np.array([math.log1p(x[0])]), -2.0, "ValueError"),
        (lambda x: np.array([math.pow(x[0], 0.5) - 1.0]), -1.0, "ValueError"),
        (lambda x: np.array([math.exp(x[0]) - 1.0]), 1000.0, "OverflowError"),
        (lambda x: np.array([1.0 / float(x[0]) - 1.0]), 0.0, "ZeroDivisionError"),
        (lambda x: np.array([float(math.floor(np.log(x[0]))) - 1.0]), -1.0, "ValueError"),  # floor of numpy's NaN
    ],
    ids=["sqrt", "acos", "acosh", "log1p", "pow", "exp_overflow", "float_division", "floor_of_nan"],
)
def test_every_math_domain_error_at_the_initial_point_is_classified_not_raised(residual, x0, exception):
    record = DampedNewtonProvider().execute(_problem(residual, _no_jacobian_needed, x0=x0), _method("newton"))
    assert record.convergence is ConvergenceState.DIVERGED
    assert record.diagnostics.failure_class == NumericalFailureClass.NON_FINITE.value
    assert exception in record.reason and record.diagnostics.iterations == 0


def _shape_mismatch(_x):
    return np.ones(3) @ np.ones(2)  # numpy raises ValueError: a caller's bug, not a domain


def _unparseable(_x):
    return np.array([float("not a number")])  # ValueError from float(): a caller's bug


def _singular_inverse(x):
    return np.linalg.inv(np.zeros((1, 1))) @ x  # LinAlgError, a ValueError subclass


@pytest.mark.parametrize("method", ["newton", "newton_armijo"])
@pytest.mark.parametrize(
    ("residual", "expected"),
    [(_shape_mismatch, ValueError), (_unparseable, ValueError), (_singular_inverse, np.linalg.LinAlgError)],
    ids=["shape_mismatch", "unparseable", "linalg_error"],
)
def test_a_programming_error_in_the_residual_propagates_instead_of_being_classified(residual, expected, method):
    with pytest.raises(expected):
        DampedNewtonProvider().execute(_problem(residual, _jacobian), _method(method))


def test_a_programming_error_in_the_jacobian_propagates():
    def broken_jacobian(_x):
        return np.linalg.inv(np.zeros((1, 1)))

    with pytest.raises(np.linalg.LinAlgError):
        DampedNewtonProvider().execute(_problem(_numpy_log, broken_jacobian), _method("newton"))


def test_a_bug_reached_only_at_a_trial_point_is_not_backtracked_into_convergence():
    """F(x) = atan(x) from x0 = 1.5: the full Newton step is x0 - atan(x0) (1 + x0^2) = 1.5 - 0.98279 * 3.25 = -1.694.

    The residual has a bug below x = -1 (an unimplemented branch raising ValueError). Before the narrowing the
    trial point was backtracked like a domain error and the solve converged to 0 with one warning; the bug must
    reach the caller instead.
    """

    def residual(x):
        if x[0] < -1.0:
            raise ValueError("residual bug: branch below -1 not implemented")
        return np.array([math.atan(x[0])])

    def jacobian(x):
        return np.array([[1.0 / (1.0 + x[0] ** 2)]])

    assert 1.5 - math.atan(1.5) * (1.0 + 1.5 ** 2) < -1.0  # the fixture's first trial point is in the bug branch
    with pytest.raises(ValueError, match="residual bug"):
        DampedNewtonProvider().execute(_problem(residual, jacobian, x0=1.5), _method("newton_armijo"))


def test_backtracked_domain_failures_are_counted_in_the_record():
    record = DampedNewtonProvider().execute(_problem(_math_log, _jacobian), _method("newton_armijo"))
    counts = [w for w in record.diagnostics.warnings if w.startswith("line-search trial points that raised")]
    assert len(counts) == 1 and int(counts[0].rsplit(":", 1)[1]) >= 1


def test_a_method_chain_does_not_retry_a_programming_error_as_non_convergence():
    from engcore.numerical.robust import solve_with_method_chain

    with pytest.raises(np.linalg.LinAlgError):
        solve_with_method_chain(DampedNewtonProvider(), _problem(_singular_inverse, _jacobian),
                                [_method("newton"), _method("newton_armijo")])


def test_acceptance_re_evaluation_propagates_a_programming_error_and_rejects_a_domain_error():
    from engcore.numerical.health import ResidualScaling
    from engcore.numerical.nonlinear import acceptance_measure

    state = {"mode": "ok"}

    def residual(x):
        if state["mode"] == "bug":
            raise ValueError("residual bug after the solve")
        if state["mode"] == "domain":
            return np.array([math.sqrt(-1.0)])
        return np.array([x[0] - 2.0])

    problem = _problem(residual, lambda _x: np.array([[1.0]]), x0=0.0)
    record = DampedNewtonProvider().execute(problem, _method("newton"))
    assert record.convergence is ConvergenceState.CONVERGED
    state["mode"] = "domain"
    assert acceptance_measure(problem, record, ResidualScaling()) == math.inf
    state["mode"] = "bug"
    with pytest.raises(ValueError, match="residual bug after the solve"):
        acceptance_measure(problem, record, ResidualScaling())


def _near_singular_linear(eps):
    return NumericalProblem(
        problem_id="near_singular_linear",
        kind=ProblemKind.NONLINEAR_ROOT,
        operator=OperatorIdentity("near_singular_linear", "1", hashlib.sha256(b"nsl").hexdigest(), "declared"),
        unknowns=UnitBoundary((VariableSpec("a", "m", 1.0, 1), VariableSpec("b", "m", 1.0, 1))),
        operands={"residual": lambda x: np.array([x[0] + x[1] - 2.0, x[0] + (1.0 + eps) * x[1] - 2.0]),
                  "jacobian": lambda _x: np.array([[1.0, 1.0], [1.0, 1.0 + eps]])},
        initial={"a": Quantity(0.0, "m"), "b": Quantity(0.0, "m")},
    )


def _limited_newton(limit):
    return NumericalMethod("newton", SolverSettings(tolerances={"residual_atol": 1e-10, "step_rtol": 1e-14},
                                                    options={"max_iterations": 5, "condition_limit": limit}))


def test_a_looser_declared_condition_limit_admits_but_never_upgrades_the_recorded_label():
    """J = [[1, 1], [1, 1 + eps]] has cond_2 ~ 4 / eps; eps = 4e-13 gives ~1e13: above the 1e12 default, below 1e14.

    The solve admits J under the declared limit 1e14 (policy sets the bar), but the record still judges it by the
    stricter default and calls it ill-conditioned: a caller's looser policy is not evidence of good conditioning.
    """
    record = DampedNewtonProvider().execute(_near_singular_linear(4e-13), _limited_newton(1e14))
    assert record.convergence is ConvergenceState.CONVERGED
    condition = record.diagnostics.condition
    assert 1e12 < condition.condition_number < 1e14
    assert condition.threshold == 1e12 and condition.status.value == "ill_conditioned"


def test_a_tighter_declared_condition_limit_is_the_bar_the_record_states():
    """Same J (cond ~1e13) under a declared limit 1e8: refused as SINGULAR_JACOBIAN, recorded against 1e8, not 1e12."""
    record = DampedNewtonProvider().execute(_near_singular_linear(4e-13), _limited_newton(1e8))
    assert record.convergence is ConvergenceState.FAILED
    assert record.diagnostics.failure_class == NumericalFailureClass.SINGULAR_JACOBIAN.value
    condition = record.diagnostics.condition
    assert condition.threshold == 1e8 and condition.status.value == "ill_conditioned"


# ---- 2026-10-18 remediation F1-d: the exit diagnostic reuses the admission estimate it would repeat ---------------


@pytest.mark.parametrize(("eps", "limit", "converged"), [(1.0, 1e10, True), (4e-13, 1e8, False)],
                         ids=["converged_well_conditioned", "refused_ill_conditioned"])
def test_the_recorded_condition_is_computed_once_when_it_equals_the_admission_estimate(monkeypatch, eps, limit, converged):
    from engcore.numerical import core, nonlinear

    calls = []

    def counting(matrix, **kwargs):
        calls.append(kwargs.get("threshold"))
        return core.condition_of(matrix, **kwargs)

    monkeypatch.setattr(nonlinear, "condition_of", counting)
    record = DampedNewtonProvider().execute(_near_singular_linear(eps), _limited_newton(limit))
    assert (record.convergence is ConvergenceState.CONVERGED) is converged
    # one Jacobian (a linear residual converges in one step, or is refused at the first), one estimate: the record's
    # threshold min(limit, 1e12) equals the admission threshold, so nothing is recomputed
    assert calls == [limit]
    fresh = core.condition_of(np.array([[1.0, 1.0], [1.0, 1.0 + eps]]), threshold=limit)
    assert record.diagnostics.condition == fresh


def test_a_looser_declared_limit_still_recomputes_against_the_stricter_bar(monkeypatch):
    from engcore.numerical import core, nonlinear

    calls = []

    def counting(matrix, **kwargs):
        calls.append(kwargs.get("threshold"))
        return core.condition_of(matrix, **kwargs)

    monkeypatch.setattr(nonlinear, "condition_of", counting)
    DampedNewtonProvider().execute(_near_singular_linear(4e-13), _limited_newton(1e14))
    assert calls == [1e14, 1e12]  # admission at the declared limit, the record at the stricter default
