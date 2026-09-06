"""Errors raised when assembling or reading an evidence package.

One subclass, deliberately. The evidence layer has exactly one failure mode
worth distinguishing from the rest of the platform — "this package does not say
what it claims to say" — and splitting that into a taxonomy would suggest a
caller could usefully branch on which way a package was malformed. It cannot:
every one of them means the package must not be read as evidence.

Subclasses ``ScientificCoreError`` so a caller catching the platform's root
error still catches these, which is the same choice ``ElectricalDCError`` makes
in the DC domain.
"""

from __future__ import annotations

from ..scientific.errors import ScientificCoreError

__all__ = ["EvidencePackageError"]


class EvidencePackageError(ScientificCoreError):
    """An evidence package is malformed, or claims a verdict it does not support."""
