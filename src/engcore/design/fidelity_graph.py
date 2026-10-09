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
  envelope, near-threshold confusion and the HULL of the measured points.  The
  measurement is computed from the pairs, never declared; the validity domain
  is declared but must lie inside the measured hull.  A link is ADMITTED under a
  :class:`LinkAdmissionPolicy` record, and the admission binds the exact
  measurement, domain and version it judged: any later change un-admits it.

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
    point_hull: Mapping[str, tuple[float, float]] = field(default_factory=dict)  # per-variable [min, max] of the pair points

    def to_dict(self) -> dict[str, Any]:
        return {"pairs": self.pairs, "evaluation_set_digest": self.evaluation_set_digest, "rank_correlation": self.rank_correlation,
                "decision_agreement": self.decision_agreement, "discrepancy_status": self.discrepancy_status.value,
                "discrepancy_mean": self.discrepancy_mean, "discrepancy_std": self.discrepancy_std,
                "discrepancy_envelope": None if self.discrepancy_envelope is None else list(self.discrepancy_envelope),
                "near_threshold_pairs": self.near_threshold_pairs, "near_threshold_confusion": self.near_threshold_confusion,
                "threshold": self.threshold, "sense": self.sense.value, "envelope_k": self.envelope_k, "near_band": self.near_band,
                "point_hull": {k: list(v) for k, v in sorted(self.point_hull.items())}}

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


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
    if isinstance(min_pairs_for_discrepancy, bool) or min_pairs_for_discrepancy < MIN_PAIRS_FLOOR:
        raise FidelityGraphRefusal(f"a discrepancy needs at least {MIN_PAIRS_FLOOR} pairs")
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
    common = set.intersection(*(set(p.point) for p in pairs))
    hull = {k: (min(p.point[k] for p in pairs), max(p.point[k] for p in pairs)) for k in sorted(common)}
    return LinkMeasurement(len(pairs), _digest([p.to_dict() for p in pairs]), rho, agree, status, mean, std, env, len(near),
                           confusion, threshold, sense, envelope_k, near_band, hull)


#: absolute floor on the pairs behind any quantified discrepancy (a policy may require more, never less)
MIN_PAIRS_FLOOR = 10


@dataclass(frozen=True)
class LinkAdmissionPolicy:
    """The floors a link must meet to be admitted for elimination.  A record, so admissions say what they were held to."""

    policy_id: str
    min_pairs: int
    min_rank_correlation: float
    min_decision_agreement: float
    max_near_threshold_confusion: float | None = None   # None: no near-threshold requirement beyond the envelope

    def __post_init__(self) -> None:
        if not str(self.policy_id).strip():
            raise FidelityGraphRefusal("an admission policy has an id")
        if isinstance(self.min_pairs, bool) or self.min_pairs < MIN_PAIRS_FLOOR:
            raise FidelityGraphRefusal(f"an admission policy requires at least {MIN_PAIRS_FLOOR} pairs")
        if not (-1 <= float(self.min_rank_correlation) <= 1 and 0 <= float(self.min_decision_agreement) <= 1):
            raise FidelityGraphRefusal("correlation floor in [-1, 1]; agreement floor in [0, 1]")

    def to_dict(self) -> dict[str, Any]:
        return {"policy_id": self.policy_id, "min_pairs": self.min_pairs, "min_rank_correlation": self.min_rank_correlation,
                "min_decision_agreement": self.min_decision_agreement, "max_near_threshold_confusion": self.max_near_threshold_confusion}

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


# ---------------------------------------------------------------------------- links


class LinkStatus(str, Enum):
    MEASURED = "measured"      # measured, not admitted: may not eliminate
    ADMITTED = "admitted"      # may eliminate inside its domain
    SUSPENDED = "suspended"    # an audit (or an authority) withdrew it: its eliminations are resurrectable
    RETIRED = "retired"


_STATUS_ACTIONS = ("measured", "admitted", "suspended", "retired")


