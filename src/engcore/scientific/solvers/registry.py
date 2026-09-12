"""Solver registry with explicit, never-silent resolution, and no shared sessions.

Two failure modes are treated as first-class errors rather than papered over:

* nothing matches  -> :class:`SolverNotFoundError`
* several match    -> :class:`AmbiguousSolverError`

Picking "the first one" would make results depend on registration order,
which is exactly the kind of hidden nondeterminism this platform exists to
eliminate. A caller that genuinely has a preference supplies a selection
rule and thereby records that choice.

What the registry stores, and what it hands out
-----------------------------------------------
A solver adapter binds the system a problem describes -- and the operating
point, the numerics or the realization beside it -- to the instance, keyed by
problem id, and ``prepare`` reads that binding. A solver instance is therefore
a *session*: it carries the requests made through it.

This registry used to store one instance per solver and return it from every
``resolve``, so every caller of the registry shared one session. Two
independent requests binding the same problem id solved at each other's
operating point, and a request that failed left a binding behind that refused
the next one.

So the registry stores a **definition** and never a session: a zero-argument
factory, plus a probe built once at registration that answers the identity,
capability and support questions, and is never returned and never bound.
Every solver the registry hands out -- from :meth:`resolve`, :meth:`get`,
:meth:`candidates`, :meth:`list`, iteration, or as a candidate passed to a
selection rule -- is a fresh session from the factory. A failed request's
session is dropped with the request; nothing is reset, because nothing it
touched is shared.

Registering an already-constructed solver is refused. The registry cannot tell
a pristine instance from one carrying another request's bindings, and a copy
of either would be a guess about which of its attributes are configuration.
"""

from __future__ import annotations

import weakref
from typing import Callable, Iterable, Iterator, Sequence

from ..errors import (
    AmbiguousSolverError,
    DuplicateRegistrationError,
    SolverNotFoundError,
)
from .capability import SolverCapability
from .protocol import (
    DeclaredSupport,
    ScientificSolver,
    SolverIdentity,
    capability_gap,
)

SelectionRule = Callable[[Sequence[ScientificSolver]], ScientificSolver]

#: What the registry accepts: a class, or any zero-argument callable, that
#: returns a new solver every time it is called.
SolverFactory = Callable[[], ScientificSolver]


def _looks_constructed(candidate: object) -> bool:
    """Is this a solver instance rather than something that makes one?"""
    if isinstance(candidate, type):
        return False
    return isinstance(candidate, DeclaredSupport) or any(
        hasattr(candidate, name) for name in ("identity", "prepare", "solve")
    )


class SolverDefinition:
    """One registered solver: how to make a session, and what it declares.

    The probe is private to the definition. It exists so that identity,
    capabilities and support can be answered without constructing a session
    per question, and it is never handed to a caller, so nothing ever binds to
    it.
    """

    def __init__(self, factory: SolverFactory, probe: ScientificSolver) -> None:
        self._factory = factory
        self._probe = probe
        self._identity: SolverIdentity = probe.identity
        # Sessions already handed out, by object identity. Solver adapters are
        # mostly plain dataclasses, which are unhashable, so this is keyed by
        # ``id`` and holds weak references: a dead session's entry goes with it
        # and its id cannot be mistaken for a new session's.
        self._issued: dict[int, weakref.ref] = {}

    @property
    def identity(self) -> SolverIdentity:
        return self._identity

    @property
    def capabilities(self) -> frozenset[SolverCapability]:
        return frozenset(self._probe.capabilities)

    def supports(self, problem) -> bool:
        return self._probe.supports(problem)

    def new_session(self) -> ScientificSolver:
        """A solver no other request has been given.

        Refused if the factory hands back the probe or an instance it already
        produced: a factory that returns one object every time turns the
        registry back into the shared session it exists to prevent.
        """
        session = self._factory()
        label = f"{self._identity.solver_id}@{self._identity.version}"
        issued = self._issued.get(id(session))
        if session is self._probe or (issued is not None and issued() is session):
            raise TypeError(
                f"the factory registered for {label} returned a solver instance "
                f"it had already produced; every request needs a new session, "
                f"or two requests share one set of bindings"
            )
        if session.identity != self._identity:
            raise TypeError(
                f"the factory registered for {label} produced a solver "
                f"identifying as {session.identity.solver_id}@"
                f"{session.identity.version}; a definition's sessions must all "
                f"be the solver it was registered as"
            )
        self._remember(session)
        return session

    def _remember(self, session: ScientificSolver) -> None:
        key = id(session)
        issued = self._issued

        def forget(_reference, key=key):
            issued.pop(key, None)

        try:
            issued[key] = weakref.ref(session, forget)
        except TypeError:
            # A ``__slots__`` solver without ``__weakref__``: nothing to track
            # it by that would not keep it alive. The probe check still holds.
            pass


