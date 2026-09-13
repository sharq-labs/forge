"""The universal solver contract.

Four things are deliberately distinct types, because collapsing them is how
scientific provenance gets lost:

1. :class:`~engcore.scientific.ir.problem.ScientificProblem` — what is asked.
2. :class:`PreparedSolve`   — solver-specific state derived from the problem
   (discretization, assembled system, chosen settings).
3. :class:`RawSolverOutput` — what the numerical backend actually returned,
   including convergence detail, before any scientific interpretation.
4. ``ScientificResult``     — the interpreted, unit-carrying, validated,
   provenance-bearing record (see ``..results``).

No backend adapter (SciPy, Cantera, OpenFOAM, FEniCSx, ngspice) is
implemented here — only the contract they will satisfy.
"""

from __future__ import annotations

import math
import numbers
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol, runtime_checkable

from ..errors import ScientificCoreError
from ..results.data_reference import ScientificDataReference
from ..results.immutable import detach, freeze
from ..serialization import (
    require_schema,
    require_schema_any,
    schema_string,
    unwritable,
)
from ..units.quantity import Quantity
from .capability import SolverCapability

SOLVER_IDENTITY_SCHEMA = schema_string("solver_identity")
#: Bumped alongside ``scientific_result``. ``data_references`` is part of this
#: record's serialized semantics too: it is the only statement of which bulk
#: arrays a solve produced once they have left ``diagnostics``, so a reader
#: that dropped it would report a solve as having produced nothing.
RAW_OUTPUT_SCHEMA = schema_string("raw_solver_output", 2)

#: The version before ``data_references`` existed. Still read, never written.
RAW_OUTPUT_SCHEMA_V1 = schema_string("raw_solver_output", 1)

#: Exactly the versions this reader knows how to interpret. Not a range.
SUPPORTED_RAW_OUTPUT_SCHEMAS = (RAW_OUTPUT_SCHEMA_V1, RAW_OUTPUT_SCHEMA)


class ConvergenceState(str, Enum):
    """What the numerical backend reported about its own termination.

    ``NOT_APPLICABLE`` is for direct/closed-form evaluation, which neither
    converges nor fails to; it must not be conflated with CONVERGED.
    """

    NOT_APPLICABLE = "not_applicable"
    CONVERGED = "converged"
    NOT_CONVERGED = "not_converged"
    MAX_ITERATIONS = "max_iterations"
    DIVERGED = "diverged"
    FAILED = "failed"


@dataclass(frozen=True)
class SolverIdentity:
    """Versioned identity of a solver, recorded in every result."""

    solver_id: str
    version: str
    backend: str = ""

    def __post_init__(self) -> None:
        for label in ("solver_id", "version"):
            if not str(getattr(self, label)).strip():
                raise ScientificCoreError(f"solver requires a non-empty {label}")
            object.__setattr__(self, label, str(getattr(self, label)).strip())

    @property
    def key(self) -> tuple[str, str]:
        return (self.solver_id, self.version)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SOLVER_IDENTITY_SCHEMA,
            "solver_id": self.solver_id,
            "version": self.version,
            "backend": self.backend,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SolverIdentity":
        require_schema(payload, SOLVER_IDENTITY_SCHEMA)
        return cls(
            solver_id=payload["solver_id"],
            version=payload["version"],
            backend=payload.get("backend", ""),
        )


