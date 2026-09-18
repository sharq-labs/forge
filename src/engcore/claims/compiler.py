"""CORE-2 -- the scientific claim compiler: structured claim in, execution readiness out.

``compile_claim`` reads a :class:`~engcore.claims.contract.ScientificClaim` (or
its serialized form) and a :class:`~engcore.claims.capabilities.CapabilityRegistry`
and decides, **without running anything**, whether the claim can be executed:

``READY``                   one capability is selected, every input it requires
                            is stated, and its models' applicability is decided
                            or pending only on state the run computes.
``NEEDS_INPUT``             one capability is selected, and a required input,
                            an input that would make a validity condition
                            assessable, the target, or the reported element is
                            missing. Nothing is defaulted in its place.
``AMBIGUOUS``               more than one capability qualifies, or the quantity
                            is reported per element and the claim names none.
``UNSUPPORTED_CAPABILITY``  no registered capability produces the quantity with
                            the claim's dimension, capabilities and shape, or
                            every candidate was rejected (a model OUTSIDE its
                            validated domain, applicability that can never be
                            established, inputs it would silently drop).
``REFUSED``                 the request is not a well-formed claim.

It also predicts, from declarations only, the gaps that will keep a READY claim
from being SUPPORTED -- a required level no route here attains, a required
uncertainty channel this capability never quantifies, a discrepancy the rule
will not accept -- so a caller learns before the run that the answer can at
best be INSUFFICIENT_EVIDENCE, and why.

The compiler is not a planner and not a parser. It never reads the claim's prose
statement, never infers a missing value, and never ranks two applicable
capabilities: ambiguity is reported, with the declared identifiers that would
separate the candidates.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..scientific.serialization import schema_string
from ..scientific.units.quantity import Quantity, dimensionality
from ..sria.uncertainty import DiscrepancyKind
from ._records import tagged_digest
from .capabilities import CapabilityDeclaration, CapabilityRegistry, MismatchReason
from .contract import ScientificClaim
from .errors import ClaimContractError
from .repair import RepairAction, RepairKind, merge_repairs
from .uq_studies import study_spec
from .selection import (
    CandidateAssessment,
    CandidateStatus,
    ModelSelection,
    RejectionReason,
    UnknownBasis,
    concrete,
    select_capability,
    supplied_indices,
)

COMPILED_CLAIM_SCHEMA = schema_string("compiled_claim")
_TAG = "crafty.claims.compiled/1"


class CompilationStatus(str, Enum):
    READY = "ready"
    NEEDS_INPUT = "needs_input"
    AMBIGUOUS = "ambiguous"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    REFUSED = "refused"


#: Least ready first. When two findings disagree, the less ready one wins.
READINESS_ORDER: tuple[CompilationStatus, ...] = (
    CompilationStatus.REFUSED,
    CompilationStatus.UNSUPPORTED_CAPABILITY,
    CompilationStatus.AMBIGUOUS,
    CompilationStatus.NEEDS_INPUT,
    CompilationStatus.READY,
)


def readiness_rank(status: CompilationStatus) -> int:
    return READINESS_ORDER.index(CompilationStatus(status))


class GapKind(str, Enum):
    """A gap predicted from declarations that a run cannot close."""

    LEVEL_UNATTAINABLE = "level_unattainable"
    CHANNEL_UNQUANTIFIED = "channel_unquantified"
    DISCREPANCY_UNSUPPORTED = "discrepancy_unsupported"
    APPLICABILITY_PENDING = "applicability_pending"
    #: Pending conditions the system measured may need an input the claim omits.
    APPLICABILITY_AT_RISK = "applicability_at_risk"


@dataclass(frozen=True)
class PredictedGap:
    kind: GapKind
    target: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "target": self.target, "detail": self.detail}


@dataclass(frozen=True)
class CompiledClaim:
    """The compiler's answer. Derived, deterministic, and recomputed rather than trusted."""

    status: CompilationStatus
    claim: ScientificClaim | None
    registry_digest: str
    reasons: tuple[str, ...]
    repairs: tuple[RepairAction, ...]
    selection: ModelSelection | None = None
    target: Quantity | None = None
    instance: str | None = None
    required_inputs: tuple[str, ...] = ()
    missing_inputs: tuple[str, ...] = ()
    predicted_gaps: tuple[PredictedGap, ...] = ()
    claim_error: str | None = None

    @property
    def ready(self) -> bool:
        return self.status is CompilationStatus.READY

    @property
    def capability(self) -> CandidateAssessment | None:
        return None if self.selection is None else self.selection.selected

    def to_dict(self) -> dict[str, Any]:
        capability = self.capability
        return {
            "schema": COMPILED_CLAIM_SCHEMA,
            "status": self.status.value,
            "claim_identity": None if self.claim is None else self.claim.identity_digest,
            "claim_record": None if self.claim is None else self.claim.record_digest,
            "claim_error": self.claim_error,
            "registry_digest": self.registry_digest,
            "qoi": None
            if self.claim is None
            else {
                "name": self.claim.qoi.name,
                "units": self.claim.qoi.units,
                "dimension": self.claim.qoi.dimension,
                "qualifiers": dict(sorted(self.claim.qoi.qualifiers.items())),
            },
            "comparison": None
            if self.claim is None
            else {
                "kind": self.claim.kind.value,
                "operator": self.claim.operator.value,
                "target": None if self.target is None else self.target.to_dict(),
                "target_ref": self.claim.target.input_ref,
                "tolerance": None if self.claim.tolerance is None else self.claim.tolerance.to_dict(),
            },
            "capability": None
            if capability is None
            else {"capability_id": capability.capability_id, "version": capability.version, "digest": capability.digest},
            "instance": self.instance,
            "required_inputs": list(self.required_inputs),
            "missing_inputs": list(self.missing_inputs),
            "predicted_gaps": [g.to_dict() for g in self.predicted_gaps],
            "reasons": list(self.reasons),
            "repairs": [r.to_dict() for r in self.repairs],
            "selection": None if self.selection is None else self.selection.to_dict(),
        }

    @property
    def digest(self) -> str:
        return tagged_digest(_TAG, self.to_dict())


