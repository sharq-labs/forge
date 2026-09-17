"""Batch 7 of the 2026-09-16 core re-audit: the credibility report reads the whole result (I-10).

Closes R-10 (the report never read convergence), R-40 (a provenance override dropped declared but unassessed
models) and R-43 (UncertaintySource reached no verdict, report or budget, and SRIA channels accepted a
NUMERICAL record as aleatoric or model form). Preregistered in
`benchmarks/core_v4_false_confidence/BATCH7_THRESHOLD_PROTOCOL.json`.

R-10 and the from_result half of R-43 are on the PRODUCTION path: the MCP tools build their reports through
`from_result` and read `derive_verdict`, and production passes `run.provenance` as the override R-40 is about.

Every test here was committed as `xfail(strict=True)` first and run with `--runxfail` at 8149151 to watch it
fail; the markers came off in the implementation commit, and the xfail commit is 5b8d036. What the 25 of them failed on there, recorded so
the evidence is not overstated:

* 10 on an assertion, which is the scientific content: each of the four unfinished convergence states
  reporting SUPPORTED, the same verdict surviving a round trip, and the provenance override leaving
  ``unassessed_models`` empty;
* 4 on ``CredibilityEvidenceError: serialized verdict 'insufficient_evidence' does not match the verdict its
  contents produce ('supported')`` -- the boundary's own consistency check firing because the verdict the test
  writes into the payload is the one the fix will derive and the unfixed code does not;
* 3 on ``DID NOT RAISE`` -- the SRIA channel refusals, which is an assertion about a refusal that is absent;
* 7 on ``AttributeError`` and 1 on ``TypeError`` -- the fields, properties and keyword argument the
  improvement adds, which could not be posed at 8149151 at all. Their scientific content is carried by the
  assertion group above: the same four states, the same override, the same numerical estimate.

``test_r10_a_converged_result_keeps_its_verdict`` and ``test_r40_an_override_may_still_widen_the_inventory``
already held at 8149151 and are not reproductions: they are the guards that this batch changes neither the
converged path nor the widening half of the override, so they carry no xfail.
"""

from __future__ import annotations

import json

import pytest

from engcore.domains.thermal_models.lumped import LUMPED_CAPACITY_MODEL
from engcore.mcp.errors import CredibilityEvidenceError
from engcore.mcp.evidence import (
    CredibilityEvidenceReport,
    CredibilityVerdict,
    ModelValidityRecord,
    derive_verdict,
)
from engcore.scientific.ir.problem import ModelReference
from engcore.scientific.models.definition import ValidityAssessment, ValidityStatus
from engcore.scientific.results.provenance import ExecutionBinding, ProvenanceRecord
from engcore.scientific.results.result import ScientificResult
from engcore.scientific.results.uncertainty import (
    Uncertainty,
    UncertaintyKind,
    UncertaintySource,
)
from engcore.scientific.results.validation import (
    ValidationCheck,
    ValidationLevel,
    ValidationOutcome,
    ValidationReport,
)
from engcore.scientific.solvers.protocol import ConvergenceState, SolverIdentity
from engcore.scientific.units.quantity import Quantity

MODEL = ModelReference(LUMPED_CAPACITY_MODEL.model_id, LUMPED_CAPACITY_MODEL.version)
OTHER = ModelReference("electrical.dc.kcl", "0.1.0")
SOLVER = SolverIdentity("audit.lumped_ode", "1")
CONDITIONS = tuple(c.name for c in LUMPED_CAPACITY_MODEL.validity.conditions)

#: The states a solver reports that are neither "it finished" nor "it does not converge at all".
UNFINISHED = (
    ConvergenceState.NOT_CONVERGED,
    ConvergenceState.MAX_ITERATIONS,
    ConvergenceState.DIVERGED,
    ConvergenceState.FAILED,
)


def _in_domain() -> ValidityAssessment:
    return ValidityAssessment(status=ValidityStatus.IN_DOMAIN, satisfied=CONDITIONS)


