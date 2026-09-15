"""Core trust closure: the invariants PR #39 and PR #24 proposed, reproduced against main and then enforced.

Each adversarial test here failed on ``main`` at 7c3ded9 before the fix it guards; the legitimate cases beside them
passed before and after. The reproductions of results, support,
evidence and belief were taken from PR #39's regression tests; the uncertainty-alias, calibration-spec, registry
and per-status cases were added when those invariants were reconciled. Every guard is also removed on purpose by
a formal mutation in ``tests/mutation_guards.py`` (GUARD 28), and this module is that mutation's target suite.
"""

from __future__ import annotations

import pytest

from engcore.scientific.errors import ScientificCoreError
from engcore.scientific.ir.problem import ModelReference, ScientificProblem
from engcore.scientific.models.definition import ValidityAssessment, ValidityStatus
from engcore.scientific.results.provenance import ExecutionBinding, ProvenanceRecord
from engcore.scientific.results.result import ScientificResult
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.results.validation import ValidationCheck, ValidationLevel, ValidationOutcome, ValidationReport
from engcore.scientific.solvers.protocol import ConvergenceState, DeclaredSupport, SolverIdentity
from engcore.scientific.units.quantity import Quantity
from engcore.sria.errors import EvidenceError
from engcore.sria.evidence import ClaimBinding, ClaimType, Evidence, EvidenceStatus, SourceClass
from engcore.sria.gateway import BeliefEntry, BeliefUpdateGateway
from engcore.sria.uncertainty import (
    DiscrepancyKind,
    ModelDiscrepancy,
    SubjectModel,
    UncertaintyChannel,
    UncertaintyDeclaration,
)

MODEL_V1 = ModelReference("trust.model", "1")
MODEL_V2 = ModelReference("trust.model", "2")
SOLVER = SolverIdentity("trust.solver", "1")
OTHER_SOLVER = SolverIdentity("other.solver", "1")


# ---------------------------------------------------------------------------
# A. inference admits no source whose applicability was assessed and not established
#
# PR #39 proposed making ``is_usable`` require IN_DOMAIN. Current main pins the opposite on purpose
# (``test_is_usable_is_independent_of_validity_in_both_directions``: a caller who wants validity must ask), and
# calibration sweeps deliberately admit candidates recorded as not assessed. So the question is asked where
# evidence is admitted, and ``is_usable`` keeps its pinned meaning.
# ---------------------------------------------------------------------------
def _validity(status: ValidityStatus) -> ValidityAssessment:
    if status is ValidityStatus.IN_DOMAIN:
        return ValidityAssessment(status=status, satisfied=("declared-range",))
    if status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN:
        return ValidityAssessment(status=status, violated=("declared-range",))
    return ValidityAssessment(status=status)


def _result(*, model=MODEL_V1, provenance=None, solver=SOLVER, validity=ValidityStatus.IN_DOMAIN, models=None):
    models = (model.key,) if models is None else models
    provenance = provenance or ProvenanceRecord(
        run_id="trust-run", models=models, solvers=(() if solver is None else (solver.key,)))
    kwargs = {}
    if validity is None:
        kwargs["validity_not_assessed"] = {m: "not assessed in this regression fixture" for m, _v in models}
    else:
        kwargs["validity"] = {m: _validity(validity) for m, _v in models}
    return ScientificResult(result_id="trust-result", values={"y": Quantity(1.0, "dimensionless")},
                            provenance=provenance, models=models, solver=solver, **kwargs)


_ADMISSION_MODEL = ("synthetic.admission", "1")
_DIMENSIONAL = ValidationReport(checks=(ValidationCheck(
    name="dimensional_consistency", outcome=ValidationOutcome.PASS, establishes=ValidationLevel.DIMENSIONALLY_VALID,
    evidence=("fixture: kelvin declared by the fixture",)),))
_SEQUENCE = ValidationReport(checks=(ValidationCheck(
    name="tolerance_ladder", outcome=ValidationOutcome.PASS, establishes=ValidationLevel.NUMERICALLY_CONVERGED,
    residual=1e-10, tolerance=1e-8, evidence=("fixture: a converged ladder",)),))


def _source(validity):
    kwargs = ({"validity_not_assessed": {_ADMISSION_MODEL[0]: "a calibration candidate: nothing to assess yet"}}
              if validity is None else {"validity": {_ADMISSION_MODEL[0]: _validity(validity)}})
    return ScientificResult(
        result_id="admission-source", problem_id="admission", values={"y": Quantity(1.25, "kelvin")},
        models=(_ADMISSION_MODEL,), solver=SolverIdentity("algebraic", "1.0.0"), convergence=ConvergenceState.NOT_APPLICABLE,
        validation=_DIMENSIONAL, provenance=ProvenanceRecord(run_id="admission-run", models=(_ADMISSION_MODEL,),
                                                            solvers=(("algebraic", "1.0.0"),)),
        **kwargs)


