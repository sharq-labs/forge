from engcore.scientific.replay_core import *


def profile():
    return RunManifestProfile("p",("scientific_law",),("scientific_law",),False)

def env():
    return RuntimeEnvironment("Python 3.12","linux","a"*64)

def artifact():
    return (ArtifactIdentity("scientific_law","law","b"*64),)

def test_manifest_lineage_binds_parent_run_to_exact_parent_manifest_digest():
    root=ScientificRunManifest("root",profile(),artifact(),env())
    child=ScientificRunManifest("child",profile(),artifact(),env(),
                                parent_run_id=root.run_id,parent_manifest_digest=root.digest)
    assert verify_manifest_lineage((root,child)).verified

def test_manifest_lineage_refuses_missing_or_wrong_parent_identity():
    root=ScientificRunManifest("root",profile(),artifact(),env())
    child=ScientificRunManifest("child",profile(),artifact(),env(),
                                parent_run_id=root.run_id,parent_manifest_digest="f"*64)
    result=verify_manifest_lineage((root,child))
    assert not result.verified