def _result(**overrides) -> ScientificResult:
    """A result that is SUPPORTED on every axis except the one a test moves."""
    fields = dict(
        result_id="batch7-result",
        values={"T": Quantity(350.0, "K")},
        provenance=ProvenanceRecord(run_id="batch7-run",
                                    bindings=(ExecutionBinding(model=MODEL, solver=SOLVER),)),
        models=(MODEL.key,),
        solver=SOLVER,
        convergence=ConvergenceState.CONVERGED,
        validation=ValidationReport(checks=(ValidationCheck(
            name="analytic", outcome=ValidationOutcome.PASS,
            # R-04 (batch 9): ANALYTICALLY_VERIFIED is now held to its issuer's record. This
            # fixture needs a level-bearing PASS check and not that particular level, and
            # DIMENSIONALLY_VALID needs no issuer.
            establishes=ValidationLevel.DIMENSIONALLY_VALID, residual=1e-9, tolerance=1e-6),)),
        validity={MODEL.model_id: _in_domain()},
    )
    fields.update(overrides)
    return ScientificResult(**fields)


# =====================================================================
# R-10: the report never read the result's convergence
# =====================================================================
@pytest.mark.parametrize("state", UNFINISHED, ids=[s.value for s in UNFINISHED])
def test_r10_a_result_whose_solver_did_not_finish_is_never_supported(state):
    """The audited record: convergence=diverged, is_usable=False, verdict=supported."""
    result = _result(convergence=state)
    assert result.is_usable is False
    report = CredibilityEvidenceReport.from_result(result)
    assert report.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE, (
        f"a result whose solver reported {state.value} with one passing level-bearing check reports "
        f"{report.verdict.value}")


@pytest.mark.parametrize("state", UNFINISHED, ids=[s.value for s in UNFINISHED])
def test_r10_the_convergence_state_is_in_the_report_and_its_json(state):
    """'convergence' in report JSON: False, in the audited record."""
    report = CredibilityEvidenceReport.from_result(_result(convergence=state))
    assert report.convergence is state
    payload = json.loads(json.dumps(report.to_dict()))
    assert payload["convergence"] == state.value


@pytest.mark.parametrize("state", UNFINISHED, ids=[s.value for s in UNFINISHED])
def test_r10_the_downgrade_survives_a_round_trip(state):
    """The audited record read back SUPPORTED after from_dict."""
    report = CredibilityEvidenceReport.from_result(_result(convergence=state))
    again = CredibilityEvidenceReport.from_dict(json.loads(json.dumps(report.to_dict())))
    assert again.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE


@pytest.mark.parametrize("state", UNFINISHED, ids=[s.value for s in UNFINISHED])
def test_r10_the_downgrade_survives_a_payload_with_the_new_field_deleted(state):
    """A reader written before the field, and a hand-edit that deletes it, both keep the downgrade.

    That is what the NOT_RUN check is for: a new top-level field is additive, so it can be dropped, and a
    payload whose verdict was rewritten to match would then re-derive SUPPORTED.
    """
    payload = json.loads(json.dumps(CredibilityEvidenceReport.from_result(_result(convergence=state)).to_dict()))
    payload.pop("convergence", None)
    payload["verdict"] = CredibilityVerdict.INSUFFICIENT_EVIDENCE.value
    assert CredibilityEvidenceReport.from_dict(payload).verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE


def test_r10_a_converged_result_keeps_its_verdict():
    """The route that must keep working. Already held at 8149151, so it carries no xfail: it is the guard that
    this batch does not change the converged path, not a reproduction."""
    assert CredibilityEvidenceReport.from_result(_result()).verdict is CredibilityVerdict.SUPPORTED
    direct = CredibilityEvidenceReport.from_result(_result(convergence=ConvergenceState.NOT_APPLICABLE))
    assert direct.verdict is CredibilityVerdict.SUPPORTED


def test_r10_a_converged_result_carries_the_state_it_reached():
    """NOT_APPLICABLE is a claim -- direct or closed-form evaluation -- and None is the absence of one, which
    is why the field's default decides nothing."""
    assert CredibilityEvidenceReport.from_result(_result()).convergence is ConvergenceState.CONVERGED
    direct = CredibilityEvidenceReport.from_result(_result(convergence=ConvergenceState.NOT_APPLICABLE))
    assert direct.convergence is ConvergenceState.NOT_APPLICABLE


def test_r10_derive_verdict_reads_convergence_on_its_own():
    """derive_verdict is exported and documented as usable alone, so the rule has to live in it."""
    result = _result()
    passing = dict(
        validity=[ModelValidityRecord(model_id=MODEL.model_id, version=MODEL.version, assessment=_in_domain())],
        validation=list(result.validation.checks))
    assert derive_verdict(**passing) is CredibilityVerdict.SUPPORTED
    assert derive_verdict(**passing, convergence=ConvergenceState.CONVERGED) is CredibilityVerdict.SUPPORTED
    assert derive_verdict(**passing, convergence=ConvergenceState.NOT_APPLICABLE) is CredibilityVerdict.SUPPORTED
    for state in UNFINISHED:
        assert derive_verdict(**passing, convergence=state) is CredibilityVerdict.INSUFFICIENT_EVIDENCE, state


