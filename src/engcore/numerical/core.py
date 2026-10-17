"""Provider-neutral numerical execution contracts (BIG 6).

Layering: this sits *beneath* the Scientific Core's problem-level solvers
(``ScientificSolver`` -> ``RawSolverOutput`` -> admission -> ``ScientificResult``).
It reuses the Core's numerical vocabulary rather than duplicating it:

* provider identity  -> :class:`~engcore.scientific.solvers.protocol.SolverIdentity`
* tolerances/options -> :class:`~engcore.scientific.solvers.protocol.SolverSettings`
* termination        -> :class:`~engcore.scientific.solvers.protocol.ConvergenceState`
* value health       -> :class:`~engcore.scientific.numerics.health.NumericHealth`
* conditioning       -> :class:`~engcore.scientific.numerics.conditioning.ConditionEstimate`
* admission          -> :func:`~engcore.scientific.solvers.admission.require_finite`

and bridges into the Core with :func:`to_raw_solver_output`.

Authority: a provider computes.  It never decides applicability, physical
validity, validation, evidence sufficiency or whether UNKNOWN becomes known.
``CONVERGED`` means numerical termination criteria were met -- nothing more.
A non-converged solve exposes no outputs: the last iterate is withheld, never
returned as a result.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import math
import re
from typing import Any, Callable, Mapping

import numpy as np

from ..scenarios.timeline import TimeWindow, canonical_digest
from ..scientific.errors import InvalidScientificProblem
from ..scientific.numerics.conditioning import ConditionEstimate, classify_condition_number
from ..scientific.numerics.health import NumericHealth, assess_numeric_values
from ..scientific.solvers.protocol import ConvergenceState, RawSolverOutput, SolverIdentity, SolverSettings
from ..scientific.units.quantity import Quantity, normalize_unit

_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]*$")


class NumericalRefusal(InvalidScientificProblem):
    """A numerical problem that cannot be executed as posed."""


class ProviderUnavailable(NumericalRefusal):
    """The provider's backend is not installed in this environment."""


def _identifier(value: object, label: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text or not _ID.fullmatch(text):
        raise NumericalRefusal(f"{label} must be a non-empty typed identifier")
    return text


# --------------------------------------------------------------------------
# Unit / scaling boundary
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class VariableSpec:
    """One named block of a numerical vector: its unit, scale and length.

    numeric = quantity.magnitude_in(unit) / scale ; quantity = numeric * scale [unit]
    Affine units (degC) are refused: an array of affine coordinates cannot be
    scaled or differenced without ambiguity.  Use kelvin.
    """

    name: str
    unit: str
    scale: float = 1.0
    size: int = 1

    def __post_init__(self) -> None:
        from ..scientific.units.quantity import is_ratio_scale

        object.__setattr__(self, "name", _identifier(self.name, "variable name"))
        unit = normalize_unit(self.unit)
        if not is_ratio_scale(unit):
            raise NumericalRefusal(f"variable {self.name!r} uses affine unit {unit!r}; normalize to a ratio scale first")
        object.__setattr__(self, "unit", unit)
        scale = float(self.scale)
        if not math.isfinite(scale) or scale <= 0:
            raise NumericalRefusal(f"variable {self.name!r} scale must be finite and positive")
        object.__setattr__(self, "scale", scale)
        if isinstance(self.size, bool) or not isinstance(self.size, int) or self.size < 1:
            raise NumericalRefusal(f"variable {self.name!r} size must be a positive integer")

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "unit": self.unit, "scale": self.scale, "size": self.size}


