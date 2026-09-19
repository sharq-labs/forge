from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime,timezone
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from .source import KnowledgeSource,KnowledgeSourceClass


class KnowledgeFreshness(str,Enum):
    CURRENT="current"
    STALE="stale"
    UNKNOWN="unknown"
    NOT_APPLICABLE="not_applicable"


@dataclass(frozen=True)
class FreshnessPolicy:
    max_age_days:Mapping[KnowledgeSourceClass,int|None]
    require_timestamp:bool=True

    def __post_init__(self)->None:
        normalized={}
        for key,value in dict(self.max_age_days).items():
            cls=KnowledgeSourceClass(key)
            if value is not None and int(value)<0: raise ValueError("freshness max age must be non-negative or None")
            normalized[cls]=None if value is None else int(value)
        object.__setattr__(self,"max_age_days",MappingProxyType(normalized))

    def assess(self,source:KnowledgeSource,*,now:datetime)->KnowledgeFreshness:
        limit=self.max_age_days.get(source.source_class)
        if limit is None:
            return KnowledgeFreshness.NOT_APPLICABLE
        if not source.published_at:
            return KnowledgeFreshness.UNKNOWN
        try: stamp=datetime.fromisoformat(source.published_at.replace("Z","+00:00"))
        except ValueError: return KnowledgeFreshness.UNKNOWN
        if stamp.tzinfo is None: return KnowledgeFreshness.UNKNOWN
        age=(now.astimezone(timezone.utc)-stamp.astimezone(timezone.utc)).total_seconds()/86400
        return KnowledgeFreshness.CURRENT if age<=limit else KnowledgeFreshness.STALE
