"""Credibility evidence reporting for consumers of the scientific runtime.

A consumer of ``engcore.scientific``, never a modifier of it. Nothing here
computes physics, evaluates a validity condition or re-runs a check: this layer
transports judgements already made — by a model's validity domain, by a
solver's validation — into one record an engineer of record can read, and
derives a single advisory verdict from them.

This is the verification and validation (V&V) layer: it reports credibility
in the sense ASME V&V 10/20/40 and NASA-STD-7009 use the word, claims no
conformance with any of them, and is advisory input to an engineer of record
rather than a decision. See :mod:`engcore.mcp.evidence` for the full statement.

- ``evidence``  the :class:`~engcore.mcp.evidence.CredibilityEvidenceReport`
                record and the one pure function that decides a verdict
- ``errors``    the one error this layer raises
"""

from __future__ import annotations

from .errors import CredibilityEvidenceError, EvidencePackageError
from .evidence import (
    ASSERTED_CONTEXT_SCHEMA,
    EVIDENCE_PACKAGE_SCHEMA,
    MODEL_VALIDITY_SCHEMA,
    AssertedContext,
    CredibilityEvidenceReport,
    CredibilityVerdict,
    EvidencePackage,
    ModelValidityRecord,
    derive_verdict,
)

__all__ = [
    "ASSERTED_CONTEXT_SCHEMA",
    "EVIDENCE_PACKAGE_SCHEMA",
    "MODEL_VALIDITY_SCHEMA",
    "AssertedContext",
    "CredibilityEvidenceError",
    "CredibilityEvidenceReport",
    "CredibilityVerdict",
    "EvidencePackage",  # deprecated alias
    "EvidencePackageError",  # deprecated alias
    "ModelValidityRecord",
    "derive_verdict",
]
