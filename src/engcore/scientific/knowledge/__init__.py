"""Offline, content-addressed scientific knowledge and source-trust contracts."""

from .source import KnowledgeSource,KnowledgeSourceClass
from .trust import SourcePin,SourceStanding,SourceTrustAssessment,TrustedSourceRegistry
from .freshness import FreshnessPolicy,KnowledgeFreshness
from .claim import KnowledgeClaim,KnowledgeKind
from .snapshot import KnowledgeSnapshot
from .admission import KnowledgeAdmission,KnowledgeAdmissionStatus,admit_claim
from .conflicts import KnowledgeConflict,KnowledgeConflictStatus,compare_claims
from .ingestion import KnowledgeIngestionReceipt,verify_ingestion_receipt

__all__=["KnowledgeSource","KnowledgeSourceClass","SourcePin","SourceStanding","SourceTrustAssessment",
"TrustedSourceRegistry","FreshnessPolicy","KnowledgeFreshness","KnowledgeClaim","KnowledgeKind",
"KnowledgeSnapshot","KnowledgeAdmission","KnowledgeAdmissionStatus","admit_claim","KnowledgeConflict",
"KnowledgeConflictStatus","compare_claims","KnowledgeIngestionReceipt","verify_ingestion_receipt"]

from .query import KnowledgeQuery
from .resolution import KnowledgeSetAssessment, KnowledgeSetStatus, assess_knowledge_set
from .versioning import (
    SourceSupersession, SourceVersionKey, SourceVersionRelation,
    compare_source_versions,
)
from .registry import ScientificKnowledgeRegistry

__all__ += [
    "KnowledgeQuery", "KnowledgeSetAssessment", "KnowledgeSetStatus",
    "assess_knowledge_set", "SourceVersionKey", "SourceVersionRelation",
    "SourceSupersession", "compare_source_versions",
    "ScientificKnowledgeRegistry",
]