# ---------------------------------------------------------------------------
# Pieces
# ---------------------------------------------------------------------------


def _refused(reason: str, registry: CapabilityRegistry, claim: ScientificClaim | None = None) -> CompiledClaim:
    return CompiledClaim(
        status=CompilationStatus.REFUSED,
        claim=claim,
        registry_digest=registry.digest,
        reasons=(reason,),
        repairs=(RepairAction(RepairKind.RESTATE_CLAIM, "claim", reason, source="contract:scientific_claim"),),
        claim_error=reason,
    )


def _unsupported_repairs(claim: ScientificClaim, registry: CapabilityRegistry, selection: ModelSelection) -> list[RepairAction]:
    repairs: list[RepairAction] = []
    same_name = [d for d in registry.producing(claim.qoi.name)]
    detail: dict[str, Any] = {
        "quantity": claim.qoi.name,
        "dimension": claim.qoi.dimension,
        "required_capabilities": sorted(c.identifier for c in claim.required_capabilities),
        "claim_shape": claim.kind.value,
        "produced_elsewhere": sorted(
            f"{d.capability_id}:{d.produced(claim.qoi.name).dimension}" for d in same_name
        ),
        "registered_quantities": list(registry.produced_quantities()),
    }
    if not selection.matched:
        repairs.append(
            RepairAction(
                RepairKind.EXTEND_CAPABILITY,
                claim.qoi.name,
                "no registered capability produces this quantity with the claim's dimension, "
                "scientific capabilities and claim shape",
                source=f"registry:{registry.digest}",
                detail=detail,
            )
        )
        for candidate in selection.candidates:
            reasons = {r for r, _ in candidate.match.reasons}
            if MismatchReason.CAPABILITY_NOT_PROVIDED in reasons and len(reasons) == 1:
                repairs.append(
                    RepairAction(
                        RepairKind.NARROW_CAPABILITY,
                        candidate.capability_id,
                        "this capability produces the quantity but does not provide every "
                        "required scientific capability",
                        source=f"capability:{candidate.capability_id}",
                        detail={"reasons": [d for _, d in candidate.match.reasons]},
                    )
                )
    return repairs


