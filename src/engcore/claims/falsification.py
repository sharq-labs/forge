"""Sealed falsifiers and their verdicts: the only path to a verdict-backed hypothesis status.

Three parties, three records:

* An :class:`ExposureAuthority` is the MEASUREMENT side (an escrow, an instrument record, an experiment log).  It owns
  the clock.  Evidence exists for a falsifier only as an :class:`EvidenceItem` the authority RELEASED: the item's
  digest is derived from its fields, its exposure sequence is the authority's clock at release, and an HMAC binds both.
  The evidence id is the authority's ACQUISITION identity: re-releasing an acquisition keeps its first exposure, while
  a genuine repeat measurement (a new acquisition) is new evidence even when its value is identical.  The API given to
  the proposer side (a registry) does not expose ``release``; inside one process that is construction, not isolation.
* A :class:`Falsifier` is pre-registered against ONE hypothesis claim (:attr:`Hypothesis.content_digest`): the test
  conditions, an admissible :class:`EvidenceSource`, the refutation criterion and EVERYTHING it compares against --
  the predicted value and its uncertainty, the coverage factor ``k`` (bounded by :data:`K_MAX`) and the RESOLUTION the
  test must achieve (the largest ``k * u`` that still discriminates).  Nothing a verdict depends on is supplied at
  judge time.
* The :class:`FalsifierRegistry` (one per campaign, issued by the authority) is a hash chain of SEALS (stamped with the
  authority's clock) and JUDGMENTS.  :func:`judge` records every verdict in the chain; status is derived from the chain
  only, so a verdict cannot be forged into, or left out of, a hypothesis's record -- and :func:`apply_verdicts` itself
  judges EVERY post-seal release that matches a sealed falsifier (source, observable, unit and test conditions), so no
  refuting measurement can be left unjudged.
* A refutation follows the hypothesis id: once any revision of a hypothesis is refuted in a campaign, every later
  revision of that id is REFUTED there.  A different claim is a new hypothesis (``derive_hypothesis``, parents kept).
* :func:`verify_status` checks a record against an EXPECTED :class:`RegistryAnchor` (authority fingerprint + campaign),
  so a record cannot be verified against a registry of the claimant's choosing.

Verdicts: REFUTED, NOT_REFUTED, INCONCLUSIVE.  INCONCLUSIVE whenever an uncertainty is UNKNOWN (``None``) -- missing
uncertainty never becomes zero -- when an observation claims zero uncertainty without the falsifier allowing exact data,
and when the evidence is too uncertain to reach the sealed resolution.

A post-hoc change is a NEW falsifier version (:meth:`Falsifier.revise`), sealed later on the authority's clock and
judged only on evidence released after ITS seal; a refutation by any version of a falsifier still stands.

Seal-time vacuity guards: the resolution is at most half the predicted magnitude (or of a sealed ``scale`` when the
prediction is zero) and must exceed ``k * prediction_uncertainty``; a forbidden region's resolution is at most its
width.  Residual (recorded as deferred hardening): a forbidden region far from anything the hypothesis predicts is still
vacuous; registries and keys are per process with no persistence or attestation; inside one Python process the
authority's key is protected by construction only (the SECURITY_BOUNDARY_NOT_PROVEN caveat of the Blindfold escrow).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Mapping

from ..sria.decision import Hypothesis, HypothesisStatus, VerdictReference

FALSIFIER_SCHEMA = "engcore.claims.falsifier/2"
VERDICT_SCHEMA = "engcore.claims.falsifier_verdict/2"
GENESIS = "0" * 64
#: policy ceiling on the coverage factor: a falsifier that cannot fail is not a falsifier
K_MAX = 10.0


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class FalsificationRefused(ValueError):
    """A falsifier, seal or verdict that would let a hypothesis look better tested than it is."""


class CriterionKind(str, Enum):
    PREDICTION_DEVIATION = "prediction_deviation"   # refuted when |observed - predicted| > k * sqrt(u_obs^2 + u_pred^2)
    FORBIDDEN_REGION = "forbidden_region"           # refuted when the observation lies in [low, high] beyond k * u_obs


class EvidenceSource(str, Enum):
    """Admissible evidence sources: records an exposure authority produces.  Never a caller assertion or an opinion."""

    ESCROW_OBSERVATION = "escrow_observation"
    MEASUREMENT_RECORD = "measurement_record"
    EXPERIMENT_RECORD = "experiment_record"


class Verdict(str, Enum):
    REFUTED = "refuted"
    NOT_REFUTED = "not_refuted"
    INCONCLUSIVE = "inconclusive"


_REQUIRED = {CriterionKind.PREDICTION_DEVIATION: ("k", "predicted", "resolution"),
             CriterionKind.FORBIDDEN_REGION: ("k", "low", "high", "resolution")}
_ALLOWED = {CriterionKind.PREDICTION_DEVIATION: {"k", "predicted", "prediction_uncertainty", "resolution", "scale"},
            CriterionKind.FORBIDDEN_REGION: {"k", "low", "high", "resolution"}}
#: the resolution may be at most this fraction of the predicted magnitude (a test that cannot tell 0 from 2x is vacuous)
MAX_RELATIVE_RESOLUTION = 0.5
_HEX = set("0123456789abcdef")


@dataclass(frozen=True)
class Falsifier:
    falsifier_id: str
    hypothesis_id: str
    hypothesis_content_digest: str
    observable: str
    unit: str
    test_conditions: Mapping[str, Any]
    evidence_source: EvidenceSource
    criterion: CriterionKind
    parameters: Mapping[str, float]      # see _REQUIRED; ``prediction_uncertainty`` absent = UNKNOWN (-> INCONCLUSIVE)
    version: int = 1
    supersedes: str = ""                 # digest of the falsifier this revision replaces (required iff version > 1)
    allow_exact_observation: bool = False

    def __post_init__(self) -> None:
        for label in ("falsifier_id", "hypothesis_id", "observable", "unit"):
            if not str(getattr(self, label)).strip():
                raise FalsificationRefused(f"a falsifier names its {label}")
        if "@" in self.falsifier_id:
            raise FalsificationRefused("a falsifier id has no '@' (references are id@vN)")
        if len(str(self.hypothesis_content_digest)) != 64 or set(str(self.hypothesis_content_digest)) - _HEX:
            raise FalsificationRefused("a falsifier binds the hypothesis CONTENT digest it tests")
        if not isinstance(self.allow_exact_observation, bool):
            raise FalsificationRefused("allow_exact_observation is a boolean")
        try:
            object.__setattr__(self, "evidence_source", EvidenceSource(self.evidence_source))
        except ValueError as exc:
            raise FalsificationRefused(f"evidence source must be one of {[s.value for s in EvidenceSource]}") from exc
        object.__setattr__(self, "criterion", CriterionKind(self.criterion))
        params = {str(k): float(val) for k, val in dict(self.parameters).items()}
        if any(not math.isfinite(val) for val in params.values()):
            raise FalsificationRefused("criterion parameters are finite")
        missing = [k for k in _REQUIRED[self.criterion] if k not in params]
        if missing:
            raise FalsificationRefused(f"{self.criterion.value} seals {missing} before any evidence: never defaulted, never supplied later")
        if set(params) - _ALLOWED[self.criterion]:
            raise FalsificationRefused(f"unknown criterion parameters {sorted(set(params) - _ALLOWED[self.criterion])}")
        if not 0 < params["k"] <= K_MAX:
            raise FalsificationRefused(f"the coverage factor k is in (0, {K_MAX}]: a falsifier that cannot fail is not a falsifier")
        if not params["resolution"] > 0:
            raise FalsificationRefused("the resolution (largest k*u that still discriminates) is positive")
        if params.get("prediction_uncertainty", 0.0) < 0:
            raise FalsificationRefused("a prediction uncertainty is non-negative")
        if self.criterion is CriterionKind.FORBIDDEN_REGION:
            if not params["low"] < params["high"]:
                raise FalsificationRefused("a forbidden region declares low < high")
            if params["resolution"] > params["high"] - params["low"]:
                raise FalsificationRefused("a forbidden region's resolution is at most its width")
        else:
            magnitude = abs(params["predicted"]) if params["predicted"] != 0 else params.get("scale", 0.0)
            if not magnitude > 0:
                raise FalsificationRefused("a zero prediction seals a positive scale for its resolution")
            if params["resolution"] > MAX_RELATIVE_RESOLUTION * magnitude:
                raise FalsificationRefused(f"the resolution exceeds {MAX_RELATIVE_RESOLUTION} x the predicted magnitude: a test "
                                           "that cannot fail is not a falsifier")
            if "prediction_uncertainty" in params and params["k"] * params["prediction_uncertainty"] >= params["resolution"]:
                raise FalsificationRefused("k x prediction uncertainty already exceeds the resolution: this falsifier can never "
                                           "discriminate")
        object.__setattr__(self, "parameters", dict(sorted(params.items())))
        object.__setattr__(self, "test_conditions", json.loads(json.dumps(dict(self.test_conditions), sort_keys=True)))
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise FalsificationRefused("falsifier versions are integers starting at 1")
        if (self.version > 1) != bool(self.supersedes):
            raise FalsificationRefused("a version above 1 names the falsifier it supersedes, and version 1 supersedes nothing")

    @property
    def ref(self) -> str:
        return f"{self.falsifier_id}@v{self.version}"

    def to_dict(self) -> dict[str, Any]:
        return {"schema": FALSIFIER_SCHEMA, "falsifier_id": self.falsifier_id, "hypothesis_id": self.hypothesis_id,
                "hypothesis_content_digest": self.hypothesis_content_digest, "observable": self.observable, "unit": self.unit,
                "test_conditions": dict(self.test_conditions), "evidence_source": self.evidence_source.value,
                "criterion": self.criterion.value, "parameters": dict(self.parameters), "version": self.version,
                "supersedes": self.supersedes, "allow_exact_observation": self.allow_exact_observation}

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())

    def revise(self, **changes: Any) -> "Falsifier":
        """A post-hoc change is a NEW falsifier version (sealed separately); the original is never mutated."""
        for fixed in ("falsifier_id", "hypothesis_id", "hypothesis_content_digest", "version", "supersedes"):
            if fixed in changes:
                raise FalsificationRefused(f"a revision keeps the {fixed}; a test of other content is a new falsifier")
        return replace(self, version=self.version + 1, supersedes=self.digest, **changes)


# ---------------------------------------------------------------------------- evidence + the exposure authority


def evidence_content_digest(source: EvidenceSource, observable: str, unit: str, value: float, uncertainty: float | None,
                            conditions: Mapping[str, Any]) -> str:
    return _digest({"source": EvidenceSource(source).value, "observable": observable, "unit": unit, "value": float(value),
                    "uncertainty": None if uncertainty is None else float(uncertainty), "conditions": dict(conditions)})


@dataclass(frozen=True)
class EvidenceItem:
    """One observation RELEASED by an exposure authority.  ``uncertainty`` None = UNKNOWN (never zero)."""

    evidence_id: str
    source: EvidenceSource
    observable: str
    unit: str
    value: float
    uncertainty: float | None
    conditions: Mapping[str, Any]
    authority_id: str
    exposure_sequence: int
    exposure_mac: str

    @property
    def content_digest(self) -> str:
        """Derived from the fields -- a value swapped under a recorded digest no longer matches it."""
        return evidence_content_digest(self.source, self.observable, self.unit, self.value, self.uncertainty, self.conditions)


class _Issued:
    """Marker: only an authority constructs a registry."""


class ExposureAuthority:
    """The measurement side's clock.  Only it releases evidence; it stamps seals; it issues one registry per campaign."""

    def __init__(self, authority_id: str, *, key: bytes | None = None) -> None:
        if not str(authority_id).strip():
            raise FalsificationRefused("an exposure authority has an id")
        self.authority_id = authority_id
        self.__key = key if key is not None else os.urandom(32)
        self._clock = 0
        self._released: dict[str, EvidenceItem] = {}      # acquisition id -> the item as first released
        self._registries: dict[str, FalsifierRegistry] = {}
        self._issued = _Issued()

    @property
    def fingerprint(self) -> str:
        """Identifies this authority's KEY (not just its id string): another authority with the same id differs."""
        return hashlib.sha256(b"forge.exposure-authority\n" + self.__key).hexdigest()

    @property
    def clock(self) -> int:
        return self._clock

    def _tick(self) -> int:
        self._clock += 1
        return self._clock

    def _mac(self, evidence_id: str, content: str, seq: int) -> str:
        return hmac.new(self.__key, f"{self.authority_id}\n{evidence_id}\n{content}\n{seq}".encode(), hashlib.sha256).hexdigest()

    def release(self, *, evidence_id: str, source: EvidenceSource | str, observable: str, unit: str, value: float,
                uncertainty: float | None, conditions: Mapping[str, Any] | None = None) -> EvidenceItem:
        """Expose one observation to the proposer side NOW (on this authority's clock).  ``evidence_id`` is the
        acquisition identity this authority assigned to the measurement."""
        source = EvidenceSource(source)
        if not str(evidence_id).strip():
            raise FalsificationRefused("released evidence has an id")
        if not math.isfinite(float(value)):
            raise FalsificationRefused("an observation value is finite; a non-finite value is not evidence")
        if uncertainty is not None and not (math.isfinite(float(uncertainty)) and float(uncertainty) >= 0):
            raise FalsificationRefused("an observation uncertainty is finite and non-negative, or UNKNOWN (None)")
        conds = json.loads(json.dumps(dict(conditions or {}), sort_keys=True))
        content = evidence_content_digest(source, observable, unit, value, uncertainty, conds)
        prior = self._released.get(evidence_id)
        if prior is not None:                             # an acquisition re-released keeps its FIRST exposure
            if prior.content_digest != content:
                raise FalsificationRefused("this acquisition was already released with other content")
            return prior
        seq = self._tick()
        item = EvidenceItem(evidence_id, source, observable, unit, float(value), None if uncertainty is None else float(uncertainty),
                            conds, self.authority_id, seq, self._mac(evidence_id, content, seq))
        self._released[evidence_id] = item
        return item

    def _releases_after(self, clock: int) -> tuple[EvidenceItem, ...]:
        return tuple(sorted((e for e in self._released.values() if e.exposure_sequence > clock), key=lambda e: e.exposure_sequence))

    def verify(self, item: EvidenceItem) -> bool:
        prior = self._released.get(getattr(item, "evidence_id", None))
        return (isinstance(item, EvidenceItem) and prior is not None and item.authority_id == self.authority_id
                and prior.content_digest == item.content_digest and prior.exposure_sequence == item.exposure_sequence
                and hmac.compare_digest(item.exposure_mac, self._mac(item.evidence_id, item.content_digest, item.exposure_sequence)))

    def novelty_ledger(self, campaign_id: str) -> Any:
        """THE novelty ledger of a campaign, on this authority's clock (see :mod:`engcore.claims.novelty`)."""
        from .novelty import NoveltyLedger  # local: novelty depends on this module, not the reverse
        if not str(campaign_id).strip():
            raise FalsificationRefused("a novelty ledger belongs to a campaign")
        ledgers = self.__dict__.setdefault("_novelty_ledgers", {})
        if campaign_id not in ledgers:
            ledgers[campaign_id] = NoveltyLedger(self, campaign_id, self._issued)
        return ledgers[campaign_id]

    def registry(self, campaign_id: str) -> "FalsifierRegistry":
        """THE registry of a campaign (one per campaign: a fresh registry cannot be forked to drop a refutation)."""
        if not str(campaign_id).strip():
            raise FalsificationRefused("a registry belongs to a campaign")
        if campaign_id not in self._registries:
            self._registries[campaign_id] = FalsifierRegistry(self, campaign_id, self._issued)
        return self._registries[campaign_id]


