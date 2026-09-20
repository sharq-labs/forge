"""Provider protocol for cross-domain Composition Packs."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .blueprint import CouplingPolicyTemplate, SystemGraphBlueprint
from .contracts import (
    ProvidedCompositionValidation,
    SystemApplicabilityRule,
    UncertaintyCompositionRule,
)
from .manifest import CompositionPackManifest
from .semantics import CouplingSemantic, PortSemanticBinding


@runtime_checkable
class CompositionPackProvider(Protocol):
    @property
    def manifest(self) -> CompositionPackManifest: ...

    def blueprints(self) -> tuple[SystemGraphBlueprint, ...]: ...

    def coupling_policy_templates(
        self,
    ) -> tuple[CouplingPolicyTemplate, ...]: ...

    def port_semantics(self) -> tuple[PortSemanticBinding, ...]: ...

    def coupling_semantics(self) -> tuple[CouplingSemantic, ...]: ...

    def applicability_rules(self) -> tuple[SystemApplicabilityRule, ...]: ...

    def uncertainty_rules(self) -> tuple[UncertaintyCompositionRule, ...]: ...

    def validation_protocols(
        self,
    ) -> tuple[ProvidedCompositionValidation, ...]: ...


__all__ = ["CompositionPackProvider"]
