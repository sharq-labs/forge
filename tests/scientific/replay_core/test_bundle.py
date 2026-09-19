import pytest
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.replay_core import ArtifactIdentity, ReplayBundle, RuntimeEnvironment

def env():
    return RuntimeEnvironment("Python 3.12","linux","a"*64)

def test_bundle_rejects_duplicate_artifact_identity():
    a=ArtifactIdentity("law","x","b"*64)
    with pytest.raises(InvalidScientificProblem):
        ReplayBundle("r",(a,a),env(),1)