# ---------------------------------------------------------------------------- the registry (seals + judgments)


@dataclass(frozen=True)
class RegistryEntry:
    sequence: int
    previous: str
    kind: str                     # "sealed" | "judged"
    subject: str                  # falsifier digest | verdict digest
    payload_json: str

    @property
    def digest(self) -> str:
        return _digest({"sequence": self.sequence, "previous": self.previous, "kind": self.kind, "subject": self.subject,
                        "payload": json.loads(self.payload_json)})


@dataclass(frozen=True)
class FalsifierVerdict:
    falsifier_digest: str
    falsifier_ref: str
    hypothesis_id: str
    hypothesis_content_digest: str
    evidence_id: str
    evidence_content_digest: str
    evidence_exposure_sequence: int
    seal_clock: int
    verdict: Verdict
    observed: float
    predicted: float | None
    k: float
    combined_uncertainty: float | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"schema": VERDICT_SCHEMA, "falsifier_digest": self.falsifier_digest, "falsifier_ref": self.falsifier_ref,
                "hypothesis_id": self.hypothesis_id, "hypothesis_content_digest": self.hypothesis_content_digest,
                "evidence_id": self.evidence_id, "evidence_content_digest": self.evidence_content_digest,
                "evidence_exposure_sequence": self.evidence_exposure_sequence, "seal_clock": self.seal_clock,
                "verdict": self.verdict.value, "observed": self.observed, "predicted": self.predicted, "k": self.k,
                "combined_uncertainty": self.combined_uncertainty, "reason": self.reason}

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