@dataclass(frozen=True)
class UnitBoundary:
    """The exact map between named unit-bearing quantities and one flat array."""

    variables: tuple[VariableSpec, ...]

    def __post_init__(self) -> None:
        items = tuple(self.variables)
        if not items or any(not isinstance(v, VariableSpec) for v in items) or len({v.name for v in items}) != len(items):
            raise NumericalRefusal("unit boundary requires unique VariableSpec entries")
        object.__setattr__(self, "variables", items)

    @property
    def size(self) -> int:
        return sum(v.size for v in self.variables)

    def to_array(self, values: Mapping[str, Any]) -> np.ndarray:
        names = {v.name for v in self.variables}
        if set(values) != names:
            raise NumericalRefusal(f"boundary needs exactly {sorted(names)}; got {sorted(values)}")
        out: list[float] = []
        for v in self.variables:
            raw = values[v.name]
            items = tuple(raw) if isinstance(raw, (tuple, list)) else (raw,)
            if len(items) != v.size:
                raise NumericalRefusal(f"variable {v.name!r} expects {v.size} value(s), got {len(items)}")
            for q in items:
                if not isinstance(q, Quantity):
                    raise NumericalRefusal(f"variable {v.name!r} must be given as Quantity records, not bare numbers")
                q.require_compatible(v.unit, context=f"numerical variable {v.name!r}")
                out.append(q.magnitude_in(v.unit) / v.scale)
        return np.asarray(out, dtype=float)

    def from_array(self, array: np.ndarray) -> dict[str, Quantity | tuple[Quantity, ...]]:
        flat = np.asarray(array, dtype=float).reshape(-1)
        if flat.size != self.size:
            raise NumericalRefusal(f"array has {flat.size} entries; boundary maps {self.size}")
        if not np.all(np.isfinite(flat)):
            raise NumericalRefusal("array contains non-finite entries; it cannot be mapped back to quantities")
        result: dict[str, Any] = {}
        i = 0
        for v in self.variables:
            block = tuple(Quantity(float(x) * v.scale, v.unit) for x in flat[i:i + v.size])
            result[v.name] = block[0] if v.size == 1 else block
            i += v.size
        return result

    def to_dict(self) -> list[dict[str, Any]]:
        return [v.to_dict() for v in self.variables]


# --------------------------------------------------------------------------
# Problem identity
# --------------------------------------------------------------------------


class ProblemKind(str, Enum):
    LINEAR = "linear"
    NONLINEAR_ROOT = "nonlinear_root"
    OPTIMIZATION = "optimization"
    QUADRATURE = "quadrature"
    ODE_IVP = "ode_ivp"
    DAE = "dae"


@dataclass(frozen=True)
class OperatorIdentity:
    """Identity of the equations/operator.

    For array operands the digest is computed from the arrays.  For callables
    it is DECLARED by the caller (or derived from a SymPy expression): Forge
    cannot hash arbitrary code, so a declared digest is an ATTESTATION, not a
    proof -- two different callables under one declared digest are not
    distinguishable.  That limit is stated, not hidden.
    """

    operator_id: str
    version: str
    definition_digest: str
    derivation: str  # "array_bytes" | "symbolic_srepr" | "declared"

    def __post_init__(self) -> None:
        object.__setattr__(self, "operator_id", _identifier(self.operator_id, "operator_id"))
        if not str(self.version).strip():
            raise NumericalRefusal("operator identity requires a version")
        d = str(self.definition_digest).strip().lower()
        if len(d) != 64 or any(c not in "0123456789abcdef" for c in d):
            raise NumericalRefusal("operator definition_digest must be sha256 hex")
        object.__setattr__(self, "definition_digest", d)
        if self.derivation not in ("array_bytes", "symbolic_srepr", "declared"):
            raise NumericalRefusal("operator derivation must be array_bytes, symbolic_srepr or declared")

    def to_dict(self) -> dict[str, Any]:
        return {"operator_id": self.operator_id, "version": self.version, "definition_digest": self.definition_digest, "derivation": self.derivation}


