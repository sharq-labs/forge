from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime,timezone
from enum import Enum
from types import MappingProxyType
from typing import Mapping, Any
import hashlib, json

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
        if not isinstance(self.require_timestamp, bool):
            raise ValueError("require_timestamp must be bool")
        object.__setattr__(self,"max_age_days",MappingProxyType(normalized))

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_age_days": {
                key.value: value
                for key, value in sorted(
                    self.max_age_days.items(), key=lambda item: item[0].value
                )
            },
            "require_timestamp": self.require_timestamp,
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def assess(self,source:KnowledgeSource,*,now:datetime)->KnowledgeFreshness:
        if now.tzinfo is None:
            raise ValueError("freshness assessment time must be timezone-aware")
        if source.source_class not in self.max_age_days:
            return KnowledgeFreshness.UNKNOWN
        limit=self.max_age_days[source.source_class]
        if limit is None:
            return KnowledgeFreshness.NOT_APPLICABLE
        if not source.published_at:
            return KnowledgeFreshness.UNKNOWN
        try: stamp=datetime.fromisoformat(source.published_at.replace("Z","+00:00"))
        except ValueError: return KnowledgeFreshness.UNKNOWN
        if stamp.tzinfo is None: return KnowledgeFreshness.UNKNOWN
        age=(now.astimezone(timezone.utc)-stamp.astimezone(timezone.utc)).total_seconds()/86400
        if age < 0:
            return KnowledgeFreshness.UNKNOWN
        return KnowledgeFreshness.CURRENT if age<=limit else KnowledgeFreshness.STALE