@dataclass(frozen=True)
class SolverSettings:
    """Numerical settings actually used, recorded for provenance."""

    tolerances: Mapping[str, float] = field(default_factory=dict)
    options: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        tolerances: dict[str, float] = {}
        for key, value in self.tolerances.items():
            tolerance = float(value)
            if not math.isfinite(tolerance):
                raise ScientificCoreError(
                    f"solver tolerance {str(key)!r} must be finite, got "
                    f"{tolerance!r}"
                )
            if tolerance < 0.0:
                raise ScientificCoreError(
                    f"solver tolerance {str(key)!r} must be non-negative, got "
                    f"{tolerance!r}"
                )
            tolerances[str(key)] = tolerance
        object.__setattr__(self, "tolerances", freeze(tolerances))
        unrecordable = unwritable(self.options, path="options")
        if unrecordable is not None:
            where, kind = unrecordable
            raise ScientificCoreError(
                f"solver settings cannot be recorded: {where} is a {kind}, "
                f"which no scientific record can carry. These settings are "
                f"what a provenance record says the run used, so one that "
                f"cannot be written down is a claim that does not survive the "
                f"boundary it was written for"
            )
        object.__setattr__(self, "options", freeze(dict(self.options)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "tolerances": dict(sorted(self.tolerances.items())),
            "options": {
                key: detach(value)
                for key, value in sorted(self.options.items(), key=lambda kv: kv[0])
            },
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SolverSettings":
        return cls(
            tolerances=dict(payload.get("tolerances", {})),
            options=dict(payload.get("options", {})),
        )


@dataclass(frozen=True)
class PreparedSolve:
    """Solver-specific state produced from a problem, before execution."""

    problem: Any
    solver: SolverIdentity
    settings: SolverSettings = field(default_factory=SolverSettings)
    payload: Any = None
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "notes", tuple(self.notes))


def _iteration_count(value: Any) -> int | None:
    """A recorded iteration count: a non-negative whole number, or unrecorded."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, numbers.Integral):
        raise ScientificCoreError(
            f"raw solver output iteration count must be a whole number, got "
            f"{value!r} ({type(value).__name__})"
        )
    count = int(value)
    if count < 0:
        raise ScientificCoreError(
            f"raw solver output iteration count must be non-negative, got "
            f"{count}; no solve takes fewer than zero iterations"
        )
    return count


def _wall_seconds(value: Any) -> float | None:
    """A recorded wall time: finite, non-negative seconds, or unrecorded."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise ScientificCoreError(
            f"raw solver output wall time must be a number of seconds, got "
            f"{value!r} ({type(value).__name__})"
        )
    seconds = float(value)
    if not math.isfinite(seconds) or seconds < 0.0:
        raise ScientificCoreError(
            f"raw solver output wall time must be finite and non-negative, "
            f"got {seconds!r}"
        )
    return seconds