#: Phase 1 BR6 -- the bounded dense conversions this module may make of a SPARSE
#: operand.  A dense operand is already dense; these bound only conversions the
#: caller did not ask for.  An exact 2-norm condition number of a sparse matrix
#: is computed by densifying it only up to this dimension (8 MiB of float64).
SPARSE_EXACT_CONDITION_LIMIT = 1000
#: A sparse 1-norm condition ESTIMATE factorizes the matrix once (sparse LU);
#: above this many stored entries it is not attempted and conditioning is
#: reported unresolved.
SPARSE_ESTIMATE_NNZ_LIMIT = 5_000_000
#: A provider whose method is dense (``dense_lu``) densifies a sparse operand
#: only up to this dimension (128 MiB of float64); above it the problem is refused.
DENSE_CONVERSION_LIMIT = 4096


def is_sparse(a: Any) -> bool:
    """A SciPy sparse matrix or array (duck-typed: it converts to CSR and counts stored entries)."""
    return hasattr(a, "tocsr") and hasattr(a, "nnz")


def canonical_csr(a: Any, *, require_finite: bool = True) -> Any:
    """A validated canonical CSR COPY of a sparse operand; the caller's matrix is never modified.

    Validation reads the STORED entries only -- nothing is densified.  The
    structure is checked in full (index ranges, ``indptr`` monotonicity), the
    dtype must be real numeric, duplicates are summed and indices sorted (so
    one operator has one identity whatever its storage order), and every
    stored value must be finite.  Explicit zeros are kept: they are part of the
    declared structure.
    """
    try:
        csr = a.tocsr(copy=True)
    except TypeError:
        csr = a.tocsr().copy()
    try:
        csr.check_format(full_check=True)
    except ValueError as exc:
        raise NumericalRefusal(f"sparse operand has an invalid structure: {exc}") from exc
    dtype = csr.data.dtype
    if dtype == np.bool_ or not np.issubdtype(dtype, np.number) or np.issubdtype(dtype, np.complexfloating):
        raise NumericalRefusal(f"sparse operand must be real numeric, got dtype {dtype}")
    csr.sum_duplicates()
    if require_finite and not np.all(np.isfinite(csr.data)):
        bad = int(np.count_nonzero(~np.isfinite(csr.data)))
        raise NumericalRefusal(f"sparse operand stores {bad} non-finite entr{'y' if bad == 1 else 'ies'}")
    return csr


def bounded_dense(a: Any, *, limit: int, purpose: str) -> np.ndarray:
    """``a`` as a dense float array; a sparse operand is converted only up to ``limit`` x ``limit``."""
    if not is_sparse(a):
        return np.asarray(a, dtype=float)
    rows, cols = a.shape
    if max(rows, cols) > limit:
        raise NumericalRefusal(
            f"{purpose} would densify a {rows}x{cols} sparse operand ({8 * rows * cols / 2**20:.0f} MiB); "
            f"the dense conversion limit is {limit}. Use a sparse method."
        )
    return canonical_csr(a).toarray().astype(float, copy=False)


def array_digest(*arrays: Any) -> str:
    h = hashlib.sha256()
    for a in arrays:
        if is_sparse(a):
            # canonical: an already canonical CSR hashes exactly as before
            a = canonical_csr(a)
            for part in (a.data, a.indices, a.indptr):
                arr = np.ascontiguousarray(part)
                h.update(str(arr.dtype).encode() + str(arr.shape).encode() + arr.tobytes())
            h.update(str(a.shape).encode())
            continue
        arr = np.ascontiguousarray(np.asarray(a, dtype=float))
        h.update(str(arr.shape).encode() + arr.tobytes())
    return h.hexdigest()


