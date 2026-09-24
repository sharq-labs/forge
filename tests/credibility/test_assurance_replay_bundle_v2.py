from dataclasses import replace
import pytest

from engcore.credibility.assurance_manifest import (
    PRODUCTION_ASSURANCE_PROFILE, production_assurance_artifacts,
)
from engcore.credibility.assurance_replay_bundle import (
    ProductionAssuranceBundle, build_production_assurance_bundle,
)
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.replay_core import ScientificRunManifest
from engcore.scientific.validation_core import ValidationDecision, ValidationReport
from tests.credibility.test_assurance_manifest_v2 import (
    certification, combined_uq, environment, evidence_graph,
    provenance, validation, verification,
)
from tests.scientific.knowledge.helpers import freshness, registry
from engcore.scientific.equations import LawReference


def kwargs(run_id="run"):
    knowledge,evidence=evidence_graph()
    return {
        "run_id":run_id,
        "environment":environment(),
        "law":LawReference("law","7"*64),
        "knowledge":knowledge,
        "evidence":evidence,
        "validation":validation(),
        "combined_uq":combined_uq(),
        "verification":verification(),
        "certification":certification(),
        "provenance":provenance(run_id),
        "knowledge_trust":registry(),
        "knowledge_freshness":freshness(),
        "random_seed":17,
    }


def test_production_assurance_bundle_round_trips_all_payloads_and_manifest():
    bundle=build_production_assurance_bundle(**kwargs())
    restored=ProductionAssuranceBundle.from_dict(
        bundle.to_dict(),
        knowledge_trust=bundle.knowledge_trust,
        knowledge_freshness=bundle.knowledge_freshness,
    )
    assert restored.to_dict()==bundle.to_dict()


def test_production_assurance_bundle_refuses_a_manifest_from_another_profile():
    bundle=build_production_assurance_bundle(**kwargs())
    wrong_profile=replace(
        PRODUCTION_ASSURANCE_PROFILE,
        profile_id="not-production-assurance",
    )
    wrong_manifest=replace(bundle.manifest,profile=wrong_profile)
    with pytest.raises(InvalidScientificProblem,match="wrong profile"):
        ProductionAssuranceBundle(
            wrong_manifest,bundle.law,bundle.knowledge,bundle.evidence,
            bundle.validation,bundle.combined_uq,bundle.verification,
            bundle.certification,bundle.provenance,bundle.knowledge_trust,
            bundle.knowledge_freshness,bundle.measurement_observations,
        )


def test_evidence_graph_payload_round_trip_is_typed():
    bundle=build_production_assurance_bundle(**kwargs())
    restored=type(bundle.evidence).from_dict(bundle.evidence.to_dict())
    assert restored.to_dict()==bundle.evidence.to_dict()


def test_payload_change_with_old_manifest_is_refused_by_content_addressing():
    bundle=build_production_assurance_bundle(**kwargs())
    payload=bundle.to_dict()
    payload["law"]["fingerprint"]="8"*64
    with pytest.raises(InvalidScientificProblem,match="payload digests"):
        ProductionAssuranceBundle.from_dict(
            payload,
            knowledge_trust=bundle.knowledge_trust,
            knowledge_freshness=bundle.knowledge_freshness,
        )


def test_rehashed_forged_validation_is_still_refused_by_semantic_revalidation():
    base=build_production_assurance_bundle(**kwargs())
    forged=ValidationReport(ValidationDecision.ACCEPTED,())
    artifacts=production_assurance_artifacts(
        law=base.law,knowledge=base.knowledge,evidence=base.evidence,
        validation=forged,combined_uq=base.combined_uq,
        verification=base.verification,certification=base.certification,
        provenance=base.provenance,
        knowledge_trust=base.knowledge_trust,
        knowledge_freshness=base.knowledge_freshness,
    )
    forged_manifest=ScientificRunManifest(
        base.manifest.run_id,PRODUCTION_ASSURANCE_PROFILE,artifacts,
        base.manifest.environment,base.manifest.random_seed,
        base.manifest.parent_run_id,base.manifest.parent_manifest_digest,
        base.manifest.replay_of_manifest_digest,
    )
    with pytest.raises(InvalidScientificProblem,match="validation report decision"):
        ProductionAssuranceBundle(
            forged_manifest,base.law,base.knowledge,base.evidence,forged,
            base.combined_uq,base.verification,base.certification,base.provenance,
            base.knowledge_trust,base.knowledge_freshness,
        )


def test_rehashed_provenance_with_wrong_certified_commit_is_still_refused():
    base=build_production_assurance_bundle(**kwargs())
    forged=provenance(base.manifest.run_id,git_commit="b"*40)
    artifacts=production_assurance_artifacts(
        law=base.law,knowledge=base.knowledge,evidence=base.evidence,
        validation=base.validation,combined_uq=base.combined_uq,
        verification=base.verification,certification=base.certification,
        provenance=forged,
        knowledge_trust=base.knowledge_trust,
        knowledge_freshness=base.knowledge_freshness,
    )
    forged_manifest=ScientificRunManifest(
        base.manifest.run_id,PRODUCTION_ASSURANCE_PROFILE,artifacts,
        base.manifest.environment,base.manifest.random_seed,
    )
    with pytest.raises(InvalidScientificProblem,match="git commit"):
        ProductionAssuranceBundle(
            forged_manifest,base.law,base.knowledge,base.evidence,base.validation,
            base.combined_uq,base.verification,base.certification,forged,
            base.knowledge_trust,base.knowledge_freshness,
        )
