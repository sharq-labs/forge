import pytest
from engcore.scientific.certification_core import *
from engcore.scientific.certification_core.serialization import certification_from_dict,certification_to_dict

def test_certification_round_trip_rederives_verification():
    p=CertificationProfile("prod",("fast",))
    r=CertificationRecord("a"*40,p,(CertificationGateResult("fast",False,"b"*64),),(CertificationArtifact("x","c"*64),))
    payload=certification_to_dict(r);payload["verified"]=True
    with pytest.raises(ValueError,match="forged"):
        certification_from_dict(payload)
