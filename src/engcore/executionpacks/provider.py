"""Execution-pack provider protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..execution.multiphysics import ParticipantFactoryDeclaration
from .manifest import ExecutionPackManifest


@runtime_checkable
class ExecutionPackProvider(Protocol):
    @property
    def manifest(self) -> ExecutionPackManifest: ...

    def participant_factories(
        self,
    ) -> tuple[ParticipantFactoryDeclaration, ...]: ...


__all__ = ["ExecutionPackProvider"]
