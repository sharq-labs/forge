"""CORE-4 -- model selection: which declared capability may bear evidence for a claim.

The rule this module exists to enforce is the one easiest to lose: **a model is
never chosen because it can execute.** A candidate is a capability whose
declared output, dimension, scientific capabilities and claim shape match the
claim (:meth:`CapabilityRegistry.match`). Matching only makes it a candidate.
Whether it may *bear evidence* depends on whether its models are applicable to
what the claim states -- and that is assessed here, before anything runs, with
each model's own :class:`~engcore.scientific.models.definition.ValidityDomain`.

Pre-execution applicability
---------------------------
Each active model instance is assessed over exactly the inputs the claim
supplied that feed it (``ValidityDomain.assess(declared=...)``). The result uses
the Core's own vocabulary -- :class:`ValidityStatus` and
:class:`UnknownReason` -- and adds one thing the Core cannot know: **why** a
condition is UNKNOWN *before* the run.

``MISSING_CONTEXT``
    The condition reads a declared, caller-suppliable input directly and the
    claim does not state it. Actionable and blocking: the compiler asks for it.
``PENDING_EXECUTION``
    The condition reads state the run computes (a derived group, a coupled
    temperature). It will be decided by the run's own assessment. When the
    system measured that omitting some unstated input leaves this condition
    UNKNOWN, those inputs are carried as *advisory*: the measurement
    (``CaseDescription.unlocks``) is a union over regimes -- a free-convection
    fluid property is listed even for a forced-convection case -- so it can say
    what *may* be needed, never what *is*.
``DECLARED_UNASSESSABLE``
    The capability declares it never assembles the context this condition
    reads. No input changes that, so the model's applicability can never be
    established here and the candidate cannot bear evidence.
``NOT_ASSESSABLE``
    Evaluated and inconclusive for a reason no declaration repairs (a
    conservative screen not cleared, a value shape the Core cannot read).

Selection
---------
1. Rejected, with the reason recorded: a candidate that would silently drop a
   supplied input it does not declare; one given an input it cannot accept; one
   given a qualifier that selects nothing; one with a model OUTSIDE its
   validated domain on what the claim states; one whose applicability can never
   be established (a model with no conditions, or a declared-unassessable one).
2. **UNKNOWN never beats IN_DOMAIN**: if any viable candidate is IN_DOMAIN on
   what the claim states, the UNKNOWN ones are outranked, not merged with it.
3. Exactly one survivor is selected. More than one is AMBIGUOUS and is left to
   the caller to separate with a structured requirement: nothing here ranks
   two applicable capabilities by convenience.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

from ..scientific.errors import ScientificCoreError
from ..scientific.models.definition import UnknownReason, ValidityStatus
from ..scientific.units.quantity import Quantity
from .capabilities import (
    CapabilityDeclaration,
    CapabilityMatch,
    CapabilityRegistry,
    InputDeclaration,
    ModelUse,
    declared_path,
    input_problem,
)
from .contract import ScientificClaim

_INDEX = re.compile(r"\[(\d+)\]")


class UnknownBasis(str, Enum):
    """Why a condition is UNKNOWN before execution. See the module docstring."""

    MISSING_CONTEXT = "missing_context"
    PENDING_EXECUTION = "pending_execution"
    DECLARED_UNASSESSABLE = "declared_unassessable"
    NOT_ASSESSABLE = "not_assessable"


class CandidateStatus(str, Enum):
    SELECTED = "selected"
    #: Viable, but another viable candidate exists: the claim is AMBIGUOUS.
    VIABLE = "viable"
    #: Viable but UNKNOWN while another viable candidate is IN_DOMAIN.
    OUTRANKED = "outranked"
    REJECTED = "rejected"
    #: Did not match the claim's quantity, dimension, capabilities or shape.
    NOT_A_CANDIDATE = "not_a_candidate"


class RejectionReason(str, Enum):
    UNACCEPTED_INPUT = "unaccepted_input"
    INVALID_INPUT = "invalid_input"
    UNUSED_QUALIFIER = "unused_qualifier"
    OUTSIDE_VALIDITY = "outside_validity"
    VALIDITY_UNASSESSABLE = "validity_unassessable"


@dataclass(frozen=True)
class ConditionStatus:
    """One validity condition of one model instance, as assessed before execution."""

    condition: str
    outcome: str  # "satisfied" | "violated" | "unknown"
    reason: UnknownReason | None = None
    basis: UnknownBasis | None = None
    missing_inputs: tuple[str, ...] = ()
    alternatives: tuple[str, ...] = ()
    declared: Mapping[str, Any] | None = None
    note: str = ""
    advisory_inputs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition": self.condition,
            "outcome": self.outcome,
            "reason": None if self.reason is None else self.reason.value,
            "basis": None if self.basis is None else self.basis.value,
            "missing_inputs": list(self.missing_inputs),
            "advisory_inputs": list(self.advisory_inputs),
            "alternatives": list(self.alternatives),
            "declared": None if self.declared is None else dict(self.declared),
            "note": self.note,
        }


@dataclass(frozen=True)
class ModelApplicability:
    """A model instance's pre-execution applicability, with its declared scope.

    ``status`` is the Core's :class:`ValidityStatus` over what the claim states.
    ``assumptions`` and ``exclusions`` are the model's own, carried so a
    selection explains *what the chosen model assumes and excludes*.
    """

    model_id: str
    version: str
    instance: str | None
    status: ValidityStatus
    conditions: tuple[ConditionStatus, ...]
    assumptions: tuple[str, ...]
    exclusions: tuple[str, ...]

    def unknown_of(self, basis: UnknownBasis) -> tuple[ConditionStatus, ...]:
        return tuple(c for c in self.conditions if c.basis is basis)

    @property
    def violated(self) -> tuple[ConditionStatus, ...]:
        return tuple(c for c in self.conditions if c.outcome == "violated")

    @property
    def bases(self) -> frozenset[UnknownBasis]:
        return frozenset(c.basis for c in self.conditions if c.basis is not None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "version": self.version,
            "instance": self.instance,
            "status": self.status.value,
            "conditions": [c.to_dict() for c in self.conditions],
            "assumptions": list(self.assumptions),
            "exclusions": list(self.exclusions),
        }


@dataclass(frozen=True)
class CandidateAssessment:
    """Everything selection concluded about one registered capability."""

    capability_id: str
    version: str
    digest: str
    match: CapabilityMatch
    status: CandidateStatus
    applicability: ValidityStatus | None = None
    models: tuple[ModelApplicability, ...] = ()
    rejections: tuple[tuple[RejectionReason, str], ...] = ()
    unaccepted_inputs: tuple[str, ...] = ()
    input_problems: tuple[tuple[str, str], ...] = ()

    @property
    def viable(self) -> bool:
        return self.status in (CandidateStatus.SELECTED, CandidateStatus.VIABLE, CandidateStatus.OUTRANKED)

    @property
    def bases(self) -> frozenset[UnknownBasis]:
        found: set[UnknownBasis] = set()
        for model in self.models:
            found |= model.bases
        return frozenset(found)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "version": self.version,
            "digest": self.digest,
            "match": self.match.to_dict(),
            "status": self.status.value,
            "applicability": None if self.applicability is None else self.applicability.value,
            "unknown_bases": sorted(b.value for b in self.bases),
            "models": [m.to_dict() for m in self.models],
            "rejections": [{"reason": r.value, "detail": d} for r, d in self.rejections],
            "unaccepted_inputs": list(self.unaccepted_inputs),
            "input_problems": [{"path": p, "problem": d} for p, d in self.input_problems],
        }


@dataclass(frozen=True)
class ModelSelection:
    """The outcome of selection over a registry. Deterministic, in registry order."""

    candidates: tuple[CandidateAssessment, ...]

    @property
    def selected(self) -> CandidateAssessment | None:
        chosen = [c for c in self.candidates if c.status is CandidateStatus.SELECTED]
        return chosen[0] if chosen else None

    @property
    def matched(self) -> tuple[CandidateAssessment, ...]:
        return tuple(c for c in self.candidates if c.status is not CandidateStatus.NOT_A_CANDIDATE)

    @property
    def ambiguous(self) -> tuple[CandidateAssessment, ...]:
        return tuple(c for c in self.candidates if c.status is CandidateStatus.VIABLE)

    @property
    def rejected(self) -> tuple[CandidateAssessment, ...]:
        return tuple(c for c in self.candidates if c.status is CandidateStatus.REJECTED)

    def to_dict(self) -> dict[str, Any]:
        selected = self.selected
        return {
            "selected": None if selected is None else selected.capability_id,
            "ambiguous": [c.capability_id for c in self.ambiguous],
            "candidates": [c.to_dict() for c in self.candidates],
        }


# ---------------------------------------------------------------------------
# Inputs, instances, activation
# ---------------------------------------------------------------------------


def supplied_indices(claim_paths: Iterable[str], section: str) -> tuple[int, ...]:
    """Element indices the claim addresses in array ``section`` (``stages[]``)."""
    head = section[: -len("[]")]
    found = set()
    for path in claim_paths:
        if path.startswith(head + "["):
            match = _INDEX.match(path[len(head):])
            if match:
                found.add(int(match.group(1)))
    return tuple(sorted(found))


def concrete(path: str, index: int | None) -> str:
    """``stages[].x`` at element 2 -> ``stages[2].x``. Global paths are unchanged."""
    return path if index is None else path.replace("[]", f"[{index}]", 1)


def active_models(declaration: CapabilityDeclaration, claim_paths: Iterable[str]) -> tuple[ModelUse, ...]:
    paths = tuple(declared_path(p) for p in claim_paths)
    return tuple(
        model
        for model in declaration.models
        if model.always_active
        or any(p == prefix or p.startswith(prefix + ".") for prefix in model.activation for p in paths)
    )


def _instances(model: ModelUse, claim_paths: Iterable[str]) -> tuple[int | None, ...]:
    if model.instance_section is None:
        return (None,)
    indices = supplied_indices(claim_paths, model.instance_section)
    return indices or (0,)


# ---------------------------------------------------------------------------
# Pre-execution applicability of one model instance
# ---------------------------------------------------------------------------


def _model_inputs(declaration: CapabilityDeclaration, model_id: str) -> tuple[InputDeclaration, ...]:
    return tuple(i for i in declaration.inputs if i.model_id == model_id)


def assess_model(
    declaration: CapabilityDeclaration,
    model: ModelUse,
    index: int | None,
    supplied: Mapping[str, Any],
) -> ModelApplicability:
    """Assess one model instance over exactly the inputs the claim supplied to it."""
    instance = None if index is None else f"{model.instance_section[:-2]}[{index}]"
    definition = model.definition
    unassessable = declaration.unassessable(model.model_id)
    feeds = _model_inputs(declaration, model.model_id)

    def path_of(item: InputDeclaration) -> str:
        return concrete(item.path, index if item.array_section == model.instance_section else None)

    context = {}
    for item in feeds:
        value = supplied.get(path_of(item))
        if value is not None:
            context[item.model_input] = value

    base = dict(
        model_id=model.model_id,
        version=model.version,
        instance=instance,
        assumptions=model.assumptions,
        exclusions=model.exclusions,
    )
    if definition is None or not definition.validity.conditions:
        return ModelApplicability(
            status=ValidityStatus.UNKNOWN,
            conditions=(
                ConditionStatus(
                    condition="*",
                    outcome="unknown",
                    basis=UnknownBasis.DECLARED_UNASSESSABLE,
                    note=(
                        "the model declares no validity conditions: absence of declared "
                        "limits is not evidence of unlimited validity"
                        if definition is not None
                        else "the declaration carries no live model definition to assess"
                    ),
                ),
            ),
            **base,
        )
    try:
        assessment = definition.validity.assess(declared=context, record_values=True)
    except ScientificCoreError as exc:
        return ModelApplicability(
            status=ValidityStatus.UNKNOWN,
            conditions=(ConditionStatus("*", "unknown", basis=UnknownBasis.NOT_ASSESSABLE, note=str(exc)),),
            **base,
        )

    by_name = {c.name: c for c in definition.validity.conditions}
    reasons = {u.name: u.reason for u in assessment.unknown_reasons}
    statuses: dict[str, ConditionStatus] = {}

    def missing_for(name: str) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        """(direct missing, advisory missing, alternatives) for one condition."""
        keys = getattr(by_name[name], "context_keys", frozenset({name}))
        direct = [item for item in feeds if item.model_input in keys]
        measured = [item for item in feeds if name in item.unlocks_conditions and item not in direct]
        direct_missing = sorted({path_of(i) for i in direct if path_of(i) not in supplied})
        advisory = sorted({path_of(i) for i in measured if path_of(i) not in supplied})
        alternatives = sorted(
            {
                concrete(a, index if "[]" in a else None)
                for i in direct + measured
                if path_of(i) not in supplied
                for a in i.alternative_to
            }
        )
        return tuple(direct_missing), tuple(advisory), tuple(alternatives)

    def classify(name: str, seen: frozenset[str] = frozenset()) -> ConditionStatus:
        if name in statuses:
            return statuses[name]
        if name in assessment.satisfied:
            return ConditionStatus(name, "satisfied")
        if name in assessment.violated:
            condition = by_name[name]
            return ConditionStatus(
                name,
                "violated",
                declared=condition.to_dict(),
                note="violated on the inputs the claim states",
            )
        reason = reasons.get(name)
        if name in unassessable:
            return ConditionStatus(name, "unknown", reason, UnknownBasis.DECLARED_UNASSESSABLE, note=unassessable[name])
        if reason is UnknownReason.NOT_SUPPLIED:
            missing, advisory, alternatives = missing_for(name)
            if missing:
                return ConditionStatus(name, "unknown", reason, UnknownBasis.MISSING_CONTEXT, missing, alternatives)
            return ConditionStatus(
                name, "unknown", reason, UnknownBasis.PENDING_EXECUTION,
                alternatives=alternatives if advisory else (),
                advisory_inputs=advisory,
            )
        if reason is UnknownReason.PREREQUISITE_NOT_ESTABLISHED:
            requires = tuple(getattr(by_name[name], "requires", ()) or ())
            upstream = [classify(r, seen | {name}) for r in requires if r not in seen]
            missing = tuple(sorted({p for u in upstream for p in u.missing_inputs}))
            if any(u.basis is UnknownBasis.MISSING_CONTEXT for u in upstream):
                return ConditionStatus(name, "unknown", reason, UnknownBasis.MISSING_CONTEXT, missing)
            if any(u.basis is UnknownBasis.DECLARED_UNASSESSABLE for u in upstream):
                return ConditionStatus(name, "unknown", reason, UnknownBasis.DECLARED_UNASSESSABLE)
            return ConditionStatus(name, "unknown", reason, UnknownBasis.PENDING_EXECUTION)
        return ConditionStatus(name, "unknown", reason, UnknownBasis.NOT_ASSESSABLE)

    for condition in definition.validity.conditions:
        statuses[condition.name] = classify(condition.name)

    return ModelApplicability(
        status=assessment.status,
        conditions=tuple(statuses[c.name] for c in definition.validity.conditions),
        **base,
    )


# ---------------------------------------------------------------------------
# One candidate
# ---------------------------------------------------------------------------


def assess_candidate(
    declaration: CapabilityDeclaration, match: CapabilityMatch, claim: ScientificClaim
) -> CandidateAssessment:
    """Everything that decides whether ``declaration`` may bear evidence for ``claim``."""
    base = dict(
        capability_id=declaration.capability_id,
        version=declaration.version,
        digest=declaration.digest,
        match=match,
    )
    if not match.matched:
        return CandidateAssessment(status=CandidateStatus.NOT_A_CANDIDATE, **base)

    supplied = dict(claim.supplied_inputs)
    rejections: list[tuple[RejectionReason, str]] = []

    # Every supplied input must be one this capability reads; otherwise the
    # claim would be answered with part of what it states silently dropped.
    # The target's input_ref is exempt: the comparison reads it, not the run.
    exempt = {claim.target.input_ref} if claim.target.input_ref else set()
    unaccepted = sorted(p for p in supplied if p not in exempt and declaration.input(p) is None)
    if unaccepted:
        rejections.append(
            (
                RejectionReason.UNACCEPTED_INPUT,
                f"{declaration.capability_id} declares no input {unaccepted}; answering would drop them",
            )
        )
    problems = []
    for path in sorted(supplied):
        item = declaration.input(path)
        if item is None or path in exempt:
            continue
        problem = input_problem(item, path, supplied[path])
        if problem is not None:
            problems.append((path, problem))
    if problems:
        rejections.append((RejectionReason.INVALID_INPUT, "; ".join(p for _, p in problems)))

    produced = declaration.produced(claim.qoi.name)
    extra_qualifiers = sorted(set(claim.qoi.qualifiers) - ({produced.instance_key} if produced.instance_key else set()))
    if extra_qualifiers:
        rejections.append(
            (
                RejectionReason.UNUSED_QUALIFIER,
                f"{declaration.capability_id} reports {claim.qoi.name!r} "
                + (f"per {produced.instance_key!r}" if produced.instance_key else "once per case")
                + f"; qualifier(s) {extra_qualifiers} would select nothing",
            )
        )

    paths = tuple(supplied)
    models = tuple(
        assess_model(declaration, model, index, supplied if not problems else {k: v for k, v in supplied.items() if k not in dict(problems)})
        for model in active_models(declaration, paths)
        for index in _instances(model, paths)
    )
    outside = [m for m in models if m.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN]
    if outside:
        rejections.append(
            (
                RejectionReason.OUTSIDE_VALIDITY,
                "; ".join(
                    f"{m.model_id}@{m.version}{'' if m.instance is None else f' [{m.instance}]'} violates "
                    f"{[c.condition for c in m.violated]}"
                    for m in outside
                ),
            )
        )
    unassessable = [m for m in models if UnknownBasis.DECLARED_UNASSESSABLE in m.bases]
    if unassessable:
        rejections.append(
            (
                RejectionReason.VALIDITY_UNASSESSABLE,
                "; ".join(
                    f"{m.model_id}@{m.version} cannot establish its applicability here: "
                    f"{[c.condition for c in m.unknown_of(UnknownBasis.DECLARED_UNASSESSABLE)]}"
                    for m in unassessable
                ),
            )
        )

    if outside:
        applicability = ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    elif any(m.status is not ValidityStatus.IN_DOMAIN for m in models) or not models:
        applicability = ValidityStatus.UNKNOWN
    else:
        applicability = ValidityStatus.IN_DOMAIN

    return CandidateAssessment(
        status=CandidateStatus.REJECTED if rejections else CandidateStatus.VIABLE,
        applicability=applicability,
        models=models,
        rejections=tuple(rejections),
        unaccepted_inputs=tuple(unaccepted),
        input_problems=tuple(problems),
        **base,
    )


def _with_status(candidate: CandidateAssessment, status: CandidateStatus) -> CandidateAssessment:
    from dataclasses import replace

    return replace(candidate, status=status)


def select_capability(claim: ScientificClaim, registry: CapabilityRegistry) -> ModelSelection:
    """Assess every registered capability against ``claim`` and select at most one."""
    matches = registry.match(
        quantity=claim.qoi.name,
        dimension=claim.qoi.dimension,
        required=claim.required_capabilities,
        claim_kind=claim.kind,
    )
    assessed = [assess_candidate(registry.get(m.capability_id), m, claim) for m in matches]
    viable = [c for c in assessed if c.status is CandidateStatus.VIABLE]
    known = [c for c in viable if c.applicability is ValidityStatus.IN_DOMAIN]
    keep = {c.capability_id for c in (known or viable)}
    out = []
    for candidate in assessed:
        if candidate.status is CandidateStatus.VIABLE:
            if candidate.capability_id not in keep:
                candidate = _with_status(candidate, CandidateStatus.OUTRANKED)
            elif len(keep) == 1:
                candidate = _with_status(candidate, CandidateStatus.SELECTED)
        out.append(candidate)
    return ModelSelection(tuple(out))


__all__ = [
    "CandidateAssessment",
    "CandidateStatus",
    "ConditionStatus",
    "ModelApplicability",
    "ModelSelection",
    "RejectionReason",
    "UnknownBasis",
    "active_models",
    "assess_candidate",
    "assess_model",
    "concrete",
    "select_capability",
    "supplied_indices",
]
