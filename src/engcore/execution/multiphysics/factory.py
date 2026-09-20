"""Factory registry for executable multiphysics participants.

The scientific graph declares identities. This registry is the execution-side
bridge that materializes those identities into ExecutableParticipant objects.
Selection is exact and deterministic: no registration-order fallback and no
adapter guessing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping

from ...scientific.errors import InvalidScientificProblem
from ...scientific.multiphysics import ParticipantSpec, PhysicsGraph
from .participant import ExecutableParticipant

ParticipantFactory = Callable[[ParticipantSpec], ExecutableParticipant]


@dataclass(frozen=True)
class ParticipantFactoryDeclaration:
    adapter_id: str
    adapter_version: str
    solver_id: str
    solver_version: str
    factory: ParticipantFactory
    description: str = ""

    def __post_init__(self) -> None:
        for label in (
            "adapter_id",
            "adapter_version",
            "solver_id",
            "solver_version",
        ):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidScientificProblem(
                    f"participant factory declaration requires {label}"
                )
            object.__setattr__(self, label, value)
        if not callable(self.factory):
            raise InvalidScientificProblem(
                "participant factory declaration requires callable factory"
            )
        object.__setattr__(
            self,
            "description",
            str(self.description).strip(),
        )

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (
            self.adapter_id,
            self.adapter_version,
            self.solver_id,
            self.solver_version,
        )

    def matches(self, spec: ParticipantSpec) -> bool:
        return self.key == (
            spec.adapter_id,
            spec.adapter_version,
            spec.solver_id,
            spec.solver_version,
        )


@dataclass(frozen=True)
class ParticipantFactoryCoverage:
    participant_id: str
    adapter_id: str
    adapter_version: str
    solver_id: str
    solver_version: str
    available: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "participant_id": self.participant_id,
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "solver_id": self.solver_id,
            "solver_version": self.solver_version,
            "available": self.available,
        }


class ParticipantFactoryRegistry:
    """Exact execution factory registry for PhysicsGraph participants."""

    def __init__(
        self,
        declarations: Iterable[ParticipantFactoryDeclaration] = (),
    ) -> None:
        self._items: dict[
            tuple[str, str, str, str],
            ParticipantFactoryDeclaration,
        ] = {}
        for declaration in declarations:
            self.register(declaration)

    def register(
        self,
        declaration: ParticipantFactoryDeclaration,
    ) -> None:
        if not isinstance(
            declaration,
            ParticipantFactoryDeclaration,
        ):
            raise TypeError(
                "ParticipantFactoryRegistry accepts "
                "ParticipantFactoryDeclaration only"
            )
        if declaration.key in self._items:
            raise InvalidScientificProblem(
                "duplicate participant factory for "
                f"{declaration.adapter_id}@{declaration.adapter_version} / "
                f"{declaration.solver_id}@{declaration.solver_version}"
            )
        self._items[declaration.key] = declaration

    def declaration_for(
        self,
        spec: ParticipantSpec,
    ) -> ParticipantFactoryDeclaration:
        if not isinstance(spec, ParticipantSpec):
            raise TypeError("declaration_for requires ParticipantSpec")
        key = (
            spec.adapter_id,
            spec.adapter_version,
            spec.solver_id,
            spec.solver_version,
        )
        try:
            return self._items[key]
        except KeyError:
            raise InvalidScientificProblem(
                "no executable participant factory for "
                f"{spec.participant_id!r}: "
                f"adapter={spec.adapter_id}@{spec.adapter_version}, "
                f"solver={spec.solver_id}@{spec.solver_version}"
            ) from None

    def coverage(
        self,
        graph: PhysicsGraph,
    ) -> tuple[ParticipantFactoryCoverage, ...]:
        if not isinstance(graph, PhysicsGraph):
            raise TypeError("coverage requires PhysicsGraph")
        result = []
        for spec in graph.participants:
            key = (
                spec.adapter_id,
                spec.adapter_version,
                spec.solver_id,
                spec.solver_version,
            )
            result.append(
                ParticipantFactoryCoverage(
                    participant_id=spec.participant_id,
                    adapter_id=spec.adapter_id,
                    adapter_version=spec.adapter_version,
                    solver_id=spec.solver_id,
                    solver_version=spec.solver_version,
                    available=key in self._items,
                )
            )
        return tuple(result)

    def missing(
        self,
        graph: PhysicsGraph,
    ) -> tuple[ParticipantFactoryCoverage, ...]:
        return tuple(
            item for item in self.coverage(graph) if not item.available
        )

    def build(
        self,
        spec: ParticipantSpec,
    ) -> ExecutableParticipant:
        declaration = self.declaration_for(spec)
        participant = declaration.factory(spec)

        if not isinstance(participant, ExecutableParticipant):
            raise InvalidScientificProblem(
                f"factory for participant {spec.participant_id!r} returned "
                f"{type(participant).__name__}, not ExecutableParticipant"
            )
        if participant.spec != spec:
            raise InvalidScientificProblem(
                f"factory for participant {spec.participant_id!r} returned "
                "an executable participant with a different ParticipantSpec"
            )
        return participant

    def build_graph(
        self,
        graph: PhysicsGraph,
    ) -> Mapping[str, ExecutableParticipant]:
        if not isinstance(graph, PhysicsGraph):
            raise TypeError("build_graph requires PhysicsGraph")
        missing = self.missing(graph)
        if missing:
            detail = [
                (
                    item.participant_id,
                    f"{item.adapter_id}@{item.adapter_version}",
                    f"{item.solver_id}@{item.solver_version}",
                )
                for item in missing
            ]
            raise InvalidScientificProblem(
                f"multiphysics graph has no executable factories for {detail}"
            )
        return {
            spec.participant_id: self.build(spec)
            for spec in graph.participants
        }

    def __iter__(self):
        for key in sorted(self._items):
            yield self._items[key]


__all__ = [
    "ParticipantFactory",
    "ParticipantFactoryCoverage",
    "ParticipantFactoryDeclaration",
    "ParticipantFactoryRegistry",
]
