import math
import pytest

from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.replay_core import ReplayTolerance,RuntimeEnvironment


def test_runtime_dependency_digest_requires_actual_sha256_not_only_length():
    with pytest.raises(InvalidScientificProblem,match="SHA-256"):
        RuntimeEnvironment("Python 3.12","linux","z"*64)


def test_replay_tolerance_refuses_nan_and_infinity():
    with pytest.raises(InvalidScientificProblem,match="finite"):
        ReplayTolerance(float("nan"),0)
    with pytest.raises(InvalidScientificProblem,match="finite"):
        ReplayTolerance(0,float("inf"))
