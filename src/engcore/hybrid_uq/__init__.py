"""Core V2: routed uncertainty quantification -- a resolved grid, a named local-Gaussian route, or a refusal.

Core V1 can produce parameter covariance, intervals, identifiability and predictive uncertainty only by
enumerating a tensor grid, which is m^p forward evaluations. This package ADDS a scalable route beside it
and changes nothing in V1:

* ``POSTERIOR_GRID`` -- V1's grid, used only after the repaired V1 resolution checks accept it;
* ``LOCAL_GAUSSIAN_APPROXIMATION`` -- N(z_hat, (J_w^T J_w)^-1) at the calibrated estimate, O(p) forward
  evaluations, with mandatory validity diagnostics and multistart;
* ``LINEARIZED_PREDICTIVE_UQ`` -- parameter and measurement uncertainty, separately.

No approximation class is an exact posterior. Route validity and identifiability are separate records. A
refused route emits no numbers. The surface is defined in docs/CORE_V2_API_DESIGN.md; no V1 canonical module
exports a V2 name, so the V1 frozen digest cannot move.
"""

from .identifiability import RoutedIdentifiability, assess_routed_identifiability
from .local_gaussian import (
    LocalGaussianPosterior,
    MultistartPolicy,
    ParameterInterval,
    RouteDiagnostics,
    local_gaussian_posterior,
)
from .predictive import RoutedPredictiveUncertainty, grid_predictive_uncertainty, linearized_predictive_uq
from .router import GridRebuildPolicy, HybridUQResult, route_uncertainty, routed_predictive_uncertainty
from .sensitivity import LocalSensitivity, reconstruct_local_sensitivity
from .vocabulary import (
    GRID_ROUTE_MAXIMUM_PARAMETERS,
    MEASUREMENT_UNCERTAINTY,
    MODEL_DISCREPANCY_NOT_MODELLED,
    PARAMETER_UNCERTAINTY,
    UNCERTAINTY_SOURCES,
    ApproximationClass,
    HybridUQError,
    RouteClaim,
    RouteDecision,
    RouteReason,
    RouteRefusedError,
)

__all__ = [
    "ApproximationClass",
    "RouteClaim",
    "RouteReason",
    "RouteDecision",
    "HybridUQError",
    "RouteRefusedError",
    "PARAMETER_UNCERTAINTY",
    "MEASUREMENT_UNCERTAINTY",
    "MODEL_DISCREPANCY_NOT_MODELLED",
    "UNCERTAINTY_SOURCES",
    "GRID_ROUTE_MAXIMUM_PARAMETERS",
    "LocalSensitivity",
    "reconstruct_local_sensitivity",
    "MultistartPolicy",
    "RouteDiagnostics",
    "ParameterInterval",
    "LocalGaussianPosterior",
    "local_gaussian_posterior",
    "RoutedIdentifiability",
    "assess_routed_identifiability",
    "RoutedPredictiveUncertainty",
    "linearized_predictive_uq",
    "grid_predictive_uncertainty",
    "GridRebuildPolicy",
    "HybridUQResult",
    "route_uncertainty",
    "routed_predictive_uncertainty",
]
