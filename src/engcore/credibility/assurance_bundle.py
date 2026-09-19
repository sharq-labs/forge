"""Composite provenance binding across validation, evidence, UQ, verification,
replay and certification.

This module is deliberately above the Scientific Core. Scientific primitives do
not import credibility; credibility may compose their already-derived records.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib, json, re
from typing import Any, Mapping

from ..scientific.certification_core import CertificationRecord, certification_record_fingerprint
from ..scientific.replay_core import ReplayBundle, replay_bundle_fingerprint
from ..scientific.validation_core import ValidationReport, validation_report_fingerprint
from ..scientific.verification import VerificationReport, verification_report_fingerprint
from ..scientific.serialization import require_schema, schema_string
from ..uq.model_form import ModelFormEstimate, model_form_estimate_fingerprint
from .evidence_graph import EvidenceGraph, evidence_graph_fingerprint

ASSURANCE_BUNDLE_SCHEMA=schema_string("scientific_assurance_bundle")
_SHA256=re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class AssuranceBundle:
    validation_digest:str
    evidence_digest:str
    model_form_digest:str
    verification_digest:str
    replay_digest:str
    certification_digest:str

    def __post_init__(self)->None:
        for name in (
            "validation_digest","evidence_digest","model_form_digest",
            "verification_digest","replay_digest","certification_digest",
        ):
            value=str(getattr(self,name)).strip().lower()
            if not _SHA256.fullmatch(value):
                raise ValueError(f"{name} must be lowercase SHA-256")
            object.__setattr__(self,name,value)

    @classmethod
    def from_records(
        cls,
        *,
        validation:ValidationReport,
        evidence:EvidenceGraph,
        model_form:ModelFormEstimate,
        verification:VerificationReport,
        replay:ReplayBundle,
        certification:CertificationRecord,
    )->"AssuranceBundle":
        return cls(
            validation_report_fingerprint(validation),
            evidence_graph_fingerprint(evidence),
            model_form_estimate_fingerprint(model_form),
            verification_report_fingerprint(verification),
            replay_bundle_fingerprint(replay),
            certification_record_fingerprint(certification),
        )

    def to_dict(self)->dict[str,Any]:
        return {"schema":ASSURANCE_BUNDLE_SCHEMA,
                **{name:getattr(self,name) for name in (
                    "validation_digest","evidence_digest","model_form_digest",
                    "verification_digest","replay_digest","certification_digest")}}

    @classmethod
    def from_dict(cls,payload:Mapping[str,Any])->"AssuranceBundle":
        require_schema(payload,ASSURANCE_BUNDLE_SCHEMA)
        return cls(*(payload[name] for name in (
            "validation_digest","evidence_digest","model_form_digest",
            "verification_digest","replay_digest","certification_digest")))

    @property
    def digest(self)->str:
        return hashlib.sha256(json.dumps(self.to_dict(),sort_keys=True,separators=(",",":")).encode()).hexdigest()