@dataclass(frozen=True)
class LinkAuditEvent:
    action: str                # "measured", "admitted", "audit", "suspended", "retired"
    actor: str
    reason: str
    detail: Mapping[str, Any] = field(default_factory=dict, hash=False)

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
        hull = self.measurement.point_hull
        for var, (lo, hi) in self.domain.bounds.items():
            if var not in hull or lo < hull[var][0] or hi > hull[var][1]:
                raise FidelityGraphRefusal(f"the validity domain on {var!r} [{lo}, {hi}] exceeds what the link was measured on "
                                           f"{list(hull.get(var, ())) or '(never varied)'}; a domain is not declared wider than the data")
        status_events = [e for e in self.audit if e.action in _STATUS_ACTIONS]
        if self.status is LinkStatus.ADMITTED:
            last = status_events[-1] if status_events else None
            ok = (last is not None and last.action == "admitted"
                  and last.detail.get("measurement_digest") == self.measurement.digest
                  and last.detail.get("domain_digest") == _digest(self.domain.to_dict())
                  and last.detail.get("version") == self.version)
            if not ok:
                raise FidelityGraphRefusal("an ADMITTED link's last status event is the admission of THIS measurement, domain and "
                                           "version; admission is not a field to set or carry over")
            if self.measurement.discrepancy_status is not DiscrepancyStatus.QUANTIFIED:
                raise FidelityGraphRefusal("an ADMITTED link has a QUANTIFIED discrepancy")
        elif self.status is not LinkStatus.MEASURED and not any(e.action == "admitted" for e in status_events):
            raise FidelityGraphRefusal(f"a {self.status.value} link records its admission in the audit history")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": LINK_SCHEMA, "link_id": self.link_id, "low": self.low.to_dict(), "high": self.high.to_dict(),
                "observable": self.observable, "unit": self.unit, "domain": self.domain.to_dict(),
                "measurement": self.measurement.to_dict(), "version": self.version, "status": self.status.value,
                "audit": [e.to_dict() for e in self.audit]}

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())

    @property
    def standing_digest(self) -> str:
        """What an elimination stood on: link id, version, measurement and domain.  Audit notes do not change it."""
        return _digest({"link_id": self.link_id, "version": self.version, "measurement": self.measurement.digest,
                        "domain": _digest(self.domain.to_dict()), "low": self.low.node_id, "high": self.high.node_id})

    def admit(self, policy: LinkAdmissionPolicy, *, actor: str, reason: str) -> "FidelityLink":
        """Admit the link for elimination under ``policy``.  The admission binds this measurement, domain and version."""
        if not isinstance(policy, LinkAdmissionPolicy):
            raise FidelityGraphRefusal("admission is held to a LinkAdmissionPolicy record")
        if not str(actor).strip() or not str(reason).strip():
            raise FidelityGraphRefusal("admission names its actor and reason")
        if self.status is not LinkStatus.MEASURED:
            raise FidelityGraphRefusal(f"only a MEASURED link is admitted (this one is {self.status.value}); re-measure to re-admit")
        m = self.measurement
        if m.pairs < policy.min_pairs:
            raise FidelityGraphRefusal(f"the link was measured on {m.pairs} pairs; the policy requires {policy.min_pairs}")
        if m.discrepancy_status is not DiscrepancyStatus.QUANTIFIED:
            raise FidelityGraphRefusal("the link's discrepancy is UNKNOWN; it cannot be admitted to eliminate")
        if m.rank_correlation is None or m.rank_correlation < policy.min_rank_correlation:
            raise FidelityGraphRefusal(f"rank correlation {m.rank_correlation} is below the policy's {policy.min_rank_correlation}")
        if m.decision_agreement < policy.min_decision_agreement:
            raise FidelityGraphRefusal(f"decision agreement {m.decision_agreement} is below the policy's {policy.min_decision_agreement}")
        if policy.max_near_threshold_confusion is not None and (m.near_threshold_confusion is None
                                                               or m.near_threshold_confusion > policy.max_near_threshold_confusion):
            raise FidelityGraphRefusal("near-threshold confusion is unmeasured or above the policy's bound")
        detail = {"measurement_digest": m.digest, "domain_digest": _digest(self.domain.to_dict()), "version": self.version + 1,
                  "policy": policy.to_dict(), "policy_digest": policy.digest}
        return replace(self, version=self.version + 1, status=LinkStatus.ADMITTED,
                       audit=self.audit + (LinkAuditEvent("admitted", actor, reason, detail),))

    def suspend(self, *, actor: str, reason: str, detail: Mapping[str, Any] | None = None) -> "FidelityLink":
        if self.status is not LinkStatus.ADMITTED:
            raise FidelityGraphRefusal("only an ADMITTED link is suspended")
        return replace(self, version=self.version + 1, status=LinkStatus.SUSPENDED,
                       audit=self.audit + (LinkAuditEvent("suspended", actor, reason, dict(detail or {})),))

    def retire(self, *, actor: str, reason: str) -> "FidelityLink":
        return replace(self, version=self.version + 1, status=LinkStatus.RETIRED,
                       audit=self.audit + (LinkAuditEvent("retired", actor, reason),))

    def remeasured(self, measurement: LinkMeasurement, *, actor: str, reason: str,
                   domain: ValidityDomain | None = None) -> "FidelityLink":
        """A new version measured on a NEW evaluation set; it starts MEASURED (re-admission is a fresh decision)."""
        used = {self.measurement.evaluation_set_digest} | {e.detail.get("evaluation_set_digest") for e in self.audit
                                                             if e.action == "measured"}
        if measurement.evaluation_set_digest in used:
            raise FidelityGraphRefusal("re-measurement needs a new evaluation set; the same pairs cannot re-admit a link they "
                                       "already admitted or that an audit suspended")
        event = LinkAuditEvent("measured", actor, reason, {"evaluation_set_digest": measurement.evaluation_set_digest})
        return replace(self, version=self.version + 1, status=LinkStatus.MEASURED, measurement=measurement,
                       domain=domain or self.domain, audit=self.audit + (event,))


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
    REJECT_HARD = "reject_hard"    # logical/physical constraint on the INPUTS, or exact duplicate: needs no link


