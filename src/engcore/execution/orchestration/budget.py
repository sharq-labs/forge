from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class ExecutionBudget:
    max_attempts:int=1
    max_refinements:int=0
    max_wall_seconds:float|None=None

    def __post_init__(self)->None:
        if self.max_attempts<1 or self.max_refinements<0:
            raise ValueError("execution budget requires max_attempts>=1 and max_refinements>=0")
        if self.max_wall_seconds is not None and float(self.max_wall_seconds)<=0:
            raise ValueError("max_wall_seconds must be positive when supplied")
