"""Targeted mutation kill-checks for the claim layer's load-bearing guards.

``tests/mutation_guards.py`` is SHA-256 pinned by the certification snapshot, so
guards written after the last certification cannot join its population without
a re-certification round. Until then, each guard of this layer is checked the
same way here: a *mutant* disables or inverts it, and the property it protects
must then observably fail. A mutant under which the property still holds
**survives**, and this file fails -- the guard it targets is not load-bearing
as written.

Every case asserts both halves: the property holds on the real code, and the
mutant breaks it.
"""

from __future__ import annotations

import copy
from dataclasses import replace

import pytest

import engcore.claims.assessment as assessment_module
import engcore.claims.capabilities as capabilities_module
import engcore.claims.compiler as compiler_module
import engcore.claims.context as context_module
import engcore.claims.planning as planning_module
import engcore.claims.routes as routes_module
import engcore.claims.selection as selection_module
import engcore.claims.sources as sources_module
import engcore.claims.uncertainty as uncertainty_module
import engcore.claims.verdict as verdict_module
from claims_support import et_claim, et_inputs, t3_claim
from engcore.claims import (
    CapabilityDeclarationError,
    CapabilityRegistry,
    ClaimTarget,
    CompilationStatus,
    DecisionBinding,
    EvidenceRequirement,
    ExperimentPlan,
    PlanningError,
    RouteClass,
    RouteDeclaration,
    RouteKind,
    SourceStatus,
    UncertaintyDemand,
    assemble_evidence,
    assess_claim,
    compile_claim,
    execute_plan,
    plan_experiment,
)
from engcore.mcp.capabilities import NAFEMS_T3_CAPABILITY_ID, production_registry
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind, UncertaintySource
from engcore.scientific.results.validation import ValidationLevel
from engcore.scientific.units.quantity import Quantity
from engcore.sria import SourceClass
from engcore.sria.uncertainty import UncertaintyChannel


def _registry():
    return production_registry()


# ---- the properties -----------------------------------------------------------------


def violated_without_the_bar_is_not_a_contradiction():
    record = assess_claim(
        et_claim(target=ClaimTarget(value=Quantity(310.0, "kelvin")),
                 evidence=EvidenceRequirement((ValidationLevel.EXPERIMENTALLY_VALIDATED,))),
        _registry(),
    ).to_dict()
    assert record["verdict"] == "insufficient_evidence"


def missing_required_input_needs_input():
    # The initial temperature feeds no validity condition, so only the
    # required-input rule can catch its absence. (heat_capacity would not do:
    # a lumped-model condition reads it directly, and that blocks it too.)
    inputs = et_inputs()
    del inputs["stages[0].body.initial_temperature"]
    assert compile_claim(et_claim(known_inputs=inputs), _registry()).status is CompilationStatus.NEEDS_INPUT


def outside_model_is_never_selected():
    point = dict(t3_claim().operating_context)
    point["conductivity"] = Quantity(36.0, "watt / meter / kelvin")
    assert compile_claim(t3_claim(operating_context=point), _registry()).status is CompilationStatus.UNSUPPORTED_CAPABILITY


def foreign_context_is_refused():
    registry = _registry()
    a, b = t3_claim(), t3_claim(decision=DecisionBinding("d-2", "another use"))
    plan_a = plan_experiment(compile_claim(a, registry), registry)
    plan_b = plan_experiment(compile_claim(b, registry), registry)
    report = execute_plan(plan_a, registry, dict(a.supplied_inputs)).report
    evidence = assemble_evidence(plan_a, a, report).evidence
    assert context_module.context_problems(evidence, plan_b, report)


def straddling_band_decides_nothing():
    """Phase 2: the production T3 refinement study's GCI band (about 3.7 mK) straddles a 0.2 mK tolerance edge."""
    demand = UncertaintyDemand(frozenset({UncertaintyChannel.NUMERICAL}), None, False)
    record = assess_claim(t3_claim(uncertainty=demand, tolerance=Quantity(0.0002, "kelvin")), _registry()).to_dict()
    assert record["comparison"]["point_satisfied"] is True
    assert record["verdict"] == "insufficient_evidence"


def mixture_enters_no_channel():
    record = Uncertainty(kind=UncertaintyKind.STANDARD, standard_uncertainty=Quantity(1.0, "kelvin"),
                         method="x", source_kind=UncertaintySource.COMBINED)
    assert uncertainty_module.transport({"q": record}).channels == {}


def edited_plan_is_refused():
    registry = _registry()
    wire = copy.deepcopy(plan_experiment(compile_claim(t3_claim(), registry), registry).to_dict())
    wire["content"]["case"]["conductivity"] = "36.0 watt / kelvin / meter"
    with pytest.raises(PlanningError):
        ExperimentPlan.from_dict(wire)


def shared_implementation_is_not_independent():
    a = routes_module.pinned_dependencies("kinetics.cstr.integration:BDF").identities
    b = routes_module.pinned_dependencies("kinetics.cstr.integration:Radau").identities
    assert routes_module.classify_dependencies(a, b)[0] is not RouteClass.INDEPENDENT


