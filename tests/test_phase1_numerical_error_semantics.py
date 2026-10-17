"""Phase 1 BR3 -- honest numerical error semantics for coupled runs.

* The mapping "error budget" no longer sums a round-trip residual and a
  conservation residual into a ``relative_bound``: both are DIAGNOSTICS.
* The run record's ``coupling_error_bound`` is no longer filled from them.
* A non-identity field mapping leaves its forward error UNQUANTIFIED.
* In the claims NUMERICAL channel a diagnostic neither passes nor closes
  anything; before BR3 a conservation residual of 0.0 passed a mapped run.

NOT RUN (Phase 1 build phase): docs/work/DEFERRED_VALIDATION.md, DV-36.
"""

from __future__ import annotations

import pytest

import engcore.claims.coupling_numerical as coupling_numerical
from engcore.claims.coupling_numerical import CouplingConditionAction, condition_numerical_uncertainty
from engcore.claims.numerical_uq import RefinementLevel, estimate_numerical_uncertainty
from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.execution.multiphysics import (
    AdvanceResult, CallbackParticipant, CouplingErrorBudget, CouplingErrorContribution, InitializationResult,
    MultiphysicsRuntime,
)
from engcore.execution.multiphysics.numerical_error import (
    CouplingNumericalErrorAssessment, ErrorAccountingVerdict, ErrorSourceStatus, NumericalErrorSource, run_digest,
)
from engcore.execution.multiphysics.participant import RuntimeCheckpoint
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.multiphysics import (
    CheckpointRecord, CouplingPlan, CouplingScheme, IterationSemantics, ParticipantSpec, PhysicsGraph,
    PortDefinition, PortDirection, PortKind, TimePolicy,
)
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.units.quantity import Quantity
from engcore.sria.uncertainty import UncertaintyChannel

UNKNOWN = Uncertainty.unknown("test output uncertainty not quantified")


# ---- the diagnostics record ------------------------------------------------------------------


def _diagnostics(round_trip=1e-3, conservation=0.0):
    return [{"edge_id": "e_field", "mapping": {"round_trip_relative_l2": round_trip,
                                                "conservation_relative_error": conservation}}]


def test_mapping_residuals_are_recorded_as_diagnostics_and_never_summed_into_a_bound():
    budget = CouplingErrorBudget.from_mapping_diagnostics(_diagnostics())
    payload = budget.to_dict()
    assert payload["evidence_class"] == "diagnostic_not_bound"
    assert "relative_bound" not in payload
    assert not hasattr(budget, "relative_bound")
    assert {c["evidence_class"] for c in payload["contributions"]} == {"round_trip_residual", "conservation_residual"}
    assert all("relative_bound" not in c for c in payload["contributions"])


def test_a_contribution_must_name_a_known_diagnostic_method():
    with pytest.raises(InvalidScientificProblem):
        CouplingErrorContribution("edge:e:occurrence:1", 0.1, "some_error_bound")


def test_a_contribution_refuses_a_negative_or_non_finite_value():
    for value in (-1.0, float("nan"), float("inf")):
        with pytest.raises(InvalidScientificProblem):
            CouplingErrorContribution("edge:e:occurrence:1", value, "mapping_round_trip")


# ---- the assessment --------------------------------------------------------------------------


def test_a_diagnostic_carries_its_measured_value():
    with pytest.raises(InvalidScientificProblem):
        NumericalErrorSource("s", "mapping", ErrorSourceStatus.DIAGNOSTIC, None, "mapping_round_trip")


def test_diagnostics_alone_never_make_a_coupled_run_bounded():
    assessment = CouplingNumericalErrorAssessment("r", "a" * 64, True, (
        NumericalErrorSource("edge:e:occurrence:1", "mapping", ErrorSourceStatus.DIAGNOSTIC, 0.0, "mapping_conservation"),
    ))
    assert assessment.verdict is ErrorAccountingVerdict.INCOMPLETE
    assert assessment.quantified_relative_bound is None
    assert assessment.estimated_relative is None


def test_a_diagnostic_does_not_change_the_verdict_of_open_sources():
    open_source = NumericalErrorSource("run:splitting", "splitting", ErrorSourceStatus.UNQUANTIFIED, None, "explicit_staggering")
    diagnostic = NumericalErrorSource("edge:e:occurrence:1", "mapping", ErrorSourceStatus.DIAGNOSTIC, 0.0, "mapping_round_trip")
    with_diag = CouplingNumericalErrorAssessment("r", "a" * 64, True, (open_source, diagnostic))
    without = CouplingNumericalErrorAssessment("r", "a" * 64, True, (open_source,))
    assert with_diag.verdict is without.verdict is ErrorAccountingVerdict.INCOMPLETE