@dataclass(frozen=True)
class NumericalProblem:
    """A normalized numerical problem.  Arrays are owned here, behind the boundary.

    ``operands`` holds kind-specific data (matrix/rhs for LINEAR; residual/
    jacobian callables for NONLINEAR_ROOT; rhs for ODE_IVP; objective for
    OPTIMIZATION).  ``initial`` is required where the kind needs it.
    ``window`` (ODE) is a BIG 2 TimeWindow: the integrator steps inside it and
    owns no timeline; ``breakpoints`` are declared discontinuities it must stop at.
    """

    problem_id: str
    kind: ProblemKind
    operator: OperatorIdentity
    unknowns: UnitBoundary
    operands: Mapping[str, Any] = field(default_factory=dict)
    initial: Mapping[str, Any] | None = None
    parameters: Mapping[str, Quantity] = field(default_factory=dict)
    window: TimeWindow | None = None
    breakpoints: tuple[Quantity, ...] = ()
    output_times: tuple[Quantity, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "problem_id", _identifier(self.problem_id, "problem_id"))
        object.__setattr__(self, "kind", ProblemKind(self.kind))
        if not isinstance(self.operator, OperatorIdentity) or not isinstance(self.unknowns, UnitBoundary):
            raise NumericalRefusal("problem requires OperatorIdentity and UnitBoundary")
        for key, value in dict(self.parameters).items():
            if not isinstance(value, Quantity):
                raise NumericalRefusal(f"parameter {key!r} must be a Quantity")
        needs_initial = self.kind in (ProblemKind.NONLINEAR_ROOT, ProblemKind.OPTIMIZATION, ProblemKind.ODE_IVP, ProblemKind.DAE)
        if needs_initial and self.initial is None:
            raise NumericalRefusal(f"{self.kind.value} problem requires explicit initial values; none are assumed")
        if self.initial is not None:
            self.unknowns.to_array(self.initial)  # shape/unit check now, not inside a provider
        if self.kind in (ProblemKind.ODE_IVP, ProblemKind.DAE):
            if not isinstance(self.window, TimeWindow):
                raise NumericalRefusal("time integration requires an authorized BIG 2 TimeWindow")
            for t in self.output_times:
                if t.to("s").magnitude <= float(self.window.start.seconds):
                    raise NumericalRefusal("output times must lie strictly after the window start; the initial state is an input, not an output")
            for t in tuple(self.breakpoints) + tuple(self.output_times):
                from ..scenarios.timeline import TimePoint
                if not self.window.contains(TimePoint(self.window.basis_id, t)) and t.to("s").magnitude != float(self.window.end.seconds):
                    raise NumericalRefusal("breakpoints and output times must lie inside the authorized window")
        if self.kind is ProblemKind.LINEAR:
            a, b = self.operands.get("matrix"), self.operands.get("rhs")
            if a is None or b is None:
                raise NumericalRefusal("linear problem requires 'matrix' and 'rhs'")
            n = self.unknowns.size
            if is_sparse(b):
                raise NumericalRefusal("linear 'rhs' must be a dense vector, not a sparse matrix")
            try:
                rhs = np.asarray(b, dtype=float).reshape(-1)
                # Phase 1 BR6: a sparse matrix is validated on its stored
                # entries and never densified here
                matrix = a if is_sparse(a) else np.asarray(a, dtype=float)
            except (TypeError, ValueError) as exc:
                raise NumericalRefusal(f"linear operands are not numeric arrays: {exc}") from exc
            if tuple(matrix.shape) != (n, n) or rhs.size != n:
                raise NumericalRefusal(f"linear operand shapes {tuple(matrix.shape)} / {np.asarray(b).shape} do not match {n} unknowns")
            if is_sparse(matrix):
                # structure and dtype refused here; finiteness of the stored entries below
                finite_matrix = bool(np.all(np.isfinite(canonical_csr(matrix, require_finite=False).data)))
            else:
                finite_matrix = bool(np.all(np.isfinite(matrix)))
            if not finite_matrix or not np.all(np.isfinite(rhs)):
                raise NumericalRefusal("linear operands contain non-finite values")
            if self.operator.derivation == "array_bytes" and self.operator.definition_digest != array_digest(a, b):
                raise NumericalRefusal("operator digest does not match the matrix/rhs it names")

    def identity(self) -> dict[str, Any]:
        return {
            "problem_id": self.problem_id, "kind": self.kind.value, "operator": self.operator.to_dict(),
            # Array operands are ALWAYS hashed into identity, whatever the operator
            # declares: Forge holds the arrays, so their identity is proven, not attested.
            "operand_digest": array_digest(self.operands["matrix"], self.operands["rhs"]) if self.kind is ProblemKind.LINEAR else None,
            "unknowns": self.unknowns.to_dict(),
            "initial": None if self.initial is None else self.unknowns.to_array(self.initial).tolist(),
            "parameters": {k: v.to_dict() for k, v in sorted(dict(self.parameters).items())},
            "window": None if self.window is None else self.window.to_dict(),
            "breakpoints": [b.to_dict() for b in self.breakpoints],
            "output_times": [t.to_dict() for t in self.output_times],
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.identity())


