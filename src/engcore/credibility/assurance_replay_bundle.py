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
from ..scientific.knowledge import (
    FreshnessPolicy,
    KnowledgeSnapshot,
    KnowledgeSourceClass,
    SourcePin,
    TrustedSourceRegistry,
)
from ..scientific.measurements import CalibratedMeasurementObservation
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
    "production_scientific_assurance_bundle", 2
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
    knowledge_trust: TrustedSourceRegistry
    knowledge_freshness: FreshnessPolicy
    measurement_observations: tuple[CalibratedMeasurementObservation, ...] = ()

    def __post_init__(self) -> None:
        observations = tuple(
            sorted(
                tuple(self.measurement_observations),
                key=lambda item: (
                    getattr(item, "observation_id", ""),
                    getattr(item, "digest", ""),
                ),
            )
        )
        object.__setattr__(self, "measurement_observations", observations)
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
            knowledge_trust=self.knowledge_trust,
            knowledge_freshness=self.knowledge_freshness,
            measurement_observations=self.measurement_observations,
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
                    knowledge_trust=self.knowledge_trust,
                    knowledge_freshness=self.knowledge_freshness,
                    measurement_observations=self.measurement_observations,
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
            "knowledge_trust_pins": [
                pin.to_dict()
                for pin in sorted(
                    self.knowledge_trust.pins,
                    key=lambda item: item.source_id,
                )
            ],
            "knowledge_freshness_policy": self.knowledge_freshness.to_dict(),
            "measurement_observations": [
                observation.to_dict()
                for observation in self.measurement_observations
            ],
        }

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
        *,
        knowledge_trust: TrustedSourceRegistry,
        knowledge_freshness: FreshnessPolicy,
    ) -> "ProductionAssuranceBundle":
        require_schema(payload, PRODUCTION_ASSURANCE_BUNDLE_SCHEMA)
        if not isinstance(knowledge_trust, TrustedSourceRegistry):
            raise InvalidScientificProblem(
                "production assurance bundle reader requires authoritative knowledge trust"
            )
        if not isinstance(knowledge_freshness, FreshnessPolicy):
            raise InvalidScientificProblem(
                "production assurance bundle reader requires authoritative freshness policy"
            )
        carried_trust = TrustedSourceRegistry(
            tuple(
                SourcePin(
                    item["source_id"],
                    item["issuer"],
                    item["document_digest"],
                    item["version"],
                )
                for item in payload.get("knowledge_trust_pins", ())
            )
        )
        raw_freshness = payload.get("knowledge_freshness_policy")
        if not isinstance(raw_freshness, Mapping):
            raise InvalidScientificProblem(
                "production assurance bundle carries no freshness policy"
            )
        carried_freshness = FreshnessPolicy(
            {
                KnowledgeSourceClass(key): value
                for key, value in dict(
                    raw_freshness.get("max_age_days", {})
                ).items()
            },
            bool(raw_freshness.get("require_timestamp", True)),
        )
        if carried_trust.digest != knowledge_trust.digest:
            raise InvalidScientificProblem(
                "production assurance bundle knowledge trust registry differs from the authoritative registry"
            )
        if carried_freshness.digest != knowledge_freshness.digest:
            raise InvalidScientificProblem(
                "production assurance bundle freshness policy differs from the authoritative policy"
            )
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
            knowledge_trust,
            knowledge_freshness,
            tuple(
                CalibratedMeasurementObservation.from_dict(item)
                for item in payload.get("measurement_observations", ())
            ),
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
        kwargs["knowledge_trust"],
        kwargs["knowledge_freshness"],
        tuple(kwargs.get("measurement_observations", ())),
    )
