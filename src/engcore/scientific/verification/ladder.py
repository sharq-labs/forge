from enum import IntEnum
from .route import VerificationRouteKind


class VerificationLevel(IntEnum):
    V0=0
    V1=1
    V2=2
    V3=3
    V4=4
    V5=5
    V6=6
    V7=7


def level_for_route(kind:VerificationRouteKind)->VerificationLevel:
    mapping={
        VerificationRouteKind.SAME_SOLVER_RERUN:VerificationLevel.V0,
        VerificationRouteKind.DIFFERENT_ALGORITHM:VerificationLevel.V1,
        VerificationRouteKind.DIFFERENT_IMPLEMENTATION:VerificationLevel.V2,
        VerificationRouteKind.DIFFERENT_MODEL:VerificationLevel.V3,
        VerificationRouteKind.ANALYTICAL_REFERENCE:VerificationLevel.V4,
        VerificationRouteKind.EXTERNAL_SOLVER:VerificationLevel.V5,
        VerificationRouteKind.EXPERIMENTAL_MEASUREMENT:VerificationLevel.V6,
        VerificationRouteKind.INDEPENDENT_REPRODUCTION:VerificationLevel.V7,
    }
    return mapping[VerificationRouteKind(kind)]
