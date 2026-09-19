from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ModelResidualObservation:
    observation_id:str
    independence_group:str
    residual:float
    known_standard_uncertainty:float
    held_out:bool

    def __post_init__(self)->None:
        oid=str(self.observation_id).strip()
        group=str(self.independence_group).strip()
        residual=float(self.residual)
        known=float(self.known_standard_uncertainty)
        if not oid or not group:
            raise ValueError("model residual observation requires id and independence group")
        if not math.isfinite(residual) or not math.isfinite(known) or known<0:
            raise ValueError("model residual observation requires finite residual and non-negative uncertainty")
        if not isinstance(self.held_out,bool):
            raise ValueError("held_out must be bool")
        object.__setattr__(self,"observation_id",oid)
        object.__setattr__(self,"independence_group",group)
        object.__setattr__(self,"residual",residual)
        object.__setattr__(self,"known_standard_uncertainty",known)