# --------------------------------------------------------------------------
# Method, diagnostics, execution record
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class NumericalMethod:
    """Algorithm + settings.  Reuses the Core's validated ``SolverSettings``."""

    method: str
    settings: SolverSettings = field(default_factory=SolverSettings)
    required_tolerances: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "method", _identifier(self.method, "method"))
        if not isinstance(self.settings, SolverSettings):
            raise NumericalRefusal("method settings must be SolverSettings")
        missing = [k for k in self.required_tolerances if k not in self.settings.tolerances]
        if missing:
            raise NumericalRefusal(f"method {self.method!r} requires explicit tolerances {missing}; none are defaulted")

    def to_dict(self) -> dict[str, Any]:
        return {"method": self.method, "settings": self.settings.to_dict()}


@dataclass(frozen=True)
class NumericalDiagnostics:
    residual_norm: float | None = None
    residual_history: tuple[float, ...] = ()
    iterations: int | None = None
    objective_value: float | None = None
    function_evaluations: int | None = None
    jacobian_evaluations: int | None = None
    accepted_steps: int | None = None
    rejected_steps: int | None = None
    error_estimate: float | None = None
    condition: ConditionEstimate | None = None
    health: NumericHealth | None = None
    termination_message: str = ""
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "residual_norm": self.residual_norm, "residual_history": list(self.residual_history),
            "iterations": self.iterations, "objective_value": self.objective_value, "function_evaluations": self.function_evaluations,
            "jacobian_evaluations": self.jacobian_evaluations, "accepted_steps": self.accepted_steps,
            "rejected_steps": self.rejected_steps, "error_estimate": self.error_estimate,
            "condition": None if self.condition is None else {"condition_number": self.condition.condition_number, "status": self.condition.status.value, "method": self.condition.method, "threshold": self.condition.threshold},
            "health": None if self.health is None else {"status": self.health.status.value, "nonfinite_count": self.health.nonfinite_count},
            "termination_message": self.termination_message, "warnings": list(self.warnings),
        }


_SUCCESS = (ConvergenceState.CONVERGED, ConvergenceState.NOT_APPLICABLE)


@dataclass(frozen=True)
class NumericalExecutionRecord:
    """One numerical execution: exactly what was solved, by whom, how, and what came out.

    ``outputs`` exist only for CONVERGED / NOT_APPLICABLE executions.  For
    ODE problems ``trajectory`` holds the declared output times.
    """

    problem_digest: str
    problem_identity: Mapping[str, Any]
    provider: SolverIdentity
    method: NumericalMethod
    convergence: ConvergenceState
    outputs: Mapping[str, Any]
    diagnostics: NumericalDiagnostics
    trajectory: tuple[tuple[Quantity, Mapping[str, Any]], ...] = ()
    determinism: str = "not_bitwise_guaranteed"
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "convergence", ConvergenceState(self.convergence))
        if self.convergence not in _SUCCESS and (self.outputs or self.trajectory):
            raise NumericalRefusal("a non-converged execution exposes no outputs; the last iterate is withheld")
        if self.convergence in _SUCCESS and not self.outputs:
            raise NumericalRefusal("a successful execution must map its result back to quantities")
        if self.determinism not in ("bitwise_for_same_platform", "not_bitwise_guaranteed"):
            raise NumericalRefusal("unsupported determinism statement")

    @property
    def succeeded(self) -> bool:
        return self.convergence in _SUCCESS

    @property
    def execution_identity(self) -> str:
        """Everything that decides WHAT was executed: problem, provider, method, settings."""
        return canonical_digest({"problem": self.problem_digest, "provider": self.provider.to_dict(), "method": self.method.to_dict()})

    def _values(self, mapping: Mapping[str, Any]) -> dict[str, Any]:
        out = {}
        for k, v in sorted(mapping.items()):
            out[k] = [q.to_dict() for q in v] if isinstance(v, tuple) else v.to_dict()
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification": "numerical_execution_not_scientific_evidence",
            "execution_identity": self.execution_identity, "problem_digest": self.problem_digest,
            "problem": dict(self.problem_identity), "provider": self.provider.to_dict(), "method": self.method.to_dict(),
            "convergence": self.convergence.value, "outputs": self._values(self.outputs),
            "trajectory": [[t.to_dict(), self._values(v)] for t, v in self.trajectory],
            "diagnostics": self.diagnostics.to_dict(), "determinism": self.determinism, "reason": self.reason,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())


