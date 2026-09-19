from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class VerificationRouteKind(str,Enum):
    SAME_SOLVER_RERUN="same_solver_rerun"
    DIFFERENT_ALGORITHM="different_algorithm"
    DIFFERENT_IMPLEMENTATION="different_implementation"
    DIFFERENT_MODEL="different_model"
    ANALYTICAL_REFERENCE="analytical_reference"
    EXTERNAL_SOLVER="external_solver"
    EXPERIMENTAL_MEASUREMENT="experimental_measurement"
    INDEPENDENT_REPRODUCTION="independent_reproduction"


@dataclass(frozen=True)
class VerificationRoute:
    route_id:str
    kind:VerificationRouteKind
    implementation_digest:str

    def __post_init__(self)->None:
        rid=str(self.route_id).strip()
        if not rid:
            raise ValueError("verification route requires route_id")
        object.__setattr__(self,"route_id",rid)
        object.__setattr__(self,"kind",VerificationRouteKind(self.kind))
        if len(str(self.implementation_digest))!=64:
            raise ValueError("implementation_digest must be SHA-256 length")
