from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CoverageAssessment:
    empirical_coverage:float
    target_coverage:float
    adequate:bool


def assess_coverage(hits:int,total:int,target:float)->CoverageAssessment:
    if total<=0 or hits<0 or hits>total:
        raise ValueError("coverage counts are invalid")
    target=float(target)
    if target<=0 or target>1:
        raise ValueError("target coverage must be in (0,1]")
    empirical=hits/total
    return CoverageAssessment(empirical,target,empirical>=target)
