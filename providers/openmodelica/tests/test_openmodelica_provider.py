"""Second-wave provider: real OpenModelica simulation + Proof E (OpenModelica vs BIG 6 SciPy ODE, independent paths)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from engcore.providers import ComparisonDeclaration, OutputSelection, ProviderRegistry, compare_providers
from engcore.scenarios import TimePoint, TimeWindow
from engcore.scientific.units.quantity import Quantity
from forge_openmodelica import LumpedThermalProblem, OpenModelicaProvider, descriptor

REG = ProviderRegistry()
descriptor.register(REG)
OK = REG.status("openmodelica").available
pytestmark = pytest.mark.skipif(not OK, reason="OpenModelica unavailable")
W = TimeWindow(TimePoint("lab", Quantity(0, "s")), TimePoint("lab", Quantity(1000, "s")))


def problem():
    return LumpedThermalProblem(Quantity(500, "J/K"), Quantity(2, "W/K"), Quantity(20, "W"), Quantity(293.15, "K"), Quantity(293.15, "K"), W, 10, 1e-8)


def test_openmodelica_executes_and_matches_the_analytic_solution_verification_only():
    rec = OpenModelicaProvider(REG).simulate(problem())
    assert rec.succeeded, rec.reason
    s = rec.series_for("temperature")
    exact = [293.15 + 10.0 * (1 - math.exp(-t / 250.0)) for t in s.times_s]
    assert np.max(np.abs(np.array(s.values) - exact)) < 1e-4  # analytic verification of the integration, not validation
    assert "model ForgeLumpedThermal" in rec.artifacts["model.mo"] and rec.identity.window == W


def test_proof_e_openmodelica_and_scipy_solve_ivp_corroborate():
    from engcore.numerical import NumericalMethod, NumericalProblem, OperatorIdentity, ProblemKind, SciPyODEProvider, UnitBoundary, VariableSpec
    from engcore.scientific.solvers.protocol import SolverSettings
    om = OpenModelicaProvider(REG).simulate(problem())
    times = om.series_for("temperature").times_s[1:]
    rhs = lambda t, y: np.array([(20.0 - 2.0 * (y[0] - 293.15)) / 500.0])  # noqa: E731
    ode = NumericalProblem("lumped-thermal", ProblemKind.ODE_IVP, OperatorIdentity("thermal.lumped_capacitance", "1", "0" * 64, "declared"),
                           UnitBoundary((VariableSpec("T", "K"),)), {"rhs": rhs}, initial={"T": Quantity(293.15, "K")}, window=W,
                           output_times=tuple(Quantity(t, "s") for t in times))
    sp = SciPyODEProvider().execute(ode, NumericalMethod("RK45", SolverSettings({"rtol": 1e-10, "atol": 1e-10}, {})))
    assert sp.succeeded, getattr(sp, "reason", "")
    by_t = {round(t.to("s").magnitude, 9): state["T"] for t, state in sp.trajectory}
    sp_vals = [float(np.ravel(np.asarray(by_t[round(t, 9)].to("K").magnitude))[0]) for t in times]
    decl = ComparisonDeclaration("lumped temperature at the 10 output instants", "K", "identity: same output instants requested from both",
                                 Quantity(1e-4, "K"), 0.0, "C=500 J/K, hA=2 W/K, P=20 W, Ta=293.15 K")
    wanted = {round(t, 9) for t in times}
    sp_rows = tuple(i for i, (t, _) in enumerate(sp.trajectory) if round(t.to("s").magnitude, 9) in wanted)
    assert len(sp_rows) == len(times)
    cmp = compare_providers(decl, om, "temperature", sp, "T", a_select=OutputSelection(rows=tuple(range(1, len(times) + 1))),
                            b_select=OutputSelection(rows=sp_rows))
    assert cmp.max_absolute == float(np.abs(np.asarray(om.series_for("temperature").values[1:]) - np.asarray(sp_vals)).max())
    print("PROOF_E_ODE", cmp.to_dict())
    assert cmp.within_tolerance
