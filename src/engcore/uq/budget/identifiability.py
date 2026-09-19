from __future__ import annotations

from enum import Enum


class IdentifiabilityStatus(str,Enum):
    IDENTIFIABLE="identifiable"
    WEAK="weak"
    UNIDENTIFIABLE="unidentifiable"
    UNKNOWN="unknown"


def assess_identifiability(condition_number:float|None, *, weak_threshold:float=1e6)->IdentifiabilityStatus:
    if condition_number is None:
        return IdentifiabilityStatus.UNKNOWN
    value=float(condition_number)
    if value<=0:
        return IdentifiabilityStatus.UNIDENTIFIABLE
    if value>=weak_threshold*100:
        return IdentifiabilityStatus.UNIDENTIFIABLE
    if value>=weak_threshold:
        return IdentifiabilityStatus.WEAK
    return IdentifiabilityStatus.IDENTIFIABLE
