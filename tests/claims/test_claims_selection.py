"""CORE-4: model selection -- applicability decides, executability never does.

Synthetic capabilities with real ``ScientificModelDefinition`` records, so each
selection rule is exercised in isolation from any domain.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from claims_support import claim
from engcore.claims import (
    CandidateStatus,
    CapabilityDeclaration,
    CapabilityRegistry,
    ClaimTarget,
    InputDeclaration,
    InputKind,
    InputRole,
    ModelUse,
    ProducedQuantity,
    ProvidedCapability,
    QuantityOfInterest,
    RejectionReason,
    RouteDeclaration,
    RouteKind,
    UnassessableCondition,
    UncertaintyCapability,
    UnknownBasis,
    select_capability,
)
from engcore.claims.contract import ClaimKind
from engcore.scientific.models.definition import (
    InputSourceKind,
    ModelInputSpec,
    ModelOutputSpec,
    RangeCondition,
    ScientificModelDefinition,
    ValidityDomain,
    ValidityStatus,
)
from engcore.scientific.units.quantity import Quantity


def _model(model_id: str, *, version: str = "1.0.0", derived: bool = False, conditions: bool = True) -> ScientificModelDefinition:
    """A model with input ``span`` and either a condition on it or on a derived ratio."""
    if not conditions:
        validity = ValidityDomain(conditions=())
    elif derived:
        validity = ValidityDomain(
            conditions=(RangeCondition(name="span_ratio", minimum=Quantity(0.0, "dimensionless"), maximum=Quantity(1.0, "dimensionless")),),
            derived_quantities=frozenset({"span_ratio"}),
        )
    else:
        validity = ValidityDomain(
            conditions=(RangeCondition(name="span", minimum=Quantity(0.0, "meter"), maximum=Quantity(2.0, "meter")),),
        )
    return ScientificModelDefinition(
        model_id=model_id,
        version=version,
        name=model_id,
        domain="synthetic",
        inputs=(ModelInputSpec(name="span", source_kind=InputSourceKind.PARAMETER, unit_exemplar="meter"),),
        outputs=(ModelOutputSpec(metric="deflection", unit_exemplar="meter"),),
        assumptions=("small deflection",),
        exclusions=("plasticity",),
        validity=validity,
    )


def _capability(capability_id: str, model: ScientificModelDefinition, **overrides) -> CapabilityDeclaration:
    fields = dict(
        capability_id=capability_id,
        version="1",
        domain="synthetic",
        summary="synthetic",
        provides=(ProvidedCapability(f"synthetic:{capability_id.split('.')[-1]}", "stated: synthetic"),),
        inputs=(
            InputDeclaration("beam.span", InputKind.QUANTITY, InputRole.PARAMETER, True, "meter",
                             model_id=model.model_id, model_input="span", unlocks_conditions=("span_ratio",)),
        ),
        produces=(ProducedQuantity("deflection", "meter", model_id=model.model_id),),
        models=(ModelUse.of(model),),
        solvers=(),
        claim_shapes=frozenset(ClaimKind),
        attainable_levels=(),
        uncertainty=UncertaintyCapability({}, "none"),
        routes=(RouteDeclaration(f"{capability_id}.primary", RouteKind.PRIMARY_SIMULATION, "primary"),),
        executor=lambda case, *, run_id: None,
    )
    fields.update(overrides)
    return CapabilityDeclaration(**fields)


def _claim(span: float | None = 1.0, **overrides):
    inputs = {} if span is None else {"beam.span": Quantity(span, "meter")}
    fields = dict(
        qoi=QuantityOfInterest("deflection", "millimeter"),
        target=ClaimTarget(value=Quantity(5.0, "millimeter")),
        operating_context={},
        known_inputs=inputs,
    )
    fields.update(overrides)
    return claim(**fields)


def _by_id(selection):
    return {c.capability_id: c for c in selection.candidates}


# ---------------------------------------------------------------------------


def test_exactly_one_compatible_candidate_is_selected_with_its_model_version_and_scope() -> None:
    registry = CapabilityRegistry((_capability("syn.known", _model("syn.beam")),))
    selection = select_capability(_claim(), registry)
    chosen = selection.selected
    assert chosen is not None and chosen.capability_id == "syn.known"
    assert chosen.applicability is ValidityStatus.IN_DOMAIN
    (model,) = chosen.models
    assert (model.model_id, model.version) == ("syn.beam", "1.0.0")
    assert model.assumptions == ("small deflection",) and model.exclusions == ("plasticity",)


def test_unknown_applicability_never_beats_a_known_in_domain_candidate() -> None:
    registry = CapabilityRegistry(
        (_capability("syn.known", _model("syn.beam")), _capability("syn.pending", _model("syn.ratio", derived=True)))
    )
    by_id = _by_id(select_capability(_claim(), registry))
    assert by_id["syn.known"].status is CandidateStatus.SELECTED
    assert by_id["syn.pending"].status is CandidateStatus.OUTRANKED
    assert by_id["syn.pending"].applicability is ValidityStatus.UNKNOWN
    assert UnknownBasis.PENDING_EXECUTION in by_id["syn.pending"].bases


def test_without_a_known_candidate_an_unknown_one_may_be_selected_but_stays_unknown() -> None:
    registry = CapabilityRegistry((_capability("syn.pending", _model("syn.ratio", derived=True)),))
    chosen = select_capability(_claim(), registry).selected
    assert chosen is not None and chosen.applicability is ValidityStatus.UNKNOWN


def test_two_applicable_candidates_are_ambiguous_not_ranked() -> None:
    registry = CapabilityRegistry(
        (_capability("syn.a", _model("syn.beam_a")), _capability("syn.b", _model("syn.beam_b")))
    )
    selection = select_capability(_claim(), registry)
    assert selection.selected is None
    assert [c.capability_id for c in selection.ambiguous] == ["syn.a", "syn.b"]


def test_an_outside_model_is_never_evidence_bearing_even_when_it_is_the_only_one() -> None:
    registry = CapabilityRegistry((_capability("syn.known", _model("syn.beam")),))
    selection = select_capability(_claim(span=5.0), registry)
    (candidate,) = selection.candidates
    assert selection.selected is None
    assert candidate.status is CandidateStatus.REJECTED
    assert candidate.applicability is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert RejectionReason.OUTSIDE_VALIDITY in {r for r, _ in candidate.rejections}
    (violated,) = candidate.models[0].violated
    assert violated.declared["maximum"]["magnitude"] == 2.0  # the model's own bound, not invented


def test_an_outside_candidate_does_not_block_an_applicable_one() -> None:
    narrow = _model("syn.narrow")
    wide = replace(
        _model("syn.wide"),
        validity=ValidityDomain(conditions=(RangeCondition(name="span", minimum=Quantity(0.0, "meter"), maximum=Quantity(10.0, "meter")),)),
    )
    registry = CapabilityRegistry((_capability("syn.narrow", narrow), _capability("syn.wide", wide)))
    by_id = _by_id(select_capability(_claim(span=5.0), registry))
    assert by_id["syn.narrow"].status is CandidateStatus.REJECTED
    assert by_id["syn.wide"].status is CandidateStatus.SELECTED


def test_a_model_that_cannot_evaluate_its_validity_is_rejected() -> None:
    registry = CapabilityRegistry((_capability("syn.blind", _model("syn.blind", conditions=False)),))
    (candidate,) = select_capability(_claim(), registry).candidates
    assert candidate.status is CandidateStatus.REJECTED
    assert RejectionReason.VALIDITY_UNASSESSABLE in {r for r, _ in candidate.rejections}


def test_a_declared_unassessable_condition_rejects_the_candidate_whatever_is_supplied() -> None:
    model = _model("syn.ratio", derived=True)
    registry = CapabilityRegistry(
        (_capability("syn.unassessable", model,
                     unassessable_conditions=(UnassessableCondition("syn.ratio", "span_ratio", "never assembled here"),)),)
    )
    (candidate,) = select_capability(_claim(), registry).candidates
    assert candidate.status is CandidateStatus.REJECTED
    assert UnknownBasis.DECLARED_UNASSESSABLE in candidate.bases


def test_a_candidate_missing_a_direct_validity_input_reports_it_as_missing_context() -> None:
    registry = CapabilityRegistry((_capability("syn.known", _model("syn.beam")),))
    chosen = select_capability(_claim(span=None), registry).selected
    assert chosen is not None and chosen.applicability is ValidityStatus.UNKNOWN
    (condition,) = chosen.models[0].unknown_of(UnknownBasis.MISSING_CONTEXT)
    assert condition.missing_inputs == ("beam.span",)


def test_a_measured_unlock_is_advisory_not_blocking() -> None:
    registry = CapabilityRegistry((_capability("syn.pending", _model("syn.ratio", derived=True)),))
    chosen = select_capability(_claim(span=None), registry).selected
    (condition,) = chosen.models[0].conditions
    assert condition.basis is UnknownBasis.PENDING_EXECUTION
    assert condition.advisory_inputs == ("beam.span",)
    assert chosen.models[0].unknown_of(UnknownBasis.MISSING_CONTEXT) == ()


def test_a_supplied_input_a_candidate_would_drop_rejects_it() -> None:
    registry = CapabilityRegistry((_capability("syn.known", _model("syn.beam")),))
    stray = _claim(known_inputs={"beam.span": Quantity(1.0, "meter"), "beam.width": Quantity(0.1, "meter")})
    (candidate,) = select_capability(stray, registry).candidates
    assert candidate.status is CandidateStatus.REJECTED
    assert candidate.unaccepted_inputs == ("beam.width",)


def test_the_target_input_is_the_comparisons_and_is_not_a_dropped_input() -> None:
    registry = CapabilityRegistry((_capability("syn.known", _model("syn.beam")),))
    referenced = _claim(
        known_inputs={"beam.span": Quantity(1.0, "meter"), "limits.allowed_deflection": Quantity(4.0, "millimeter")},
        target=ClaimTarget(input_ref="limits.allowed_deflection"),
    )
    assert select_capability(referenced, registry).selected is not None


def test_a_qualifier_that_selects_nothing_rejects_the_candidate() -> None:
    registry = CapabilityRegistry((_capability("syn.known", _model("syn.beam")),))
    qualified = _claim(qoi=QuantityOfInterest("deflection", "millimeter", {"component_id": "B1"}))
    (candidate,) = select_capability(qualified, registry).candidates
    assert RejectionReason.UNUSED_QUALIFIER in {r for r, _ in candidate.rejections}


def test_executability_alone_selects_nothing() -> None:
    """A capability that matches and can run, with nothing assessable, is not chosen."""
    registry = CapabilityRegistry((_capability("syn.blind", _model("syn.blind", conditions=False)),))
    selection = select_capability(_claim(), registry)
    assert registry.get("syn.blind").executable
    assert selection.selected is None


def test_the_selected_model_version_is_bound_to_the_candidate_digest() -> None:
    first = CapabilityRegistry((_capability("syn.known", _model("syn.beam", version="1.0.0")),))
    second = CapabilityRegistry((_capability("syn.known", _model("syn.beam", version="1.1.0")),))
    a = select_capability(_claim(), first).selected
    b = select_capability(_claim(), second).selected
    assert a.digest != b.digest
    assert a.models[0].version == "1.0.0" and b.models[0].version == "1.1.0"
    assert first.digest != second.digest


def test_selection_never_executes(monkeypatch) -> None:
    def refuse(case, *, run_id):  # pragma: no cover - reaching it is the failure
        raise AssertionError("selection executed a capability")

    registry = CapabilityRegistry((_capability("syn.known", _model("syn.beam"), executor=refuse),))
    assert select_capability(_claim(), registry).selected is not None
