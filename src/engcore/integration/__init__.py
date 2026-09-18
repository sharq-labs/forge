"""Integration boundaries that compose stable Forge layers.

Nothing in this package owns scientific truth.  It connects records that are
already authoritative in their own layers without making the Scientific Core
import SRIA or making SRIA depend on MCP.
"""

from .decision_evidence import (
    CREDIBILITY_REPORT_CRITIC_ID,
    CredibilityReportCritic,
    DecisionEvidenceBridgeError,
    decision_context_ref,
    evidence_from_credibility_report,
    report_digest,
)

__all__ = [
    "CREDIBILITY_REPORT_CRITIC_ID",
    "CredibilityReportCritic",
    "DecisionEvidenceBridgeError",
    "decision_context_ref",
    "evidence_from_credibility_report",
    "report_digest",
]
