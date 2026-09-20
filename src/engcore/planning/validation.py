"""Deterministic completeness and capability screening for EngineeringIntent."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..claims.capabilities import (
    CapabilityDeclaration,
    CapabilityRegistry,
    InputKind,
    declared_path,
    input_problem,
)
from ..scientific.ir.values import (
    BooleanValue,
    CategoricalValue,
    IntegerValue,
    ScientificValue,
)
from ..scientific.serialization import require_schema, schema_string
from ..scientific.units.quantity import Quantity
from .intent import EngineeringIntent, IntentQuantityOfInterest
from .verification import VerificationPlanningRegistry

INTENT_VALIDATION_SCHEMA = schema_string("engineering_intent_validation")
QOI_SCREEN_SCHEMA = schema_string("engineering_intent_qoi_screen")
PLANNING_ISSUE_SCHEMA = schema_string("engineering_planning_issue")


class IntentReadiness(str, Enum):
    READY = "ready"
    NEEDS_CLARIFICATION = "needs_clarification"
    UNSUPPORTED = "unsupported"


class IssueKind(str, Enum):
    MISSING_INPUT = "missing_input"
    INVALID_INPUT = "invalid_input"
    NO_CAPABILITY = "no_capability"
    AMBIGUOUS_CAPABILITY = "ambiguous_capability"
    EVIDENCE_UNATTAINABLE = "evidence_unattainable"
    UNCERTAINTY_UNAVAILABLE = "uncertainty_unavailable"
    INDEPENDENT_ROUTE_UNAVAILABLE = "independent_route_unavailable"


@dataclass(frozen=True)
class PlanningIssue:
    kind: IssueKind
    subject: str
    detail: str
    blocking: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", IssueKind(self.kind))
        object.__setattr__(self, "subject", str(self.subject).strip())
        object.__setattr__(self, "detail", str(self.detail).strip())
        if not self.subject or not self.detail:
            raise ValueError("planning issue requires subject and detail")
        if not isinstance(self.blocking, bool):
            raise ValueError("planning issue blocking must be boolean")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PLANNING_ISSUE_SCHEMA,
            "kind": self.kind.value,
            "subject": self.subject,
            "detail": self.detail,
            "blocking": self.blocking,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PlanningIssue":
        require_schema(payload, PLANNING_ISSUE_SCHEMA)
        return cls(
            kind=IssueKind(payload["kind"]),
            subject=payload["subject"],
            detail=payload["detail"],
            blocking=payload["blocking"],
        )


@dataclass(frozen=True)
class QOICapabilityScreen:
    qoi_id: str
    capability_id: str
    capability_version: str
    capability_digest: str
    eligible: bool
    missing_inputs: tuple[str, ...] = ()
    invalid_inputs: tuple[str, ...] = ()
    evidence_gaps: tuple[str, ...] = ()
    uncertainty_gaps: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for label in ("qoi_id", "capability_id", "capability_version", "capability_digest"):
            if not str(getattr(self, label)).strip():
                raise ValueError(f"capability screen requires {label}")
        for label in (
            "missing_inputs",
            "invalid_inputs",
            "evidence_gaps",
            "uncertainty_gaps",
            "reasons",
        ):
            object.__setattr__(
                self,
                label,
                tuple(sorted(set(str(x) for x in getattr(self, label)))),
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": QOI_SCREEN_SCHEMA,
            "qoi_id": self.qoi_id,
            "capability_id": self.capability_id,
            "capability_version": self.capability_version,
            "capability_digest": self.capability_digest,
            "eligible": self.eligible,
            "missing_inputs": list(self.missing_inputs),
            "invalid_inputs": list(self.invalid_inputs),
            "evidence_gaps": list(self.evidence_gaps),
            "uncertainty_gaps": list(self.uncertainty_gaps),
            "reasons": list(self.reasons),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "QOICapabilityScreen":
        require_schema(payload, QOI_SCREEN_SCHEMA)
        return cls(
            qoi_id=payload["qoi_id"],
            capability_id=payload["capability_id"],
            capability_version=payload["capability_version"],
            capability_digest=payload["capability_digest"],
            eligible=payload["eligible"],
            missing_inputs=tuple(payload.get("missing_inputs", ())),
            invalid_inputs=tuple(payload.get("invalid_inputs", ())),
            evidence_gaps=tuple(payload.get("evidence_gaps", ())),
            uncertainty_gaps=tuple(payload.get("uncertainty_gaps", ())),
            reasons=tuple(payload.get("reasons", ())),
        )


@dataclass(frozen=True)
class IntentValidation:
    intent_identity: str
    registry_digest: str
    readiness: IntentReadiness
    screens: tuple[QOICapabilityScreen, ...]
    issues: tuple[PlanningIssue, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "readiness", IntentReadiness(self.readiness))
        object.__setattr__(
            self,
            "screens",
            tuple(sorted(self.screens, key=lambda x: (x.qoi_id, x.capability_id))),
        )
        object.__setattr__(
            self,
            "issues",
            tuple(sorted(self.issues, key=lambda x: (x.subject, x.kind.value, x.detail))),
        )

    def screens_for(self, qoi_id: str) -> tuple[QOICapabilityScreen, ...]:
        return tuple(item for item in self.screens if item.qoi_id == qoi_id)

    def eligible_for(self, qoi_id: str) -> tuple[QOICapabilityScreen, ...]:
        return tuple(item for item in self.screens_for(qoi_id) if item.eligible)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": INTENT_VALIDATION_SCHEMA,
            "intent_identity": self.intent_identity,
            "registry_digest": self.registry_digest,
            "readiness": self.readiness.value,
            "screens": [item.to_dict() for item in self.screens],
            "issues": [item.to_dict() for item in self.issues],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "IntentValidation":
        require_schema(payload, INTENT_VALIDATION_SCHEMA)
        return cls(
            intent_identity=payload["intent_identity"],
            registry_digest=payload["registry_digest"],
            readiness=IntentReadiness(payload["readiness"]),
            screens=tuple(
                QOICapabilityScreen.from_dict(item)
                for item in payload.get("screens", ())
            ),
            issues=tuple(
                PlanningIssue.from_dict(item)
                for item in payload.get("issues", ())
            ),
        )


def _plain(value: ScientificValue) -> Any:
    if isinstance(value, Quantity):
        return value
    if isinstance(value, IntegerValue):
        return value.value
    if isinstance(value, BooleanValue):
        return value.value
    if isinstance(value, CategoricalValue):
        return value.value
    raise TypeError(type(value).__name__)


def _facts_by_declared_path(
    intent: EngineeringIntent,
) -> Mapping[str, tuple[tuple[str, ScientificValue], ...]]:
    grouped: dict[str, list[tuple[str, ScientificValue]]] = {}
    for fact in intent.facts:
        grouped.setdefault(declared_path(fact.path), []).append(
            (fact.path, fact.value)
        )
    return {
        key: tuple(sorted(values, key=lambda x: x[0]))
        for key, values in grouped.items()
    }


def _screen(
    intent: EngineeringIntent,
    qoi: IntentQuantityOfInterest,
    declaration: CapabilityDeclaration,
    facts: Mapping[str, tuple[tuple[str, ScientificValue], ...]],
    verification_registry: VerificationPlanningRegistry | None,
) -> QOICapabilityScreen:
    reasons: list[str] = []
    produced = declaration.produced(qoi.name)
    if produced is None:
        reasons.append(f"does not produce {qoi.name!r}")
    elif produced.dimension != qoi.dimension:
        reasons.append(
            f"produces {qoi.name!r} as [{produced.dimension}], "
            f"requested [{qoi.dimension}]"
        )

    required = intent.required_for(qoi)
    missing_science = sorted(
        capability.identifier
        for capability in required - declaration.provided_capabilities
    )
    if missing_science:
        reasons.append(
            f"does not provide required scientific capabilities {missing_science}"
        )
    if not declaration.executable:
        reasons.append("has no executable route in this registry")

    missing_inputs: list[str] = []
    invalid_inputs: list[str] = []
    if not reasons:
        for input_decl in declaration.inputs:
            supplied = facts.get(input_decl.path, ())
            if input_decl.required and not supplied:
                missing_inputs.append(input_decl.path)
                continue
            for actual_path, typed in supplied:
                problem = input_problem(input_decl, actual_path, _plain(typed))
                if problem:
                    invalid_inputs.append(problem)

    evidence_gaps: list[str] = []
    if produced is not None:
        attainable = declaration.attainable(qoi.name)
        for level in intent.context.required_levels:
            if level not in attainable:
                evidence_gaps.append(
                    f"required level {level.value} is not attainable for {qoi.name}"
                )
        if intent.context.require_independent_verification:
            options = (
                ()
                if verification_registry is None
                else verification_registry.independent_options(
                    declaration.capability_id,
                    declaration.primary_route.route_id,
                )
            )
            if not options:
                evidence_gaps.append(
                    "independent verification is required, but no explicit "
                    "planning-time route pair establishes strong/external "
                    "independence; a different route id alone is not evidence "
                    "of independence"
                )

    uncertainty_gaps: list[str] = []
    available_channels = (
        declaration.uncertainty.channels_for(qoi.name)
        if produced
        else frozenset()
    )
    for channel in intent.context.required_uncertainty:
        if channel not in available_channels:
            uncertainty_gaps.append(
                f"required uncertainty channel {channel.value} is not quantified"
            )

    return QOICapabilityScreen(
        qoi_id=qoi.qoi_id,
        capability_id=declaration.capability_id,
        capability_version=declaration.version,
        capability_digest=declaration.digest,
        eligible=not reasons and not invalid_inputs,
        missing_inputs=tuple(missing_inputs),
        invalid_inputs=tuple(invalid_inputs),
        evidence_gaps=tuple(evidence_gaps),
        uncertainty_gaps=tuple(uncertainty_gaps),
        reasons=tuple(reasons),
    )


def validate_intent(
    intent: EngineeringIntent,
    registry: CapabilityRegistry,
    *,
    verification_registry: VerificationPlanningRegistry | None = None,
) -> IntentValidation:
    """Screen one intent against every executable product capability.

    This function never chooses between eligible capabilities. More than one
    eligible capability is an ambiguity for the planner unless an explicit
    PlannerPolicy resolves it later.
    """
    if not isinstance(intent, EngineeringIntent):
        raise TypeError("validate_intent requires EngineeringIntent")
    if not isinstance(registry, CapabilityRegistry):
        raise TypeError("validate_intent requires CapabilityRegistry")

    facts = _facts_by_declared_path(intent)
    screens: list[QOICapabilityScreen] = []
    issues: list[PlanningIssue] = []

    for qoi in intent.qois:
        qoi_screens = tuple(
            _screen(intent, qoi, declaration, facts, verification_registry)
            for declaration in registry.declarations
            if declaration.produced(qoi.name) is not None
        )
        screens.extend(qoi_screens)
        eligible = [item for item in qoi_screens if item.eligible]
        if not qoi_screens or not eligible:
            detail = (
                f"no registered executable capability can produce {qoi.name!r} "
                f"in [{qoi.dimension}] with the requested scientific capabilities"
            )
            issues.append(
                PlanningIssue(
                    IssueKind.NO_CAPABILITY,
                    qoi.qoi_id,
                    detail,
                    True,
                )
            )
            continue
        if len(eligible) > 1:
            issues.append(
                PlanningIssue(
                    IssueKind.AMBIGUOUS_CAPABILITY,
                    qoi.qoi_id,
                    f"eligible capabilities are "
                    f"{[item.capability_id for item in eligible]}; "
                    "selection must be explicit",
                    True,
                )
            )
        for candidate in eligible:
            for path in candidate.missing_inputs:
                issues.append(
                    PlanningIssue(
                        IssueKind.MISSING_INPUT,
                        f"{qoi.qoi_id}:{candidate.capability_id}:{path}",
                        f"{candidate.capability_id} requires {path}",
                        True,
                    )
                )
            for detail in candidate.invalid_inputs:
                issues.append(
                    PlanningIssue(
                        IssueKind.INVALID_INPUT,
                        f"{qoi.qoi_id}:{candidate.capability_id}",
                        detail,
                        True,
                    )
                )
            for detail in candidate.evidence_gaps:
                kind = (
                    IssueKind.INDEPENDENT_ROUTE_UNAVAILABLE
                    if "independent verification" in detail
                    else IssueKind.EVIDENCE_UNATTAINABLE
                )
                issues.append(
                    PlanningIssue(
                        kind,
                        f"{qoi.qoi_id}:{candidate.capability_id}",
                        detail,
                        False,
                    )
                )
            for detail in candidate.uncertainty_gaps:
                issues.append(
                    PlanningIssue(
                        IssueKind.UNCERTAINTY_UNAVAILABLE,
                        f"{qoi.qoi_id}:{candidate.capability_id}",
                        detail,
                        False,
                    )
                )

    if any(issue.kind is IssueKind.NO_CAPABILITY for issue in issues):
        readiness = IntentReadiness.UNSUPPORTED
    elif any(issue.blocking for issue in issues):
        readiness = IntentReadiness.NEEDS_CLARIFICATION
    else:
        readiness = IntentReadiness.READY

    return IntentValidation(
        intent_identity=intent.identity_digest,
        registry_digest=registry.digest,
        readiness=readiness,
        screens=tuple(screens),
        issues=tuple(issues),
    )


__all__ = [
    "INTENT_VALIDATION_SCHEMA",
    "PLANNING_ISSUE_SCHEMA",
    "QOI_SCREEN_SCHEMA",
    "IntentReadiness",
    "IntentValidation",
    "IssueKind",
    "PlanningIssue",
    "QOICapabilityScreen",
    "validate_intent",
]
