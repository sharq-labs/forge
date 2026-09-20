"""Provider protocol for cross-domain Composition Packs."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..claims.capabilities import CapabilityDeclaration
from .blueprint import CouplingPolicyTemplate, SystemGraphBlueprint
from .contracts import (
    ProvidedCompositionValidation,
    SystemApplicabilityRule,
    UncertaintyCompositionRule,
)
from .inputs import ExternalInputBinding
from .manifest import CompositionPackManifest
from .uncertainty import ProvidedCompositionUncertainty
from .verification import ProvidedCompositionVerification
from .semantics import CouplingSemantic, PortSemanticBinding


@runtime_checkable
class CompositionPackProvider(Protocol):
    @property
    def manifest(self) -> CompositionPackManifest: ...

    def claim_capabilities(
        self,
    ) -> tuple[CapabilityDeclaration, ...]: ...

    def blueprints(self) -> tuple[SystemGraphBlueprint, ...]: ...

    def coupling_policy_templates(
        self,
    ) -> tuple[CouplingPolicyTemplate, ...]: ...

    def port_semantics(self) -> tuple[PortSemanticBinding, ...]: ...

    def coupling_semantics(self) -> tuple[CouplingSemantic, ...]: ...

    def external_input_bindings(
        self,
    ) -> tuple[ExternalInputBinding, ...]: ...

    def applicability_rules(self) -> tuple[SystemApplicabilityRule, ...]: ...

    def uncertainty_rules(self) -> tuple[UncertaintyCompositionRule, ...]: ...

    def validation_protocols(
        self,
    ) -> tuple[ProvidedCompositionValidation, ...]: ...

    def uncertainty_producers(
        self,
    ) -> tuple[ProvidedCompositionUncertainty, ...]: ...

    def verification_protocols(
        self,
    ) -> tuple[ProvidedCompositionVerification, ...]: ...


__all__ = ["CompositionPackProvider"]
