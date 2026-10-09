"""FidelityGraph: measured relationships between fidelities, and the only path by which a cheap model may eliminate.

Builds on :mod:`.fidelity` (ordered rungs) and :mod:`.multifidelity` (per-rung
observations, standing, promotion) -- neither is replaced.  What this adds is
an explicit, MEASURED relationship between two realizations:

* a :class:`FidelityNode` binds a ladder rung to one model realization
  (model / realization / adapter identity);
* a :class:`FidelityLink` ``L -> H`` binds two nodes, an observable, a validity
  domain, the digest of the paired evaluation set it was measured on, and the
  measurement itself (:func:`measure_link`): rank correlation, decision
  agreement at the declared threshold, the discrepancy ``H - L`` and its
  envelope, and near-threshold confusion.  Nothing in a measurement is
  declared; everything is computed from the pairs.  A link must be ADMITTED (by
  a named authority, with enough pairs and a quantified discrepancy) before it
  can be used, and every change is a new version with an audit event.

Scientific rules enforced here:

* Cheap models PRIORITIZE; they never raise an evidence level.  A screening
  decision is a scheduling record (``ScreeningOutcome``), never a SUPPORTS /
  CONTRADICTS observation of :mod:`.multifidelity`.
* A cheap model ELIMINATES only through an ADMITTED link whose validity domain
  contains the candidate and whose discrepancy is QUANTIFIED, and only when even
  the optimistic end of the discrepancy envelope fails the threshold.  With no
  such link (or discrepancy UNKNOWN) the candidate is PROMOTED, unless it is
  rejected on a hard logical constraint, a hard physical constraint, or exact
  duplication -- the only rejections that need no link.
* Every elimination is recorded (:class:`EliminationLedger`, hash-chained) with
  the link identity and version, the reason and the decision margin.
* A declared fraction of eliminations, stratified by margin, is evaluated at the
  higher fidelity (:func:`audit_sample`); the measured FALSE_ELIMINATION_RATE
  above the campaign bound SUSPENDS the link (:func:`record_audit`).
* Candidates eliminated under a link version that is no longer ADMITTED
  (suspended, retired or superseded) become eligible for deterministic
  resurrection (:func:`resurrection_queue`); nothing disappears without trace.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Iterable, Mapping

from ..scientific.errors import InvalidScientificProblem
from .fidelity import FidelityLadder, FidelityRung

LINK_SCHEMA = "engcore.design.fidelity_link/1"
NODE_SCHEMA = "engcore.design.fidelity_node/1"
LEDGER_SCHEMA = "engcore.design.elimination_ledger/1"
GENESIS = "0" * 64


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class FidelityGraphRefusal(InvalidScientificProblem):
    """A fidelity relationship or screening decision the evidence does not support."""


# ---------------------------------------------------------------------------- nodes and domains


@dataclass(frozen=True)
class FidelityNode:
    """One rung realized by one concrete model/solver/adapter."""

    rung: FidelityRung
    model_ref: str
    realization_id: str
    realization_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.rung, FidelityRung):
            raise FidelityGraphRefusal("a fidelity node binds a FidelityRung")
        for label in ("model_ref", "realization_id", "realization_version"):
            if not str(getattr(self, label)).strip():
                raise FidelityGraphRefusal(f"a fidelity node names its {label}: a rung without a realization computes nothing")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": NODE_SCHEMA, "rung": self.rung.to_dict(), "model_ref": self.model_ref,
                "realization_id": self.realization_id, "realization_version": self.realization_version}

    @property
    def node_id(self) -> str:
        return _digest(self.to_dict())


@dataclass(frozen=True)
class ValidityDomain:
    """A box over named, unit-explicit variables.  A point missing a variable is OUTSIDE (never assumed inside)."""

    bounds: Mapping[str, tuple[float, float]]
    unit_of: Mapping[str, str]

    def __post_init__(self) -> None:
        if not self.bounds:
            raise FidelityGraphRefusal("a validity domain bounds at least one variable; 'everywhere' is not a domain")
        clean = {}
        for k, (lo, hi) in self.bounds.items():
            lo, hi = float(lo), float(hi)
            if not (math.isfinite(lo) and math.isfinite(hi) and lo <= hi):
                raise FidelityGraphRefusal(f"domain bound for {k!r} must be finite with lo <= hi")
            if not str(self.unit_of.get(k, "")).strip():
                raise FidelityGraphRefusal(f"domain variable {k!r} names its unit")
            clean[str(k)] = (lo, hi)
        object.__setattr__(self, "bounds", dict(sorted(clean.items())))
        object.__setattr__(self, "unit_of", {k: str(self.unit_of[k]) for k in clean})

    def contains(self, point: Mapping[str, float]) -> bool:
        for k, (lo, hi) in self.bounds.items():
            if k not in point:
                return False
            v = float(point[k])
            if not (math.isfinite(v) and lo <= v <= hi):
                return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {"bounds": {k: list(v) for k, v in self.bounds.items()}, "unit_of": dict(self.unit_of)}


# ---------------------------------------------------------------------------- measurement


class Sense(str, Enum):
    """How a candidate passes the screened constraint on the observable."""

    AT_MOST = "at_most"     # passes when value <= threshold
    AT_LEAST = "at_least"   # passes when value >= threshold

    def passes(self, value: float, threshold: float) -> bool:
        return value <= threshold if self is Sense.AT_MOST else value >= threshold


@dataclass(frozen=True)
class PairedEvaluation:
    """One candidate evaluated at BOTH fidelities (the calibration / evaluation set of a link)."""

    candidate_key: str
    point: Mapping[str, float]
    low_value: float
    high_value: float

    def __post_init__(self) -> None:
        if not str(self.candidate_key).strip():
            raise FidelityGraphRefusal("a paired evaluation names its candidate")
        for label in ("low_value", "high_value"):
            v = float(getattr(self, label))
            if not math.isfinite(v):
                raise FidelityGraphRefusal(f"a paired evaluation's {label} is finite; a failed evaluation is not a pair")
            object.__setattr__(self, label, v)
        object.__setattr__(self, "point", {str(k): float(v) for k, v in sorted(dict(self.point).items())})

    def to_dict(self) -> dict[str, Any]:
        return {"candidate_key": self.candidate_key, "point": dict(self.point), "low_value": self.low_value, "high_value": self.high_value}


class DiscrepancyStatus(str, Enum):
    QUANTIFIED = "quantified"
    UNKNOWN = "unknown"          # too few pairs: never treated as zero


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _pearson(a: list[float], b: list[float]) -> float | None:
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((y - mb) ** 2 for y in b))
    if sa == 0 or sb == 0:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb)


@dataclass(frozen=True)
class LinkMeasurement:
    """Computed from pairs by :func:`measure_link`; never declared."""

    pairs: int
    evaluation_set_digest: str
    rank_correlation: float | None          # Spearman; None when undefined (constant values)
    decision_agreement: float               # fraction of pairs where L and H take the same pass/fail decision
    discrepancy_status: DiscrepancyStatus
    discrepancy_mean: float | None          # mean of H - L
    discrepancy_std: float | None
    discrepancy_envelope: tuple[float, float] | None  # [lo, hi] of H - L used for elimination
    near_threshold_pairs: int
    near_threshold_confusion: float | None  # disagreement rate among pairs within the band; None when no pairs there
    threshold: float
    sense: Sense
    envelope_k: float
    near_band: float

    def to_dict(self) -> dict[str, Any]:
        return {"pairs": self.pairs, "evaluation_set_digest": self.evaluation_set_digest, "rank_correlation": self.rank_correlation,
                "decision_agreement": self.decision_agreement, "discrepancy_status": self.discrepancy_status.value,
                "discrepancy_mean": self.discrepancy_mean, "discrepancy_std": self.discrepancy_std,
                "discrepancy_envelope": None if self.discrepancy_envelope is None else list(self.discrepancy_envelope),
                "near_threshold_pairs": self.near_threshold_pairs, "near_threshold_confusion": self.near_threshold_confusion,
                "threshold": self.threshold, "sense": self.sense.value, "envelope_k": self.envelope_k, "near_band": self.near_band}


def measure_link(pairs: Iterable[PairedEvaluation], *, threshold: float, sense: Sense | str, envelope_k: float = 3.0,
                 near_band: float, min_pairs_for_discrepancy: int = 10) -> LinkMeasurement:
    """Measure the L -> H relationship on paired evaluations.

    The discrepancy envelope is ``[min(mean - k*std, min(d)), max(mean + k*std, max(d))]`` of ``d = H - L``:
    never narrower than what was observed.  Below ``min_pairs_for_discrepancy`` pairs it is UNKNOWN.
    """
    pairs = sorted(tuple(pairs), key=lambda p: p.candidate_key)
    if not pairs or any(not isinstance(p, PairedEvaluation) for p in pairs):
        raise FidelityGraphRefusal("a link is measured on at least one PairedEvaluation")
    if len({p.candidate_key for p in pairs}) != len(pairs):
        raise FidelityGraphRefusal("each candidate appears once in a link's evaluation set")
    sense = Sense(sense)
    threshold, envelope_k, near_band = float(threshold), float(envelope_k), float(near_band)
    if not (math.isfinite(threshold) and envelope_k > 0 and near_band > 0):
        raise FidelityGraphRefusal("threshold is finite; envelope_k and near_band are positive")
    if isinstance(min_pairs_for_discrepancy, bool) or min_pairs_for_discrepancy < 2:
        raise FidelityGraphRefusal("a discrepancy needs at least two pairs to have a spread")
    low = [p.low_value for p in pairs]
    high = [p.high_value for p in pairs]
    d = [h - lo for h, lo in zip(high, low)]
    rho = _pearson(_ranks(low), _ranks(high)) if len(pairs) > 1 else None
    agree = sum(sense.passes(lo, threshold) == sense.passes(h, threshold) for lo, h in zip(low, high)) / len(pairs)
    near = [(lo, h) for lo, h in zip(low, high) if abs(lo - threshold) <= near_band]
    confusion = None if not near else sum(sense.passes(lo, threshold) != sense.passes(h, threshold) for lo, h in near) / len(near)
    if len(pairs) >= min_pairs_for_discrepancy:
        mean = sum(d) / len(d)
        std = math.sqrt(sum((x - mean) ** 2 for x in d) / (len(d) - 1))
        env = (min(mean - envelope_k * std, min(d)), max(mean + envelope_k * std, max(d)))
        status = DiscrepancyStatus.QUANTIFIED
    else:
        mean = std = None
        env = None
        status = DiscrepancyStatus.UNKNOWN
    return LinkMeasurement(len(pairs), _digest([p.to_dict() for p in pairs]), rho, agree, status, mean, std, env, len(near),
                           confusion, threshold, sense, envelope_k, near_band)


# ---------------------------------------------------------------------------- links


class LinkStatus(str, Enum):
    MEASURED = "measured"      # measured, not admitted: may not eliminate
    ADMITTED = "admitted"      # may eliminate inside its domain
    SUSPENDED = "suspended"    # an audit (or an authority) withdrew it: its eliminations are resurrectable
    RETIRED = "retired"


@dataclass(frozen=True)
class LinkAuditEvent:
    action: str                # "measured", "admitted", "audit", "suspended", "retired"
    actor: str
    reason: str
    detail: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action, "actor": self.actor, "reason": self.reason, "detail": dict(self.detail)}


@dataclass(frozen=True)
class FidelityLink:
    link_id: str
    low: FidelityNode
    high: FidelityNode
    observable: str
    unit: str
    domain: ValidityDomain
    measurement: LinkMeasurement
    version: int = 1
    status: LinkStatus = LinkStatus.MEASURED
    audit: tuple[LinkAuditEvent, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", LinkStatus(self.status))
        if not all(str(getattr(self, k)).strip() for k in ("link_id", "observable", "unit")):
            raise FidelityGraphRefusal("a fidelity link names its id, observable and unit")
        if self.low.rung.rank >= self.high.rung.rank:
            raise FidelityGraphRefusal("a link runs from a LOWER to a HIGHER fidelity rank")
        if self.low.node_id == self.high.node_id:
            raise FidelityGraphRefusal("a link joins two different realizations")
        if not isinstance(self.measurement, LinkMeasurement):
            raise FidelityGraphRefusal("a link carries a computed LinkMeasurement")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise FidelityGraphRefusal("link versions start at 1")
        object.__setattr__(self, "audit", tuple(self.audit))
        if self.status is LinkStatus.ADMITTED and self.measurement.discrepancy_status is not DiscrepancyStatus.QUANTIFIED:
            raise FidelityGraphRefusal("an ADMITTED link has a QUANTIFIED discrepancy; UNKNOWN discrepancy never admits elimination")
        if self.status is not LinkStatus.MEASURED and not any(e.action == "admitted" for e in self.audit):
            raise FidelityGraphRefusal(f"a {self.status.value} link records its admission in the audit history")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": LINK_SCHEMA, "link_id": self.link_id, "low": self.low.to_dict(), "high": self.high.to_dict(),
                "observable": self.observable, "unit": self.unit, "domain": self.domain.to_dict(),
                "measurement": self.measurement.to_dict(), "version": self.version, "status": self.status.value,
                "audit": [e.to_dict() for e in self.audit]}

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())

    def _next(self, status: LinkStatus, event: LinkAuditEvent, **changes: Any) -> "FidelityLink":
        return replace(self, version=self.version + 1, status=status, audit=self.audit + (event,), **changes)

    def admit(self, *, actor: str, reason: str, min_pairs: int, min_rank_correlation: float | None = None) -> "FidelityLink":
        """Admit the link for elimination.  Needs a named actor, enough pairs and a QUANTIFIED discrepancy."""
        if not str(actor).strip() or not str(reason).strip():
            raise FidelityGraphRefusal("admission names its actor and reason")
        if self.status is not LinkStatus.MEASURED:
            raise FidelityGraphRefusal(f"only a MEASURED link is admitted (this one is {self.status.value}); re-measure to re-admit")
        m = self.measurement
        if m.pairs < min_pairs:
            raise FidelityGraphRefusal(f"the link was measured on {m.pairs} pairs; admission requires {min_pairs}")
        if m.discrepancy_status is not DiscrepancyStatus.QUANTIFIED:
            raise FidelityGraphRefusal("the link's discrepancy is UNKNOWN; it cannot be admitted to eliminate")
        if min_rank_correlation is not None and (m.rank_correlation is None or m.rank_correlation < min_rank_correlation):
            raise FidelityGraphRefusal(f"rank correlation {m.rank_correlation} is below the required {min_rank_correlation}")
        return self._next(LinkStatus.ADMITTED, LinkAuditEvent("admitted", actor, reason, {"min_pairs": min_pairs}))

    def suspend(self, *, actor: str, reason: str, detail: Mapping[str, Any] | None = None) -> "FidelityLink":
        if self.status is not LinkStatus.ADMITTED:
            raise FidelityGraphRefusal("only an ADMITTED link is suspended")
        return self._next(LinkStatus.SUSPENDED, LinkAuditEvent("suspended", actor, reason, dict(detail or {})))

    def retire(self, *, actor: str, reason: str) -> "FidelityLink":
        return self._next(LinkStatus.RETIRED, LinkAuditEvent("retired", actor, reason))

    def remeasured(self, measurement: LinkMeasurement, *, actor: str, reason: str) -> "FidelityLink":
        """A new version measured on a new evaluation set; it starts MEASURED (re-admission is a fresh decision)."""
        audit = self.audit + (LinkAuditEvent("measured", actor, reason, {"evaluation_set_digest": measurement.evaluation_set_digest}),)
        return replace(self, version=self.version + 1, status=LinkStatus.MEASURED, measurement=measurement,
                       audit=tuple(e for e in audit))


@dataclass(frozen=True)
class FidelityGraph:
    """Nodes on ONE ladder and the links between them."""

    ladder: FidelityLadder
    nodes: tuple[FidelityNode, ...]
    links: tuple[FidelityLink, ...] = ()

    def __post_init__(self) -> None:
        ids = {}
        for n in self.nodes:
            if self.ladder.rung(n.rung.rung_id) != n.rung:
                raise FidelityGraphRefusal(f"node rung {n.rung.rung_id!r} is not the ladder's rung")
            ids[n.node_id] = n
        if len(ids) != len(self.nodes):
            raise FidelityGraphRefusal("fidelity nodes are unique")
        seen = set()
        for link in self.links:
            if link.low.node_id not in ids or link.high.node_id not in ids:
                raise FidelityGraphRefusal(f"link {link.link_id!r} joins nodes outside the graph")
            if link.link_id in seen:
                raise FidelityGraphRefusal(f"link {link.link_id!r} appears twice; one current version per link")
            seen.add(link.link_id)

    def link(self, link_id: str) -> FidelityLink:
        for link in self.links:
            if link.link_id == link_id:
                return link
        raise FidelityGraphRefusal(f"no link {link_id!r}")

    def with_link(self, link: FidelityLink) -> "FidelityGraph":
        return replace(self, links=tuple(x for x in self.links if x.link_id != link.link_id) + (link,))


# ---------------------------------------------------------------------------- screening


class ScreeningOutcome(str, Enum):
    PROMOTE = "promote"
    ELIMINATE = "eliminate"        # by an admitted, in-domain, quantified link (resurrectable)
    REJECT_HARD = "reject_hard"    # logical/physical constraint or exact duplicate: needs no link


class HardRejection(str, Enum):
    LOGICAL_CONSTRAINT = "logical_constraint"
    PHYSICAL_CONSTRAINT = "physical_constraint"
    EXACT_DUPLICATE = "exact_duplicate"


@dataclass(frozen=True)
class ScreeningDecision:
    candidate_key: str
    outcome: ScreeningOutcome
    reason: str
    link_id: str = ""
    link_version: int = 0
    margin: float | None = None    # distance of the optimistic bound beyond the threshold (eliminations)
    hard_rejection: HardRejection | None = None
    classification: str = "scheduling_decision_not_evidence"

    def to_dict(self) -> dict[str, Any]:
        return {"candidate_key": self.candidate_key, "outcome": self.outcome.value, "reason": self.reason, "link_id": self.link_id,
                "link_version": self.link_version, "margin": self.margin,
                "hard_rejection": None if self.hard_rejection is None else self.hard_rejection.value, "classification": self.classification}


def screen(candidate_key: str, *, low_value: float | None, point: Mapping[str, float], link: FidelityLink | None,
           hard_rejection: tuple[HardRejection | str, str] | None = None) -> ScreeningDecision:
    """Decide PROMOTE / ELIMINATE / REJECT_HARD for one candidate screened at the low fidelity."""
    if hard_rejection is not None:
        kind, why = HardRejection(hard_rejection[0]), str(hard_rejection[1]).strip()
        if not why:
            raise FidelityGraphRefusal("a hard rejection states its reason")
        return ScreeningDecision(candidate_key, ScreeningOutcome.REJECT_HARD, why, hard_rejection=kind)
    if link is None:
        return ScreeningDecision(candidate_key, ScreeningOutcome.PROMOTE, "no fidelity link: a cheap result only prioritizes")
    if low_value is None or not math.isfinite(float(low_value)):
        return ScreeningDecision(candidate_key, ScreeningOutcome.PROMOTE, "no finite low-fidelity value: promote, never eliminate",
                                 link.link_id, link.version)
    if link.status is not LinkStatus.ADMITTED:
        return ScreeningDecision(candidate_key, ScreeningOutcome.PROMOTE, f"link is {link.status.value}, not admitted: promote",
                                 link.link_id, link.version)
    if not link.domain.contains(point):
        return ScreeningDecision(candidate_key, ScreeningOutcome.PROMOTE, "outside the link's validity domain: promote",
                                 link.link_id, link.version)
    m = link.measurement
    if m.discrepancy_status is not DiscrepancyStatus.QUANTIFIED or m.discrepancy_envelope is None:
        return ScreeningDecision(candidate_key, ScreeningOutcome.PROMOTE, "discrepancy UNKNOWN: promote", link.link_id, link.version)
    lo, hi = m.discrepancy_envelope
    low_value = float(low_value)
    if m.sense is Sense.AT_MOST:
        optimistic = low_value + lo          # the smallest the high-fidelity value can plausibly be
        margin = optimistic - m.threshold
    else:
        optimistic = low_value + hi
        margin = m.threshold - optimistic
    if margin > 0:
        return ScreeningDecision(candidate_key, ScreeningOutcome.ELIMINATE,
                                 f"even the optimistic high-fidelity bound {optimistic:.6g} fails the threshold {m.threshold:.6g}",
                                 link.link_id, link.version, margin)
    return ScreeningDecision(candidate_key, ScreeningOutcome.PROMOTE, "the discrepancy envelope admits a pass: promote",
                             link.link_id, link.version, margin)


# ---------------------------------------------------------------------------- ledger, audit, resurrection


@dataclass(frozen=True)
class LedgerEntry:
    sequence: int
    previous: str
    kind: str                       # "eliminated" | "rejected_hard" | "resurrected" | "audited"
    candidate_key: str
    payload: Mapping[str, Any]

    @property
    def digest(self) -> str:
        return _digest({"sequence": self.sequence, "previous": self.previous, "kind": self.kind, "candidate_key": self.candidate_key,
                        "payload": dict(self.payload)})

    def to_dict(self) -> dict[str, Any]:
        return {"sequence": self.sequence, "previous": self.previous, "kind": self.kind, "candidate_key": self.candidate_key,
                "payload": dict(self.payload), "digest": self.digest}


class EliminationLedger:
    """Append-only, hash-chained record of every non-promotion and every resurrection."""

    def __init__(self, entries: Iterable[LedgerEntry] = ()) -> None:
        self._entries: list[LedgerEntry] = []
        for e in entries:
            self._append(e)

    @property
    def head(self) -> str:
        return self._entries[-1].digest if self._entries else GENESIS

    @property
    def entries(self) -> tuple[LedgerEntry, ...]:
        return tuple(self._entries)

    def _append(self, entry: LedgerEntry) -> LedgerEntry:
        if entry.sequence != len(self._entries) or entry.previous != self.head:
            raise FidelityGraphRefusal("ledger entry does not extend the head; the ledger is not rewritten")
        self._entries.append(entry)
        return entry

    def _add(self, kind: str, key: str, payload: Mapping[str, Any]) -> LedgerEntry:
        return self._append(LedgerEntry(len(self._entries), self.head, kind, key, json.loads(json.dumps(dict(payload), sort_keys=True))))

    def record(self, decision: ScreeningDecision) -> LedgerEntry | None:
        """Record a non-promotion (promotions need no entry here; they continue to the next fidelity)."""
        if decision.outcome is ScreeningOutcome.PROMOTE:
            return None
        kind = "eliminated" if decision.outcome is ScreeningOutcome.ELIMINATE else "rejected_hard"
        return self._add(kind, decision.candidate_key, decision.to_dict())

    def eliminations(self) -> tuple[LedgerEntry, ...]:
        """Eliminations not yet resurrected."""
        resurrected = {(e.candidate_key, e.payload.get("eliminated_at")) for e in self._entries if e.kind == "resurrected"}
        return tuple(e for e in self._entries if e.kind == "eliminated" and (e.candidate_key, e.sequence) not in resurrected)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": LEDGER_SCHEMA, "head": self.head, "entries": [e.to_dict() for e in self._entries]}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any], *, expected_head: str | None = None) -> "EliminationLedger":
        if payload.get("schema") != LEDGER_SCHEMA:
            raise FidelityGraphRefusal("not an elimination ledger")
        entries = []
        for p in payload.get("entries", ()):
            e = LedgerEntry(p["sequence"], p["previous"], p["kind"], p["candidate_key"], p["payload"])
            if e.digest != p["digest"]:
                raise FidelityGraphRefusal(f"ledger entry {p['sequence']} does not match its digest")
            entries.append(e)
        ledger = cls(entries)
        if ledger.head != payload.get("head") or (expected_head is not None and ledger.head != expected_head):
            raise FidelityGraphRefusal("the elimination ledger does not hash to its recorded (or expected) head")
        return ledger


def audit_sample(ledger: EliminationLedger, link: FidelityLink, *, fraction: float, seed: str, strata: int = 3) -> tuple[str, ...]:
    """Candidates eliminated under ``link`` (any version) to re-evaluate at the higher fidelity.

    Deterministic: within each margin stratum (equal-count bins, smallest margins first) the candidates are ordered by
    ``sha256(seed, key)`` and ``ceil(fraction * n)`` are taken -- at least one per non-empty stratum, so the near-threshold
    eliminations are always audited."""
    fraction = float(fraction)
    if not 0 < fraction <= 1:
        raise FidelityGraphRefusal("the audit fraction is in (0, 1]")
    if not str(seed).strip() or strata < 1:
        raise FidelityGraphRefusal("the audit is seeded and stratified")
    elim = sorted((e for e in ledger.eliminations() if e.payload.get("link_id") == link.link_id),
                  key=lambda e: (float(e.payload.get("margin") or 0.0), e.candidate_key))
    if not elim:
        return ()
    bins = [elim[i * len(elim) // strata:(i + 1) * len(elim) // strata] for i in range(strata)]
    chosen: list[str] = []
    for b in bins:
        if not b:
            continue
        ordered = sorted(b, key=lambda e: hashlib.sha256(f"{seed}\n{e.candidate_key}".encode()).hexdigest())
        chosen.extend(e.candidate_key for e in ordered[:max(1, math.ceil(fraction * len(b)))])
    return tuple(sorted(set(chosen)))


@dataclass(frozen=True)
class AuditResult:
    link_id: str
    link_version: int
    audited: int
    false_eliminations: int
    false_elimination_rate: float | None   # None when fewer than min_audits audits: never read as 0
    bound: float
    suspended: bool

    def to_dict(self) -> dict[str, Any]:
        return {"link_id": self.link_id, "link_version": self.link_version, "audited": self.audited,
                "false_eliminations": self.false_eliminations, "false_elimination_rate": self.false_elimination_rate,
                "bound": self.bound, "suspended": self.suspended}


def record_audit(ledger: EliminationLedger, link: FidelityLink, high_values: Mapping[str, float], *, bound: float, min_audits: int,
                 actor: str) -> tuple[FidelityLink, AuditResult]:
    """Score audited eliminations at the higher fidelity; suspend the link when FALSE_ELIMINATION_RATE > bound.

    A false elimination is an eliminated candidate whose HIGH-fidelity value passes the threshold."""
    if not 0 <= float(bound) < 1 or min_audits < 1:
        raise FidelityGraphRefusal("the false-elimination bound is in [0, 1) and min_audits >= 1")
    eliminated = {e.candidate_key: e for e in ledger.eliminations() if e.payload.get("link_id") == link.link_id}
    unknown = sorted(set(high_values) - set(eliminated))
    if unknown:
        raise FidelityGraphRefusal(f"audited candidates {unknown} were not eliminated under link {link.link_id!r}")
    m = link.measurement
    false = 0
    for key, value in sorted(high_values.items()):
        value = float(value)
        if not math.isfinite(value):
            raise FidelityGraphRefusal(f"audit value for {key!r} is not finite; a failed audit run is not an audit")
        passed = m.sense.passes(value, m.threshold)
        false += passed
        ledger._add("audited", key, {"link_id": link.link_id, "link_version": link.version, "high_value": value,
                                     "false_elimination": passed})
    n = len(high_values)
    rate = false / n if n >= min_audits else None
    suspend = rate is not None and rate > float(bound) and link.status is LinkStatus.ADMITTED
    result = AuditResult(link.link_id, link.version, n, false, rate, float(bound), suspend)
    if suspend:
        link = link.suspend(actor=actor, reason=f"false-elimination rate {rate:.4g} exceeds the campaign bound {float(bound):.4g}",
                            detail=result.to_dict())
    else:
        link = replace(link, audit=link.audit + (LinkAuditEvent("audit", actor, "false-elimination audit", result.to_dict()),))
    return link, result


def resurrection_queue(ledger: EliminationLedger, graph: FidelityGraph, *, actor: str) -> tuple[str, ...]:
    """Requeue every elimination made under a link version that no longer stands (suspended, retired, superseded or
    gone).  Appends one 'resurrected' entry per candidate; deterministic order (ledger sequence)."""
    current = {link.link_id: link for link in graph.links}
    out = []
    for e in ledger.eliminations():
        link = current.get(e.payload.get("link_id"))
        stands = link is not None and link.status is LinkStatus.ADMITTED and link.version == e.payload.get("link_version")
        if stands:
            continue
        why = "link gone" if link is None else (f"link {link.status.value}" if link.status is not LinkStatus.ADMITTED
                                                else f"link superseded (v{e.payload.get('link_version')} -> v{link.version})")
        ledger._add("resurrected", e.candidate_key, {"eliminated_at": e.sequence, "link_id": e.payload.get("link_id"),
                                                     "link_version": e.payload.get("link_version"), "reason": why, "actor": actor})
        out.append(e.candidate_key)
    return tuple(out)


__all__ = [
    "AuditResult", "DiscrepancyStatus", "EliminationLedger", "FidelityGraph", "FidelityGraphRefusal", "FidelityLink", "FidelityNode",
    "HardRejection", "LINK_SCHEMA", "LedgerEntry", "LinkAuditEvent", "LinkMeasurement", "LinkStatus", "PairedEvaluation",
    "ScreeningDecision", "ScreeningOutcome", "Sense", "ValidityDomain", "audit_sample", "measure_link", "record_audit",
    "resurrection_queue", "screen",
]
