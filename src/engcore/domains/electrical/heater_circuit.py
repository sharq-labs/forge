"""Series heater circuit solved through the BIG 6 numerical layer (coupling reference adapter).

    V = I * (R_s + R_h(T)),   R_h(T) = R_0 * (1 + alpha * (T - T_0)),   P_h = I^2 R_h(T)

The linear TCR law and its parameters are DECLARED inputs of this reference
adapter (not calibrated data); a non-positive heater resistance is outside the
law's applicability and is refused rather than solved.  The KVL residual is
posed as a BIG 6 ``NumericalProblem`` and solved with ``SciPyRootProvider`` so
the electrical participant is a genuinely different provider type from a PDE
participant.  Its execution record is returned unchanged for coupling provenance.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ...numerical import (
    NumericalMethod, NumericalProblem, OperatorIdentity, ProblemKind, SciPyRootProvider, UnitBoundary, VariableSpec,
)
from ...scenarios.timeline import canonical_digest
from ...scientific.errors import InvalidScientificProblem
from ...scientific.solvers.protocol import SolverSettings
from ...scientific.units.quantity import Quantity


@dataclass(frozen=True)
class HeaterCircuit:
    supply_voltage: Quantity
    series_resistance: Quantity
    r0: Quantity
    t0: Quantity
    alpha: Quantity
    #: BIG 6 root method.  SciPy 1.18 ``hybr`` reports "not making good
    #: progress" for 6-8% of states of this LINEAR residual after reaching it to
    #: machine precision (67 of an 800-state V x T grid on 2026-10-13), and BIG 6
    #: correctly refuses a backend non-success, so a coupled run died mid-window
    #: for no physical reason; ``lm`` refused none of the 800 and matched the
    #: closed form to 7e-16.  The default was ``hybr`` until 2026-10-13, kept
    #: for BIG 9 identity -- which is why :meth:`identity` still omits the
    #: method when it is ``hybr``: a record without one was, and still means, a
    #: ``hybr`` solve, and a default-built circuit now names ``lm``.
    root_method: str = "lm"

    def identity(self) -> dict:
        ident = {k: getattr(self, k).to_dict() for k in ("supply_voltage", "series_resistance", "r0", "t0", "alpha")}
        if self.root_method != "hybr":
            ident["root_method"] = self.root_method
        return ident

    def heater_resistance(self, temperature: Quantity) -> float:
        r = self.r0.to("ohm").magnitude * (1 + self.alpha.to("1/K").magnitude * (temperature.to("K").magnitude - self.t0.to("K").magnitude))
        if not r > 0:
            raise InvalidScientificProblem(f"heater resistance {r} ohm at {temperature} is outside the linear TCR law's applicability")
        return r

    def solve(self, temperature: Quantity):
        """Return (numerical execution record, dissipated power Quantity)."""
        rh = self.heater_resistance(temperature)
        v = self.supply_voltage.to("V").magnitude
        rs = self.series_resistance.to("ohm").magnitude
        residual = lambda x: np.array([v - x[0] * (rs + rh)])  # noqa: E731  current in A
        jac = lambda x: np.array([[-(rs + rh)]])  # noqa: E731
        op = OperatorIdentity("electrical.series_kvl", "1", canonical_digest({"circuit": self.identity(), "rh_ohm": rh}), "declared")
        problem = NumericalProblem(f"kvl-{op.definition_digest[:12]}", ProblemKind.NONLINEAR_ROOT, op,
                                   UnitBoundary((VariableSpec("current", "A"),)), {"residual": residual, "jacobian": jac},
                                   initial={"current": Quantity(v / (rs + rh) * 0.5, "A")},
                                   parameters={"temperature": temperature.to("K"), "heater_resistance": Quantity(rh, "ohm")})
        record = SciPyRootProvider().execute(problem, NumericalMethod(self.root_method, SolverSettings({"xtol": 1e-14, "residual_atol": 1e-10},
                                                                                               {"max_function_evaluations": 100})))
        if not record.succeeded:
            return record, None
        i = record.outputs["current"].to("A").magnitude
        return record, Quantity(i * i * rh, "W")