# ---- the run record and the claims channel ---------------------------------------------------


def _uncoupled(run_id="coupled"):
    spec = ParticipantSpec("a", "m", "1", "r", "1", "s", "1", "a", "1",
                           (PortDefinition("x", PortDirection.OUTPUT, PortKind.SCALAR, "temperature", "K"),),
                           transient=True, checkpointable=True, deterministic_restore=True)
    participant = CallbackParticipant(
        spec, initialize=lambda *_: InitializationResult({"x": Quantity(0, "K")}, {"x": UNKNOWN}),
        advance=lambda r: AdvanceResult(r.end, {"x": Quantity(1, "K")}, {"x": UNKNOWN}, 1, True),
        checkpoint=lambda t: RuntimeCheckpoint(CheckpointRecord("a", t, "0" * 64, True), None),
        restore=lambda cp: None)
    plan = CouplingPlan("solo", CouplingScheme.EXPLICIT, IterationSemantics.SERIAL,
                        TimePolicy(Quantity(0, "s"), Quantity(1, "s"), Quantity(1, "s")))
    store = InMemoryBulkStore()
    return MultiphysicsRuntime(PhysicsGraph("solo", (spec,), ()), plan, {"a": participant},
                               resolver=BulkDataResolver(store), store=store).run(run_id, external_inputs={})


def _study(run_id="coupled", values=(2.0, 3.0, 5.0)):
    levels = tuple(RefinementLevel(k, v, {"n": 2 ** (2 - k)}, f"{run_id}~numerical~{k}") for k, v in enumerate(values))
    estimate = estimate_numerical_uncertainty(levels, quantity="q", units="K", refinement_ratio=2.0, formal_order=1.0,
                                              order_tolerance=0.1)
    return {"channel": UncertaintyChannel.NUMERICAL.value, "kind": "refinement", "spec": {"ratio": 2.0},
            "runs": [{"run_id": level.run_id, "value": level.value} for level in levels],
            "estimate": estimate.to_dict(), "problem": None, "uncertainty": estimate.to_uncertainty().to_dict()}


def test_the_runtime_no_longer_records_a_coupling_error_bound():
    run = _uncoupled()
    assert run.coupling_error_bound is None
    assert run.final_outputs["_coupling_error"]["evidence_class"] == "diagnostic_not_bound"


def _with_assessment(monkeypatch, run, sources):
    assessment = CouplingNumericalErrorAssessment(run.run_id, run_digest(run), True, tuple(sources))
    monkeypatch.setattr(coupling_numerical, "assess_coupling_numerical_error", lambda _run, splitting=None: assessment)


def test_a_zero_conservation_residual_no_longer_passes_the_numerical_channel(monkeypatch):
    run = _uncoupled()
    _with_assessment(monkeypatch, run, [
        NumericalErrorSource("edge:e:occurrence:1", "mapping", ErrorSourceStatus.DIAGNOSTIC, 0.0, "mapping_conservation"),
    ])
    out = condition_numerical_uncertainty(_study(), run)
    assert out.action is CouplingConditionAction.VETOED
    assert not out.uncertainty.is_quantified


def test_a_diagnostic_beside_an_open_forward_error_vetoes_through_the_forward_error(monkeypatch):
    run = _uncoupled()
    _with_assessment(monkeypatch, run, [
        NumericalErrorSource("edge:e:occurrence:1", "mapping", ErrorSourceStatus.DIAGNOSTIC, 0.0, "mapping_conservation"),
        NumericalErrorSource("window:0:edge:e:mapping_forward_error", "mapping", ErrorSourceStatus.UNQUANTIFIED, None,
                             "mapping_forward_error"),
    ])
    out = condition_numerical_uncertainty(_study(), run)
    assert out.action is CouplingConditionAction.VETOED
    assert "mapping_forward_error" in out.reason


def test_a_diagnostic_does_not_veto_sources_that_are_exactly_zero(monkeypatch):
    run = _uncoupled()
    _with_assessment(monkeypatch, run, [
        NumericalErrorSource("edge:e:occurrence:1", "mapping", ErrorSourceStatus.DIAGNOSTIC, 0.25, "mapping_round_trip"),
        NumericalErrorSource("hypothetical:proven", "mapping", ErrorSourceStatus.QUANTIFIED, 0.0, "proven_zero"),
    ])
    out = condition_numerical_uncertainty(_study(), run)
    assert out.action is CouplingConditionAction.PASSED