class FalsifierRegistry:
    """Hash-chained record of seals (stamped with the authority's clock) and judgments.  Issued by an authority."""

    def __init__(self, authority: ExposureAuthority, campaign_id: str, issued: Any = None) -> None:
        if not isinstance(authority, ExposureAuthority) or issued is not getattr(authority, "_issued", object()):
            raise FalsificationRefused("a registry is issued by its exposure authority (ExposureAuthority.registry)")
        self.__authority = authority
        self.campaign_id = campaign_id
        self._entries: list[RegistryEntry] = []
        self._sealed: dict[str, Falsifier] = {}
        self._seal_clock: dict[str, int] = {}
        self._versions: dict[tuple[str, int], str] = {}
        self._verdicts: dict[str, FalsifierVerdict] = {}

    @property
    def head(self) -> str:
        return self._entries[-1].digest if self._entries else GENESIS

    @property
    def anchor(self) -> "RegistryAnchor":
        return RegistryAnchor(self.__authority.fingerprint, self.campaign_id)

    def _verify_evidence(self, item: EvidenceItem) -> bool:
        return self.__authority.verify(item)

    def _tick(self) -> int:
        return self.__authority._tick()

    def _matching_releases(self, f: Falsifier) -> tuple[EvidenceItem, ...]:
        """Every release after ``f``'s seal that the falsifier applies to (source, observable, unit, test conditions)."""
        return tuple(e for e in self.__authority._releases_after(self._seal_clock[f.digest])
                     if e.source is f.evidence_source and e.observable == f.observable and e.unit == f.unit
                     and dict(e.conditions) == dict(f.test_conditions))

    def _judged(self, falsifier_digest: str) -> set[str]:
        return {v.evidence_id for v in self._verdicts.values() if v.falsifier_digest == falsifier_digest}

    def unjudged(self, hypothesis_id: str) -> tuple[tuple[str, str], ...]:
        """(falsifier ref, evidence id) pairs of matching post-seal releases not yet judged, for any of the hypothesis's
        falsifiers (every version)."""
        out = []
        for f in self._sealed.values():
            if f.hypothesis_id == hypothesis_id:
                done = self._judged(f.digest)
                out.extend((f.ref, e.evidence_id) for e in self._matching_releases(f) if e.evidence_id not in done)
        return tuple(sorted(out))

    def judge_all(self, hypothesis_id: str) -> tuple["FalsifierVerdict", ...]:
        """Judge every matching post-seal release for every sealed falsifier of this hypothesis: nothing is left out."""
        out = []
        for f in sorted(self._sealed.values(), key=lambda x: x.digest):
            if f.hypothesis_id == hypothesis_id:
                done = self._judged(f.digest)
                out.extend(judge(f.digest, self, e) for e in self._matching_releases(f) if e.evidence_id not in done)
        return tuple(out)

    @property
    def entries(self) -> tuple[RegistryEntry, ...]:
        return tuple(self._entries)

    def verify_chain(self) -> str:
        prev = GENESIS
        for i, e in enumerate(self._entries):
            if e.sequence != i or e.previous != prev:
                raise FalsificationRefused(f"the falsifier registry chain is broken at entry {i}")
            prev = e.digest
        return prev

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
        key = (falsifier.falsifier_id, falsifier.version)
        if key in self._versions:
            raise FalsificationRefused(f"{falsifier.ref} is already sealed; a change is a new version")
        if falsifier.version > 1:
            prior = self._sealed.get(falsifier.supersedes)
            if prior is None or prior.falsifier_id != falsifier.falsifier_id or prior.version != falsifier.version - 1 \
                    or prior.hypothesis_id != falsifier.hypothesis_id:
                raise FalsificationRefused("a revision supersedes the sealed previous version of the same falsifier")
        elif any(fid == falsifier.falsifier_id for fid, _v in self._versions):
            raise FalsificationRefused(f"falsifier {falsifier.falsifier_id!r} exists; a change is a new version, not a new v1")
        clock = self._tick()
        e = self._add("sealed", d, {**falsifier.to_dict(), "authority_clock": clock})
        self._sealed[d] = falsifier
        self._seal_clock[d] = clock
        self._versions[key] = d
        return e

    def sealed(self, falsifier_digest: str) -> Falsifier:
        f = self._sealed.get(falsifier_digest)
        if f is None:
            raise FalsificationRefused("the falsifier is not sealed; an unsealed falsifier decides nothing")
        return f

    def seal_clock(self, falsifier_digest: str) -> int:
        self.sealed(falsifier_digest)
        return self._seal_clock[falsifier_digest]

    def sealed_for(self, hypothesis_id: str, content_digest: str) -> tuple[Falsifier, ...]:
        """Every sealed version of every falsifier for this claim."""
        return tuple(f for f in self._sealed.values() if f.hypothesis_id == hypothesis_id and f.hypothesis_content_digest == content_digest)

    def current_for(self, hypothesis_id: str, content_digest: str) -> tuple[Falsifier, ...]:
        """The latest sealed version of each falsifier for this claim."""
        latest: dict[str, Falsifier] = {}
        for f in self.sealed_for(hypothesis_id, content_digest):
            if f.falsifier_id not in latest or f.version > latest[f.falsifier_id].version:
                latest[f.falsifier_id] = f
        return tuple(latest[k] for k in sorted(latest))

    def _record(self, verdict: FalsifierVerdict) -> FalsifierVerdict:
        d = verdict.digest
        if d not in self._verdicts:
            self._add("judged", d, verdict.to_dict())
            self._verdicts[d] = verdict
        return verdict

    def verdict(self, digest: str) -> FalsifierVerdict | None:
        return self._verdicts.get(digest)

    def verdicts_for(self, hypothesis_id: str, content_digest: str) -> tuple[FalsifierVerdict, ...]:
        """EVERY recorded verdict for this claim, every falsifier version: nothing judged can be left out."""
        return tuple(sorted((v for v in self._verdicts.values() if v.hypothesis_id == hypothesis_id
                             and v.hypothesis_content_digest == content_digest), key=lambda v: v.digest))

    def refutations_of(self, hypothesis_id: str) -> tuple[FalsifierVerdict, ...]:
        """Every REFUTED verdict for ANY revision of this hypothesis id (a refutation follows the id)."""
        return tuple(sorted((v for v in self._verdicts.values() if v.hypothesis_id == hypothesis_id and v.verdict is Verdict.REFUTED),
                            key=lambda v: v.digest))


