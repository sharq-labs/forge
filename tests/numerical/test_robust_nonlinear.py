"""Robust nonlinear solving: declared method chain and parameter continuation (ERT V1, Big Rock 7).

Both strategies only compose provider executions: a result exists only when an
execution of the target problem converged by its own criteria; a failed
attempt's iterate is never reused.  NOT YET EXECUTED (build phase): see
docs/work/DEFERRED_VALIDATION.md.
"""

from __future__ import annotations

import numpy as np
import pytest

from engcore.numerical import (
    NumericalDiagnostics, NumericalExecutionRecord, NumericalMethod, NumericalProblem, NumericalProvider,
    NumericalRefusal, OperatorIdentity, ProblemKind, SciPyRootProvider, UnitBoundary, VariableSpec,
)
from engcore.numerical.core import failed
from engcore.numerical.robust import solve_by_continuation, solve_with_method_chain
from engcore.scientific.solvers.protocol import ConvergenceState, SolverIdentity, SolverSettings
from engcore.scientific.units.quantity import Quantity

BOUNDARY = UnitBoundary((VariableSpec("x", "K"),))
OPERATOR = OperatorIdentity("shifted_identity", "1", "a" * 64, "declared")


def _problem(lam: float, x0: float = 0.0) -> NumericalProblem:
    """x - 10 lam = 0 (root 10 lam); lam is a declared parameter, so each lam is its own problem identity."""
    root = 10.0 * lam
    return NumericalProblem(
        "shifted", ProblemKind.NONLINEAR_ROOT, OPERATOR, BOUNDARY,
        operands={"residual": lambda x, r=root: np.asarray([x[0] - r]), "root": root},
        initial={"x": Quantity(x0, "K")}, parameters={"lam": Quantity(lam, "dimensionless")},
    )


class Fake(NumericalProvider):
    """'good' converges, 'bad' never does, 'basin' converges only from within 3 K of the root."""

    identity = SolverIdentity("fake.root", "1")
    kinds = frozenset({ProblemKind.NONLINEAR_ROOT})
    methods = frozenset({"good", "bad", "basin"})

    def __init__(self):
        self.starts: list[tuple[str, float]] = []

    def _execute(self, problem, method):
        x0 = float(problem.unknowns.to_array(problem.initial)[0])
        root = float(problem.operands["root"])
        self.starts.append((method.method, x0))
        if method.method == "bad" or (method.method == "basin" and abs(x0 - root) > 3.0):
            return failed(problem, self.identity, method, ConvergenceState.NOT_CONVERGED, NumericalDiagnostics(),
                          "outside the basin of attraction")
        return NumericalExecutionRecord(problem.digest, problem.identity(), self.identity, method, ConvergenceState.CONVERGED,
                                        problem.unknowns.from_array(np.asarray([root])), NumericalDiagnostics())


def _m(name):
    return NumericalMethod(name)


# ---- method chain --------------------------------------------------------------------------


def test_chain_accepts_the_first_converging_method_and_records_every_attempt():
    provider = Fake()
    out = solve_with_method_chain(provider, _problem(1.0), (_m("bad"), _m("good")))
    assert out.succeeded and out.accepted.method.method == "good"
    assert [a.method for a in out.attempts] == ["bad", "good"]


def test_every_chain_attempt_starts_from_the_declared_initial_values():
    provider = Fake()
    solve_with_method_chain(provider, _problem(1.0, x0=4.0), (_m("bad"), _m("good")))
    assert [x0 for _, x0 in provider.starts] == [4.0, 4.0]  # never a failed attempt's iterate


def test_a_chain_where_every_method_fails_has_no_result():
    out = solve_with_method_chain(Fake(), _problem(1.0), (_m("bad"),))
    assert not out.succeeded and out.accepted is None and "every declared method failed" in out.reason


def test_a_refusal_is_a_configuration_error_not_a_numerical_failure():
    with pytest.raises(NumericalRefusal, match="does not implement method"):
        solve_with_method_chain(Fake(), _problem(1.0), (_m("bad"), _m("newton")))


@pytest.mark.parametrize("methods", [(), (_m("good"),) * 2, tuple(_m("good") for _ in range(9))])
def test_chain_declarations_are_bounded_and_unique(methods):
    with pytest.raises(NumericalRefusal):
        solve_with_method_chain(Fake(), _problem(1.0), methods)


