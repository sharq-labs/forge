from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

class RefinementStrategy(str,Enum):
    TIME_STEP="time_step"
    MESH="mesh"
    TOLERANCE="tolerance"
    PRECISION="precision"

@dataclass(frozen=True)
class RefinementRequest:
    strategy:RefinementStrategy
    level:int
    factor:float

    def __post_init__(self)->None:
        object.__setattr__(self,"strategy",RefinementStrategy(self.strategy))
        if self.level<1 or float(self.factor)<=0 or float(self.factor)>=1:
            raise ValueError("refinement requires level>=1 and 0<factor<1")
