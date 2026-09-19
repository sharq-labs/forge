"""Bridge admitted scientific knowledge into the evidence graph.

The bridge consumes an already-derived KnowledgeAdmission.  A URL, source class
or citation string never becomes trusted evidence by itself.
"""

from __future__ import annotations

from ..scientific.errors import InvalidScientificProblem
from ..scientific.knowledge import (
    KnowledgeAdmission,
    KnowledgeAdmissionStatus,
    KnowledgeSnapshot,
    KnowledgeSourceClass,
)
from .evidence_graph.node import EvidenceAuthority, EvidenceNode
from .evidence_graph.provenance import EvidenceProvenance


_AUTHORITY = {
    KnowledgeSourceClass.PEER_REVIEWED: EvidenceAuthority.PEER_REVIEWED,
    KnowledgeSourceClass.STANDARD: EvidenceAuthority.STANDARD,
    KnowledgeSourceClass.OFFICIAL_DATA: EvidenceAuthority.OFFICIAL_DATA,
    KnowledgeSourceClass.REFERENCE_DATABASE: EvidenceAuthority.REFERENCE_DATA,
    KnowledgeSourceClass.MANUFACTURER_DATASHEET: EvidenceAuthority.DATASHEET,
    KnowledgeSourceClass.EXPERIMENTAL_DATASET: EvidenceAuthority.EXPERIMENT,
    KnowledgeSourceClass.OTHER: EvidenceAuthority.UNKNOWN,
}


def evidence_from_admitted_knowledge(
    snapshot: KnowledgeSnapshot,
    admission: KnowledgeAdmission,
) -> EvidenceNode:
    if (
        admission.status is not KnowledgeAdmissionStatus.ADMISSIBLE
        or not admission.admissible
    ):
        raise InvalidScientificProblem(
            "only an admissible knowledge claim may become evidence"
        )
    claim = next(
        (c for c in snapshot.claims if c.claim_id == admission.claim_id),
        None,
    )
    if claim is None:
        raise InvalidScientificProblem(
            "knowledge admission references a claim absent from snapshot"
        )
    source = next(
        (s for s in snapshot.sources if s.source_id == claim.source_id),
        None,
    )
    if source is None:
        raise InvalidScientificProblem(
            "knowledge claim source is absent from snapshot"
        )
    if claim.source_document_digest != source.document_digest:
        raise InvalidScientificProblem(
            "knowledge claim source digest differs from snapshot source"
        )
    provenance = EvidenceProvenance(
        source.source_id,
        source.issuer,
        source.document_digest,
        source.version,
        source.locator,
        source.retrieved_at,
        source.source_class.value,
        admission.source_standing.value,
        admission.freshness.value,
        claim.applicability_context_digest,
        claim.digest,
    )
    return EvidenceNode(
        evidence_id=f"knowledge:{claim.claim_id}",
        authority=_AUTHORITY[source.source_class],
        content_digest=claim.digest,
        source=source.locator,
        observed_at=source.published_at,
        applicability=claim.applicability_context_digest,
        provenance=provenance,
    )
