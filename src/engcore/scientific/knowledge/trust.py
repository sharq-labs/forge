from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any,Mapping

from ..errors import InvalidScientificProblem
from .source import KnowledgeSource


@dataclass(frozen=True)
class SourcePin:
    source_id:str
    issuer:str
    document_digest:str
    version:str

    def __post_init__(self)->None:
        probe=KnowledgeSource(self.source_id,self.issuer,self.document_digest,self.version,
                              "pinned://identity","other")
        object.__setattr__(self,"source_id",probe.source_id);object.__setattr__(self,"issuer",probe.issuer)
        object.__setattr__(self,"document_digest",probe.document_digest);object.__setattr__(self,"version",probe.version)


class SourceStanding(str,Enum):
    PINNED="pinned"
    UNTRUSTED="untrusted"
    DIGEST_MISMATCH="digest_mismatch"
    VERSION_MISMATCH="version_mismatch"
    ISSUER_MISMATCH="issuer_mismatch"


@dataclass(frozen=True)
class SourceTrustAssessment:
    standing:SourceStanding
    reason:str
    @property
    def trusted(self)->bool: return self.standing is SourceStanding.PINNED


@dataclass(frozen=True)
class TrustedSourceRegistry:
    pins:tuple[SourcePin,...]

    def __post_init__(self)->None:
        pins=tuple(self.pins)
        if any(not isinstance(p,SourcePin) for p in pins): raise InvalidScientificProblem("trusted source registry accepts SourcePin only")
        ids=[p.source_id for p in pins]
        if len(ids)!=len(set(ids)): raise InvalidScientificProblem("trusted source registry contains duplicate source ids")
        object.__setattr__(self,"pins",pins)

    def assess(self,source:KnowledgeSource)->SourceTrustAssessment:
        pin=next((p for p in self.pins if p.source_id==source.source_id),None)
        if pin is None: return SourceTrustAssessment(SourceStanding.UNTRUSTED,"source id is not pinned")
        if pin.issuer!=source.issuer: return SourceTrustAssessment(SourceStanding.ISSUER_MISMATCH,"issuer differs from trust pin")
        if pin.version!=source.version: return SourceTrustAssessment(SourceStanding.VERSION_MISMATCH,"version differs from trust pin")
        if pin.document_digest!=source.document_digest: return SourceTrustAssessment(SourceStanding.DIGEST_MISMATCH,"document digest differs from trust pin")
        return SourceTrustAssessment(SourceStanding.PINNED,"source identity exactly matches trust pin")