class HardRejection(str, Enum):
    LOGICAL_CONSTRAINT = "logical_constraint"
    PHYSICAL_CONSTRAINT = "physical_constraint"
    EXACT_DUPLICATE = "exact_duplicate"


@dataclass(frozen=True)
class HardRejectionBasis:
    """Why a candidate is rejected without any model: a versioned constraint judged on the candidate's INPUTS only, or the
    exact duplicate it repeats.  A constraint judged on a model output is not a hard rejection: it goes through a link."""

    kind: HardRejection
    basis_ref: str                 # "constraint_id@version" or the duplicated candidate key
    reason: str
    judged_on_inputs_only: bool = False
    duplicate_digest: str = ""     # for EXACT_DUPLICATE: the content digest both candidates share

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", HardRejection(self.kind))
        if not str(self.basis_ref).strip() or not str(self.reason).strip():
            raise FidelityGraphRefusal("a hard rejection names its basis and reason")
        if self.kind is HardRejection.EXACT_DUPLICATE:
            if len(str(self.duplicate_digest)) != 64:
                raise FidelityGraphRefusal("an exact-duplicate rejection names the shared content digest")
        else:
            if self.judged_on_inputs_only is not True:
                raise FidelityGraphRefusal("a hard constraint is judged on the candidate's inputs only; a constraint judged on a "
                                           "model output is a cheap-model elimination and needs an admitted link")
            if "@" not in self.basis_ref:
                raise FidelityGraphRefusal("a constraint basis is versioned: 'constraint_id@version'")

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "basis_ref": self.basis_ref, "reason": self.reason,
                "judged_on_inputs_only": self.judged_on_inputs_only, "duplicate_digest": self.duplicate_digest}


@dataclass(frozen=True)
class ScreeningDecision:
    candidate_key: str
    outcome: ScreeningOutcome
    reason: str
    link_id: str = ""
    link_version: int = 0
    standing_digest: str = ""
    margin: float | None = None    # distance of the optimistic bound beyond the threshold (eliminations)
    low_value: float | None = None
    point: Mapping[str, float] = field(default_factory=dict, hash=False)
    threshold: float | None = None
    sense: str = ""
    hard: HardRejectionBasis | None = None
    classification: str = "scheduling_decision_not_evidence"

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcome", ScreeningOutcome(self.outcome))
        if not str(self.candidate_key).strip():
            raise FidelityGraphRefusal("a screening decision names its candidate")
        if self.outcome is ScreeningOutcome.ELIMINATE:
            if not (self.link_id and self.link_version >= 1 and len(self.standing_digest) == 64 and self.margin is not None
                    and self.margin > 0 and self.low_value is not None and self.threshold is not None and self.sense):
                raise FidelityGraphRefusal("an elimination names its link standing, low value, threshold and a positive margin")
        if self.outcome is ScreeningOutcome.REJECT_HARD and not isinstance(self.hard, HardRejectionBasis):
            raise FidelityGraphRefusal("a hard rejection carries its HardRejectionBasis")

    def to_dict(self) -> dict[str, Any]:
        return {"candidate_key": self.candidate_key, "outcome": self.outcome.value, "reason": self.reason, "link_id": self.link_id,
                "link_version": self.link_version, "standing_digest": self.standing_digest, "margin": self.margin,
                "low_value": self.low_value, "point": dict(self.point), "threshold": self.threshold, "sense": self.sense,
                "hard": None if self.hard is None else self.hard.to_dict(), "classification": self.classification}


