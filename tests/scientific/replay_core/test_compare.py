from engcore.scientific.replay_core import ReplayTolerance, compare_numeric

def test_numeric_replay_uses_max_absolute_or_relative_tolerance():
    result=compare_numeric(100.0,100.05,ReplayTolerance(absolute=0.01,relative=0.001))
    assert result.matched
