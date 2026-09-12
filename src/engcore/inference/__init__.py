"""Shared inference contracts pulled by K1.5 and K2 evidence.

The package keeps domain meaning outside the shared inference layer.  K1.5
provides the numerical-admissibility boundary; K2 adds a small reusable grid
posterior engine that can consume only predictions already admitted through
that boundary.

Sprint 8 adds the third contract: what a calibrated parameter *is*.  The grid
engine identifies its axes by ``parameter_names``, a tuple of display strings,
and ``parameters`` supplies the identity those strings stand for -- canonical
name, unit, model association, physical bounds and transform -- so that "the
same parameter" is a checkable claim rather than a matching label.
"""

from .admissibility import (
    AdmissibleAnalyticPrediction,
    AdmissibleNumericalPrediction,
    InferenceAdmissibilityError,
    require_admissible_analytic_prediction,
    require_admissible_numerical_prediction,
    require_admitted_prediction,
)
from .field_observation import (
    FieldObservationError,
    FieldObservationKind,
    FieldObservationOperator,
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
from .parameters import (
    CalibrationParameterSet,
    ParameterBounds,
    ParameterEstimate,
    ParameterIdentity,
    ParameterIdentityError,
    ParameterTransform,
    bind_parameter_set_to_grid,
    require_parameter_set,
)
from .calibration import (
    CalibrationError,
    CalibrationProvenance,
    CalibrationResult,
    CalibrationSpec,
    CalibrationStatus,
    GridResolutionError,
    IdentifiabilityReport,
    IdentifiabilityStatus,
    NoiseModel,
    assess_identifiability,
    calibrate,
    posterior_effective_sample_size,
    posterior_grid_diagnostics,
    GRID_TOO_COARSE_FOR_INFERENCE,
)
from .split import (
    DataLeakageError,
    ObservationSplit,
    observation_content_digest,
    require_split,
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
    "CalibrationParameterSet",
    "ParameterBounds",
    "ParameterEstimate",
    "ParameterIdentity",
    "ParameterIdentityError",
    "ParameterTransform",
    "bind_parameter_set_to_grid",
    "require_parameter_set",
    "DataLeakageError",
    "ObservationSplit",
    "observation_content_digest",
    "require_split",
    "AdmissibleAnalyticPrediction",
    "require_admissible_analytic_prediction",
    "require_admitted_prediction",
    "CalibrationError",
    "CalibrationProvenance",
    "CalibrationResult",
    "CalibrationSpec",
    "CalibrationStatus",
    "GridResolutionError",
    "IdentifiabilityReport",
    "IdentifiabilityStatus",
    "NoiseModel",
    "assess_identifiability",
    "calibrate",
    "posterior_effective_sample_size",
    "posterior_grid_diagnostics",
    "GRID_TOO_COARSE_FOR_INFERENCE",
    "FieldObservationError",
    "FieldObservationKind",
    "FieldObservationOperator",
]
