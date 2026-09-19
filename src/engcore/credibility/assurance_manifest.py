"""Production assurance manifest: one replayable identity for the scientific trust chain."""

from __future__ import annotations

from datetime import datetime

from ..scientific.certification_core import CertificationRecord, verify_certification_record
from ..scientific.certification_core.serialization import certification_to_dict
from ..scientific.equations import LawReference
from ..scientific.errors import InvalidScientificProblem
from ..scientific.knowledge import FreshnessPolicy, KnowledgeSnapshot, TrustedSourceRegistry
from ..scientific.measurements import CalibratedMeasurementObservation
from ..scientific.replay_core import (
    ArtifactIdentity,
    RunManifestProfile,
    RuntimeEnvironment,
    ScientificRunManifest,
    artifact_from_payload,
    provenance_artifact,
)
from ..scientific.results.provenance import ProvenanceRecord
from ..scientific.results.uncertainty import UncertaintyKind, UncertaintySource
from ..scientific.validation_core import (
    ValidationDecision,
    ValidationPolicy,
    ValidationReport,
)
from ..scientific.validation_core.gate import gate_validation
from ..scientific.verification import VerificationDecision, VerificationRunRecord
from ..uq.combined import CombinationReport, report_to_dict
from .evidence_graph import (
    EvidenceAuthority,
    EvidenceGraph,
    EvidenceGraphPolicy,
    assess_graph,
)
from .knowledge_evidence import evidence_from_knowledge
from .replay_binding import (
    evidence_graph_artifact,
    knowledge_snapshot_artifact,
    law_artifact,
)


PRODUCTION_ASSURANCE_PROFILE = RunManifestProfile(
    "production-scientific-assurance/v2",
    (
        "certification_record",
        "combined_uq",
        "evidence_graph",
        "knowledge_snapshot",
        "knowledge_trust_registry",
        "knowledge_freshness_policy",
        "measurement_evidence",
        "provenance_record",
        "scientific_law",
        "validation_report",
        "verification_run",
    ),
    (
        "certification_record",
        "combined_uq",
        "evidence_graph",
        "knowledge_snapshot",
        "knowledge_trust_registry",
        "knowledge_freshness_policy",
        "measurement_evidence",
        "provenance_record",
        "scientific_law",
        "validation_report",
        "verification_run",
    ),
    False,
    (
        "certification_record",
        "evidence_graph",
        "knowledge_snapshot",
        "knowledge_trust_registry",
        "knowledge_freshness_policy",
        "measurement_evidence",
        "scientific_law",
        "validation_report",
    ),
)


def _validate_knowledge_evidence(
    snapshot: KnowledgeSnapshot,
    graph: EvidenceGraph,
    trust: TrustedSourceRegistry,
    freshness: FreshnessPolicy,
) -> None:
    if not isinstance(trust, TrustedSourceRegistry):
        raise InvalidScientificProblem(
            "production assurance requires an authoritative TrustedSourceRegistry"
        )
    if not isinstance(freshness, FreshnessPolicy):
        raise InvalidScientificProblem(
            "production assurance requires an authoritative FreshnessPolicy"
        )
    claims = {claim.digest: claim for claim in snapshot.claims}
    for node in graph.nodes:
        if not node.evidence_id.startswith("knowledge:"):
            continue
        if node.provenance is None:
            raise InvalidScientificProblem(
                f"knowledge evidence {node.evidence_id!r} has no typed provenance"
            )
        claim = claims.get(node.content_digest)
        if claim is None:
            raise InvalidScientificProblem(
                f"knowledge evidence {node.evidence_id!r} does not bind a claim in the supplied snapshot"
            )
        assessed_at = datetime.fromisoformat(
            node.provenance.assessed_at.replace("Z", "+00:00")
        )
        try:
            expected = evidence_from_knowledge(
                snapshot,
                claim.claim_id,
                trust,
                freshness,
                now=assessed_at,
                target_context_digest=claim.applicability_context_digest,
            )
        except InvalidScientificProblem as exc:
            raise InvalidScientificProblem(
                f"knowledge evidence {node.evidence_id!r} no longer derives from the authoritative trust/freshness policy: {exc}"
            ) from exc
        if expected.to_dict() != node.to_dict():
            raise InvalidScientificProblem(
                f"knowledge evidence {node.evidence_id!r} provenance does not re-derive from the authoritative trust/freshness policy"
            )


_PIN_REQUIRED_AUTHORITIES = frozenset(
    {
        EvidenceAuthority.EXPERIMENT,
        EvidenceAuthority.STANDARD,
        EvidenceAuthority.PEER_REVIEWED,
        EvidenceAuthority.OFFICIAL_DATA,
        EvidenceAuthority.REFERENCE_DATA,
        EvidenceAuthority.DATASHEET,
        EvidenceAuthority.EXTERNAL_ORACLE,
    }
)


def _measurement_evidence_payload(
    observations: tuple[CalibratedMeasurementObservation, ...],
) -> dict[str, object]:
    return {
        "observations": [
            observation.to_dict()
            for observation in sorted(
                observations,
                key=lambda item: (item.observation_id, item.digest),
            )
        ]
    }