class SolverRegistry:
    """Maps ``(solver_id, version)`` to a solver definition, and hands out sessions."""

    def __init__(self, factories: Iterable[SolverFactory] = ()) -> None:
        self._definitions: dict[tuple[str, str], SolverDefinition] = {}
        for factory in factories:
            self.register(factory)

    # ---- mutation -------------------------------------------------------
    def register(self, factory: SolverFactory) -> SolverDefinition:
        if _looks_constructed(factory) or not callable(factory):
            name = type(factory).__name__
            raise TypeError(
                f"SolverRegistry registers solver factories, not solver "
                f"instances: got an already-constructed {name}. A solver instance "
                f"carries the bindings of the requests made through it, so the "
                f"registry cannot keep one without sharing it. Register the class "
                f"(SolverRegistry([{name}])) or a zero-argument callable "
                f"(lambda: {name}(...))"
            )
        solver = factory()
        identity = solver.identity
        if not isinstance(identity, SolverIdentity):
            raise TypeError("solver.identity must be a SolverIdentity")
        self._require_core_support_decision(solver)
        if identity.key in self._definitions:
            raise DuplicateRegistrationError(
                f"solver {identity.solver_id!r} version {identity.version!r} "
                f"is already registered"
            )
        definition = SolverDefinition(factory, solver)
        self._definitions[identity.key] = definition
        return definition

    @staticmethod
    def _require_core_support_decision(solver: ScientificSolver) -> None:
        """A registered solver does not decide its own support question.

        ``supports`` answers "can this solver serve this problem", and the
        registry's ``resolve`` is what acts on the answer. An adapter that
        implements it by hand is answering a question about capability
        coverage that only the core sees the whole of -- and two adapters that
        did got it wrong in the same way, by checking one capability and
        ignoring the rest of the request.

        So the comparison belongs to :class:`DeclaredSupport` and an adapter
        declares its way to an answer. Refused here rather than trusted,
        because the registry is what turns a wrong "yes" into a solve.
        """
        if not isinstance(solver, DeclaredSupport):
            raise TypeError(
                f"solver {type(solver).__name__} does not use the core support "
                f"contract; a solver decides which problems it serves by "
                f"declaring capabilities, serves_capabilities and "
                f"served_models on DeclaredSupport, not by implementing "
                f"supports() itself"
            )
        if type(solver).supports is not DeclaredSupport.supports:
            raise TypeError(
                f"solver {type(solver).__name__} overrides supports(); the "
                f"support decision is the core's, so that comparison cannot be "
                f"answered per adapter. Declare serves_capabilities and "
                f"served_models, and put anything they cannot express in "
                f"additional_support_gap()"
            )

    def unregister(self, solver_id: str, version: str) -> None:
        key = (str(solver_id), str(version))
        if key not in self._definitions:
            raise SolverNotFoundError(
                f"no solver {solver_id!r} version {version!r} to unregister"
            )
        del self._definitions[key]

    # ---- lookup ---------------------------------------------------------
    def definition(self, solver_id: str, version: str) -> SolverDefinition:
        key = (str(solver_id), str(version))
        try:
            return self._definitions[key]
        except KeyError:
            raise SolverNotFoundError(
                f"no solver {solver_id!r} version {version!r} registered"
            ) from None

    def get(self, solver_id: str, version: str) -> ScientificSolver:
        """A new session of the named solver."""
        return self.definition(solver_id, version).new_session()

    def _supporting(self, problem) -> tuple[SolverDefinition, ...]:
        return tuple(
            self._definitions[key]
            for key in sorted(self._definitions)
            if self._definitions[key].supports(problem)
        )

    def candidates(self, problem) -> tuple[ScientificSolver, ...]:
        """A new session of every solver that declares support, in deterministic order."""
        return tuple(definition.new_session() for definition in self._supporting(problem))

    def resolve(
        self,
        problem,
        *,
        selection_rule: SelectionRule | None = None,
    ) -> ScientificSolver:
        """A new session of the one solver for this problem, or fail explicitly."""
        supporting = self._supporting(problem)

        if not supporting:
            detail = self._no_match_detail(problem)
            raise SolverNotFoundError(
                f"no registered solver supports problem "
                f"{problem.problem_id!r}{detail}"
            )

        if len(supporting) > 1:
            if selection_rule is None:
                names = ", ".join(
                    f"{d.identity.solver_id}@{d.identity.version}" for d in supporting
                )
                raise AmbiguousSolverError(
                    f"{len(supporting)} solvers support problem "
                    f"{problem.problem_id!r} ({names}); supply a selection_rule "
                    f"— the core never chooses silently"
                )
            matches = tuple(definition.new_session() for definition in supporting)
            chosen = selection_rule(matches)
            if not any(chosen is match for match in matches):
                raise AmbiguousSolverError(
                    "selection_rule returned a solver that does not support "
                    "the problem"
                )
            return chosen

        return supporting[0].new_session()

    def _no_match_detail(self, problem) -> str:
        if not self._definitions:
            return "; registry is empty"
        gaps = []
        for key in sorted(self._definitions):
            missing = capability_gap(self._definitions[key], problem)
            if missing:
                gaps.append(
                    f"{key[0]}@{key[1]} lacks {sorted(missing)}"
                )
        return f"; {'; '.join(gaps)}" if gaps else ""

    # ---- introspection --------------------------------------------------
    def capabilities(self) -> frozenset[SolverCapability]:
        declared: set[SolverCapability] = set()
        for definition in self._definitions.values():
            declared |= set(definition.capabilities)
        return frozenset(declared)

    def capability_names(self) -> tuple[str, ...]:
        return tuple(sorted(c.name for c in self.capabilities()))

    def list(self) -> tuple[ScientificSolver, ...]:
        """A new session of every registered solver, in deterministic order."""
        return tuple(
            self._definitions[key].new_session() for key in sorted(self._definitions)
        )

    def __len__(self) -> int:
        return len(self._definitions)

    def __iter__(self) -> Iterator[ScientificSolver]:
        return iter(self.list())