def unpinned_route_is_refused():
    from test_claims_capabilities import declaration

    primary = RouteDeclaration("p", RouteKind.PRIMARY_SIMULATION, "primary")
    with pytest.raises(CapabilityDeclarationError):
        declaration(routes=(primary, RouteDeclaration("r", RouteKind.SOLVER_ROUTE, "x", check_name="c", pinned_route="made.up.route")))


def unimplemented_source_answers_not_implemented():
    outcomes = {o.source_class: o for o in sources_module.gather_evidence({"simulation_evidence": None})}
    assert outcomes[SourceClass.MEASUREMENT].status is SourceStatus.NOT_IMPLEMENTED


def unknown_never_beats_in_domain():
    from test_claims_selection import _capability, _claim, _model

    registry = CapabilityRegistry((_capability("syn.known", _model("syn.beam")), _capability("syn.pending", _model("syn.ratio", derived=True))))
    assert selection_module.select_capability(_claim(), registry).selected.capability_id == "syn.known"


# ---- the mutants ---------------------------------------------------------------------


def _admissible_without_assurance(basis):
    return basis.ready and basis.executed and basis.bound


def _always_point(claim, value, bound, uncertainty):
    no_demand = replace(claim, uncertainty=UncertaintyDemand(frozenset(), None, False))
    return ORIGINAL_COMPARE(no_demand, value, bound, uncertainty)


def _combined_is_numerical(name, record):
    if record.is_quantified and UncertaintySource(record.source_kind) is UncertaintySource.COMBINED:
        return uncertainty_module.TransportedRecord(name, uncertainty_module.TransportState.ATTRIBUTED, UncertaintyChannel.NUMERICAL, record)
    return ORIGINAL_CLASSIFY(name, record)


def _select_without_preference(claim, registry):
    matches = registry.match(quantity=claim.qoi.name, dimension=claim.qoi.dimension,
                             required=claim.required_capabilities, claim_kind=claim.kind)
    assessed = [selection_module.assess_candidate(registry.get(m.capability_id), m, claim) for m in matches]
    viable = [c for c in assessed if c.status is selection_module.CandidateStatus.VIABLE]
    out = []
    for candidate in assessed:
        if candidate.status is selection_module.CandidateStatus.VIABLE and candidate is viable[-1]:
            candidate = replace(candidate, status=selection_module.CandidateStatus.SELECTED)
        elif candidate.status is selection_module.CandidateStatus.VIABLE:
            candidate = replace(candidate, status=selection_module.CandidateStatus.OUTRANKED)
        out.append(candidate)
    return selection_module.ModelSelection(tuple(out))


def _assess_without_rejections(declaration, match, claim):
    candidate = ORIGINAL_ASSESS_CANDIDATE(declaration, match, claim)
    if candidate.status is selection_module.CandidateStatus.REJECTED:
        return replace(candidate, status=selection_module.CandidateStatus.VIABLE, rejections=())
    return candidate


ORIGINAL_COMPARE = verdict_module.compare
ORIGINAL_CLASSIFY = uncertainty_module.classify_record
ORIGINAL_ASSESS_CANDIDATE = selection_module.assess_candidate

MUTANTS = [
    ("admissibility_ignores_assurance", violated_without_the_bar_is_not_a_contradiction,
     [(verdict_module, "admissible", _admissible_without_assurance)]),
    ("required_inputs_ignored", missing_required_input_needs_input,
     [(compiler_module, "_required_paths", lambda declaration, paths: [])]),
    ("rejections_ignored", outside_model_is_never_selected,
     [(selection_module, "assess_candidate", _assess_without_rejections)]),
    ("context_unchecked", foreign_context_is_refused,
     [(context_module, "context_problems", lambda evidence, plan, report=None: ())]),
    ("guard_band_bypassed", straddling_band_decides_nothing,
     [(verdict_module, "compare", _always_point), (assessment_module, "compare", _always_point)]),
    ("combined_filed_as_numerical", mixture_enters_no_channel,
     [(uncertainty_module, "classify_record", _combined_is_numerical)]),
    ("plan_binding_skipped", edited_plan_is_refused,
     [(planning_module.ExperimentPlan, "_require_bound", lambda self: None)]),
    ("independence_assumed", shared_implementation_is_not_independent,
     [(routes_module, "classify_dependencies", lambda a, b: (RouteClass.INDEPENDENT, ()))]),
    ("route_pins_unverified", unpinned_route_is_refused,
     [(capabilities_module.RouteDeclaration, "verify_references", lambda self: None)]),
    ("every_source_implemented", unimplemented_source_answers_not_implemented,
     [(sources_module.EvidenceSourceAdapter, "implemented", property(lambda self: True))]),
    ("unknown_beats_in_domain", unknown_never_beats_in_domain,
     [(selection_module, "select_capability", _select_without_preference)]),
]


@pytest.mark.parametrize("name, prop, patches", MUTANTS, ids=[m[0] for m in MUTANTS])
def test_each_guard_is_load_bearing(monkeypatch, name, prop, patches) -> None:
    prop()  # the property holds on the real code
    with monkeypatch.context() as patched:
        for owner, attribute, replacement in patches:
            patched.setattr(owner, attribute, replacement)
        try:
            prop()
        except (Exception, pytest.fail.Exception):
            return  # killed: the property no longer holds
    pytest.fail(f"mutant {name!r} survived: the property still holds with the guard disabled")