def _validate_evidence_witnesses(
    graph: EvidenceGraph,
    observations: tuple[CalibratedMeasurementObservation, ...],
) -> None:
    observations = tuple(observations)
    if any(
        not isinstance(item, CalibratedMeasurementObservation)
        for item in observations
    ):
        raise InvalidScientificProblem(
            "production measurement witnesses must be calibrated measurement observations"
        )
    by_digest = {item.digest: item for item in observations}
    if len(by_digest) != len(observations):
        raise InvalidScientificProblem(
            "production measurement witnesses contain duplicate observations"
        )

    measurement_nodes = tuple(
        node for node in graph.nodes
        if node.authority is EvidenceAuthority.MEASUREMENT
    )
    node_digests = {node.content_digest for node in measurement_nodes}
    witness_digests = set(by_digest)
    missing = sorted(node_digests - witness_digests)
    extra = sorted(witness_digests - node_digests)
    if missing:
        raise InvalidScientificProblem(
            "production measurement evidence has no calibrated witness for "
            + ", ".join(missing)
        )
    if extra:
        raise InvalidScientificProblem(
            "production measurement witnesses are not represented in the evidence graph: "
            + ", ".join(extra)
        )

    for node in measurement_nodes:
        observation = by_digest[node.content_digest]
        if node.evidence_id != f"measurement:{observation.observation_id}":
            raise InvalidScientificProblem(
                f"measurement evidence {node.evidence_id!r} does not bind its observation id"
            )
        if node.source != f"instrument:{observation.instrument.instrument_id}":
            raise InvalidScientificProblem(
                f"measurement evidence {node.evidence_id!r} instrument differs from its witness"
            )
        if node.applicability != observation.context.digest:
            raise InvalidScientificProblem(
                f"measurement evidence {node.evidence_id!r} context differs from its witness"
            )
        if node.observed_at != observation.observed_at:
            raise InvalidScientificProblem(
                f"measurement evidence {node.evidence_id!r} timestamp differs from its witness"
            )

    for node in graph.nodes:
        if node.authority not in _PIN_REQUIRED_AUTHORITIES:
            continue
        if not node.evidence_id.startswith("knowledge:"):
            raise InvalidScientificProblem(
                f"external source evidence {node.evidence_id!r} is not bound to the authoritative knowledge snapshot"
            )
        if node.provenance is None:
            raise InvalidScientificProblem(
                f"external evidence {node.evidence_id!r} has no typed source provenance"
            )
        if not node.provenance.trusted:
            raise InvalidScientificProblem(
                f"external evidence {node.evidence_id!r} is not pinned/trusted"
            )
        if not node.provenance.fresh_enough:
            raise InvalidScientificProblem(
                f"external evidence {node.evidence_id!r} is stale or freshness is unknown"
            )


def validate_production_assurance_components(
    *,
    run_id: str,
    law: LawReference,
    knowledge: KnowledgeSnapshot,
    evidence: EvidenceGraph,
    validation: ValidationReport,
    combined_uq: CombinationReport,
    verification: VerificationRunRecord,
    certification: CertificationRecord,
    provenance: ProvenanceRecord,
    knowledge_trust: TrustedSourceRegistry,
    knowledge_freshness: FreshnessPolicy,
    measurement_observations: tuple[CalibratedMeasurementObservation, ...] = (),
) -> None:
    if not isinstance(law, LawReference):
        raise InvalidScientificProblem("production assurance requires LawReference")
    if not isinstance(knowledge, KnowledgeSnapshot) or not isinstance(evidence, EvidenceGraph):
        raise InvalidScientificProblem("production assurance requires typed knowledge and evidence")
    if not isinstance(provenance, ProvenanceRecord):
        raise InvalidScientificProblem("production assurance requires ProvenanceRecord")
    if provenance.run_id != str(run_id).strip():
        raise InvalidScientificProblem(
            "production assurance run_id differs from provenance run_id"
        )
    if not provenance.bindings:
        raise InvalidScientificProblem(
            "production assurance requires model-to-solver execution bindings in provenance"
        )

    derived_validation = gate_validation(validation.stages, ValidationPolicy())
    if derived_validation.decision is not validation.decision:
        raise InvalidScientificProblem(
            "validation report decision does not match the production validation gate"
        )
    if derived_validation.decision is not ValidationDecision.ACCEPTED:
        raise InvalidScientificProblem(
            f"production assurance requires accepted validation, got {derived_validation.decision.value}"
        )

    verification_result = verification.result
    if (
        not verification_result.complete
        or verification_result.verification.decision is not VerificationDecision.VERIFIED
    ):
        raise InvalidScientificProblem(
            "production assurance requires complete independently verified evidence"
        )

    certification_result = verify_certification_record(certification)
    if not certification.profile.required_gates:
        raise InvalidScientificProblem(
            "production assurance certification profile must require at least one gate"
        )
    if not certification_result.verified:
        raise InvalidScientificProblem(
            "production assurance requires a verified certification record: "
            + "; ".join(certification_result.problems)
        )
    if not provenance.git_commit:
        raise InvalidScientificProblem(
            "production assurance requires provenance to name the certified git commit"
        )
    if provenance.git_commit != certification.commit_sha:
        raise InvalidScientificProblem(
            "provenance git commit differs from certification commit"
        )

    if (
        combined_uq.output.kind is UncertaintyKind.UNKNOWN
        or combined_uq.output.source_kind is not UncertaintySource.COMBINED
    ):
        raise InvalidScientificProblem(
            "production assurance requires quantified COMBINED uncertainty"
        )
    try:
        verification_nominal = verification.primary.value.to(
            combined_uq.nominal.units
        )
    except Exception as exc:
        raise InvalidScientificProblem(
            "combined UQ nominal is dimensionally incompatible with the independently verified primary value"
        ) from exc
    if verification_nominal.magnitude != combined_uq.nominal.magnitude:
        raise InvalidScientificProblem(
            "combined UQ nominal differs from the independently verified primary value"
        )

    graph_assessment = assess_graph(
        evidence,
        EvidenceGraphPolicy(
            refuse_conflicts=True,
            require_known_authority=True,
        ),
    )
    if not graph_assessment.admissible:
        raise InvalidScientificProblem(
            "production assurance evidence graph is inadmissible: "
            + "; ".join(graph_assessment.problems)
        )
    _validate_knowledge_evidence(
        knowledge,
        evidence,
        knowledge_trust,
        knowledge_freshness,
    )
    _validate_evidence_witnesses(evidence, tuple(measurement_observations))


