from __future__ import annotations

from dataclasses import dataclass
import math

from .component import UncertaintyComponent
from .correlation import Correlation


@dataclass(frozen=True)
class AggregatedUncertainty:
    standard_uncertainty:float
    variance:float


def aggregate_uncertainty(components:tuple[UncertaintyComponent,...],correlations:tuple[Correlation,...]=())->AggregatedUncertainty:
    ids=[c.component_id for c in components]
    if len(ids)!=len(set(ids)):
        raise ValueError("duplicate uncertainty component id")
    by_id={c.component_id:c for c in components}
    rho={}
    for item in correlations:
        if item.left_id not in by_id or item.right_id not in by_id:
            raise ValueError("correlation references unknown uncertainty component")
        if item.key in rho:
            raise ValueError("duplicate correlation pair")
        rho[item.key]=item.coefficient
    variance=sum(c.standard_uncertainty**2 for c in components)
    for (left,right),coefficient in rho.items():
        variance += 2*coefficient*by_id[left].standard_uncertainty*by_id[right].standard_uncertainty
    if variance < -1e-15:
        raise ValueError("correlation matrix implies negative aggregate variance")
    variance=max(0.0,variance)
    return AggregatedUncertainty(math.sqrt(variance),variance)
