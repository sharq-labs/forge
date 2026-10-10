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
* Defeaters -- a CONTRADICTS edge from an admissible (known authority, same context) node into ANY subject, any
  evidence the claim structure CITES (selected or not, usable or not: dropping a check or a pin from a contradicted
  record never removes its contradiction), or the lineage of either; an admissible outside-domain finding (a cited
  level-0 applicability record, or a supplied ApplicabilityReport 'outside' decided on the subject); a FALSIFIED
  red-team envelope for a subject; or an explicit typed :class:`Defeater`.  A contradiction is closed only by a
  registry-pinned newer version of the contradicting source that is outside that closure (noted, never silent).
  Sub-bar contradictions (unknown authority, other context) are recorded as notes.
* Supersession only ever LOWERS: any admissible SUPERSEDES edge into a record disqualifies it as support, whether or not
  the superseder is pinned or itself contradicted (the strict bar is for closing contradictions only).
* The dominant blocking gap -- a defeater first, then any applicability shortfall, then the largest gap (ties by
  :data:`FACTOR_PRIORITY`), mapped onto :class:`~engcore.claims.gaps.GapClass`.

Propagation over a claim structure (:class:`ClaimNode`): AND takes the WEAKEST child per factor; OR takes ONE whole
branch (the best by the declared lexicographic order over :data:`FACTOR_PRIORITY`) only when the branches are
independent -- positively shown by distinct content digests and sources, provenance with distinct issuers, source ids and
document digests, and disjoint lineage over every relation but CONTRADICTS; missing provenance means independence is
UNKNOWN and OR is treated like AND.

Existing records stand behind every level, re-read on each assessment (a node earns nothing by its label):

* applicability inside the domain -- the node carries the digest of a supplied
  :class:`~engcore.system_runtime.records.ApplicabilityReport` with status ``within`` whose ``evidence_digest`` is the
  SUBJECT's content digest (decided on this result);
* a UQ factor -- the node carries the digest of a supplied
  :class:`~engcore.sria.assurance.uncertainty_budget.ChannelEntry` of THAT channel; ``quantified`` needs a KNOWN or
  BOUNDED entry whose uncertainty declares the channel's own source kind (an unattributed number quantifies nothing);
  ``declared`` is also met by a NOT_APPLICABLE entry (a rationale-bearing statement) from an authority that could have
  quantified the channel; an UNKNOWN entry backs no level (UNKNOWN never improves an answer);
* adversarial standing -- a supplied SURVIVED envelope for the subject whose ``subject_digest`` the claim leaf declares
  (``attacked_subject_digest``, bound into the claim structure digest), so an envelope for another statement of the
  claim (another threshold, observable or route set) supplies nothing.

