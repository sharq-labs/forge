"""System-level validity, uncertainty and validation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from ..domainpacks.manifest import ArtifactRef
from .errors import InvalidCompositionPackProvider


@dataclass(frozen=True, order=True)
class SystemApplicabilityRule:
    blueprint_id: str
    rule_id: str
    assumptions: tuple[str, ...]
    required_evidence: tuple[str, ...]
    description: str = ""

    def __post_init__(self) -> None:
        for label in ("blueprint_id", "rule_id"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidCompositionPackProvider(
                    f"system applicability rule requires {label}"
                )
            object.__setattr__(self, label, value)
        object.__setattr__(
            self,
            "assumptions",
            tuple(sorted({str(item).strip() for item in self.assumptions if str(item).strip()})),
        )
        object.__setattr__(
            self,
            "required_evidence",
            tuple(sorted({str(item).strip() for item in self.required_evidence if str(item).strip()})),
        )
        object.__setattr__(self, "description", str(self.description).strip())

    @property
    def key(self) -> tuple[str, str]:
        return self.blueprint_id, self.rule_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "blueprint_id": self.blueprint_id,
            "rule_id": self.rule_id,
            "assumptions": list(self.assumptions),
            "required_evidence": list(self.required_evidence),
            "description": self.description,
        }


class UncertaintyCompositionStrategy(str, Enum):
    INDEPENDENT = "independent"
    CORRELATED = "correlated"
    ENSEMBLE = "ensemble"
    BOUNDED_WORST_CASE = "bounded_worst_case"
    UNKNOWN = "unknown"


@dataclass(frozen=True, order=True)
class UncertaintyCompositionRule:
    blueprint_id: str
    rule_id: str
    strategy: UncertaintyCompositionStrategy
    channels: tuple[str, ...] = ()
    correlation_model_id: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        for label in ("blueprint_id", "rule_id"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidCompositionPackProvider(
                    f"uncertainty composition rule requires {label}"
                )
            object.__setattr__(self, label, value)
        object.__setattr__(
            self,
            "strategy",
            UncertaintyCompositionStrategy(self.strategy),
        )
        object.__setattr__(
            self,
            "channels",
            tuple(sorted({str(item).strip() for item in self.channels if str(item).strip()})),
        )
        correlation = str(self.correlation_model_id).strip()
        if (
            self.strategy is UncertaintyCompositionStrategy.CORRELATED
            and not correlation
        ):
            raise InvalidCompositionPackProvider(
                "correlated uncertainty composition requires correlation_model_id"
            )
        if (
            self.strategy is not UncertaintyCompositionStrategy.CORRELATED
            and correlation
        ):
            raise InvalidCompositionPackProvider(
                "correlation_model_id is valid only for correlated strategy"
            )
        object.__setattr__(self, "correlation_model_id", correlation)
        object.__setattr__(self, "description", str(self.description).strip())

    @property
    def key(self) -> tuple[str, str]:
        return self.blueprint_id, self.rule_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "blueprint_id": self.blueprint_id,
            "rule_id": self.rule_id,
            "strategy": self.strategy.value,
            "channels": list(self.channels),
            "correlation_model_id": self.correlation_model_id,
            "description": self.description,
        }


@dataclass(frozen=True)
class ProvidedCompositionValidation:
    blueprint_id: str
    ref: ArtifactRef
    implementation: Any

    def __post_init__(self) -> None:
        blueprint_id = str(self.blueprint_id).strip()
        if not blueprint_id:
            raise InvalidCompositionPackProvider(
                "composition validation requires blueprint_id"
            )
        object.__setattr__(self, "blueprint_id", blueprint_id)
        if not isinstance(self.ref, ArtifactRef):
            raise InvalidCompositionPackProvider(
                "composition validation ref must be ArtifactRef"
            )
        if self.implementation is None or not callable(self.implementation):
            raise InvalidCompositionPackProvider(
                "composition validation implementation must be callable"
            )


__all__ = [
    "ProvidedCompositionValidation",
    "SystemApplicabilityRule",
    "UncertaintyCompositionRule",
    "UncertaintyCompositionStrategy",
]