# ---- continuation --------------------------------------------------------------------------


def test_the_basin_method_cannot_solve_the_target_directly():
    assert not solve_with_method_chain(Fake(), _problem(1.0), (_m("basin"),)).succeeded


def test_continuation_reaches_the_target_through_converged_warm_starts_only():
    provider = Fake()
    out = solve_by_continuation(provider, _problem, _m("basin"), initial_step=0.25, minimum_step=0.05, max_steps=20)
    assert out.succeeded
    assert out.accepted.outputs["x"].magnitude_in("K") == pytest.approx(10.0)
    # starts: lam 0 from 0, then each step from the previous CONVERGED root 2.5 apart
    assert [x0 for _, x0 in provider.starts] == pytest.approx([0.0, 0.0, 2.5, 5.0, 7.5])
    assert out.target_problem_digest == _problem(1.0).digest


def test_a_failed_step_is_halved_and_its_iterate_is_never_reused():
    provider = Fake()
    out = solve_by_continuation(provider, _problem, _m("basin"), initial_step=1.0, minimum_step=0.05, max_steps=20)
    assert out.succeeded
    # lam 0 (ok) -> lam 1 from 0 (fails, 10 > 3) -> lam 0.5 from 0 (fails, 5 > 3) -> lam 0.25 from 0 (ok) -> ...
    starts = [x0 for _, x0 in provider.starts]
    assert starts[:4] == pytest.approx([0.0, 0.0, 0.0, 0.0])
    lams = [a.lam for a in out.attempts]
    assert lams[:4] == pytest.approx([0.0, 1.0, 0.5, 0.25])


def test_continuation_fails_honestly_below_the_minimum_step():
    out = solve_by_continuation(Fake(), _problem, _m("basin"), initial_step=1.0, minimum_step=0.5, max_steps=20)
    assert not out.succeeded and "below the declared minimum" in out.reason


def test_continuation_fails_honestly_when_the_step_budget_is_spent():
    out = solve_by_continuation(Fake(), _problem, _m("basin"), initial_step=0.25, minimum_step=0.25, max_steps=3)
    assert not out.succeeded and "step budget" in out.reason


def test_an_unsolved_starting_problem_ends_the_continuation():
    out = solve_by_continuation(Fake(), _problem, _m("bad"), initial_step=0.5, minimum_step=0.1, max_steps=10)
    assert not out.succeeded and "lam = 0" in out.reason and len(out.attempts) == 1


@pytest.mark.parametrize("kwargs", [dict(initial_step=0.0), dict(initial_step=1.5), dict(minimum_step=0.6),
                                    dict(max_steps=0), dict(max_steps=True)])
def test_continuation_parameters_are_declared_and_bounded(kwargs):
    base = dict(initial_step=0.5, minimum_step=0.1, max_steps=10)
    with pytest.raises(NumericalRefusal):
        solve_by_continuation(Fake(), _problem, _m("basin"), **{**base, **kwargs})


def test_a_family_that_changes_its_unknowns_is_refused():
    other = UnitBoundary((VariableSpec("y", "K"),))

    def family(lam):
        problem = _problem(lam)
        if lam == 0.0:
            return problem
        return NumericalProblem("shifted", ProblemKind.NONLINEAR_ROOT, OPERATOR, other, operands=problem.operands,
                                initial={"y": Quantity(0.0, "K")}, parameters=problem.parameters)

    with pytest.raises(NumericalRefusal, match="unknowns"):
        solve_by_continuation(Fake(), family, _m("basin"), initial_step=0.5, minimum_step=0.1, max_steps=10)


def test_continuation_with_the_real_scipy_root_provider():
    method = NumericalMethod("hybr", SolverSettings(tolerances={"xtol": 1e-12, "residual_atol": 1e-9},
                                                    options={"max_function_evaluations": 200}),
                             required_tolerances=("xtol", "residual_atol"))
    out = solve_by_continuation(SciPyRootProvider(), _problem, method, initial_step=0.5, minimum_step=0.1, max_steps=10)
    assert out.succeeded and out.accepted.outputs["x"].magnitude_in("K") == pytest.approx(10.0, abs=1e-9)
    assert out.to_dict()["classification"] == "numerical_execution_not_scientific_evidence"
