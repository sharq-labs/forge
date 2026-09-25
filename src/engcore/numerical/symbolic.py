"""SymPy-backed symbolic operators: equations, exact Jacobians, derived identity.

Symbolic manipulation is a mathematical convenience, never scientific
evidence.  Its value here is architectural: the operator identity is the
digest of the canonical expression (``srepr``), so the same equations give
the same identity and an edited equation gives a different one -- unlike an
opaque Python callable, whose identity can only be declared.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from .core import NumericalRefusal, OperatorIdentity, ProviderUnavailable


def _sympy():
    try:
        import sympy
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ProviderUnavailable("SymPy is not installed; install the 'symbolic' extra") from exc
    return sympy


@dataclass(frozen=True)
class SymbolicSystem:
    """F(x) = 0 with symbols ``variables`` (in normalized units) and residual ``expressions``."""

    operator_id: str
    variables: tuple[str, ...]
    expressions: tuple[str, ...]
    version: str = "1"

    def __post_init__(self) -> None:
        if not self.variables or len(self.variables) != len(self.expressions):
            raise NumericalRefusal("symbolic system needs one residual expression per unknown")

    def _parsed(self):
        sp = _sympy()
        syms = sp.symbols(self.variables)
        syms = syms if isinstance(syms, tuple) else (syms,)
        local = {name: s for name, s in zip(self.variables, syms)}
        exprs = [sp.sympify(e, locals=local) for e in self.expressions]
        stray = set().union(*(e.free_symbols for e in exprs)) - set(syms)
        if stray:
            raise NumericalRefusal(f"symbolic residual uses undeclared symbols {sorted(map(str, stray))}")
        return sp, syms, exprs

    def identity(self) -> OperatorIdentity:
        sp, syms, exprs = self._parsed()
        canonical = sp.srepr((tuple(syms), tuple(exprs)))
        return OperatorIdentity(self.operator_id, self.version, hashlib.sha256(canonical.encode()).hexdigest(), "symbolic_srepr")

    def callables(self) -> tuple[Callable[[Any], Any], Callable[[Any], Any]]:
        sp, syms, exprs = self._parsed()
        jac = sp.Matrix(exprs).jacobian(sp.Matrix(syms))
        f = sp.lambdify([syms], exprs, "numpy")
        j = sp.lambdify([syms], jac, "numpy")
        return (lambda x: np.asarray(f(tuple(x)), dtype=float).reshape(-1),
                lambda x: np.asarray(j(tuple(x)), dtype=float))
