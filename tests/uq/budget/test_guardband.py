from engcore.uq.budget import guard_band

def test_guard_band_expands_value_by_k_u():
    assert guard_band(10,2,2).lower==6
