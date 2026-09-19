from engcore.scientific.certification_core import *

def test_missing_required_gate_refuses_certification():
    p=CertificationProfile("prod",("fast","scientific"))
    r=CertificationRecord("a"*40,p,(CertificationGateResult("fast",True,"b"*64),),(CertificationArtifact("report","c"*64),))
    assert not verify_certification_record(r).verified
