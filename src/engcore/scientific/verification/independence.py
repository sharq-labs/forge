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
    level:IndependenceLevel
    shared_components:tuple[str,...]=()
    rationale:str=""

    def __post_init__(self)->None:
        object.__setattr__(self,"level",IndependenceLevel(self.level))
        object.__setattr__(self,"shared_components",tuple(self.shared_components))
        if self.level in {IndependenceLevel.STRONG,IndependenceLevel.EXTERNAL} and self.shared_components:
            raise ValueError("strong/external independence cannot claim shared implementation components")
