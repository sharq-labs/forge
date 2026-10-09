"""Credibility vectors on the EXISTING evidence graph: what a claim has, what a decision needs, and the gap.

Nothing here is new evidence.  Every factor level is EARNED from :class:`~engcore.credibility.evidence_graph.EvidenceNode`
records of one :class:`~engcore.credibility.evidence_graph.EvidenceGraph`:

* ``f(C)`` -- the factor vector of a claim.  A :class:`FactorClaim` names a factor, a level and the graph nodes that
  back it; the level counts only if every node exists, is bound to the decision's context (``node.applicability``),
  has an authority admissible for that factor and level (an experiment for experimental validation; cross-solver
  agreement is never validation), and is not superseded.  A factor nobody earned is UNKNOWN, which is below every
  level and never satisfies a requirement.  The vector is computed from SUPPORTING evidence only, so removing evidence
  can never raise it.
* ``r(D)`` -- the required vector of a decision, set ONLY by a risk policy (:data:`RISK_POLICY_V1` or a declared one).
  The policy sets the bar; it is never evidence and never raises ``f``.
* ``g = r - f`` -- per factor, in ordinal steps; an UNKNOWN factor's gap is ``required + 1`` and is flagged unknown.
* Defeaters -- a CONTRADICTS edge from an admissible, non-superseded node into supporting evidence, or an explicit
  :class:`Defeater` (a REFUTED falsifier verdict, a FALSIFIED red-team envelope).  An open defeater blocks the decision
  whatever the gap.
* The dominant blocking gap -- an open defeater first, then the largest gap (ties broken by :data:`FACTOR_PRIORITY`),
  mapped onto the existing :class:`~engcore.claims.gaps.GapClass` vocabulary so ``claims.next_experiment`` can plan it.

Propagation over a claim structure (:class:`ClaimNode`): AND takes the WEAKEST child per factor; OR takes the STRONGER
child per factor only when the children's evidence is independent in the graph (no shared node, no shared lineage
ancestor through DERIVED_FROM / REPLICATES / CALIBRATES); otherwise OR is treated like AND.  Independence is computed
from the graph, never asserted.

Residual (deferred hardening): a defeater is a node in the graph; a graph from which the contradicting node was deleted
is a different graph (its digest is bound into the report), but this module cannot know a node is missing.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from ..credibility.evidence_graph import EvidenceAuthority, EvidenceGraph, EvidenceRelation, evidence_graph_fingerprint
from .gaps import GapClass

CREDIBILITY_VECTOR_SCHEMA = "engcore.claims.credibility_vector/1"
UNKNOWN = -1


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class CredibilityRefused(ValueError):
    pass


class Factor(str, Enum):
    APPLICABILITY = "applicability"
    VERIFICATION = "verification"
    VALIDATION = "validation"
    NUMERICAL_UQ = "numerical_uq"
    PARAMETER_UQ = "parameter_uq"
    MEASUREMENT_UQ = "measurement_uq"
    MODEL_FORM_UQ = "model_form_uq"
    INDEPENDENT_ROUTES = "independent_routes"
    ADVERSARIAL = "adversarial"


#: ordinal level names per factor (index = level).  UNKNOWN (-1) is below all of them.
LEVELS: Mapping[Factor, tuple[str, ...]] = {
    Factor.APPLICABILITY: ("outside_domain", "inside_domain"),
    Factor.VERIFICATION: ("none", "solution_verified", "code_and_solution_verified"),
    Factor.VALIDATION: ("none", "benchmark", "experimental"),
    Factor.NUMERICAL_UQ: ("declared", "quantified"),
    Factor.PARAMETER_UQ: ("declared", "quantified"),
    Factor.MEASUREMENT_UQ: ("declared", "quantified"),
    Factor.MODEL_FORM_UQ: ("declared", "quantified"),
    Factor.INDEPENDENT_ROUTES: ("none", "one", "two_or_more"),
    Factor.ADVERSARIAL: ("not_attacked", "survived_declared_attack"),
}

FACTOR_PRIORITY = (Factor.APPLICABILITY, Factor.VERIFICATION, Factor.VALIDATION, Factor.MODEL_FORM_UQ, Factor.NUMERICAL_UQ,
                   Factor.PARAMETER_UQ, Factor.MEASUREMENT_UQ, Factor.INDEPENDENT_ROUTES, Factor.ADVERSARIAL)

#: the existing gap vocabulary each factor's shortfall is
FACTOR_GAP: Mapping[Factor, GapClass] = {
    Factor.APPLICABILITY: GapClass.MODEL_APPLICABILITY_UNKNOWN, Factor.VERIFICATION: GapClass.CHECK_NOT_RUN,
    Factor.VALIDATION: GapClass.VALIDATION_LEVEL_MISSING, Factor.NUMERICAL_UQ: GapClass.NUMERICAL_UQ_MISSING,
    Factor.PARAMETER_UQ: GapClass.PARAMETER_UQ_MISSING, Factor.MEASUREMENT_UQ: GapClass.MEASUREMENT_UQ_MISSING,
    Factor.MODEL_FORM_UQ: GapClass.MODEL_FORM_UNCERTAINTY_UNKNOWN, Factor.INDEPENDENT_ROUTES: GapClass.INDEPENDENT_ROUTE_MISSING,
    Factor.ADVERSARIAL: GapClass.ASSURANCE_OBLIGATION_UNMET,
}

_A = EvidenceAuthority
_COMPUTED = frozenset({_A.SIMULATION, _A.ANALYTICAL})
_EXTERNAL_REFERENCE = frozenset({_A.REFERENCE_DATA, _A.STANDARD, _A.PEER_REVIEWED, _A.OFFICIAL_DATA})
_MEASURED = frozenset({_A.MEASUREMENT, _A.EXPERIMENT})
_KNOWN = frozenset(_A) - {_A.UNKNOWN}


def _admissible(factor: Factor, level: int) -> frozenset[EvidenceAuthority]:
    """Which authorities can earn ``level`` of ``factor``.  Validation needs something outside the model: an external
    reference for a benchmark, a measurement or experiment for experimental validation."""
    if factor is Factor.VALIDATION:
        return {0: _KNOWN, 1: _EXTERNAL_REFERENCE | _MEASURED, 2: _MEASURED}[level]
    if factor is Factor.VERIFICATION:
        return _KNOWN if level == 0 else _COMPUTED | _EXTERNAL_REFERENCE
    if factor in (Factor.INDEPENDENT_ROUTES, Factor.ADVERSARIAL):
        return _KNOWN if level == 0 else _COMPUTED
    if factor is Factor.MEASUREMENT_UQ and level == 1:
        return _MEASURED | _EXTERNAL_REFERENCE
    return _KNOWN


@dataclass(frozen=True)
class FactorClaim:
    factor: Factor
    level: int
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "factor", Factor(self.factor))
        object.__setattr__(self, "evidence_ids", tuple(sorted(set(self.evidence_ids))))
        if isinstance(self.level, bool) or not isinstance(self.level, int) or not 0 <= self.level < len(LEVELS[self.factor]):
            raise CredibilityRefused(f"{self.factor.value} levels are 0..{len(LEVELS[self.factor]) - 1} ({LEVELS[self.factor]})")
        if not self.evidence_ids:
            raise CredibilityRefused("a factor level names the graph evidence that earns it; a level is never asserted")


@dataclass(frozen=True)
class Defeater:
    defeater_id: str
    kind: str                       # e.g. "falsifier_refuted", "red_team_falsified", "contradiction"
    evidence_ids: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"defeater_id": self.defeater_id, "kind": self.kind, "evidence_ids": list(self.evidence_ids), "reason": self.reason}


# ---------------------------------------------------------------------------- the graph view


class _GraphView:
    def __init__(self, graph: EvidenceGraph, context_digest: str) -> None:
        self.graph = graph
        self.context = context_digest
        self.nodes = {n.evidence_id: n for n in graph.nodes}
        self.superseded = {e.target_id for e in graph.edges if e.relation is EvidenceRelation.SUPERSEDES}
        self._parents: dict[str, set[str]] = {}
        for e in graph.edges:
            if e.relation in (EvidenceRelation.DERIVED_FROM, EvidenceRelation.REPLICATES, EvidenceRelation.CALIBRATES):
                self._parents.setdefault(e.source_id, set()).add(e.target_id)

    def usable(self, evidence_id: str, factor: Factor, level: int) -> str | None:
        """None when the node may back this level; otherwise why not."""
        node = self.nodes.get(evidence_id)
        if node is None:
            return f"{evidence_id} is not in the evidence graph"
        if evidence_id in self.superseded:
            return f"{evidence_id} is superseded"
        if node.applicability != self.context:
            return f"{evidence_id} is bound to another context than the decision's"
        if node.authority not in _admissible(factor, level):
            return f"{evidence_id} ({node.authority.value}) cannot earn {factor.value}={LEVELS[factor][level]}"
        return None

    def lineage(self, evidence_id: str) -> set[str]:
        seen, todo = set(), [evidence_id]
        while todo:
            x = todo.pop()
            if x in seen:
                continue
            seen.add(x)
            todo.extend(self._parents.get(x, ()))
        return seen

    def contradictions_of(self, ids: set[str]) -> list[Defeater]:
        out = []
        for e in self.graph.edges:
            if e.relation is EvidenceRelation.CONTRADICTS and e.target_id in ids and e.source_id not in self.superseded:
                src = self.nodes[e.source_id]
                if src.authority is not EvidenceAuthority.UNKNOWN:
                    out.append(Defeater(f"contradiction:{e.source_id}->{e.target_id}", "contradiction", (e.source_id, e.target_id),
                                        f"{e.source_id} ({src.authority.value}) contradicts supporting evidence {e.target_id}"))
        return out


# ---------------------------------------------------------------------------- vectors


@dataclass(frozen=True)
class FactorVector:
    levels: Mapping[Factor, int] = field(hash=False)
    support: Mapping[Factor, tuple[str, ...]] = field(hash=False)
    rejected: tuple[str, ...] = ()

    def level(self, factor: Factor) -> int:
        return self.levels.get(factor, UNKNOWN)

    def to_dict(self) -> dict[str, Any]:
        return {"levels": {f.value: (LEVELS[f][lv] if lv >= 0 else "UNKNOWN") for f, lv in sorted(self.levels.items(), key=lambda kv: kv[0].value)},
                "support": {f.value: list(ids) for f, ids in sorted(self.support.items(), key=lambda kv: kv[0].value)},
                "rejected": list(self.rejected)}


def _leaf_vector(claims: tuple[FactorClaim, ...], view: _GraphView) -> FactorVector:
    levels: dict[Factor, int] = {f: UNKNOWN for f in Factor}
    support: dict[Factor, tuple[str, ...]] = {}
    rejected = []
    for fc in claims:
        why = [w for w in (view.usable(eid, fc.factor, fc.level) for eid in fc.evidence_ids) if w]
        if fc.factor is Factor.INDEPENDENT_ROUTES and not why and fc.level >= 1:
            needed = {1: 1, 2: 2}[fc.level]
            lineages = [view.lineage(e) for e in fc.evidence_ids]
            disjoint = all(not (a & b) for i, a in enumerate(lineages) for b in lineages[i + 1:])
            if len(fc.evidence_ids) < needed or not disjoint:
                why.append(f"independent_routes={LEVELS[fc.factor][fc.level]} needs {needed} lineage-disjoint route records")
        if why:
            rejected.extend(f"{fc.factor.value}={LEVELS[fc.factor][fc.level]}: {w}" for w in why)
            continue
        if fc.level > levels[fc.factor]:
            levels[fc.factor] = fc.level
            support[fc.factor] = fc.evidence_ids
    return FactorVector(levels, support, tuple(sorted(rejected)))


class Combine(str, Enum):
    AND = "and"
    OR = "or"


@dataclass(frozen=True)
class ClaimNode:
    """A leaf (``claims`` set) or an AND/OR of children."""

    node_id: str
    claims: tuple[FactorClaim, ...] = ()
    combine: Combine | None = None
    children: tuple["ClaimNode", ...] = ()

    def __post_init__(self) -> None:
        if bool(self.children) == bool(self.claims) and not (not self.children and not self.claims):
            raise CredibilityRefused("a claim node is a leaf (factor claims) or a combination (children), not both")
        if self.children and self.combine is None:
            raise CredibilityRefused("a combination declares AND or OR")
        if self.combine is not None:
            object.__setattr__(self, "combine", Combine(self.combine))

    def evidence(self) -> set[str]:
        return {e for c in self.claims for e in c.evidence_ids} | {e for ch in self.children for e in ch.evidence()}


def _vector(node: ClaimNode, view: _GraphView, notes: list[str]) -> FactorVector:
    if not node.children:
        return _leaf_vector(node.claims, view)
    kids = [_vector(ch, view, notes) for ch in node.children]
    use_max = False
    if node.combine is Combine.OR:
        lineages = [set().union(*(view.lineage(e) for e in ch.evidence())) if ch.evidence() else set() for ch in node.children]
        independent = all(not (a & b) for i, a in enumerate(lineages) for b in lineages[i + 1:])
        use_max = independent
        if not independent:
            notes.append(f"{node.node_id}: OR branches share evidence lineage; combined as the weakest (independence not supported)")
    levels = {f: (max if use_max else min)(k.level(f) for k in kids) for f in Factor}
    support: dict[Factor, tuple[str, ...]] = {}
    for f in Factor:
        ids: set[str] = set()
        for k in kids:
            if use_max and k.level(f) != levels[f]:
                continue
            ids |= set(k.support.get(f, ()))
        if levels[f] >= 0:
            support[f] = tuple(sorted(ids))
    return FactorVector(levels, support, tuple(sorted({r for k in kids for r in k.rejected})))


# ---------------------------------------------------------------------------- requirements (policy only)


class RiskClass(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


#: required minimum level per factor and risk class.  Declared policy, versioned; never evidence.
RISK_POLICY_V1: Mapping[RiskClass, Mapping[Factor, int]] = {
    RiskClass.LOW: {Factor.APPLICABILITY: 1, Factor.VERIFICATION: 1, Factor.NUMERICAL_UQ: 0},
    RiskClass.MEDIUM: {Factor.APPLICABILITY: 1, Factor.VERIFICATION: 1, Factor.VALIDATION: 1, Factor.NUMERICAL_UQ: 1,
                       Factor.PARAMETER_UQ: 0, Factor.MODEL_FORM_UQ: 0},
    RiskClass.HIGH: {Factor.APPLICABILITY: 1, Factor.VERIFICATION: 2, Factor.VALIDATION: 2, Factor.NUMERICAL_UQ: 1,
                     Factor.PARAMETER_UQ: 1, Factor.MEASUREMENT_UQ: 1, Factor.MODEL_FORM_UQ: 1, Factor.INDEPENDENT_ROUTES: 1},
    RiskClass.CRITICAL: {Factor.APPLICABILITY: 1, Factor.VERIFICATION: 2, Factor.VALIDATION: 2, Factor.NUMERICAL_UQ: 1,
                         Factor.PARAMETER_UQ: 1, Factor.MEASUREMENT_UQ: 1, Factor.MODEL_FORM_UQ: 1, Factor.INDEPENDENT_ROUTES: 2,
                         Factor.ADVERSARIAL: 1},
}


@dataclass(frozen=True)
class DecisionRequirement:
    decision_id: str
    context_digest: str
    risk_class: RiskClass
    policy_id: str = "forge.credibility.risk_policy/1"
    required: Mapping[Factor, int] | None = field(default=None, hash=False)   # None: the named policy's row

    def __post_init__(self) -> None:
        object.__setattr__(self, "risk_class", RiskClass(self.risk_class))
        if not str(self.decision_id).strip() or len(str(self.context_digest)) != 64:
            raise CredibilityRefused("a decision requirement names the decision and binds its context digest")
        req = dict(RISK_POLICY_V1[self.risk_class]) if self.required is None else {Factor(k): int(v) for k, v in dict(self.required).items()}
        for f, lv in req.items():
            if not 0 <= lv < len(LEVELS[f]):
                raise CredibilityRefused(f"required {f.value} level {lv} is not a level of that factor")
        object.__setattr__(self, "required", req)


# ---------------------------------------------------------------------------- the report


@dataclass(frozen=True)
class FactorGap:
    factor: Factor
    required: int
    attained: int
    gap: int
    unknown: bool

    def to_dict(self) -> dict[str, Any]:
        return {"factor": self.factor.value, "required": LEVELS[self.factor][self.required],
                "attained": LEVELS[self.factor][self.attained] if self.attained >= 0 else "UNKNOWN", "gap": self.gap,
                "unknown": self.unknown, "gap_class": FACTOR_GAP[self.factor].value}


@dataclass(frozen=True)
class CredibilityVectorReport:
    decision_id: str
    claim_id: str
    graph_digest: str
    policy_id: str
    risk_class: RiskClass
    vector: FactorVector
    gaps: tuple[FactorGap, ...]
    defeaters: tuple[Defeater, ...]
    notes: tuple[str, ...]

    @property
    def open_defeaters(self) -> tuple[Defeater, ...]:
        return self.defeaters

    @property
    def requirement_met(self) -> bool:
        return not self.defeaters and all(g.gap <= 0 for g in self.gaps)

    @property
    def dominant_blocking_gap(self) -> dict[str, Any] | None:
        if self.defeaters:
            d = self.defeaters[0]
            return {"kind": "defeater", "defeater": d.to_dict()}
        blocking = [g for g in self.gaps if g.gap > 0]
        if not blocking:
            return None
        top = max(blocking, key=lambda g: (g.gap, -FACTOR_PRIORITY.index(g.factor)))
        return {"kind": "factor_gap", **top.to_dict()}

    def to_dict(self) -> dict[str, Any]:
        return {"schema": CREDIBILITY_VECTOR_SCHEMA, "decision_id": self.decision_id, "claim_id": self.claim_id,
                "graph_digest": self.graph_digest, "policy_id": self.policy_id, "risk_class": self.risk_class.value,
                "vector": self.vector.to_dict(), "gaps": [g.to_dict() for g in self.gaps],
                "open_defeaters": [d.to_dict() for d in self.defeaters], "dominant_blocking_gap": self.dominant_blocking_gap,
                "requirement_met": self.requirement_met, "notes": list(self.notes)}

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


def assess_credibility(claim: ClaimNode, graph: EvidenceGraph, requirement: DecisionRequirement, *,
                       defeaters: tuple[Defeater, ...] = ()) -> CredibilityVectorReport:
    """f(C) from the graph, r(D) from the policy, g = r - f, open defeaters, dominant blocking gap."""
    view = _GraphView(graph, requirement.context_digest)
    notes: list[str] = []
    vec = _vector(claim, view, notes)
    gaps = []
    for f in FACTOR_PRIORITY:
        if f not in requirement.required:
            continue
        req, got = requirement.required[f], vec.level(f)
        gaps.append(FactorGap(f, req, got, (req + 1) if got == UNKNOWN else max(0, req - got), got == UNKNOWN))
    used = {e for ids in vec.support.values() for e in ids}
    found = view.contradictions_of(used)
    for d in defeaters:
        missing = [e for e in d.evidence_ids if e not in view.nodes]
        if missing:
            raise CredibilityRefused(f"defeater {d.defeater_id} cites evidence not in the graph: {missing}")
        found.append(d)
    return CredibilityVectorReport(requirement.decision_id, claim.node_id, evidence_graph_fingerprint(graph), requirement.policy_id,
                                   requirement.risk_class, vec, tuple(gaps), tuple(sorted(found, key=lambda d: d.defeater_id)),
                                   tuple(notes) + tuple(f"rejected: {r}" for r in vec.rejected))


__all__ = ["ClaimNode", "Combine", "CredibilityRefused", "CredibilityVectorReport", "Defeater", "DecisionRequirement", "FACTOR_GAP",
           "FACTOR_PRIORITY", "Factor", "FactorClaim", "FactorGap", "FactorVector", "LEVELS", "RISK_POLICY_V1", "RiskClass", "UNKNOWN",
           "assess_credibility"]
