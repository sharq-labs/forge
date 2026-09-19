"""Errors owned by the credibility/V&V layer."""

from __future__ import annotations

from ..scientific.errors import ScientificCoreError

__all__ = ["CredibilityEvidenceError"]


class CredibilityEvidenceError(ScientificCoreError):
    """A credibility report is malformed or overstates what its contents support."""