def _rejection_repairs(candidate: CandidateAssessment) -> list[RepairAction]:
    repairs: list[RepairAction] = []
    source = f"capability:{candidate.capability_id}"
    for path in candidate.unaccepted_inputs:
        repairs.append(
            RepairAction(
                RepairKind.REMOVE_UNACCEPTED_INPUT,
                path,
                f"{candidate.capability_id} does not accept this input; answering the claim would drop it",
                required_for=(candidate.capability_id,),
                source=source,
            )
        )
    for path, problem in candidate.input_problems:
        repairs.append(RepairAction(RepairKind.CORRECT_INPUT, path, problem, required_for=(candidate.capability_id,), source=source))
    for model in candidate.models:
        for condition in model.violated:
            declared = dict(condition.declared or {})
            repairs.append(
                RepairAction(
                    RepairKind.MOVE_INSIDE_VALIDITY,
                    condition.condition,
                    f"{model.model_id}@{model.version} is outside its declared validity on the stated inputs",
                    required_for=(f"model:{model.model_id}",),
                    source=f"model:{model.model_id}@{model.version}#condition:{condition.condition}",
                    detail={"declared_condition": declared, "instance": model.instance},
                )
            )
        for condition in model.unknown_of(UnknownBasis.DECLARED_UNASSESSABLE):
            repairs.append(
                RepairAction(
                    RepairKind.EXTEND_CAPABILITY,
                    f"{candidate.capability_id}#{model.model_id}#{condition.condition}",
                    condition.note or "this capability never assembles the context this condition reads",
                    required_for=(f"model:{model.model_id}",),
                    source=source,
                )
            )
    return repairs


def _distinguishing(candidates: tuple[CandidateAssessment, ...], registry: CapabilityRegistry) -> list[RepairAction]:
    repairs = []
    provided = {c.capability_id: registry.get(c.capability_id).provided_capabilities for c in candidates}
    for candidate in candidates:
        others = set().union(*(p for cid, p in provided.items() if cid != candidate.capability_id))
        unique = sorted(c.identifier for c in provided[candidate.capability_id] - others)
        repairs.append(
            RepairAction(
                RepairKind.NARROW_CAPABILITY,
                candidate.capability_id,
                "several capabilities qualify; require a scientific capability only this one provides"
                if unique
                else "several capabilities qualify and this one provides nothing the others lack; "
                "distinguish it by the inputs the claim states",
                alternatives=tuple(unique),
                source=f"capability:{candidate.capability_id}",
                detail={"provides": sorted(c.identifier for c in provided[candidate.capability_id])},
            )
        )
    return repairs


def _required_paths(declaration: CapabilityDeclaration, supplied_paths: tuple[str, ...]) -> list[str]:
    paths = []
    for item in declaration.required_inputs:
        section = item.array_section
        if section is None:
            paths.append(item.path)
        else:
            for index in supplied_indices(supplied_paths, section) or (0,):
                paths.append(concrete(item.path, index))
    return sorted(paths)


def _instance(
    claim: ScientificClaim, declaration: CapabilityDeclaration
) -> tuple[str | None, list[str], list[RepairAction], CompilationStatus | None]:
    """Which reported element the claim is about; or why that is not yet decided."""
    produced = declaration.produced(claim.qoi.name)
    if produced.instance_key is None:
        return None, [], [], None
    supplied = claim.supplied_inputs
    indices = supplied_indices(tuple(supplied), produced.instance_path.split("[]")[0] + "[]")
    ids = [supplied.get(concrete(produced.instance_path, i)) for i in indices]
    ids = [i for i in ids if isinstance(i, str)]
    wanted = claim.qoi.qualifiers.get(produced.instance_key)
    source = f"capability:{declaration.capability_id}#produces:{produced.name}"
    if wanted is not None:
        if wanted in ids:
            return wanted, [], [], None
        return (
            None,
            [f"the claim is about {produced.instance_key}={wanted!r}, which the stated inputs do not describe"],
            [
                RepairAction(
                    RepairKind.SELECT_INSTANCE,
                    produced.instance_key,
                    f"{produced.name} is reported per {produced.instance_key}; the claim names an element the inputs do not describe",
                    alternatives=tuple(ids),
                    source=source,
                    detail={"requested": wanted, "instance_path": produced.instance_path},
                )
            ],
            CompilationStatus.NEEDS_INPUT,
        )
    if len(ids) == 1:
        return ids[0], [], [], None
    if len(ids) > 1:
        return (
            None,
            [f"{produced.name} is reported once per {produced.instance_key} and the claim names none of {ids}"],
            [
                RepairAction(
                    RepairKind.SELECT_INSTANCE,
                    produced.instance_key,
                    f"{produced.name} is reported per {produced.instance_key}; name the element the claim is about",
                    alternatives=tuple(ids),
                    source=source,
                )
            ],
            CompilationStatus.AMBIGUOUS,
        )
    return None, [], [], None  # no element described yet: the missing required input says so


