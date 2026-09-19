from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RouteComparison:
    primary_route_id:str
    verification_route_id:str
    agreement:bool
    normalized_error:float|None=None

    def __post_init__(self)->None:
        if self.primary_route_id==self.verification_route_id:
            raise ValueError("verification comparison requires distinct route ids")
        if self.normalized_error is not None and float(self.normalized_error)<0:
            raise ValueError("normalized_error must be non-negative")
