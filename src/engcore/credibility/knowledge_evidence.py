"""Bridge scientific knowledge into the evidence graph by re-deriving admission."""

from __future__ import annotations

from datetime import datetime

from ..scientific.errors import InvalidScientificProblem
from ..scientific.knowledge import (
    FreshnessPolicy,
    KnowledgeAdmissionStatus,
    KnowledgeSnapshot,
    KnowledgeSourceClass,
    TrustedSourceRegistry,
    admit_claim,
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


def evidence_from_knowledge(
    snapshot: KnowledgeSnapshot,
    claim_id: str,
    registry: TrustedSourceRegistry,
    freshness_policy: FreshnessPolicy,
    *,
    now: datetime,
    target_context_digest: str,
) -> EvidenceNode:
    admission = admit_claim(
        snapshot,
        claim_id,
        registry,
        freshness_policy,
        now=now,
        target_context_digest=target_context_digest,
    )
    if admission.status is not KnowledgeAdmissionStatus.ADMISSIBLE:
        raise InvalidScientificProblem(
            "knowledge claim is not admissible: " + "; ".join(admission.reasons)
        )
    claim = next(c for c in snapshot.claims if c.claim_id == claim_id)
    source = next(s for s in snapshot.sources if s.source_id == claim.source_id)
    pin = registry.pin_for(source.source_id)
    if pin is None:
        raise InvalidScientificProblem(
            "admissible knowledge source unexpectedly has no trust pin"
        )
    provenance = EvidenceProvenance(
        source.source_id,
        source.issuer,
        source.document_digest,
        source.version,
        source.locator,
        source.published_at,
        source.retrieved_at,
        source.source_class.value,
        pin.issuer,
        pin.document_digest,
        pin.version,
        freshness_policy.max_age_days.get(source.source_class),
        freshness_policy.require_timestamp,
        now.isoformat(),
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
