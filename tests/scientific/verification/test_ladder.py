from engcore.scientific.verification import *

def test_external_solver_is_v5_not_truth():
    assert level_for_route(VerificationRouteKind.EXTERNAL_SOLVER) is VerificationLevel.V5
