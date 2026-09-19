from engcore.uq.budget import assess_coverage

def test_coverage_is_empirical_not_assumed():
    r=assess_coverage(94,100,0.95)
    assert not r.adequate
