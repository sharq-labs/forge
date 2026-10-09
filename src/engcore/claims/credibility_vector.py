"""Credibility vectors on the EXISTING evidence graph: what a claim has, what a decision needs, and the gap.

Nothing here is new evidence and no new evidence vocabulary: factor levels are a declared PROJECTION of the existing
:class:`~engcore.scientific.results.validation.ValidationLevel` (see :data:`VALIDATION_LEVEL_PROJECTION`, checked complete
at import) and of the existing UQ channel names (``numerical``, ``epistemic_parameter``, ``aleatoric``, ``model_form`` --
the keys of :mod:`engcore.claims.gaps`), earned only from :class:`~engcore.credibility.evidence_graph.EvidenceNode`
records of one :class:`~engcore.credibility.evidence_graph.EvidenceGraph`:

* ``f(C)`` -- the factor vector of a claim about ONE subject node (the result being judged).  A :class:`FactorClaim`
  names a factor, its basis (a ValidationLevel or a UQ channel), a level and the nodes that back it.  The level counts
  only if every node exists, SUPPORTS or VALIDATES the subject (an edge in the graph), is bound to the decision's
  context, has an authority admissible for that factor and level (an experiment for experimental validation; a model's
  own run never quantifies model-form uncertainty; cross-solver agreement is an independent route, never validation),
  carries trusted, fresh provenance where the level needs it (validation, quantified UQ, independent routes), backs no
  other factor, and is not superseded by an admissible node.  A factor nobody earned is UNKNOWN, below every level and
  never satisfying a requirement.  An admissible OUTSIDE-domain applicability finding is a defeater, not a low rung.
* ``r(D)`` -- the required vector, ONLY from a registered, immutable, risk-monotone policy (:data:`RISK_POLICY_V1`); the
  report binds the policy digest and the row it used.  The policy sets the bar; it is never evidence.
* ``g = r - f`` per factor; UNKNOWN's gap is ``required + 1`` and is flagged.
* Defeaters -- a CONTRADICTS edge from an admissible (known authority, same context) node into the support OR its
  lineage, an admissible outside-domain finding, a FALSIFIED red-team envelope, or an explicit typed :class:`Defeater`.
  A contradiction is closed only by an admissible superseder that is not itself part of the support (noted, never
  silent).  Sub-bar contradictions (unknown authority, other context) are recorded as notes.
* The dominant blocking gap -- a defeater first, then any applicability shortfall, then the largest gap (ties by
  :data:`FACTOR_PRIORITY`), mapped onto :class:`~engcore.claims.gaps.GapClass`.

Propagation over a claim structure (:class:`ClaimNode`): AND takes the WEAKEST child per factor; OR takes ONE whole
branch (the best by the declared lexicographic order over :data:`FACTOR_PRIORITY`) only when the branches are
independent -- positively shown by distinct content digests and sources, provenance with distinct issuers, source ids and
document digests, and disjoint lineage over every relation but CONTRADICTS; missing provenance means independence is
UNKNOWN and OR is treated like AND.

The report is OUTPUT for a reader, not a persisted authority: there is no reader that trusts a stored report; re-run
:func:`assess_credibility` on the graph.  Residual (deferred hardening): independence is only as good as provenance; a
graph from which a contradicting node was deleted is a different graph (its fingerprint is bound), but this module cannot
know a node is missing.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from ..credibility.evidence_graph import EvidenceAuthority, EvidenceGraph, EvidenceRelation, evidence_graph_fingerprint
from ..scientific.results.validation import ValidationLevel
from .gaps import _CHANNEL_GAP, GapClass

CREDIBILITY_VECTOR_SCHEMA = "engcore.claims.credibility_vector/2"
UNKNOWN = -1
_HEX = set("0123456789abcdef")


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


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
LEVELS: Mapping[Factor, tuple[str, ...]] = MappingProxyType({
    Factor.APPLICABILITY: ("outside_domain", "inside_domain"),
    Factor.VERIFICATION: ("none", "solution_verified", "code_and_solution_verified"),
    Factor.VALIDATION: ("none", "benchmark", "experimental"),
    Factor.NUMERICAL_UQ: ("declared", "quantified"),
    Factor.PARAMETER_UQ: ("declared", "quantified"),
    Factor.MEASUREMENT_UQ: ("declared", "quantified"),
    Factor.MODEL_FORM_UQ: ("declared", "quantified"),
    Factor.INDEPENDENT_ROUTES: ("none", "one", "two_or_more"),
    Factor.ADVERSARIAL: ("not_attacked", "survived_declared_attack"),
})

#: every ValidationLevel classified: the factor and level it projects to, or None (not credited by this projection)
VALIDATION_LEVEL_PROJECTION: Mapping[ValidationLevel, tuple[Factor, int] | None] = MappingProxyType({
    ValidationLevel.UNVERIFIED: None,
    ValidationLevel.DIMENSIONALLY_VALID: None,
    ValidationLevel.NUMERICALLY_CONVERGED: (Factor.VERIFICATION, 1),          # solution verification
    ValidationLevel.ANALYTICALLY_VERIFIED: (Factor.VERIFICATION, 2),          # code verification (with a converged solution)
    ValidationLevel.BENCHMARK_VALIDATED: (Factor.VALIDATION, 1),
    ValidationLevel.CROSS_SOLVER_VALIDATED: (Factor.INDEPENDENT_ROUTES, 1),   # R-39: implementations agree; NOT validation
    ValidationLevel.EXPERIMENTALLY_VALIDATED: (Factor.VALIDATION, 2),
})
#: the UQ factors and the existing channel names (claims.gaps) they are
UQ_CHANNEL: Mapping[Factor, str] = MappingProxyType({Factor.NUMERICAL_UQ: "numerical", Factor.PARAMETER_UQ: "epistemic_parameter",
                                                     Factor.MEASUREMENT_UQ: "aleatoric", Factor.MODEL_FORM_UQ: "model_form"})
ENVELOPE_SURVIVED = "trust_envelope:survived"


def _require_complete_projection() -> None:
    if set(VALIDATION_LEVEL_PROJECTION) != set(ValidationLevel):
        raise RuntimeError("VALIDATION_LEVEL_PROJECTION must classify every ValidationLevel")
    if set(UQ_CHANNEL.values()) != set(_CHANNEL_GAP):
        raise RuntimeError("UQ_CHANNEL must cover exactly the UQ channels of claims.gaps")


_require_complete_projection()

FACTOR_PRIORITY = (Factor.APPLICABILITY, Factor.VERIFICATION, Factor.VALIDATION, Factor.MODEL_FORM_UQ, Factor.NUMERICAL_UQ,
                   Factor.PARAMETER_UQ, Factor.MEASUREMENT_UQ, Factor.INDEPENDENT_ROUTES, Factor.ADVERSARIAL)

FACTOR_GAP: Mapping[Factor, GapClass] = MappingProxyType({
    Factor.APPLICABILITY: GapClass.MODEL_APPLICABILITY_UNKNOWN, Factor.VERIFICATION: GapClass.CHECK_NOT_RUN,
    Factor.VALIDATION: GapClass.VALIDATION_LEVEL_MISSING, **{f: _CHANNEL_GAP[ch] for f, ch in UQ_CHANNEL.items()},
    Factor.INDEPENDENT_ROUTES: GapClass.INDEPENDENT_ROUTE_MISSING, Factor.ADVERSARIAL: GapClass.ASSURANCE_OBLIGATION_UNMET,
})

_A = EvidenceAuthority
_COMPUTED = frozenset({_A.SIMULATION, _A.ANALYTICAL})
_EXTERNAL_REFERENCE = frozenset({_A.REFERENCE_DATA, _A.STANDARD, _A.PEER_REVIEWED, _A.OFFICIAL_DATA})
_MEASURED = frozenset({_A.MEASUREMENT, _A.EXPERIMENT})
_KNOWN = frozenset(_A) - {_A.UNKNOWN}
_SUPPORT_RELATIONS = (EvidenceRelation.SUPPORTS, EvidenceRelation.VALIDATES)


def _admissible(factor: Factor, level: int) -> frozenset[EvidenceAuthority]:
    """Which authorities can earn ``level`` of ``factor``."""
    if factor is Factor.VALIDATION:
        return {1: _EXTERNAL_REFERENCE | _MEASURED, 2: _MEASURED}[level]
    if factor in (Factor.VERIFICATION, Factor.INDEPENDENT_ROUTES, Factor.ADVERSARIAL):
        return _COMPUTED                                     # verification checks THIS run: a document cannot verify it
    if factor is Factor.APPLICABILITY:
        return _KNOWN
    if level == 0:                                           # a declared uncertainty
        return _KNOWN
    return {Factor.NUMERICAL_UQ: _COMPUTED, Factor.PARAMETER_UQ: _COMPUTED | _MEASURED | _EXTERNAL_REFERENCE,
            Factor.MEASUREMENT_UQ: _MEASURED | _EXTERNAL_REFERENCE,
            Factor.MODEL_FORM_UQ: _MEASURED | _EXTERNAL_REFERENCE}[factor]   # model-form discrepancy needs an outside reference


def _needs_provenance(factor: Factor, level: int) -> bool:
    return (factor is Factor.VALIDATION and level >= 1) or (factor in UQ_CHANNEL and level >= 1) \
        or (factor is Factor.INDEPENDENT_ROUTES and level >= 1)


@dataclass(frozen=True)
class FactorClaim:
    """``basis``: a ValidationLevel value (verification / validation / independent routes), the UQ channel name (UQ
    factors), ``"applicability"`` or :data:`ENVELOPE_SURVIVED` (adversarial).  The level must be what the basis projects to."""

    factor: Factor
    level: int
    evidence_ids: tuple[str, ...]
    basis: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "factor", Factor(self.factor))
        object.__setattr__(self, "evidence_ids", tuple(sorted(set(self.evidence_ids))))
        if isinstance(self.level, bool) or not isinstance(self.level, int) or not 0 <= self.level < len(LEVELS[self.factor]):
            raise CredibilityRefused(f"{self.factor.value} levels are 0..{len(LEVELS[self.factor]) - 1} ({LEVELS[self.factor]})")
        if not self.evidence_ids:
            raise CredibilityRefused("a factor level names the graph evidence that earns it; a level is never asserted")
        f, lv, b = self.factor, self.level, self.basis
        if f in (Factor.VERIFICATION, Factor.VALIDATION, Factor.INDEPENDENT_ROUTES):
            try:
                proj = VALIDATION_LEVEL_PROJECTION[ValidationLevel(b)]
            except ValueError as exc:
                raise CredibilityRefused(f"{f.value} is earned through a ValidationLevel basis, not {b!r}") from exc
            top = proj[1] if proj and proj[0] is f else None
            if top is None or (f is Factor.INDEPENDENT_ROUTES and lv not in (1, 2)) or (f is not Factor.INDEPENDENT_ROUTES and lv != top):
                raise CredibilityRefused(f"basis {b!r} does not project to {f.value}={LEVELS[f][lv]}")
            if f is Factor.VERIFICATION and lv == 2 and len(self.evidence_ids) < 2:
                raise CredibilityRefused("code AND solution verification are two records")
        elif f in UQ_CHANNEL:
            if b != UQ_CHANNEL[f]:
                raise CredibilityRefused(f"{f.value} is the {UQ_CHANNEL[f]!r} uncertainty channel; basis {b!r} is another")
        elif f is Factor.ADVERSARIAL:
            if lv != 1 or b != ENVELOPE_SURVIVED:
                raise CredibilityRefused("adversarial standing is earned only by a SURVIVED trust envelope")
        elif b != "applicability":
            raise CredibilityRefused("applicability is earned with basis 'applicability'")


DEFEATER_KINDS = ("contradiction", "outside_domain", "falsifier_refuted", "red_team_falsified")


@dataclass(frozen=True)
class Defeater:
    defeater_id: str
    kind: str
    evidence_ids: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if not str(self.defeater_id).strip() or self.kind not in DEFEATER_KINDS or not str(self.reason).strip():
            raise CredibilityRefused(f"a defeater has an id, a kind in {DEFEATER_KINDS} and a reason")

    def to_dict(self) -> dict[str, Any]:
        return {"defeater_id": self.defeater_id, "kind": self.kind, "evidence_ids": list(self.evidence_ids), "reason": self.reason}


# ---------------------------------------------------------------------------- the graph view


class _GraphView:
    def __init__(self, graph: EvidenceGraph, context_digest: str) -> None:
        self.graph = graph
        self.context = context_digest
        self.nodes = {n.evidence_id: n for n in graph.nodes}
        self._parents: dict[str, set[str]] = {}
        for e in graph.edges:
            if e.relation is not EvidenceRelation.CONTRADICTS:
                self._parents.setdefault(e.source_id, set()).add(e.target_id)

    def admissible_node(self, evidence_id: str) -> bool:
        n = self.nodes.get(evidence_id)
        return n is not None and n.authority is not EvidenceAuthority.UNKNOWN and n.applicability == self.context

    def superseders(self, evidence_id: str, protected: set[str]) -> list[str]:
        """Admissible superseders of ``evidence_id`` that are not themselves part of the protected (support) closure."""
        return [e.source_id for e in self.graph.edges if e.relation is EvidenceRelation.SUPERSEDES and e.target_id == evidence_id
                and self.admissible_node(e.source_id) and e.source_id not in protected]

    def supports_subject(self, evidence_id: str, subject: str) -> bool:
        return any(e.source_id == evidence_id and e.target_id == subject and e.relation in _SUPPORT_RELATIONS for e in self.graph.edges)

    def usable(self, evidence_id: str, factor: Factor, level: int, subject: str) -> str | None:
        node = self.nodes.get(evidence_id)
        if node is None:
            return f"{evidence_id} is not in the evidence graph"
        if evidence_id == subject:
            return f"{evidence_id} is the subject itself; a result does not back its own credibility"
        if node.applicability != self.context:
            return f"{evidence_id} is bound to another context than the decision's"
        if node.authority not in _admissible(factor, level):
            return f"{evidence_id} ({node.authority.value}) cannot earn {factor.value}={LEVELS[factor][level]}"
        if not self.supports_subject(evidence_id, subject):
            return f"{evidence_id} has no SUPPORTS/VALIDATES edge to the subject {subject}"
        if self.superseders(evidence_id, set()):
            return f"{evidence_id} is superseded by admissible evidence"
        if _needs_provenance(factor, level):
            prov = node.provenance
            if prov is None or not prov.trusted or not prov.fresh_enough:
                return f"{evidence_id} needs trusted, fresh provenance for {factor.value}={LEVELS[factor][level]}"
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

    def independent(self, a: str, b: str, subject: str) -> bool:
        """POSITIVE independence: distinct records from distinct sources with distinct pinned provenance, disjoint lineage
        (the subject excluded: everything supports it).  Missing provenance -> not shown independent."""
        na, nb = self.nodes[a], self.nodes[b]
        if na.content_digest == nb.content_digest or na.source == nb.source:
            return False
        pa, pb = na.provenance, nb.provenance
        if pa is None or pb is None or pa.issuer == pb.issuer or pa.source_id == pb.source_id or pa.document_digest == pb.document_digest:
            return False
        return not ((self.lineage(a) - {subject}) & (self.lineage(b) - {subject}))

    def contradictions_of(self, support: set[str], notes: list[str]) -> list[Defeater]:
        closure = set().union(*(self.lineage(s) for s in support)) if support else set()
        out = []
        for e in self.graph.edges:
            if e.relation is not EvidenceRelation.CONTRADICTS or e.target_id not in closure:
                continue
            if not self.admissible_node(e.source_id):
                notes.append(f"sub-bar contradiction of {e.target_id} by {e.source_id} (unknown authority or other context)")
                continue
            closed_by = self.superseders(e.source_id, closure)
            if closed_by:
                notes.append(f"contradiction {e.source_id}->{e.target_id} closed by admissible superseder(s) {closed_by}")
                continue
            src = self.nodes[e.source_id]
            out.append(Defeater(f"contradiction:{e.source_id}->{e.target_id}", "contradiction", (e.source_id, e.target_id),
                                f"{e.source_id} ({src.authority.value}) contradicts {e.target_id}, which the support rests on"))
        return out


# ---------------------------------------------------------------------------- vectors


@dataclass(frozen=True)
class FactorVector:
    levels: Mapping[Factor, int] = field(hash=False)
    support: Mapping[Factor, tuple[str, ...]] = field(hash=False)
    rejected: tuple[str, ...] = ()
    defeaters: tuple[Defeater, ...] = ()

    def level(self, factor: Factor) -> int:
        return self.levels.get(factor, UNKNOWN)

    def order_key(self) -> tuple[int, ...]:
        return tuple(self.level(f) for f in FACTOR_PRIORITY)

    def to_dict(self) -> dict[str, Any]:
        return {"levels": {f.value: (LEVELS[f][lv] if lv >= 0 else "UNKNOWN") for f, lv in sorted(self.levels.items(), key=lambda kv: kv[0].value)},
                "support": {f.value: list(ids) for f, ids in sorted(self.support.items(), key=lambda kv: kv[0].value)},
                "rejected": list(self.rejected)}


def _leaf_vector(subject: str, claims: tuple[FactorClaim, ...], view: _GraphView, envelopes: Mapping[str, str]) -> FactorVector:
    levels: dict[Factor, int] = {f: UNKNOWN for f in Factor}
    support: dict[Factor, tuple[str, ...]] = {}
    rejected: list[str] = []
    defeaters: list[Defeater] = []
    used: dict[str, Factor] = {}
    for fc in sorted(claims, key=lambda c: (FACTOR_PRIORITY.index(c.factor), -c.level, c.evidence_ids)):
        label = f"{fc.factor.value}={LEVELS[fc.factor][fc.level]}"
        why = [w for w in (view.usable(eid, fc.factor, fc.level, subject) for eid in fc.evidence_ids) if w]
        reused = [e for e in fc.evidence_ids if e in used and used[e] is not fc.factor]
        if reused:
            why.append(f"{reused} already back {sorted({used[e].value for e in reused})}: one record backs one factor")
        if fc.factor is Factor.INDEPENDENT_ROUTES and not why:
            ids = fc.evidence_ids
            pairs_ok = all(view.independent(a, b, subject) for i, a in enumerate(ids) for b in ids[i + 1:])
            if len(ids) < fc.level or not pairs_ok:
                why.append(f"{label} needs {fc.level} positively independent route records (distinct source, issuer, "
                           "document and lineage)")
        if fc.factor is Factor.ADVERSARIAL and not why:
            if any(envelopes.get(view.nodes[e].content_digest) != "survived" for e in fc.evidence_ids):
                why.append("adversarial standing cites a node that is not a SURVIVED trust envelope supplied to the assessment")
        if why:
            rejected.extend(f"{label}: {w}" for w in why)
            continue
        for e in fc.evidence_ids:
            used[e] = fc.factor
        if fc.factor is Factor.APPLICABILITY and fc.level == 0:
            defeaters.append(Defeater(f"outside_domain:{subject}", "outside_domain", fc.evidence_ids,
                                      f"admissible evidence {list(fc.evidence_ids)} places {subject} OUTSIDE its model's domain"))
            levels[fc.factor] = 0
            support[fc.factor] = fc.evidence_ids
            continue
        if fc.factor is Factor.APPLICABILITY and levels[fc.factor] == 0:
            rejected.append(f"{label}: an admissible outside-domain finding stands; it is not overridden by another record")
            continue
        if fc.level > levels[fc.factor]:
            levels[fc.factor] = fc.level
            support[fc.factor] = fc.evidence_ids
    return FactorVector(levels, support, tuple(sorted(rejected)), tuple(defeaters))


class Combine(str, Enum):
    AND = "and"
    OR = "or"


@dataclass(frozen=True)
class ClaimNode:
    """A LEAF (a ``subject_id`` -- the graph node of the result judged -- and its factor claims) or a COMBINATION
    (AND/OR of children).  Exactly one of the two."""

    node_id: str
    claims: tuple[FactorClaim, ...] = ()
    combine: Combine | None = None
    children: tuple["ClaimNode", ...] = ()
    subject_id: str = ""

    def __post_init__(self) -> None:
        if not str(self.node_id).strip():
            raise CredibilityRefused("a claim node has an id")
        if bool(self.children) == bool(self.subject_id):
            raise CredibilityRefused("a claim node is a leaf (subject + factor claims) or a combination (children), exactly one")
        if self.children:
            if self.combine is None or self.claims:
                raise CredibilityRefused("a combination declares AND or OR and carries no factor claims of its own")
            object.__setattr__(self, "combine", Combine(self.combine))
        elif self.combine is not None:
            raise CredibilityRefused("a leaf does not combine")

    def evidence(self) -> set[str]:
        return {e for c in self.claims for e in c.evidence_ids} | {e for ch in self.children for e in ch.evidence()}

    def structure(self) -> Any:
        if self.children:
            return [self.node_id, self.combine.value, [ch.structure() for ch in self.children]]
        return [self.node_id, self.subject_id, sorted([c.factor.value, c.level, c.basis, list(c.evidence_ids)] for c in self.claims)]


def _vector(node: ClaimNode, view: _GraphView, notes: list[str], envelopes: Mapping[str, str]) -> FactorVector:
    if not node.children:
        return _leaf_vector(node.subject_id, node.claims, view, envelopes)
    kids = [_vector(ch, view, notes, envelopes) for ch in node.children]
    defeaters = tuple(d for k in kids for d in k.defeaters)
    rejected = tuple(sorted({r for k in kids for r in k.rejected}))
    if node.combine is Combine.OR:
        evid = [sorted(ch.evidence()) for ch in node.children]
        subjects = {c.subject_id for c in _leaves(node)}
        independent = all(view.independent(a, b, s) for i, ea in enumerate(evid) for eb in evid[i + 1:] for a in ea for b in eb
                           for s in subjects) and all(evid)
        if independent:
            best = max(range(len(kids)), key=lambda i: (kids[i].order_key(), -i))
            notes.append(f"{node.node_id}: OR took branch {node.children[best].node_id} whole (branches shown independent)")
            return FactorVector(kids[best].levels, kids[best].support, rejected, defeaters)
        notes.append(f"{node.node_id}: OR branches not shown independent; combined as the weakest")
    levels = {f: min(k.level(f) for k in kids) for f in Factor}
    support = {f: tuple(sorted(set().union(*(set(k.support.get(f, ())) for k in kids)))) for f in Factor if levels[f] >= 0}
    return FactorVector(levels, support, rejected, defeaters)


def _leaves(node: ClaimNode) -> list[ClaimNode]:
    return [node] if not node.children else [x for ch in node.children for x in _leaves(ch)]


# ---------------------------------------------------------------------------- requirements (registered policy only)


class RiskClass(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


_RISK_ORDER = (RiskClass.LOW, RiskClass.MEDIUM, RiskClass.HIGH, RiskClass.CRITICAL)

RISK_POLICY_V1_ID = "forge.credibility.risk_policy/1"
#: required minimum level per factor and risk class.  Declared policy, versioned, immutable; never evidence.
RISK_POLICY_V1: Mapping[RiskClass, Mapping[Factor, int]] = MappingProxyType({
    RiskClass.LOW: MappingProxyType({Factor.APPLICABILITY: 1, Factor.VERIFICATION: 1, Factor.NUMERICAL_UQ: 0}),
    RiskClass.MEDIUM: MappingProxyType({Factor.APPLICABILITY: 1, Factor.VERIFICATION: 1, Factor.VALIDATION: 1,
                                        Factor.NUMERICAL_UQ: 1, Factor.PARAMETER_UQ: 0, Factor.MODEL_FORM_UQ: 0}),
    RiskClass.HIGH: MappingProxyType({Factor.APPLICABILITY: 1, Factor.VERIFICATION: 2, Factor.VALIDATION: 2, Factor.NUMERICAL_UQ: 1,
                                      Factor.PARAMETER_UQ: 1, Factor.MEASUREMENT_UQ: 1, Factor.MODEL_FORM_UQ: 1,
                                      Factor.INDEPENDENT_ROUTES: 1}),
    RiskClass.CRITICAL: MappingProxyType({Factor.APPLICABILITY: 1, Factor.VERIFICATION: 2, Factor.VALIDATION: 2,
                                          Factor.NUMERICAL_UQ: 1, Factor.PARAMETER_UQ: 1, Factor.MEASUREMENT_UQ: 1,
                                          Factor.MODEL_FORM_UQ: 1, Factor.INDEPENDENT_ROUTES: 2, Factor.ADVERSARIAL: 1}),
})
_POLICIES: dict[str, Mapping[RiskClass, Mapping[Factor, int]]] = {}


def policy_digest(policy: Mapping[RiskClass, Mapping[Factor, int]]) -> str:
    return _digest({r.value: {f.value: lv for f, lv in sorted(row.items(), key=lambda kv: kv[0].value)} for r, row in policy.items()})


def register_risk_policy(policy_id: str, policy: Mapping[RiskClass, Mapping[Factor, int]]) -> None:
    """Register a policy once.  Every risk class has a non-empty row of valid levels, and a higher risk class never
    requires less than a lower one (factor by factor)."""
    if not str(policy_id).strip() or set(policy) != set(RiskClass):
        raise CredibilityRefused("a risk policy has an id and a row for every risk class")
    frozen = {}
    for r in RiskClass:
        row = {Factor(f): lv for f, lv in dict(policy[r]).items()}
        if not row or any(isinstance(lv, bool) or not isinstance(lv, int) or not 0 <= lv < len(LEVELS[f]) for f, lv in row.items()):
            raise CredibilityRefused(f"risk class {r.value}: a non-empty row of valid integer levels")
        frozen[r] = MappingProxyType(row)
    for lo, hi in zip(_RISK_ORDER, _RISK_ORDER[1:]):
        if any(frozen[hi].get(f, -1) < lv for f, lv in frozen[lo].items()):
            raise CredibilityRefused(f"risk class {hi.value} requires less than {lo.value}: a policy is monotone in risk")
    if policy_id in _POLICIES and policy_digest(_POLICIES[policy_id]) != policy_digest(frozen):
        raise CredibilityRefused(f"policy {policy_id!r} is already registered with other rows")
    _POLICIES[policy_id] = MappingProxyType(frozen)


register_risk_policy(RISK_POLICY_V1_ID, RISK_POLICY_V1)


@dataclass(frozen=True)
class DecisionRequirement:
    decision_id: str
    context_digest: str
    risk_class: RiskClass
    policy_id: str = RISK_POLICY_V1_ID

    def __post_init__(self) -> None:
        object.__setattr__(self, "risk_class", RiskClass(self.risk_class))
        ctx = str(self.context_digest)
        if not str(self.decision_id).strip() or len(ctx) != 64 or set(ctx) - _HEX:
            raise CredibilityRefused("a decision requirement names the decision and binds its context digest (sha256 hex)")
        if self.policy_id not in _POLICIES:
            raise CredibilityRefused(f"no registered risk policy {self.policy_id!r}; r(D) comes only from a registered policy")

    @property
    def required(self) -> Mapping[Factor, int]:
        return _POLICIES[self.policy_id][self.risk_class]

    @property
    def policy_digest(self) -> str:
        return policy_digest(_POLICIES[self.policy_id])


# ---------------------------------------------------------------------------- the report


@dataclass(frozen=True)
class FactorGap:
    factor: Factor
    required: int
    attained: int
    gap: int
    unknown: bool

    @property
    def gap_class(self) -> GapClass:
        if self.factor is Factor.APPLICABILITY and self.attained == 0:
            return GapClass.MODEL_OUTSIDE_DOMAIN
        return FACTOR_GAP[self.factor]

    def to_dict(self) -> dict[str, Any]:
        return {"factor": self.factor.value, "required": LEVELS[self.factor][self.required],
                "attained": LEVELS[self.factor][self.attained] if self.attained >= 0 else "UNKNOWN", "gap": self.gap,
                "unknown": self.unknown, "gap_class": self.gap_class.value}


@dataclass(frozen=True)
class CredibilityVectorReport:
    decision_id: str
    claim_id: str
    claim_structure_digest: str
    context_digest: str
    graph_digest: str
    policy_id: str
    policy_digest: str
    risk_class: RiskClass
    required: Mapping[Factor, int] = field(hash=False)
    vector: FactorVector = field(hash=False, default=None)  # type: ignore[assignment]
    gaps: tuple[FactorGap, ...] = ()
    defeaters: tuple[Defeater, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def open_defeaters(self) -> tuple[Defeater, ...]:
        return self.defeaters

    @property
    def requirement_met(self) -> bool:
        return bool(self.gaps) and not self.defeaters and all(g.gap <= 0 for g in self.gaps)

    @property
    def dominant_blocking_gap(self) -> dict[str, Any] | None:
        if self.defeaters:
            return {"kind": "defeater", "defeater": self.defeaters[0].to_dict()}
        blocking = [g for g in self.gaps if g.gap > 0]
        if not blocking:
            return None
        applicability = [g for g in blocking if g.factor is Factor.APPLICABILITY]
        top = applicability[0] if applicability else max(blocking, key=lambda g: (g.gap, -FACTOR_PRIORITY.index(g.factor)))
        return {"kind": "factor_gap", **top.to_dict()}

    def to_dict(self) -> dict[str, Any]:
        return {"schema": CREDIBILITY_VECTOR_SCHEMA, "decision_id": self.decision_id, "claim_id": self.claim_id,
                "claim_structure_digest": self.claim_structure_digest, "context_digest": self.context_digest,
                "graph_digest": self.graph_digest, "policy_id": self.policy_id, "policy_digest": self.policy_digest,
                "risk_class": self.risk_class.value,
                "required": {f.value: LEVELS[f][lv] for f, lv in sorted(self.required.items(), key=lambda kv: kv[0].value)},
                "vector": self.vector.to_dict(), "gaps": [g.to_dict() for g in self.gaps],
                "open_defeaters": [d.to_dict() for d in self.defeaters], "dominant_blocking_gap": self.dominant_blocking_gap,
                "requirement_met": self.requirement_met, "notes": list(self.notes)}

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


def envelope_digest(envelope: Any) -> str:
    """The content digest an evidence node carries for a red-team TrustEnvelope (``engcore.claims.redteam``)."""
    return hashlib.sha256(json.dumps(envelope.to_dict(), sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def assess_credibility(claim: ClaimNode, graph: EvidenceGraph, requirement: DecisionRequirement, *,
                       defeaters: tuple[Defeater, ...] = (), red_team: tuple[Any, ...] = ()) -> CredibilityVectorReport:
    """f(C) from the graph, r(D) from the registered policy, g = r - f, open defeaters, dominant blocking gap.
    ``red_team``: TrustEnvelope records; a SURVIVED one can back ADVERSARIAL (through the graph node carrying its digest),
    a FALSIFIED one is a defeater."""
    view = _GraphView(graph, requirement.context_digest)
    notes: list[str] = []
    envelopes = {envelope_digest(env): env.outcome.value for env in red_team}
    for leaf in _leaves(claim):
        if leaf.subject_id not in view.nodes:
            raise CredibilityRefused(f"claim {leaf.node_id}'s subject {leaf.subject_id!r} is not in the evidence graph")
    vec = _vector(claim, view, notes, envelopes)
    required = requirement.required
    gaps = []
    for f in FACTOR_PRIORITY:
        if f in required:
            req, got = required[f], vec.level(f)
            gaps.append(FactorGap(f, req, got, (req + 1) if got == UNKNOWN else max(0, req - got), got == UNKNOWN))
    support = {e for ids in vec.support.values() for e in ids}
    found = list(vec.defeaters) + view.contradictions_of(support, notes)
    for env in red_team:
        if env.outcome.value == "falsified":
            found.append(Defeater(f"red_team:{env.claim_id}:{envelope_digest(env)[:12]}", "red_team_falsified", (), env.statement()))
    for d in defeaters:
        missing = [e for e in d.evidence_ids if e not in view.nodes]
        if missing:
            raise CredibilityRefused(f"defeater {d.defeater_id} cites evidence not in the graph: {missing}")
        found.append(d)
    order = {k: i for i, k in enumerate(DEFEATER_KINDS)}
    return CredibilityVectorReport(
        requirement.decision_id, claim.node_id, _digest(claim.structure()), requirement.context_digest, evidence_graph_fingerprint(graph),
        requirement.policy_id, requirement.policy_digest, requirement.risk_class, required, vec, tuple(gaps),
        tuple(sorted({d.defeater_id: d for d in found}.values(), key=lambda d: (order[d.kind], d.defeater_id))),
        tuple(notes) + tuple(f"rejected: {r}" for r in vec.rejected))


__all__ = ["ClaimNode", "Combine", "CredibilityRefused", "CredibilityVectorReport", "DEFEATER_KINDS", "Defeater", "DecisionRequirement",
           "ENVELOPE_SURVIVED", "FACTOR_GAP", "FACTOR_PRIORITY", "Factor", "FactorClaim", "FactorGap", "FactorVector", "LEVELS",
           "RISK_POLICY_V1", "RISK_POLICY_V1_ID", "RiskClass", "UNKNOWN", "UQ_CHANNEL", "VALIDATION_LEVEL_PROJECTION",
           "assess_credibility", "envelope_digest", "policy_digest", "register_risk_policy"]
