"""A scientific hypothesis that keeps its judgments apart.

The Minimal Mind's hypothesis is one log-linear structure, and its conclusion is one "law" (gap map: the P2
identifiability failure read a parameter question off the shape of a law).  :class:`ScientificHypothesis` separates what
that single field conflated: the model family, its latent parameter set, the applicability domain, the variable roles
it was bound through, the scoped claims made about it, the competing alternatives, the evidence for and against, and
the discriminators that remain unresolved.  There is no ``law`` field, and :meth:`ScientificHypothesis.from_dict`
refuses one.

The identity is the canonical :class:`engcore.sria.decision.Hypothesis` record (:meth:`ScientificHypothesis.canonical`);
this record adds structure around it and grants it no status.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from ...sria.decision import Hypothesis, HypothesisKind, ProposalProvenance, ProposerKind
from .claims import ScopedClaim
from .roles import RoleTable

HYPOTHESIS_SCHEMA = "forge.mind.repsem.hypothesis/1"
_KEYS = ("schema", "hypothesis_id", "model_family", "parameter_set", "applicability_domain", "variable_roles", "claims",
         "competing_alternatives", "evidence_for", "evidence_against", "unresolved_discriminators")


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class ParameterEstimate:
    name: str
    low: float
    high: float
    estimate: float | None
    standard_error: float | None

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "low": self.low, "high": self.high, "estimate": self.estimate,
                "standard_error": self.standard_error}


@dataclass(frozen=True)
class EvidenceItem:
    kind: str
    digest: str
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "digest": self.digest, "summary": self.summary}


@dataclass(frozen=True)
class ScientificHypothesis:
    hypothesis_id: str
    model_family: Mapping[str, Any]
    parameter_set: tuple[ParameterEstimate, ...]
    applicability_domain: Mapping[str, Any]
    variable_roles: RoleTable
    claims: tuple[ScopedClaim, ...]
    competing_alternatives: tuple[Mapping[str, Any], ...]
    evidence_for: tuple[EvidenceItem, ...]
    evidence_against: tuple[EvidenceItem, ...]
    unresolved_discriminators: tuple[str, ...]

    def canonical(self) -> Hypothesis:
        fam = self.model_family
        return Hypothesis(hypothesis_id=self.hypothesis_id, model_ref=fam["family_id"], kind=HypothesisKind.EQUATION,
                          description="declared model family bound through declared variable roles",
                          statement=fam.get("description", ""),
                          structure_digest=_digest({"family": fam, "roles": self.variable_roles.digest}),
                          proposal=ProposalProvenance(ProposerKind.ALGORITHM, "forge.mind.repsem@1"))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": HYPOTHESIS_SCHEMA, "hypothesis_id": self.hypothesis_id, "model_family": dict(self.model_family),
                "parameter_set": [p.to_dict() for p in self.parameter_set],
                "applicability_domain": dict(self.applicability_domain), "variable_roles": self.variable_roles.to_dict(),
                "claims": [c.to_dict() for c in self.claims],
                "competing_alternatives": [dict(a) for a in self.competing_alternatives],
                "evidence_for": [e.to_dict() for e in self.evidence_for],
                "evidence_against": [e.to_dict() for e in self.evidence_against],
                "unresolved_discriminators": list(self.unresolved_discriminators)}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "ScientificHypothesis":
        if d.get("schema") != HYPOTHESIS_SCHEMA:
            raise ValueError(f"not a repsem hypothesis: {d.get('schema')!r}")
        extra = sorted(set(d) - set(_KEYS))
        if extra:
            raise ValueError(f"unknown hypothesis keys {extra}: a hypothesis has no generic 'law' or other catch-all field")
        return cls(d["hypothesis_id"], dict(d["model_family"]),
                   tuple(ParameterEstimate(**p) for p in d["parameter_set"]), dict(d["applicability_domain"]),
                   RoleTable.from_dict(d["variable_roles"]), tuple(ScopedClaim.from_dict(c) for c in d["claims"]),
                   tuple(dict(a) for a in d["competing_alternatives"]),
                   tuple(EvidenceItem(**e) for e in d["evidence_for"]),
                   tuple(EvidenceItem(**e) for e in d["evidence_against"]), tuple(d["unresolved_discriminators"]))

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


__all__ = ["EvidenceItem", "HYPOTHESIS_SCHEMA", "ParameterEstimate", "ScientificHypothesis"]
