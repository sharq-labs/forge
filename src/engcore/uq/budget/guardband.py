from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DecisionBand:
    lower:float
    upper:float


def guard_band(value:float,uncertainty:float,coverage_factor:float=2.0)->DecisionBand:
    value,uncertainty,k=float(value),float(uncertainty),float(coverage_factor)
    if uncertainty<0 or k<=0:
        raise ValueError("uncertainty must be >=0 and coverage_factor >0")
    width=k*uncertainty
    return DecisionBand(value-width,value+width)
