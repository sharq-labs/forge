from engcore.scientific.certification_core import *

def test_failed_gate_is_never_hidden_by_other_green_gates():
    p=CertificationProfile("prod",("fast",))
    r=CertificationRecord("a"*40,p,(CertificationGateResult("fast",False,"b"*64),),(CertificationArtifact("report","c"*64),))
    assert not verify_certification_record(r).verified
