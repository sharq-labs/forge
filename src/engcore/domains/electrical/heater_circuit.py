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
from ...numerical.robust import RobustSolveRecord, solve_with_method_chain
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
    #: progress" for ~6% of states of this LINEAR residual after reaching it to
    #: machine precision (and BIG 6 correctly refuses a backend non-success);
    #: ``lm`` does not.  Default kept for BIG 9 identity.
    root_method: str = "hybr"
    #: Declared root-method CHAIN (e.g. ``("hybr", "lm")``), the recorded
    #: alternative to choosing ``root_method="lm"`` by hand: every method solves
    #: the SAME problem from the same initial current, the first that converges
    #: by its own criteria is accepted, and every attempt is kept
    #: (:meth:`solve_with_attempts`).  Empty: the single ``root_method`` path,
    #: unchanged.  Named in the identity only when declared, so circuits without
    #: a chain keep their identity, operator digest and records byte-for-byte.
    root_methods: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        chain = tuple(str(m).strip() for m in self.root_methods)
        if chain:
            if self.root_method != "hybr":
                raise InvalidScientificProblem("declare either root_method or a root_methods chain, not both")
            if any(m not in ("hybr", "lm") for m in chain) or len(set(chain)) != len(chain):
                raise InvalidScientificProblem("root_methods is a chain of distinct SciPy root methods ('hybr', 'lm')")
        object.__setattr__(self, "root_methods", chain)

    def identity(self) -> dict:
        ident = {k: getattr(self, k).to_dict() for k in ("supply_voltage", "series_resistance", "r0", "t0", "alpha")}
        if self.root_method != "hybr":
            ident["root_method"] = self.root_method
        if self.root_methods:
            ident["root_methods"] = list(self.root_methods)
        return ident

    def heater_resistance(self, temperature: Quantity) -> float:
        r = self.r0.to("ohm").magnitude * (1 + self.alpha.to("1/K").magnitude * (temperature.to("K").magnitude - self.t0.to("K").magnitude))
        if not r > 0:
            raise InvalidScientificProblem(f"heater resistance {r} ohm at {temperature} is outside the linear TCR law's applicability")
        return r

    def solve(self, temperature: Quantity):
        """Return (numerical execution record, dissipated power Quantity).

        With a ``root_methods`` chain the record is the ACCEPTED execution (or,
        if every method failed, the last attempt); all attempts are available
        from :meth:`solve_with_attempts`.
        """
        _, record, power = self.solve_with_attempts(temperature)
        return record, power

    def solve_with_attempts(self, temperature: Quantity) -> tuple[RobustSolveRecord | None, object, Quantity | None]:
        """(chain record or None without a chain, numerical execution record, dissipated power or None)."""
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
        chain: RobustSolveRecord | None = None
        if not self.root_methods:
            record = SciPyRootProvider().execute(problem, NumericalMethod(self.root_method, SolverSettings({"xtol": 1e-14, "residual_atol": 1e-10},
                                                                                                   {"max_function_evaluations": 100})))
        else:
            # the same settings as the single-method path, for every method of the declared chain
            chain = solve_with_method_chain(
                SciPyRootProvider(), problem,
                tuple(NumericalMethod(m, SolverSettings({"xtol": 1e-14, "residual_atol": 1e-10}, {"max_function_evaluations": 100}))
                      for m in self.root_methods))
            record = chain.accepted if chain.accepted is not None else chain.attempts[-1].record
        if not record.succeeded:
            return chain, record, None
        i = record.outputs["current"].to("A").magnitude
        return chain, record, Quantity(i * i * rh, "W")