# =====================================================================
# R-40: a provenance override dropped declared but unassessed models
# =====================================================================
def _two_models() -> ScientificResult:
    """A result declaring two models, one assessed IN_DOMAIN and one explicitly not assessed."""
    return _result(
        models=(MODEL.key, OTHER.key),
        provenance=ProvenanceRecord(run_id="batch7-run", bindings=(
            ExecutionBinding(model=MODEL, solver=SOLVER), ExecutionBinding(model=OTHER, solver=SOLVER))),
        validity={MODEL.model_id: _in_domain()},
        validity_not_assessed={OTHER.model_id: "no validity domain was declared for this model"},
    )


def test_r40_a_provenance_override_cannot_drop_a_declared_model():
    """The audited record: INSUFFICIENT_EVIDENCE with the result's own provenance, SUPPORTED with an
    overriding run provenance naming only the assessed model, and unassessed=()."""
    result = _two_models()
    own = CredibilityEvidenceReport.from_result(result)
    assert own.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE
    assert OTHER.key in own.unassessed_models
    narrowed = ProvenanceRecord(run_id="coupled-run",
                                bindings=(ExecutionBinding(model=MODEL, solver=SOLVER),))
    overridden = CredibilityEvidenceReport.from_result(result, provenance=narrowed)
    assert OTHER.key in overridden.unassessed_models, (
        f"an override provenance naming only {MODEL.model_id!r} left unassessed_models "
        f"{overridden.unassessed_models}")
    assert overridden.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE


def test_r40_an_override_may_still_widen_the_inventory():
    """The route that must keep working: the override is the documented path for a coupled run, and a run
    provenance naming MORE models than the result declares still adds them."""
    third = ModelReference("thermal.conduction1d.linear_diffusion", "0.1.0")
    wider = ProvenanceRecord(run_id="coupled-run", bindings=(
        ExecutionBinding(model=MODEL, solver=SOLVER), ExecutionBinding(model=third, solver=SOLVER)))
    report = CredibilityEvidenceReport.from_result(_result(), provenance=wider)
    assert third.key in report.known_models and MODEL.key in report.known_models


# =====================================================================
# R-43: uncertainty reached no verdict, report or budget
# =====================================================================
def _numerical(value: float = 0.001) -> Uncertainty:
    return Uncertainty(kind=UncertaintyKind.STANDARD, standard_uncertainty=Quantity(value, "K"),
                       source_kind=UncertaintySource.NUMERICAL, method="mesh refinement, two levels")


def test_r43_the_report_carries_per_value_uncertainty_and_its_source():
    """The audited record: from_result drops result.uncertainty, and 'numerical' appears nowhere in the JSON."""
    report = CredibilityEvidenceReport.from_result(_result(uncertainty={"T": _numerical()}))
    assert report.uncertainty["T"].source_kind is UncertaintySource.NUMERICAL
    payload = json.loads(json.dumps(report.to_dict()))
    assert payload["uncertainty"]["T"]["source_kind"] == "numerical"
    assert payload["verdict_qualifiers"]["uncertainty_sources"] == {"T": "numerical"}
    again = CredibilityEvidenceReport.from_dict(payload)
    assert again.uncertainty["T"].source_kind is UncertaintySource.NUMERICAL


def test_r43_a_numerical_estimate_may_not_be_declared_as_aleatoric_or_model_form():
    """The audited record: a mesh-refinement NUMERICAL estimate filed under ALEATORIC and MODEL_FORM makes
    budget_from_declaration report both channels as KNOWN."""
    from engcore.sria.uncertainty import (
        DiscrepancyKind,
        ModelDiscrepancy,
        SubjectModel,
        UncertaintyChannel,
        UncertaintyDeclaration,
    )

    for channel in (UncertaintyChannel.ALEATORIC, UncertaintyChannel.MODEL_FORM,
                    UncertaintyChannel.EPISTEMIC_PARAMETER):
        with pytest.raises(Exception) as raised:
            UncertaintyDeclaration(
                subject_model=SubjectModel.PREDICTION_MODEL,
                discrepancy=ModelDiscrepancy(kind=DiscrepancyKind.ZERO_DECLARED, rationale="declared zero"),
                channels={channel: _numerical()})
        assert "numerical" in str(raised.value).lower(), (channel, raised.value)
    # the one channel it belongs to is accepted
    UncertaintyDeclaration(
        subject_model=SubjectModel.PREDICTION_MODEL,
        discrepancy=ModelDiscrepancy(kind=DiscrepancyKind.ZERO_DECLARED, rationale="declared zero"),
        channels={UncertaintyChannel.NUMERICAL: _numerical()})


