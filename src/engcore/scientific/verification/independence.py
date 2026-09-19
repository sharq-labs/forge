from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class IndependenceLevel(str,Enum):
    NONE="none"
    PARTIAL="partial"
    STRONG="strong"
    EXTERNAL="external"


@dataclass(frozen=True)
class IndependenceEvidence:
    primary_route_id:str
    verification_route_id:str
    level:IndependenceLevel
    shared_components:tuple[str,...]=()
    rationale:str=""

    def __post_init__(self)->None:
        primary=str(self.primary_route_id).strip()
        verification=str(self.verification_route_id).strip()
        if not primary or not verification or primary==verification:
            raise ValueError("independence evidence requires two distinct route ids")
        object.__setattr__(self,"primary_route_id",primary)
        object.__setattr__(self,"verification_route_id",verification)
        object.__setattr__(self,"level",IndependenceLevel(self.level))
        components=tuple(sorted(set(str(x).strip() for x in self.shared_components)))
        if any(not x for x in components):
            raise ValueError("shared component identities must be non-empty")
        object.__setattr__(self,"shared_components",components)
        if self.level in {IndependenceLevel.STRONG,IndependenceLevel.EXTERNAL} and components:
            raise ValueError("strong/external independence cannot claim shared implementation components")

    @property
    def pair(self)->tuple[str,str]:
        return (self.primary_route_id,self.verification_route_id)
