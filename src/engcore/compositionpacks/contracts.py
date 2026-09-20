"""System-level validity, uncertainty and validation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

from ..domainpacks.manifest import ArtifactRef
from ..scientific.ir.values import (
    ScientificValue,
    decode_value,
    encode_value,
    require_scientific_value,
)
from ..scientific.serialization import (
    require_schema,
    require_schema_any,
    schema_string,
)
from ..sria.uncertainty import UncertaintyChannel
from .applicability import ApplicabilityPredicate
from .errors import InvalidCompositionPackProvider

SYSTEM_VALIDATION_CHECK_SCHEMA = schema_string(
    "composition_system_validation_check"
)
SYSTEM_VALIDATION_RESULT_SCHEMA_V1 = schema_string(
    "composition_system_validation_result"
)
SYSTEM_VALIDATION_RESULT_SCHEMA = schema_string(
    "composition_system_validation_result",
    2,
)

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
    predicates: tuple[ApplicabilityPredicate, ...]
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
        predicates = tuple(self.predicates)
        if any(
            not isinstance(item, ApplicabilityPredicate)
            for item in predicates
        ):
            raise InvalidCompositionPackProvider(
                "system applicability predicates must be ApplicabilityPredicate records"
            )
        ids = [item.predicate_id for item in predicates]
        if len(ids) != len(set(ids)):
            raise InvalidCompositionPackProvider(
                "system applicability contains duplicate predicate ids"
            )
        object.__setattr__(
            self,
            "predicates",
            tuple(sorted(predicates, key=lambda item: item.predicate_id)),
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
        object.__setattr__(
            self,
            "description",
            str(self.description).strip(),
        )

    @property
    def key(self) -> tuple[str, str]:
        return self.blueprint_id, self.rule_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "blueprint_id": self.blueprint_id,
            "rule_id": self.rule_id,
            "predicates": [
                item.to_dict() for item in self.predicates
            ],
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
        object.__setattr__(
            self,
            "description",
            str(self.description).strip(),
        )

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
class SystemValidationCheck:
    check_id: str
    passed: bool
    observed: ScientificValue | None = None
    expected: ScientificValue | None = None
    tolerance: ScientificValue | None = None
    absolute_error: ScientificValue | None = None
    relative_error: float | None = None
    evidence: tuple[str, ...] = ()
    detail: str = ""

    def __post_init__(self) -> None:
        check_id = str(self.check_id).strip()
        if not check_id:
            raise InvalidCompositionPackProvider(
                "system validation check requires check_id"
            )
        object.__setattr__(self, "check_id", check_id)
        if not isinstance(self.passed, bool):
            raise InvalidCompositionPackProvider(
                "system validation check passed must be boolean"
            )
        for label in (
            "observed",
            "expected",
            "tolerance",
            "absolute_error",
        ):
            value = getattr(self, label)
            if value is not None:
                require_scientific_value(
                    value,
                    context=f"system_validation.{check_id}.{label}",
                )
        if self.relative_error is not None:
            value = float(self.relative_error)
            if not math.isfinite(value) or value < 0.0:
                raise InvalidCompositionPackProvider(
                    "system validation relative_error must be finite non-negative"
                )
            object.__setattr__(self, "relative_error", value)
        object.__setattr__(
            self,
            "evidence",
            tuple(
                str(item).strip()
                for item in self.evidence
                if str(item).strip()
            ),
        )
        object.__setattr__(self, "detail", str(self.detail).strip())

    def to_dict(self) -> dict[str, Any]:
        def enc(value):
            return None if value is None else encode_value(value)

        return {
            "schema": SYSTEM_VALIDATION_CHECK_SCHEMA,
            "check_id": self.check_id,
            "passed": self.passed,
            "observed": enc(self.observed),
            "expected": enc(self.expected),
            "tolerance": enc(self.tolerance),
            "absolute_error": enc(self.absolute_error),
            "relative_error": self.relative_error,
            "evidence": list(self.evidence),
            "detail": self.detail,
        }

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "SystemValidationCheck":
        require_schema(payload, SYSTEM_VALIDATION_CHECK_SCHEMA)

        def dec(name: str):
            raw = payload.get(name)
            return None if raw is None else decode_value(raw)

        return cls(
            check_id=payload["check_id"],
            passed=payload["passed"],
            observed=dec("observed"),
            expected=dec("expected"),
            tolerance=dec("tolerance"),
            absolute_error=dec("absolute_error"),
            relative_error=payload.get("relative_error"),
            evidence=tuple(payload.get("evidence", ())),
            detail=payload.get("detail", ""),
        )


@dataclass(frozen=True)
class SystemValidationResult:
    valid: bool
    checks: tuple[SystemValidationCheck, ...] = ()
    findings: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.valid, bool):
            raise InvalidCompositionPackProvider(
                "system validation result valid must be boolean"
            )
        checks = tuple(self.checks)
        if any(
            not isinstance(item, SystemValidationCheck)
            for item in checks
        ):
            raise InvalidCompositionPackProvider(
                "system validation checks must be SystemValidationCheck records"
            )
        ids = [item.check_id for item in checks]
        if len(ids) != len(set(ids)):
            raise InvalidCompositionPackProvider(
                "system validation checks contain duplicate ids"
            )
        if checks and self.valid != all(item.passed for item in checks):
            raise InvalidCompositionPackProvider(
                "system validation valid flag must equal conjunction of checks"
            )
        object.__setattr__(
            self,
            "checks",
            tuple(sorted(checks, key=lambda item: item.check_id)),
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
            "schema": SYSTEM_VALIDATION_RESULT_SCHEMA,
            "valid": self.valid,
            "checks": [item.to_dict() for item in self.checks],
            "findings": list(self.findings),
            "evidence": list(self.evidence),
        }

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "SystemValidationResult":
        schema = require_schema_any(
            payload,
            (
                SYSTEM_VALIDATION_RESULT_SCHEMA_V1,
                SYSTEM_VALIDATION_RESULT_SCHEMA,
            ),
        )
        return cls(
            valid=payload["valid"],
            checks=(
                ()
                if schema == SYSTEM_VALIDATION_RESULT_SCHEMA_V1
                else tuple(
                    SystemValidationCheck.from_dict(item)
                    for item in payload.get("checks", ())
                )
            ),
            findings=tuple(payload.get("findings", ())),
            evidence=tuple(payload.get("evidence", ())),
        )


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
    "SYSTEM_VALIDATION_CHECK_SCHEMA",
    "SYSTEM_VALIDATION_RESULT_SCHEMA",
    "SYSTEM_VALIDATION_RESULT_SCHEMA_V1",
    "SystemValidationCheck",
    "SystemValidationResult",
    "UncertaintyCompositionRule",
    "UncertaintyCompositionStrategy",
    "system_contract_digest",
]
