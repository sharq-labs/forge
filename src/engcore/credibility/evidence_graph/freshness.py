from __future__ import annotations

from enum import Enum
from datetime import datetime, timezone


class FreshnessStatus(str,Enum):
    CURRENT="current"
    STALE="stale"
    UNKNOWN="unknown"


def assess_freshness(observed_at:str, *, now:datetime, max_age_seconds:int)->FreshnessStatus:
    if not observed_at:
        return FreshnessStatus.UNKNOWN
    if max_age_seconds<0:
        raise ValueError("max_age_seconds must be non-negative")
    try:
        stamp=datetime.fromisoformat(observed_at.replace("Z","+00:00"))
    except ValueError:
        return FreshnessStatus.UNKNOWN
    if stamp.tzinfo is None:
        return FreshnessStatus.UNKNOWN
    age=(now.astimezone(timezone.utc)-stamp.astimezone(timezone.utc)).total_seconds()
    return FreshnessStatus.CURRENT if age<=max_age_seconds else FreshnessStatus.STALE
