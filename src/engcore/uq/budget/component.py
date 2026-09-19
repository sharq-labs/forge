from __future__ import annotations

from dataclasses import dataclass
import math

from .source import UncertaintySource


@dataclass(frozen=True)
class UncertaintyComponent:
    component_id:str
    source:UncertaintySource
    standard_uncertainty:float

    def __post_init__(self)->None:
        cid=str(self.component_id).strip()
        u=float(self.standard_uncertainty)
        if not cid or not math.isfinite(u) or u<0:
            raise ValueError("uncertainty component requires id and finite non-negative uncertainty")
        object.__setattr__(self,"component_id",cid)
        object.__setattr__(self,"source",UncertaintySource(self.source))
        object.__setattr__(self,"standard_uncertainty",u)
