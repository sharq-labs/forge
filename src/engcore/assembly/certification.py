"""The certification gate: a versioned policy, and evidence that fails closed.

WHAT CHANGED AND WHY
---------------------
Three of the questions this gate used to answer were weaker than they read.

``system_validation_passed`` asked whether every validation result *present*
was valid. A pack declaring four validation protocols and running one passed
it. Completeness is an exact-set question -- required against executed -- and
it is now asked as one, separately, in both directions.

``uncertainty_authority_satisfied`` asked whether a producer was pinned and
whether *some* result existed. It could not say which quantity on which channel
was covered. The quantity x channel matrix now says, per cell, quantified /
unknown / missing / not applicable, and ``UNKNOWN`` is never read as zero.

``replay_roundtrip_verified`` was a serialization roundtrip wearing the word
replay. It is renamed to ``serialization_roundtrip_verified``, which is what it
checks and is worth checking; actual re-execution is a different gate fed by
:mod:`engcore.assembly.replay`.

THE POLICY IS THE THING THAT DECIDES
-------------------------------------
Gates are evaluated whether or not a policy requires them, because a gap that
is not evaluated cannot be seen. What a policy decides is which gaps *block*.
The certificate carries the required gates -- so a failing required gate makes
the record refuse -- and pins the digest of the complete assessment, including
the non-required evaluations that failed, as an artifact. A reader of the
certificate can therefore tell the difference between "everything was checked
and passed" and "everything required by this policy passed", which are not the
same sentence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .multiphysics import AuthorizedMultiphysicsRun
from .replay import DEFAULT_REPLAY_POLICY, ReplayOutcome, ReplayPolicy
from .trust import (
    NumericalRequirement,
    ProtocolCompleteness,
    UQCoverage,
    assess_numerical_completeness,
    assess_protocol_completeness,
    assess_uq_coverage,
    authorized_run_binding,
    evidence_digest,
)
from ..scientific.certification_core.artifact import CertificationArtifact
from ..scientific.certification_core.gate import CertificationGateResult
from ..scientific.certification_core.profile import CertificationProfile
from ..scientific.certification_core.record import CertificationRecord
from ..scientific.corpus.authority import (
    NUMERICAL_EXECUTION_PROFILE,
    VALIDATION_AUTHORITY_PROFILE,
)
from ..scientific.corpus.envelope import (
    EnvelopeVerdict,
    ValidationEnvelope,
    ValidationQueryPoint,
)
from ..scientific.corpus.numerical import NumericalCheck, NumericalEvidence
from ..scientific.errors import InvalidScientificProblem
from ..scientific.results.uncertainty import UncertaintySource
from ..scientific.verification.adjudication import VerificationDecision

AUTHORITY_CHAIN_PINNED = "authority_chain_pinned"
SYSTEM_VALIDATION_PASSED = "system_validation_passed"
VALIDATION_PROTOCOL_COMPLETENESS = "validation_protocol_completeness"
VERIFICATION_PROTOCOL_COMPLETENESS = "verification_protocol_completeness"
INDEPENDENT_VERIFICATION_PASSED = "independent_verification_passed"
UNCERTAINTY_AUTHORITY_SATISFIED = "uncertainty_authority_satisfied"
UQ_CHANNEL_COMPLETENESS = "uq_channel_completeness"
SERIALIZATION_ROUNDTRIP_VERIFIED = "serialization_roundtrip_verified"
COMPUTATIONAL_REPLAY_VERIFIED = "computational_replay_verified"
NUMERICAL_EVIDENCE_PRESENT = "numerical_evidence_present"
VALIDATION_ENVELOPE_SUPPORTED = "validation_envelope_supported"

ALL_GATES = (
    AUTHORITY_CHAIN_PINNED,
    SYSTEM_VALIDATION_PASSED,
    VALIDATION_PROTOCOL_COMPLETENESS,
    VERIFICATION_PROTOCOL_COMPLETENESS,
    INDEPENDENT_VERIFICATION_PASSED,
    UNCERTAINTY_AUTHORITY_SATISFIED,
    UQ_CHANNEL_COMPLETENESS,
    SERIALIZATION_ROUNDTRIP_VERIFIED,
    COMPUTATIONAL_REPLAY_VERIFIED,
    NUMERICAL_EVIDENCE_PRESENT,
    VALIDATION_ENVELOPE_SUPPORTED,
)


@dataclass(frozen=True)
class TrustPolicy:
    """Which gaps block certification, under a name and a version.

    A policy that required everything would be the only honest one if the
    evidence existed. It does not yet for every blueprint, and a policy that
    silently required less than it claimed would be worse than one that says
    which gates it treats as advisory. So both sets are explicit and the
    policy's own digest is pinned into the certificate.
    """

    policy_id: str
    version: str
    required_gates: tuple[str, ...]
    recorded_gates: tuple[str, ...] = ()
    #: Which envelope verdicts count as entitlement to predict. A policy that
    #: accepted SPARSE_SUPPORT or EXTRAPOLATING would be saying so out loud
    #: rather than reaching that position by never asking about the point.
    accepted_envelope_verdicts: tuple[str, ...] = (EnvelopeVerdict.SUPPORTED.value,)
    #: What numerical credibility this policy requires. ``None`` means the
    #: policy has NOT SAID, which is not the same as requiring nothing and
    #: cannot be satisfied by producing nothing.
    numerical_requirement: NumericalRequirement | None = None

    def __post_init__(self) -> None:
        for label in ("policy_id", "version"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidScientificProblem(f"trust policy requires {label}")
            object.__setattr__(self, label, value)
        required = tuple(str(item).strip() for item in self.required_gates)
        recorded = tuple(str(item).strip() for item in self.recorded_gates)
        if not required:
            raise InvalidScientificProblem(
                "a trust policy that requires no gate certifies nothing"
            )
        unknown = sorted(set(required + recorded) - set(ALL_GATES))
        if unknown:
            raise InvalidScientificProblem(
                f"trust policy names gates this gate cannot evaluate: {unknown}"
            )
        overlap = sorted(set(required) & set(recorded))
        if overlap:
            raise InvalidScientificProblem(
                f"gates {overlap} are both required and merely recorded; a gate "
                f"either blocks or it does not"
            )
        object.__setattr__(self, "required_gates", tuple(sorted(set(required))))
        object.__setattr__(self, "recorded_gates", tuple(sorted(set(recorded))))
        accepted = tuple(
            sorted({EnvelopeVerdict(item).value for item in self.accepted_envelope_verdicts})
        )
        if not accepted:
            raise InvalidScientificProblem(
                "a policy accepting no envelope verdict can never be satisfied"
            )
        object.__setattr__(self, "accepted_envelope_verdicts", accepted)
        if self.numerical_requirement is not None and not isinstance(
            self.numerical_requirement, NumericalRequirement
        ):
            raise InvalidScientificProblem(
                "numerical_requirement must be a NumericalRequirement or None"
            )

    @property
    def evaluated_gates(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.required_gates) | set(self.recorded_gates)))

    @property
    def profile(self) -> CertificationProfile:
        return CertificationProfile(
            profile_id=f"{self.policy_id}/{self.version}",
            required_gates=self.required_gates,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "required_gates": list(self.required_gates),
            "recorded_gates": list(self.recorded_gates),
            "accepted_envelope_verdicts": list(self.accepted_envelope_verdicts),
            "numerical_requirement": (
                None
                if self.numerical_requirement is None
                else self.numerical_requirement.to_dict()
            ),
        }

    @property
    def digest(self) -> str:
        return evidence_digest(self.to_dict())


#: The production posture. Authority, validation, verification and
#: serialization integrity block. The four Sprint 2 gates that need evidence
#: production does not yet produce for every blueprint -- the UQ matrix, an
#: actual re-execution, a numerical roster and a validated envelope -- are
#: evaluated and recorded, and a reader can see exactly which of them is short.
MULTIPHYSICS_PRODUCTION_POLICY = TrustPolicy(
    policy_id="forge.multiphysics.production",
    version="2",
    required_gates=(
        AUTHORITY_CHAIN_PINNED,
        SYSTEM_VALIDATION_PASSED,
        VALIDATION_PROTOCOL_COMPLETENESS,
        VERIFICATION_PROTOCOL_COMPLETENESS,
        INDEPENDENT_VERIFICATION_PASSED,
        UNCERTAINTY_AUTHORITY_SATISFIED,
        SERIALIZATION_ROUNDTRIP_VERIFIED,
    ),
    recorded_gates=(
        UQ_CHANNEL_COMPLETENESS,
        COMPUTATIONAL_REPLAY_VERIFIED,
        NUMERICAL_EVIDENCE_PRESENT,
        VALIDATION_ENVELOPE_SUPPORTED,
    ),
    numerical_requirement=NumericalRequirement(
        "forge.multiphysics.production.numerical", (NumericalCheck.CONVERGENCE.value,)
    ),
)

#: Every gate blocks. This is what a claim of full scientific trust costs, and
#: it exists so that "we are not there yet" is a statement about the evidence
#: rather than about the absence of a standard.
MULTIPHYSICS_FULL_TRUST_POLICY = TrustPolicy(
    policy_id="forge.multiphysics.full_trust",
    version="1",
    required_gates=ALL_GATES,
    # Only demonstrated support entitles a prediction. Sparse evidence,
    # extrapolation, a failing region and an unlocatable point all fail.
    accepted_envelope_verdicts=(EnvelopeVerdict.SUPPORTED.value,),
    numerical_requirement=NumericalRequirement(
        "forge.multiphysics.full_trust.numerical", (NumericalCheck.CONVERGENCE.value,)
    ),
)

#: Kept for readers of older certificates: the V1 profile this gate emitted
#: before completeness and real replay existed.
MULTIPHYSICS_PRODUCTION_PROFILE = MULTIPHYSICS_PRODUCTION_POLICY.profile


@dataclass(frozen=True, order=True)
class TrustGateEvaluation:
    """One gate, its verdict, whether it blocks, and the evidence behind it."""

    gate_id: str
    passed: bool
    required: bool
    evidence: Mapping[str, Any]

    def __post_init__(self) -> None:
        gate = str(self.gate_id).strip()
        if gate not in ALL_GATES:
            raise InvalidScientificProblem(f"unknown trust gate {gate!r}")
        object.__setattr__(self, "gate_id", gate)
        for label in ("passed", "required"):
            if not isinstance(getattr(self, label), bool):
                raise InvalidScientificProblem(f"trust gate {label} must be boolean")
        object.__setattr__(self, "evidence", dict(self.evidence))

    @property
    def digest(self) -> str:
        return evidence_digest(dict(self.evidence))

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "passed": self.passed,
            "required": self.required,
            "evidence_digest": self.digest,
            "evidence": dict(self.evidence),
        }

    def as_gate_result(self) -> CertificationGateResult:
        return CertificationGateResult(
            gate_id=self.gate_id, passed=self.passed, evidence_digest=self.digest
        )


@dataclass(frozen=True)
class TrustAssessment:
    """Every gate this policy evaluated, blocking and advisory alike."""

    policy: TrustPolicy
    evaluations: tuple[TrustGateEvaluation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.policy, TrustPolicy):
            raise InvalidScientificProblem("a trust assessment requires a TrustPolicy")
        evaluations = tuple(sorted(self.evaluations))
        if any(not isinstance(item, TrustGateEvaluation) for item in evaluations):
            raise InvalidScientificProblem(
                "a trust assessment requires TrustGateEvaluation records"
            )
        ids = [item.gate_id for item in evaluations]
        if len(ids) != len(set(ids)):
            raise InvalidScientificProblem("trust assessment repeats a gate")
        missing = sorted(set(self.policy.evaluated_gates) - set(ids))
        if missing:
            raise InvalidScientificProblem(
                f"trust assessment does not evaluate every gate its policy names: "
                f"{missing}"
            )
        object.__setattr__(self, "evaluations", evaluations)

    def gate(self, gate_id: str) -> TrustGateEvaluation:
        for item in self.evaluations:
            if item.gate_id == gate_id:
                return item
        raise InvalidScientificProblem(f"gate {gate_id!r} was not evaluated")

    @property
    def unmet_required(self) -> tuple[str, ...]:
        return tuple(
            item.gate_id for item in self.evaluations if item.required and not item.passed
        )

    @property
    def recorded_gaps(self) -> tuple[str, ...]:
        """Gates that failed but do not block under this policy. The visible debt."""
        return tuple(
            item.gate_id
            for item in self.evaluations
            if not item.required and not item.passed
        )

    @property
    def satisfied(self) -> bool:
        return not self.unmet_required

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy.to_dict(),
            "evaluations": [item.to_dict() for item in self.evaluations],
            "unmet_required": list(self.unmet_required),
            "recorded_gaps": list(self.recorded_gaps),
            "satisfied": self.satisfied,
        }

    @property
    def digest(self) -> str:
        return evidence_digest(self.to_dict())


def _validation_completeness(
    authorized: AuthorizedMultiphysicsRun,
) -> ProtocolCompleteness:
    return assess_protocol_completeness(
        authorized.composition_snapshot,
        authorized.graph_plan.blueprint_id,
        "validation",
        tuple(
            (item.protocol_id, item.protocol_version)
            for item in authorized.system_validation
        ),
    )


def _verification_completeness(
    authorized: AuthorizedMultiphysicsRun,
) -> ProtocolCompleteness:
    return assess_protocol_completeness(
        authorized.composition_snapshot,
        authorized.graph_plan.blueprint_id,
        "verification",
        tuple(
            (item.protocol_id, item.protocol_version)
            for item in authorized.system_verification
        ),
    )


def _uq_coverage(authorized: AuthorizedMultiphysicsRun) -> UQCoverage:
    produced = {
        (item.result.quantity, item.result.channel.value): (
            item.result.uncertainty,
            item.result.method_id,
        )
        for item in authorized.system_uncertainty
    }
    return assess_uq_coverage(
        authorized.composition_snapshot, authorized.graph_plan.blueprint_id, produced
    )


def assess_authorized_multiphysics_run(
    authorized: AuthorizedMultiphysicsRun,
    *,
    policy: TrustPolicy = MULTIPHYSICS_PRODUCTION_POLICY,
    replay: ReplayOutcome | None = None,
    replay_policy: ReplayPolicy = DEFAULT_REPLAY_POLICY,
    numerical: NumericalEvidence | None = None,
    envelope: ValidationEnvelope | None = None,
    envelope_queries: tuple[ValidationQueryPoint, ...] = (),
) -> TrustAssessment:
    """Evaluate every gate the policy names, and say which of them block.

    Absent evidence never passes a gate. A run with no replay outcome fails
    ``computational_replay_verified``; whether that stops certification is the
    policy's decision, not this function's.
    """
    if not isinstance(authorized, AuthorizedMultiphysicsRun):
        raise TypeError(
            "assess_authorized_multiphysics_run requires AuthorizedMultiphysicsRun"
        )
    if not isinstance(policy, TrustPolicy):
        raise TypeError("assess_authorized_multiphysics_run requires a TrustPolicy")

    graph_plan = authorized.graph_plan
    composition = authorized.composition_snapshot
    execution = authorized.execution_snapshot
    findings: dict[str, tuple[bool, dict[str, Any]]] = {}

    authority_checks = {
        "composition_plan_matches_snapshot": (
            graph_plan.authority_pack_digest == composition.authority_digest
        ),
        "execution_plan_matches_snapshot": (
            graph_plan.execution_pack_digest == execution.authority_digest
        ),
        "execution_bound_to_composition": (
            execution.composition_authority_digest == composition.authority_digest
        ),
        "graph_matches_executed_graph": graph_plan.graph == authorized.run.graph,
        "coupling_plan_matches_execution": (
            graph_plan.coupling_plan == authorized.run.plan
        ),
        "validation_implementations_pinned": bool(composition.validation_implementations),
        "verification_implementations_pinned": bool(
            composition.verification_implementations
        ),
        "semantic_authority_pinned": bool(
            composition.semantic_authority
            and composition.semantic_authority.get("digest")
        ),
        "scenario_bound": (
            graph_plan.scenario is None
            or authorized.run.scenario_digest == graph_plan.scenario.digest
        ),
    }
    findings[AUTHORITY_CHAIN_PINNED] = (all(authority_checks.values()), authority_checks)

    validation_checks = {
        "protocol_count": len(authorized.system_validation),
        "all_valid": bool(authorized.system_validation)
        and all(item.result.valid for item in authorized.system_validation),
        "pinned_implementations": bool(composition.validation_implementations),
    }
    findings[SYSTEM_VALIDATION_PASSED] = (
        bool(validation_checks["all_valid"])
        and bool(validation_checks["pinned_implementations"]),
        validation_checks,
    )

    validation_completeness = _validation_completeness(authorized)
    findings[VALIDATION_PROTOCOL_COMPLETENESS] = (
        validation_completeness.complete,
        validation_completeness.to_dict(),
    )
    verification_completeness = _verification_completeness(authorized)
    findings[VERIFICATION_PROTOCOL_COMPLETENESS] = (
        verification_completeness.complete,
        verification_completeness.to_dict(),
    )

    verification_checks = {
        "protocol_count": len(authorized.system_verification),
        "all_plans_complete": bool(authorized.system_verification)
        and all(item.run.result.complete for item in authorized.system_verification),
        "all_decisions_verified": bool(authorized.system_verification)
        and all(
            item.run.result.verification.decision is VerificationDecision.VERIFIED
            for item in authorized.system_verification
        ),
        "pinned_implementations": bool(composition.verification_implementations),
    }
    findings[INDEPENDENT_VERIFICATION_PASSED] = (
        bool(
            verification_checks["all_plans_complete"]
            and verification_checks["all_decisions_verified"]
            and verification_checks["pinned_implementations"]
        ),
        verification_checks,
    )

    parameter_uncertainty_requested = any(
        item.uncertainty.is_quantified
        and item.uncertainty.source_kind is UncertaintySource.PARAMETER
        for item in authorized.run.external_inputs
    )
    uncertainty_checks = {
        "producer_implementations_pinned": bool(composition.uncertainty_implementations),
        "quantified_parameter_inputs_present": parameter_uncertainty_requested,
        "system_results_count": len(authorized.system_uncertainty),
        "quantified_results_present_when_requested": (
            not parameter_uncertainty_requested or bool(authorized.system_uncertainty)
        ),
    }
    findings[UNCERTAINTY_AUTHORITY_SATISFIED] = (
        bool(
            uncertainty_checks["producer_implementations_pinned"]
            and uncertainty_checks["quantified_results_present_when_requested"]
        ),
        uncertainty_checks,
    )

    uq_coverage = _uq_coverage(authorized)
    findings[UQ_CHANNEL_COMPLETENESS] = (uq_coverage.complete, uq_coverage.to_dict())

    roundtrip_problem = ""
    try:
        restored = AuthorizedMultiphysicsRun.from_dict(authorized.to_dict())
        roundtrip_ok = restored.digest == authorized.digest
    except Exception as exc:  # noqa: BLE001
        roundtrip_ok = False
        roundtrip_problem = f"{type(exc).__name__}: {exc}"
    findings[SERIALIZATION_ROUNDTRIP_VERIFIED] = (
        roundtrip_ok,
        {
            "digest": authorized.digest,
            "roundtrip_digest_matches": roundtrip_ok,
            "problem": roundtrip_problem,
            "note": (
                "serialization integrity only; this gate re-executes nothing and "
                "is not computational replay"
            ),
        },
    )

    # THE REPLAY GATE ASKS THE EVIDENCE, NOT THE STATUS.
    #
    # It used to accept `status is REPLAYED_MATCH and original_run_id matches`,
    # which any record could satisfy without anything having been executed.
    # `certifies` recomputes the expected identity from THIS run and THIS
    # policy and enumerates every way the evidence fails to be about them.
    replay_evidence: dict[str, Any] = {
        "supplied": replay is not None,
        "policy_id": replay_policy.policy_id,
        "policy_digest": replay_policy.digest,
        "note": (
            "an absent, unsealed or foreign replay outcome is not a verified "
            "replay, whatever its status field says"
        ),
    }
    replay_problems: tuple[str, ...] = ("no replay outcome was supplied",)
    if replay is not None:
        if not isinstance(replay, ReplayOutcome):
            raise TypeError("replay evidence must be a ReplayOutcome")
        replay_problems = replay.certifies(authorized, replay_policy)
        replay_evidence.update(replay.to_dict())
    replay_evidence["problems"] = list(replay_problems)
    findings[COMPUTATIONAL_REPLAY_VERIFIED] = (not replay_problems, replay_evidence)

    run_binding = authorized_run_binding(authorized)
    numerical_completeness = assess_numerical_completeness(
        policy.numerical_requirement, numerical
    )
    numerical_evidence: dict[str, Any] = {
        "supplied": numerical is not None,
        "computation": run_binding.digest,
        "scope_profile": NUMERICAL_EXECUTION_PROFILE.profile_id,
        "completeness": numerical_completeness.to_dict(),
    }
    numerical_problems: list[str] = []
    if numerical is None:
        numerical_problems.append("no numerical evidence was supplied")
    else:
        if not isinstance(numerical, NumericalEvidence):
            raise TypeError("numerical evidence must be a NumericalEvidence record")
        # SCOPE FIRST. Evidence naming only a shared solver would satisfy every
        # run using that solver, so the profile floor is checked before the
        # containment match.
        if numerical.binding is None:
            numerical_problems.append(
                f"numerical evidence from {numerical.producer_id!r} names no "
                f"execution binding"
            )
        else:
            numerical_problems.extend(
                NUMERICAL_EXECUTION_PROFILE.unmet(numerical.binding, run_binding)
            )
        numerical_problems.extend(numerical.belongs_to(run_binding))
        numerical_evidence.update(
            {
                "producer_id": numerical.producer_id,
                "digest": numerical.digest,
                "binding": (
                    None if numerical.binding is None else numerical.binding.to_dict()
                ),
            }
        )
    # An UNSTATED requirement cannot be satisfied by an empty roster.
    if not numerical_completeness.complete:
        numerical_problems.append(
            f"numerical requirement {numerical_completeness.requirement_id!r} is "
            f"not met; enforceable={numerical_completeness.enforceable}, "
            f"missing={list(numerical_completeness.missing)}, "
            f"violated={list(numerical_completeness.violated)}"
        )
    numerical_evidence["problems"] = list(numerical_problems)
    findings[NUMERICAL_EVIDENCE_PRESENT] = (not numerical_problems, numerical_evidence)

    query = tuple(envelope_queries or ())
    envelope_evidence: dict[str, Any] = {
        "supplied": envelope is not None,
        "computation": run_binding.digest,
        "scope_profile": VALIDATION_AUTHORITY_PROFILE.profile_id,
        "accepted_verdicts": list(policy.accepted_envelope_verdicts),
        "query_points": [item.to_dict() for item in query],
    }
    envelope_problems: list[str] = []
    if envelope is None:
        envelope_problems.append("no validation envelope was supplied")
    else:
        if not isinstance(envelope, ValidationEnvelope):
            raise TypeError("envelope evidence must be a ValidationEnvelope")
        if envelope.target is None:
            envelope_problems.append("the envelope names no validation target")
        else:
            # SCOPE FIRST, for the same reason as the numerical gate: an
            # envelope bound only to a MODEL is satisfied by every run using
            # that model, whatever realization or authority it ran under.
            envelope_problems.extend(
                VALIDATION_AUTHORITY_PROFILE.unmet(envelope.target, run_binding)
            )
        envelope_problems.extend(envelope.belongs_to(run_binding))

        # THE PREDICTION, NOT THE ENVELOPE'S BEST CELL. A model validated in
        # one operating region does not make every run using it validated.
        if not query:
            envelope_problems.append(
                "no validation query point was supplied, so whether this "
                "prediction lies inside empirical support is UNKNOWN; Core "
                "cannot derive a domain's validation coordinates for it"
            )
        accepted = set(policy.accepted_envelope_verdicts)
        classifications = []
        for point in query:
            found = envelope.classify_point(point)
            classifications.append(
                {
                    "qoi_id": point.qoi_id,
                    "label": point.label,
                    "verdict": found.verdict.value,
                    "declared": found.declared.value,
                    "why": found.why,
                }
            )
            if found.verdict.value not in accepted:
                envelope_problems.append(
                    f"prediction point {point.qoi_id!r}"
                    + (f" ({point.label})" if point.label else "")
                    + f" is {found.verdict.value}, which this policy does not "
                    f"accept: {found.why}"
                )
        envelope_evidence.update(
            {
                "envelope_id": envelope.envelope_id,
                "region_id": envelope.region.region_id,
                "coverage": envelope.coverage.status_counts(),
                # Recorded BESIDE the coverage map, never inside it: a correct
                # refusal answers a different question from this gate's.
                "guardrail": envelope.guardrail_counts,
                "campaign_report_digest": envelope.campaign_report_digest,
                "target": None if envelope.target is None else envelope.target.to_dict(),
                "classifications": classifications,
                "digest": envelope.digest,
            }
        )
    envelope_evidence["problems"] = list(envelope_problems)
    findings[VALIDATION_ENVELOPE_SUPPORTED] = (not envelope_problems, envelope_evidence)

    required = set(policy.required_gates)
    evaluations = tuple(
        TrustGateEvaluation(
            gate_id=gate_id,
            passed=findings[gate_id][0],
            required=gate_id in required,
            evidence=findings[gate_id][1],
        )
        for gate_id in policy.evaluated_gates
    )
    return TrustAssessment(policy=policy, evaluations=evaluations)


def certification_record_from_assessment(
    assessment: TrustAssessment,
    authorized: AuthorizedMultiphysicsRun,
    *,
    commit_sha: str,
) -> CertificationRecord:
    """Build the certificate. It carries the gates the policy required.

    The advisory evaluations are not gates in the record -- a certificate that
    listed a failing advisory gate would be refused by the standard verifier,
    and one that listed it as passing would be a lie. They are pinned instead
    through the ``trust_assessment`` artifact digest, which covers every
    evaluation including the failures, so the certificate cannot be read as
    "everything was checked" when it was not.
    """
    if not isinstance(assessment, TrustAssessment):
        raise TypeError("certification requires a TrustAssessment")
    required_ids = set(assessment.policy.required_gates)
    gates = tuple(
        item.as_gate_result()
        for item in assessment.evaluations
        if item.gate_id in required_ids
    )
    artifacts = (
        CertificationArtifact("authorized_multiphysics_run", authorized.digest),
        CertificationArtifact(
            "composition_authority_snapshot", authorized.composition_snapshot.digest
        ),
        CertificationArtifact(
            "execution_authority_snapshot", authorized.execution_snapshot.digest
        ),
        CertificationArtifact(
            "multiphysics_run_record", evidence_digest(authorized.run.to_dict())
        ),
        CertificationArtifact("trust_policy", assessment.policy.digest),
        CertificationArtifact("trust_assessment", assessment.digest),
    )
    return CertificationRecord(
        commit_sha=commit_sha,
        profile=assessment.policy.profile,
        gates=gates,
        artifacts=artifacts,
    )


def certify_authorized_multiphysics_run(
    authorized: AuthorizedMultiphysicsRun,
    *,
    commit_sha: str,
    policy: TrustPolicy = MULTIPHYSICS_PRODUCTION_POLICY,
    replay: ReplayOutcome | None = None,
    replay_policy: ReplayPolicy = DEFAULT_REPLAY_POLICY,
    numerical: NumericalEvidence | None = None,
    envelope: ValidationEnvelope | None = None,
    envelope_queries: tuple[ValidationQueryPoint, ...] = (),
) -> CertificationRecord:
    """Assess one authorized run against a policy and certify what it earned."""
    assessment = assess_authorized_multiphysics_run(
        authorized,
        policy=policy,
        replay=replay,
        replay_policy=replay_policy,
        numerical=numerical,
        envelope=envelope,
        envelope_queries=envelope_queries,
    )
    return certification_record_from_assessment(
        assessment, authorized, commit_sha=commit_sha
    )


__all__ = [
    "ALL_GATES",
    "AUTHORITY_CHAIN_PINNED",
    "COMPUTATIONAL_REPLAY_VERIFIED",
    "INDEPENDENT_VERIFICATION_PASSED",
    "MULTIPHYSICS_FULL_TRUST_POLICY",
    "MULTIPHYSICS_PRODUCTION_POLICY",
    "MULTIPHYSICS_PRODUCTION_PROFILE",
    "NUMERICAL_EVIDENCE_PRESENT",
    "SERIALIZATION_ROUNDTRIP_VERIFIED",
    "SYSTEM_VALIDATION_PASSED",
    "TrustAssessment",
    "TrustGateEvaluation",
    "TrustPolicy",
    "UNCERTAINTY_AUTHORITY_SATISFIED",
    "UQ_CHANNEL_COMPLETENESS",
    "VALIDATION_ENVELOPE_SUPPORTED",
    "VALIDATION_PROTOCOL_COMPLETENESS",
    "VERIFICATION_PROTOCOL_COMPLETENESS",
    "assess_authorized_multiphysics_run",
    "certification_record_from_assessment",
    "certify_authorized_multiphysics_run",
]
