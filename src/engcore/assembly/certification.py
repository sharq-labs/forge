"""Certification gate for authorized multiphysics production runs.

This module adapts Composition/Execution authority to the existing generic
scientific certification core. It does not create a second certificate format.
"""

from __future__ import annotations

import hashlib
import json

from .multiphysics import AuthorizedMultiphysicsRun
from ..scientific.certification_core.artifact import CertificationArtifact
from ..scientific.certification_core.gate import CertificationGateResult
from ..scientific.certification_core.profile import CertificationProfile
from ..scientific.certification_core.record import CertificationRecord
from ..scientific.results.uncertainty import UncertaintySource
from ..scientific.verification.adjudication import VerificationDecision

MULTIPHYSICS_PRODUCTION_PROFILE = CertificationProfile(
    profile_id="forge.multiphysics.production.v1",
    required_gates=(
        "authority_chain_pinned",
        "system_validation_passed",
        "uncertainty_authority_satisfied",
        "independent_verification_passed",
        "replay_roundtrip_verified",
    ),
)


def _digest(payload) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def _gate(
    gate_id: str,
    passed: bool,
    payload,
) -> CertificationGateResult:
    return CertificationGateResult(
        gate_id=gate_id,
        passed=bool(passed),
        evidence_digest=_digest(payload),
    )


def certify_authorized_multiphysics_run(
    authorized: AuthorizedMultiphysicsRun,
    *,
    commit_sha: str,
) -> CertificationRecord:
    """Build a standard CertificationRecord from one authorized graph run."""

    if not isinstance(authorized, AuthorizedMultiphysicsRun):
        raise TypeError(
            "certify_authorized_multiphysics_run requires "
            "AuthorizedMultiphysicsRun"
        )

    graph_plan = authorized.graph_plan
    composition = authorized.composition_snapshot
    execution = authorized.execution_snapshot

    authority_checks = {
        "composition_plan_matches_snapshot": (
            graph_plan.authority_pack_digest
            == composition.authority_digest
        ),
        "execution_plan_matches_snapshot": (
            graph_plan.execution_pack_digest
            == execution.authority_digest
        ),
        "execution_bound_to_composition": (
            execution.composition_authority_digest
            == composition.authority_digest
        ),
        "graph_matches_executed_graph": (
            graph_plan.graph == authorized.run.graph
        ),
        "coupling_plan_matches_execution": (
            graph_plan.coupling_plan == authorized.run.plan
        ),
        "validation_implementations_pinned": bool(
            composition.validation_implementations
        ),
        "verification_implementations_pinned": bool(
            composition.verification_implementations
        ),
        "semantic_authority_pinned": bool(
            composition.semantic_authority
            and composition.semantic_authority.get("digest")
        ),
    }
    authority_gate = _gate(
        "authority_chain_pinned",
        all(authority_checks.values()),
        authority_checks,
    )

    validation_checks = {
        "protocol_count": len(authorized.system_validation),
        "all_valid": bool(authorized.system_validation)
        and all(
            item.result.valid for item in authorized.system_validation
        ),
        "pinned_implementations": bool(
            composition.validation_implementations
        ),
    }
    validation_gate = _gate(
        "system_validation_passed",
        bool(validation_checks["all_valid"])
        and bool(validation_checks["pinned_implementations"]),
        validation_checks,
    )

    parameter_uncertainty_requested = any(
        item.uncertainty.is_quantified
        and item.uncertainty.source_kind is UncertaintySource.PARAMETER
        for item in authorized.run.external_inputs
    )
    uncertainty_checks = {
        "producer_implementations_pinned": bool(
            composition.uncertainty_implementations
        ),
        "quantified_parameter_inputs_present": (
            parameter_uncertainty_requested
        ),
        "system_results_count": len(authorized.system_uncertainty),
        "quantified_results_present_when_requested": (
            not parameter_uncertainty_requested
            or bool(authorized.system_uncertainty)
        ),
    }
    uncertainty_gate = _gate(
        "uncertainty_authority_satisfied",
        bool(
            uncertainty_checks["producer_implementations_pinned"]
            and uncertainty_checks[
                "quantified_results_present_when_requested"
            ]
        ),
        uncertainty_checks,
    )

    verification_checks = {
        "protocol_count": len(authorized.system_verification),
        "all_plans_complete": bool(authorized.system_verification)
        and all(
            item.run.result.complete
            for item in authorized.system_verification
        ),
        "all_decisions_verified": bool(authorized.system_verification)
        and all(
            item.run.result.verification.decision
            is VerificationDecision.VERIFIED
            for item in authorized.system_verification
        ),
        "pinned_implementations": bool(
            composition.verification_implementations
        ),
    }
    verification_gate = _gate(
        "independent_verification_passed",
        bool(
            verification_checks["all_plans_complete"]
            and verification_checks["all_decisions_verified"]
            and verification_checks["pinned_implementations"]
        ),
        verification_checks,
    )

    replay_problem = ""
    try:
        replayed = AuthorizedMultiphysicsRun.from_dict(
            authorized.to_dict()
        )
        replay_ok = replayed.digest == authorized.digest
    except Exception as exc:
        replay_ok = False
        replay_problem = f"{type(exc).__name__}: {exc}"
    replay_checks = {
        "digest": authorized.digest,
        "roundtrip_digest_matches": replay_ok,
        "problem": replay_problem,
    }
    replay_gate = _gate(
        "replay_roundtrip_verified",
        replay_ok,
        replay_checks,
    )

    artifacts = (
        CertificationArtifact(
            "authorized_multiphysics_run",
            authorized.digest,
        ),
        CertificationArtifact(
            "composition_authority_snapshot",
            composition.digest,
        ),
        CertificationArtifact(
            "execution_authority_snapshot",
            execution.digest,
        ),
        CertificationArtifact(
            "multiphysics_run_record",
            _digest(authorized.run.to_dict()),
        ),
    )

    return CertificationRecord(
        commit_sha=commit_sha,
        profile=MULTIPHYSICS_PRODUCTION_PROFILE,
        gates=(
            authority_gate,
            validation_gate,
            uncertainty_gate,
            verification_gate,
            replay_gate,
        ),
        artifacts=artifacts,
    )


__all__ = [
    "MULTIPHYSICS_PRODUCTION_PROFILE",
    "certify_authorized_multiphysics_run",
]