def screen(candidate_key: str, *, low_value: float | None, point: Mapping[str, float], link: FidelityLink | None,
           low_node: FidelityNode | None = None, observable: str = "",
           hard_rejection: HardRejectionBasis | None = None) -> ScreeningDecision:
    """Decide PROMOTE / ELIMINATE / REJECT_HARD for one candidate screened at the low fidelity.

    With a link, ``low_node`` and ``observable`` must be the link's: a value from another realization or another
    observable is not what the link measured."""
    point = {str(k): float(v) for k, v in dict(point).items()}
    if hard_rejection is not None:
        if not isinstance(hard_rejection, HardRejectionBasis):
            raise FidelityGraphRefusal("a hard rejection is a HardRejectionBasis")
        return ScreeningDecision(candidate_key, ScreeningOutcome.REJECT_HARD, hard_rejection.reason, point=point, hard=hard_rejection)
    if link is None:
        return ScreeningDecision(candidate_key, ScreeningOutcome.PROMOTE, "no fidelity link: a cheap result only prioritizes",
                                 low_value=low_value, point=point)
    if low_node is None or low_node.node_id != link.low.node_id or observable != link.observable:
        raise FidelityGraphRefusal("the screened value must come from the link's low realization and observable")
    ident = dict(link_id=link.link_id, link_version=link.version, standing_digest=link.standing_digest, point=point)
    if low_value is None or not math.isfinite(float(low_value)):
        return ScreeningDecision(candidate_key, ScreeningOutcome.PROMOTE, "no finite low-fidelity value: promote, never eliminate", **ident)
    low_value = float(low_value)
    if link.status is not LinkStatus.ADMITTED:
        return ScreeningDecision(candidate_key, ScreeningOutcome.PROMOTE, f"link is {link.status.value}, not admitted: promote",
                                 low_value=low_value, **ident)
    if not link.domain.contains(point):
        return ScreeningDecision(candidate_key, ScreeningOutcome.PROMOTE, "outside the link's validity domain: promote",
                                 low_value=low_value, **ident)
    m = link.measurement
    if m.discrepancy_status is not DiscrepancyStatus.QUANTIFIED or m.discrepancy_envelope is None:
        return ScreeningDecision(candidate_key, ScreeningOutcome.PROMOTE, "discrepancy UNKNOWN: promote", low_value=low_value, **ident)
    lo, hi = m.discrepancy_envelope
    if m.sense is Sense.AT_MOST:
        optimistic = low_value + lo          # the smallest the high-fidelity value can plausibly be
        margin = optimistic - m.threshold
    else:
        optimistic = low_value + hi
        margin = m.threshold - optimistic
    common = dict(low_value=low_value, threshold=m.threshold, sense=m.sense.value, **ident)
    if margin > 0:
        return ScreeningDecision(candidate_key, ScreeningOutcome.ELIMINATE,
                                 f"even the optimistic high-fidelity bound {optimistic:.6g} fails the threshold {m.threshold:.6g}",
                                 margin=margin, **common)
    return ScreeningDecision(candidate_key, ScreeningOutcome.PROMOTE, "the discrepancy envelope admits a pass: promote",
                             margin=margin, **common)


# ---------------------------------------------------------------------------- ledger, audit, resurrection


@dataclass(frozen=True)
class LedgerEntry:
    sequence: int
    previous: str
    kind: str                       # "eliminated" | "rejected_hard" | "resurrected" | "audit_drawn" | "audited"
    candidate_key: str
    payload_json: str               # canonical JSON: an entry cannot be edited in place

    @property
    def payload(self) -> dict[str, Any]:
        return json.loads(self.payload_json)

    @property
    def digest(self) -> str:
        return _digest({"sequence": self.sequence, "previous": self.previous, "kind": self.kind, "candidate_key": self.candidate_key,
                        "payload": json.loads(self.payload_json)})

    def to_dict(self) -> dict[str, Any]:
        return {"sequence": self.sequence, "previous": self.previous, "kind": self.kind, "candidate_key": self.candidate_key,
                "payload": self.payload, "digest": self.digest}


