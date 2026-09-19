from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.units.quantity import Quantity
from engcore.uq.budget import Correlation
from .contribution import UncertaintyContribution
from .policy import CombinationPolicy


@dataclass(frozen=True)
class CombinationReport:
    nominal:Quantity
    contributions:tuple[UncertaintyContribution,...]
    policy:CombinationPolicy
    correlations:tuple[Correlation,...]
    output:Uncertainty
    assumptions:tuple[str,...]

    def __post_init__(self)->None:
        if not isinstance(self.nominal,Quantity) or not isinstance(self.output,Uncertainty):
            raise InvalidScientificProblem("combination report requires nominal Quantity and output Uncertainty")
        object.__setattr__(self,"contributions",tuple(self.contributions))
        object.__setattr__(self,"correlations",tuple(self.correlations))
        object.__setattr__(self,"assumptions",tuple(self.assumptions))