def _numerical(validity):
    from engcore.inference.admissibility import AdmissibleNumericalPrediction

    return AdmissibleNumericalPrediction(
        prediction_id="p", domain="synthetic", adapter_id="adapter", binding_ref="binding:p", verification_ref="verification:p",
        source_result=_source(validity), observable_names=("y",), sequence_validation=_SEQUENCE)


def _analytic(validity):
    from engcore.inference.admissibility import AdmissibleAnalyticPrediction

    return AdmissibleAnalyticPrediction(
        prediction_id="p", domain="synthetic", adapter_id="adapter", binding_ref="binding:p", verification_ref="verification:p",
        source_result=_source(validity), observable_names=("y",), validation=_DIMENSIONAL,
        analytic_basis="closed form y = f(x) for this fixture")


@pytest.mark.parametrize("route", [_numerical, _analytic], ids=["numerical", "analytic"])
@pytest.mark.parametrize("status", [ValidityStatus.OUTSIDE_VALIDATED_DOMAIN, ValidityStatus.UNKNOWN],
                         ids=["OUTSIDE_VALIDATED_DOMAIN", "UNKNOWN"])
def test_a_admission_refuses_a_usable_source_whose_model_was_assessed_and_not_shown_to_apply(route, status):
    from engcore.inference.admissibility import InferenceAdmissibilityError

    source = _source(status)
    assert source.is_usable is True, "the source is numerically clean; only its applicability is in question"
    with pytest.raises(InferenceAdmissibilityError, match="applicability was assessed and not established"):
        route(status)


@pytest.mark.parametrize("route", [_numerical, _analytic], ids=["numerical", "analytic"])
def test_a_admission_still_admits_an_in_domain_source(route):
    assert route(ValidityStatus.IN_DOMAIN).source_result.validity_of(_ADMISSION_MODEL[0]).status is ValidityStatus.IN_DOMAIN


@pytest.mark.parametrize("route", [_numerical, _analytic], ids=["numerical", "analytic"])
def test_a_an_explicit_reasoned_non_assessment_stays_admissible_for_a_calibration_sweep(route):
    prediction = route(None)
    assert prediction.source_result.unassessed_models == (_ADMISSION_MODEL[0],)


def test_a_a_missing_assessment_cannot_even_be_constructed():
    with pytest.raises(ScientificCoreError):
        ScientificResult(result_id="gap", values={"y": Quantity(1.0, "dimensionless")},
                         provenance=ProvenanceRecord(run_id="gap", models=(MODEL_V1.key,), solvers=(SOLVER.key,)),
                         models=(MODEL_V1.key,), solver=SOLVER)


# ---------------------------------------------------------------------------
# B. a result may narrow its provenance, never contradict it
# ---------------------------------------------------------------------------
def test_b_a_result_declaring_a_model_its_provenance_does_not_name_is_refused():
    provenance = ProvenanceRecord(run_id="wrong-model", models=(MODEL_V2.key,), solvers=(SOLVER.key,))
    with pytest.raises(ScientificCoreError, match="provenance does not name"):
        _result(model=MODEL_V1, provenance=provenance)


def test_b_a_result_declaring_a_solver_its_provenance_does_not_name_is_refused():
    provenance = ProvenanceRecord(run_id="wrong-solver", models=(MODEL_V1.key,), solvers=(OTHER_SOLVER.key,))
    with pytest.raises(ScientificCoreError, match="provenance does not name that solver"):
        _result(provenance=provenance, solver=SOLVER)


def test_b_a_bound_solver_must_be_bound_to_a_model_the_result_declares():
    provenance = ProvenanceRecord(run_id="unbound", models=(MODEL_V1.key, MODEL_V2.key),
                                  bindings=(ExecutionBinding(model=MODEL_V1, solver=SOLVER),))
    with pytest.raises(ScientificCoreError, match="no provenance execution binding connects"):
        _result(model=MODEL_V2, provenance=provenance, solver=SOLVER)


def test_b_narrowing_provenance_is_allowed_and_survives_read_back():
    provenance = ProvenanceRecord(run_id="wide", models=(MODEL_V1.key, ("support.model", "1")),
                                  solvers=(SOLVER.key, OTHER_SOLVER.key))
    result = _result(provenance=provenance)
    assert ScientificResult.from_dict(result.to_dict()).to_dict() == result.to_dict()


def test_b_a_contradiction_is_refused_on_read_back_too():
    payload = _result().to_dict()
    payload["models"] = [["trust.model", "2"]]
    payload["validity"] = {"trust.model": payload["validity"]["trust.model"]}
    with pytest.raises(ScientificCoreError, match="provenance does not name"):
        ScientificResult.from_dict(payload)


