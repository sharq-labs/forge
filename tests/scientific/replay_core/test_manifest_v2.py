import pytest

from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.replay_core import (
    ArtifactIdentity,RunManifestProfile,RuntimeEnvironment,ScientificRunManifest,
)


def env(digest="a"*64):
    return RuntimeEnvironment("Python 3.12","linux",digest,"x86","IEEE-754")


def profile():
    return RunManifestProfile(
        "production",
        ("scientific_law","knowledge_snapshot","evidence_graph"),
        ("scientific_law","knowledge_snapshot","evidence_graph"),
        False,
    )


def artifacts():
    return (
        ArtifactIdentity("evidence_graph","e","3"*64),
        ArtifactIdentity("scientific_law","law","1"*64),
        ArtifactIdentity("knowledge_snapshot","k","2"*64),
    )


def manifest(run_id="run",**kwargs):
    return ScientificRunManifest(
        run_id,profile(),kwargs.pop("artifacts",artifacts()),
        kwargs.pop("environment",env()),kwargs.pop("random_seed",7),
        kwargs.pop("parent_run_id",None),kwargs.pop("parent_manifest_digest",None),
        kwargs.pop("replay_of_manifest_digest",None),
    )


def test_manifest_is_order_independent_and_content_addressed():
    a=manifest(artifacts=artifacts())
    b=manifest(artifacts=tuple(reversed(artifacts())))
    assert a.contract_artifacts==b.contract_artifacts
    assert a.digest==b.digest
    assert ScientificRunManifest.from_dict(a.to_dict()).to_dict()==a.to_dict()


def test_missing_required_artifact_kind_is_refused():
    with pytest.raises(InvalidScientificProblem,match="missing required"):
        manifest(artifacts=artifacts()[:-1])


def test_manifest_wire_digest_is_rederived():
    payload=manifest().to_dict()
    payload["manifest_digest"]="f"*64
    with pytest.raises(InvalidScientificProblem,match="forged"):
        ScientificRunManifest.from_dict(payload)


def test_parent_lineage_requires_both_parent_id_and_parent_digest():
    with pytest.raises(InvalidScientificProblem,match="declared together"):
        manifest(parent_run_id="parent")


def test_replay_exact_kinds_must_be_required_by_profile():
    with pytest.raises(InvalidScientificProblem,match="subset"):
        RunManifestProfile(
            "bad",("scientific_law",),("scientific_law",),True,
            ("knowledge_snapshot",),
        )


def test_same_artifact_kind_and_identifier_cannot_bind_two_digests():
    duplicate=(
        ArtifactIdentity("scientific_law","law","1"*64),
        ArtifactIdentity("scientific_law","law","2"*64),
        ArtifactIdentity("knowledge_snapshot","k","3"*64),
        ArtifactIdentity("evidence_graph","e","4"*64),
    )
    with pytest.raises(InvalidScientificProblem,match="duplicate artifact"):
        manifest(artifacts=duplicate)
