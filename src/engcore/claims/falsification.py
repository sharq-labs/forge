"""Sealed falsifiers and their verdicts: the only path to a verdict-backed hypothesis status.

A :class:`Falsifier` is pre-registered against ONE hypothesis revision (its content digest): the test conditions, the
admissible evidence source, the refutation criterion, the uncertainty it requires and a version.  It is SEALED in a
:class:`FalsifierRegistry` -- a hash-chained ledger that also records when each piece of evidence was EXPOSED.  A verdict
may use only evidence exposed after the falsifier was sealed: a falsifier written after seeing the data is post-hoc.

Post-hoc modification never mutates the original: :meth:`Falsifier.revise` produces a new version that must be sealed
again, and it can be judged only on evidence exposed after ITS seal.

Verdicts: REFUTED, NOT_REFUTED, INCONCLUSIVE.  If the uncertainty the criterion requires is UNKNOWN (``None``), the
verdict is INCONCLUSIVE -- missing uncertainty never becomes zero.

:func:`apply_verdicts` is how a hypothesis gets SURVIVING / REFUTED / UNKNOWN: from every verdict recorded for its exact
content (a refuting verdict cannot be left out), producing typed
:class:`~engcore.sria.decision.VerdictReference` records.  :func:`verify_status` checks a hypothesis's claimed status
against the verdict store.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Iterable, Mapping

from ..sria.decision import Hypothesis, HypothesisStatus, VerdictReference

FALSIFIER_SCHEMA = "engcore.claims.falsifier/1"
VERDICT_SCHEMA = "engcore.claims.falsifier_verdict/1"
GENESIS = "0" * 64


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class FalsificationRefused(ValueError):
    """A falsifier, seal or verdict that would let a hypothesis look better tested than it is."""


class CriterionKind(str, Enum):
    PREDICTION_DEVIATION = "prediction_deviation"   # refuted when |observed - predicted| > k * sqrt(u_obs^2 + u_pred^2)
    FORBIDDEN_REGION = "forbidden_region"           # refuted when the observation lies in [low, high] beyond its uncertainty


class Verdict(str, Enum):
    REFUTED = "refuted"
    NOT_REFUTED = "not_refuted"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class Falsifier:
    falsifier_id: str
    hypothesis_id: str
    hypothesis_content_digest: str
    observable: str
    unit: str
    test_conditions: Mapping[str, Any]
    evidence_source: str                 # the admissible evidence source class, e.g. "escrow:observe" or "sria:measurement"
    criterion: CriterionKind
    parameters: Mapping[str, float]      # PREDICTION_DEVIATION: {"k": 3}; FORBIDDEN_REGION: {"low": .., "high": .., "k": ..}
    version: int = 1
    supersedes: str = ""                 # digest of the falsifier this revision replaces

    def __post_init__(self) -> None:
        for label in ("falsifier_id", "hypothesis_id", "observable", "unit", "evidence_source"):
            if not str(getattr(self, label)).strip():
                raise FalsificationRefused(f"a falsifier names its {label}")
        if len(str(self.hypothesis_content_digest)) != 64:
            raise FalsificationRefused("a falsifier binds the hypothesis CONTENT digest it tests")
        object.__setattr__(self, "criterion", CriterionKind(self.criterion))
        params = {str(k): float(val) for k, val in dict(self.parameters).items()}
        if any(not math.isfinite(val) for val in params.values()):
            raise FalsificationRefused("criterion parameters are finite")
        if params.get("k", 0.0) <= 0:
            raise FalsificationRefused("the criterion's coverage factor k is positive and declared (never defaulted)")
        if self.criterion is CriterionKind.FORBIDDEN_REGION and not ("low" in params and "high" in params and params["low"] < params["high"]):
            raise FalsificationRefused("a forbidden region declares low < high")
        object.__setattr__(self, "parameters", dict(sorted(params.items())))
        object.__setattr__(self, "test_conditions", json.loads(json.dumps(dict(self.test_conditions), sort_keys=True)))
        if isinstance(self.version, bool) or self.version < 1:
            raise FalsificationRefused("falsifier versions start at 1")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": FALSIFIER_SCHEMA, "falsifier_id": self.falsifier_id, "hypothesis_id": self.hypothesis_id,
                "hypothesis_content_digest": self.hypothesis_content_digest, "observable": self.observable, "unit": self.unit,
                "test_conditions": dict(self.test_conditions), "evidence_source": self.evidence_source,
                "criterion": self.criterion.value, "parameters": dict(self.parameters), "version": self.version,
                "supersedes": self.supersedes}

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())

    def revise(self, **changes: Any) -> "Falsifier":
        """A post-hoc change is a NEW falsifier version (sealed separately); the original is never mutated."""
        if "falsifier_id" in changes or "hypothesis_id" in changes:
            raise FalsificationRefused("a revision keeps the falsifier and hypothesis ids")
        return replace(self, version=self.version + 1, supersedes=self.digest, **changes)


@dataclass(frozen=True)
class RegistryEntry:
    sequence: int
    previous: str
    kind: str                     # "sealed" | "exposed"
    subject: str                  # falsifier digest | evidence id
    payload_json: str

    @property
    def digest(self) -> str:
        return _digest({"sequence": self.sequence, "previous": self.previous, "kind": self.kind, "subject": self.subject,
                        "payload": json.loads(self.payload_json)})


class FalsifierRegistry:
    """Hash-chained record of seals and evidence exposures.  Order is the only clock that matters here."""

    def __init__(self) -> None:
        self._entries: list[RegistryEntry] = []
        self._sealed: dict[str, Falsifier] = {}
        self._seal_seq: dict[str, int] = {}
        self._exposed: dict[str, int] = {}

    @property
    def head(self) -> str:
        return self._entries[-1].digest if self._entries else GENESIS

    @property
    def entries(self) -> tuple[RegistryEntry, ...]:
        return tuple(self._entries)

    def _add(self, kind: str, subject: str, payload: Mapping[str, Any]) -> RegistryEntry:
        e = RegistryEntry(len(self._entries), self.head, kind, subject, json.dumps(dict(payload), sort_keys=True))
        self._entries.append(e)
        return e

    def seal(self, falsifier: Falsifier) -> RegistryEntry:
        if not isinstance(falsifier, Falsifier):
            raise FalsificationRefused("only a Falsifier is sealed")
        d = falsifier.digest
        if d in self._sealed:
            raise FalsificationRefused("this falsifier is already sealed")
        if falsifier.supersedes and falsifier.supersedes not in self._sealed:
            raise FalsificationRefused("a revision supersedes a sealed falsifier")
        e = self._add("sealed", d, falsifier.to_dict())
        self._sealed[d] = falsifier
        self._seal_seq[d] = e.sequence
        return e

    def expose(self, evidence_id: str, *, evidence_digest: str) -> RegistryEntry:
        """Record that a piece of evidence became visible to the proposer side.  Re-exposure keeps the FIRST time."""
        if not str(evidence_id).strip() or len(str(evidence_digest)) != 64:
            raise FalsificationRefused("exposure names the evidence and its digest")
        if evidence_id in self._exposed:
            return self._entries[self._exposed[evidence_id]]
        e = self._add("exposed", evidence_id, {"evidence_digest": evidence_digest})
        self._exposed[evidence_id] = e.sequence
        return e

    def sealed(self, falsifier_digest: str) -> Falsifier:
        f = self._sealed.get(falsifier_digest)
        if f is None:
            raise FalsificationRefused("the falsifier is not sealed; an unsealed falsifier decides nothing")
        return f

    def seal_sequence(self, falsifier_digest: str) -> int:
        self.sealed(falsifier_digest)
        return self._seal_seq[falsifier_digest]

    def exposure_sequence(self, evidence_id: str) -> int | None:
        return self._exposed.get(evidence_id)

    def sealed_for(self, hypothesis_id: str, content_digest: str) -> tuple[Falsifier, ...]:
        return tuple(f for f in self._sealed.values() if f.hypothesis_id == hypothesis_id and f.hypothesis_content_digest == content_digest)


@dataclass(frozen=True)
class EvidenceItem:
    """One admissible observation offered to a falsifier.  ``uncertainty`` None = UNKNOWN (never zero)."""

    evidence_id: str
    evidence_digest: str
    source: str
    observable: str
    unit: str
    value: float
    uncertainty: float | None


@dataclass(frozen=True)
class FalsifierVerdict:
    falsifier_digest: str
    falsifier_ref: str
    hypothesis_id: str
    hypothesis_content_digest: str
    evidence_ids: tuple[str, ...]
    verdict: Verdict
    observed: float | None
    predicted: float | None
    combined_uncertainty: float | None
    reason: str
    registry_head: str

    def to_dict(self) -> dict[str, Any]:
        return {"schema": VERDICT_SCHEMA, "falsifier_digest": self.falsifier_digest, "falsifier_ref": self.falsifier_ref,
                "hypothesis_id": self.hypothesis_id, "hypothesis_content_digest": self.hypothesis_content_digest,
                "evidence_ids": list(self.evidence_ids), "verdict": self.verdict.value, "observed": self.observed,
                "predicted": self.predicted, "combined_uncertainty": self.combined_uncertainty, "reason": self.reason,
                "registry_head": self.registry_head}

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


def judge(falsifier_digest: str, registry: FalsifierRegistry, evidence: EvidenceItem, *, predicted: float | None,
          prediction_uncertainty: float | None) -> FalsifierVerdict:
    """Apply a SEALED falsifier to evidence exposed after its seal."""
    f = registry.sealed(falsifier_digest)
    exposed = registry.exposure_sequence(evidence.evidence_id)
    if exposed is None:
        raise FalsificationRefused("the evidence was never exposed through the registry; its timing is unknown")
    if exposed < registry.seal_sequence(falsifier_digest):
        raise FalsificationRefused("the evidence was exposed BEFORE this falsifier was sealed: a post-hoc test decides nothing")
    if evidence.source != f.evidence_source:
        raise FalsificationRefused(f"evidence source {evidence.source!r} is not the falsifier's admissible source {f.evidence_source!r}")
    if evidence.observable != f.observable or evidence.unit != f.unit:
        raise FalsificationRefused("the evidence measures another observable or unit than the falsifier declared")
    base = dict(falsifier_digest=falsifier_digest, falsifier_ref=f"{f.falsifier_id}@v{f.version}", hypothesis_id=f.hypothesis_id,
                hypothesis_content_digest=f.hypothesis_content_digest, evidence_ids=(evidence.evidence_id,),
                observed=float(evidence.value), registry_head=registry.head)
    missing = []
    if evidence.uncertainty is None:
        missing.append("observation uncertainty")
    if f.criterion is CriterionKind.PREDICTION_DEVIATION and predicted is None:
        missing.append("prediction")
    if f.criterion is CriterionKind.PREDICTION_DEVIATION and prediction_uncertainty is None:
        missing.append("prediction uncertainty")
    if missing:
        return FalsifierVerdict(**base, verdict=Verdict.INCONCLUSIVE, predicted=predicted, combined_uncertainty=None,
                                reason=f"{', '.join(missing)} UNKNOWN: inconclusive (never treated as zero)")
    u_obs = float(evidence.uncertainty)
    if not (math.isfinite(u_obs) and u_obs >= 0):
        raise FalsificationRefused("an observation uncertainty is finite and non-negative")
    k = f.parameters["k"]
    if f.criterion is CriterionKind.PREDICTION_DEVIATION:
        u_pred = float(prediction_uncertainty)
        if not (math.isfinite(u_pred) and u_pred >= 0):
            raise FalsificationRefused("a prediction uncertainty is finite and non-negative")
        u = math.sqrt(u_obs ** 2 + u_pred ** 2)
        dev = abs(float(evidence.value) - float(predicted))
        refuted = dev > k * u
        reason = f"|observed - predicted| = {dev:.6g} {'>' if refuted else '<='} k*u = {k * u:.6g}"
        return FalsifierVerdict(**base, verdict=Verdict.REFUTED if refuted else Verdict.NOT_REFUTED, predicted=float(predicted),
                                combined_uncertainty=u, reason=reason)
    lo, hi = f.parameters["low"], f.parameters["high"]
    inside = lo + k * u_obs <= evidence.value <= hi - k * u_obs          # inside the forbidden region beyond its uncertainty
    outside = evidence.value < lo - k * u_obs or evidence.value > hi + k * u_obs
    verdict = Verdict.REFUTED if inside else Verdict.NOT_REFUTED if outside else Verdict.INCONCLUSIVE
    return FalsifierVerdict(**base, verdict=verdict, predicted=predicted, combined_uncertainty=u_obs,
                            reason=f"observation {evidence.value:.6g} +- {k}*{u_obs:.3g} vs forbidden [{lo:.6g}, {hi:.6g}]")


class VerdictStore:
    def __init__(self) -> None:
        self._verdicts: dict[str, FalsifierVerdict] = {}

    def add(self, verdict: FalsifierVerdict) -> str:
        d = verdict.digest
        self._verdicts[d] = verdict
        return d

    def get(self, digest: str) -> FalsifierVerdict | None:
        return self._verdicts.get(digest)

    def for_content(self, hypothesis_id: str, content_digest: str) -> tuple[FalsifierVerdict, ...]:
        return tuple(sorted((v for v in self._verdicts.values() if v.hypothesis_id == hypothesis_id
                             and v.hypothesis_content_digest == content_digest), key=lambda v: v.digest))


def _status_from(verdicts: Iterable[FalsifierVerdict], sealed: Iterable[Falsifier]) -> HypothesisStatus:
    verdicts = tuple(verdicts)
    if any(v.verdict is Verdict.REFUTED for v in verdicts):
        return HypothesisStatus.REFUTED
    judged = {v.falsifier_digest for v in verdicts if v.verdict is Verdict.NOT_REFUTED}
    if verdicts and all(f.digest in judged for f in sealed):
        return HypothesisStatus.SURVIVING
    return HypothesisStatus.UNKNOWN


def apply_verdicts(hypothesis: Hypothesis, registry: FalsifierRegistry, store: VerdictStore) -> Hypothesis:
    """The hypothesis's status from EVERY verdict recorded for its exact content.

    REFUTED if any sealed falsifier refuted it; SURVIVING only when every sealed falsifier for this content has a
    NOT_REFUTED verdict; otherwise UNKNOWN (an inconclusive or missing verdict is not survival)."""
    content = hypothesis.content_digest
    sealed = registry.sealed_for(hypothesis.hypothesis_id, content)
    if not sealed:
        raise FalsificationRefused("no sealed falsifier tests this hypothesis content")
    missing = sorted(f"{f.falsifier_id}@v{f.version}" for f in sealed if f"{f.falsifier_id}@v{f.version}" not in hypothesis.falsifier_refs)
    if missing:
        raise FalsificationRefused(f"the hypothesis does not list its sealed falsifiers {missing}")
    verdicts = store.for_content(hypothesis.hypothesis_id, content)
    status = _status_from(verdicts, sealed)
    if status is HypothesisStatus.UNKNOWN:
        return hypothesis.revise(status=HypothesisStatus.UNKNOWN, status_basis=())
    cited = [v for v in verdicts if (status is HypothesisStatus.REFUTED and v.verdict is Verdict.REFUTED)
             or (status is HypothesisStatus.SURVIVING and v.verdict is Verdict.NOT_REFUTED)]
    basis = tuple(VerdictReference(v.falsifier_ref, v.digest, v.verdict.value, content) for v in cited)
    return hypothesis.revise(status=status, status_basis=basis)


def verify_status(hypothesis: Hypothesis, registry: FalsifierRegistry, store: VerdictStore) -> list[str]:
    """Why ``hypothesis``'s status is NOT what the sealed falsifiers and recorded verdicts establish (empty when it is)."""
    problems = []
    for ref in hypothesis.status_basis:
        v = store.get(ref.verdict_digest)
        if v is None:
            problems.append(f"verdict {ref.verdict_digest[:12]} is not in the verdict store")
            continue
        if (v.falsifier_ref, v.verdict.value, v.hypothesis_content_digest) != (ref.falsifier_ref, ref.verdict, ref.content_digest):
            problems.append(f"verdict {ref.verdict_digest[:12]} does not say what the reference claims")
        try:
            registry.sealed(v.falsifier_digest)
        except FalsificationRefused:
            problems.append(f"verdict {ref.verdict_digest[:12]} used an unsealed falsifier")
    content = hypothesis.content_digest
    sealed = registry.sealed_for(hypothesis.hypothesis_id, content)
    if hypothesis.status in (HypothesisStatus.SURVIVING, HypothesisStatus.REFUTED, HypothesisStatus.UNKNOWN) and sealed:
        expected = _status_from(store.for_content(hypothesis.hypothesis_id, content), sealed)
        if expected is not hypothesis.status:
            problems.append(f"the recorded verdicts establish {expected.value}, not {hypothesis.status.value}")
    elif hypothesis.status in (HypothesisStatus.SURVIVING, HypothesisStatus.REFUTED):
        problems.append("no sealed falsifier exists for this hypothesis content")
    return problems


__all__ = ["CriterionKind", "EvidenceItem", "FalsificationRefused", "Falsifier", "FalsifierRegistry", "FalsifierVerdict",
           "RegistryEntry", "Verdict", "VerdictStore", "apply_verdicts", "judge", "verify_status"]
