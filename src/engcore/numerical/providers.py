"""Numerical providers: NumPy, SciPy, SymPy (symbolic operator), PETSc and SUNDIALS contracts.

Callables in ``NumericalProblem.operands`` work in the NORMALIZED space the
problem's ``UnitBoundary`` defines (and, for ODEs, time in seconds).  Raw
backend objects never leave this module: every provider returns a
:class:`NumericalExecutionRecord`.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import scipy
import scipy.linalg as sla
import scipy.optimize as sopt
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from scipy.integrate import solve_ivp

from ..scenarios.timeline import TimePoint
from ..scientific.solvers.protocol import ConvergenceState, SolverIdentity
from ..scientific.units.quantity import Quantity
from .core import (
    NumericalDiagnostics, NumericalExecutionRecord, NumericalMethod, NumericalProblem, NumericalProvider,
    NumericalRefusal, ProblemKind, ProviderUnavailable, condition_of, failed, health_of,
)


def _tol(method: NumericalMethod, key: str) -> float:
    if key not in method.settings.tolerances:
        raise NumericalRefusal(f"method {method.method!r} requires an explicit tolerance {key!r}; none is defaulted")
    return float(method.settings.tolerances[key])


def _opt(method: NumericalMethod, key: str, default: Any = None) -> Any:
    return method.settings.options.get(key, default)


def _success(problem, provider, method, state, x, diagnostics, *, trajectory=(), determinism="not_bitwise_guaranteed"):
    health = health_of(x)
    diagnostics = NumericalDiagnostics(**{**diagnostics.__dict__, "health": health})
    if not np.all(np.isfinite(x)):
        return failed(problem, provider, method, ConvergenceState.FAILED, diagnostics, "non-finite solution")
    return NumericalExecutionRecord(problem.digest, problem.identity(), provider, method, state,
                                    problem.unknowns.from_array(x), diagnostics, tuple(trajectory), determinism)


# --------------------------------------------------------------------------
# Linear
# --------------------------------------------------------------------------


class NumPyDenseLinearProvider(NumericalProvider):
    """Dense LU via numpy.linalg.solve.  Required tolerance: residual_rtol."""

    identity = SolverIdentity("numpy.linalg", np.__version__, backend="LAPACK gesv")
    kinds = frozenset({ProblemKind.LINEAR})
    methods = frozenset({"dense_lu"})

    def _execute(self, problem, method):
        _tol(method, "residual_rtol")  # required before any work, not discovered after
        a = problem.operands["matrix"]
        a = a.toarray() if hasattr(a, "toarray") else np.asarray(a, dtype=float)
        b = np.asarray(problem.operands["rhs"], dtype=float).reshape(-1)
        cond = condition_of(a)
        try:
            x = np.linalg.solve(a, b)
        except np.linalg.LinAlgError as exc:
            return failed(problem, self.identity, method, ConvergenceState.FAILED, NumericalDiagnostics(condition=cond, termination_message=str(exc)), "singular matrix")
        r = float(np.linalg.norm(a @ x - b) / max(np.linalg.norm(b), 1e-300))
        d = NumericalDiagnostics(residual_norm=r, condition=cond, termination_message="direct solve")
        if not math.isfinite(r) or r > _tol(method, "residual_rtol"):
            return failed(problem, self.identity, method, ConvergenceState.FAILED, d, f"relative residual {r} exceeds residual_rtol")
        return _success(problem, self.identity, method, ConvergenceState.NOT_APPLICABLE, x, d, )


class SciPyLinearProvider(NumericalProvider):
    """Sparse direct (spsolve) or iterative GMRES.  GMRES requires rtol and max_iterations."""

    identity = SolverIdentity("scipy.sparse.linalg", scipy.__version__, backend="SuperLU / GMRES")
    kinds = frozenset({ProblemKind.LINEAR})
    methods = frozenset({"sparse_direct", "gmres"})

    def _execute(self, problem, method):
        a = sp.csr_matrix(problem.operands["matrix"])
        b = np.asarray(problem.operands["rhs"], dtype=float).reshape(-1)
        cond = condition_of(a) if a.shape[0] <= 2000 else None
        if method.method == "sparse_direct":
            _tol(method, "residual_rtol")
            x = spla.spsolve(a.tocsc(), b)
            r = float(np.linalg.norm(a @ x - b) / max(np.linalg.norm(b), 1e-300))
            d = NumericalDiagnostics(residual_norm=r, condition=cond, termination_message="SuperLU direct solve")
            if not math.isfinite(r) or r > _tol(method, "residual_rtol"):
                return failed(problem, self.identity, method, ConvergenceState.FAILED, d, "residual check failed")
            return _success(problem, self.identity, method, ConvergenceState.NOT_APPLICABLE, x, d)
        maxiter = _opt(method, "max_iterations")
        if not isinstance(maxiter, int) or maxiter < 1:
            raise NumericalRefusal("gmres requires an explicit positive integer option 'max_iterations'")
        history: list[float] = []
        restart = _opt(method, "restart")
        if not isinstance(restart, int) or restart < 1:
            raise NumericalRefusal("gmres requires an explicit positive integer option 'restart' (Krylov subspace size); maxiter counts restart cycles")
        x, info = spla.gmres(a, b, rtol=_tol(method, "rtol"), atol=0.0, maxiter=maxiter, restart=restart,
                             callback=lambda rk: history.append(float(rk)), callback_type="pr_norm")
        r = float(np.linalg.norm(a @ x - b) / max(np.linalg.norm(b), 1e-300))
        d = NumericalDiagnostics(residual_norm=r, residual_history=tuple(history), iterations=len(history), condition=cond,
                                 termination_message=f"gmres info={info}")
        if info > 0:
            return failed(problem, self.identity, method, ConvergenceState.MAX_ITERATIONS, d, "gmres hit max_iterations")
        if info < 0 or not math.isfinite(r):
            return failed(problem, self.identity, method, ConvergenceState.FAILED, d, "gmres breakdown")
        if r > _tol(method, "rtol") * (1 + 1e-6):
            return failed(problem, self.identity, method, ConvergenceState.NOT_CONVERGED, d, f"true relative residual {r} exceeds rtol despite info=0")
        return _success(problem, self.identity, method, ConvergenceState.CONVERGED, x, d)


# --------------------------------------------------------------------------
# Nonlinear / optimization
# --------------------------------------------------------------------------


class SciPyRootProvider(NumericalProvider):
    """scipy.optimize.root.  Required tolerances: xtol, residual_atol (acceptance)."""

    identity = SolverIdentity("scipy.optimize.root", scipy.__version__, backend="MINPACK")
    kinds = frozenset({ProblemKind.NONLINEAR_ROOT})
    methods = frozenset({"hybr", "lm"})

    def _execute(self, problem, method):
        f = problem.operands.get("residual")
        if not callable(f):
            raise NumericalRefusal("nonlinear problem requires a 'residual' callable")
        jac = problem.operands.get("jacobian")
        x0 = problem.unknowns.to_array(problem.initial)
        maxfev = _opt(method, "max_function_evaluations")
        if not isinstance(maxfev, int) or maxfev < 1:
            raise NumericalRefusal("root solve requires an explicit positive integer option 'max_function_evaluations'")
        opts = {"xtol": _tol(method, "xtol"), ("maxfev" if method.method == "hybr" else "maxiter"): maxfev}
        with np.errstate(all="ignore"):
            sol = sopt.root(f, x0, jac=jac if callable(jac) else None, method=method.method, options=opts)
            fx = np.asarray(f(sol.x), dtype=float)
        rn = float(np.linalg.norm(fx)) if np.all(np.isfinite(fx)) else math.inf
        d = NumericalDiagnostics(residual_norm=rn if math.isfinite(rn) else None, function_evaluations=int(getattr(sol, "nfev", 0)),
                                 jacobian_evaluations=int(getattr(sol, "njev", 0) or 0), termination_message=str(sol.message))
        if not math.isfinite(rn):
            return failed(problem, self.identity, method, ConvergenceState.DIVERGED, d, "non-finite residual")
        if not sol.success:
            state = ConvergenceState.MAX_ITERATIONS if "calls" in str(sol.message) or "maximum" in str(sol.message).lower() else ConvergenceState.NOT_CONVERGED
            return failed(problem, self.identity, method, state, d, f"backend did not converge: {sol.message}")
        if rn > _tol(method, "residual_atol"):
            return failed(problem, self.identity, method, ConvergenceState.NOT_CONVERGED, d, f"residual norm {rn} exceeds residual_atol")
        return _success(problem, self.identity, method, ConvergenceState.CONVERGED, sol.x, d)


class SciPyMinimizeProvider(NumericalProvider):
    """scipy.optimize.minimize.  Required tolerance: gtol (BFGS) or xatol/fatol (Nelder-Mead)."""

    identity = SolverIdentity("scipy.optimize.minimize", scipy.__version__)
    kinds = frozenset({ProblemKind.OPTIMIZATION})
    methods = frozenset({"BFGS", "Nelder-Mead"})

    def _execute(self, problem, method):
        f = problem.operands.get("objective")
        if not callable(f):
            raise NumericalRefusal("optimization problem requires an 'objective' callable")
        maxiter = _opt(method, "max_iterations")
        if not isinstance(maxiter, int) or maxiter < 1:
            raise NumericalRefusal("minimize requires an explicit positive integer option 'max_iterations'")
        allowed = {"BFGS": {"gtol"}, "Nelder-Mead": {"xatol", "fatol"}}[method.method]
        given = set(method.settings.tolerances)
        if not given or not given <= allowed:
            raise NumericalRefusal(f"{method.method} takes tolerances {sorted(allowed)}; got {sorted(given)}")
        opts = {"maxiter": maxiter}
        opts.update({k: float(v) for k, v in method.settings.tolerances.items()})
        with np.errstate(all="ignore"):
            sol = sopt.minimize(f, problem.unknowns.to_array(problem.initial), method=method.method, options=opts)
        d = NumericalDiagnostics(objective_value=float(sol.fun) if math.isfinite(float(sol.fun)) else None, iterations=int(sol.nit),
                                 function_evaluations=int(sol.nfev), termination_message=str(sol.message))
        if not math.isfinite(float(sol.fun)):
            return failed(problem, self.identity, method, ConvergenceState.DIVERGED, d, "non-finite objective")
        if not sol.success:
            state = ConvergenceState.MAX_ITERATIONS if sol.nit >= maxiter else ConvergenceState.NOT_CONVERGED
            return failed(problem, self.identity, method, state, d, f"backend did not converge: {sol.message}")
        return _success(problem, self.identity, method, ConvergenceState.CONVERGED, sol.x, d)


# --------------------------------------------------------------------------
# Time integration
# --------------------------------------------------------------------------


class SciPyODEProvider(NumericalProvider):
    """scipy.integrate.solve_ivp inside one authorized TimeWindow.

    Required tolerances: rtol, atol.  Declared breakpoints split the window
    into segments integrated separately: the integrator is never allowed to
    step across a discontinuity it was told about.  The provider owns only
    numerical steps; BIG 2 owns the window, its basis and its events.
    """

    identity = SolverIdentity("scipy.integrate.solve_ivp", scipy.__version__)
    kinds = frozenset({ProblemKind.ODE_IVP})
    methods = frozenset({"RK45", "BDF", "Radau", "LSODA"})

    def _execute(self, problem, method):
        rhs = problem.operands.get("rhs")
        if not callable(rhs):
            raise NumericalRefusal("ODE problem requires an 'rhs' callable f(t_seconds, y_normalized)")
        start, end = float(problem.window.start.seconds), float(problem.window.end.seconds)
        cuts = sorted({b.to("s").magnitude for b in problem.breakpoints if start < b.to("s").magnitude < end})
        edges = [start, *cuts, end]
        outs = sorted({t.to("s").magnitude for t in problem.output_times} | {end})
        y = problem.unknowns.to_array(problem.initial)
        nfev = njev = nlu = 0
        traj: list[tuple[Quantity, dict]] = []
        for a, b in zip(edges, edges[1:]):
            t_eval = [t for t in outs if a < t <= b]
            with np.errstate(all="ignore"):
                sol = solve_ivp(rhs, (a, b), y, method=method.method, rtol=_tol(method, "rtol"), atol=_tol(method, "atol"),
                                t_eval=t_eval or None)
            nfev += int(sol.nfev); njev += int(sol.njev); nlu += int(sol.nlu)
            sol_y = np.asarray(sol.y, dtype=float)
            d = NumericalDiagnostics(function_evaluations=nfev, jacobian_evaluations=njev, accepted_steps=None,
                                     termination_message=str(sol.message))
            if not sol.success or sol_y.size == 0 or not np.all(np.isfinite(sol_y)):
                state = ConvergenceState.DIVERGED if sol_y.size and not np.all(np.isfinite(sol_y)) else ConvergenceState.FAILED
                return failed(problem, self.identity, method, state, d, f"integration failed in segment [{a}, {b}] s: {sol.message}")
            for i, t in enumerate(sol.t):
                if any(math.isclose(t, o, rel_tol=0, abs_tol=0) or t == o for o in t_eval):
                    traj.append((Quantity(float(t), "s"), problem.unknowns.from_array(sol_y[:, i])))
            y = sol_y[:, -1]
        missing = sorted(set(outs) - {t.magnitude for t, _ in traj})
        if missing:
            return failed(problem, self.identity, method, ConvergenceState.FAILED,
                          NumericalDiagnostics(function_evaluations=nfev, termination_message="output coverage"),
                          f"requested output times {missing} s were not produced")
        d = NumericalDiagnostics(function_evaluations=nfev, jacobian_evaluations=njev, termination_message="integrated all segments",
                                 warnings=(f"{len(cuts)} declared breakpoint(s) bridged by restart",) if cuts else ())
        return _success(problem, self.identity, method, ConvergenceState.CONVERGED, y, d, trajectory=traj)


# --------------------------------------------------------------------------
# Optional backends: PETSc (scalable linear), SUNDIALS (stiff ODE/DAE)
# --------------------------------------------------------------------------


class PETScLinearProvider(NumericalProvider):
    """petsc4py KSP.  Optional: unavailable -> ProviderUnavailable, never a silent fallback."""

    kinds = frozenset({ProblemKind.LINEAR})
    methods = frozenset({"ksp_gmres", "ksp_cg"})

    def __init__(self) -> None:
        try:
            import petsc4py  # noqa: F401
            version = petsc4py.__version__
        except ImportError:
            version = "unavailable"
        self.identity = SolverIdentity("petsc4py.KSP", version, backend="PETSc")

    def available(self) -> bool:
        return self.identity.version != "unavailable"

    def _execute(self, problem, method):  # pragma: no cover - requires petsc4py
        from petsc4py import PETSc

        a = sp.csr_matrix(problem.operands["matrix"])
        b = np.asarray(problem.operands["rhs"], dtype=float).reshape(-1)
        maxiter = _opt(method, "max_iterations")
        if not isinstance(maxiter, int) or maxiter < 1:
            raise NumericalRefusal("PETSc KSP requires an explicit positive integer option 'max_iterations'")
        A = PETSc.Mat().createAIJ(size=a.shape, csr=(a.indptr, a.indices, a.data))
        ksp = PETSc.KSP().create()
        ksp.setOperators(A)
        ksp.setType(method.method.removeprefix("ksp_"))
        pc = _opt(method, "preconditioner")
        if not isinstance(pc, str) or not pc:
            raise NumericalRefusal("PETSc KSP requires an explicit 'preconditioner' option (it is part of the execution identity)")
        ksp.getPC().setType(pc)
        ksp.setTolerances(rtol=_tol(method, "rtol"), atol=0.0, max_it=maxiter)
        bv, xv = A.createVecs()
        bv.setArray(b)
        ksp.solve(bv, xv)
        reason = ksp.getConvergedReason()
        d = NumericalDiagnostics(residual_norm=float(ksp.getResidualNorm()), iterations=int(ksp.getIterationNumber()), termination_message=f"KSP reason {reason}")
        if reason <= 0:
            return failed(problem, self.identity, method, ConvergenceState.MAX_ITERATIONS if reason == -3 else ConvergenceState.NOT_CONVERGED, d, f"KSP diverged, reason {reason}")
        return _success(problem, self.identity, method, ConvergenceState.CONVERGED, xv.getArray().copy(), d)


class SundialsProvider(NumericalProvider):
    """Contract for SUNDIALS CVODE/IDA (stiff ODE / DAE).  Implementation is the next numerical slice."""

    kinds = frozenset({ProblemKind.ODE_IVP, ProblemKind.DAE})
    methods = frozenset({"cvode_bdf", "ida"})

    #: No SUNDIALS binding is wired yet, so the contract reports unavailable
    #: rather than probing for a package it would not use.
    identity = SolverIdentity("sundials", "unavailable")

    def available(self) -> bool:
        return False

    def _execute(self, problem, method):  # pragma: no cover
        raise NumericalRefusal("SUNDIALS execution is not implemented yet; use SciPyODEProvider BDF/Radau for stiff ODEs")
