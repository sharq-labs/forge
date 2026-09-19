from engcore.credibility.assurance_bundle import AssuranceBundle

def test_assurance_bundle_round_trip_and_digest_are_deterministic():
    b=AssuranceBundle("a"*64,"b"*64,"c"*64,"d"*64,"e"*64,"f"*64)
    assert AssuranceBundle.from_dict(b.to_dict())==b
    assert b.digest==AssuranceBundle.from_dict(b.to_dict()).digest