@dataclass(frozen=True)
class RawSolverOutput:
    """Unintepreted backend output plus its self-reported convergence."""

    convergence: ConvergenceState
    values: Mapping[str, float] = field(default_factory=dict)
    residuals: Mapping[str, float] = field(default_factory=dict)
    iterations: int | None = None
    wall_seconds: float | None = None
    warnings: tuple[str, ...] = ()
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
    artifacts: tuple[str, ...] = ()
    data_references: tuple[ScientificDataReference, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "convergence", ConvergenceState(self.convergence))
        object.__setattr__(
            self,
            "values",
            freeze({str(k): float(v) for k, v in self.values.items()}),
        )
        object.__setattr__(
            self,
            "residuals",
            freeze({str(k): float(v) for k, v in self.residuals.items()}),
        )
        self._require_finite_on_success()
        object.__setattr__(self, "iterations", _iteration_count(self.iterations))
        object.__setattr__(self, "wall_seconds", _wall_seconds(self.wall_seconds))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "artifacts", tuple(self.artifacts))
        unrecordable = unwritable(self.diagnostics, path="diagnostics")
        if unrecordable is not None:
            where, kind = unrecordable
            raise ScientificCoreError(
                f"raw solver output cannot be recorded: {where} is a {kind}, "
                f"which no scientific record can carry"
            )
        object.__setattr__(self, "diagnostics", freeze(dict(self.diagnostics)))
        references = tuple(self.data_references)
        for reference in references:
            if not isinstance(reference, ScientificDataReference):
                raise ScientificCoreError(
                    f"raw output data reference must be a ScientificDataReference, "
                    f"got {type(reference).__name__}"
                )
        object.__setattr__(
            self,
            "data_references",
            tuple(sorted(references, key=lambda r: r.name)),
        )

    def _require_finite_on_success(self) -> None:
        if not self.succeeded:
            return
        offenders = sorted(
            f"{label}={value!r}"
            for label, value in (
                *self.values.items(),
                *((f"residual:{k}", v) for k, v in self.residuals.items()),
            )
            if not math.isfinite(value)
        )
        if offenders:
            raise ScientificCoreError(
                f"a solve reporting {self.convergence.value} returned "
                f"non-finite value(s) {offenders}. A NaN or an infinity "
                f"cannot be admitted by a successful solve"
            )

    @property
    def succeeded(self) -> bool:
        return self.convergence in (
            ConvergenceState.CONVERGED,
            ConvergenceState.NOT_APPLICABLE,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": RAW_OUTPUT_SCHEMA,
            "convergence": self.convergence.value,
            "values": dict(sorted(self.values.items())),
            "residuals": dict(sorted(self.residuals.items())),
            "iterations": self.iterations,
            "wall_seconds": self.wall_seconds,
            "warnings": list(self.warnings),
            "diagnostics": dict(sorted(self.diagnostics.items(), key=lambda kv: kv[0])),
            "artifacts": list(self.artifacts),
            "data_references": [r.to_dict() for r in self.data_references],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RawSolverOutput":
        version = require_schema_any(payload, SUPPORTED_RAW_OUTPUT_SCHEMAS)
        return cls(
            convergence=ConvergenceState(payload["convergence"]),
            values=dict(payload.get("values", {})),
            residuals=dict(payload.get("residuals", {})),
            iterations=payload.get("iterations"),
            wall_seconds=payload.get("wall_seconds"),
            warnings=tuple(payload.get("warnings", ())),
            diagnostics=dict(payload.get("diagnostics", {})),
            artifacts=tuple(payload.get("artifacts", ())),
            data_references=()
            if version == RAW_OUTPUT_SCHEMA_V1
            else tuple(
                ScientificDataReference.from_dict(r)
                for r in payload.get("data_references", ())
            ),
        )


@runtime_checkable
class ScientificSolver(Protocol):
    """What every solver adapter must provide."""

    @property
    def identity(self) -> SolverIdentity: ...

    @property
    def capabilities(self) -> frozenset[SolverCapability]: ...

    def supports(self, problem) -> bool: ...

    def prepare(self, problem) -> PreparedSolve: ...

    def solve(self, prepared: PreparedSolve) -> RawSolverOutput: ...

    def validate(self, prepared: PreparedSolve, raw: RawSolverOutput): ...

    def extract_metrics(
        self, prepared: PreparedSolve, raw: RawSolverOutput
    ) -> Mapping[str, Quantity]: ...


def capability_gap(solver: ScientificSolver, problem) -> frozenset[str]:
    """Capabilities the problem requires that the solver does not declare."""
    declared = {c.name for c in solver.capabilities}
    return frozenset(problem.required_capabilities) - declared


class DeclaredSupport:
    """``supports`` implemented once, from what a solver declares."""

    serves_capabilities: frozenset[str] = frozenset()
    served_models: tuple = ()

    def support_gap(self, problem) -> tuple[str, ...]:
        """Every reason this solver cannot serve this problem, in order."""
        from ..ir.problem import ScientificProblem

        if not isinstance(problem, ScientificProblem):
            return (f"not a ScientificProblem: {type(problem).__name__}",)

        reasons: list[str] = []

        requested = frozenset(problem.required_capabilities)
        declared = {capability.name for capability in self.capabilities}
        missing = sorted(requested - declared)
        if missing:
            reasons.append(
                f"the problem requires {missing}, which this solver does not "
                f"declare; it declares {sorted(declared)}"
            )

        unasked = sorted(frozenset(self.serves_capabilities) - requested)
        if unasked:
            reasons.append(
                f"the problem does not require {unasked}, which is what this "
                f"solver is for; it requires {sorted(requested) or 'nothing'}"
            )

        if self.served_models:
            served = {(model.model_id, model.version) for model in self.served_models}
            referenced = {reference.key for reference in problem.models}
            if not referenced & served:
                render = lambda keys: [f"{model_id}@{version}" for model_id, version in sorted(keys)]
                reasons.append(
                    f"the problem names no model version this solver implements; it "
                    f"names {render(referenced) or 'none'} and this solver "
                    f"implements {render(served)}"
                )

        reasons.extend(self.additional_support_gap(problem))
        return tuple(reasons)

    def additional_support_gap(self, problem) -> tuple[str, ...]:
        return ()

    def supports(self, problem) -> bool:
        return not self.support_gap(problem)