@dataclass(frozen=True)
class RegistryAnchor:
    """Which registry a consumer trusts: the authority's key fingerprint and the campaign."""

    authority_fingerprint: str
    campaign_id: str


def judge(falsifier_digest: str, registry: FalsifierRegistry, evidence: EvidenceItem) -> FalsifierVerdict:
    """Apply a SEALED falsifier to evidence its authority released AFTER the seal; the verdict is recorded in the chain.
    Every number compared is either sealed in the falsifier or carried by the released evidence."""
    f = registry.sealed(falsifier_digest)
    if not registry._verify_evidence(evidence):
        raise FalsificationRefused("the evidence was not released by this registry's exposure authority (or was altered)")
    seal_clock = registry.seal_clock(falsifier_digest)
    if evidence.exposure_sequence <= seal_clock:
        raise FalsificationRefused("the evidence was exposed BEFORE this falsifier was sealed: a post-hoc test decides nothing")
    if evidence.source is not f.evidence_source:
        raise FalsificationRefused(f"evidence source {evidence.source.value!r} is not the falsifier's admissible source "
                                   f"{f.evidence_source.value!r}")
    if evidence.observable != f.observable or evidence.unit != f.unit:
        raise FalsificationRefused("the evidence measures another observable or unit than the falsifier declared")
    if dict(evidence.conditions) != dict(f.test_conditions):
        raise FalsificationRefused("the evidence was taken at other conditions than the falsifier's sealed test conditions")
    p = f.parameters
    k = p["k"]
    base = dict(falsifier_digest=falsifier_digest, falsifier_ref=f.ref, hypothesis_id=f.hypothesis_id,
                hypothesis_content_digest=f.hypothesis_content_digest, evidence_id=evidence.evidence_id,
                evidence_content_digest=evidence.content_digest, evidence_exposure_sequence=evidence.exposure_sequence,
                seal_clock=seal_clock, observed=float(evidence.value), k=k, predicted=p.get("predicted"))

    def inconclusive(reason: str, u: float | None = None) -> FalsifierVerdict:
        return registry._record(FalsifierVerdict(**base, verdict=Verdict.INCONCLUSIVE, combined_uncertainty=u, reason=reason))

    if evidence.uncertainty is None:
        return inconclusive("observation uncertainty UNKNOWN: inconclusive (never treated as zero)")
    u_obs = float(evidence.uncertainty)
    if u_obs == 0 and not f.allow_exact_observation:
        return inconclusive("the observation claims zero uncertainty and the falsifier did not allow exact data")
    if f.criterion is CriterionKind.PREDICTION_DEVIATION:
        if "prediction_uncertainty" not in p:
            return inconclusive("prediction uncertainty UNKNOWN: inconclusive (never treated as zero)")
        u = math.sqrt(u_obs ** 2 + p["prediction_uncertainty"] ** 2)
        if k * u > p["resolution"]:
            return inconclusive(f"k*u = {k * u:.6g} exceeds the sealed resolution {p['resolution']:.6g}: the evidence cannot "
                                "discriminate", u)
        dev = abs(float(evidence.value) - p["predicted"])
        refuted = dev > k * u
        return registry._record(FalsifierVerdict(**base, verdict=Verdict.REFUTED if refuted else Verdict.NOT_REFUTED,
                                                 combined_uncertainty=u,
                                                 reason=f"|observed - predicted| = {dev:.6g} {'>' if refuted else '<='} k*u = {k * u:.6g}"))
    if k * u_obs > p["resolution"]:
        return inconclusive(f"k*u = {k * u_obs:.6g} exceeds the sealed resolution {p['resolution']:.6g}", u_obs)
    lo, hi, val = p["low"], p["high"], float(evidence.value)
    inside = lo + k * u_obs <= val <= hi - k * u_obs          # inside the forbidden region beyond its uncertainty
    outside = val < lo - k * u_obs or val > hi + k * u_obs
    verdict = Verdict.REFUTED if inside else Verdict.NOT_REFUTED if outside else Verdict.INCONCLUSIVE
    return registry._record(FalsifierVerdict(**base, verdict=verdict, combined_uncertainty=u_obs,
                                             reason=f"observation {val:.6g} +- {k}*{u_obs:.3g} vs forbidden [{lo:.6g}, {hi:.6g}]"))


