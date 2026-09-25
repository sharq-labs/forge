"""BIG 6 numerical foundation: providers, identity, fail-closed diagnostics, integration.

Numerical convergence and cross-provider agreement are NOT validation.
Material data used here are the illustrative BIG 5 test fixtures.
"""

from __future__ import annotations

import importlib.util
import json
import math

import numpy as np
import pytest
import scipy.sparse as sp

from engcore.materials import MaterialState
from engcore.numerical import (
    NumPyDenseLinearProvider, NumericalMethod, NumericalProblem, NumericalRefusal, OperatorIdentity,
    PETScLinearProvider, ProblemKind, ProviderUnavailable, SciPyLinearProvider, SciPyMinimizeProvider,
    SciPyODEProvider, SciPyRootProvider, SundialsProvider, SymbolicSystem, UnitBoundary, VariableSpec,
    array_digest, compare_executions, to_raw_solver_output,
)
from engcore.scenarios import NamedQuantity, TimeBasis, TimePoint, TimeWindow
from engcore.scientific.errors import ScientificCoreError
from engcore.scientific.solvers.protocol import ConvergenceState, SolverSettings
from engcore.scientific.units.quantity import Quantity

_spec = importlib.util.spec_from_file_location("materials_fixtures", "tests/test_materials_engine.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)


def method(name, tolerances, **options):
    return NumericalMethod(name, SolverSettings(tolerances, options))


# ---- 1. linear: steady 1D conduction with a RESOLVED material conductivity ---


def _conduction_problem(n=8, t_left=500.0, t_right=300.0):
    props, _ = M._alloy_set()
    resolved = props.resolve("thermal_conductivity", M._alloy_state(400))  # BIG 5 resolution
    k = resolved.value.value.magnitude_in("W/(m*K)")
    length, h = 0.1, 0.1 / (n + 1)
    main = np.full(n, 2 * k / h**2)
    off = np.full(n - 1, -k / h**2)
    a = sp.diags([off, main, off], [-1, 0, 1]).tocsr()
    b = np.zeros(n)
    b[0] += k / h**2 * t_left / 100.0
    b[-1] += k / h**2 * t_right / 100.0
    op = OperatorIdentity("fd.steady_conduction_1d", "1", array_digest(a, b), "array_bytes")
    boundary = UnitBoundary((VariableSpec("T", "K", scale=100.0, size=n),))
    problem = NumericalProblem("slab-conduction", ProblemKind.LINEAR, op, boundary, {"matrix": a, "rhs": b},
                               parameters={"k": resolved.value.value})
    return problem, resolved


def test_linear_system_three_providers_agree_and_result_is_quantities():
    problem, resolved = _conduction_problem()
    dense = NumPyDenseLinearProvider().execute(problem, method("dense_lu", {"residual_rtol": 1e-12}))
    direct = SciPyLinearProvider().execute(problem, method("sparse_direct", {"residual_rtol": 1e-12}))
    gmres = SciPyLinearProvider().execute(problem, method("gmres", {"rtol": 1e-12}, max_iterations=200, restart=20))
    for rec in (dense, direct, gmres):
        assert rec.succeeded and rec.outputs["T"][0].units == "kelvin"
    temps = [q.magnitude for q in dense.outputs["T"]]
    assert temps == sorted(temps, reverse=True) and 300 < min(temps) < max(temps) < 500  # linear profile
    assert np.allclose(temps, np.linspace(500, 300, 10)[1:-1])
    agreement = compare_executions(dense, gmres, rtol=1e-8, atol=1e-8)
    assert agreement.agree and agreement.to_dict()["classification"] == "numerical_agreement_not_validation"
    assert len({dense.execution_identity, direct.execution_identity, gmres.execution_identity}) == 3
    assert dense.diagnostics.condition is not None and gmres.diagnostics.iterations >= 1
    # the problem binds the resolved material property it was assembled from
    assert problem.identity()["parameters"]["k"]["magnitude"] == resolved.value.value.magnitude
    raw = to_raw_solver_output(dense, {"T": "K"})
    assert raw.convergence is ConvergenceState.NOT_APPLICABLE and raw.diagnostics["numerical_execution_identity"] == dense.execution_identity


def test_linear_refusals_and_failures():
    problem, _ = _conduction_problem()
    with pytest.raises(NumericalRefusal, match="residual_rtol"):
        method("dense_lu", {}, ).__class__("dense_lu", SolverSettings({}), ("residual_rtol",))
    with pytest.raises(NumericalRefusal, match="do not match"):
        NumericalProblem("bad", ProblemKind.LINEAR, problem.operator, UnitBoundary((VariableSpec("T", "K", size=3),)), problem.operands)
    singular = np.array([[1.0, 2.0], [2.0, 4.0]])
    rhs = np.array([1.0, 2.0])
    p = NumericalProblem("singular", ProblemKind.LINEAR, OperatorIdentity("s", "1", array_digest(singular, rhs), "array_bytes"),
                         UnitBoundary((VariableSpec("x", "m", size=2),)), {"matrix": singular, "rhs": rhs})
    rec = NumPyDenseLinearProvider().execute(p, method("dense_lu", {"residual_rtol": 1e-12}))
    assert not rec.succeeded and rec.outputs == {} and rec.diagnostics.condition.status.value != "well_conditioned"
    short = SciPyLinearProvider().execute(problem, method("gmres", {"rtol": 1e-14}, max_iterations=1, restart=1))
    assert short.convergence is ConvergenceState.MAX_ITERATIONS and short.outputs == {}
    with pytest.raises(NumericalRefusal, match="max_iterations"):
        SciPyLinearProvider().execute(problem, method("gmres", {"rtol": 1e-8}))
    with pytest.raises(NumericalRefusal, match="non-finite"):
        bad = np.array([[1.0, np.nan], [0.0, 1.0]])
        NumericalProblem("nan", ProblemKind.LINEAR, OperatorIdentity("n", "1", "0" * 64, "declared"), UnitBoundary((VariableSpec("x", "m", size=2),)), {"matrix": bad, "rhs": rhs})
    with pytest.raises(NumericalRefusal, match="digest does not match"):
        NumericalProblem("forged", ProblemKind.LINEAR, OperatorIdentity("f", "1", "0" * 64, "array_bytes"), UnitBoundary((VariableSpec("x", "m", size=2),)), {"matrix": np.eye(2), "rhs": rhs})


def test_tolerance_method_or_provider_changes_identity_and_replay_reproduces():
    problem, _ = _conduction_problem()
    a = SciPyLinearProvider().execute(problem, method("gmres", {"rtol": 1e-10}, max_iterations=200, restart=20))
    b = SciPyLinearProvider().execute(problem, method("gmres", {"rtol": 1e-11}, max_iterations=200, restart=20))
    c = NumPyDenseLinearProvider().execute(problem, method("dense_lu", {"residual_rtol": 1e-10}))
    assert len({a.execution_identity, b.execution_identity, c.execution_identity}) == 3
    replay = SciPyLinearProvider().execute(problem, method("gmres", {"rtol": 1e-10}, max_iterations=200, restart=20))
    assert replay.execution_identity == a.execution_identity and compare_executions(a, replay, rtol=0, atol=1e-12).agree
    assert json.loads(json.dumps(a.to_dict()))["classification"] == "numerical_execution_not_scientific_evidence"
    with pytest.raises(ScientificCoreError):
        SolverSettings({"rtol": -1.0})


# ---- 2. nonlinear: SymPy operator, two methods -------------------------------


def _circle_line():
    system = SymbolicSystem("circle_line", ("x", "y"), ("x**2 + y**2 - 4", "x - y"))
    f, j = system.callables()
    boundary = UnitBoundary((VariableSpec("x", "m"), VariableSpec("y", "m")))
    return NumericalProblem("circle-line", ProblemKind.NONLINEAR_ROOT, system.identity(), boundary,
                            {"residual": f, "jacobian": j}, initial={"x": Quantity(1, "m"), "y": Quantity(0.5, "m")})


def test_nonlinear_root_two_methods_agree_with_exact_jacobian():
    problem = _circle_line()
    tol = {"xtol": 1e-12, "residual_atol": 1e-9}
    hybr = SciPyRootProvider().execute(problem, method("hybr", tol, max_function_evaluations=200))
    lm = SciPyRootProvider().execute(problem, method("lm", tol, max_function_evaluations=200))
    assert hybr.succeeded and lm.succeeded
    assert hybr.outputs["x"].magnitude == pytest.approx(math.sqrt(2))
    assert compare_executions(hybr, lm, rtol=1e-8, atol=1e-10).agree
    assert problem.operator.derivation == "symbolic_srepr"
    edited = SymbolicSystem("circle_line", ("x", "y"), ("x**2 + y**2 - 5", "x - y")).identity()
    assert edited.definition_digest != problem.operator.definition_digest


def test_nonlinear_failure_withholds_the_last_iterate():
    system = SymbolicSystem("no_root", ("x",), ("x**2 + 1",))
    f, j = system.callables()
    p = NumericalProblem("no-root", ProblemKind.NONLINEAR_ROOT, system.identity(), UnitBoundary((VariableSpec("x", "m"),)),
                         {"residual": f, "jacobian": j}, initial={"x": Quantity(0.3, "m")})
    rec = SciPyRootProvider().execute(p, method("hybr", {"xtol": 1e-12, "residual_atol": 1e-9}, max_function_evaluations=50))
    assert not rec.succeeded and rec.outputs == {} and rec.convergence in (ConvergenceState.NOT_CONVERGED, ConvergenceState.MAX_ITERATIONS)
    with pytest.raises(NumericalRefusal, match="undeclared symbols"):
        SymbolicSystem("bad", ("x",), ("x + z",)).identity()


def test_problem_level_refusals():
    problem = _circle_line()
    with pytest.raises(NumericalRefusal, match="initial values"):
        NumericalProblem("x", ProblemKind.NONLINEAR_ROOT, problem.operator, problem.unknowns, problem.operands)
    with pytest.raises(NumericalRefusal, match="Quantity records"):
        NumericalProblem("x", ProblemKind.NONLINEAR_ROOT, problem.operator, problem.unknowns, problem.operands, initial={"x": 1.0, "y": 1.0})
    with pytest.raises(Exception):
        NumericalProblem("x", ProblemKind.NONLINEAR_ROOT, problem.operator, problem.unknowns, problem.operands, initial={"x": Quantity(1, "s"), "y": Quantity(1, "m")})
    with pytest.raises(NumericalRefusal, match="affine"):
        VariableSpec("T", "degC")
    with pytest.raises(NumericalRefusal, match="does not support"):
        SciPyODEProvider().execute(problem, method("RK45", {"rtol": 1e-6, "atol": 1e-9}))
    with pytest.raises(NumericalRefusal, match="does not implement"):
        SciPyRootProvider().execute(problem, method("broyden1", {"xtol": 1e-9, "residual_atol": 1e-9}, max_function_evaluations=10))


# ---- 3. ODE inside a BIG 2 window, material-parameterised ---------------------

BASIS = TimeBasis("lab", "elapsed", "t0")


def _cooling(method_name, *, breakpoints=(), window_s=600.0, stiff=False):
    props, _ = M._alloy_set()
    # BIG 5: density valid only near room temperature -> resolved there, and bound into the problem
    rho = props.resolve("density", M._alloy_state(293.15)).value.value.magnitude_in("kg/m^3")
    cp, volume, h_area = 900.0, 1e-4, 0.5 if not stiff else 5e3
    tau = rho * cp * volume / h_area
    ambient = lambda t: 300.0 if t < 300.0 else 280.0  # noqa: E731  (step declared as breakpoint)
    rhs = lambda t, y: np.array([-(y[0] * 100.0 - ambient(t)) / tau / 100.0])  # noqa: E731
    window = TimeWindow(TimePoint("lab", Quantity(0, "s")), TimePoint("lab", Quantity(window_s, "s")))
    problem = NumericalProblem(
        "lumped-cooling", ProblemKind.ODE_IVP, OperatorIdentity("lumped_newton_cooling", "1", array_digest(np.array([tau])), "declared"),
        UnitBoundary((VariableSpec("T", "K", scale=100.0),)), {"rhs": rhs}, initial={"T": Quantity(400, "K")},
        parameters={"density": Quantity(rho, "kg/m^3")}, window=window, breakpoints=tuple(breakpoints),
        output_times=(Quantity(150, "s"), Quantity(300, "s")),
    )
    rec = SciPyODEProvider().execute(problem, method(method_name, {"rtol": 1e-9, "atol": 1e-11}))
    return problem, rec, tau


def test_ode_in_time_window_two_methods_agree_with_analytic_and_bridge_breakpoint():
    _, rk, tau = _cooling("RK45", breakpoints=(Quantity(300, "s"),))
    _, bdf, _ = _cooling("BDF", breakpoints=(Quantity(300, "s"),))
    assert rk.succeeded and bdf.succeeded and compare_executions(rk, bdf, rtol=1e-6, atol=1e-6).agree
    t300 = 300 + 100 * math.exp(-300 / tau)
    exact = 280 + (t300 - 280) * math.exp(-300 / tau)
    assert rk.outputs["T"].magnitude == pytest.approx(exact, rel=1e-6)
    assert [t.magnitude for t, _ in rk.trajectory] == [150.0, 300.0, 600.0]
    assert rk.diagnostics.warnings and "breakpoint" in rk.diagnostics.warnings[0]


def test_ode_refusals_and_stiff_method():
    with pytest.raises(NumericalRefusal, match="TimeWindow"):
        NumericalProblem("x", ProblemKind.ODE_IVP, OperatorIdentity("o", "1", "0" * 64, "declared"), UnitBoundary((VariableSpec("T", "K"),)),
                         {"rhs": lambda t, y: y}, initial={"T": Quantity(1, "K")})
    with pytest.raises(NumericalRefusal, match="inside the authorized window"):
        _cooling("RK45", breakpoints=(Quantity(900, "s"),))
    with pytest.raises(NumericalRefusal, match="rtol"):
        NumericalMethod("RK45", SolverSettings({"atol": 1e-9}), ("rtol", "atol"))
    _, stiff, _ = _cooling("Radau", stiff=True)
    assert stiff.succeeded


def test_ode_divergence_is_failed_not_an_output():
    window = TimeWindow(TimePoint("lab", Quantity(0, "s")), TimePoint("lab", Quantity(10, "s")))
    p = NumericalProblem("blowup", ProblemKind.ODE_IVP, OperatorIdentity("blow", "1", "0" * 64, "declared"), UnitBoundary((VariableSpec("y", "m"),)),
                         {"rhs": lambda t, y: y**2}, initial={"y": Quantity(1, "m")}, window=window)
    rec = SciPyODEProvider().execute(p, method("RK45", {"rtol": 1e-6, "atol": 1e-9}))
    assert not rec.succeeded and rec.outputs == {} and rec.trajectory == ()


# ---- 4. optimization ---------------------------------------------------------


def test_optimization_two_methods_agree():
    rosen = lambda x: (x[0] - 1) ** 2 + 10 * (x[1] + 2) ** 2 + 0.1 * (x[0] - 1) ** 4  # noqa: E731  (smooth, well conditioned)
    p = NumericalProblem("rosenbrock", ProblemKind.OPTIMIZATION, OperatorIdentity("rosenbrock", "1", "a" * 64, "declared"),
                         UnitBoundary((VariableSpec("a", "m"), VariableSpec("b", "m"))), {"objective": rosen},
                         initial={"a": Quantity(-1, "m"), "b": Quantity(1, "m")})
    bfgs = SciPyMinimizeProvider().execute(p, method("BFGS", {"gtol": 1e-6}, max_iterations=500))
    nm = SciPyMinimizeProvider().execute(p, method("Nelder-Mead", {"xatol": 1e-10, "fatol": 1e-12}, max_iterations=5000))
    assert bfgs.succeeded and nm.succeeded and bfgs.outputs["b"].magnitude == pytest.approx(-2, abs=1e-4) and compare_executions(bfgs, nm, rtol=1e-3, atol=1e-3).agree
    starved = SciPyMinimizeProvider().execute(p, method("BFGS", {"gtol": 1e-12}, max_iterations=2))
    assert not starved.succeeded and starved.outputs == {}


# ---- optional backends -------------------------------------------------------


def test_optional_backends_refuse_when_unavailable():
    problem, _ = _conduction_problem()
    petsc = PETScLinearProvider()
    if not petsc.available():
        with pytest.raises(ProviderUnavailable):
            petsc.execute(problem, method("ksp_gmres", {"rtol": 1e-10}, max_iterations=100))
    sundials = SundialsProvider()
    if not sundials.available():
        _, rec, _ = _cooling("RK45")
        with pytest.raises(ProviderUnavailable):
            sundials.execute(NumericalProblem(**{**_cooling("RK45")[0].__dict__}), method("cvode_bdf", {"rtol": 1e-6, "atol": 1e-9}))


def test_linear_identity_hashes_arrays_even_when_digest_is_declared():
    rhs = np.array([1.0, 2.0])
    op = OperatorIdentity("declared_linear", "1", "0" * 64, "declared")
    boundary = UnitBoundary((VariableSpec("x", "m", size=2),))
    a = NumericalProblem("same-id", ProblemKind.LINEAR, op, boundary, {"matrix": np.eye(2), "rhs": rhs})
    b = NumericalProblem("same-id", ProblemKind.LINEAR, op, boundary, {"matrix": 2 * np.eye(2), "rhs": rhs})
    assert a.digest != b.digest
    ra = NumPyDenseLinearProvider().execute(a, method("dense_lu", {"residual_rtol": 1e-12}))
    rb = NumPyDenseLinearProvider().execute(b, method("dense_lu", {"residual_rtol": 1e-12}))
    with pytest.raises(NumericalRefusal, match="same problem"):
        compare_executions(ra, rb, rtol=1, atol=1)


def test_bridge_keeps_failure_reason_and_missing_tolerance_is_a_refusal():
    singular = np.array([[1.0, 2.0], [2.0, 4.0]])
    rhs = np.array([1.0, 2.0])
    p = NumericalProblem("singular2", ProblemKind.LINEAR, OperatorIdentity("s", "1", array_digest(singular, rhs), "array_bytes"),
                         UnitBoundary((VariableSpec("x", "m", size=2),)), {"matrix": singular, "rhs": rhs})
    rec = NumPyDenseLinearProvider().execute(p, method("dense_lu", {"residual_rtol": 1e-12}))
    raw = to_raw_solver_output(rec, {"x": "m"})
    assert raw.diagnostics["reason"] and raw.values == {}
    with pytest.raises(NumericalRefusal, match="explicit tolerance"):
        NumPyDenseLinearProvider().execute(p, method("dense_lu", {}))


def test_ode_output_at_window_start_is_refused():
    with pytest.raises(NumericalRefusal, match="strictly after"):
        window = TimeWindow(TimePoint("lab", Quantity(0, "s")), TimePoint("lab", Quantity(10, "s")))
        NumericalProblem("o", ProblemKind.ODE_IVP, OperatorIdentity("o", "1", "0" * 64, "declared"), UnitBoundary((VariableSpec("y", "m"),)),
                         {"rhs": lambda t, y: -y}, initial={"y": Quantity(1, "m")}, window=window, output_times=(Quantity(0, "s"),))


def test_breakpoint_restart_uses_state_at_breakpoint_not_last_output():
    window = TimeWindow(TimePoint("lab", Quantity(0, "s")), TimePoint("lab", Quantity(10, "s")))
    p = NumericalProblem("ramp", ProblemKind.ODE_IVP, OperatorIdentity("ramp", "1", "0" * 64, "declared"), UnitBoundary((VariableSpec("y", "m"),)),
                         {"rhs": lambda t, y: np.array([1.0])}, initial={"y": Quantity(0, "m")}, window=window,
                         breakpoints=(Quantity(5, "s"),), output_times=(Quantity(2, "s"),))
    rec = SciPyODEProvider().execute(p, method("RK45", {"rtol": 1e-10, "atol": 1e-12}))
    assert rec.outputs["y"].magnitude == pytest.approx(10.0)
    assert [t.magnitude for t, _ in rec.trajectory] == [2.0, 10.0]
