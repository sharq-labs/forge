from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
import math
import numpy as np

from .component import UncertaintyComponent
from .correlation import Correlation
from .matrix import require_positive_semidefinite_correlation


@dataclass(frozen=True)
class AggregatedUncertainty:
    standard_uncertainty:float
    variance:float


def aggregate_uncertainty(components:tuple[UncertaintyComponent,...],correlations:tuple[Correlation,...]=())->AggregatedUncertainty:
    """Correlation-aware root-sum-square of DECLARED components under DECLARED correlations.

    Hostile review (empty-UQ authority): an empty budget is UNKNOWN, not zero -- it is refused, never
    aggregated to 0.0. And independence is a claim: every pair of components needs a declared
    Correlation (coefficient 0.0 states independence); an undeclared pair is refused rather than
    silently read as independent, which would understate the total whenever the sources are correlated.
    """
    components=tuple(components)
    correlations=tuple(correlations)
    if not components:
        raise ValueError("no uncertainty component is declared: an empty budget is UNKNOWN, not zero")
    declared={c.key for c in correlations}
    missing=sorted(
        pair for pair in (tuple(sorted((a.component_id,b.component_id))) for a,b in combinations(components,2))
        if pair not in declared
    )
    if missing:
        raise ValueError(
            f"correlation is undeclared for component pairs {missing}: independence is a claim, declare it "
            "(coefficient 0.0) or declare the correlation"
        )
    matrix=require_positive_semidefinite_correlation(components,correlations)
    vector=np.asarray([c.standard_uncertainty for c in components],dtype=float)
    variance=float(vector @ matrix @ vector)
    if variance < -1e-12:
        raise ValueError("correlation matrix implies negative aggregate variance")
    variance=max(0.0,variance)
    return AggregatedUncertainty(math.sqrt(variance),variance)