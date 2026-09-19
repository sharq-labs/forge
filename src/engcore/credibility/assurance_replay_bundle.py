"""Self-contained, revalidated payload bundle for production scientific assurance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..scientific.certification_core import CertificationRecord
from ..scientific.certification_core.serialization import (
    certification_from_dict,
    certification_to_dict,
)
from ..scientific.equations import LawReference
from ..scientific.errors import InvalidScientificProblem
from ..scientific.knowledge import KnowledgeSnapshot
from ..scientific.replay_core import ScientificRunManifest
from ..scientific.results.provenance import ProvenanceRecord
from ..scientific.serialization import require_schema, schema_string
from ..scientific.validation_core import ValidationReport
from ..scientific.verification import VerificationRunRecord
from ..uq.combined import CombinationReport, report_from_dict, report_to_dict
from .assurance_manifest import (
    PRODUCTION_ASSURANCE_PROFILE,
    build_production_assurance_manifest,
    production_assurance_artifacts,
    validate_production_assurance_components,
)
from .evidence_graph import EvidenceGraph

PRODUCTION_ASSURANCE_BUNDLE_SCHEMA = schema_string(
    "production_scientific_assurance_bundle"
)


@dataclass(frozen=True)
class ProductionAssuranceBundle:
    manifest: ScientificRunManifest
    law: LawReference
    knowledge: KnowledgeSnapshot
    evidence: EvidenceGraph
    validation: ValidationReport
    combined_uq: CombinationReport
    verification: VerificationRunRecord
    certification: CertificationRecord
    provenance: ProvenanceRecord

    def __post_init__(self) -> None:
        if not isinstance(self.manifest, ScientificRunManifest):
            raise InvalidScientificProblem(
                "production assurance bundle requires ScientificRunManifest"
            )
        if self.manifest.profile != PRODUCTION_ASSURANCE_PROFILE:
            raise InvalidScientificProblem(
                "production assurance bundle manifest uses the wrong profile"
            )
        validate_production_assurance_components(
            run_id=self.manifest.run_id,
            law=self.law,
            knowledge=self.knowledge,
            evidence=self.evidence,
            validation=self.validation,
            combined_uq=self.combined_uq,
            verification=self.verification,
            certification=self.certification,
            provenance=self.provenance,
        )
        expected = tuple(
            sorted(
                production_assurance_artifacts(
                    law=self.law,
                    knowledge=self.knowledge,
                    evidence=self.evidence,
                    validation=self.validation,
                    combined_uq=self.combined_uq,
                    verification=self.verification,
                    certification=self.certification,
                    provenance=self.provenance,
                ),
                key=lambda a: (a.kind, a.identifier, a.digest),
            )
        )
        if self.manifest.contract_artifacts != expected:
            raise InvalidScientificProblem(
                "production assurance bundle payload digests do not match its manifest"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PRODUCTION_ASSURANCE_BUNDLE_SCHEMA,
            "manifest": self.manifest.to_dict(),
            "law": self.law.to_dict(),
            "knowledge": self.knowledge.to_dict(),
            "evidence": self.evidence.to_dict(),
            "validation": self.validation.to_dict(),
            "combined_uq": report_to_dict(self.combined_uq),
            "verification": self.verification.to_dict(),
            "certification": certification_to_dict(self.certification),
            "provenance": self.provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProductionAssuranceBundle":
        require_schema(payload, PRODUCTION_ASSURANCE_BUNDLE_SCHEMA)
        return cls(
            ScientificRunManifest.from_dict(payload["manifest"]),
            LawReference.from_dict(payload["law"]),
            KnowledgeSnapshot.from_dict(payload["knowledge"]),
            EvidenceGraph.from_dict(payload["evidence"]),
            ValidationReport.from_dict(payload["validation"]),
            report_from_dict(payload["combined_uq"]),
            VerificationRunRecord.from_dict(payload["verification"]),
            certification_from_dict(payload["certification"]),
            ProvenanceRecord.from_dict(payload["provenance"]),
        )


def build_production_assurance_bundle(**kwargs: Any) -> ProductionAssuranceBundle:
    manifest = build_production_assurance_manifest(**kwargs)
    return ProductionAssuranceBundle(
        manifest,
        kwargs["law"],
        kwargs["knowledge"],
        kwargs["evidence"],
        kwargs["validation"],
        kwargs["combined_uq"],
        kwargs["verification"],
        kwargs["certification"],
        kwargs["provenance"],
    )