_LEDGER_KINDS = ("eliminated", "rejected_hard", "resurrected", "audit_drawn", "audited")


class EliminationLedger:
    """Append-only, hash-chained record of every non-promotion, audit and resurrection.

    A ledger is a record, not a security boundary: in-process code can always build entries by hand.  Its job is to make
    every elimination traceable and every edit detectable when it is read back against an expected head."""

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
        if entry.kind not in _LEDGER_KINDS:
            raise FidelityGraphRefusal(f"unknown ledger entry kind {entry.kind!r}")
        if entry.sequence != len(self._entries) or entry.previous != self.head:
            raise FidelityGraphRefusal("ledger entry does not extend the head; the ledger is not rewritten")
        self._entries.append(entry)
        return entry

    def _add(self, kind: str, key: str, payload: Mapping[str, Any]) -> LedgerEntry:
        return self._append(LedgerEntry(len(self._entries), self.head, kind, key, json.dumps(dict(payload), sort_keys=True)))

    def standing(self) -> dict[str, LedgerEntry]:
        """Candidate -> its standing non-promotion entry (eliminated or rejected and not resurrected)."""
        out: dict[str, LedgerEntry] = {}
        for e in self._entries:
            if e.kind in ("eliminated", "rejected_hard"):
                out[e.candidate_key] = e
            elif e.kind == "resurrected" and out.get(e.candidate_key) is not None \
                    and out[e.candidate_key].sequence == e.payload.get("eliminated_at"):
                del out[e.candidate_key]
        return out

    def record(self, decision: ScreeningDecision, *, link: FidelityLink | None = None, low_node: FidelityNode | None = None) -> LedgerEntry | None:
        """Record a non-promotion.  An elimination is RE-SCREENED against ``link`` and refused unless it reproduces exactly;
        a candidate that already stands eliminated or rejected is not recorded twice."""
        if not isinstance(decision, ScreeningDecision):
            raise FidelityGraphRefusal("the ledger records ScreeningDecision records")
        if decision.outcome is ScreeningOutcome.PROMOTE:
            return None
        if decision.candidate_key in self.standing():
            raise FidelityGraphRefusal(f"{decision.candidate_key!r} already stands eliminated/rejected")
        if decision.outcome is ScreeningOutcome.ELIMINATE:
            if link is None:
                raise FidelityGraphRefusal("an elimination is recorded against the link it claims")
            again = screen(decision.candidate_key, low_value=decision.low_value, point=decision.point, link=link,
                           low_node=low_node, observable=link.observable)
            if again.to_dict() != decision.to_dict():
                raise FidelityGraphRefusal("the elimination does not reproduce under the link it names; it is not recorded")
            return self._add("eliminated", decision.candidate_key, decision.to_dict())
        return self._add("rejected_hard", decision.candidate_key, decision.to_dict())

    def eliminations(self) -> tuple[LedgerEntry, ...]:
        """Standing eliminations (not hard rejections), in ledger order."""
        return tuple(sorted((e for e in self.standing().values() if e.kind == "eliminated"), key=lambda e: e.sequence))

    def resurrect(self, entry: LedgerEntry, *, reason: str, actor: str) -> LedgerEntry:
        if self.standing().get(entry.candidate_key) != entry:
            raise FidelityGraphRefusal("only a standing elimination or rejection is resurrected")
        return self._add("resurrected", entry.candidate_key, {"eliminated_at": entry.sequence, "reason": reason, "actor": actor,
                                                              "link_id": entry.payload.get("link_id"),
                                                              "link_version": entry.payload.get("link_version")})

    def to_dict(self) -> dict[str, Any]:
        return {"schema": LEDGER_SCHEMA, "head": self.head, "entries": [e.to_dict() for e in self._entries]}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any], *, expected_head: str | None) -> "EliminationLedger":
        """Rebuild and verify.  ``expected_head`` is required (pass ``None`` only to inspect an unanchored copy)."""
        if payload.get("schema") != LEDGER_SCHEMA:
            raise FidelityGraphRefusal("not an elimination ledger")
        entries = []
        for p in payload.get("entries", ()):
            e = LedgerEntry(p["sequence"], p["previous"], p["kind"], p["candidate_key"], json.dumps(p["payload"], sort_keys=True))
            if e.digest != p["digest"]:
                raise FidelityGraphRefusal(f"ledger entry {p['sequence']} does not match its digest")
            entries.append(e)
        ledger = cls(entries)
        if ledger.head != payload.get("head") or (expected_head is not None and ledger.head != expected_head):
            raise FidelityGraphRefusal("the elimination ledger does not hash to its recorded (or expected) head")
        return ledger


