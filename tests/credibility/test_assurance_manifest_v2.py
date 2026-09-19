from datetime import datetime, timezone
import pytest

from engcore.credibility.assurance_manifest import (
    PRODUCTION_ASSURANCE_PROFILE, build_production_assurance_manifest,
)
from engcore.credibility.evidence_graph import EvidenceGraph, EvidenceNode
from engcore.credibility.knowledge_evidence import evidence_from_knowledge
from engcore.scientific.certification_core import (
    CertificationArtifact, CertificationGateResult, CertificationProfile,
    CertificationRecord,
)
from engcore.scientific.equations import LawReference
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.replay_core import (
    OutputExpectation, OutputObservation, RunReplayRecord, RuntimeEnvironment,
    verify_run_manifest,
)
from engcore.scientific.results.provenance import ProvenanceRecord
from engcore.scientific.results.uncertainty import (
    Uncertainty, UncertaintyKind, UncertaintySource,
)
from engcore.scientific.units.quantity import Quantity
from engcore.scientific.validation_core import (
    StageResult, ValidationDecision, ValidationReport, ValidationStage,
)
from engcore.scientific.verification import (
    DependencyComponent, DependencyRole, RouteDependencyManifest,
    VerificationCandidate, VerificationObservation, VerificationPolicy,
    VerificationRoute, VerificationRouteKind, VerificationRunRecord,
    plan_verification,
)
from engcore.uq.combined import (
    CombinationMode, CombinationPolicy, UncertaintyContribution,
    combine_uncertainties,
)
from tests.scientific.knowledge.helpers import (
    CONTEXT, freshness, registry, snapshot,
)


def environment():
    return RuntimeEnvironment("Python 3.12","linux","9"*64,"x86","IEEE-754")


def validation():
    return ValidationReport(
        ValidationDecision.ACCEPTED,
        tuple(StageResult(stage,True) for stage in ValidationStage),
    )


def certification(*, required=("fast",), passed=True):
    return CertificationRecord(
        "a"*40,
        CertificationProfile("prod",tuple(required)),
        (CertificationGateResult("fast",passed,"b"*64),),
        (CertificationArtifact("report","d"*64),),
    )


def combined_uq():
    primitive=Uncertainty(
        kind=UncertaintyKind.STANDARD,
        standard_uncertainty=Quantity(1,"kelvin"),
        method="measurement standard uncertainty",
        source_kind=UncertaintySource.MEASUREMENT,
    )
    contribution=UncertaintyContribution(
        "measurement",primitive,"e"*64,("f"*64,),"measurement-independent",
    )
    return combine_uncertainties(
        Quantity(300,"kelvin"),
        (contribution,),
        CombinationPolicy(CombinationMode.STANDARD_RSS),
    )


def verification(*, candidate_value=300.2):
    primary_route=VerificationRoute(
        "primary",VerificationRouteKind.DIFFERENT_IMPLEMENTATION,"1"*64
    )
    primary_dependencies=RouteDependencyManifest(
        "primary",
        (DependencyComponent("solver-primary","2"*64,DependencyRole.SOLVER),),
        "internal",
    )
    candidate_route=VerificationRoute(
        "external",VerificationRouteKind.EXTERNAL_SOLVER,"3"*64
    )
    candidate_dependencies=RouteDependencyManifest(
        "external",
        (DependencyComponent("solver-external","4"*64,DependencyRole.SOLVER),),
        "external-lab",True,
    )
    plan=plan_verification(
        primary_route,primary_dependencies,
        (VerificationCandidate(candidate_route,candidate_dependencies),),
        VerificationPolicy(),
    )
    return VerificationRunRecord(
        plan,
        VerificationObservation("primary",Quantity(300,"kelvin"),"5"*64,True),
        (VerificationObservation("external",Quantity(candidate_value,"kelvin"),"6"*64,True),),
        Quantity(1,"kelvin"),
    )


def evidence_graph():
    snap=snapshot()
    node=evidence_from_knowledge(
        snap,"claim-1",registry(),freshness(),
        now=datetime(2026,9,19,tzinfo=timezone.utc),
        target_context_digest=CONTEXT,
    )
    return snap,EvidenceGraph((node,))


def build(run_id="run", **overrides):
    snap,graph=evidence_graph()
    return build_production_assurance_manifest(
        run_id=run_id,
        environment=overrides.pop("environment",environment()),
        law=overrides.pop("law",LawReference("law","7"*64)),
        knowledge=overrides.pop("knowledge",snap),
        evidence=overrides.pop("evidence",graph),
        validation=overrides.pop("validation",validation()),
        combined_uq=overrides.pop("combined_uq",combined_uq()),
        verification=overrides.pop("verification",verification()),
        certification=overrides.pop("certification",certification()),
        provenance=overrides.pop(
            "provenance",ProvenanceRecord(run_id,git_commit="a"*40)
        ),
        random_seed=overrides.pop("random_seed",17),
        parent=overrides.pop("parent",None),
        replay_of=overrides.pop("replay_of",None),
    )


def test_production_manifest_contains_exactly_the_eight_required_assurance_artifacts():
    manifest=build()
    assert manifest.profile==PRODUCTION_ASSURANCE_PROFILE
    assert {a.kind for a in manifest.contract_artifacts}==set(
        PRODUCTION_ASSURANCE_PROFILE.required_artifact_kinds
    )
    assert len(manifest.contract_artifacts)==8


def test_production_manifest_rederives_validation_instead_of_trusting_accepted_flag():
    forged=ValidationReport(ValidationDecision.ACCEPTED,())
    with pytest.raises(InvalidScientificProblem,match="validation report decision"):
        build(validation=forged)


def test_production_manifest_requires_complete_independent_verification():
    with pytest.raises(InvalidScientificProblem,match="independently verified"):
        build(verification=verification(candidate_value=303))


def test_production_manifest_refuses_certification_profile_with_no_required_gate():
    with pytest.raises(InvalidScientificProblem,match="at least one gate"):
        build(certification=certification(required=()))


def test_production_manifest_binds_provenance_commit_to_certification_commit():
    with pytest.raises(InvalidScientificProblem,match="git commit"):
        build(provenance=ProvenanceRecord("run",git_commit="b"*40))


def test_production_manifest_refuses_knowledge_evidence_whose_pin_rederives_untrusted():
    snap,graph=evidence_graph()
    payload=graph.nodes[0].to_dict()
    payload["provenance"].pop("trust_status")
    payload["provenance"]["pin_document_digest"]="0"*64
    tampered=EvidenceGraph((EvidenceNode.from_dict(payload),))
    with pytest.raises(InvalidScientificProblem,match="not pinned/trusted"):
        build(knowledge=snap,evidence=tampered)


def test_full_production_manifest_can_be_replayed_with_new_run_provenance_and_typed_output_tolerance():
    expected=build("run")
    actual=build(
        "replay-run",
        provenance=ProvenanceRecord("replay-run",git_commit="a"*40),
        replay_of=expected,
    )
    assert verify_run_manifest(expected,actual).verified
    replay=RunReplayRecord(
        expected,actual,
        (OutputExpectation(
            "temperature",Quantity(300,"kelvin"),Quantity(1,"kelvin"),0,
        ),),
        (OutputObservation(
            "temperature",Quantity(300.5,"kelvin"),"8"*64,
        ),),
    )
    assert replay.verification.verified