# ---------------------------------------------------------------------------- status from the chain


def _expected(hypothesis: Hypothesis, registry: FalsifierRegistry) -> tuple[HypothesisStatus, tuple[FalsifierVerdict, ...], list[str]]:
    content = hypothesis.content_digest
    current = registry.current_for(hypothesis.hypothesis_id, content)
    problems = []
    refs = set(hypothesis.falsifier_refs)
    current_refs = {f.ref for f in current}
    refutations = registry.refutations_of(hypothesis.hypothesis_id)
    if refutations:                                                # any version, any revision of this id: never laundered
        return HypothesisStatus.REFUTED, refutations, problems
    if refs != current_refs:
        problems.append(f"the hypothesis lists falsifiers {sorted(refs)} but this registry holds {sorted(current_refs)} for its claim "
                        "(every listed falsifier is sealed here, every sealed one is listed, at its latest version)")
    pending = registry.unjudged(hypothesis.hypothesis_id)
    if pending:
        problems.append(f"matching post-seal evidence is not judged yet: {list(pending)[:5]}")
    verdicts = registry.verdicts_for(hypothesis.hypothesis_id, content)
    passed = {v.falsifier_digest for v in verdicts if v.verdict is Verdict.NOT_REFUTED}
    if current and not problems and all(f.digest in passed for f in current):
        current_digests = {f.digest for f in current}
        cited = tuple(v for v in verdicts if v.verdict is Verdict.NOT_REFUTED and v.falsifier_digest in current_digests)
        return HypothesisStatus.SURVIVING, cited, problems
    return HypothesisStatus.UNKNOWN, (), problems