def failed(problem: NumericalProblem, provider: SolverIdentity, method: NumericalMethod, state: ConvergenceState,
           diagnostics: NumericalDiagnostics, reason: str) -> NumericalExecutionRecord:
    return NumericalExecutionRecord(problem.digest, problem.identity(), provider, method, state, {}, diagnostics, (), reason=reason)


class NumericalProvider(ABC):
    """A numerical backend.  It computes; it holds no scientific authority."""

    identity: SolverIdentity
    kinds: frozenset[ProblemKind]
    methods: frozenset[str]
    #: why the backend is unavailable, as observed (an import error's type and text);
    #: carried into the refusal so a broken install is not reported as an absent one
    unavailable_reason: str = "backend is not installed"

    def available(self) -> bool:
        return True

    def execute(self, problem: NumericalProblem, method: NumericalMethod) -> NumericalExecutionRecord:
        if not isinstance(problem, NumericalProblem) or not isinstance(method, NumericalMethod):
            raise NumericalRefusal("execute requires a NumericalProblem and NumericalMethod")
        if not self.available():
            raise ProviderUnavailable(f"provider {self.identity.solver_id!r} is unavailable: {self.unavailable_reason}")
        if problem.kind not in self.kinds:
            raise NumericalRefusal(f"provider {self.identity.solver_id!r} does not support {problem.kind.value} problems")
        if method.method not in self.methods:
            raise NumericalRefusal(f"provider {self.identity.solver_id!r} does not implement method {method.method!r}")
        return self._execute(problem, method)

    @abstractmethod
    def _execute(self, problem: NumericalProblem, method: NumericalMethod) -> NumericalExecutionRecord: ...


# --------------------------------------------------------------------------
# Agreement, bridge
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class NumericalAgreement:
    """Agreement of two executions of the SAME problem.  Never validation."""

    agree: bool
    max_abs_difference: Mapping[str, float]
    rtol: float
    atol: float
    comparison: str = "allclose(rtol, atol) in each variable's boundary unit"

    def to_dict(self) -> dict[str, Any]:
        return {"classification": "numerical_agreement_not_validation", "agree": self.agree, "max_abs_difference": dict(self.max_abs_difference), "rtol": self.rtol, "atol": self.atol, "comparison": self.comparison}


