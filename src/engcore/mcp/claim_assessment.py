"""Transport for structured scientific-claim assessment: one canonical decision path.

Every MCP claim tool decides through :func:`engcore.claims.assess_claim` and
returns its record unchanged. Nothing here builds a charter, an obligation set,
an authority, an Arbiter or a verdict.

Trust Repair Pass 1 (Review 3, R3-02). This module used to run its own SRIA
decision for a ``(system, case, quantity)`` request. That decision:

- read the run's report-wide ``attained_levels``, so a level established for one
  quantity was certified for every quantity;
- never compared the value with anything, so a false decision statement was
  ``valid``;
- skipped uncertainty obligations, the budget, the discrepancy check and policy.

On the same input it returned ``valid`` where the canonical path returned
INSUFFICIENT_EVIDENCE or CONTRADICTED. It was a second authority with a weaker
policy, so it was removed rather than repaired.

Two request shapes are accepted, and both reach the canonical path:

- ``{"claim": <scientific_claim/1>}`` -- exactly what ``assess_scientific_claim``
  takes.
- The case-based shape, ``{"system", "case", "quantity_name", "decision",
  "required_levels", "discrepancy", "comparison", "uncertainty"[,
  "decision_context"]}``.
  - ``comparison`` is ``{"operator": "<"|"<="|">"|">="|"==", "target":
    <quantity>, "tolerance": <quantity, required for "==">}``.
  - ``uncertainty`` is the caller's explicit ``claim_uncertainty_demand/1``. An
    empty demand is a declaration, never a default this transport makes.
  - The case becomes the claim's inputs through
    :func:`engcore.claims.inputs_from_case`, the inverse of ``build_case`` that
    the claim layer owns.
  - A free-text decision statement without a structured comparison is refused:
    it has no truth value the canonical path can decide, and inventing one would
    be a second authority again.
  - The claim must be routed to the requested system's capability, or the
    answer is refused.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..scientific.results.validation import ValidationLevel
from ..scientific.serialization import schema_string
from ..sria import DiscrepancyKind, ModelDiscrepancy

#: The schema of a refusal this transport returns. A successful assessment is
#: the canonical ``claim_assessment_record`` itself, unchanged.
CLAIM_ASSESSMENT_ERROR_SCHEMA = schema_string("mcp_claim_assessment_error")
#: Kept for import compatibility. Since Trust Repair Pass 1 a successful
#: response carries the canonical record's schema, not this one.
CLAIM_ASSESSMENT_SCHEMA = schema_string("mcp_claim_assessment")

_CASE_SHAPE_KEYS = (
    "system", "case", "quantity_name", "decision", "required_levels", "discrepancy", "comparison",
    "uncertainty", "decision_context", "report_index",
)


class ClaimAssessmentError(ValueError):
    """A structured assessment request is incomplete or ambiguous."""


def _mapping(payload: Any, *, name: str) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise ClaimAssessmentError(f"{name} must be an object")
    return payload


def _text(payload: Mapping[str, Any], key: str, *, where: str = "request") -> str:
    value = str(payload.get(key, "")).strip()
    if not value:
        raise ClaimAssessmentError(f"{where}.{key} is required and must be non-empty")
    return value


def _required_levels(payload: Any) -> tuple[ValidationLevel, ...]:
    if isinstance(payload, (str, bytes)) or not isinstance(payload, Sequence):
        raise ClaimAssessmentError("required_levels must be a non-empty array")
    if not payload:
        raise ClaimAssessmentError(
            "required_levels must name at least one evidentiary level; "
            "a decision standard cannot be inferred"
        )
    try:
        levels = tuple(ValidationLevel(item) for item in payload)
    except (TypeError, ValueError) as exc:
        raise ClaimAssessmentError(
            f"required_levels contains an unknown ValidationLevel: {exc}"
        ) from exc
    if ValidationLevel.UNVERIFIED in levels:
        raise ClaimAssessmentError(
            "UNVERIFIED is absence of a level and cannot be a requirement"
        )
    if len(set(levels)) != len(levels):
        raise ClaimAssessmentError("required_levels contains a duplicate level")
    return levels


def _discrepancy(payload: Any) -> ModelDiscrepancy:
    raw = _mapping(payload, name="discrepancy")
    try:
        kind = DiscrepancyKind(_text(raw, "kind", where="discrepancy"))
    except ValueError as exc:
        raise ClaimAssessmentError(f"discrepancy.kind is invalid: {exc}") from exc
    rationale = _text(raw, "rationale", where="discrepancy")
    reference = str(raw.get("reference", "")).strip()
    try:
        return ModelDiscrepancy(kind=kind, reference=reference, rationale=rationale)
    except Exception as exc:
        raise ClaimAssessmentError(f"invalid discrepancy declaration: {exc}") from exc


def _quantity(value: Any, *, where: str) -> Any:
    from ..scientific.units.quantity import Quantity

    try:
        if isinstance(value, str):
            return Quantity.parse(value)
        if isinstance(value, Mapping):
            return Quantity.from_dict(dict(value))
    except Exception as exc:
        raise ClaimAssessmentError(f"{where} is not a quantity: {exc}") from exc
    raise ClaimAssessmentError(f"{where} must be quantity text such as '310 kelvin' or a quantity object")


def claim_from_case_request(request: Mapping[str, Any]) -> Any:
    """The canonical :class:`~engcore.claims.ScientificClaim` a case-based request states.

    Pure input translation: no system is run and nothing is decided. The case
    becomes the claim's inputs through the capability's own ``inputs_from_case``.
    The comparison, levels, decision and discrepancy are the caller's own
    statements. Anything the canonical contract cannot express is refused here
    rather than approximated.
    """
    from ..claims import (
        ClaimKind,
        ClaimTarget,
        DecisionBinding,
        EvidenceRequirement,
        QuantityOfInterest,
        RequestedOutput,
        ScientificClaim,
        UncertaintyDemand,
        inputs_from_case,
    )
    from ..claims.errors import ClaimLayerError
    from ..scientific.ir.constraints import ConstraintOperator
    from .capabilities import production_registry

    system_name = _text(request, "system")
    case = _mapping(request.get("case"), name="case")
    quantity_name = _text(request, "quantity_name")
    decision_raw = _mapping(request.get("decision"), name="decision")
    decision_id = _text(decision_raw, "id", where="decision")
    statement = _text(decision_raw, "statement", where="decision")
    required_levels = _required_levels(request.get("required_levels"))
    discrepancy = _discrepancy(request.get("discrepancy"))
    if request.get("report_index") is not None:
        raise ClaimAssessmentError(
            "report_index is not part of a canonical claim: the claim layer selects the instance "
            "from the claim's own inputs and qualifiers, and this transport will not pick a stage for it"
        )
    if request.get("comparison") is None:
        raise ClaimAssessmentError(
            "comparison is required: a free-text decision statement has no truth value the canonical "
            "claim path can decide. State {operator, target[, tolerance]} or call assess_scientific_claim "
            "with a scientific_claim/1 record"
        )
    # The uncertainty demand is a scientific declaration ("empty is a declaration, not a default"):
    # the transport never makes it for the caller, so the case shape must state it (Review: F5).
    if request.get("uncertainty") is None:
        raise ClaimAssessmentError(
            "uncertainty is required: state the decision's uncertainty demand as a claim_uncertainty_demand/1 "
            "record, e.g. {required_channels: [], coverage_factor: null, require_supported_discrepancy: false} "
            "for a point comparison"
        )
    comparison = _mapping(request.get("comparison"), name="comparison")
    try:
        operator = ConstraintOperator(_text(comparison, "operator", where="comparison"))
    except ValueError as exc:
        raise ClaimAssessmentError(f"comparison.operator is invalid: {exc}") from exc
    target = _quantity(comparison.get("target"), where="comparison.target")
    tolerance = None if comparison.get("tolerance") is None else _quantity(
        comparison.get("tolerance"), where="comparison.tolerance"
    )
    capability_id = f"system.{system_name}"
    registry = production_registry()
    if capability_id not in registry:
        raise ClaimAssessmentError(
            f"system {system_name!r} has no registered claim capability; known: {sorted(d.capability_id for d in registry)}"
        )
    try:
        from ..claims import DecisionContext

        uncertainty_raw = dict(_mapping(request.get("uncertainty"), name="uncertainty"))
        uncertainty_raw.setdefault("schema", "claim_uncertainty_demand/1")
        uncertainty = UncertaintyDemand.from_dict(uncertainty_raw)
        context_raw = request.get("decision_context")
        decision_context = None if context_raw is None else DecisionContext.from_dict(
            _mapping(context_raw, name="decision_context")
        )
        inputs = inputs_from_case(registry.get(capability_id), case)
        return ScientificClaim(
            claim_id=f"mcp-assess:{system_name}:{decision_id}",
            statement=statement,
            kind=ClaimKind.TOLERANCE_BAND if operator is ConstraintOperator.EQUAL else ClaimKind.THRESHOLD,
            qoi=QuantityOfInterest(name=quantity_name, units=str(target.units)),
            operator=operator,
            target=ClaimTarget(value=target),
            tolerance=tolerance,
            required_capabilities=frozenset(),
            operating_context={},
            known_inputs=inputs,
            missing_inputs=frozenset(),
            assumptions=(),
            decision=DecisionBinding(decision_id, statement),
            evidence=EvidenceRequirement(required_levels),
            uncertainty=uncertainty,
            discrepancy=discrepancy,
            requested_outputs=frozenset({RequestedOutput.VERDICT}),
            decision_context=decision_context,
        )
    except (ClaimLayerError, ValueError, TypeError) as exc:
        raise ClaimAssessmentError(f"the request does not state a canonical claim: {exc}") from exc


def assess_structured_claim(
    claim: Any,
    *,
    external: Sequence[Mapping[str, Any]] | None = None,
    empirical_observations: Sequence[Mapping[str, Any]] | None = None,
    model_form_qualification: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The canonical record for one claim under the production registries. The only decision path here."""
    from ..claims.assessment import assess_claim
    from ..claims.external_evidence import PRODUCTION_EXTERNAL_REGISTRY, read_external_record
    from ..claims.measurement_dataset import DatasetObservation
    from ..uq.model_form.qualification import ProducerQualification
    from .capabilities import production_registry

    offered = []
    for item in external or ():
        raw = item.get("record", item) if isinstance(item, Mapping) else item
        offered.append(read_external_record(raw))
    empirical = tuple(DatasetObservation.from_dict(item) for item in (empirical_observations or ()))
    qualification = (
        None if model_form_qualification is None else ProducerQualification.from_dict(model_form_qualification)
    )
    return assess_claim(
        claim,
        production_registry(),
        external=tuple(offered),
        empirical_observations=empirical,
        model_form_qualification=qualification,
        trust=PRODUCTION_EXTERNAL_REGISTRY,
    ).to_dict()


