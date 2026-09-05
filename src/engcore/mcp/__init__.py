"""Evidence packaging for consumers of the scientific runtime.

A consumer of ``engcore.scientific``, never a modifier of it. Nothing here
computes physics, evaluates a validity condition or re-runs a check: this layer
transports judgements already made — by a model's validity domain, by a
solver's validation — into one record an engineer of record can read, and
derives a single advisory verdict from them.

- ``evidence``  the :class:`~engcore.mcp.evidence.EvidencePackage` record and
                the one pure function that decides a verdict
- ``errors``    the one error this layer raises
"""

from __future__ import annotations

from .errors import EvidencePackageError
from .evidence import (
    ASSERTED_CONTEXT_SCHEMA,
    EVIDENCE_PACKAGE_SCHEMA,
    MODEL_VALIDITY_SCHEMA,
    AssertedContext,
    EvidencePackage,
    EvidenceVerdict,
    ModelValidityRecord,
    derive_verdict,
)

__all__ = [
    "ASSERTED_CONTEXT_SCHEMA",
    "EVIDENCE_PACKAGE_SCHEMA",
    "MODEL_VALIDITY_SCHEMA",
    "AssertedContext",
    "EvidencePackage",
    "EvidencePackageError",
    "EvidenceVerdict",
    "ModelValidityRecord",
    "derive_verdict",
]
