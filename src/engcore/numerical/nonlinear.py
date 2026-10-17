"""Damped Newton for square nonlinear root problems (Phase 3 BR13).

A NumericalProvider beside ``SciPyRootProvider``: it adds what MINPACK does not
expose -- a declared, scale-aware acceptance measure, a recorded step-length
history, and a classified failure (``numerical.health``).  It holds no
scientific authority: CONVERGED means only that the declared residual measure
fell to the declared tolerance.

Methods
    ``newton``         full Newton steps ``x <- x + dx``, ``J(x) dx = -F(x)``.
    ``newton_armijo``  the same direction with backtracking on the merit
                       ``phi = 0.5 * ||D F||_2^2`` until the Armijo condition
                       ``phi(x + a dx) <= phi(x) - 2 c1 a phi(x)`` holds (the
                       exact Newton direction has slope ``-2 phi``).

Acceptance (no default anywhere)
    tolerances ``residual_atol`` (on the measure ``max_i |F_i| / s_i``, with the
    declared ``residual_scales`` s, or unscaled when none are declared) and
    ``step_rtol`` (a step below ``step_rtol * (1 + ||x||_inf)`` while the
    residual is above tolerance is STEP_STAGNATION, never convergence);
    option ``max_iterations``.  ``newton_armijo`` also needs ``armijo_c1`` in
    (0, 0.5), ``backtrack_factor`` in (0, 1) and ``max_backtracks``.

Jacobian
    the problem's ``jacobian`` operand, or -- only when the method declares
    ``finite_difference_step`` -- forward differences with relative step
    ``h_j = fd * max(1, |x_j|)``; the record says which.  The system must be
    square: a least-squares "root" is a different problem and is refused.
    A Jacobian the linear solve cannot use is SINGULAR_JACOBIAN; with a declared
    ``condition_limit``, so is one whose condition number -- exact, or a
    proven lower bound for a large sparse Jacobian (``core.condition_of``) --
    exceeds it.  An unresolved condition estimate refuses nothing and is
    recorded as unresolved.

What a converged record does NOT say is stated in it
(:data:`~engcore.numerical.health.RESIDUAL_IS_NOT_AN_ERROR_BOUND`).
"""

from __future__ import annotations

import math
from typing import Any, Callable

import numpy as np

from ..scientific.solvers.protocol import ConvergenceState, SolverIdentity
from .core import (
    DENSE_CONVERSION_LIMIT, SPARSE_EXACT_CONDITION_LIMIT, NumericalDiagnostics, NumericalExecutionRecord,
    NumericalMethod, NumericalProblem, NumericalProvider, NumericalRefusal, ProblemKind, canonical_csr,
    condition_of, failed, health_of, is_sparse,
)
from .health import (
    RESIDUAL_IS_NOT_AN_ERROR_BOUND, HistoryPolicy, NumericalFailureClass, ResidualScaling, classify_history,
)


def _required_tolerance(method: NumericalMethod, key: str) -> float:
    if key not in method.settings.tolerances:
        raise NumericalRefusal(f"method {method.method!r} requires an explicit tolerance {key!r}; none is defaulted")
    value = float(method.settings.tolerances[key])
    if not math.isfinite(value) or value < 0.0:
        raise NumericalRefusal(f"tolerance {key!r} must be finite and non-negative")
    return value


def _int_option(method: NumericalMethod, key: str, low: int, high: int, *, required: bool = True) -> int | None:
    value = method.settings.options.get(key)
    if value is None and not required:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise NumericalRefusal(f"method {method.method!r} requires option {key!r} as an int in [{low}, {high}]")
    return value


def _float_option(method: NumericalMethod, key: str, low: float, high: float, *, required: bool = True,
                  open_low: bool = True, open_high: bool = True) -> float | None:
    value = method.settings.options.get(key)
    if value is None and not required:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise NumericalRefusal(f"method {method.method!r} requires option {key!r} as a finite number")
    v = float(value)
    if (v <= low if open_low else v < low) or (v >= high if open_high else v > high):
        raise NumericalRefusal(f"option {key!r} = {v!r} lies outside its admissible range")
    return v


