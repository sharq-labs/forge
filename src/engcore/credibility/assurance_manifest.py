"""Production assurance manifest: one replayable identity for the scientific trust chain."""

from __future__ import annotations

from ..scientific.certification_core import CertificationRecord, verify_certification_record
from ..scientific.certification_core.serialization import certification_to_dict
from ..scientific.equations import LawReference
from ..scientific.errors import InvalidScientificProblem
from ..scientific.knowledge import KnowledgeSnapshot
from ..scientific.replay_core import (
    RunManifestProfile, RuntimeEnvironment, ScientificRunManifest,
    artifact_from_payload, provenance_artifact,
)
from ..scientific.results.provenance import ProvenanceRecord
from ..scientific.results.uncertainty import UncertaintyKind, UncertaintySource
from ..scientific.validation_core import ValidationDecision, ValidationPolicy, ValidationReport
from ..scientific.validation_core.gate import gate_validation
from ..scientific.verification import VerificationDecision, VerificationRunRecord
from ..uq.combined import CombinationReport, report_to_dict
from .evidence_graph import EvidenceGraph, EvidenceGraphPolicy, assess_graph
from .replay_binding import evidence_graph_artifact, knowledge_snapshot_artifact, law_artifact


PRODUCTION_ASSURANCE_PROFILE = RunManifestProfile(
    "production-scientific-assurance/v1",
    (
        "certification_record",
        "combined_uq",
        "evidence_graph",
        "knowledge_snapshot",
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
        "scientific_law",
        "validation_report",
    ),
)


def _validate_knowledge_evidence(
    snapshot: KnowledgeSnapshot,
    graph: EvidenceGraph,
) -> None:
    claims={claim.digest:claim for claim in snapshot.claims}
    sources={source.source_id:source for source in snapshot.sources}
    for node in graph.nodes:
        if not node.evidence_id.startswith("knowledge:"):
            continue
        if node.provenance is None:
            raise InvalidScientificProblem(
                f"knowledge evidence {node.evidence_id!r} has no typed provenance"
            )
        if not node.provenance.trusted:
            raise InvalidScientificProblem(
                f"knowledge evidence {node.evidence_id!r} is not pinned/trusted"
            )
        if not node.provenance.fresh_enough:
            raise InvalidScientificProblem(
                f"knowledge evidence {node.evidence_id!r} is stale or freshness is unknown"
            )
        claim=claims.get(node.content_digest)
        if claim is None:
            raise InvalidScientificProblem(
                f"knowledge evidence {node.evidence_id!r} does not bind a claim in the supplied snapshot"
            )
        source=sources.get(claim.source_id)
        if source is None or source.document_digest!=node.provenance.document_digest:
            raise InvalidScientificProblem(
                f"knowledge evidence {node.evidence_id!r} source identity differs from the supplied snapshot"
            )
        if claim.applicability_context_digest!=node.provenance.context_digest:
            raise InvalidScientificProblem(
                f"knowledge evidence {node.evidence_id!r} applicability differs from the supplied snapshot claim"
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
    random_seed: int | None = None,
    parent: ScientificRunManifest | None = None,
    replay_of: ScientificRunManifest | None = None,
) -> ScientificRunManifest:
    if provenance.run_id!=str(run_id).strip():
        raise InvalidScientificProblem(
            "production assurance run_id differs from provenance run_id"
        )
    derived_validation=gate_validation(validation.stages,ValidationPolicy())
    if derived_validation.decision is not validation.decision:
        raise InvalidScientificProblem(
            "validation report decision does not match the production validation gate"
        )
    if derived_validation.decision is not ValidationDecision.ACCEPTED:
        raise InvalidScientificProblem(
            f"production assurance requires accepted validation, got {derived_validation.decision.value}"
        )

    verification_result=verification.result
    if not verification_result.complete or verification_result.verification.decision is not VerificationDecision.VERIFIED:
        raise InvalidScientificProblem(
            "production assurance requires complete independently verified evidence"
        )

    certification_result=verify_certification_record(certification)
    if not certification.profile.required_gates:
        raise InvalidScientificProblem(
            "production assurance certification profile must require at least one gate"
        )
    if not certification_result.verified:
        raise InvalidScientificProblem(
            "production assurance requires a verified certification record: "
            + "; ".join(certification_result.problems)
        )
    if provenance.git_commit and provenance.git_commit!=certification.commit_sha:
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

    graph_assessment=assess_graph(
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
    _validate_knowledge_evidence(knowledge,evidence)

    artifacts=(
        law_artifact(law),
        knowledge_snapshot_artifact(knowledge),
        evidence_graph_artifact(evidence),
        artifact_from_payload("validation_report","validation",validation.to_dict()),
        artifact_from_payload("combined_uq","combined-uq",report_to_dict(combined_uq)),
        artifact_from_payload("verification_run","independent-verification",verification.to_dict()),
        artifact_from_payload("certification_record",certification.commit_sha,certification_to_dict(certification)),
        provenance_artifact(provenance),
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
