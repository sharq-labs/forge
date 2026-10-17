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

    def __post_init__(self)->None:
        # Direct construction must not bypass build(): an empty budget is UNKNOWN, not zero, and a
        # declared aggregate that its own components do not reproduce is refused.
        components=tuple(self.components)
        correlations=tuple(self.correlations)
        if not all(isinstance(c,UncertaintyComponent) for c in components):
            raise TypeError("uncertainty budget components must be UncertaintyComponent records")
        if not all(isinstance(c,Correlation) for c in correlations):
            raise TypeError("uncertainty budget correlations must be Correlation records")
        expected=aggregate_uncertainty(components,correlations)
        if not isinstance(self.aggregate,AggregatedUncertainty) or self.aggregate!=expected:
            raise ValueError("uncertainty budget aggregate does not match its declared components and correlations")
        object.__setattr__(self,"components",components)
        object.__setattr__(self,"correlations",correlations)

    @classmethod
    def build(cls,components:tuple[UncertaintyComponent,...],correlations:tuple[Correlation,...]=())->"UncertaintyBudgetReport":
        return cls(tuple(components),tuple(correlations),aggregate_uncertainty(tuple(components),tuple(correlations)))
