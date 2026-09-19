from __future__ import annotations

from dataclasses import dataclass
import math

from engcore.scientific.units.validation import require_unit


@dataclass(frozen=True)
class ModelResidualObservation:
    observation_id:str
    independence_group:str
    quantity:str
    units:str
    residual:float
    known_uncertainty_half_width:float
    held_out:bool

    def __post_init__(self)->None:
        oid=str(self.observation_id).strip()
        group=str(self.independence_group).strip()
        quantity=str(self.quantity).strip()
        units=require_unit(self.units,context="model-form residual units")
        residual=float(self.residual)
        known=float(self.known_uncertainty_half_width)
        if not oid or not group or not quantity:
            raise ValueError("model residual observation requires id, independence group and quantity")
        if not math.isfinite(residual) or not math.isfinite(known) or known<0:
            raise ValueError("model residual observation requires finite residual and non-negative known uncertainty half-width")
        if not isinstance(self.held_out,bool):
            raise ValueError("held_out must be bool")
        object.__setattr__(self,"observation_id",oid)
        object.__setattr__(self,"independence_group",group)
        object.__setattr__(self,"quantity",quantity)
        object.__setattr__(self,"units",units)
        object.__setattr__(self,"residual",residual)
        object.__setattr__(self,"known_uncertainty_half_width",known)
