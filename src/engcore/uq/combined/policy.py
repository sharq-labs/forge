from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from engcore.scientific.results.uncertainty import UncertaintySource


class CombinationMode(str,Enum):
    STANDARD_RSS="standard_rss"
    CONSERVATIVE_INTERVAL="conservative_interval"
    HYBRID_INTERVAL="hybrid_interval"


class MissingCorrelationPolicy(str,Enum):
    REFUSE="refuse"
    ASSUME_ZERO="assume_zero"


@dataclass(frozen=True)
class CombinationPolicy:
    mode:CombinationMode
    missing_correlation:MissingCorrelationPolicy=MissingCorrelationPolicy.REFUSE
    standard_coverage_factor:float|None=None
    required_sources:tuple[UncertaintySource,...]=()

    def __post_init__(self)->None:
        object.__setattr__(self,"mode",CombinationMode(self.mode))
        object.__setattr__(self,"missing_correlation",MissingCorrelationPolicy(self.missing_correlation))
        sources=tuple(UncertaintySource(x) for x in self.required_sources)
        if len(sources)!=len(set(sources)): raise ValueError("required_sources contains duplicates")
        if any(s in {UncertaintySource.UNSPECIFIED,UncertaintySource.COMBINED} for s in sources):
            raise ValueError("required_sources must name primitive uncertainty channels")
        object.__setattr__(self,"required_sources",sources)
        if self.standard_coverage_factor is not None:
            k=float(self.standard_coverage_factor)
            if k<=0: raise ValueError("standard_coverage_factor must be positive")
            object.__setattr__(self,"standard_coverage_factor",k)
        if self.mode is CombinationMode.HYBRID_INTERVAL and self.standard_coverage_factor is None:
            raise ValueError("HYBRID_INTERVAL requires an explicit standard_coverage_factor")
