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
from ..results.immutable import freeze
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
        # `freeze`, not `dict`. `frozen=True` protects the BINDING, never the
        # container behind it: `settings.tolerances["rtol"] = 1e-3` was
        # refused and `settings.tolerances["rtol"] = 1e-3` through the mapping
        # itself was not. These two mappings are recorded for provenance and
        # travel into `PreparedSolve`, so a tolerance edited after the record
        # was built changes what a stored claim means -- the run says it was
        # solved to a bound nobody solved it to.
        object.__setattr__(self, "tolerances", freeze(tolerances))
        object.__setattr__(self, "options", freeze(dict(self.options)))

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

    **This is the sanctioned home for non-finite values, and only for a solve
    that says it failed.** A diverged solve genuinely produces NaN or ±Inf, and
    forcing an adapter to hide that would make it lie about what happened. A
    solve reporting CONVERGED or NOT_APPLICABLE and returning a number that is
    not a number is telling two stories at once, and this record refuses to
    carry both -- see :meth:`_require_finite_on_success`.

    That refusal is the floor under
    :mod:`engcore.scientific.solvers.admission`. An adapter that reaches an
    external provider should admit its numbers there, where the refusal names
    the provider, the channel and the reason, and arrives in the adapter's own
    failure category. An adapter that does not still cannot construct this
    record -- so a provider value cannot enter a result unchecked, whether or
    not the adapter that fetched it remembered the rule.
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
        # Frozen, for the reason `SolverSettings` above is: this is the record
        # a solver's numbers arrive in, and it is the first thing on the trust
        # boundary. A value injected here after `_require_finite_on_success`
        # ran would be a number that never passed admission, sitting in the
        # record that exists to say numbers did.
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
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "artifacts", tuple(self.artifacts))
        object.__setattr__(self, "diagnostics", freeze(dict(self.diagnostics)))
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

    def _require_finite_on_success(self) -> None:
        """A solve that says it succeeded may not return a non-number.

        **Why this is here and not left to each adapter.** Every admission gate
        an adapter writes is a tolerance comparison, and ``abs(nan - x) > tol``
        is False -- so a gate written to catch a provider whose numbers are
        wrong cannot catch a provider whose numbers are not numbers. That is a
        property of the shape, which means the next adapter written will have
        the same hole, and a rule living in the last adapter's private method
        will not be there when it is.

        So the refusal is on the object every adapter must return. There is no
        route from a backend into a ``ScientificResult`` that does not pass
        through this constructor: ``extract_metrics`` reads this record, and a
        value invented after it is not a value the backend produced. An adapter
        that skips :mod:`engcore.scientific.solvers.admission` therefore
        produces **nothing** rather than something unchecked.

        **Scoped to a succeeded solve, and that scope is the whole design.**
        NOT_CONVERGED, MAX_ITERATIONS, DIVERGED and FAILED keep the sanctioned
        home: a diverged solve genuinely produces NaN, and a record that could
        not say so would force every adapter to launder its own failure.
        CONVERGED and NOT_APPLICABLE cannot, because a solve claiming to have
        completed and returning a number that is not a number is telling two
        stories, and the platform has no reading under which both are true.

        Residuals are held to the same rule for the same reason: a residual is
        what a validation check compares against a tolerance, and a NaN
        residual passes every tolerance ever written for it.
        """
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
                f"satisfies every tolerance comparison written against it -- "
                f"abs(nan - x) > tol is False -- so it cannot be admitted and "
                f"then checked. Either the solve did not succeed, and this "
                f"record should say which of NOT_CONVERGED, DIVERGED or FAILED "
                f"it was, or the number came from outside and belongs in "
                f"engcore.scientific.solvers.admission before it reaches here"
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


class DeclaredSupport:
    """``supports`` implemented once, from what a solver declares.

    The defect
    ----------
    Two adapters answered the support question by checking a single
    capability::

        def supports(self, problem):
            return LUMPED_CAPACITY_TRANSIENT.name in problem.required_capabilities

    A problem asking for that capability **and one more** got ``True`` from a
    solver that cannot serve the second. The registry then resolved to it, and
    the failure arrived later as an exception from ``prepare`` or, worse, as a
    result computed by a solver the problem never asked for. A third adapter
    matched on the model reference alone and never looked at capabilities at
    all.

    The five adapters that *did* get it right had five separate
    implementations of the same three comparisons, which is the same defect one
    step from happening: the next domain writes a sixth, and the sixth is where
    the next review finds this.

    The contract
    ------------
    An adapter **declares** and does not compare. Three declarations:

    ``capabilities``
        Everything this solver can do. The request must be a subset — that is
        the check the two broken adapters were missing.

    ``serves_capabilities``
        The capability (or capabilities) that identify this solver's work. The
        request must *include* them. This is the other direction, and it is
        what stops a solver claiming a problem that declares nothing at all:
        the empty set is a subset of everything, so the subset test alone
        answers ``True`` for a problem that asked for nothing.

    ``served_models``
        The model records this solver implements. The request must name one.
        A capability says what kind of computation is wanted;
        ``core:algebraic`` is true of countless unrelated relations, and only
        the model says *which*.

    ``additional_support_gap``
        The hook for a domain fact none of the three can express -- one
        adapter's "every named model must have a declared realization in this
        domain", for instance. It returns reasons, not a boolean, so a refusal
        explains itself. Deliberately a hook and not a fourth declaration: the
        core cannot know what those facts are, and pretending otherwise is how
        a universal contract acquires domain knowledge.

    The core does the comparing, in :meth:`support_gap`. An adapter that
    overrides ``supports`` is refused by ``SolverRegistry.register``: a solver
    that hand-rolls the comparison is the thing this class exists to stop, and
    a registry that accepted one would resolve to it.
    """

    #: The capability names that identify this solver's work. A problem that
    #: does not ask for all of them is not this solver's problem.
    serves_capabilities: frozenset[str] = frozenset()

    #: Model records this solver implements. Empty means "any model", which is
    #: almost never right and is why every adapter here declares some.
    served_models: tuple = ()

    def support_gap(self, problem) -> tuple[str, ...]:
        """Every reason this solver cannot serve this problem, in order.

        Empty means it can. A tuple rather than a boolean because a solver that
        says only "no" makes the caller guess, and the registry's
        "no solver supports this problem" message is where the guess happens.
        """
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
            served = {model.model_id for model in self.served_models}
            referenced = {reference.model_id for reference in problem.models}
            if not referenced & served:
                reasons.append(
                    f"the problem names no model this solver implements; it "
                    f"names {sorted(referenced) or 'none'} and this solver "
                    f"implements {sorted(served)}"
                )

        reasons.extend(self.additional_support_gap(problem))
        return tuple(reasons)

    def additional_support_gap(self, problem) -> tuple[str, ...]:
        """Domain facts the three declarations cannot express. Usually none."""
        return ()

    def supports(self, problem) -> bool:
        """True when this solver can legitimately handle the whole request.

        Not overridable by an adapter: ``SolverRegistry.register`` refuses a
        solver that redefines it. Declare, do not compare.
        """
        return not self.support_gap(problem)
