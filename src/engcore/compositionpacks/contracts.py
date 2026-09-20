"""System-level validity, uncertainty and validation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Any, Iterable

from ..domainpacks.manifest import ArtifactRef
from ..sria.uncertainty import UncertaintyChannel
from .errors import InvalidCompositionPackProvider


_PATH_SEGMENT = r"[a-zA-Z_][a-zA-Z0-9_]*(?:\[\d+\])?"
_PATH = re.compile(rf"^{_PATH_SEGMENT}(?:\.{_PATH_SEGMENT})*$")


@dataclass(frozen=True, order=True)
class SystemEvidenceRequirement:
    path: str
    description: str = ""

    def __post_init__(self) -> None:
        path = str(self.path).strip()
        if not _PATH.fullmatch(path):
            raise InvalidCompositionPackProvider(
                f"system evidence path {path!r} must be a dotted concrete path"
            )
        object.__setattr__(self, "path", path)
        object.__setattr__(
            self,
            "description",
            str(self.description).strip(),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "path": self.path,
            "description": self.description,
        }


@dataclass(frozen=True, order=True)
class SystemApplicabilityRule:
    blueprint_id: str
    rule_id: str
    assumptions: tuple[str, ...]
    required_evidence: tuple[SystemEvidenceRequirement, ...]
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
        evidence = tuple(self.required_evidence)
        if any(
            not isinstance(item, SystemEvidenceRequirement)
            for item in evidence
        ):
            raise InvalidCompositionPackProvider(
                "required_evidence must contain SystemEvidenceRequirement records"
            )
        if len({item.path for item in evidence}) != len(evidence):
            raise InvalidCompositionPackProvider(
                "system applicability required_evidence contains duplicate paths"
            )
        object.__setattr__(
            self,
            "required_evidence",
            tuple(sorted(evidence, key=lambda item: item.path)),
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
            "required_evidence": [
                item.to_dict() for item in self.required_evidence
            ],
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
    channels: tuple[UncertaintyChannel, ...] = ()
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
        channels = tuple(
            sorted(
                {UncertaintyChannel(item) for item in self.channels},
                key=lambda item: item.value,
            )
        )
        object.__setattr__(self, "channels", channels)
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
            "channels": [item.value for item in self.channels],
            "correlation_model_id": self.correlation_model_id,
            "description": self.description,
        }


@dataclass(frozen=True)
class SystemValidationResult:
    valid: bool
    findings: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.valid, bool):
            raise InvalidCompositionPackProvider(
                "system validation result valid must be boolean"
            )
        object.__setattr__(
            self,
            "findings",
            tuple(
                str(item).strip()
                for item in self.findings
                if str(item).strip()
            ),
        )
        object.__setattr__(
            self,
            "evidence",
            tuple(
                str(item).strip()
                for item in self.evidence
                if str(item).strip()
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "findings": list(self.findings),
            "evidence": list(self.evidence),
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


def system_contract_digest(
    *,
    port_semantics: Iterable[Any],
    coupling_semantics: Iterable[Any],
    external_input_bindings: Iterable[Any],
    applicability_rules: Iterable[SystemApplicabilityRule],
    uncertainty_rules: Iterable[UncertaintyCompositionRule],
) -> str:
    payload = {
        "port_semantics": [
            item.to_dict()
            for item in sorted(
                tuple(port_semantics),
                key=lambda item: item.key,
            )
        ],
        "coupling_semantics": [
            item.to_dict()
            for item in sorted(
                tuple(coupling_semantics),
                key=lambda item: item.key,
            )
        ],
        "external_input_bindings": [
            item.to_dict()
            for item in sorted(
                tuple(external_input_bindings),
                key=lambda item: item.key,
            )
        ],
        "applicability_rules": [
            item.to_dict()
            for item in sorted(
                tuple(applicability_rules),
                key=lambda item: item.key,
            )
        ],
        "uncertainty_rules": [
            item.to_dict()
            for item in sorted(
                tuple(uncertainty_rules),
                key=lambda item: item.key,
            )
        ],
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


__all__ = [
    "ProvidedCompositionValidation",
    "SystemApplicabilityRule",
    "SystemEvidenceRequirement",
    "SystemValidationResult",
    "UncertaintyCompositionRule",
    "UncertaintyCompositionStrategy",
    "system_contract_digest",
]
