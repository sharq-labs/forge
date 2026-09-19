"""Runtime provider contract for one atomic scientific Domain Pack."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol, runtime_checkable

from ..scientific.models.definition import ScientificModelDefinition
from ..scientific.realizations.definition import ModelRealizationDefinition
from .manifest import ArtifactRef, DomainPackManifest


@dataclass(frozen=True)
class ProvidedArtifact:
    """Bind one manifest identity to its runtime implementation."""

    ref: ArtifactRef
    implementation: Any

    def __post_init__(self) -> None:
        if not isinstance(self.ref, ArtifactRef):
            raise TypeError("ProvidedArtifact.ref must be an ArtifactRef")
        if self.implementation is None:
            raise TypeError("ProvidedArtifact implementation may not be None")


@runtime_checkable
class DomainPackProvider(Protocol):
    """No lifecycle hooks: this contract exposes facts and factories only."""

    @property
    def manifest(self) -> DomainPackManifest: ...

    def models(self) -> tuple[ScientificModelDefinition, ...]: ...

    def realizations(self) -> tuple[ModelRealizationDefinition, ...]: ...

    def solver_factories(self) -> tuple[Callable[[], Any], ...]: ...

    def calibration_protocols(self) -> tuple[ProvidedArtifact, ...]: ...

    def validation_protocols(self) -> tuple[ProvidedArtifact, ...]: ...

    def uq_producers(self) -> tuple[ProvidedArtifact, ...]: ...

    def measurement_adapters(self) -> tuple[ProvidedArtifact, ...]: ...

    def transformations(self) -> tuple[ProvidedArtifact, ...]: ...

    def benchmarks(self) -> tuple[ProvidedArtifact, ...]: ...
