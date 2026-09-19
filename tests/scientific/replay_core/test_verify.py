from engcore.scientific.replay_core import *

def test_environment_drift_refuses_replay_verification():
    a=ArtifactIdentity("law","x","b"*64)
    e1=RuntimeEnvironment("Python 3.12","linux","a"*64)
    e2=RuntimeEnvironment("Python 3.12","linux","c"*64)
    assert not verify_replay_bundle(ReplayBundle("r",(a,),e1,1),ReplayBundle("r",(a,),e2,1)).verified
