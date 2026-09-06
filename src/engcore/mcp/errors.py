"""Errors raised when assembling or reading a credibility evidence report.

One subclass, deliberately. The verification and validation (V&V) layer has
exactly one failure mode worth distinguishing from the rest of the platform —
"this report does not say what it claims to say" — and splitting that into a
taxonomy would suggest a caller could usefully branch on which way a report was
malformed. It cannot: every one of them means the report must not be read as
evidence.

Subclasses ``ScientificCoreError`` so a caller catching the platform's root
error still catches these, which is the same choice ``ElectricalDCError`` makes
in the DC domain.
"""

from __future__ import annotations

from ..scientific.errors import ScientificCoreError

__all__ = ["CredibilityEvidenceError", "EvidencePackageError"]


class CredibilityEvidenceError(ScientificCoreError):
    """The report is malformed, or claims a verdict its contents do not support."""


#: Deprecated alias, kept for one release alongside
#: :class:`~engcore.mcp.evidence.EvidencePackage`. New code should use
#: :class:`CredibilityEvidenceError`.
EvidencePackageError = CredibilityEvidenceError