def production_assurance_artifacts(
    *,
    law: LawReference,
    knowledge: KnowledgeSnapshot,
    evidence: EvidenceGraph,
    validation: ValidationReport,
    combined_uq: CombinationReport,
    verification: VerificationRunRecord,
    certification: CertificationRecord,
    provenance: ProvenanceRecord,
    knowledge_trust: TrustedSourceRegistry,
    knowledge_freshness: FreshnessPolicy,
    measurement_observations: tuple[CalibratedMeasurementObservation, ...] = (),
) -> tuple[ArtifactIdentity, ...]:
    return (
        law_artifact(law),
        knowledge_snapshot_artifact(knowledge),
        artifact_from_payload(
            "knowledge_trust_registry",
            "authoritative-source-pins",
            {
                "pins": [
                    pin.to_dict()
                    for pin in sorted(
                        knowledge_trust.pins,
                        key=lambda item: item.source_id,
                    )
                ]
            },
        ),
        artifact_from_payload(
            "knowledge_freshness_policy",
            "authoritative-freshness-policy",
            knowledge_freshness.to_dict(),
        ),
        evidence_graph_artifact(evidence),
        artifact_from_payload(
            "measurement_evidence",
            "calibrated-measurements",
            _measurement_evidence_payload(tuple(measurement_observations)),
        ),
        artifact_from_payload(
            "validation_report", "validation", validation.to_dict()
        ),
        artifact_from_payload(
            "combined_uq", "combined-uq", report_to_dict(combined_uq)
        ),
        artifact_from_payload(
            "verification_run", "independent-verification", verification.to_dict()
        ),
        artifact_from_payload(
            "certification_record",
            certification.commit_sha,
            certification_to_dict(certification),
        ),
        provenance_artifact(provenance),
    )


def build_production_assurance_manifest(
    *,
    run_id: str,
    environment: RuntimeEnvironment,
    law: LawReference,
    knowledge: KnowledgeSnapshot,
    evidence: EvidenceGraph,
    validation: ValidationReport,
    combined_uq: CombinationReport,
    verification: VerificationRunRecord,
    certification: CertificationRecord,
    provenance: ProvenanceRecord,
    knowledge_trust: TrustedSourceRegistry,
    knowledge_freshness: FreshnessPolicy,
    measurement_observations: tuple[CalibratedMeasurementObservation, ...] = (),
    random_seed: int | None = None,
    parent: ScientificRunManifest | None = None,
    replay_of: ScientificRunManifest | None = None,
) -> ScientificRunManifest:
    validate_production_assurance_components(
        run_id=run_id,
        law=law,
        knowledge=knowledge,
        evidence=evidence,
        validation=validation,
        combined_uq=combined_uq,
        verification=verification,
        certification=certification,
        provenance=provenance,
        knowledge_trust=knowledge_trust,
        knowledge_freshness=knowledge_freshness,
        measurement_observations=measurement_observations,
    )
    artifacts = production_assurance_artifacts(
        law=law,
        knowledge=knowledge,
        evidence=evidence,
        validation=validation,
        combined_uq=combined_uq,
        verification=verification,
        certification=certification,
        provenance=provenance,
        knowledge_trust=knowledge_trust,
        knowledge_freshness=knowledge_freshness,
        measurement_observations=measurement_observations,
    )
    return ScientificRunManifest(
        str(run_id).strip(),
        PRODUCTION_ASSURANCE_PROFILE,
        artifacts,
        environment,
        random_seed,
        parent.run_id if parent is not None else None,
        parent.digest if parent is not None else None,
        replay_of.digest if replay_of is not None else None,
    )
