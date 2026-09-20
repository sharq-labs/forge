"""Factory registry for executable multiphysics participants.

The scientific graph declares identities. This registry is the execution-side
bridge that materializes those identities into ExecutableParticipant objects.
Selection is exact and deterministic: no registration-order fallback and no
adapter guessing.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Callable, Iterable, Mapping

from ...scientific.errors import InvalidScientificProblem
from ...scientific.multiphysics import (
    ParticipantModelRef,
    ParticipantSpec,
    PhysicsGraph,
)
from .participant import ExecutableParticipant

ParticipantFactory = Callable[[ParticipantSpec], ExecutableParticipant]


@dataclass(frozen=True)
class ParticipantFactoryDeclaration:
    model_id: str
    model_version: str
    realization_id: str
    realization_version: str
    solver_id: str
    solver_version: str
    adapter_id: str
    adapter_version: str
    factory: ParticipantFactory
    description: str = ""
    models: tuple[ParticipantModelRef, ...] = ()

    def __post_init__(self) -> None:
        for label in (
            "model_id",
            "model_version",
            "realization_id",
            "realization_version",
            "solver_id",
            "solver_version",
            "adapter_id",
            "adapter_version",
        ):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidScientificProblem(
                    f"participant factory declaration requires {label}"
                )
            object.__setattr__(self, label, value)
        models = tuple(self.models)
        if not models:
            models = (
                ParticipantModelRef(
                    self.model_id,
                    self.model_version,
                ),
            )
        if any(
            not isinstance(item, ParticipantModelRef)
            for item in models
        ):
            raise InvalidScientificProblem(
                "participant factory models must be ParticipantModelRef records"
            )
        keys = [item.key for item in models]
        if len(keys) != len(set(keys)):
            raise InvalidScientificProblem(
                "participant factory model assembly contains duplicates"
            )
        if (self.model_id, self.model_version) not in set(keys):
            raise InvalidScientificProblem(
                "participant factory primary model must be in model assembly"
            )
        object.__setattr__(
            self,
            "models",
            tuple(sorted(models, key=lambda item: item.key)),
        )
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
    def model_keys(self) -> tuple[tuple[str, str], ...]:
        return tuple(item.key for item in self.models)

    @property
    def key(self) -> tuple[object, ...]:
        return (
            self.model_keys,
            self.realization_id,
            self.realization_version,
            self.solver_id,
            self.solver_version,
            self.adapter_id,
            self.adapter_version,
        )

    def identity_dict(self) -> dict[str, str]:
        return {
            "model_id": self.model_id,
            "model_version": self.model_version,
            "models": [
                item.to_dict() for item in self.models
            ],
            "realization_id": self.realization_id,
            "realization_version": self.realization_version,
            "solver_id": self.solver_id,
            "solver_version": self.solver_version,
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
        }

    def matches(self, spec: ParticipantSpec) -> bool:
        return self.key == (
            spec.model_keys,
            spec.realization_id,
            spec.realization_version,
            spec.solver_id,
            spec.solver_version,
            spec.adapter_id,
            spec.adapter_version,
        )


@dataclass(frozen=True)
class ParticipantFactoryCoverage:
    participant_id: str
    model_id: str
    model_version: str
    realization_id: str
    realization_version: str
    solver_id: str
    solver_version: str
    adapter_id: str
    adapter_version: str
    available: bool

    def __post_init__(self) -> None:
        for label in (
            "participant_id",
            "model_id",
            "model_version",
            "realization_id",
            "realization_version",
            "solver_id",
            "solver_version",
            "adapter_id",
            "adapter_version",
        ):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidScientificProblem(
                    f"participant factory coverage requires {label}"
                )
            object.__setattr__(self, label, value)
        if not isinstance(self.available, bool):
            raise InvalidScientificProblem(
                "participant factory coverage available must be boolean"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "participant_id": self.participant_id,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "realization_id": self.realization_id,
            "realization_version": self.realization_version,
            "solver_id": self.solver_id,
            "solver_version": self.solver_version,
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "available": self.available,
        }

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, object],
    ) -> "ParticipantFactoryCoverage":
        return cls(
            participant_id=str(payload["participant_id"]),
            model_id=str(payload["model_id"]),
            model_version=str(payload["model_version"]),
            realization_id=str(payload["realization_id"]),
            realization_version=str(payload["realization_version"]),
            solver_id=str(payload["solver_id"]),
            solver_version=str(payload["solver_version"]),
            adapter_id=str(payload["adapter_id"]),
            adapter_version=str(payload["adapter_version"]),
            available=payload["available"],
        )


class ParticipantFactoryRegistry:
    """Exact execution factory registry for PhysicsGraph participants."""

    def __init__(
        self,
        declarations: Iterable[ParticipantFactoryDeclaration] = (),
    ) -> None:
        self._items: dict[
            tuple[object, ...],
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
                f"model={declaration.model_id}@{declaration.model_version}, "
                f"realization={declaration.realization_id}@{declaration.realization_version}, "
                f"solver={declaration.solver_id}@{declaration.solver_version}, "
                f"adapter={declaration.adapter_id}@{declaration.adapter_version}"
            )
        self._items[declaration.key] = declaration

    def declaration_for(
        self,
        spec: ParticipantSpec,
    ) -> ParticipantFactoryDeclaration:
        if not isinstance(spec, ParticipantSpec):
            raise TypeError("declaration_for requires ParticipantSpec")
        key = (
            spec.model_keys,
            spec.realization_id,
            spec.realization_version,
            spec.solver_id,
            spec.solver_version,
            spec.adapter_id,
            spec.adapter_version,
        )
        try:
            return self._items[key]
        except KeyError:
            raise InvalidScientificProblem(
                "no executable participant factory for "
                f"{spec.participant_id!r}: "
                f"model={spec.model_id}@{spec.model_version}, "
                f"realization={spec.realization_id}@{spec.realization_version}, "
                f"solver={spec.solver_id}@{spec.solver_version}, "
                f"adapter={spec.adapter_id}@{spec.adapter_version}"
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
                spec.model_keys,
                spec.realization_id,
                spec.realization_version,
                spec.solver_id,
                spec.solver_version,
                spec.adapter_id,
                spec.adapter_version,
            )
            result.append(
                ParticipantFactoryCoverage(
                    participant_id=spec.participant_id,
                    model_id=spec.model_id,
                    model_version=spec.model_version,
                    realization_id=spec.realization_id,
                    realization_version=spec.realization_version,
                    solver_id=spec.solver_id,
                    solver_version=spec.solver_version,
                    adapter_id=spec.adapter_id,
                    adapter_version=spec.adapter_version,
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

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(
            [
                self._items[key].identity_dict()
                for key in sorted(self._items)
            ],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

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
                    f"{item.model_id}@{item.model_version}",
                    f"{item.realization_id}@{item.realization_version}",
                    f"{item.solver_id}@{item.solver_version}",
                    f"{item.adapter_id}@{item.adapter_version}",
                )
                for item in missing
            ]
            raise InvalidScientificProblem(
                f"multiphysics graph has no executable factories for {detail}"
            )
        built: dict[str, ExecutableParticipant] = {}
        try:
            for spec in graph.participants:
                built[spec.participant_id] = self.build(spec)
        except Exception:
            for participant_id in sorted(built, reverse=True):
                try:
                    built[participant_id].finalize()
                except Exception:
                    pass
            raise
        return built

    def __iter__(self):
        for key in sorted(self._items):
            yield self._items[key]


__all__ = [
    "ParticipantFactory",
    "ParticipantFactoryCoverage",
    "ParticipantFactoryDeclaration",
    "ParticipantFactoryRegistry",
]
