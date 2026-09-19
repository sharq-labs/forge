from engcore.scientific.certification_core import *

def test_certification_fingerprint_is_order_stable():
    p=CertificationProfile("prod",("a","b"))
    g1=CertificationGateResult("a",True,"a"*64);g2=CertificationGateResult("b",True,"b"*64)
    a1=CertificationArtifact("x","c"*64);a2=CertificationArtifact("y","d"*64)
    r1=CertificationRecord("e"*40,p,(g1,g2),(a1,a2));r2=CertificationRecord("e"*40,p,(g2,g1),(a2,a1))
    assert certification_record_fingerprint(r1)==certification_record_fingerprint(r2)
