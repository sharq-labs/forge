"""Shared inference contracts pulled by K1.5 and K2 evidence.

The package keeps domain meaning outside the shared inference layer.  K1.5
provides the numerical-admissibility boundary; K2 adds a small reusable grid
posterior engine that can consume only predictions already admitted through
that boundary.
"""

from .admissibility import (
    AdmissibleNumericalPrediction,
    InferenceAdmissibilityError,
    require_admissible_numerical_prediction,
)
from .grid import (
    AdmittedForwardRow,
    AdmittedForwardTable,
    GaussianObservation,
    InferenceProblemError,
    ObservationSet,
    PosteriorGrid,
    gaussian_grid_posterior,
)

__all__ = [
    "AdmissibleNumericalPrediction",
    "InferenceAdmissibilityError",
    "require_admissible_numerical_prediction",
    "AdmittedForwardRow",
    "AdmittedForwardTable",
    "GaussianObservation",
    "InferenceProblemError",
    "ObservationSet",
    "PosteriorGrid",
    "gaussian_grid_posterior",
]