And two authorities behind every strong level: a supplied, PASSING
:class:`~engcore.scientific.results.validation.ValidationCheck` (re-read through ``from_dict``, so its issuer record is
re-verified against the platform's oracle/consensus registries) whose canonical digest the backing node carries, for
verification, validation and independent routes; and a :class:`~engcore.scientific.knowledge.trust.TrustedSourceRegistry`
pin for any level that needs trusted provenance (a record's own pin fields are never trust).  The subject must be bound
to the decision context.  A policy must dominate :data:`RISK_POLICY_V1` row by row.

The report is OUTPUT for a reader, not a persisted authority: there is no reader that trusts a stored report; re-run
:func:`assess_credibility` on the graph.  Residual (deferred hardening): independence is only as good as provenance; a
graph from which a contradicting node was deleted is a different graph (its fingerprint is bound), but this module cannot
know a node is missing.  An ApplicabilityReport / ChannelEntry / ValidationCheck names no result value beyond what is
stated above (the ApplicabilityReport's evidence digest); the claim's attacked statement is what the claim declares, not
a contract record.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from ..credibility.evidence_graph import EvidenceAuthority, EvidenceGraph, EvidenceRelation, evidence_graph_fingerprint
from ..scientific.errors import ScientificCoreError
from ..scientific.knowledge.trust import TrustedSourceRegistry
from ..scientific.results.uncertainty import UncertaintySource
from ..scientific.results.validation import ValidationCheck, ValidationLevel, ValidationOutcome
from ..sria.assurance.uncertainty_budget import ChannelEntry, ChannelState
from ..system_runtime.records import ApplicabilityReport
from .gaps import _CHANNEL_GAP, GapClass
from .redteam import TrustEnvelope

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
#: the source kind a quantified entry of each channel must declare (UNSPECIFIED is accepted by a budget, never here)
_UQ_SOURCE: Mapping[str, UncertaintySource] = MappingProxyType({"numerical": UncertaintySource.NUMERICAL,
                                                               "epistemic_parameter": UncertaintySource.PARAMETER,
                                                               "aleatoric": UncertaintySource.MEASUREMENT,
                                                               "model_form": UncertaintySource.MODEL_FORM})
ENVELOPE_SURVIVED = "trust_envelope:survived"


def _require_complete_projection() -> None:
    if set(VALIDATION_LEVEL_PROJECTION) != set(ValidationLevel):
        raise RuntimeError("VALIDATION_LEVEL_PROJECTION must classify every ValidationLevel")
    if set(UQ_CHANNEL.values()) != set(_CHANNEL_GAP) or set(_UQ_SOURCE) != set(_CHANNEL_GAP):
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
        or (factor is Factor.INDEPENDENT_ROUTES and level >= 1) or (factor is Factor.APPLICABILITY and level >= 1) \
        or factor is Factor.ADVERSARIAL


#: the ValidationLevel(s) a backing check must establish, per factor and level
_CHECK_LEVELS: Mapping[tuple[Factor, int], frozenset[ValidationLevel]] = MappingProxyType({
    (Factor.VERIFICATION, 1): frozenset({ValidationLevel.NUMERICALLY_CONVERGED}),
    (Factor.VERIFICATION, 2): frozenset({ValidationLevel.NUMERICALLY_CONVERGED, ValidationLevel.ANALYTICALLY_VERIFIED}),
    (Factor.VALIDATION, 1): frozenset({ValidationLevel.BENCHMARK_VALIDATED}),
    (Factor.VALIDATION, 2): frozenset({ValidationLevel.EXPERIMENTALLY_VALIDATED}),
    (Factor.INDEPENDENT_ROUTES, 1): frozenset({ValidationLevel.CROSS_SOLVER_VALIDATED}),
    (Factor.INDEPENDENT_ROUTES, 2): frozenset({ValidationLevel.CROSS_SOLVER_VALIDATED}),
})


def record_digest(record: ValidationCheck | ApplicabilityReport | ChannelEntry) -> str:
    """The content digest an evidence node carries for the existing record (check, applicability report, channel entry)
    it records."""
    return _digest(record.to_dict())


def check_digest(check: ValidationCheck) -> str:
    """The content digest an evidence node carries for the ValidationCheck it records."""
    return record_digest(check)


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
    def __init__(self, graph: EvidenceGraph, context_digest: str, trusted: TrustedSourceRegistry | None,
                 checks: Mapping[str, ValidationLevel], applicability: Mapping[str, ApplicabilityReport] | None = None,
                 uq: Mapping[str, ChannelEntry] | None = None) -> None:
        self.graph = graph
        self.context = context_digest
        self.trusted = trusted
        self.checks = checks                                  # check digest -> level it establishes (re-verified, PASS)
        self.applicability = applicability or {}             # report digest -> re-read ApplicabilityReport
        self.uq = uq or {}                                    # entry digest -> re-read ChannelEntry
        self.nodes = {n.evidence_id: n for n in graph.nodes}
        self._parents: dict[str, set[str]] = {}
        for e in graph.edges:
            if e.relation is not EvidenceRelation.CONTRADICTS:
                self._parents.setdefault(e.source_id, set()).add(e.target_id)

    def trusted_provenance(self, evidence_id: str) -> bool:
        """Pinned by the TRUSTED SOURCE REGISTRY (never by the record's own pin fields) and fresh enough."""
        node = self.nodes.get(evidence_id)
        prov = None if node is None else node.provenance
        if prov is None or self.trusted is None or not prov.fresh_enough:
            return False
        pin = self.trusted.pin_for(prov.source_id)
        return pin is not None and (pin.issuer, pin.document_digest, pin.version) == (prov.issuer, prov.document_digest, prov.version)

    def admissible_node(self, evidence_id: str) -> bool:
        n = self.nodes.get(evidence_id)
        return n is not None and n.authority is not EvidenceAuthority.UNKNOWN and n.applicability == self.context

    def contradicted(self, evidence_id: str) -> bool:
        return any(e.relation is EvidenceRelation.CONTRADICTS and e.target_id == evidence_id and self.admissible_node(e.source_id)
                   for e in self.graph.edges)

    def superseders(self, evidence_id: str, protected: set[str]) -> list[str]:
        """Superseders of ``evidence_id`` that are a NEWER VERSION OF THE SAME PINNED SOURCE: trusted provenance with the
        same source id and issuer, another version, the same authority, not themselves contradicted, and not part of the
        protected (support) closure.  Anything else is just another record."""
        target = self.nodes.get(evidence_id)
        out = []
        for e in self.graph.edges:
            if e.relation is not EvidenceRelation.SUPERSEDES or e.target_id != evidence_id or e.source_id in protected:
                continue
            sup = self.nodes[e.source_id]
            if target is None or target.provenance is None or sup.provenance is None or not self.admissible_node(e.source_id):
                continue
            if not self.trusted_provenance(e.source_id) or sup.authority is not target.authority or self.contradicted(e.source_id):
                continue
            if (sup.provenance.source_id, sup.provenance.issuer) != (target.provenance.source_id, target.provenance.issuer) \
                    or sup.provenance.version == target.provenance.version:
                continue
            out.append(e.source_id)
        return out

    def superseded_by(self, evidence_id: str) -> list[str]:
        """EVERY admissible (known authority, same context) node with a SUPERSEDES edge into ``evidence_id`` -- pinned or
        not, contradicted or not.  Supersession only lowers: less trust input or more counter-evidence never revives a
        superseded record."""
        return sorted({e.source_id for e in self.graph.edges if e.relation is EvidenceRelation.SUPERSEDES
                       and e.target_id == evidence_id and self.admissible_node(e.source_id)})

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
        if self.superseded_by(evidence_id):
            return f"{evidence_id} is superseded by {self.superseded_by(evidence_id)}: a superseded record is not support"
        if _needs_provenance(factor, level) and not self.trusted_provenance(evidence_id):
            return (f"{evidence_id} needs provenance pinned by the trusted source registry for {factor.value}="
                    f"{LEVELS[factor][level]}")
        if (factor, level) in _CHECK_LEVELS and self.checks.get(node.content_digest) not in _CHECK_LEVELS[(factor, level)]:
            return (f"{evidence_id} does not carry the digest of a supplied, re-verified, passing ValidationCheck establishing "
                    f"{sorted(lv.value for lv in _CHECK_LEVELS[(factor, level)])}")
        if factor is Factor.APPLICABILITY and level == 1:
            report = self.applicability.get(node.content_digest)
            if report is None or report.status != "within" or report.evidence_digest != self.nodes[subject].content_digest:
                return (f"{evidence_id} does not carry the digest of a supplied, re-read ApplicabilityReport 'within' decided on "
                        f"the subject {subject} (its evidence digest): applicability is not a label")
        if factor in UQ_CHANNEL:
            channel, entry = UQ_CHANNEL[factor], self.uq.get(node.content_digest)
            if entry is None or entry.channel.value != channel:
                return f"{evidence_id} does not carry the digest of a supplied, re-read {channel!r} ChannelEntry: UQ is not a label"
            if entry.state is ChannelState.UNKNOWN:
                return f"{evidence_id}'s {channel!r} entry is UNKNOWN: an unevaluated channel backs no level"
            if entry.is_quantified and entry.uncertainty.source_kind is not _UQ_SOURCE[channel]:
                return (f"{evidence_id}'s {channel!r} entry declares source {entry.uncertainty.source_kind.value!r}, not "
                        f"{_UQ_SOURCE[channel].value!r}: an unattributed or other-channel number quantifies nothing")
            if level == 1 and not entry.is_quantified:
                return f"{evidence_id}'s {channel!r} entry is {entry.state.value}: it declares, it does not quantify"
            if entry.state is ChannelState.NOT_APPLICABLE and node.authority not in _admissible(factor, 1):
                return (f"{evidence_id} ({node.authority.value}) cannot declare {channel!r} not applicable: only an authority "
                        "that could quantify the channel can")
        if factor is Factor.VALIDATION:
            subject_line = self.lineage(subject)
            twins = [n.evidence_id for n in self.graph.nodes if n.content_digest == node.content_digest] + [evidence_id]
            behind = set().union(*(self.lineage(t, subject) for t in twins)) - {subject}
            if any(e.source_id in behind and e.relation is EvidenceRelation.CALIBRATES and e.target_id in subject_line
                   for e in self.graph.edges):
                return (f"{evidence_id} (a record of the same content, or its lineage) calibrated the model it would validate: "
                        "calibration data is not validation")
        return None

    def lineage(self, evidence_id: str, stop: str | None = None) -> set[str]:
        """``evidence_id`` and its ancestors through every relation but CONTRADICTS.  With ``stop`` (a subject), the
        walk reaches ``stop`` but never goes THROUGH it (everything supports a subject; its own lineage is not shared
        provenance of the records that judge it) -- unless the walk starts there."""
        seen, todo = set(), [evidence_id]
        while todo:
            x = todo.pop()
            if x in seen:
                continue
            seen.add(x)
            if x != stop or x == evidence_id:
                todo.extend(self._parents.get(x, ()))
        return seen

    def independent(self, a: str, b: str, subject: str) -> bool:
        """POSITIVE independence: distinct records from distinct sources with distinct pinned provenance, disjoint lineage
        (the subject excluded: everything supports it).  Missing provenance -> not shown independent."""
        if a not in self.nodes or b not in self.nodes:
            return False
        na, nb = self.nodes[a], self.nodes[b]
        if na.content_digest == nb.content_digest or na.source == nb.source:
            return False
        pa, pb = na.provenance, nb.provenance
        if pa is None or pb is None or pa.issuer == pb.issuer or pa.source_id == pb.source_id or pa.document_digest == pb.document_digest:
            return False
        return not ((self.lineage(a, subject) - {subject}) & (self.lineage(b, subject) - {subject}))

    def contradictions_of(self, subjects: set[str], cited: set[str], notes: list[str]) -> list[Defeater]:
        """Admissible contradictions of every subject, every CITED record (selected or not) and the full lineage of
        each: what the claim rests on, independent of which alternative won and of child order."""
        closure = set().union(set(), *(self.lineage(x) for x in subjects | cited))
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
                                f"{e.source_id} ({src.authority.value}) contradicts {e.target_id}, which the claim rests on"))
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


def _leaf_vector(leaf: "ClaimNode", view: _GraphView, envelopes: Mapping[str, tuple[str, str, str]]) -> FactorVector:
    subject, claims = leaf.subject_id, leaf.claims
    levels: dict[Factor, int] = {f: UNKNOWN for f in Factor}
    support: dict[Factor, tuple[str, ...]] = {}
    rejected: list[str] = []
    defeaters: list[Defeater] = []
    cited: dict[str, set[Factor]] = {}                     # decided over ALL citations first: order-independent and
    for fc in claims:                                       # monotone (removing a record never frees another for reuse)
        for e in fc.evidence_ids:
            cited.setdefault(e, set()).add(fc.factor)
    for fc in sorted(claims, key=lambda c: (FACTOR_PRIORITY.index(c.factor), -c.level, c.evidence_ids)):
        label = f"{fc.factor.value}={LEVELS[fc.factor][fc.level]}"
        why = [w for w in (view.usable(eid, fc.factor, fc.level, subject) for eid in fc.evidence_ids) if w]
        defeater_claim = fc.factor is Factor.APPLICABILITY and fc.level == 0
        shared = [] if defeater_claim else sorted(e for e in fc.evidence_ids if len(cited[e]) > 1)   # a defeater stands
        if shared:
            why.append(f"{shared} are cited for several factors ({sorted({f.value for e in shared for f in cited[e]})}): one "
                       "record backs one factor, so every claim citing them is refused")
        if fc.factor is Factor.VERIFICATION and fc.level == 2 and not why:
            got = {view.checks.get(view.nodes[e].content_digest) for e in fc.evidence_ids}
            if not _CHECK_LEVELS[(Factor.VERIFICATION, 2)] <= got:
                why.append("code AND solution verification are two checks (analytically verified + numerically converged)")
        if fc.factor is Factor.INDEPENDENT_ROUTES and not why:
            ids = fc.evidence_ids
            pairs_ok = all(view.independent(a, b, subject) for i, a in enumerate(ids) for b in ids[i + 1:])
            subject_node = view.nodes[subject]
            pairs_ok = pairs_ok and all(view.nodes[e].content_digest != subject_node.content_digest and view.nodes[e].source != subject_node.source
                                        and e not in view.lineage(subject) for e in ids)
            if len(ids) < fc.level or not pairs_ok:
                why.append(f"{label} needs {fc.level} positively independent route records (distinct source, issuer, "
                           "document and lineage)")
        if fc.factor is Factor.ADVERSARIAL and not why:
            bound = ("survived", subject, leaf.attacked_subject_digest)
            if not leaf.attacked_subject_digest or any(envelopes.get(view.nodes[e].content_digest) != bound for e in fc.evidence_ids):
                why.append("adversarial standing cites a node that is not a SURVIVED trust envelope, supplied to the assessment, "
                           "for THIS subject and the attacked statement the claim declares (attacked_subject_digest)")
        if why:
            rejected.extend(f"{label}: {w}" for w in why)
            continue
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
    #: a leaf's red-team statement: the ``subject_digest`` of the ClaimSubject (observable, unit, sense, threshold,
    #: routes) the claim says was attacked.  Bound into the structure digest; ADVERSARIAL needs an envelope for it.
    attacked_subject_digest: str = ""

    def __post_init__(self) -> None:
        if not str(self.node_id).strip():
            raise CredibilityRefused("a claim node has an id")
        if bool(self.children) == bool(self.subject_id):
            raise CredibilityRefused("a claim node is a leaf (subject + factor claims) or a combination (children), exactly one")
        d = str(self.attacked_subject_digest)
        if d and (self.children or len(d) != 64 or set(d) - _HEX):
            raise CredibilityRefused("attacked_subject_digest is a leaf's sha256 hex digest of the attacked ClaimSubject")
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
        out = [self.node_id, self.subject_id, sorted([c.factor.value, c.level, c.basis, list(c.evidence_ids)] for c in self.claims)]
        return out + [self.attacked_subject_digest] if self.attacked_subject_digest else out


def _vector(node: ClaimNode, view: _GraphView, notes: list[str], envelopes: Mapping[str, tuple[str, str, str]]) -> FactorVector:
    if not node.children:
        return _leaf_vector(node, view, envelopes)
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
    """Register a policy once.  Every risk class has a non-empty row of valid levels, a higher risk class never requires
    less than a lower one, and every row DOMINATES the baseline :data:`RISK_POLICY_V1` row (so applicability is always
    required): a registered policy can raise the bar, never lower it."""
    if not isinstance(policy_id, str) or not policy_id.strip() or policy_id != policy_id.strip() or set(policy) != set(RiskClass):
        raise CredibilityRefused("a risk policy has a normalized id and a row for every risk class")
    frozen = {}
    for r in RiskClass:
        row = {Factor(f): lv for f, lv in dict(policy[r]).items()}
        if not row or any(isinstance(lv, bool) or not isinstance(lv, int) or not 0 <= lv < len(LEVELS[f]) for f, lv in row.items()):
            raise CredibilityRefused(f"risk class {r.value}: a non-empty row of valid integer levels")
        frozen[r] = MappingProxyType(row)
    for lo, hi in zip(_RISK_ORDER, _RISK_ORDER[1:]):
        if any(frozen[hi].get(f, -1) < lv for f, lv in frozen[lo].items()):
            raise CredibilityRefused(f"risk class {hi.value} requires less than {lo.value}: a policy is monotone in risk")
    if _POLICIES.get(RISK_POLICY_V1_ID) is not None:
        for r in RiskClass:
            weaker = [f.value for f, lv in _POLICIES[RISK_POLICY_V1_ID][r].items() if frozen[r].get(f, -1) < lv]
            if weaker:
                raise CredibilityRefused(f"risk class {r.value} would require less than {RISK_POLICY_V1_ID} on {weaker}: a "
                                         "registered policy may only be STRICTER than the baseline")
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
                       trusted_sources: TrustedSourceRegistry | None = None, validation_checks: tuple[ValidationCheck, ...] = (),
                       applicability_reports: tuple[ApplicabilityReport, ...] = (), uncertainty_entries: tuple[ChannelEntry, ...] = (),
                       defeaters: tuple[Defeater, ...] = (), red_team: tuple[Any, ...] = ()) -> CredibilityVectorReport:
    """f(C) from the graph, r(D) from the registered policy, g = r - f, open defeaters, dominant blocking gap.
    ``trusted_sources`` pins provenance; ``validation_checks`` are re-verified (``from_dict``) and only PASSING ones back
    a level; ``applicability_reports`` / ``uncertainty_entries`` are re-read (``from_dict``) and back applicability and
    the UQ factors through the nodes carrying their digests (an 'outside' report decided on a subject is a defeater);
    ``red_team``: TrustEnvelope records -- a SURVIVED one for the subject and the claim's attacked statement can back
    ADVERSARIAL (through the graph node carrying its digest), a FALSIFIED one for a subject is a defeater."""
    checks: dict[str, ValidationLevel] = {}
    notes: list[str] = []
    reports: dict[str, ApplicabilityReport] = {}
    entries: dict[str, ChannelEntry] = {}
    for kind, records, cls, into in (("applicability report", applicability_reports, ApplicabilityReport, reports),
                                     ("uncertainty channel entry", uncertainty_entries, ChannelEntry, entries)):
        for rec in records:
            if not isinstance(rec, cls):
                raise CredibilityRefused(f"a {kind} is a {cls.__name__} record")
            try:
                again = cls.from_dict(rec.to_dict())
            except Exception as exc:   # noqa: BLE001 - a record that does not re-read is noted and never used
                notes.append(f"{kind} refused on re-read: {str(exc)[:160]}")
                continue
            into[record_digest(again)] = again
    for chk in validation_checks:
        try:
            again = ValidationCheck.from_dict(chk.to_dict())          # re-verifies issuer records against the registries
        except (ScientificCoreError, ValueError, KeyError, TypeError) as exc:
            notes.append(f"validation check {getattr(chk, 'name', '?')!r} refused on re-read: {str(exc)[:160]}")
            continue
        if again.outcome is ValidationOutcome.PASS and again.establishes is not None:
            checks[check_digest(again)] = again.establishes
    view = _GraphView(graph, requirement.context_digest, trusted_sources, checks, reports, entries)
    if any(not isinstance(env, TrustEnvelope) for env in red_team):
        raise CredibilityRefused("red-team input is TrustEnvelope records")
    envelopes = {envelope_digest(env): (env.outcome.value, env.claim_id, env.subject_digest) for env in red_team}
    leaves = _leaves(claim)
    for leaf in leaves:
        subject = view.nodes.get(leaf.subject_id)
        if subject is None:
            raise CredibilityRefused(f"claim {leaf.node_id}'s subject {leaf.subject_id!r} is not in the evidence graph")
        if subject.applicability != requirement.context_digest or subject.authority is EvidenceAuthority.UNKNOWN:
            raise CredibilityRefused(f"subject {leaf.subject_id!r} is not a known-authority result bound to the decision's context")
    vec = _vector(claim, view, notes, envelopes)
    required = requirement.required
    gaps = []
    for f in FACTOR_PRIORITY:
        if f in required:
            req, got = required[f], vec.level(f)
            gaps.append(FactorGap(f, req, got, (req + 1) if got == UNKNOWN else max(0, req - got), got == UNKNOWN))
    subjects = {leaf.subject_id for leaf in leaves}
    found = list(vec.defeaters) + view.contradictions_of(subjects, claim.evidence(), notes)
    for leaf in leaves:
        sd = view.nodes[leaf.subject_id].content_digest
        for d, ar in sorted(reports.items()):
            if ar.evidence_digest == sd and ar.status == "outside":
                found.append(Defeater(f"outside_domain:{leaf.subject_id}:{d[:12]}", "outside_domain", (),
                                      f"applicability report {ar.check_id!r} decided on {leaf.subject_id} places it OUTSIDE its "
                                      f"model's domain: {ar.reason}"))
            elif ar.evidence_digest == sd and ar.status == "unknown":
                notes.append(f"applicability report {ar.check_id!r} on {leaf.subject_id} is UNKNOWN; it backs nothing")
    for env in red_team:
        if env.outcome.value == "falsified" and env.claim_id in subjects:
            found.append(Defeater(f"red_team:{env.claim_id}:{envelope_digest(env)[:12]}", "red_team_falsified", (), env.statement()))
        elif env.outcome.value == "falsified":
            notes.append(f"a FALSIFIED envelope for {env.claim_id!r}, which is no subject of this claim, is not evidence about it")
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
           "assess_credibility", "check_digest", "envelope_digest", "policy_digest", "record_digest", "register_risk_policy"]
