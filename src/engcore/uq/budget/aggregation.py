from __future__ import annotations

from dataclasses import dataclass
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
    components=tuple(components)
    correlations=tuple(correlations)
    matrix=require_positive_semidefinite_correlation(components,correlations)
    vector=np.asarray([c.standard_uncertainty for c in components],dtype=float)
    variance=float(vector @ matrix @ vector) if len(vector) else 0.0
    if variance < -1e-12:
        raise ValueError("correlation matrix implies negative aggregate variance")
    variance=max(0.0,variance)
    return AggregatedUncertainty(math.sqrt(variance),variance)