def apply_verdicts(hypothesis: Hypothesis, registry: FalsifierRegistry) -> Hypothesis:
    """The hypothesis's status from EVERY verdict the registry chain holds for it, after judging every matching
    post-seal release (nothing can be left unjudged).

    REFUTED if any version of any falsifier refuted any revision of this hypothesis id; SURVIVING only when every listed
    falsifier (each at its latest sealed version) has a NOT_REFUTED verdict and nothing refutes; otherwise UNKNOWN (an
    inconclusive or missing verdict is not survival)."""
    registry.judge_all(hypothesis.hypothesis_id)
    status, cited, problems = _expected(hypothesis, registry)
    if status is HypothesisStatus.REFUTED:
        basis = tuple(VerdictReference(v.falsifier_ref, v.digest, v.verdict.value, v.hypothesis_content_digest) for v in cited)
        return hypothesis.revise(status=status, status_basis=basis)
    if problems:
        raise FalsificationRefused("; ".join(problems))
    if status is HypothesisStatus.UNKNOWN:
        return hypothesis.revise(status=HypothesisStatus.UNKNOWN, status_basis=())
    basis = tuple(VerdictReference(v.falsifier_ref, v.digest, v.verdict.value, hypothesis.content_digest) for v in cited)
    return hypothesis.revise(status=status, status_basis=basis)