def _predicted_gaps(claim: ScientificClaim, declaration: CapabilityDeclaration, candidate: CandidateAssessment) -> tuple[list[PredictedGap], list[RepairAction]]:
    gaps: list[PredictedGap] = []
    repairs: list[RepairAction] = []
    source = f"capability:{declaration.capability_id}"
    attainable = declaration.attainable()
    for level in claim.evidence.required_levels:
        if level not in attainable:
            gaps.append(
                PredictedGap(
                    GapKind.LEVEL_UNATTAINABLE,
                    level.value,
                    f"{declaration.capability_id} declares no route that can attain {level.value}; "
                    f"attainable here: {sorted(l.value for l in attainable)}",
                )
            )
            repairs.append(
                RepairAction(
                    RepairKind.PROVIDE_EVIDENCE,
                    level.value,
                    "the decision requires this level and no declared route of the selected capability attains it",
                    required_for=(f"decision:{claim.decision.decision_id}",),
                    source=source,
                    detail={"attainable": [a.to_dict() for a in declaration.attainable_levels]},
                )
            )
    for channel in claim.uncertainty.ordered_channels():
        study, unavailable = study_spec(declaration, claim, channel)
        if study is None:
            gaps.append(
                PredictedGap(
                    GapKind.CHANNEL_UNQUANTIFIED,
                    channel.value,
                    f"{declaration.capability_id} cannot quantify the {channel.value} uncertainty of "
                    f"{claim.qoi.name} for this claim ({unavailable}): {declaration.uncertainty.basis}",
                )
            )
            repairs.append(
                RepairAction(
                    RepairKind.PROVIDE_UNCERTAINTY,
                    channel.value,
                    "the decision requires this uncertainty channel quantified with an attributed source; "
                    "an UNKNOWN channel is not zero",
                    required_for=(f"decision:{claim.decision.decision_id}",),
                    source=source,
                    detail={"basis": declaration.uncertainty.basis},
                )
            )
    if claim.uncertainty.require_supported_discrepancy and claim.discrepancy.kind is not DiscrepancyKind.CONSTRAINED_PRIOR:
        gaps.append(
            PredictedGap(
                GapKind.DISCREPANCY_UNSUPPORTED,
                claim.discrepancy.kind.value,
                "the decision requires model-form discrepancy to be supported; UNKNOWN is not supported "
                "and a ZERO_DECLARED assumption is supported only by evidence, never by declaration",
            )
        )
        repairs.append(
            RepairAction(
                RepairKind.SUPPORT_DISCREPANCY,
                "discrepancy",
                "declare a constrained prior with a reference, or supply evidence that supports the zero assumption",
                required_for=(f"decision:{claim.decision.decision_id}",),
                source="sria:model_discrepancy_check",
                detail={"declared": claim.discrepancy.to_dict()},
            )
        )
    pending = sorted(
        {f"{m.model_id}#{c.condition}" for m in candidate.models for c in m.unknown_of(UnknownBasis.PENDING_EXECUTION)}
    )
    if pending:
        gaps.append(
            PredictedGap(
                GapKind.APPLICABILITY_PENDING,
                "validity",
                f"{len(pending)} condition(s) read state the run computes and are decided by the run's own "
                f"assessment: {pending}",
            )
        )
    source = f"capability:{declaration.capability_id}"
    for model in candidate.models:
        for condition in model.unknown_of(UnknownBasis.PENDING_EXECUTION):
            if not condition.advisory_inputs:
                continue
            gaps.append(
                PredictedGap(
                    GapKind.APPLICABILITY_AT_RISK,
                    f"{model.model_id}#{condition.condition}",
                    f"the system measured that omitting {list(condition.advisory_inputs)} can leave this "
                    f"condition UNKNOWN; whether this case needs them is decided by the run",
                )
            )
            for path in condition.advisory_inputs:
                item = declaration.input(path)
                repairs.append(
                    RepairAction(
                        RepairKind.SUPPLY_VALIDITY_EVIDENCE,
                        path,
                        "may be needed to assess this condition (advisory: the run decides) -- "
                        + (item.description if item is not None and item.description else path),
                        required_for=(f"model:{model.model_id}#condition:{condition.condition}",),
                        alternatives=condition.alternatives,
                        source=f"{source}#input:{declared_path_of(path)}",
                        detail={
                            "advisory": True,
                            "dimension": None if item is None else item.dimension,
                            "unit_exemplar": None if item is None else item.unit_exemplar,
                        },
                    )
                )
    return gaps, repairs


