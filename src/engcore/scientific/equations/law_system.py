"""Extended law contract binding equations to checkable assumptions and conditions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ..errors import InvalidScientificProblem
from ..units.quantity import Quantity
from .assumptions import AssumptionAssessment, AssumptionSet, CheckableAssumption
from .conditions import EquationCondition, evaluate_condition
from .evaluation import EquationEvaluation
from .law import LawDefinition


@dataclass(frozen=True)
class ScientificLawSystem:
    law: LawDefinition
    checkable_assumptions: tuple[CheckableAssumption,...]=()
    conditions: tuple[EquationCondition,...]=()

    def __post_init__(self) -> None:
        if not isinstance(self.law,LawDefinition):
            raise InvalidScientificProblem("ScientificLawSystem requires LawDefinition")
        object.__setattr__(self,"checkable_assumptions",tuple(self.checkable_assumptions))
        object.__setattr__(self,"conditions",tuple(self.conditions))
        assumptions=AssumptionSet(self.checkable_assumptions)
        assumptions.require_dimensions(self.law.symbol_units)
        aids=[x.assumption_id for x in self.checkable_assumptions]
        if len(aids)!=len(set(aids)):
            raise InvalidScientificProblem("law system contains duplicate assumption ids")
        cids=[x.condition_id for x in self.conditions]
        if len(cids)!=len(set(cids)):
            raise InvalidScientificProblem("law system contains duplicate condition ids")
        for condition in self.conditions:
            condition.require_contract(self.law.symbol_units)

    def assess_assumptions(self,bindings:Mapping[str,Quantity],*,
                           derivative_bindings:Mapping[str,Quantity]|None=None)->tuple[AssumptionAssessment,...]:
        return AssumptionSet(self.checkable_assumptions).assess(
            bindings,derivative_bindings=derivative_bindings
        )

    def evaluate_conditions(self,bindings:Mapping[str,Quantity],*,
                            derivative_bindings:Mapping[str,Quantity]|None=None)->tuple[EquationEvaluation,...]:
        return tuple(
            evaluate_condition(c,bindings,derivative_bindings=derivative_bindings)
            for c in self.conditions
        )