def compare_executions(a: NumericalExecutionRecord, b: NumericalExecutionRecord, *, rtol: float, atol: float) -> NumericalAgreement:
    if a.problem_digest != b.problem_digest:
        raise NumericalRefusal("agreement is only defined between executions of the same problem")
    if not (a.succeeded and b.succeeded):
        raise NumericalRefusal("a failed execution has no outputs to compare")
    if set(a.outputs) != set(b.outputs):
        raise NumericalRefusal("executions expose different outputs; they are not comparable")
    if [t.magnitude for t, _ in a.trajectory] != [t.magnitude for t, _ in b.trajectory]:
        raise NumericalRefusal("executions report trajectories at different times; they are not comparable")
    diffs: dict[str, float] = {}
    ok = True
    pairs = [(a.outputs, b.outputs, "")] + [(ya, yb, f"@{t.magnitude}s") for (t, ya), (_, yb) in zip(a.trajectory, b.trajectory)]
    for oa, ob, suffix in pairs:
        for key in sorted(oa):
            xa = oa[key] if isinstance(oa[key], tuple) else (oa[key],)
            xb = ob[key] if isinstance(ob[key], tuple) else (ob[key],)
            unit = xa[0].units
            va = np.array([q.magnitude_in(unit) for q in xa])
            vb = np.array([q.magnitude_in(unit) for q in xb])
            diffs[key + suffix] = float(np.max(np.abs(va - vb)))
            ok = ok and bool(np.allclose(va, vb, rtol=rtol, atol=atol))
    return NumericalAgreement(ok, diffs, float(rtol), float(atol))
    for key in sorted(a.outputs):
        xa = a.outputs[key] if isinstance(a.outputs[key], tuple) else (a.outputs[key],)
        xb = b.outputs[key] if isinstance(b.outputs[key], tuple) else (b.outputs[key],)
        unit = xa[0].units
        va = np.array([q.magnitude_in(unit) for q in xa])
        vb = np.array([q.magnitude_in(unit) for q in xb])
        diffs[key] = float(np.max(np.abs(va - vb)))
        ok = ok and bool(np.allclose(va, vb, rtol=rtol, atol=atol))
    return NumericalAgreement(ok, diffs, float(rtol), float(atol))


def to_raw_solver_output(record: NumericalExecutionRecord, unit_of: Mapping[str, str]) -> RawSolverOutput:
    """Bridge into the Core solver pipeline (admission -> ScientificResult).

    ``unit_of`` states the unit each scalar output is written in, so the bare
    numbers RawSolverOutput carries stay attributable.
    """
    values: dict[str, float] = {}
    if record.succeeded:
        for key, v in record.outputs.items():
            if isinstance(v, tuple):
                for i, q in enumerate(v):
                    values[f"{key}[{i}]"] = q.magnitude_in(unit_of[key])
            else:
                values[key] = v.magnitude_in(unit_of[key])
    d = record.diagnostics
    residuals = {} if d.residual_norm is None else {"residual_norm": d.residual_norm}
    return RawSolverOutput(
        record.convergence, values, residuals if record.succeeded or d.residual_norm is None or math.isfinite(d.residual_norm) else {},
        d.iterations, None, tuple(d.warnings),
        {"numerical_execution_identity": record.execution_identity, "numerical_execution_digest": record.digest, "units": dict(unit_of),
         "reason": record.reason, "termination_message": d.termination_message,
         "classification": "numerical_execution_not_scientific_evidence"},
    )


def health_of(values: np.ndarray) -> NumericHealth:
    return assess_numeric_values(tuple(float(x) for x in np.asarray(values).reshape(-1)))


def _exact_condition(dense: np.ndarray, threshold: float = 1e12) -> ConditionEstimate:
    try:
        c = float(np.linalg.cond(dense))
    except np.linalg.LinAlgError:
        c = math.inf
    if math.isnan(c):
        c = math.inf
    return classify_condition_number(max(c, 1.0), method="numpy.linalg.cond (2-norm)", threshold=threshold)