def verify_status(hypothesis: Hypothesis, registry: FalsifierRegistry, *, anchor: RegistryAnchor) -> list[str]:
    """Why ``hypothesis``'s status is NOT what the EXPECTED campaign registry establishes (empty when it is).  Every
    consumer of a hypothesis status gates on this; construction alone checks only shape."""
    if registry.anchor != anchor:
        return ["the registry is not the expected one (authority key or campaign differs): a claimant does not choose its verifier"]
    try:
        registry.verify_chain()
    except FalsificationRefused as exc:
        return [str(exc)]
    problems = []
    for ref in hypothesis.status_basis:
        v = registry.verdict(ref.verdict_digest)
        if v is None:
            problems.append(f"verdict {ref.verdict_digest[:12]} is not in the registry chain")
            continue
        if (v.falsifier_ref, v.verdict.value, v.hypothesis_content_digest) != (ref.falsifier_ref, ref.verdict, ref.content_digest):
            problems.append(f"verdict {ref.verdict_digest[:12]} does not say what the reference claims")
    if registry.refutations_of(hypothesis.hypothesis_id) and hypothesis.status is not HypothesisStatus.REFUTED:
        problems.append(f"this hypothesis id is refuted in the registry; status {hypothesis.status.value} hides it "
                        "(a different claim is a new hypothesis)")
    if hypothesis.status is HypothesisStatus.INDISTINGUISHABLE:
        problems.append("INDISTINGUISHABLE has no registry adjudication rule yet; it cannot be verified")
    if hypothesis.status in (HypothesisStatus.SURVIVING, HypothesisStatus.REFUTED) or \
            (hypothesis.status is HypothesisStatus.UNKNOWN and hypothesis.falsifier_refs):
        expected, cited, why = _expected(hypothesis, registry)
        problems.extend(why)
        if expected is not hypothesis.status:
            problems.append(f"the registry chain establishes {expected.value}, not {hypothesis.status.value}")
        elif {b.verdict_digest for b in hypothesis.status_basis} != {v.digest for v in cited}:
            problems.append("the status basis does not cite exactly the verdicts that decide it")
    return problems


__all__ = ["CriterionKind", "EvidenceItem", "EvidenceSource", "ExposureAuthority", "FalsificationRefused", "Falsifier",
           "FalsifierRegistry", "FalsifierVerdict", "K_MAX", "MAX_RELATIVE_RESOLUTION", "RegistryAnchor", "RegistryEntry", "Verdict", "apply_verdicts", "evidence_content_digest",
           "judge", "verify_status"]
