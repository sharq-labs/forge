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
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol, runtime_checkable

from ..errors import ScientificCoreError
from ..results.data_reference import ScientificDataReference
from ..serialization import require_schema, require_schema_any, schema_string
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
            tolerances[str(key)] = tolerance
        object.__setattr__(self, "tolerances", tolerances)
        object.__setattr__(self, "options", dict(self.options))

    def to_dict(self) -> dict[str, Any]:
        return {
            "tolerances": dict(sorted(self.tolerances.items())),
            "options": dict(sorted(self.options.items(), key=lambda kv: kv[0])),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SolverSettings":
        return cls(
            tolerances=dict(payload.get("tolerances", {})),
            options=dict(payload.get("options", {})),
        )


@dataclass(frozen=True)
class PreparedSolve:
    """Solver-specific state produced from a problem, before execution.

    ``payload`` is opaque to the core: an assembled matrix, a mesh handle, a
    compiled netlist. The core only guarantees it travels with the problem
    and the settings that produced it.
    """

    problem: Any
    solver: SolverIdentity
    settings: SolverSettings = field(default_factory=SolverSettings)
    payload: Any = None
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "notes", tuple(self.notes))


@dataclass(frozen=True)
class RawSolverOutput:
    """Unintepreted backend output plus its self-reported convergence.

    Values may be plain numbers here — this is the one place where numeric
    kernels are allowed to speak numbers. They become unit-carrying
    quantities in ``extract_metrics``.

    **This is the sanctioned home for non-finite values.** A diverged solve
    genuinely produces NaN or ±Inf, and forcing an adapter to hide that would
    make it lie about what happened. The finiteness invariant begins one
    layer up, at :class:`~engcore.scientific.units.Quantity`: raw output may
    be non-finite, interpreted science may not.
    """

    convergence: ConvergenceState
    values: Mapping[str, float] = field(default_factory=dict)
    residuals: Mapping[str, float] = field(default_factory=dict)
    iterations: int | None = None
    wall_seconds: float | None = None
    warnings: tuple[str, ...] = ()
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
    artifacts: tuple[str, ...] = ()
    #: Identities of bulk arrays this solve produced and handed to a store.
    #: The arrays themselves are not here and never were: ``diagnostics`` is
    #: an untyped dict that gets serialized, so an O(mesh) array parked in it
    #: makes every stored raw record unreadable. A reference is O(1) and says
    #: precisely which data was produced without carrying it.
    data_references: tuple[ScientificDataReference, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "convergence", ConvergenceState(self.convergence))
        object.__setattr__(
            self, "values", {str(k): float(v) for k, v in self.values.items()}
        )
        object.__setattr__(
            self, "residuals", {str(k): float(v) for k, v in self.residuals.items()}
        )
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "artifacts", tuple(self.artifacts))
        object.__setattr__(self, "diagnostics", dict(self.diagnostics))
        references = tuple(self.data_references)
        for reference in references:
            if not isinstance(reference, ScientificDataReference):
                raise ScientificCoreError(
                    f"raw output data reference must be a "
                    f"ScientificDataReference, got {type(reference).__name__}"
                )
        object.__setattr__(
            self,
            "data_references",
            tuple(sorted(references, key=lambda r: r.name)),
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
            # Same compatibility branch as ``ScientificResult.from_dict``: a
            # ``raw_solver_output/1`` record predates bulk references and loads
            # with none.
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

    def supports(self, problem) -> bool:
        """True when this solver can legitimately handle the problem.

        Implementations must answer on declared capabilities and problem
        structure — never by attempting a solve.
        """
        ...

    def prepare(self, problem) -> PreparedSolve: ...

    def solve(self, prepared: PreparedSolve) -> RawSolverOutput: ...

    def validate(self, prepared: PreparedSolve, raw: RawSolverOutput):
        """Return a ``ValidationReport`` for this solve."""
        ...

    def extract_metrics(
        self, prepared: PreparedSolve, raw: RawSolverOutput
    ) -> Mapping[str, Quantity]:
        """Attach units to raw numbers. This is the boundary where numeric
        output re-enters the unit-aware scientific world."""
        ...


def capability_gap(solver: ScientificSolver, problem) -> frozenset[str]:
    """Capabilities the problem requires that the solver does not declare."""
    declared = {c.name for c in solver.capabilities}
    return frozenset(problem.required_capabilities) - declared