def _stored_payload_with_silent_provenance():
    """A /4 payload of the shape every pre-closure producer and fixture wrote: solver and models named, provenance
    listing no participants. Built by editing a current payload, because the constructor now refuses to make one.

    Labelled /4 explicitly since the results audit (RES-01): the writer emits /5, and /5 is the version whose read
    is held to its own provenance, so a silent /5 payload is refused (see the test below)."""
    payload = _result().to_dict()
    payload["schema"] = "scientific_result/4"
    payload["provenance"]["models"] = []
    payload["provenance"]["solvers"] = []
    return payload


def test_b_a_stored_record_whose_provenance_is_silent_is_read_as_written():
    """A legacy (/4 or older) record with silent provenance is read as written, and marked.

    What changed in the results audit (RES-01): this used to hold for EVERY version, the current one included, so a
    current payload attributing itself to a fabricated model and solver read back usable. It now holds only for
    versions written before the consistency check, and the record carries the gap: it re-serializes at /4 -- which
    is still exactly the payload it was read from -- and never as the attributed /5."""
    from engcore.scientific.results.result import stored_attribution_gap

    payload = _stored_payload_with_silent_provenance()
    result = ScientificResult.from_dict(payload)
    assert result.solver == SOLVER and result.models == (MODEL_V1.key,)
    assert result.provenance.solvers == () and result.provenance.models == ()
    assert result.to_dict() == payload
    assert stored_attribution_gap(result)


def test_b_a_current_record_whose_provenance_is_silent_is_refused_on_read():
    payload = _stored_payload_with_silent_provenance()
    payload["schema"] = "scientific_result/5"
    with pytest.raises(ScientificCoreError, match="provenance does not name"):
        ScientificResult.from_dict(payload)


def test_b_new_construction_with_silent_provenance_is_still_refused():
    with pytest.raises(ScientificCoreError, match="provenance does not name"):
        _result(provenance=ProvenanceRecord(run_id="silent"))
    with pytest.raises(ScientificCoreError, match="provenance does not name that solver"):
        _result(provenance=ProvenanceRecord(run_id="silent-solvers", models=(MODEL_V1.key,)))


def test_b_a_stored_record_whose_provenance_names_another_solver_is_still_refused_on_read():
    payload = _result().to_dict()
    payload["provenance"]["solvers"] = [list(OTHER_SOLVER.key)]
    with pytest.raises(ScientificCoreError, match="provenance does not name that solver"):
        ScientificResult.from_dict(payload)


# ---------------------------------------------------------------------------
# C. declared solver support matches a model's exact version
# ---------------------------------------------------------------------------
class _ServesModelV1(DeclaredSupport):
    served_models = (MODEL_V1,)
    serves_capabilities = frozenset()
    capabilities = frozenset()


def test_c_a_solver_serving_model_at_1_does_not_support_a_problem_naming_model_at_2():
    solver = _ServesModelV1()
    assert solver.supports(ScientificProblem(problem_id="v1", models=(MODEL_V1,))) is True
    mismatch = ScientificProblem(problem_id="v2", models=(MODEL_V2,))
    assert solver.supports(mismatch) is False
    gap = " ".join(solver.support_gap(mismatch))
    assert "trust.model@2" in gap and "trust.model@1" in gap


# ---------------------------------------------------------------------------
# D, F. SRIA evidence and its uncertainty cannot change under a stale identity
# ---------------------------------------------------------------------------
def _uncertainty(channels=None) -> UncertaintyDeclaration:
    return UncertaintyDeclaration(subject_model=SubjectModel.PREDICTION_MODEL,
                                  discrepancy=ModelDiscrepancy(DiscrepancyKind.ZERO_DECLARED),
                                  channels=channels if channels is not None else {UncertaintyChannel.ALEATORIC: Uncertainty.unknown()})


def _evidence(uncertainty=None) -> Evidence:
    return Evidence(
        evidence_id="e-1", source_class=SourceClass.SIMULATION, claim_type=ClaimType.QOI_VALUE,
        claim_binding=ClaimBinding(subject_kind="component", subject_ref="wing", qualifiers={"station": "root"}),
        claim_payload={"value": {"samples": [1.0, 2.0]}}, uncertainty=uncertainty or _uncertainty(),
        provenance_ref="run-1", domain_pack_ref="aero@1", metadata={"review": {"tags": ["candidate"]}})


def test_d_evidence_identity_bearing_content_is_recursively_immutable():
    evidence = _evidence()
    with pytest.raises(TypeError):
        evidence.claim_payload["value"]["samples"][0] = 9.0
    with pytest.raises(TypeError):
        evidence.claim_binding.qualifiers["station"] = "tip"
    assert evidence.record_hash


