"""Fail-closed scientific discovery candidates.

Discovery proposes hypotheses. It never promotes a fitted pattern directly
into scientific truth.
"""

from .dataset import DiscoveryDataset, DiscoveryFeature
from .candidate import DiscoveredEquationCandidate, DiscoveryCandidateStatus
from .symbolic_regression import SparseDiscoveryPolicy, discover_sparse_equations
from .anomaly import ResidualAnomaly, detect_residual_anomalies
from .regimes import RegimeBoundaryCandidate, detect_regime_boundaries
from .hypothesis_generation import (
    GeneratedHypothesis,
    GeneratedHypothesisKind,
    equation_hypothesis,
    regime_hypothesis,
)
from .campaign import (
    DiscoveryDecision,
    DiscoveryReview,
    review_discovery_candidate,
)

__all__ = [
    "DiscoveryFeature",
    "DiscoveryDataset",
    "DiscoveryCandidateStatus",
    "DiscoveredEquationCandidate",
    "SparseDiscoveryPolicy",
    "discover_sparse_equations",
    "ResidualAnomaly",
    "detect_residual_anomalies",
    "RegimeBoundaryCandidate",
    "detect_regime_boundaries",
    "GeneratedHypothesisKind",
    "GeneratedHypothesis",
    "equation_hypothesis",
    "regime_hypothesis",
    "DiscoveryDecision",
    "DiscoveryReview",
    "review_discovery_candidate",
]