def test_r43_a_budget_channel_entry_refuses_a_contradictory_source():
    from engcore.sria.assurance.uncertainty_budget import ChannelEntry, ChannelState
    from engcore.sria.uncertainty import UncertaintyChannel

    with pytest.raises(Exception, match="(?i)numerical"):
        ChannelEntry(channel=UncertaintyChannel.ALEATORIC, state=ChannelState.KNOWN,
                     uncertainty=_numerical(), rationale="mesh study")
    ChannelEntry(channel=UncertaintyChannel.NUMERICAL, state=ChannelState.KNOWN,
                 uncertainty=_numerical(), rationale="mesh study")


def test_r43_a_combined_uncertainty_belongs_to_no_single_channel():
    """COMBINED is already a mixture: root-sum-squaring it with another channel double-counts what it holds."""
    from engcore.sria.assurance.uncertainty_budget import ChannelEntry, ChannelState
    from engcore.sria.uncertainty import UncertaintyChannel

    combined = Uncertainty(kind=UncertaintyKind.STANDARD, standard_uncertainty=Quantity(0.01, "K"),
                           source_kind=UncertaintySource.COMBINED, method="parameter plus noise")
    for channel in UncertaintyChannel:
        with pytest.raises(Exception, match="(?i)combined"):
            ChannelEntry(channel=channel, state=ChannelState.KNOWN, uncertainty=combined, rationale="x")


def test_r43_an_undeclared_source_is_recorded_as_unattributed_not_as_compatible():
    """UNSPECIFIED is accepted -- every domain solver still emits it -- and named, so it is visible."""
    from engcore.sria.uncertainty import (
        DiscrepancyKind,
        ModelDiscrepancy,
        SubjectModel,
        UncertaintyChannel,
        UncertaintyDeclaration,
    )

    unspecified = Uncertainty(kind=UncertaintyKind.STANDARD, standard_uncertainty=Quantity(0.01, "K"),
                              method="solver estimate")
    declaration = UncertaintyDeclaration(
        subject_model=SubjectModel.PREDICTION_MODEL,
        discrepancy=ModelDiscrepancy(kind=DiscrepancyKind.ZERO_DECLARED, rationale="declared zero"),
        channels={UncertaintyChannel.ALEATORIC: unspecified})
    assert declaration.unattributed_channels == (UncertaintyChannel.ALEATORIC,)


def test_r43_the_v1_predictive_intervals_declare_what_they_are_of():
    """posterior_predictive_uq knows its epistemic interval is PARAMETER and its total is COMBINED, says so in
    its notes in prose, and left source_kind UNSPECIFIED on both."""
    import numpy as np

    from engcore.inference.grid import AdmittedForwardTable, PosteriorGrid
    from engcore.scientific.twins import TwinReference
    from engcore.uq.predictive import PredictiveObservableSpec, posterior_predictive_uq

    points = np.linspace(0.8, 1.2, 41).reshape(-1, 1)
    density = np.exp(-0.5 * ((points[:, 0] - 1.0) / 0.05) ** 2)
    admissible = np.ones(len(points), dtype=bool)
    grid = PosteriorGrid(parameter_names=("k",), points=points, log_likelihood=np.log(density),
                         weights=density / density.sum(), dataset_id="batch7.uq", admissible_mask=admissible)
    key = "pred:y"
    table = AdmittedForwardTable(
        parameter_names=("k",), observation_keys=(key,), points=points, values=points.copy(),
        admissible_mask=admissible, admission_refs=tuple(("analytic|fixture|ver|bind",) for _ in points),
        rejection_reasons=tuple("" for _ in points))
    quantified = posterior_predictive_uq(
        grid, table, PredictiveObservableSpec(key, "dimensionless", Quantity(0.02, "dimensionless")),
        twin=TwinReference("batch7.twin", "1"), model=ModelReference("batch7.model", "1"),
        source_ref="prediction")
    assert quantified.epistemic_interval.source_kind is UncertaintySource.PARAMETER
    assert quantified.total_interval.source_kind is UncertaintySource.COMBINED