# ---------------------------------------------------------------------------
# The compiler
# ---------------------------------------------------------------------------


def compile_claim(claim: ScientificClaim | Mapping[str, Any], registry: CapabilityRegistry) -> CompiledClaim:
    """Decide whether a structured claim can be executed, and what stops it if not."""
    if not isinstance(registry, CapabilityRegistry):
        raise TypeError("compile_claim needs a CapabilityRegistry")
    if not isinstance(claim, ScientificClaim):
        try:
            claim = ScientificClaim.from_dict(claim)
        except ClaimContractError as exc:
            return _refused(str(exc), registry)

    # The target as a comparable quantity, or why it is not one yet.
    target = claim.resolve_target()
    reasons: list[str] = []
    repairs: list[RepairAction] = []
    status = CompilationStatus.READY
    if claim.target.input_ref is not None:
        stated = claim.supplied_inputs.get(claim.target.input_ref)
        if stated is not None and (not isinstance(stated, Quantity) or dimensionality(stated.units) != claim.qoi.dimension):
            return _refused(
                f"target input {claim.target.input_ref!r} is {stated!r}, which is not a quantity of "
                f"[{claim.qoi.dimension}] and cannot be compared with {claim.qoi.name!r}",
                registry,
                claim,
            )

    selection = select_capability(claim, registry)
    selected = selection.selected

    if selected is None:
        if selection.ambiguous:
            names = [c.capability_id for c in selection.ambiguous]
            return CompiledClaim(
                status=CompilationStatus.AMBIGUOUS,
                claim=claim,
                registry_digest=registry.digest,
                reasons=(f"{len(names)} capabilities qualify for this claim: {names}",),
                repairs=merge_repairs(_distinguishing(selection.ambiguous, registry)),
                selection=selection,
                target=target,
            )
        rejected = selection.rejected
        # A candidate rejected ONLY because a stated value is malformed is the
        # capability the claim addresses: the claim is refused with the
        # correction, not reported as a missing capability.
        fixable = [
            c for c in rejected if {reason for reason, _ in c.rejections} == {RejectionReason.INVALID_INPUT}
        ]
        if fixable:
            return CompiledClaim(
                status=CompilationStatus.REFUSED,
                claim=claim,
                registry_digest=registry.digest,
                reasons=tuple(f"{c.capability_id}: {d}" for c in fixable for _, d in c.rejections),
                repairs=merge_repairs([r for c in fixable for r in _rejection_repairs(c)]),
                selection=selection,
                target=target,
            )
        return CompiledClaim(
            status=CompilationStatus.UNSUPPORTED_CAPABILITY,
            claim=claim,
            registry_digest=registry.digest,
            reasons=tuple(
                [f"{c.capability_id}: {d}" for c in rejected for _, d in c.rejections]
                or [
                    f"no registered capability produces {claim.qoi.name!r} as [{claim.qoi.dimension}] "
                    f"for a {claim.kind.value} claim"
                    + (
                        f" providing {sorted(c.identifier for c in claim.required_capabilities)}"
                        if claim.required_capabilities
                        else ""
                    )
                ]
            ),
            repairs=merge_repairs(
                _unsupported_repairs(claim, registry, selection) + [r for c in rejected for r in _rejection_repairs(c)]
            ),
            selection=selection,
            target=target,
        )

    declaration = registry.get(selected.capability_id)
    supplied = claim.supplied_inputs
    source = f"capability:{declaration.capability_id}"

    required = _required_paths(declaration, tuple(supplied))
    missing = [p for p in required if p not in supplied]
    for path in missing:
        item = declaration.input(path)
        declared_unknown = path in claim.missing_inputs
        repairs.append(
            RepairAction(
                RepairKind.SUPPLY_INPUT,
                path,
                (item.description or f"{declaration.capability_id} requires {path}")
                + (" (the claim states it is unknown; it is not defaulted)" if declared_unknown else ""),
                required_for=("execution",) + ((f"model:{item.model_id}",) if item.model_id else ()),
                source=f"{source}#input:{item.path}",
                detail={
                    "kind": item.kind.value,
                    "role": item.role.value,
                    "dimension": item.dimension,
                    "unit_exemplar": item.unit_exemplar,
                },
            )
        )
    if missing:
        reasons.append(f"required input(s) not stated: {missing}")
        status = CompilationStatus.NEEDS_INPUT

    context_missing = []
    for model in selected.models:
        for condition in model.unknown_of(UnknownBasis.MISSING_CONTEXT):
            for path in condition.missing_inputs:
                context_missing.append(path)
                item = declaration.input(path)
                repairs.append(
                    RepairAction(
                        RepairKind.SUPPLY_VALIDITY_EVIDENCE,
                        path,
                        (item.description if item is not None and item.description else f"unlocks {condition.condition}"),
                        required_for=(f"model:{model.model_id}#condition:{condition.condition}",),
                        alternatives=condition.alternatives,
                        source=f"{source}#input:{declared_path_of(path)}",
                        detail={
                            "dimension": None if item is None else item.dimension,
                            "unit_exemplar": None if item is None else item.unit_exemplar,
                            "unknown_reason": None if condition.reason is None else condition.reason.value,
                        },
                    )
                )
    context_missing = sorted(set(context_missing) - set(missing))
    if context_missing:
        reasons.append(
            f"input(s) that decide model applicability are not stated: {context_missing}; "
            f"without them the selected models' applicability stays UNKNOWN"
        )
        status = CompilationStatus.NEEDS_INPUT

    if claim.target.input_ref is not None and target is None:
        reasons.append(f"the target names input {claim.target.input_ref!r}, which the claim does not state")
        repairs.append(
            RepairAction(
                RepairKind.RESOLVE_TARGET,
                claim.target.input_ref,
                "the comparison's bound is this input; state it as a quantity of the QOI's dimension",
                required_for=("comparison",),
                source="contract:scientific_claim#target",
                detail={"dimension": claim.qoi.dimension},
            )
        )
        status = CompilationStatus.NEEDS_INPUT

    instance, instance_reasons, instance_repairs, instance_status = _instance(claim, declaration)
    reasons += instance_reasons
    repairs += instance_repairs
    if instance_status is not None and readiness_rank(instance_status) < readiness_rank(status):
        status = instance_status

    gaps, gap_repairs = _predicted_gaps(claim, declaration, selected)
    repairs += gap_repairs

    return CompiledClaim(
        status=status,
        claim=claim,
        registry_digest=registry.digest,
        reasons=tuple(reasons) or (f"ready: {declaration.capability_id} selected",),
        repairs=merge_repairs(repairs),
        selection=selection,
        target=target,
        instance=instance,
        required_inputs=tuple(required),
        missing_inputs=tuple(sorted(set(missing) | set(context_missing))),
        predicted_gaps=tuple(gaps),
    )


def declared_path_of(path: str) -> str:
    from .capabilities import declared_path

    return declared_path(path)


__all__ = [
    "COMPILED_CLAIM_SCHEMA",
    "READINESS_ORDER",
    "CompilationStatus",
    "CompiledClaim",
    "GapKind",
    "PredictedGap",
    "compile_claim",
    "readiness_rank",
]
