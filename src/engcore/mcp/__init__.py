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

- ``problem``   the input boundary: a JSON description of a case becomes a
                posed problem, or is refused with the field that stopped it
- ``evidence``  the :class:`~engcore.mcp.evidence.CredibilityEvidenceReport`
                record and the one pure function that decides a verdict
- ``errors``    what this layer raises: one type for an unreadable report, one
                per failure class for an unbuildable payload
- ``server``    the MCP stdio transport over the three above. **Deliberately
                not imported here**: it needs the optional ``[mcp]``
                dependency group, and importing it from this package would
                make the whole layer unavailable without an SDK that nothing
                else in it uses. Import ``engcore.mcp.server`` directly.
"""

from __future__ import annotations

from .errors import (
    CredibilityEvidenceError,
    EvidencePackageError,
    MalformedPayloadError,
    MissingFieldError,
    MissingUnitError,
    ProblemPayloadError,
    UnknownFieldError,
    WrongDimensionError,
)
from .evidence import (
    ASSERTED_CONTEXT_SCHEMA,
    EVIDENCE_PACKAGE_SCHEMA,
    MODEL_VALIDITY_SCHEMA,
    AssertedContext,
    CouplingCriterion,
    CouplingEvidence,
    CredibilityEvidenceReport,
    CredibilityVerdict,
    EvidencePackage,
    ModelValidityRecord,
    classify_assessment,
    combine_assessments,
    derive_verdict,
)
from .problem import (
    COUPLING_SUPPLIED_INPUTS,
    CaseDescription,
    ElectroThermalCaseRun,
    FieldDescription,
    build_electrothermal_problems,
    build_electrothermal_system,
    describe_electrothermal_case,
    example_electrothermal_payload,
    run_electrothermal_case,
)

__all__ = [
    "ASSERTED_CONTEXT_SCHEMA",
    "COUPLING_SUPPLIED_INPUTS",
    "EVIDENCE_PACKAGE_SCHEMA",
    "MODEL_VALIDITY_SCHEMA",
    "AssertedContext",
    "CouplingCriterion",
    "CouplingEvidence",
    "CaseDescription",
    "CredibilityEvidenceError",
    "CredibilityEvidenceReport",
    "CredibilityVerdict",
    "ElectroThermalCaseRun",
    "EvidencePackage",  # deprecated alias
    "EvidencePackageError",  # deprecated alias
    "FieldDescription",
    "MalformedPayloadError",
    "MissingFieldError",
    "MissingUnitError",
    "ModelValidityRecord",
    "classify_assessment",
    "combine_assessments",
    "ProblemPayloadError",
    "UnknownFieldError",
    "WrongDimensionError",
    "build_electrothermal_problems",
    "build_electrothermal_system",
    "derive_verdict",
    "describe_electrothermal_case",
    "example_electrothermal_payload",
    "run_electrothermal_case",
]
