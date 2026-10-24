"""Candidate dispositions, scoped scientific claim states and named refusal conditions.

battery_rediscovery_v1 (gap map, REPRESENTATION_MISSING) asked five questions of a declared model family, and the
Minimal Mind could state an answer to none of three of them: adequacy, discrepancy and the identifiability of latent
parameters.  This module adds exactly the claim states those questions need, and no general claim language:

* five candidate dispositions (the v1 vocabulary): SUPPORTED, NOT_SUPPORTED, REVIEW, REFUSED, NOT_ASSESSABLE;
* ten scoped claim states, a positive and a negative per question (:data:`CLAIM_TYPES`);
* six refusal conditions (:class:`RefusalReason`); a non-committal disposition must name one.

A disposition is a PROPOSAL for the caller's authority, never a verdict.  Its invariants are checked on construction:
SUPPORTED carries the question's positive state and NOT_SUPPORTED its negative one, both with bound evidence; a
non-committal disposition carries no claim state and a named refusal with the condition that triggered it.

MODEL_DISCREPANCY's positive state is UNRESOLVED, not ABSENT: residuals compatible with the declared noise at the test's
resolution say nothing about discrepancy below that resolution, so a missing discrepancy is never reported as zero.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

CLAIM_SCHEMA = "forge.mind.repsem.scoped_claim/1"


class ScopedClaimRefused(ValueError):
    """A claim whose disposition, state, evidence or refusal contradict each other."""


class Disposition(str, Enum):
    SUPPORTED = "SUPPORTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    REVIEW = "REVIEW"
    REFUSED = "REFUSED"
    NOT_ASSESSABLE = "NOT_ASSESSABLE"


DECISIVE = (Disposition.SUPPORTED, Disposition.NOT_SUPPORTED)
NON_COMMITTAL = (Disposition.REVIEW, Disposition.REFUSED, Disposition.NOT_ASSESSABLE)


class RefusalReason(str, Enum):
    OUT_OF_DOMAIN = "OUT_OF_DOMAIN"
    NOT_IDENTIFIABLE = "NOT_IDENTIFIABLE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    REPRESENTATION_UNAVAILABLE = "REPRESENTATION_UNAVAILABLE"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    NO_DISCRIMINATING_EVIDENCE = "NO_DISCRIMINATING_EVIDENCE"


class ClaimState(str, Enum):
    IDENTIFIABLE = "IDENTIFIABLE"
    NOT_IDENTIFIABLE = "NOT_IDENTIFIABLE"
    MODEL_ADEQUATE = "MODEL_ADEQUATE"
    MODEL_INADEQUATE = "MODEL_INADEQUATE"
    MODEL_DISCREPANCY_UNRESOLVED = "MODEL_DISCREPANCY_UNRESOLVED"
    MODEL_DISCREPANCY_PRESENT = "MODEL_DISCREPANCY_PRESENT"
    WITHIN_CELL_SUPPORTED = "WITHIN_CELL_SUPPORTED"
    WITHIN_CELL_NOT_SUPPORTED = "WITHIN_CELL_NOT_SUPPORTED"
    CROSS_CELL_SUPPORTED = "CROSS_CELL_SUPPORTED"
    CROSS_CELL_NOT_SUPPORTED = "CROSS_CELL_NOT_SUPPORTED"


@dataclass(frozen=True)
class ClaimType:
    axis: str
    positive: ClaimState
    negative: ClaimState
    meaning: str
    required_evidence: str
    refusal_condition: str
    applicability_scope: str

    def to_dict(self) -> dict[str, Any]:
        return {"axis": self.axis, "positive": self.positive.value, "negative": self.negative.value,
                "meaning": self.meaning, "required_evidence": self.required_evidence,
                "refusal_condition": self.refusal_condition, "applicability_scope": self.applicability_scope}


CLAIM_TYPES: dict[str, ClaimType] = {c.axis: c for c in (
    ClaimType(
        "IDENTIFIABILITY", ClaimState.IDENTIFIABLE, ClaimState.NOT_IDENTIFIABLE,
        meaning="every requested LATENT_PARAMETER of the declared family is determined by the calibration observations "
                "(IDENTIFIABLE), or at least one is not (NOT_IDENTIFIABLE)",
        required_evidence="the residual Jacobian of the bound family at the calibrated estimate; IDENTIFIABLE also needs "
                          "a declared measurement noise, from which the local covariance is classified by the frozen V1 "
                          "identifiability rule (engcore.hybrid_uq.identifiability); a rank-deficient Jacobian decides "
                          "NOT_IDENTIFIABLE without one",
        refusal_condition="REPRESENTATION_UNAVAILABLE: the family cannot be bound to declared roles or a requested "
                          "parameter is not a declared LATENT_PARAMETER; INSUFFICIENT_EVIDENCE: full rank but no declared "
                          "noise, or a weakly identified ridge (REVIEW)",
        applicability_scope="the declared family, the calibration set's design, and the declared parameter bounds"),
    ClaimType(
        "MODEL_ADEQUACY", ClaimState.MODEL_ADEQUATE, ClaimState.MODEL_INADEQUATE,
        meaning="the calibrated declared family describes the calibration data within the declared adequacy bar "
                "(or, with no bar, within the declared measurement noise)",
        required_evidence="calibration residuals of the best fit, compared with a declared bar (rmse and p95) or with a "
                          "declared noise (chi-square at 0.999)",
        refusal_condition="REPRESENTATION_UNAVAILABLE: the family cannot be bound; INSUFFICIENT_EVIDENCE: neither a bar "
                          "nor a noise is declared, or the fit fails",
        applicability_scope="the declared family on the calibration set"),
    ClaimType(
        "MODEL_DISCREPANCY", ClaimState.MODEL_DISCREPANCY_UNRESOLVED, ClaimState.MODEL_DISCREPANCY_PRESENT,
        meaning="the calibrated family's residuals show structured model-form error beyond the declared measurement noise "
                "(PRESENT), or no discrepancy is resolved above it (UNRESOLVED; never 'zero')",
        required_evidence="residual chi-square against a declared noise and/or lag-1 residual autocorrelation against a "
                          "declared independence of the measurement noise",
        refusal_condition="REPRESENTATION_UNAVAILABLE: the family cannot be bound; INSUFFICIENT_EVIDENCE: no declared "
                          "noise and no structure resolved (compatibility cannot be shown without a declared noise)",
        applicability_scope="the declared family on the calibration set, at the stated resolution"),
    ClaimType(
        "WITHIN_CELL_GENERALIZATION", ClaimState.WITHIN_CELL_SUPPORTED, ClaimState.WITHIN_CELL_NOT_SUPPORTED,
        meaning="the calibrated family predicts held-out data of the SAME unit(s) within the declared acceptance bar",
        required_evidence="held-out prediction error of the calibrated family against the declared bar, after every "
                          "held-out trajectory is shown inside the declared applicability domain",
        refusal_condition="INSUFFICIENT_EVIDENCE: no such set or no bar; OUT_OF_DOMAIN: a held-out trajectory leaves the "
                          "declared domain or belongs to another unit; REPRESENTATION_UNAVAILABLE: the family cannot be bound",
        applicability_scope="calibration units only, inside the declared applicability domain"),
    ClaimType(
        "CROSS_CELL_TRANSFER", ClaimState.CROSS_CELL_SUPPORTED, ClaimState.CROSS_CELL_NOT_SUPPORTED,
        meaning="the family calibrated on some units predicts held-out data of OTHER units within the declared bar",
        required_evidence="as within-cell, for a held-out set whose units are disjoint from the calibration units",
        refusal_condition="as within-cell; OUT_OF_DOMAIN also when a held-out unit was a calibration unit",
        applicability_scope="units disjoint from calibration, inside the declared applicability domain"),
)}


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class Refusal:
    """A named refusal condition and the numbers that show it holds."""

    reason: RefusalReason
    condition: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "reason", RefusalReason(self.reason))
        except ValueError:
            raise ScopedClaimRefused(f"refusal reason {self.reason!r} is not a named condition") from None
        object.__setattr__(self, "condition", json.loads(json.dumps(dict(self.condition), sort_keys=True, allow_nan=False)))

    def to_dict(self) -> dict[str, Any]:
        return {"reason": self.reason.value, "condition": self.condition}


@dataclass(frozen=True)
class ScopedClaim:
    axis: str
    disposition: Disposition
    state: ClaimState | None = None
    refusal: Refusal | None = None
    scope: Mapping[str, Any] = field(default_factory=dict)
    evidence: tuple[str, ...] = ()
    reason: str = ""

    def __post_init__(self) -> None:
        if self.axis not in CLAIM_TYPES:
            raise ScopedClaimRefused(f"no claim type for axis {self.axis!r}; the representation is closed")
        ctype = CLAIM_TYPES[self.axis]
        try:
            object.__setattr__(self, "disposition", Disposition(self.disposition))
            object.__setattr__(self, "state", None if self.state is None else ClaimState(self.state))
        except ValueError as exc:
            raise ScopedClaimRefused(str(exc)) from None
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "scope", json.loads(json.dumps(dict(self.scope), sort_keys=True, allow_nan=False)))
        if not str(self.reason).strip():
            raise ScopedClaimRefused("a claim states its reason")
        d = self.disposition
        if d in DECISIVE:
            want = ctype.positive if d is Disposition.SUPPORTED else ctype.negative
            if self.state is not want:
                raise ScopedClaimRefused(f"{self.axis}: {d.value} carries {want.value}, not "
                                         f"{None if self.state is None else self.state.value}")
            if not self.evidence:
                raise ScopedClaimRefused(f"{self.axis}: {d.value} without bound evidence")
            if self.refusal is not None:
                raise ScopedClaimRefused(f"{self.axis}: a decisive claim carries no refusal")
        else:
            if self.state is not None:
                raise ScopedClaimRefused(f"{self.axis}: {d.value} asserts no claim state")
            if not isinstance(self.refusal, Refusal):
                raise ScopedClaimRefused(f"{self.axis}: {d.value} is allowed only under a named refusal condition")

    @property
    def claim_type(self) -> ClaimType:
        return CLAIM_TYPES[self.axis]

    def to_dict(self) -> dict[str, Any]:
        return {"schema": CLAIM_SCHEMA, "axis": self.axis, "disposition": self.disposition.value,
                "state": None if self.state is None else self.state.value,
                "refusal": None if self.refusal is None else self.refusal.to_dict(),
                "scope": dict(self.scope), "evidence": list(self.evidence), "reason": self.reason}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "ScopedClaim":
        if d.get("schema") != CLAIM_SCHEMA:
            raise ScopedClaimRefused(f"not a scoped claim: {d.get('schema')!r}")
        extra = set(d) - {"schema", "axis", "disposition", "state", "refusal", "scope", "evidence", "reason"}
        if extra:
            raise ScopedClaimRefused(f"unknown scoped claim keys {sorted(extra)}")
        r = d.get("refusal")
        return cls(d["axis"], d["disposition"], d.get("state"),
                   None if r is None else Refusal(r["reason"], r.get("condition", {})),
                   d.get("scope", {}), tuple(d.get("evidence", ())), d.get("reason", ""))

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


def decided(axis: str, positive: bool, *, evidence: tuple[str, ...], scope: Mapping[str, Any], reason: str) -> ScopedClaim:
    ctype = CLAIM_TYPES[axis]
    return ScopedClaim(axis, Disposition.SUPPORTED if positive else Disposition.NOT_SUPPORTED,
                       state=ctype.positive if positive else ctype.negative, scope=scope, evidence=evidence, reason=reason)


def refused(axis: str, disposition: Disposition, reason: RefusalReason, condition: Mapping[str, Any], *,
            scope: Mapping[str, Any] | None = None, why: str) -> ScopedClaim:
    if disposition in DECISIVE:
        raise ScopedClaimRefused("a refusal is non-committal")
    return ScopedClaim(axis, disposition, refusal=Refusal(reason, condition), scope=scope or {}, reason=why)


__all__ = ["CLAIM_SCHEMA", "CLAIM_TYPES", "ClaimState", "ClaimType", "DECISIVE", "Disposition", "NON_COMMITTAL", "Refusal",
           "RefusalReason", "ScopedClaim", "ScopedClaimRefused", "decided", "refused"]