class _Evaluation(Exception):
    """An arithmetic failure inside a caller's residual or Jacobian (classified NON_FINITE)."""


class DampedNewtonProvider(NumericalProvider):
    """Newton / Newton with Armijo backtracking on square NONLINEAR_ROOT problems (see the module docstring)."""

    identity = SolverIdentity("forge.numerical.newton", "1", backend="numpy.linalg.solve / scipy.sparse.linalg.spsolve")
    kinds = frozenset({ProblemKind.NONLINEAR_ROOT})
    methods = frozenset({"newton", "newton_armijo"})
    #: the declared scales define the acceptance measure itself
    acceptance_options = frozenset({"residual_scales"})

    # ---- configuration ---------------------------------------------------------------------

    def _configuration(self, method: NumericalMethod) -> dict[str, Any]:
        config: dict[str, Any] = {
            "residual_atol": _required_tolerance(method, "residual_atol"),
            "step_rtol": _required_tolerance(method, "step_rtol"),
            "max_iterations": _int_option(method, "max_iterations", 1, 10_000),
            "fd_step": _float_option(method, "finite_difference_step", 0.0, 1.0, required=False),
            "condition_limit": _float_option(method, "condition_limit", 1.0, math.inf, required=False),
            "history": HistoryPolicy(method.settings.options.get("divergence_factor"),
                                     method.settings.options.get("stagnation_iterations")),
        }
        scales = method.settings.options.get("residual_scales")
        config["scaling"] = ResidualScaling(None if scales is None else tuple(scales))
        if method.method == "newton_armijo":
            config["c1"] = _float_option(method, "armijo_c1", 0.0, 0.5)
            config["backtrack"] = _float_option(method, "backtrack_factor", 0.0, 1.0)
            config["max_backtracks"] = _int_option(method, "max_backtracks", 1, 60)
        return config

    # ---- evaluation ------------------------------------------------------------------------

    @staticmethod
    def _call(function: Callable[[np.ndarray], Any], x: np.ndarray) -> Any:
        try:
            with np.errstate(all="ignore"):
                return function(x.copy())
        except ArithmeticError as exc:  # ZeroDivisionError, OverflowError, FloatingPointError
            raise _Evaluation(f"{type(exc).__name__}: {exc}") from exc

    def _residual(self, f: Callable, x: np.ndarray, n: int) -> np.ndarray:
        value = np.asarray(self._call(f, x), dtype=float).reshape(-1)
        if value.size != n:
            raise NumericalRefusal(f"the residual has {value.size} components for {n} unknowns; Newton needs a square system")
        return value

    def _jacobian(self, f: Callable, jac: Callable | None, x: np.ndarray, fx: np.ndarray, fd_step: float | None) -> Any:
        n = x.size
        if jac is not None:
            value = self._call(jac, x)
            if is_sparse(value):
                matrix = canonical_csr(value, require_finite=False)
                if not np.all(np.isfinite(matrix.data)):
                    raise _Evaluation("the Jacobian has non-finite entries")
            else:
                matrix = np.asarray(value, dtype=float)
                if not np.all(np.isfinite(matrix)):
                    raise _Evaluation("the Jacobian has non-finite entries")
            if tuple(matrix.shape) != (n, n):
                raise NumericalRefusal(f"the Jacobian has shape {tuple(matrix.shape)}; expected ({n}, {n})")
            return matrix
        assert fd_step is not None
        matrix = np.empty((n, n))
        for j in range(n):
            h = fd_step * max(1.0, abs(float(x[j])))
            probe = x.copy()
            probe[j] += h
            column = (self._residual(f, probe, n) - fx) / (probe[j] - x[j])
            if not np.all(np.isfinite(column)):
                raise _Evaluation(f"a finite-difference Jacobian column ({j}) is not finite")
            matrix[:, j] = column
        return matrix

    @staticmethod
    def _solve(matrix: Any, rhs: np.ndarray) -> np.ndarray | None:
        if is_sparse(matrix):
            import scipy.sparse.linalg as spla

            with np.errstate(all="ignore"):
                try:
                    step = spla.spsolve(matrix.tocsc(), rhs)
                except RuntimeError:  # SuperLU: exactly singular
                    return None
        else:
            try:
                step = np.linalg.solve(matrix, rhs)
            except np.linalg.LinAlgError:
                return None
        step = np.asarray(step, dtype=float).reshape(-1)
        return step if np.all(np.isfinite(step)) else None

    # ---- execution -------------------------------------------------------------------------

    def _execute(self, problem: NumericalProblem, method: NumericalMethod) -> NumericalExecutionRecord:
        f = problem.operands.get("residual")
        if not callable(f):
            raise NumericalRefusal("a Newton solve requires a 'residual' callable")
        jac = problem.operands.get("jacobian")
        config = self._configuration(method)
        if not callable(jac):
            jac = None
            if config["fd_step"] is None:
                raise NumericalRefusal("no 'jacobian' operand: declare option 'finite_difference_step' to allow a "
                                       "finite-difference Jacobian; none is assumed")
        x = problem.unknowns.to_array(problem.initial).astype(float)
        n = x.size
        if n > DENSE_CONVERSION_LIMIT and jac is None:
            raise NumericalRefusal(f"a finite-difference Jacobian of {n} unknowns exceeds the dense limit {DENSE_CONVERSION_LIMIT}")
        scaling: ResidualScaling = config["scaling"]
        atol, step_rtol = config["residual_atol"], config["step_rtol"]
        weights = np.ones(n) if scaling.scales is None else 1.0 / np.asarray(scaling.scales)
        if scaling.scales is not None and len(scaling.scales) != n:
            raise NumericalRefusal(f"{len(scaling.scales)} residual scales declared for {n} residual components")

        history: list[float] = []
        lengths: list[float] = []
        evaluations = {"f": 0, "j": 0}
        notes = [RESIDUAL_IS_NOT_AN_ERROR_BOUND, f"acceptance measure: {scaling.label}",
                 "jacobian: declared operand" if jac is not None else
                 f"jacobian: forward finite differences, relative step {config['fd_step']:g}"]
        last_matrix: Any = None

        def diagnostics(failure: NumericalFailureClass | None, message: str) -> NumericalDiagnostics:
            condition = None
            if last_matrix is not None and (is_sparse(last_matrix) or n <= SPARSE_EXACT_CONDITION_LIMIT):
                condition = condition_of(last_matrix)
            return NumericalDiagnostics(
                residual_norm=history[-1] if history and math.isfinite(history[-1]) else None,
                residual_history=tuple(history), iterations=len(lengths), function_evaluations=evaluations["f"],
                jacobian_evaluations=evaluations["j"], condition=condition, termination_message=message,
                warnings=tuple(notes), failure_class=None if failure is None else failure.value,
                step_lengths=tuple(lengths),
            )

        def fail(state: ConvergenceState, failure: NumericalFailureClass, reason: str) -> NumericalExecutionRecord:
            return failed(problem, self.identity, method, state, diagnostics(failure, reason), reason)

        try:
            fx = self._residual(f, x, n)
            evaluations["f"] += 1
            measure = scaling.measure(fx)
            history.append(measure)
            if not math.isfinite(measure) or not np.all(np.isfinite(x)):
                return fail(ConvergenceState.DIVERGED, NumericalFailureClass.NON_FINITE, "the residual at the declared initial values is not finite")
            for _ in range(config["max_iterations"]):
                if measure <= atol:
                    break
                matrix = self._jacobian(f, jac, x, fx, config["fd_step"])
                evaluations["j"] += 1
                if jac is None:
                    evaluations["f"] += n
                last_matrix = matrix
                if config["condition_limit"] is not None:
                    estimate = condition_of(matrix, threshold=config["condition_limit"])
                    if estimate.condition_number is not None and estimate.condition_number > config["condition_limit"]:
                        return fail(ConvergenceState.FAILED, NumericalFailureClass.SINGULAR_JACOBIAN,
                                    f"Jacobian condition {estimate.condition_number:.3e} exceeds the declared limit "
                                    f"{config['condition_limit']:.3e} ({estimate.method})")
                step = self._solve(matrix, -fx)
                if step is None:
                    return fail(ConvergenceState.FAILED, NumericalFailureClass.SINGULAR_JACOBIAN,
                                "the Newton system J dx = -F could not be solved (singular or non-finite step)")
                alpha = 1.0
                trial = x + step
                f_trial = self._residual(f, trial, n)
                evaluations["f"] += 1
                if method.method == "newton_armijo":
                    phi0 = 0.5 * float(np.sum((weights * fx) ** 2))
                    accepted = False
                    for backtrack in range(config["max_backtracks"] + 1):
                        if np.all(np.isfinite(f_trial)):
                            phi = 0.5 * float(np.sum((weights * f_trial) ** 2))
                            if phi <= phi0 - 2.0 * config["c1"] * alpha * phi0:
                                accepted = True
                                break
                        if backtrack == config["max_backtracks"]:
                            break
                        alpha *= config["backtrack"]
                        trial = x + alpha * step
                        f_trial = self._residual(f, trial, n)
                        evaluations["f"] += 1
                    if not accepted:
                        return fail(ConvergenceState.NOT_CONVERGED, NumericalFailureClass.LINE_SEARCH_FAILED,
                                    f"no step length down to {alpha:.3g} met the Armijo condition "
                                    f"(c1 = {config['c1']:g}) in {config['max_backtracks']} backtracks")
                elif not np.all(np.isfinite(f_trial)):
                    return fail(ConvergenceState.DIVERGED, NumericalFailureClass.NON_FINITE,
                                "the full Newton step reached a point where the residual is not finite")
                taken = alpha * step
                x, fx = trial, f_trial
                lengths.append(alpha)
                measure = scaling.measure(fx)
                history.append(measure)
                failure, why = classify_history(history, config["history"])
                if failure is not None:
                    state = ConvergenceState.DIVERGED if failure in (NumericalFailureClass.DIVERGING,
                                                                     NumericalFailureClass.NON_FINITE) else ConvergenceState.NOT_CONVERGED
                    return fail(state, failure, why)
                if measure > atol and float(np.max(np.abs(taken))) <= step_rtol * (1.0 + float(np.max(np.abs(x)))):
                    return fail(ConvergenceState.NOT_CONVERGED, NumericalFailureClass.STEP_STAGNATION,
                                f"the step fell below step_rtol {step_rtol:g} while the residual measure {measure:.3e} "
                                f"exceeds residual_atol {atol:g}")
        except _Evaluation as exc:
            return fail(ConvergenceState.DIVERGED, NumericalFailureClass.NON_FINITE, f"evaluation failed: {exc}")
        if measure > atol:
            return fail(ConvergenceState.MAX_ITERATIONS, NumericalFailureClass.ITERATION_LIMIT,
                        f"{config['max_iterations']} iterations spent; residual measure {measure:.3e} > residual_atol {atol:g}")
        d = diagnostics(None, f"residual measure {measure:.3e} <= residual_atol {atol:g} after {len(lengths)} iteration(s)")
        d = NumericalDiagnostics(**{**d.__dict__, "health": health_of(x)})
        if not np.all(np.isfinite(x)):  # pragma: no cover - guarded above
            return fail(ConvergenceState.FAILED, NumericalFailureClass.NON_FINITE, "non-finite solution")
        return NumericalExecutionRecord(problem.digest, problem.identity(), self.identity, method, ConvergenceState.CONVERGED,
                                        problem.unknowns.from_array(x), d)


def acceptance_measure(problem: NumericalProblem, record: NumericalExecutionRecord, scaling: ResidualScaling) -> float:
    """The declared residual measure of ``problem`` at ``record``'s outputs (re-evaluated, never read from the record)."""
    if problem.kind is not ProblemKind.NONLINEAR_ROOT or not callable(problem.operands.get("residual")):
        raise NumericalRefusal("an acceptance measure is defined for NONLINEAR_ROOT problems with a residual callable")
    if not record.succeeded or record.problem_digest != problem.digest:
        raise NumericalRefusal("acceptance is re-checked only on a successful execution of this exact problem")
    x = problem.unknowns.to_array(record.outputs)
    with np.errstate(all="ignore"):
        try:
            value = np.asarray(problem.operands["residual"](x.copy()), dtype=float).reshape(-1)
        except ArithmeticError:
            return math.inf
    return scaling.measure(value)


__all__ = ["DampedNewtonProvider", "acceptance_measure"]