@dataclass(frozen=True)
class FalseEliminationPolicy:
    """The campaign's audit contract: what fraction is audited, how it is stratified, and when a link is suspended."""

    policy_id: str
    fraction: float
    strata: int
    bound: float
    min_audits: int

    def __post_init__(self) -> None:
        if not str(self.policy_id).strip():
            raise FidelityGraphRefusal("an audit policy has an id")
        if not (0 < float(self.fraction) <= 1 and 0 <= float(self.bound) < 1 and int(self.strata) >= 1 and int(self.min_audits) >= 1):
            raise FidelityGraphRefusal("fraction in (0,1], bound in [0,1), strata >= 1, min_audits >= 1")

    def to_dict(self) -> dict[str, Any]:
        return {"policy_id": self.policy_id, "fraction": self.fraction, "strata": self.strata, "bound": self.bound,
                "min_audits": self.min_audits}

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


def _pending_draw(ledger: EliminationLedger, link: FidelityLink) -> LedgerEntry | None:
    recorded = {e.payload.get("draw") for e in ledger.entries if e.kind == "audited"}
    draws = [e for e in ledger.entries if e.kind == "audit_drawn" and e.payload.get("standing_digest") == link.standing_digest
             and e.sequence not in recorded]
    return draws[-1] if draws else None


