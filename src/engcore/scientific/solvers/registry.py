"""Solver registry with explicit, never-silent resolution.

Two failure modes are treated as first-class errors rather than papered over:

* nothing matches  -> :class:`SolverNotFoundError`
* several match    -> :class:`AmbiguousSolverError`

Picking "the first one" would make results depend on registration order,
which is exactly the kind of hidden nondeterminism this platform exists to
eliminate. A caller that genuinely has a preference supplies a selection
rule and thereby records that choice.
"""

from __future__ import annotations

from typing import Callable, Iterable, Iterator, Sequence

from ..errors import (
    AmbiguousSolverError,
    DuplicateRegistrationError,
    SolverNotFoundError,
)
from .capability import SolverCapability
from .protocol import ScientificSolver, SolverIdentity, capability_gap

SelectionRule = Callable[[Sequence[ScientificSolver]], ScientificSolver]


class SolverRegistry:
    """Maps ``(solver_id, version)`` to a solver instance."""

    def __init__(self, solvers: Iterable[ScientificSolver] = ()) -> None:
        self._solvers: dict[tuple[str, str], ScientificSolver] = {}
        for solver in solvers:
            self.register(solver)

    # ---- mutation -------------------------------------------------------
    def register(self, solver: ScientificSolver) -> None:
        identity = solver.identity
        if not isinstance(identity, SolverIdentity):
            raise TypeError("solver.identity must be a SolverIdentity")
        if identity.key in self._solvers:
            raise DuplicateRegistrationError(
                f"solver {identity.solver_id!r} version {identity.version!r} "
                f"is already registered"
            )
        self._solvers[identity.key] = solver

    def unregister(self, solver_id: str, version: str) -> None:
        key = (str(solver_id), str(version))
        if key not in self._solvers:
            raise SolverNotFoundError(
                f"no solver {solver_id!r} version {version!r} to unregister"
            )
        del self._solvers[key]

    # ---- lookup ---------------------------------------------------------
    def get(self, solver_id: str, version: str) -> ScientificSolver:
        key = (str(solver_id), str(version))
        try:
            return self._solvers[key]
        except KeyError:
            raise SolverNotFoundError(
                f"no solver {solver_id!r} version {version!r} registered"
            ) from None

    def candidates(self, problem) -> tuple[ScientificSolver, ...]:
        """All registered solvers that declare support, in deterministic order."""
        return tuple(
            self._solvers[key]
            for key in sorted(self._solvers)
            if self._solvers[key].supports(problem)
        )

    def resolve(
        self,
        problem,
        *,
        selection_rule: SelectionRule | None = None,
    ) -> ScientificSolver:
        """Find the one solver for this problem, or fail explicitly."""
        matches = self.candidates(problem)

        if not matches:
            detail = self._no_match_detail(problem)
            raise SolverNotFoundError(
                f"no registered solver supports problem "
                f"{problem.problem_id!r}{detail}"
            )

        if len(matches) > 1:
            if selection_rule is None:
                names = ", ".join(
                    f"{s.identity.solver_id}@{s.identity.version}" for s in matches
                )
                raise AmbiguousSolverError(
                    f"{len(matches)} solvers support problem "
                    f"{problem.problem_id!r} ({names}); supply a selection_rule "
                    f"— the core never chooses silently"
                )
            chosen = selection_rule(matches)
            if chosen not in matches:
                raise AmbiguousSolverError(
                    "selection_rule returned a solver that does not support "
                    "the problem"
                )
            return chosen

        return matches[0]

    def _no_match_detail(self, problem) -> str:
        if not self._solvers:
            return "; registry is empty"
        gaps = []
        for key in sorted(self._solvers):
            solver = self._solvers[key]
            missing = capability_gap(solver, problem)
            if missing:
                gaps.append(
                    f"{key[0]}@{key[1]} lacks {sorted(missing)}"
                )
        return f"; {'; '.join(gaps)}" if gaps else ""

    # ---- introspection --------------------------------------------------
    def capabilities(self) -> frozenset[SolverCapability]:
        declared: set[SolverCapability] = set()
        for solver in self._solvers.values():
            declared |= set(solver.capabilities)
        return frozenset(declared)

    def capability_names(self) -> tuple[str, ...]:
        return tuple(sorted(c.name for c in self.capabilities()))

    def list(self) -> tuple[ScientificSolver, ...]:
        return tuple(self._solvers[key] for key in sorted(self._solvers))

    def __len__(self) -> int:
        return len(self._solvers)

    def __iter__(self) -> Iterator[ScientificSolver]:
        return iter(self.list())
