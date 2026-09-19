"""Phase 3 -- risk-aware evidence policy: the risk of a decision sets the evidence bar, and nothing else.

The generic principle (the ICH M15 / ASME V&V 40 "credibility by risk" idea,
stated without any domain in it):

    Question of Interest -> Context of Use -> Model Influence
        -> Consequence of a wrong decision -> Decision/model risk
        -> the evidence the decision requires

Ownership is split deliberately:

* **The caller or the organization owns consequence and influence.** Nothing
  here infers "high consequence" from prose; a :class:`DecisionContext` states
  both, names who assigned the consequence, and says why.
* **Forge owns the evaluation**: a versioned, digest-bound
  :class:`EvidencePolicyProfile` maps (influence, consequence) to a
  :class:`RiskClass` through its own matrix, and each risk class to an
  :class:`EvidencePolicy`. There is no universal matrix: profiles differ
  (``research_exploration``, ``engineering_decision``,
  ``high_consequence_engineering``, or an organization's own).

Two properties are load-bearing and enforced at construction, for every profile:

1. **Risk never lowers the bar within a profile.** The matrix is monotone in
   influence and in consequence, and every risk class's policy *covers* the
   one below it (a superset of levels and channels, every flag implied, any
   coverage factor at least as large).
2. **A policy grants nothing.** :func:`apply_policy` only *adds* requirements
   to the claim's own -- a union of levels and channels, OR of the flags, the
   larger coverage factor -- and the requirements a claim cannot state
   (validation evidence, an independent route, applicability) are checked
   against the run's own records by :func:`policy_findings`. Risk is never
   evidence: a satisfied policy makes a claim *eligible* to be decided, it
   supports nothing.

The profile is carried inside the decision context, so the context's digest --
and through the claim's identity the plan, the charter and every
``context_ref`` -- changes whenever the policy does. A profile whose id is a
built-in id must be byte-for-byte that built-in (digest-pinned); an
organization's own profile uses its own id.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Mapping

from ...scientific.results.validation import ValidationLevel
from ...scientific.serialization import schema_string
from ...sria.uncertainty import UncertaintyChannel
from .._records import (
    require_bool,
    require_keys,
    require_list,
    require_mapping,
    require_schema_exact,
    require_text,
    tagged_digest,
)
from ..errors import ClaimContractError

POLICY_SCHEMA = schema_string("claim_evidence_policy")
PROFILE_SCHEMA = schema_string("claim_evidence_policy_profile")
CONTEXT_SCHEMA = schema_string("claim_decision_context")
_PROFILE_TAG = "crafty.claims.policy_profile/1"
_CONTEXT_TAG = "crafty.claims.decision_context/1"
_REQUIREMENT_TAG = "crafty.claims.derived_requirement/1"


class ModelInfluence(str, Enum):
    """How much the model's output weighs in the decision, beside other evidence."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DecisionConsequence(str, Enum):
    """How bad a wrong decision would be. Assigned by the caller or organization, never inferred."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RiskClass(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


_ORDER = {"low": 0, "medium": 1, "high": 2}


def _rank(member: Enum) -> int:
    return _ORDER[member.value]


@dataclass(frozen=True)
class EvidencePolicy:
    """What a decision at one risk class requires. Requirements only; never evidence."""

    required_levels: frozenset[ValidationLevel] = frozenset()
    required_channels: frozenset[UncertaintyChannel] = frozenset()
    coverage_factor: float | None = None
    require_supported_discrepancy: bool = False
    #: The credibility report's evidence basis must be VALIDATED: something outside the model was compared.
    require_validation_evidence: bool = False
    #: A route independent of the primary solve (analytic reference, benchmark, independent solver,
    #: experiment) must be active and its level attained.
    require_independent_route: bool = False
    #: Every model the run used must be IN_DOMAIN (stated explicitly, although the credibility verdict
    #: already refuses UNKNOWN and OUTSIDE applicability).
    require_applicability: bool = False

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "required_levels", frozenset(ValidationLevel(v) for v in self.required_levels))
            object.__setattr__(self, "required_channels", frozenset(UncertaintyChannel(c) for c in self.required_channels))
        except ValueError as exc:
            raise ClaimContractError(f"evidence policy: {exc}") from exc
        if ValidationLevel.UNVERIFIED in self.required_levels:
            raise ClaimContractError("a policy cannot require UNVERIFIED")
        if self.coverage_factor is not None:
            if isinstance(self.coverage_factor, bool) or not isinstance(self.coverage_factor, (int, float)) or not self.coverage_factor > 0:
                raise ClaimContractError("policy coverage_factor must be positive or null")
            object.__setattr__(self, "coverage_factor", float(self.coverage_factor))
        for flag in ("require_supported_discrepancy", "require_validation_evidence", "require_independent_route", "require_applicability"):
            require_bool(getattr(self, flag), field=f"policy.{flag}")

    def covers(self, other: "EvidencePolicy") -> bool:
        """Whether this policy demands at least everything ``other`` demands."""
        if not (self.required_levels >= other.required_levels and self.required_channels >= other.required_channels):
            return False
        for flag in ("require_supported_discrepancy", "require_validation_evidence", "require_independent_route", "require_applicability"):
            if getattr(other, flag) and not getattr(self, flag):
                return False
        if other.coverage_factor is not None and (self.coverage_factor is None or self.coverage_factor < other.coverage_factor):
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": POLICY_SCHEMA,
            "required_levels": sorted(l.value for l in self.required_levels),
            "required_channels": sorted(c.value for c in self.required_channels),
            "coverage_factor": self.coverage_factor,
            "require_supported_discrepancy": self.require_supported_discrepancy,
            "require_validation_evidence": self.require_validation_evidence,
            "require_independent_route": self.require_independent_route,
            "require_applicability": self.require_applicability,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidencePolicy":
        payload = require_mapping(payload, field="evidence policy")
        keys = ("schema", "required_levels", "required_channels", "coverage_factor", "require_supported_discrepancy",
                "require_validation_evidence", "require_independent_route", "require_applicability")
        require_keys(payload, required=keys, record="evidence policy")
        require_schema_exact(payload, POLICY_SCHEMA, record="evidence policy")
        return cls(
            frozenset(require_list(payload["required_levels"], field="required_levels")),
            frozenset(require_list(payload["required_channels"], field="required_channels")),
            payload["coverage_factor"],
            payload["require_supported_discrepancy"],
            payload["require_validation_evidence"],
            payload["require_independent_route"],
            payload["require_applicability"],
        )


def _matrix_key(influence: ModelInfluence, consequence: DecisionConsequence) -> str:
    return f"{influence.value}/{consequence.value}"


@dataclass(frozen=True)
class EvidencePolicyProfile:
    """An organization's or domain's policy: a risk matrix and the evidence each risk class requires."""

    profile_id: str
    version: str
    description: str
    risk_matrix: Mapping[str, RiskClass]
    policies: Mapping[RiskClass, EvidencePolicy]

    def __post_init__(self) -> None:
        object.__setattr__(self, "profile_id", require_text(self.profile_id, field="profile.profile_id"))
        object.__setattr__(self, "version", require_text(self.version, field="profile.version"))
        object.__setattr__(self, "description", require_text(self.description, field="profile.description"))
        matrix = {}
        for key, value in require_mapping(self.risk_matrix, field="profile.risk_matrix").items():
            try:
                matrix[str(key)] = RiskClass(value)
            except ValueError as exc:
                raise ClaimContractError(f"profile risk matrix: {exc}") from exc
        expected = {_matrix_key(i, c) for i in ModelInfluence for c in DecisionConsequence}
        if set(matrix) != expected:
            raise ClaimContractError(
                f"a profile's risk matrix names every influence/consequence cell exactly once; missing "
                f"{sorted(expected - set(matrix))}, unknown {sorted(set(matrix) - expected)}"
            )
        object.__setattr__(self, "risk_matrix", dict(sorted(matrix.items())))
        policies = {}
        for key, value in require_mapping(self.policies, field="profile.policies").items():
            if not isinstance(value, EvidencePolicy):
                raise ClaimContractError("profile policies must be EvidencePolicy records")
            policies[RiskClass(key)] = value
        if set(policies) != set(RiskClass):
            raise ClaimContractError("a profile states a policy for every risk class")
        object.__setattr__(self, "policies", {r: policies[r] for r in RiskClass})
        # Invariant 13: within one profile, more risk never demands less evidence.
        for influence in ModelInfluence:
            for consequence in DecisionConsequence:
                here = _rank(matrix[_matrix_key(influence, consequence)])
                for more_i in ModelInfluence:
                    for more_c in DecisionConsequence:
                        if _rank(more_i) >= _rank(influence) and _rank(more_c) >= _rank(consequence):
                            if _rank(matrix[_matrix_key(more_i, more_c)]) < here:
                                raise ClaimContractError(
                                    f"profile {self.profile_id}: the risk matrix is not monotone -- "
                                    f"{more_i.value}/{more_c.value} is classed below {influence.value}/{consequence.value}"
                                )
        ordered = list(RiskClass)
        for lower, higher in zip(ordered, ordered[1:]):
            if not policies[higher].covers(policies[lower]):
                raise ClaimContractError(
                    f"profile {self.profile_id}: the {higher.value} policy demands less than the {lower.value} "
                    f"policy; a higher risk may require more evidence, never less"
                )

    def risk_class(self, influence: ModelInfluence, consequence: DecisionConsequence) -> RiskClass:
        return self.risk_matrix[_matrix_key(ModelInfluence(influence), DecisionConsequence(consequence))]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PROFILE_SCHEMA,
            "profile_id": self.profile_id,
            "version": self.version,
            "description": self.description,
            "risk_matrix": {k: v.value for k, v in self.risk_matrix.items()},
            "policies": {r.value: self.policies[r].to_dict() for r in RiskClass},
        }

    @property
    def digest(self) -> str:
        return tagged_digest(_PROFILE_TAG, self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidencePolicyProfile":
        payload = require_mapping(payload, field="policy profile")
        require_keys(payload, required=("schema", "profile_id", "version", "description", "risk_matrix", "policies"), record="policy profile")
        require_schema_exact(payload, PROFILE_SCHEMA, record="policy profile")
        policies = require_mapping(payload["policies"], field="profile.policies")
        return cls(
            payload["profile_id"], payload["version"], payload["description"], payload["risk_matrix"],
            {RiskClass(k): EvidencePolicy.from_dict(v) for k, v in policies.items()},
        )


def _matrix(rows: Mapping[ModelInfluence, tuple[RiskClass, RiskClass, RiskClass]]) -> dict[str, RiskClass]:
    return {_matrix_key(i, c): rows[i][k] for i in ModelInfluence for k, c in enumerate(DecisionConsequence)}


L, M, H = RiskClass.LOW, RiskClass.MEDIUM, RiskClass.HIGH
_NUM, _PAR, _MF = UncertaintyChannel.NUMERICAL, UncertaintyChannel.EPISTEMIC_PARAMETER, UncertaintyChannel.MODEL_FORM

#: Built-in profiles. Their ids are reserved: a context naming one must carry exactly this profile.
BUILTIN_PROFILES: Mapping[str, EvidencePolicyProfile] = {
    p.profile_id: p
    for p in (
        EvidencePolicyProfile(
            "research_exploration", "1",
            "Exploratory research: the claim's own bar, with an independent check once the model carries the decision.",
            _matrix({ModelInfluence.LOW: (L, L, L), ModelInfluence.MEDIUM: (L, L, M), ModelInfluence.HIGH: (L, M, M)}),
            {
                L: EvidencePolicy(),
                M: EvidencePolicy(require_independent_route=True),
                H: EvidencePolicy(required_channels=frozenset({_NUM}), require_independent_route=True),
            },
        ),
        EvidencePolicyProfile(
            "engineering_decision", "1",
            "An engineering decision: an independent route always; quantified numerical and parameter uncertainty and "
            "validation evidence as influence and consequence rise.",
            _matrix({ModelInfluence.LOW: (L, L, M), ModelInfluence.MEDIUM: (L, M, H), ModelInfluence.HIGH: (M, H, H)}),
            {
                L: EvidencePolicy(require_independent_route=True, require_applicability=True),
                M: EvidencePolicy(required_channels=frozenset({_NUM}), require_independent_route=True, require_applicability=True),
                H: EvidencePolicy(
                    required_channels=frozenset({_NUM, _PAR}), require_validation_evidence=True,
                    require_independent_route=True, require_applicability=True,
                ),
            },
        ),
        EvidencePolicyProfile(
            "high_consequence_engineering", "1",
            "A high-consequence decision: applicability, quantified uncertainty, external validation, an independent "
            "route and treated model discrepancy at the top risk class.",
            _matrix({ModelInfluence.LOW: (L, M, H), ModelInfluence.MEDIUM: (M, H, H), ModelInfluence.HIGH: (H, H, H)}),
            {
                L: EvidencePolicy(required_channels=frozenset({_NUM}), require_independent_route=True, require_applicability=True),
                M: EvidencePolicy(
                    required_channels=frozenset({_NUM, _PAR}), require_validation_evidence=True,
                    require_independent_route=True, require_applicability=True,
                ),
                H: EvidencePolicy(
                    required_channels=frozenset({_NUM, _PAR, _MF}), require_supported_discrepancy=True,
                    require_validation_evidence=True, require_independent_route=True, require_applicability=True,
                ),
            },
        ),
    )
}


@dataclass(frozen=True)
class DecisionContext:
    """The decision a claim serves, as the caller or organization states it. Part of the claim's identity."""

    question_of_interest: str
    context_of_use: str
    model_influence: ModelInfluence
    decision_consequence: DecisionConsequence
    consequence_owner: str
    rationale: str
    profile: EvidencePolicyProfile

    def __post_init__(self) -> None:
        for label in ("question_of_interest", "context_of_use", "consequence_owner", "rationale"):
            object.__setattr__(self, label, require_text(getattr(self, label), field=f"decision_context.{label}"))
        try:
            object.__setattr__(self, "model_influence", ModelInfluence(self.model_influence))
            object.__setattr__(self, "decision_consequence", DecisionConsequence(self.decision_consequence))
        except ValueError as exc:
            raise ClaimContractError(f"decision_context: {exc}") from exc
        if not isinstance(self.profile, EvidencePolicyProfile):
            raise ClaimContractError("decision_context.profile must be an EvidencePolicyProfile")
        builtin = BUILTIN_PROFILES.get(self.profile.profile_id)
        if builtin is not None and builtin.digest != self.profile.digest:
            raise ClaimContractError(
                f"profile id {self.profile.profile_id!r} is a built-in profile and this is not it (digest "
                f"{self.profile.digest[:12]} != {builtin.digest[:12]}); an organization's profile uses its own id"
            )

    @property
    def risk_class(self) -> RiskClass:
        return self.profile.risk_class(self.model_influence, self.decision_consequence)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CONTEXT_SCHEMA,
            "question_of_interest": self.question_of_interest,
            "context_of_use": self.context_of_use,
            "model_influence": self.model_influence.value,
            "decision_consequence": self.decision_consequence.value,
            "consequence_owner": self.consequence_owner,
            "rationale": self.rationale,
            "profile": self.profile.to_dict(),
            "profile_digest": self.profile.digest,
        }

    @property
    def digest(self) -> str:
        return tagged_digest(_CONTEXT_TAG, self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DecisionContext":
        payload = require_mapping(payload, field="decision_context")
        keys = ("schema", "question_of_interest", "context_of_use", "model_influence", "decision_consequence",
                "consequence_owner", "rationale", "profile", "profile_digest")
        require_keys(payload, required=keys, record="decision_context")
        require_schema_exact(payload, CONTEXT_SCHEMA, record="decision_context")
        profile = EvidencePolicyProfile.from_dict(payload["profile"])
        if profile.digest != payload["profile_digest"]:
            raise ClaimContractError("decision_context.profile_digest is not the digest of the profile it carries")
        return cls(
            payload["question_of_interest"], payload["context_of_use"], payload["model_influence"],
            payload["decision_consequence"], payload["consequence_owner"], payload["rationale"], profile,
        )


def builtin_context(profile_id: str, *, influence: str, consequence: str, owner: str, question: str = "stated by the caller",
                    context_of_use: str = "stated by the caller", rationale: str = "assigned by the owner") -> DecisionContext:
    """A context under a built-in profile. Convenience only; every field is still the caller's statement."""
    return DecisionContext(question, context_of_use, influence, consequence, owner, rationale, BUILTIN_PROFILES[profile_id])


@dataclass(frozen=True)
class DerivedEvidenceRequirement:
    """The evidence bar a decision context implies under its profile. Deterministic; not evidence."""

    context_digest: str
    profile_id: str
    profile_version: str
    profile_digest: str
    model_influence: ModelInfluence
    decision_consequence: DecisionConsequence
    risk_class: RiskClass
    policy: EvidencePolicy

    def to_dict(self) -> dict[str, Any]:
        return {
            "context_digest": self.context_digest,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "profile_digest": self.profile_digest,
            "model_influence": self.model_influence.value,
            "decision_consequence": self.decision_consequence.value,
            "risk_class": self.risk_class.value,
            "policy": self.policy.to_dict(),
        }

    @property
    def digest(self) -> str:
        return tagged_digest(_REQUIREMENT_TAG, self.to_dict())


def derive_requirement(context: DecisionContext) -> DerivedEvidenceRequirement:
    risk = context.risk_class
    return DerivedEvidenceRequirement(
        context_digest=context.digest,
        profile_id=context.profile.profile_id,
        profile_version=context.profile.version,
        profile_digest=context.profile.digest,
        model_influence=context.model_influence,
        decision_consequence=context.decision_consequence,
        risk_class=risk,
        policy=context.profile.policies[risk],
    )


def apply_policy(claim: Any) -> Any:
    """The claim with its policy's requirements added to its own. Only adds; idempotent; no context: unchanged."""
    from ..contract import EvidenceRequirement, UncertaintyDemand

    context = getattr(claim, "decision_context", None)
    if context is None:
        return claim
    policy = derive_requirement(context).policy
    levels = tuple(sorted(set(claim.evidence.required_levels) | set(policy.required_levels), key=list(ValidationLevel).index))
    channels = frozenset(claim.uncertainty.required_channels) | policy.required_channels
    k = claim.uncertainty.coverage_factor
    if policy.coverage_factor is not None and channels:
        k = policy.coverage_factor if k is None else max(k, policy.coverage_factor)
    evidence = EvidenceRequirement(levels)
    uncertainty = UncertaintyDemand(channels, k if channels else None,
                                    claim.uncertainty.require_supported_discrepancy or policy.require_supported_discrepancy)
    if evidence == claim.evidence and uncertainty == claim.uncertainty:
        return claim
    return replace(claim, evidence=evidence, uncertainty=uncertainty)


_INDEPENDENT_ROUTE_CLASSES = frozenset({"independent", "analytic_reference", "benchmark", "experimental"})


def policy_findings(requirement: DerivedEvidenceRequirement, plan: Any, report: Any) -> list[dict[str, str]]:
    """The policy requirements a claim cannot state, checked against the run's own records.

    Each finding names the requirement and the authoritative record it was read from. Empty: satisfied.
    """
    policy = requirement.policy
    findings: list[dict[str, str]] = []
    if policy.require_applicability:
        outside = sorted(f"{r.model_id}={r.assessment.status.value}" for r in report.validity if r.assessment.status.value != "in_domain")
        if outside or not report.validity:
            findings.append({
                "requirement": "applicability",
                "reason": f"every model must be IN_DOMAIN; the run records {outside or 'no validity records'}",
                "source": "/validity",
            })
    if policy.require_validation_evidence and report.evidence_basis != "VALIDATED":
        findings.append({
            "requirement": "validation_evidence",
            "reason": f"the decision requires validation evidence; the run's evidence basis is {report.evidence_basis}",
            "source": "/credibility/evidence_basis",
        })
    if policy.require_independent_route:
        attained = {l.value for l in report.attained_levels}
        independent = [
            r for r in plan.content["routes"]
            if r["route_class"] in _INDEPENDENT_ROUTE_CLASSES and r["active"] and r["could_establish"] in attained
        ]
        if not independent:
            findings.append({
                "requirement": "independent_route",
                "reason": "no route independent of the primary solve was active and attained its level in this run",
                "source": "/plan/content/routes",
            })
    return findings


__all__ = [
    "BUILTIN_PROFILES",
    "DecisionConsequence",
    "DecisionContext",
    "DerivedEvidenceRequirement",
    "EvidencePolicy",
    "EvidencePolicyProfile",
    "ModelInfluence",
    "RiskClass",
    "apply_policy",
    "builtin_context",
    "derive_requirement",
    "policy_findings",
]
