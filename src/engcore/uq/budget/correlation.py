from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Correlation:
    left_id:str
    right_id:str
    coefficient:float

    def __post_init__(self)->None:
        left,right=str(self.left_id).strip(),str(self.right_id).strip()
        rho=float(self.coefficient)
        if not left or not right or left==right:
            raise ValueError("correlation requires two distinct component ids")
        if not math.isfinite(rho) or rho < -1 or rho > 1:
            raise ValueError("correlation coefficient must be finite in [-1,1]")
        object.__setattr__(self,"left_id",left)
        object.__setattr__(self,"right_id",right)
        object.__setattr__(self,"coefficient",rho)

    @property
    def key(self)->tuple[str,str]:
        return tuple(sorted((self.left_id,self.right_id)))