def assess_claim_request(request: Mapping[str, Any]) -> dict[str, Any]:
    """Assess one claim request through the canonical claim path and return its record."""
    request = _mapping(request, name="request")
    if "claim" in request:
        stray = sorted(k for k in request if k in _CASE_SHAPE_KEYS)
        if stray:
            raise ClaimAssessmentError(
                f"a request carries either a claim or a case-based description, not both; also given: {stray}"
            )
        return assess_structured_claim(
            _mapping(request.get("claim"), name="claim"),
            external=request.get("external"),
            empirical_observations=request.get("empirical_observations"),
            model_form_qualification=request.get("model_form_qualification"),
        )
    record = assess_structured_claim(claim_from_case_request(request))
    # The case was translated for ONE system: if routing chose another capability, the answer is about a
    # different question than the caller asked, and it is refused rather than returned (Review: F6).
    plan = record.get("plan")
    expected = f"system.{_text(request, 'system')}"
    if plan is not None and plan["content"]["capability"]["capability_id"] != expected:
        raise ClaimAssessmentError(
            f"the claim was routed to {plan['content']['capability']['capability_id']!r}, not to the requested {expected!r}"
        )
    return record


def refused_claim_assessment(exc: Exception) -> dict[str, Any]:
    """Stable error payload for the public MCP tool."""
    return {
        "schema": CLAIM_ASSESSMENT_ERROR_SCHEMA,
        "status": "refused",
        "error": str(exc),
    }


__all__ = [
    "CLAIM_ASSESSMENT_ERROR_SCHEMA",
    "CLAIM_ASSESSMENT_SCHEMA",
    "ClaimAssessmentError",
    "assess_claim_request",
    "assess_structured_claim",
    "claim_from_case_request",
    "refused_claim_assessment",
]
