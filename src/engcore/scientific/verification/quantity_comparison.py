from __future__ import annotations

import math
from ..errors import InvalidScientificProblem,UnitCompatibilityError
from ..units.quantity import Quantity,require_spread_unit
from .comparison import RouteComparison
from .observations import VerificationObservation


def compare_observations(primary:VerificationObservation,candidate:VerificationObservation,
                         tolerance:Quantity)->RouteComparison:
    if primary.route_id==candidate.route_id: raise InvalidScientificProblem("verification comparison requires distinct routes")
    if not primary.converged or not candidate.converged:
        return RouteComparison(primary.route_id,candidate.route_id,False,None)
    if not isinstance(tolerance,Quantity) or tolerance.magnitude<=0:
        raise InvalidScientificProblem("verification tolerance must be a positive Quantity")
    require_spread_unit(tolerance.units,context="verification tolerance")
    try:
        candidate_value=candidate.value.to(primary.value.units)
        delta=abs(candidate_value.magnitude-primary.value.magnitude)
        tol=tolerance.magnitude_as_spread_in(primary.value.units)
    except UnitCompatibilityError as exc:
        raise InvalidScientificProblem(f"verification quantity dimensions differ: {exc}") from exc
    normalized=delta/tol
    if not math.isfinite(normalized): raise InvalidScientificProblem("verification normalized error is non-finite")
    return RouteComparison(primary.route_id,candidate.route_id,normalized<=1.0,normalized)
