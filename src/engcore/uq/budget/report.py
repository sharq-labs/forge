from __future__ import annotations

from dataclasses import dataclass

from .aggregation import AggregatedUncertainty, aggregate_uncertainty
from .component import UncertaintyComponent
from .correlation import Correlation


@dataclass(frozen=True)
class UncertaintyBudgetReport:
    components:tuple[UncertaintyComponent,...]
    correlations:tuple[Correlation,...]
    aggregate:AggregatedUncertainty

    @classmethod
    def build(cls,components:tuple[UncertaintyComponent,...],correlations:tuple[Correlation,...]=())->"UncertaintyBudgetReport":
        return cls(tuple(components),tuple(correlations),aggregate_uncertainty(tuple(components),tuple(correlations)))