def draw_audit(ledger: EliminationLedger, link: FidelityLink, policy: FalseEliminationPolicy) -> tuple[str, ...]:
    """Draw (and RECORD) the audit sample for ``link``'s current standing: margin-stratified, seeded by the ledger head and the
    link standing (no caller-chosen seed), at least one per non-empty stratum.  One pending draw per standing."""
    if not isinstance(policy, FalseEliminationPolicy):
        raise FidelityGraphRefusal("the audit is held to a FalseEliminationPolicy")
    if _pending_draw(ledger, link) is not None:
        raise FidelityGraphRefusal("an audit draw for this link standing is still pending; record it before drawing again")
    elim = sorted((e for e in ledger.eliminations() if e.payload.get("standing_digest") == link.standing_digest),
                  key=lambda e: (float(e.payload["margin"]), e.candidate_key))
    if not elim:
        return ()
    seed = _digest({"ledger_head": ledger.head, "standing": link.standing_digest})
    bins = [elim[i * len(elim) // policy.strata:(i + 1) * len(elim) // policy.strata] for i in range(policy.strata)]
    chosen: list[str] = []
    for b in bins:
        if not b:
            continue
        ordered = sorted(b, key=lambda e: hashlib.sha256(f"{seed}\n{e.candidate_key}".encode()).hexdigest())
        chosen.extend(e.candidate_key for e in ordered[:max(1, math.ceil(policy.fraction * len(b)))])
    keys = tuple(sorted(set(chosen)))
    ledger._add("audit_drawn", "", {"standing_digest": link.standing_digest, "link_id": link.link_id, "keys": list(keys),
                                    "seed": seed, "policy": policy.to_dict()})
    return keys


@dataclass(frozen=True)
class AuditResult:
    link_id: str
    link_version: int
    audited: int                           # cumulative, for this link standing
    false_eliminations: int
    false_elimination_rate: float | None   # None when fewer than min_audits audits: never read as 0
    bound: float
    suspended: bool
    resurrected: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"link_id": self.link_id, "link_version": self.link_version, "audited": self.audited,
                "false_eliminations": self.false_eliminations, "false_elimination_rate": self.false_elimination_rate,
                "bound": self.bound, "suspended": self.suspended, "resurrected": list(self.resurrected)}


def record_audit(ledger: EliminationLedger, link: FidelityLink, high_values: Mapping[str, float], policy: FalseEliminationPolicy, *,
                 actor: str) -> tuple[FidelityLink, AuditResult]:
    """Score the PENDING draw at the higher fidelity.  ``high_values`` must cover exactly the drawn keys.

    A false elimination (the high-fidelity value passes the threshold the candidate was eliminated against) is resurrected
    at once.  The FALSE_ELIMINATION_RATE is cumulative over every audit of this link standing; above the policy bound the
    link is suspended (and every elimination under it becomes resurrectable)."""
    draw = _pending_draw(ledger, link)
    if draw is None:
        raise FidelityGraphRefusal("no pending audit draw for this link standing; draw_audit chooses what is audited")
    keys = set(draw.payload["keys"])
    if set(high_values) != keys:
        raise FidelityGraphRefusal(f"the audit must score exactly the drawn sample (missing {sorted(keys - set(high_values))}, "
                                   f"extra {sorted(set(high_values) - keys)})")
    values = {}
    for key, value in high_values.items():
        value = float(value)
        if not math.isfinite(value):
            raise FidelityGraphRefusal(f"audit value for {key!r} is not finite; a failed audit run is not an audit")
        values[key] = value
    standing = ledger.standing()
    resurrected = []
    for key in sorted(values):
        entry = standing[key]
        sense = Sense(entry.payload["sense"])
        passed = sense.passes(values[key], float(entry.payload["threshold"]))   # the threshold it was ELIMINATED against
        ledger._add("audited", key, {"draw": draw.sequence, "standing_digest": link.standing_digest, "high_value": values[key],
                                     "false_elimination": passed})
        if passed:
            ledger.resurrect(entry, reason="the false-elimination audit found it passing at the higher fidelity", actor=actor)
            resurrected.append(key)
    audited = [e for e in ledger.entries if e.kind == "audited" and e.payload.get("standing_digest") == link.standing_digest]
    n = len(audited)
    false = sum(1 for e in audited if e.payload.get("false_elimination"))
    rate = false / n if n >= policy.min_audits else None
    suspend = rate is not None and rate > policy.bound and link.status is LinkStatus.ADMITTED
    result = AuditResult(link.link_id, link.version, n, false, rate, policy.bound, suspend, tuple(resurrected))
    if suspend:
        link = link.suspend(actor=actor, reason=f"false-elimination rate {rate:.4g} exceeds the campaign bound {policy.bound:.4g}",
                            detail={**result.to_dict(), "policy": policy.to_dict()})
    else:
        link = replace(link, audit=link.audit + (LinkAuditEvent("audit", actor, "false-elimination audit",
                                                                {**result.to_dict(), "policy": policy.to_dict()}),))
    return link, result


def resurrection_queue(ledger: EliminationLedger, graph: FidelityGraph, *, actor: str,
                       constraint_versions: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Requeue every elimination whose link standing no longer stands (suspended, retired, re-measured or gone), and every
    hard constraint rejection whose constraint version changed.  One 'resurrected' entry each; ledger order."""
    current = {link.link_id: link for link in graph.links}
    versions = dict(constraint_versions or {})
    out = []
    for key, e in sorted(ledger.standing().items(), key=lambda kv: kv[1].sequence):
        p = e.payload
        if e.kind == "eliminated":
            link = current.get(p.get("link_id"))
            if link is not None and link.status is LinkStatus.ADMITTED and link.standing_digest == p.get("standing_digest"):
                continue
            why = "link gone" if link is None else (f"link {link.status.value}" if link.status is not LinkStatus.ADMITTED
                                                    else "link re-measured / re-admitted under another standing")
        else:
            hard = p.get("hard") or {}
            if hard.get("kind") == HardRejection.EXACT_DUPLICATE.value:
                continue
            cid, _, ver = str(hard.get("basis_ref", "")).partition("@")
            if cid not in versions or versions[cid] == ver:
                continue
            why = f"constraint {cid} changed from version {ver} to {versions[cid]}"
        ledger.resurrect(e, reason=why, actor=actor)
        out.append(key)
    return tuple(out)


__all__ = [
    "AuditResult", "DiscrepancyStatus", "EliminationLedger", "FalseEliminationPolicy", "FidelityGraph", "FidelityGraphRefusal",
    "FidelityLink", "FidelityNode", "HardRejection", "HardRejectionBasis", "LINK_SCHEMA", "LedgerEntry", "LinkAdmissionPolicy",
    "LinkAuditEvent", "LinkMeasurement", "LinkStatus", "MIN_PAIRS_FLOOR", "PairedEvaluation", "ScreeningDecision",
    "ScreeningOutcome", "Sense", "ValidityDomain", "draw_audit", "measure_link", "record_audit", "resurrection_queue", "screen",
]