def _inverse_one_norm_lower_bound(solve: Callable[[np.ndarray], np.ndarray],
                                  solve_transpose: Callable[[np.ndarray], np.ndarray], n: int) -> float:
    """Hager's estimator with Higham's safeguard (LAPACK xLACON): a deterministic lower bound on ||A^-1||_1.

    Deterministic by construction (no random starting vectors), so the
    estimate is part of a reproducible execution record.
    """
    x = np.full(n, 1.0 / n)
    estimate = 0.0
    for step in range(5):
        y = solve(x)
        current = float(np.sum(np.abs(y)))
        if step > 0 and current <= estimate:
            break
        estimate = current
        z = solve_transpose(np.where(y >= 0.0, 1.0, -1.0))
        j = int(np.argmax(np.abs(z)))
        if step > 0 and abs(float(z[j])) <= float(z @ x):
            break
        x = np.zeros(n)
        x[j] = 1.0
    alternating = np.array([(-1.0) ** i * (1.0 + i / max(n - 1, 1)) for i in range(n)])
    return max(estimate, 2.0 * float(np.sum(np.abs(solve(alternating)))) / (3.0 * n))


def _estimated_condition(csr: Any, threshold: float) -> ConditionEstimate:
    if csr.nnz > SPARSE_ESTIMATE_NNZ_LIMIT:
        return classify_condition_number(None, method=(
            f"not estimated: {csr.nnz} stored entries exceed the factorization policy "
            f"({SPARSE_ESTIMATE_NNZ_LIMIT}); conditioning unresolved"), threshold=threshold)
    import scipy.sparse.linalg as spla

    try:
        lu = spla.splu(csr.tocsc().astype(np.float64))
    except RuntimeError:
        return classify_condition_number(math.inf, method="sparse LU (SuperLU) found the matrix exactly singular",
                                         threshold=threshold)
    except MemoryError:
        return classify_condition_number(None, method="not estimated: the sparse LU factorization ran out of memory",
                                         threshold=threshold)
    norm = float(np.max(np.asarray(abs(csr).sum(axis=0)).reshape(-1)))
    estimate = norm * _inverse_one_norm_lower_bound(lu.solve, lambda v: lu.solve(v, trans="T"), csr.shape[0])
    method = (f"ESTIMATED 1-norm condition lower bound {estimate:.6e} (exact ||A||_1 x Hager/Higham estimate of "
              f"||A^-1||_1 on a SuperLU factorization)")
    if not math.isfinite(estimate):
        return classify_condition_number(math.inf, method=method + "; the estimate overflowed", threshold=threshold)
    if estimate > threshold:
        return classify_condition_number(max(estimate, 1.0), threshold=threshold, method=(
            method + "; a lower bound above the threshold: the matrix is at least this ill-conditioned"))
    return classify_condition_number(None, threshold=threshold, method=(
        method + "; a lower bound below the threshold does not establish good conditioning: unresolved"))


def condition_of(matrix: Any, *, allow_factorization: bool = True, threshold: float = 1e12) -> ConditionEstimate:
    """The condition of a linear operator, stating whether it is exact or estimated (Phase 1 BR6).

    * a dense matrix: exact 2-norm condition number (``numpy.linalg.cond``);
    * a sparse matrix up to :data:`SPARSE_EXACT_CONDITION_LIMIT`: the same
      exact number after a BOUNDED dense conversion;
    * a larger sparse matrix: a deterministic 1-norm LOWER-BOUND estimate from
      one sparse LU (when ``allow_factorization``).  A lower bound above the
      threshold proves ill-conditioning; one below it proves nothing and is
      reported unresolved, never well-conditioned;
    * otherwise unresolved.  Never an uncontrolled dense conversion.
    """
    if not is_sparse(matrix):
        return _exact_condition(np.asarray(matrix, dtype=float), threshold)
    csr = canonical_csr(matrix)
    rows, cols = csr.shape
    if rows != cols:
        return classify_condition_number(None, method="not square: no condition number", threshold=threshold)
    if rows <= SPARSE_EXACT_CONDITION_LIMIT:
        return _exact_condition(csr.toarray().astype(float, copy=False), threshold)
    if not allow_factorization:
        return classify_condition_number(None, threshold=threshold, method=(
            f"not estimated: a {rows}x{cols} sparse operator under an iterative method; estimating its "
            f"condition would need the factorization the method avoids"))
    return _estimated_condition(csr, threshold)