def test_d_a_caller_mutating_what_it_passed_in_does_not_reach_the_evidence():
    payload = {"value": {"samples": [1.0, 2.0]}}
    evidence = Evidence(
        evidence_id="e-2", source_class=SourceClass.SIMULATION, claim_type=ClaimType.QOI_VALUE,
        claim_binding=ClaimBinding(subject_kind="component", subject_ref="wing", qualifiers={"station": "root"}),
        claim_payload=payload, uncertainty=_uncertainty(), provenance_ref="run-1", domain_pack_ref="aero@1")
    before = evidence.content_hash
    payload["value"]["samples"][0] = 999.0
    assert evidence.claim_payload["value"]["samples"][0] == 1.0
    assert evidence.record_hash and evidence.content_hash == before


def test_d_serialization_is_detached_from_the_record():
    evidence = _evidence()
    payload = evidence.to_dict()
    payload["claim_payload"]["value"]["samples"][0] = 99.0
    payload["metadata"]["review"]["tags"].append("edited")
    assert evidence.claim_payload["value"]["samples"][0] == 1.0
    assert list(evidence.metadata["review"]["tags"]) == ["candidate"]


def test_d_content_mutated_around_the_frozen_record_cannot_reuse_its_identity_or_be_submitted():
    evidence = _evidence()
    original = evidence.content_hash
    # Deliberately reaching around frozen=True, as a hostile or careless caller could.
    object.__setattr__(evidence, "claim_payload", {"value": {"samples": [999.0]}})
    assert evidence.content_hash == original
    with pytest.raises(EvidenceError, match="no longer matches content_hash"):
        _ = evidence.record_hash
    with pytest.raises(EvidenceError, match="no longer matches content_hash"):
        BeliefUpdateGateway().submit(evidence)


def test_f_an_uncertainty_channel_cannot_change_through_the_declaration_or_a_caller_alias():
    channels = {UncertaintyChannel.ALEATORIC: Uncertainty.unknown()}
    declaration = _uncertainty(channels)
    evidence = _evidence(declaration)
    before = evidence.content_hash
    channels[UncertaintyChannel.NUMERICAL] = Uncertainty.unknown()
    assert UncertaintyChannel.NUMERICAL not in declaration.channels
    with pytest.raises(TypeError):
        declaration.channels[UncertaintyChannel.NUMERICAL] = Uncertainty.unknown()
    assert evidence.record_hash and evidence.content_hash == before


# ---------------------------------------------------------------------------
# E. stored belief cannot change through a read
# ---------------------------------------------------------------------------
def test_e_a_belief_entry_payload_cannot_be_mutated_through_a_read():
    entry = BeliefEntry(evidence_id="e-1", belief_key="qoi_value|component:wing;station=root", claim_type="qoi_value",
                        content_hash="a" * 64, record_hash="b" * 64, status=EvidenceStatus.ACCEPTED, admitted_by="arbiter-1",
                        claim_payload={"value": {"samples": [1.0, 2.0]}})
    with pytest.raises(TypeError):
        entry.claim_payload["value"]["samples"][0] = 5.0
    serialized = entry.to_dict()
    serialized["claim_payload"]["value"]["samples"][0] = 5.0
    assert entry.claim_payload["value"]["samples"][0] == 1.0


# ---------------------------------------------------------------------------
# PR #24: a solver session whose freshness cannot be proven; a calibration record's declared inputs
# ---------------------------------------------------------------------------
def test_a_session_that_cannot_be_tracked_is_refused_rather_than_shared_between_requests():
    from engcore.scientific.solvers.registry import SolverDefinition

    class Slotted:
        __slots__ = ("identity",)

        def __init__(self):
            self.identity = SolverIdentity("slot.solver", "1")

    shared = Slotted()
    definition = SolverDefinition(lambda: shared, Slotted())
    with pytest.raises(TypeError, match="cannot be weak-referenced"):
        definition.new_session()


def test_a_calibration_spec_cannot_be_rewritten_through_its_mappings_after_construction():
    from engcore.inference.calibration import CalibrationSpec
    from engcore.inference.parameters import CalibrationParameterSet, ParameterBounds, ParameterIdentity

    unit = "dimensionless"
    parameters = CalibrationParameterSet((ParameterIdentity(
        name="k", unit=unit, model=MODEL_V1, bounds=ParameterBounds(Quantity(0.0, unit), Quantity(10.0, unit))),))
    fixed = {"t": Quantity(300.0, "kelvin")}
    spec = CalibrationSpec(parameters=parameters, fixed=fixed, initial_point={"k": Quantity(1.0, unit)})
    fixed["t"] = Quantity(900.0, "kelvin")
    assert spec.fixed["t"].magnitude == 300.0
    with pytest.raises(TypeError):
        spec.fixed["t"] = Quantity(900.0, "kelvin")
    with pytest.raises(TypeError):
        spec.initial_point["k"] = Quantity(9.0, unit)
