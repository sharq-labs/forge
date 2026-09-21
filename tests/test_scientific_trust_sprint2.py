"""The trust engine: what evidence exists, and what it is allowed to prove.

The reference data here is a declared fixture, not a scientific citation. Its
"expected" values come from a closed-form rule this file states, and the
"model" is a deliberately imperfect version of that rule. That is the point:
what is under test is the machinery that decides what the disagreement means,
and borrowing real measurements would make the test about the measurements.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from engcore.assembly.certification import (
    COMPUTATIONAL_REPLAY_VERIFIED,
    MULTIPHYSICS_FULL_TRUST_POLICY,
    MULTIPHYSICS_PRODUCTION_POLICY,
    NUMERICAL_EVIDENCE_PRESENT,
    SERIALIZATION_ROUNDTRIP_VERIFIED,
    UQ_CHANNEL_COMPLETENESS,
    VALIDATION_ENVELOPE_SUPPORTED,
    VALIDATION_PROTOCOL_COMPLETENESS,
    TrustPolicy,
    assess_authorized_multiphysics_run,
    certify_authorized_multiphysics_run,
)
from engcore.assembly.domainpacks import (
    production_composition_packs,
    production_execution_packs,
)
from engcore.assembly.multiphysics import execute_authorized_graph_plan
from engcore.assembly.replay import (
    DEFAULT_REPLAY_POLICY,
    ReplayPolicy,
    ReplayStatus,
    replay_authorized_graph_plan,
)
from engcore.assembly.trust import (
    UQCellState,
    assess_protocol_completeness,
    assess_uq_coverage,
)
from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.planning import (
    ContextOfUse,
    EngineeringComponent,
    EngineeringIntent,
    FactRole,
    IntentFact,
    IntentQuantityOfInterest,
    PlannerPolicy,
    SimulationHorizon,
    plan_engineering_intent,
)
from engcore.planning.production import production_planning_registries
from engcore.scientific.certification_core.verifier import verify_certification_record
from engcore.scientific.corpus import (
    Applicability,
    EvidenceBinding,
    AuthorityRole,
    AuthorityComponent,
    CalibratedParameterSet,
    CalibrationError,
    CalibrationObjective,
    CalibrationParameterSpec,
    CaseVerdict,
    CheckOutcome,
    CorpusError,
    CorpusLeakageError,
    CoverageDimension,
    DatasetSplit,
    EnvelopeVerdict,
    FittedParameter,
    HoldoutRelease,
    InadequacyKind,
    ModelFormDiagnosis,
    Identifiability,
    NumericalCheck,
    NumericalCheckResult,
    NumericalEvidence,
    PredictedValue,
    PredictionRefusal,
    PriorSource,
    ReferenceCase,
    ReferenceCondition,
    ReferenceDataset,
    ReferenceObservation,
    ReferenceSource,
    RefusalKind,
    SourceSnapshot,
    ToleranceBasis,
    ToleranceSpec,
    ValidationCampaign,
    ValidationCampaignReport,
    ValidationEnvelope,
    ValidationQueryPoint,
    ValidationRegion,
    build_coverage,
    build_coverage_by_metric,
    cluster_failures,
    diagnose_campaign,
    run_campaign,
)
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.replay_core.tolerance import ReplayTolerance
from engcore.scientific.units.quantity import Quantity

# =====================================================================
# A declared fixture corpus.
#
# The "source" reports  y = 10 + 0.5 * (T - 300)  exactly.
# The "model" computes  y = 10 + 0.5 * (T - 300) - 0.0004 * (T - 300)^2,
# so it is right near 300 K and drifts quadratically away from it. Against a
# 0.5 V reviewed tolerance that is inside tolerance out to about 335 K and
# outside it beyond -- a model-FORM defect, because no setting of the linear
# coefficient fixes both ends at once.
# =====================================================================

SOURCE = ReferenceSource(
    source_id="fixture.linear_response",
    authority="Forge test fixture, not a scientific citation",
    domain="generic",
    source_version="1",
    landing_url="https://fixtures.invalid/linear-response",
    allowed_hosts=("fixtures.invalid",),
)
SNAPSHOT = SourceSnapshot(
    source_id="fixture.linear_response",
    source_version="1",
    snapshot_sha256="1" * 64,
    snapshot_url="https://fixtures.invalid/linear-response/v1.csv",
    byte_length=4096,
    retrieved_at_utc="2026-01-01T00:00:00+00:00",
)

CALIBRATION_TEMPERATURES = (295.0, 300.0, 305.0, 310.0)
VALIDATION_TEMPERATURES = (315.0, 340.0, 365.0, 390.0)
HOLDOUT_TEMPERATURES = (420.0, 450.0)


def _truth(temperature: float) -> float:
    return 10.0 + 0.5 * (temperature - 300.0)


def _model(temperature: float) -> float:
    delta = temperature - 300.0
    return 10.0 + 0.5 * delta - 0.0004 * delta * delta


def _tolerance(value: float, basis: ToleranceBasis = ToleranceBasis.REVIEWED_ACCEPTANCE):
    return ToleranceSpec(Quantity(value, "V"), basis, "reviewed for this fixture")


def _case(temperature: float, split: DatasetSplit, **kwargs) -> ReferenceCase:
    """A screened case. Applicability is stated, because scoring requires it.

    ``INSIDE`` is explicit rather than defaulted: a case whose applicability
    was never established cannot produce empirical support, so a fixture that
    means to test PASS/FAIL has to say the screening was done.
    """
    kwargs.setdefault("applicability", Applicability.INSIDE)
    return ReferenceCase(
        case_id=f"T{int(temperature)}",
        split=split,
        independence_group=f"specimen-{int(temperature)}",
        conditions=(ReferenceCondition("temperature", Quantity(temperature, "K")),),
        **kwargs,
    )


def _observation(temperature: float, *, tolerance: float | None = 0.5) -> ReferenceObservation:
    return ReferenceObservation(
        case_id=f"T{int(temperature)}",
        metric="response",
        expected=Quantity(_truth(temperature), "V"),
        source_uncertainty=_tolerance(0.05, ToleranceBasis.SOURCE_REPORTED),
        acceptance_tolerance=None if tolerance is None else _tolerance(tolerance),
    )


def _dataset(**overrides) -> ReferenceDataset:
    cases = [
        *(_case(t, DatasetSplit.CALIBRATION) for t in CALIBRATION_TEMPERATURES),
        *(_case(t, DatasetSplit.VALIDATION) for t in VALIDATION_TEMPERATURES),
        *(_case(t, DatasetSplit.LOCKED_HOLDOUT) for t in HOLDOUT_TEMPERATURES),
    ]
    observations = [
        _observation(t)
        for t in (*CALIBRATION_TEMPERATURES, *VALIDATION_TEMPERATURES, *HOLDOUT_TEMPERATURES)
    ]
    defaults = dict(
        dataset_id="fixture.linear_response",
        version="1",
        source=SOURCE,
        snapshot=SNAPSHOT,
        cases=tuple(cases),
        observations=tuple(observations),
    )
    defaults.update(overrides)
    return ReferenceDataset(**defaults)


def _predictions(dataset: ReferenceDataset, cases) -> dict:
    out = {}
    for case in cases:
        temperature = case.condition("temperature").magnitude_in("K")
        out[(case.case_id, "response")] = PredictedValue(
            Quantity(_model(temperature), "V")
        )
    return out


def _ledger():
    """A fresh in-process opening authority, with a fixed clock."""
    from engcore.scientific.corpus import InMemoryHoldoutLedger

    return InMemoryHoldoutLedger(clock=lambda: "2026-02-02T00:00:00+00:00")


def _full_binding(authorized):
    """The run's own binding, which satisfies every scope profile."""
    from engcore.assembly.trust import authorized_run_binding

    return authorized_run_binding(authorized)


def _region() -> ValidationRegion:
    return ValidationRegion(
        "fixture.temperature",
        (CoverageDimension("temperature", "K", (320.0, 350.0, 400.0)),),
        minimum_supporting_cases=2,
    )


# =====================================================================
# DATA INDEPENDENCE
# =====================================================================

def test_locked_holdout_is_unreachable_without_a_registered_release():
    dataset = _dataset()

    assert [c.case_id for c in dataset.calibration_cases()] == ["T295", "T300", "T305", "T310"]
    assert all(
        case.split is not DatasetSplit.LOCKED_HOLDOUT
        for case in dataset.cases_for_fitting()
    )
    # A release is permission, not proof: the cases come from an OPENING.
    with pytest.raises(CorpusLeakageError, match="recorded HoldoutOpening"):
        dataset.opened_holdout_cases(None)


def test_a_release_does_not_carry_over_to_a_changed_dataset():
    dataset = _dataset()
    release = HoldoutRelease(
        "eval-1", "c", "1", dataset.normalized_digest,
        "2026-02-01T00:00:00+00:00", "registered",
    )
    dataset.require_release(release)
    assert len(dataset.opened_holdout_cases(_ledger().open(release))) == 2

    # One tolerance reviewed differently is a different dataset.
    changed = _dataset(
        observations=tuple(
            _observation(t, tolerance=0.9 if t == 420.0 else 0.5)
            for t in (*CALIBRATION_TEMPERATURES, *VALIDATION_TEMPERATURES, *HOLDOUT_TEMPERATURES)
        )
    )
    assert changed.normalized_digest != dataset.normalized_digest
    with pytest.raises(CorpusLeakageError, match="does not carry over"):
        changed.require_release(release)


def test_one_independence_group_may_not_straddle_the_calibration_boundary():
    shared = (
        _case(295.0, DatasetSplit.CALIBRATION),
        ReferenceCase(
            case_id="T315",
            split=DatasetSplit.VALIDATION,
            independence_group="specimen-295",
            conditions=(ReferenceCondition("temperature", Quantity(315.0, "K")),),
        ),
    )
    with pytest.raises(CorpusLeakageError, match="cannot be the fit and the test"):
        _dataset(
            cases=shared,
            observations=(_observation(295.0), _observation(315.0)),
        )


def test_a_campaign_over_the_holdout_requires_its_release():
    dataset = _dataset()
    with pytest.raises(CorpusError, match="requires a registered HoldoutRelease"):
        ValidationCampaign("c", "1", dataset, (DatasetSplit.LOCKED_HOLDOUT,))


def test_a_campaign_refuses_predictions_for_cases_it_may_not_see():
    dataset = _dataset()
    campaign = ValidationCampaign("c", "1", dataset, (DatasetSplit.CALIBRATION,))
    with pytest.raises(CorpusError, match="outside this campaign's splits"):
        run_campaign(campaign, {("T420", "response"): PredictedValue(Quantity(70.0, "V"))})


# =====================================================================
# CORE-DERIVED VERDICTS
# =====================================================================

def test_core_derives_pass_and_fail_from_the_evidence():
    dataset = _dataset()
    campaign = ValidationCampaign("c", "1", dataset, (DatasetSplit.VALIDATION,))
    report = run_campaign(campaign, _predictions(dataset, campaign.cases()))

    by_case = {item.case_id: item for item in report.comparisons}
    # 315 K: the quadratic defect is 0.09 V, inside the 0.5 V tolerance.
    assert by_case["T315"].verdict is CaseVerdict.PASS
    assert by_case["T315"].normalized_residual < 1.0
    # 390 K: the defect is 3.24 V, outside it.
    assert by_case["T390"].verdict is CaseVerdict.FAIL
    assert by_case["T390"].normalized_residual > 1.0
    assert by_case["T390"].residual == pytest.approx(0.0004 * 90.0 * 90.0)


def test_a_missing_acceptance_tolerance_is_unscored_and_never_a_pass():
    dataset = _dataset(
        observations=tuple(
            _observation(t, tolerance=None if t == 340.0 else 0.5)
            for t in (*CALIBRATION_TEMPERATURES, *VALIDATION_TEMPERATURES, *HOLDOUT_TEMPERATURES)
        )
    )
    campaign = ValidationCampaign("c", "1", dataset, (DatasetSplit.VALIDATION,))
    report = run_campaign(campaign, _predictions(dataset, campaign.cases()))

    by_case = {item.case_id: item for item in report.comparisons}
    # T340 would have FAILED. With no reviewed tolerance it is UNSCORED, and
    # it is excluded from the pass fraction rather than counted as a success.
    assert by_case["T340"].verdict is CaseVerdict.UNSCORED
    assert report.pass_fraction == pytest.approx(1 / 3)


def test_a_source_uncertainty_cannot_stand_in_as_acceptance_policy():
    with pytest.raises(CorpusError, match="different scientific claim"):
        ReferenceObservation(
            case_id="T315",
            metric="response",
            expected=Quantity(17.5, "V"),
            acceptance_tolerance=_tolerance(0.5, ToleranceBasis.SOURCE_REPORTED),
        )


def test_a_missing_prediction_is_missing_and_not_a_refusal():
    dataset = _dataset()
    campaign = ValidationCampaign("c", "1", dataset, (DatasetSplit.VALIDATION,))
    report = run_campaign(campaign, {})
    assert {item.verdict for item in report.comparisons} == {CaseVerdict.MISSING}
    assert report.pass_fraction is None


# =====================================================================
# REFUSALS ARE RESULTS
# =====================================================================

def test_declining_outside_declared_applicability_is_a_correct_refusal():
    cases = (
        _case(315.0, DatasetSplit.VALIDATION, applicability=Applicability.OUTSIDE),
    )
    dataset = _dataset(cases=cases, observations=(_observation(315.0),))
    campaign = ValidationCampaign("c", "1", dataset, (DatasetSplit.VALIDATION,))
    report = run_campaign(
        campaign,
        {
            ("T315", "response"): PredictionRefusal(
                RefusalKind.APPLICABILITY, "outside the declared validity domain"
            )
        },
    )
    verdict = report.comparisons[0].verdict
    assert verdict is CaseVerdict.CORRECT_REFUSAL
    # The guardrail worked. That is NOT evidence the science is right here.
    assert verdict.is_guardrail_success
    assert not verdict.is_empirical_support
    assert not verdict.is_scored
    assert report.pass_fraction is None
    assert report.refusal_accuracy == 1.0


def test_declining_inside_the_claimed_envelope_is_an_unexpected_refusal():
    cases = (_case(315.0, DatasetSplit.VALIDATION, applicability=Applicability.INSIDE),)
    dataset = _dataset(cases=cases, observations=(_observation(315.0),))
    campaign = ValidationCampaign("c", "1", dataset, (DatasetSplit.VALIDATION,))
    report = run_campaign(
        campaign,
        {("T315", "response"): PredictionRefusal(RefusalKind.NUMERICAL, "solver diverged")},
    )
    verdict = report.comparisons[0].verdict
    assert verdict is CaseVerdict.UNEXPECTED_REFUSAL
    assert not verdict.is_empirical_support
    assert not verdict.is_guardrail_success
    assert report.refusal_accuracy == 0.0


def test_answering_outside_applicability_is_recorded_and_not_scored():
    cases = (_case(315.0, DatasetSplit.VALIDATION, applicability=Applicability.OUTSIDE),)
    dataset = _dataset(cases=cases, observations=(_observation(315.0),))
    campaign = ValidationCampaign("c", "1", dataset, (DatasetSplit.VALIDATION,))
    report = run_campaign(campaign, _predictions(dataset, campaign.cases()))

    assert report.comparisons[0].verdict is CaseVerdict.OUTSIDE_APPLICABILITY
    assert report.pass_fraction is None


# =====================================================================
# COVERAGE AND ENVELOPE
# =====================================================================

def test_coverage_reports_untested_cells_rather_than_omitting_them():
    dataset = _dataset()
    campaign = ValidationCampaign("c", "1", dataset, (DatasetSplit.VALIDATION,))
    report = run_campaign(campaign, _predictions(dataset, campaign.cases()))
    coverage = build_coverage(report, dataset, _region(), metric="response")

    # Four bins, every one present even though only three were exercised.
    assert len(coverage.cells) == 4
    assert coverage.status_counts()["untested"] == 1


def test_the_envelope_separates_empirical_support_from_declared_applicability():
    dataset = _dataset()
    campaign = ValidationCampaign("c", "1", dataset, (DatasetSplit.VALIDATION,))
    report = run_campaign(campaign, _predictions(dataset, campaign.cases()))
    coverage = build_coverage(report, dataset, _region(), metric="response")
    envelope = ValidationEnvelope("e1", coverage, report.digest)

    # 318 K sits with T315, which passes -- one case, below the minimum of two.
    near = envelope.classify({"temperature": Quantity(318.0, "K")}, declared=Applicability.INSIDE)
    assert near.verdict is EnvelopeVerdict.SPARSE_SUPPORT

    # 360 K sits with failing cases.
    far = envelope.classify({"temperature": Quantity(360.0, "K")}, declared=Applicability.INSIDE)
    assert far.verdict is EnvelopeVerdict.OUTSIDE_VALIDATED_ENVELOPE

    # 500 K is in the top bin, which nothing has tested. Declared applicable
    # and empirically unsupported are BOTH visible; neither overrides the other.
    beyond = envelope.classify({"temperature": Quantity(500.0, "K")}, declared=Applicability.INSIDE)
    assert beyond.verdict is EnvelopeVerdict.EXTRAPOLATING
    assert beyond.declared is Applicability.INSIDE
    assert beyond.applicable_but_unsupported

    # A point that cannot be located is UNKNOWN, not extrapolating.
    assert envelope.classify({}).verdict is EnvelopeVerdict.UNKNOWN


def test_an_envelope_survives_a_roundtrip():
    dataset = _dataset()
    campaign = ValidationCampaign("c", "1", dataset, (DatasetSplit.VALIDATION,))
    report = run_campaign(campaign, _predictions(dataset, campaign.cases()))
    envelope = ValidationEnvelope("e1", build_coverage(report, dataset, _region(), metric="response"), report.digest)
    assert ValidationEnvelope.from_dict(envelope.to_dict()) == envelope
    assert ValidationCampaignReport.from_dict(report.to_dict()) == report


# =====================================================================
# MODEL FORM VS CALIBRATION
# =====================================================================

def test_a_good_fit_with_bad_holdout_is_a_suspicion_not_a_conclusion():
    dataset = _dataset()
    release = HoldoutRelease(
        "eval-1", "c", "1", dataset.normalized_digest,
        "2026-02-01T00:00:00+00:00", "registered",
    )
    campaign = ValidationCampaign(
        "c", "1", dataset,
        (DatasetSplit.CALIBRATION, DatasetSplit.VALIDATION, DatasetSplit.LOCKED_HOLDOUT),
        holdout_release=release,
    )
    opened = campaign.open_holdout(_ledger())
    report = run_campaign(opened, _predictions(dataset, opened.cases()))
    clusters = cluster_failures(report, dataset, _region())
    diagnosis = diagnose_campaign(report, clusters)

    assert diagnosis.calibration_pass_fraction == 1.0
    assert diagnosis.independent_pass_fraction is not None
    assert diagnosis.independent_pass_fraction < 0.5
    assert diagnosis.kind is InadequacyKind.MODEL_FORM_SUSPECTED
    # With no numerical or calibration evidence supplied, three alternative
    # causes are merely unexamined -- so this is a suspicion, not a finding.
    assert diagnosis.confidence == "suggestive"
    assert set(diagnosis.outstanding_alternatives) == {
        "numerical", "identifiability", "context_mismatch",
    }
    # It reports the pattern and refuses to name the mechanism.
    assert "which physics is missing" in diagnosis.why
    assert clusters and clusters[0].dimension == "temperature"


def test_a_poor_fit_is_diagnosed_as_calibration_rather_than_model_form():
    dataset = _dataset()
    campaign = ValidationCampaign(
        "c", "1", dataset, (DatasetSplit.CALIBRATION, DatasetSplit.VALIDATION)
    )
    # Everything off by 10 V, calibration included: the fit never landed.
    predictions = {
        key: PredictedValue(Quantity(value.value.magnitude_in("V") + 10.0, "V"))
        for key, value in _predictions(dataset, campaign.cases()).items()
    }
    diagnosis = diagnose_campaign(run_campaign(campaign, predictions))
    assert diagnosis.kind is InadequacyKind.CALIBRATION_PARAMETER


def test_thin_independent_evidence_diagnoses_nothing():
    dataset = _dataset(
        cases=(_case(295.0, DatasetSplit.CALIBRATION), _case(315.0, DatasetSplit.VALIDATION)),
        observations=(_observation(295.0), _observation(315.0)),
    )
    campaign = ValidationCampaign(
        "c", "1", dataset, (DatasetSplit.CALIBRATION, DatasetSplit.VALIDATION)
    )
    diagnosis = diagnose_campaign(run_campaign(campaign, _predictions(dataset, campaign.cases())))
    assert diagnosis.kind is InadequacyKind.INSUFFICIENT_EVIDENCE
    assert diagnosis.confidence == "none"


# =====================================================================
# CALIBRATION GOVERNANCE
# =====================================================================

def test_physically_impossible_calibrated_parameters_are_refused():
    spec = CalibrationParameterSpec(
        "internal_resistance", "ohm",
        lower_bound=Quantity(0.0, "ohm"),
        prior_source=PriorSource.MEASURED,
        prior_note="EIS record preceding the discharge",
    )
    objective = CalibrationObjective("rmse", "1")
    with pytest.raises(CalibrationError, match="physically impossible"):
        CalibratedParameterSet(
            "rint", "1", (spec,),
            (FittedParameter("internal_resistance", Quantity(-0.02, "ohm")),),
            objective, "fixture.linear_response", "1" * 64,
        )


def test_a_parameter_set_may_not_be_fitted_on_independent_evidence():
    spec = CalibrationParameterSpec("gain", "V/K", lower_bound=Quantity(0.0, "V/K"))
    with pytest.raises(CalibrationError, match="only calibration evidence"):
        CalibratedParameterSet(
            "gain-set", "1", (spec,),
            (FittedParameter("gain", Quantity(0.5, "V/K")),),
            CalibrationObjective("rmse", "1"), "fixture", "1" * 64,
            calibration_split=DatasetSplit.LOCKED_HOLDOUT,
        )


def test_an_identifiability_claim_needs_the_diagnostic_it_came_from():
    from engcore.scientific.corpus import Identifiability

    with pytest.raises(CalibrationError, match="needs the diagnostic"):
        FittedParameter("gain", Quantity(0.5, "V/K"), Identifiability.IDENTIFIED)


# =====================================================================
# NUMERICAL EVIDENCE
# =====================================================================

def test_a_solver_cannot_claim_a_check_it_does_not_declare():
    with pytest.raises(CorpusError, match="does not declare it can perform"):
        NumericalEvidence(
            "fixture.solver",
            (NumericalCheck.CONVERGENCE,),
            (
                NumericalCheckResult(
                    NumericalCheck.CONVERGENCE, CheckOutcome.SATISFIED, "residual fell", 1e-12
                ),
                NumericalCheckResult(
                    NumericalCheck.CONSERVATION, CheckOutcome.SATISFIED, "balanced", 1e-14
                ),
            ),
        )


def test_an_unperformed_check_is_explicit_rather_than_absent():
    evidence = NumericalEvidence(
        "fixture.solver",
        (NumericalCheck.CONVERGENCE, NumericalCheck.REFINEMENT),
        (
            NumericalCheckResult(
                NumericalCheck.CONVERGENCE, CheckOutcome.SATISFIED, "residual fell", 1e-12
            ),
            NumericalCheckResult(
                NumericalCheck.REFINEMENT,
                CheckOutcome.NOT_PERFORMED,
                "no grid refinement study was run for this configuration",
            ),
        ),
    )
    assert evidence.absent_checks == ("refinement",)
    assert not evidence.satisfies((NumericalCheck.REFINEMENT,))
    assert evidence.satisfies((NumericalCheck.CONVERGENCE,))
    assert NumericalEvidence.from_dict(evidence.to_dict()) == evidence


def test_a_declared_check_may_not_simply_be_omitted():
    with pytest.raises(CorpusError, match="omits declared checks"):
        NumericalEvidence("fixture.solver", (NumericalCheck.CONVERGENCE,), ())


# =====================================================================
# THE END-TO-END TRUST CAMPAIGN
# =====================================================================

def _graph_plan():
    facts = (
        IntentFact("thermal.heat_capacity", FactRole.PARAMETER, Quantity(100, "J/K")),
        IntentFact("thermal.ambient_conductance", FactRole.PARAMETER, Quantity(1, "W/K")),
        IntentFact("thermal.ambient_temperature", FactRole.BOUNDARY_CONDITION, Quantity(300, "K")),
        IntentFact("thermal.initial_temperature", FactRole.INITIAL_CONDITION, Quantity(300, "K")),
        IntentFact("material.reference_resistance", FactRole.PARAMETER, Quantity(10, "ohm")),
        IntentFact("material.temperature_coefficient", FactRole.PARAMETER, Quantity(0.0039, "1/K")),
        IntentFact("material.reference_temperature", FactRole.PARAMETER, Quantity(293.15, "K")),
        IntentFact("electrical.source_voltage", FactRole.BOUNDARY_CONDITION, Quantity(12, "V")),
    )
    intent = EngineeringIntent(
        "sprint2 trust", ContextOfUse("predict", "system", "error"),
        (EngineeringComponent("system", "electrothermal.feedback"),), (), facts,
        (IntentQuantityOfInterest("temperature", "final_temperature", "K", "system"),),
        simulation_horizon=SimulationHorizon(Quantity(0, "s"), Quantity(2, "s")),
    )
    return plan_engineering_intent(
        intent, production_planning_registries(),
        PlannerPolicy(capability_by_qoi={"temperature": "system.electrothermal_feedback"}),
    ).graph_plans[0]


def _authorized(run_id: str):
    store = InMemoryBulkStore()
    return execute_authorized_graph_plan(
        _graph_plan(), run_id=run_id,
        compositions=production_composition_packs(),
        executions=production_execution_packs(),
        resolver=BulkDataResolver(store), store=store,
    )


def test_end_to_end_trust_campaign_from_snapshot_to_certification():
    # --- the corpus half: source -> snapshot -> normalized dataset -> splits
    dataset = _dataset()
    assert dataset.snapshot.snapshot_sha256 == "1" * 64
    assert dataset.split_counts == {"calibration": 4, "validation": 4, "locked_holdout": 2}
    release = HoldoutRelease(
        "sprint2.e2e", "sprint2.e2e", "1", dataset.normalized_digest,
        "2026-02-01T00:00:00+00:00",
        "registered holdout evaluation for the Sprint 2 trust campaign",
    )

    # --- the run whose science this campaign is about
    authorized = _authorized("sprint2-e2e")
    target = _run_binding(authorized)

    # --- execution and Core-derived comparison over every split
    campaign = ValidationCampaign(
        "sprint2.e2e", "1", dataset,
        (DatasetSplit.CALIBRATION, DatasetSplit.VALIDATION, DatasetSplit.LOCKED_HOLDOUT),
        target=target,
        holdout_release=release,
        description="generic trust engine campaign over a declared fixture corpus",
    )
    ledger = _ledger()
    opened = campaign.open_holdout(ledger)
    report = run_campaign(opened, _predictions(dataset, opened.cases()))
    assert report.normalized_dataset_sha256 == dataset.normalized_digest
    # The opening happened on the authoritative path, and the report names the
    # OPENING rather than the permission that allowed it.
    assert ledger.was_opened(release)
    assert report.holdout_opening_digest == ledger.openings[0].digest
    assert report.counts["pass"] and report.counts["fail"]

    # --- coverage, clustering and the validated envelope
    region = _region()
    coverage = build_coverage(report, dataset, region, metric="response")
    clusters = cluster_failures(report, dataset, region)
    envelope = ValidationEnvelope("sprint2.e2e", coverage, report.digest, target=target)
    assert coverage.status_counts()["supported"] >= 1
    assert coverage.status_counts()["failed"] >= 1
    assert clusters and clusters[0].dimension == "temperature"
    assert envelope.has_any_support

    # --- what the disagreement supports saying
    diagnosis = diagnose_campaign(report, clusters)
    assert diagnosis.kind is InadequacyKind.MODEL_FORM_SUSPECTED

    assert report.target == target

    # --- the runtime half: completeness and the UQ matrix
    blueprint = authorized.graph_plan.blueprint_id
    snapshot = authorized.composition_snapshot

    validation_completeness = assess_protocol_completeness(
        snapshot, blueprint, "validation",
        tuple((i.protocol_id, i.protocol_version) for i in authorized.system_validation),
    )
    assert validation_completeness.enforceable
    assert validation_completeness.complete

    uq = assess_uq_coverage(
        snapshot, blueprint,
        {
            (i.result.quantity, i.result.channel.value): (i.result.uncertainty, i.result.method_id)
            for i in authorized.system_uncertainty
        },
    )
    # The production pack declares uncertainty producers that this run did not
    # exercise. That is a real gap, and the matrix names it instead of hiding it.
    assert uq.enforceable
    assert not uq.complete
    assert uq.missing
    assert all(cell.state is UQCellState.MISSING for cell in uq.missing)

    # --- actual computational replay, not a serialization roundtrip
    store = InMemoryBulkStore()
    replay = replay_authorized_graph_plan(
        authorized, replay_run_id="sprint2-e2e-replay",
        compositions=production_composition_packs(),
        executions=production_execution_packs(),
        resolver=BulkDataResolver(store), store=store,
        policy=DEFAULT_REPLAY_POLICY,
    )
    assert replay.status is ReplayStatus.REPLAYED_MATCH
    assert replay.compared > 0
    assert replay.verified

    # --- the certification decision
    numerical = NumericalEvidence(
        "electrothermal.coupling",
        (NumericalCheck.CONVERGENCE, NumericalCheck.REFINEMENT),
        (
            NumericalCheckResult(
                NumericalCheck.CONVERGENCE, CheckOutcome.SATISFIED,
                "every coupling window converged", 1e-10, 1e-8,
            ),
            NumericalCheckResult(
                NumericalCheck.REFINEMENT, CheckOutcome.NOT_PERFORMED,
                "no window-refinement study was run for this configuration",
            ),
        ),
        binding=target,
    )
    # The prediction point this run is actually making. Core cannot derive it,
    # so it is declared -- and the gate is about THIS point, not the envelope's
    # best cell anywhere.
    supported_point = ValidationQueryPoint(
        "response",
        {"temperature": Quantity(305.0, "K")},
        declared=Applicability.INSIDE,
        label="inside the validated region",
    )
    assessment = assess_authorized_multiphysics_run(
        authorized,
        policy=MULTIPHYSICS_PRODUCTION_POLICY,
        replay=replay,
        numerical=numerical,
        envelope=envelope,
        envelope_queries=(supported_point,),
    )
    assert assessment.satisfied
    # Every piece of evidence is bound to THIS computation, and the gates say so.
    assert assessment.gate(COMPUTATIONAL_REPLAY_VERIFIED).passed
    assert assessment.gate(SERIALIZATION_ROUNDTRIP_VERIFIED).passed
    assert assessment.gate(NUMERICAL_EVIDENCE_PRESENT).passed
    assert assessment.gate(VALIDATION_ENVELOPE_SUPPORTED).passed
    # The UQ gap is recorded as debt rather than quietly dropped.
    assert UQ_CHANNEL_COMPLETENESS in assessment.recorded_gaps

    record = certify_authorized_multiphysics_run(
        authorized, commit_sha="0" * 40,
        policy=MULTIPHYSICS_PRODUCTION_POLICY,
        replay=replay, numerical=numerical,
        envelope=envelope, envelope_queries=(supported_point,),
    )
    assert verify_certification_record(record).verified
    assert record.profile.profile_id == "forge.multiphysics.production/2"
    assert {item.name for item in record.artifacts} >= {"trust_policy", "trust_assessment"}


# =====================================================================
# CERTIFICATION FAILS CLOSED
# =====================================================================

def test_full_trust_refuses_the_run_that_the_production_policy_certifies():
    authorized = _authorized("full-trust")
    assessment = assess_authorized_multiphysics_run(
        authorized, policy=MULTIPHYSICS_FULL_TRUST_POLICY
    )
    assert not assessment.satisfied
    # Exactly the evidence that is genuinely absent, named.
    assert UQ_CHANNEL_COMPLETENESS in assessment.unmet_required
    assert COMPUTATIONAL_REPLAY_VERIFIED in assessment.unmet_required

    record = certify_authorized_multiphysics_run(
        authorized, commit_sha="0" * 40, policy=MULTIPHYSICS_FULL_TRUST_POLICY
    )
    assert not verify_certification_record(record).verified


def test_an_absent_replay_outcome_never_passes_the_replay_gate():
    authorized = _authorized("no-replay")
    assessment = assess_authorized_multiphysics_run(
        authorized, policy=MULTIPHYSICS_FULL_TRUST_POLICY
    )
    gate = assessment.gate(COMPUTATIONAL_REPLAY_VERIFIED)
    assert not gate.passed
    assert gate.evidence["supplied"] is False


def test_a_replay_outcome_from_another_run_does_not_satisfy_this_one():
    first = _authorized("replay-a")
    store = InMemoryBulkStore()
    replay = replay_authorized_graph_plan(
        first, replay_run_id="replay-a-again",
        compositions=production_composition_packs(),
        executions=production_execution_packs(),
        resolver=BulkDataResolver(store), store=store,
    )
    assert replay.verified

    second = _authorized("replay-b")
    assessment = assess_authorized_multiphysics_run(
        second, policy=MULTIPHYSICS_FULL_TRUST_POLICY, replay=replay
    )
    assert not assessment.gate(COMPUTATIONAL_REPLAY_VERIFIED).passed


def test_a_policy_may_not_both_require_and_merely_record_a_gate():
    with pytest.raises(InvalidScientificProblem, match="either blocks or it does not"):
        TrustPolicy(
            "bad", "1",
            required_gates=(VALIDATION_PROTOCOL_COMPLETENESS,),
            recorded_gates=(VALIDATION_PROTOCOL_COMPLETENESS,),
        )


def test_protocol_completeness_is_an_exact_set_in_both_directions():
    authorized = _authorized("completeness")
    snapshot = authorized.composition_snapshot
    blueprint = authorized.graph_plan.blueprint_id
    executed = tuple(
        (i.protocol_id, i.protocol_version) for i in authorized.system_verification
    )
    assert assess_protocol_completeness(snapshot, blueprint, "verification", executed).complete

    # A subset is not completeness.
    short = assess_protocol_completeness(snapshot, blueprint, "verification", executed[:1])
    assert not short.complete
    assert short.missing

    # A version drift is both a missing protocol and an unexpected one.
    drifted = tuple((artifact, "999") for artifact, _ in executed)
    moved = assess_protocol_completeness(snapshot, blueprint, "verification", drifted)
    assert moved.missing and moved.unexpected
    assert not moved.complete


def test_an_unquantified_uncertainty_is_unknown_and_is_not_coverage():
    from engcore.scientific.results.uncertainty import Uncertainty

    authorized = _authorized("uq-unknown")
    snapshot = authorized.composition_snapshot
    blueprint = authorized.graph_plan.blueprint_id
    required = sorted(snapshot.required_uncertainty_cells(blueprint))
    assert required

    produced = {
        cell: (Uncertainty.unknown("not determinable for this configuration"), "method")
        for cell in required
    }
    coverage = assess_uq_coverage(snapshot, blueprint, produced)
    assert coverage.counts()["unknown"] == len(required)
    assert coverage.counts()["quantified"] == 0
    assert not coverage.complete


# =====================================================================
# THE TWO SCIENTIFIC-SEMANTIC CORRECTIONS
# =====================================================================

def test_a_correct_refusal_buys_no_empirical_support_and_no_envelope():
    """Declining correctly is a guardrail result, never validated territory.

    Two campaigns over the same cells. In the first the model answers and is
    right; in the second it declines every case, correctly. The second must not
    look like the first to coverage, to the envelope or to the pass fraction --
    otherwise a model could widen its validated envelope by refusing more.
    """
    answered_cases = tuple(
        _case(t, DatasetSplit.VALIDATION, applicability=Applicability.INSIDE)
        for t in (315.0, 318.0)
    )
    refused_cases = tuple(
        _case(t, DatasetSplit.VALIDATION, applicability=Applicability.OUTSIDE)
        for t in (315.0, 318.0)
    )
    observations = (_observation(315.0), _observation(318.0))

    answered = _dataset(cases=answered_cases, observations=observations)
    answered_campaign = ValidationCampaign("answered", "1", answered, (DatasetSplit.VALIDATION,))
    answered_report = run_campaign(
        answered_campaign, _predictions(answered, answered_campaign.cases())
    )

    refused = _dataset(cases=refused_cases, observations=observations)
    refused_campaign = ValidationCampaign("refused", "1", refused, (DatasetSplit.VALIDATION,))
    refused_report = run_campaign(
        refused_campaign,
        {
            (case.case_id, "response"): PredictionRefusal(
                RefusalKind.APPLICABILITY, "outside the declared validity domain"
            )
            for case in refused_campaign.cases()
        },
    )

    # Answering correctly builds support. Refusing correctly does not.
    assert answered_report.counts["pass"] == 2
    assert refused_report.counts["pass"] == 0
    assert refused_report.counts["correct_refusal"] == 2
    assert answered_report.pass_fraction == 1.0
    assert refused_report.pass_fraction is None

    region = _region()
    answered_coverage = build_coverage(answered_report, answered, region, metric="response")
    refused_coverage = build_coverage(refused_report, refused, region, metric="response")

    # The shared cell is SUPPORTED where the model answered and UNTESTED where
    # it declined: a refusal does not convert an unvalidated cell.
    assert answered_coverage.status_counts()["supported"] == 1
    assert refused_coverage.status_counts()["supported"] == 0
    assert refused_coverage.status_counts()["untested"] == len(refused_coverage.cells)
    assert all(cell.passed == 0 for cell in refused_coverage.cells)

    # And the envelope over the refusing campaign covers nothing at all.
    refused_envelope = ValidationEnvelope("refused", refused_coverage, refused_report.digest)
    assert not refused_envelope.has_any_support
    assert (
        refused_envelope.classify({"temperature": Quantity(316.0, "K")}).verdict
        is EnvelopeVerdict.EXTRAPOLATING
    )

    # The guardrail result stays visible, on its own axis.
    assert refused_report.refusal_accuracy == 1.0
    assert refused_coverage.guardrail_counts() == {
        "correct_refusals": 2,
        "unexpected_refusals": 0,
    }
    assert refused_envelope.guardrail_counts["correct_refusals"] == 2


def test_poor_holdout_is_not_an_unconditional_model_form_conclusion():
    """An indicated alternative cause is returned instead of a form suspicion.

    The campaign evidence is identical throughout -- a good calibration fit and
    failing independent cases. What changes is what else the trust system was
    given to look at.
    """
    dataset = _dataset()
    campaign = ValidationCampaign(
        "c", "1", dataset, (DatasetSplit.CALIBRATION, DatasetSplit.VALIDATION)
    )
    report = run_campaign(campaign, _predictions(dataset, campaign.cases()))
    clusters = cluster_failures(report, dataset, _region())

    # 1. Nothing else supplied: a suspicion, with alternatives still open.
    bare = diagnose_campaign(report, clusters)
    assert bare.kind is InadequacyKind.MODEL_FORM_SUSPECTED
    assert bare.confidence == "suggestive"
    assert bare.outstanding_alternatives

    # 2. A parameter that was never identifiable explains the failure to
    #    transfer without implicating the model's form at all.
    weak = CalibratedParameterSet(
        "fixture-fit",
        "1",
        (CalibrationParameterSpec("gain", "V/K"),),
        (FittedParameter("gain", Quantity(0.5, "V/K")),),
        CalibrationObjective("rmse", "1"),
        dataset.dataset_id,
        dataset.normalized_digest,
    )
    assert weak.unidentified_parameters == ("gain",)
    unidentifiable = diagnose_campaign(report, clusters, parameters=weak)
    assert unidentifiable.kind is InadequacyKind.IDENTIFIABILITY

    # 3. A violated numerical check explains it too.
    broken = NumericalEvidence(
        "fixture.solver",
        (NumericalCheck.CONVERGENCE,),
        (
            NumericalCheckResult(
                NumericalCheck.CONVERGENCE,
                CheckOutcome.VIOLATED,
                "the residual did not fall",
                1e-2,
                1e-8,
            ),
        ),
    )
    assert diagnose_campaign(report, clusters, numerical=broken).kind is (
        InadequacyKind.NUMERICAL
    )

    # 4. A fit against a different dataset is a context mismatch, not a verdict
    #    on the model.
    identified_gain = FittedParameter(
        "gain", Quantity(0.5, "V/K"), Identifiability.IDENTIFIED, Quantity(0.001, "V/K")
    )
    elsewhere = CalibratedParameterSet(
        "fixture-fit",
        "1",
        (CalibrationParameterSpec("gain", "V/K"),),
        (identified_gain,),
        CalibrationObjective("rmse", "1"),
        "other.dataset",
        "9" * 64,
    )
    assert diagnose_campaign(report, clusters, parameters=elsewhere).kind is (
        InadequacyKind.CONTEXT_MISMATCH
    )

    # 5. Only once every checkable alternative is ruled out does the suspicion
    #    become supported -- and it remains a suspicion, still saying nothing
    #    about which physics is missing.
    sound = NumericalEvidence(
        "fixture.solver",
        (NumericalCheck.CONVERGENCE,),
        (
            NumericalCheckResult(
                NumericalCheck.CONVERGENCE,
                CheckOutcome.SATISFIED,
                "the residual fell below tolerance",
                1e-12,
                1e-8,
            ),
        ),
    )
    constrained = CalibratedParameterSet(
        "fixture-fit",
        "1",
        (CalibrationParameterSpec("gain", "V/K"),),
        (identified_gain,),
        CalibrationObjective("rmse", "1"),
        dataset.dataset_id,
        dataset.normalized_digest,
    )
    ruled_out = diagnose_campaign(
        report, clusters, numerical=sound, parameters=constrained
    )
    assert ruled_out.kind is InadequacyKind.MODEL_FORM_SUSPECTED
    assert ruled_out.confidence == "supported"
    assert ruled_out.outstanding_alternatives == ()
    assert set(ruled_out.ruled_out_alternatives) == {
        "applicability",
        "numerical",
        "measurement_uncertainty",
        "identifiability",
        "context_mismatch",
    }
    assert "which physics is missing" in ruled_out.why
    assert ModelFormDiagnosis.from_dict(ruled_out.to_dict()) == ruled_out


def test_a_supported_model_form_suspicion_cannot_leave_alternatives_open():
    """The record itself refuses the overconfident combination."""
    from engcore.scientific.corpus import AlternativeCause, CauseCheck, CauseState

    with pytest.raises(CorpusError, match="alternative causes remain unexamined"):
        ModelFormDiagnosis(
            InadequacyKind.MODEL_FORM_SUSPECTED,
            why="calibration fits and independent evidence does not",
            confidence="supported",
            cause_checks=(
                CauseCheck(
                    AlternativeCause.NUMERICAL,
                    CauseState.NOT_CHECKABLE,
                    "no numerical evidence was supplied",
                ),
            ),
        )


# =====================================================================
# TRUST BINDING: evidence cannot be borrowed from another computation
# =====================================================================

def _run_binding(authorized):
    from engcore.assembly.trust import authorized_run_binding

    return authorized_run_binding(authorized)


def _envelope_for(authorized, *, target=None):
    """A supported envelope over the fixture corpus, bound to some authority."""
    dataset = _dataset()
    campaign = ValidationCampaign(
        "bound", "1", dataset,
        (DatasetSplit.CALIBRATION, DatasetSplit.VALIDATION),
        target=target if target is not None else _full_binding(authorized),
    )
    report = run_campaign(campaign, _predictions(dataset, campaign.cases()))
    coverage = build_coverage(report, dataset, _region(), metric="response")
    return ValidationEnvelope("bound", coverage, report.digest, target=campaign.target)


def _numerical_for(authorized, *, binding=None):
    from engcore.scientific.corpus import NumericalEvidence

    return NumericalEvidence(
        "electrothermal.coupling",
        (NumericalCheck.CONVERGENCE,),
        (
            NumericalCheckResult(
                NumericalCheck.CONVERGENCE, CheckOutcome.SATISFIED,
                "every coupling window converged", 1e-10, 1e-8,
            ),
        ),
        binding=binding if binding is not None else _full_binding(authorized),
    )


def test_an_envelope_from_another_authority_cannot_certify_this_run():
    """Finding 2: supported cells are about some science, not about any run."""
    run_a = _authorized("authority-a")
    run_b = _authorized("authority-b")

    own = _envelope_for(run_a)
    foreign = _envelope_for(run_a, target=EvidenceBinding(
        "other-model",
        (
            AuthorityComponent(AuthorityRole.MODEL, "some.other.model", "1"),
            AuthorityComponent(AuthorityRole.REALIZATION, "some.other.realization", "1"),
        ),
    ))
    unbound = ValidationEnvelope(
        own.envelope_id, own.coverage, own.campaign_report_digest, target=None
    )

    # Its own envelope satisfies the gate, for a point inside its support.
    assert own.belongs_to(_run_binding(run_a)) == ()
    inside = ValidationQueryPoint(
        "response", {"temperature": Quantity(305.0, "K")},
        declared=Applicability.INSIDE,
    )
    assessment = assess_authorized_multiphysics_run(
        run_a, policy=MULTIPHYSICS_FULL_TRUST_POLICY,
        envelope=own, envelope_queries=(inside,),
    )
    assert assessment.gate(VALIDATION_ENVELOPE_SUPPORTED).passed

    # An envelope about another model does not, however supported its cells.
    assert foreign.has_any_support
    assert foreign.belongs_to(_run_binding(run_a))
    refused = assess_authorized_multiphysics_run(
        run_a, policy=MULTIPHYSICS_FULL_TRUST_POLICY,
        envelope=foreign, envelope_queries=(inside,),
    )
    assert not refused.gate(VALIDATION_ENVELOPE_SUPPORTED).passed
    assert refused.gate(VALIDATION_ENVELOPE_SUPPORTED).evidence["problems"]

    # Nor does an envelope that names no target at all. Fail closed.
    assert unbound.has_any_support
    assert not assess_authorized_multiphysics_run(
        run_a, policy=MULTIPHYSICS_FULL_TRUST_POLICY,
        envelope=unbound, envelope_queries=(inside,),
    ).gate(VALIDATION_ENVELOPE_SUPPORTED).passed

    # Run B differs from run A only by run id, so an envelope naming run A's
    # RUN component is refused for B -- the narrowest cross-run case there is.
    assert own.belongs_to(_run_binding(run_b))


def test_a_fabricated_or_foreign_replay_outcome_cannot_pass_the_replay_gate():
    """Finding 3: the gate reads sealed evidence, not a status field."""
    from engcore.assembly.replay import ReplayEvidence, ReplayOutcome, ReplayStatus

    run_a = _authorized("replay-bound-a")
    run_b = _authorized("replay-bound-b")
    store = InMemoryBulkStore()
    genuine = replay_authorized_graph_plan(
        run_a, replay_run_id="replay-bound-a-again",
        compositions=production_composition_packs(),
        executions=production_execution_packs(),
        resolver=BulkDataResolver(store), store=store,
    )
    assert genuine.verified and genuine.evidence is not None
    assert genuine.certifies(run_a, DEFAULT_REPLAY_POLICY) == ()

    # 1. A hand-built outcome that merely SAYS match, with the right run id and
    #    no evidence at all, is refused rather than believed.
    with pytest.raises(InvalidScientificProblem, match="must carry the evidence"):
        ReplayOutcome(
            status=ReplayStatus.REPLAYED_MATCH,
            policy_id=DEFAULT_REPLAY_POLICY.policy_id,
            policy_version=DEFAULT_REPLAY_POLICY.version,
            original_run_id=run_a.run.run_id,
            replay_run_id="fabricated",
            compared=7,
        )

    # 2. Genuine evidence, but produced for a different run. Its status is
    #    REPLAYED_MATCH and it is real -- and it cannot speak for run B.
    assert genuine.certifies(run_b, DEFAULT_REPLAY_POLICY)
    assert not assess_authorized_multiphysics_run(
        run_b, policy=MULTIPHYSICS_FULL_TRUST_POLICY, replay=genuine
    ).gate(COMPUTATIONAL_REPLAY_VERIFIED).passed

    # 3. Evidence re-sealed against another policy does not satisfy this one.
    other_policy = ReplayPolicy(
        "forge.multiphysics.replay", "2", ReplayTolerance(absolute=1.0)
    )
    assert genuine.certifies(run_a, other_policy)

    # 4. A match over zero comparisons is not a reproduction.
    hollow = ReplayEvidence(
        original_run_digest=run_a.digest,
        replayed_run_digest=run_b.digest,
        original_run_id=run_a.run.run_id,
        replay_run_id="hollow",
        graph_fingerprint=run_a.run.graph_fingerprint,
        plan_fingerprint=run_a.run.plan_fingerprint,
        scenario_digest=run_a.run.scenario_digest,
        composition_authority_digest=run_a.composition_snapshot.authority_digest,
        execution_authority_digest=run_a.execution_snapshot.authority_digest,
        policy_digest=DEFAULT_REPLAY_POLICY.digest,
        comparison_digest="0" * 64,
        compared=0,
    )
    assert "compared no quantities" in " ".join(
        hollow.mismatches(run_a, DEFAULT_REPLAY_POLICY)
    )

    # 5. A record whose replayed digest equals the original was not re-executed.
    with pytest.raises(InvalidScientificProblem, match="was not\\s+re-executed"):
        ReplayEvidence(
            original_run_digest=run_a.digest,
            replayed_run_digest=run_a.digest,
            original_run_id=run_a.run.run_id,
            replay_run_id="self",
            graph_fingerprint=run_a.run.graph_fingerprint,
            plan_fingerprint=run_a.run.plan_fingerprint,
            scenario_digest=run_a.run.scenario_digest,
            composition_authority_digest=run_a.composition_snapshot.authority_digest,
            execution_authority_digest=run_a.execution_snapshot.authority_digest,
            policy_digest=DEFAULT_REPLAY_POLICY.digest,
            comparison_digest="0" * 64,
            compared=3,
        )

    # 6. A tampered seal does not survive a roundtrip.
    payload = genuine.evidence.to_dict()
    payload["seal"] = "f" * 64
    with pytest.raises(InvalidScientificProblem, match="seal its own fields"):
        ReplayEvidence.from_dict(payload)


def test_a_holdout_release_for_one_evaluation_cannot_open_another():
    """Finding 4: evaluation_id was a label; now it binds."""
    dataset = _dataset()
    release = HoldoutRelease(
        "eval-A", "campaign-A", "1", dataset.normalized_digest,
        "2026-02-01T00:00:00+00:00", "registered for campaign A",
    )

    permitted = ValidationCampaign(
        "campaign-A", "1", dataset,
        (DatasetSplit.VALIDATION, DatasetSplit.LOCKED_HOLDOUT),
        holdout_release=release,
    )

    # Same dataset, same release, different evaluation. Refused.
    with pytest.raises(CorpusLeakageError, match="registered for campaign"):
        ValidationCampaign(
            "campaign-B", "1", dataset,
            (DatasetSplit.VALIDATION, DatasetSplit.LOCKED_HOLDOUT),
            holdout_release=release,
        )
    # A version bump is a different evaluation too.
    with pytest.raises(CorpusLeakageError, match="registered for campaign"):
        ValidationCampaign(
            "campaign-A", "2", dataset,
            (DatasetSplit.VALIDATION, DatasetSplit.LOCKED_HOLDOUT),
            holdout_release=release,
        )

    # Scoring the locked holdout goes through the opening authority, and the
    # report names the opening that actually happened.
    ledger = _ledger()
    opened = permitted.open_holdout(ledger)
    assert len(opened.cases()) == 6
    report = run_campaign(opened, _predictions(dataset, opened.cases()))
    assert ledger.openings[0].campaign_id == "campaign-A"
    assert report.holdout_opening_digest == ledger.openings[0].digest


def test_numerical_evidence_from_another_run_cannot_satisfy_this_one():
    """Finding 5: producer_id said which solver, not which execution."""
    run_a = _authorized("numerical-a")
    run_b = _authorized("numerical-b")

    own = _numerical_for(run_a)
    assert own.belongs_to(_run_binding(run_a)) == ()
    assert assess_authorized_multiphysics_run(
        run_a, policy=MULTIPHYSICS_FULL_TRUST_POLICY, numerical=own
    ).gate(NUMERICAL_EVIDENCE_PRESENT).passed

    # Real evidence, real producer, wrong execution.
    assert own.belongs_to(_run_binding(run_b))
    assert not assess_authorized_multiphysics_run(
        run_b, policy=MULTIPHYSICS_FULL_TRUST_POLICY, numerical=own
    ).gate(NUMERICAL_EVIDENCE_PRESENT).passed

    # Unbound evidence fails closed rather than being assumed local.
    unbound = _numerical_for(run_a, binding=None)
    unbound = type(unbound)(
        unbound.producer_id, unbound.supported_checks, unbound.results, None
    )
    assert unbound.belongs_to(_run_binding(run_a))
    assert not assess_authorized_multiphysics_run(
        run_a, policy=MULTIPHYSICS_FULL_TRUST_POLICY, numerical=unbound
    ).gate(NUMERICAL_EVIDENCE_PRESENT).passed


def test_undeclared_applicability_creates_no_support_and_no_envelope():
    """Finding 1: UNDECLARED is not INSIDE, and an unscreened case scores nothing."""
    cases = tuple(
        _case(t, DatasetSplit.VALIDATION, applicability=Applicability.UNDECLARED)
        for t in (315.0, 318.0)
    )
    dataset = _dataset(cases=cases, observations=(_observation(315.0), _observation(318.0)))
    campaign = ValidationCampaign("undeclared", "1", dataset, (DatasetSplit.VALIDATION,))
    report = run_campaign(campaign, _predictions(dataset, campaign.cases()))

    # These predictions would have PASSED had the cases been screened.
    assert {item.verdict for item in report.comparisons} == {
        CaseVerdict.APPLICABILITY_UNDECLARED
    }
    assert report.counts["pass"] == 0
    assert report.counts["fail"] == 0
    assert report.pass_fraction is None
    assert report.guardrail_counts["applicability_undeclared"] == 2

    # It cannot expand coverage or the envelope.
    coverage = build_coverage(report, dataset, _region(), metric="response")
    assert coverage.status_counts()["supported"] == 0
    assert all(cell.passed == 0 and cell.failed == 0 for cell in coverage.cells)
    assert sum(cell.undeclared for cell in coverage.cells) == 2
    envelope = ValidationEnvelope("undeclared", coverage, report.digest)
    assert not envelope.has_any_support

    # A disagreeing prediction is not a FAIL either: the model was never held
    # to a region nothing established it claims.
    wrong = run_campaign(
        campaign,
        {
            (case.case_id, "response"): PredictedValue(Quantity(999.0, "V"))
            for case in campaign.cases()
        },
    )
    assert wrong.counts["fail"] == 0
    assert wrong.counts["applicability_undeclared"] == 2

    # And a refusal here is neither correct nor unexpected.
    declined = run_campaign(
        campaign,
        {
            (case.case_id, "response"): PredictionRefusal(
                RefusalKind.UNSUPPORTED_REGIME, "no declared domain for this point"
            )
            for case in campaign.cases()
        },
    )
    assert declined.counts["unexpected_refusal"] == 0
    assert declined.counts["correct_refusal"] == 0
    assert declined.counts["applicability_undeclared"] == 2
    assert declined.refusal_accuracy is None
    # The state stays visible rather than being promoted to OUTSIDE.
    assert "never established" in declined.comparisons[0].detail


def test_measurement_uncertainty_is_not_inferred_from_acceptance_tolerance():
    """Finding 6: a Forge policy choice is not a statement about the source."""
    from engcore.scientific.corpus import AlternativeCause, CauseState

    def cause_of(diagnosis):
        return {item.cause: item for item in diagnosis.cause_checks}[
            AlternativeCause.MEASUREMENT_UNCERTAINTY
        ]

    # A corpus with NO source uncertainty. The residuals are marginal against
    # the acceptance tolerance, which the old rule would have read as
    # measurement spread -- purely because somebody set a tight tolerance.
    silent = _dataset(
        observations=tuple(
            ReferenceObservation(
                case_id=f"T{int(t)}",
                metric="response",
                expected=Quantity(_truth(t), "V"),
                source_uncertainty=None,
                acceptance_tolerance=_tolerance(0.5),
            )
            for t in (*CALIBRATION_TEMPERATURES, *VALIDATION_TEMPERATURES, *HOLDOUT_TEMPERATURES)
        )
    )
    campaign = ValidationCampaign(
        "c", "1", silent, (DatasetSplit.CALIBRATION, DatasetSplit.VALIDATION)
    )
    report = run_campaign(campaign, _predictions(silent, campaign.cases()))
    assert report.failures()
    assert all(item.source_uncertainty is None for item in report.failures())

    check = cause_of(diagnose_campaign(report))
    assert check.state is CauseState.NOT_CHECKABLE
    assert "acceptance tolerance is a policy choice" in check.why

    # With a generous stated source uncertainty the cause IS indicated -- and
    # the acceptance tolerance is unchanged, so only the source's own statement
    # moved the answer.
    stated = _dataset(
        observations=tuple(
            ReferenceObservation(
                case_id=f"T{int(t)}",
                metric="response",
                expected=Quantity(_truth(t), "V"),
                source_uncertainty=_tolerance(20.0, ToleranceBasis.SOURCE_REPORTED),
                acceptance_tolerance=_tolerance(0.5),
            )
            for t in (*CALIBRATION_TEMPERATURES, *VALIDATION_TEMPERATURES, *HOLDOUT_TEMPERATURES)
        )
    )
    generous = run_campaign(
        ValidationCampaign(
            "c", "1", stated, (DatasetSplit.CALIBRATION, DatasetSplit.VALIDATION)
        ),
        _predictions(stated, campaign.cases()),
    )
    indicated = diagnose_campaign(generous)
    assert cause_of(indicated).state is CauseState.INDICATED
    assert indicated.kind is InadequacyKind.MEASUREMENT_UNCERTAINTY


def test_a_declared_but_empty_requirement_set_is_enforceable():
    """Finding 7: emptiness is not a version probe."""
    from engcore.assembly.trust import assess_protocol_completeness, assess_uq_coverage
    from engcore.compositionpacks.snapshot import CompositionPackSnapshot

    authorized = _authorized("requirements")
    snapshot = authorized.composition_snapshot
    assert snapshot.declares_requirements

    # A V4 pack that requires nothing for a blueprint, and executed nothing,
    # is COMPLETE -- not unenforceable.
    empty = replace_snapshot(snapshot, protocol_requirements=(), uncertainty_requirements=())
    assert empty.declares_requirements
    completeness = assess_protocol_completeness(empty, "any.blueprint", "validation", ())
    assert completeness.enforceable
    assert completeness.complete
    assert assess_uq_coverage(empty, "any.blueprint", {}).complete

    # A pre-V4 payload declared nothing at all and stays unenforceable.
    payload = dict(snapshot.to_dict())
    payload["schema"] = "forge.composition_pack_snapshot/3"
    payload.pop("requirements_declared", None)
    legacy = CompositionPackSnapshot.from_dict(payload)
    assert not legacy.declares_requirements
    legacy_completeness = assess_protocol_completeness(
        legacy, authorized.graph_plan.blueprint_id, "validation", ()
    )
    assert not legacy_completeness.enforceable
    assert not legacy_completeness.complete


def replace_snapshot(snapshot, **changes):
    from dataclasses import replace

    return replace(snapshot, **changes)


# =====================================================================
# CERTIFICATION INTEGRITY: the five remaining borrowing paths
# =====================================================================

def test_failed_replay_evidence_cannot_be_rewrapped_as_a_match():
    """Finding 1: the outcome must be the comparison that produced its seal.

    The binding checks all passed before this: the evidence names the right
    run, the right authorities and the right policy. What was missing is that
    the *outcome wrapped around it* was the one that produced it -- so genuine
    evidence from a MISMATCHING replay could be lifted out and re-wrapped in a
    freshly built REPLAYED_MATCH with an empty difference list.
    """
    from engcore.assembly.replay import (
        ReplayDifference,
        ReplayOutcome,
        ReplayStatus,
        comparison_digest,
    )

    authorized = _authorized("rewrap")
    store = InMemoryBulkStore()
    genuine = replay_authorized_graph_plan(
        authorized, replay_run_id="rewrap-again",
        compositions=production_composition_packs(),
        executions=production_execution_packs(),
        resolver=BulkDataResolver(store), store=store,
    )
    assert genuine.verified

    # Build the evidence a MISMATCHING replay of this same run would produce.
    differences = (
        ReplayDifference(
            "final_outputs.thermal.temperature", "300", "412", "error exceeds tolerance"
        ),
    )
    mismatch_evidence = replace(
        genuine.evidence,
        comparison_digest=comparison_digest(genuine.compared, differences),
        difference_count=len(differences),
        seal="",
    )
    honest_mismatch = ReplayOutcome(
        status=ReplayStatus.REPLAYED_MISMATCH,
        policy_id=DEFAULT_REPLAY_POLICY.policy_id,
        policy_version=DEFAULT_REPLAY_POLICY.version,
        original_run_id=authorized.run.run_id,
        replay_run_id="rewrap-again",
        compared=genuine.compared,
        differences=differences,
        evidence=mismatch_evidence,
    )
    # Reported honestly, it fails the gate for the obvious reason.
    assert honest_mismatch.certifies(authorized, DEFAULT_REPLAY_POLICY)

    # Now the attack: same genuine evidence, wrapped in a MATCH with the
    # differences dropped. Every binding still matches.
    rewrapped = ReplayOutcome(
        status=ReplayStatus.REPLAYED_MATCH,
        policy_id=DEFAULT_REPLAY_POLICY.policy_id,
        policy_version=DEFAULT_REPLAY_POLICY.version,
        original_run_id=authorized.run.run_id,
        replay_run_id="rewrap-again",
        compared=genuine.compared,
        differences=(),
        evidence=mismatch_evidence,
    )
    assert mismatch_evidence.mismatches(authorized, DEFAULT_REPLAY_POLICY) == ()
    problems = rewrapped.certifies(authorized, DEFAULT_REPLAY_POLICY)
    assert problems
    assert any("different comparison" in item for item in problems)
    assert not assess_authorized_multiphysics_run(
        authorized, policy=MULTIPHYSICS_FULL_TRUST_POLICY, replay=rewrapped
    ).gate(COMPUTATIONAL_REPLAY_VERIFIED).passed

    # And the status/difference invariant is enforced at construction, in both
    # directions: a mismatch with nothing listed, and a match with something.
    with pytest.raises(InvalidScientificProblem, match="must enumerate what differed"):
        ReplayOutcome(
            status=ReplayStatus.REPLAYED_MISMATCH,
            policy_id=DEFAULT_REPLAY_POLICY.policy_id,
            policy_version=DEFAULT_REPLAY_POLICY.version,
            original_run_id=authorized.run.run_id,
            replay_run_id="empty-mismatch",
            compared=3,
            differences=(),
            evidence=genuine.evidence,
        )
    with pytest.raises(InvalidScientificProblem, match="cannot also carry differences"):
        ReplayOutcome(
            status=ReplayStatus.REPLAYED_MATCH,
            policy_id=DEFAULT_REPLAY_POLICY.policy_id,
            policy_version=DEFAULT_REPLAY_POLICY.version,
            original_run_id=authorized.run.run_id,
            replay_run_id="match-with-differences",
            compared=3,
            differences=differences,
            evidence=genuine.evidence,
        )


def test_a_locked_holdout_campaign_opens_once_through_the_execution_path():
    """Finding 2: the ledger is on the authoritative path, not beside it."""
    dataset = _dataset()
    release = HoldoutRelease(
        "eval-once", "once", "1", dataset.normalized_digest,
        "2026-02-01T00:00:00+00:00", "registered",
    )
    campaign = ValidationCampaign(
        "once", "1", dataset,
        (DatasetSplit.VALIDATION, DatasetSplit.LOCKED_HOLDOUT),
        holdout_release=release,
    )
    # THE LOCKED CASES ARE NOT VISIBLE YET. Predictions cannot even be built
    # for them without going through the opening authority first.
    with pytest.raises(CorpusLeakageError, match="not visible until it is opened"):
        campaign.cases()

    ledger = _ledger()
    opened = campaign.open_holdout(ledger)
    predictions = _predictions(dataset, opened.cases())
    report = run_campaign(opened, predictions)
    assert report.counts["pass"] or report.counts["fail"]
    assert report.holdout_opening_digest == ledger.openings[0].digest

    # The same release through the same authority is refused on the second run.
    with pytest.raises(CorpusLeakageError, match="already opened"):
        campaign.open_holdout(ledger)
    with pytest.raises(CorpusLeakageError, match="already opened"):
        run_campaign(campaign, predictions, holdout_ledger=ledger)

    # A campaign with no locked split needs no authority at all.
    open_campaign = ValidationCampaign(
        "open", "1", dataset, (DatasetSplit.VALIDATION,)
    )
    assert run_campaign(
        open_campaign, _predictions(dataset, open_campaign.cases())
    ).holdout_opening_digest == ""


def test_a_model_only_validation_binding_cannot_satisfy_the_validation_scope():
    """Finding 3: containment over a single role is not scope."""
    from engcore.scientific.corpus import VALIDATION_AUTHORITY_PROFILE

    authorized = _authorized("scope-validation")
    run_binding = _full_binding(authorized)
    model = run_binding.component(AuthorityRole.MODEL)
    assert model is not None

    # A binding naming ONLY the model. Every component it states matches the
    # run exactly -- and it says nothing about realization or authority.
    weak = EvidenceBinding("model-only", (model,))
    assert weak.mismatches(run_binding) == ()
    assert VALIDATION_AUTHORITY_PROFILE.unmet(weak, run_binding)

    envelope = _envelope_for(authorized, target=weak)
    inside = ValidationQueryPoint(
        "response", {"temperature": Quantity(305.0, "K")},
        declared=Applicability.INSIDE,
    )
    gate = assess_authorized_multiphysics_run(
        authorized, policy=MULTIPHYSICS_FULL_TRUST_POLICY,
        envelope=envelope, envelope_queries=(inside,),
    ).gate(VALIDATION_ENVELOPE_SUPPORTED)
    assert not gate.passed
    assert any("realization" in item for item in gate.evidence["problems"])


def test_a_solver_only_numerical_binding_cannot_satisfy_the_execution_scope():
    """Finding 3, the other half: a shared solver is not a shared execution."""
    from engcore.scientific.corpus import NUMERICAL_EXECUTION_PROFILE

    authorized = _authorized("scope-numerical")
    run_binding = _full_binding(authorized)
    solver = run_binding.component(AuthorityRole.SOLVER)
    assert solver is not None

    weak = EvidenceBinding("solver-only", (solver,))
    assert weak.mismatches(run_binding) == ()
    assert NUMERICAL_EXECUTION_PROFILE.unmet(weak, run_binding)

    gate = assess_authorized_multiphysics_run(
        authorized, policy=MULTIPHYSICS_FULL_TRUST_POLICY,
        numerical=_numerical_for(authorized, binding=weak),
    ).gate(NUMERICAL_EVIDENCE_PRESENT)
    assert not gate.passed
    assert any("run" in item for item in gate.evidence["problems"])

    # And the run component carries the authorized digest, so two runs of the
    # same graph are distinguishable by it.
    assert run_binding.component(AuthorityRole.RUN).digest == authorized.digest


def test_the_same_validated_model_outside_its_supported_cell_fails_the_gate():
    """Finding 4: validated somewhere is not validated here."""
    authorized = _authorized("region")
    envelope = _envelope_for(authorized)
    binding = _full_binding(authorized)

    # Region A: inside the validated cell.
    at_a = ValidationQueryPoint(
        "response", {"temperature": Quantity(305.0, "K")},
        declared=Applicability.INSIDE, label="region A",
    )
    # Region B: the SAME model and authority, at an operating point the
    # campaign found failing.
    at_b = ValidationQueryPoint(
        "response", {"temperature": Quantity(360.0, "K")},
        declared=Applicability.INSIDE, label="region B",
    )
    # Region C: beyond anything the campaign ever tested.
    at_c = ValidationQueryPoint(
        "response", {"temperature": Quantity(600.0, "K")},
        declared=Applicability.INSIDE, label="region C",
    )

    assert envelope.belongs_to(binding) == ()
    assert envelope.has_any_support

    def gate_for(*points):
        return assess_authorized_multiphysics_run(
            authorized, policy=MULTIPHYSICS_FULL_TRUST_POLICY,
            envelope=envelope, envelope_queries=points,
        ).gate(VALIDATION_ENVELOPE_SUPPORTED)

    assert gate_for(at_a).passed
    assert not gate_for(at_b).passed
    assert not gate_for(at_c).passed
    # One supported point does not carry a trajectory that leaves support.
    assert not gate_for(at_a, at_b).passed
    # And an undeclared prediction point is UNKNOWN, which full trust refuses.
    assert not gate_for().passed
    assert any(
        "no validation query point" in item
        for item in gate_for().evidence["problems"]
    )


def test_full_trust_numerical_gate_cannot_pass_on_an_undeclared_requirement():
    """Finding 5: an unstated requirement is not a satisfied one."""
    from engcore.assembly.trust import (
        NumericalRequirement,
        assess_numerical_completeness,
    )
    from engcore.scientific.corpus import NumericalEvidence

    authorized = _authorized("numerical-requirement")
    binding = _full_binding(authorized)

    # An empty roster with a correct binding. Under the old contract this
    # satisfied the gate because the caller passed no required checks.
    empty = NumericalEvidence("electrothermal.coupling", (), (), binding=binding)
    assert empty.belongs_to(binding) == ()

    silent = replace(MULTIPHYSICS_FULL_TRUST_POLICY, numerical_requirement=None)
    gate = assess_authorized_multiphysics_run(
        authorized, policy=silent, numerical=empty
    ).gate(NUMERICAL_EVIDENCE_PRESENT)
    assert not gate.passed
    assert gate.evidence["completeness"]["enforceable"] is False

    # The stated full-trust requirement is not met by an empty roster either.
    stated = assess_authorized_multiphysics_run(
        authorized, policy=MULTIPHYSICS_FULL_TRUST_POLICY, numerical=empty
    ).gate(NUMERICAL_EVIDENCE_PRESENT)
    assert not stated.passed
    assert stated.evidence["completeness"]["missing"] == ["convergence"]

    # Meeting it passes; a violated required check does not.
    assert assess_authorized_multiphysics_run(
        authorized, policy=MULTIPHYSICS_FULL_TRUST_POLICY,
        numerical=_numerical_for(authorized),
    ).gate(NUMERICAL_EVIDENCE_PRESENT).passed

    violated = NumericalEvidence(
        "electrothermal.coupling", (NumericalCheck.CONVERGENCE,),
        (
            NumericalCheckResult(
                NumericalCheck.CONVERGENCE, CheckOutcome.VIOLATED,
                "the residual did not fall", 1e-2, 1e-8,
            ),
        ),
        binding=binding,
    )
    assert not assess_authorized_multiphysics_run(
        authorized, policy=MULTIPHYSICS_FULL_TRUST_POLICY, numerical=violated
    ).gate(NUMERICAL_EVIDENCE_PRESENT).passed

    # A requirement stated as EXPLICITLY EMPTY is enforceable and satisfied --
    # the distinction an emptiness probe could not make.
    declared_none = assess_numerical_completeness(
        NumericalRequirement("none.required", ()), empty
    )
    assert declared_none.enforceable
    assert declared_none.complete


# =====================================================================
# FINAL SEMANTIC HOLES
# =====================================================================

def test_locked_cases_are_invisible_until_the_holdout_is_opened():
    """Hole 1: a release permitted an opening; it was treated as the opening.

    The previous regression built its predictions from ``campaign.cases()``
    before any ledger was involved -- which means it inspected the locked
    holdout and then decided whether to record having looked. That sequence no
    longer has an expression.
    """
    dataset = _dataset()
    release = HoldoutRelease(
        "eval-invisible", "invisible", "1", dataset.normalized_digest,
        "2026-02-01T00:00:00+00:00", "registered",
    )
    campaign = ValidationCampaign(
        "invisible", "1", dataset,
        (DatasetSplit.VALIDATION, DatasetSplit.LOCKED_HOLDOUT),
        holdout_release=release,
    )

    # 1. The campaign itself will not hand them over.
    with pytest.raises(CorpusLeakageError, match="not visible until it is opened"):
        campaign.cases()

    # 2. Nor will the dataset, against the release alone.
    with pytest.raises(CorpusLeakageError, match="recorded HoldoutOpening"):
        dataset.opened_holdout_cases(release)
    with pytest.raises(CorpusLeakageError, match="recorded HoldoutOpening"):
        dataset.opened_holdout_cases(None)

    # 3. Only an opening does, and only through an authority.
    ledger = _ledger()
    opened = campaign.open_holdout(ledger)
    locked = [
        case for case in opened.cases() if case.split is DatasetSplit.LOCKED_HOLDOUT
    ]
    assert {case.case_id for case in locked} == {"T420", "T450"}
    assert ledger.was_opened(release)

    # 4. And an opening from another release does not unlock this dataset's.
    other = _dataset(
        observations=tuple(
            _observation(t, tolerance=0.9 if t == 420.0 else 0.5)
            for t in (*CALIBRATION_TEMPERATURES, *VALIDATION_TEMPERATURES, *HOLDOUT_TEMPERATURES)
        )
    )
    foreign_release = HoldoutRelease(
        "eval-other", "other", "1", other.normalized_digest,
        "2026-02-01T00:00:00+00:00", "registered elsewhere",
    )
    foreign_opening = _ledger().open(foreign_release)
    with pytest.raises(CorpusLeakageError, match="names dataset digest"):
        dataset.opened_holdout_cases(foreign_opening)


def test_evidence_for_one_metric_cannot_support_a_query_about_another():
    """Hole 2: cells mixed metrics, so voltage evidence answered a temperature query."""
    # Two metrics over the SAME operating points, with opposite outcomes:
    # "response" agrees everywhere, "secondary" disagrees everywhere.
    cases = tuple(
        _case(t, DatasetSplit.VALIDATION) for t in (315.0, 318.0)
    )
    observations = (
        _observation(315.0),
        _observation(318.0),
        ReferenceObservation(
            case_id="T315", metric="secondary",
            expected=Quantity(1.0, "V"), acceptance_tolerance=_tolerance(0.01),
        ),
        ReferenceObservation(
            case_id="T318", metric="secondary",
            expected=Quantity(1.0, "V"), acceptance_tolerance=_tolerance(0.01),
        ),
    )
    dataset = _dataset(cases=cases, observations=observations)
    campaign = ValidationCampaign("metrics", "1", dataset, (DatasetSplit.VALIDATION,))
    predictions = dict(_predictions(dataset, campaign.cases()))
    predictions.update(
        {
            ("T315", "secondary"): PredictedValue(Quantity(99.0, "V")),
            ("T318", "secondary"): PredictedValue(Quantity(99.0, "V")),
        }
    )
    report = run_campaign(campaign, predictions)
    assert report.counts["pass"] == 2 and report.counts["fail"] == 2

    region = _region()
    by_metric = build_coverage_by_metric(report, dataset, region)
    assert set(by_metric) == {"response", "secondary"}

    # The same cell is SUPPORTED for one metric and FAILED for the other.
    good = by_metric["response"]
    bad = by_metric["secondary"]
    assert good.status_counts()["supported"] == 1
    assert good.status_counts()["failed"] == 0
    assert bad.status_counts()["supported"] == 0
    assert bad.status_counts()["failed"] == 1

    envelope = ValidationEnvelope("metrics", good, report.digest)
    assert envelope.metric == "response"

    inside = {"temperature": Quantity(316.0, "K")}
    own = envelope.classify_point(
        ValidationQueryPoint("response", inside, declared=Applicability.INSIDE)
    )
    assert own.verdict is EnvelopeVerdict.SUPPORTED

    # The query that must not be answered by this envelope.
    foreign = envelope.classify_point(
        ValidationQueryPoint("secondary", inside, declared=Applicability.INSIDE)
    )
    assert foreign.verdict is EnvelopeVerdict.UNKNOWN
    assert "is not evidence for another" in foreign.why

    # And through certification, the same query fails the gate.
    authorized = _authorized("metric-scope")
    bound = ValidationEnvelope(
        "metrics", good, report.digest, target=_full_binding(authorized)
    )
    gate = assess_authorized_multiphysics_run(
        authorized, policy=MULTIPHYSICS_FULL_TRUST_POLICY, envelope=bound,
        envelope_queries=(
            ValidationQueryPoint("secondary", inside, declared=Applicability.INSIDE),
        ),
    ).gate(VALIDATION_ENVELOPE_SUPPORTED)
    assert not gate.passed


def test_full_trust_requires_declared_applicability_inside():
    """Hole 3: the two axes were separate and only one was checked."""
    authorized = _authorized("applicability-axis")
    envelope = _envelope_for(authorized)
    inside_coordinates = {"temperature": Quantity(305.0, "K")}

    def gate_for(declared):
        return assess_authorized_multiphysics_run(
            authorized, policy=MULTIPHYSICS_FULL_TRUST_POLICY, envelope=envelope,
            envelope_queries=(
                ValidationQueryPoint("response", inside_coordinates, declared=declared),
            ),
        ).gate(VALIDATION_ENVELOPE_SUPPORTED)

    # All three are empirically SUPPORTED at this point. Only one is entitled.
    for declared in (Applicability.INSIDE, Applicability.OUTSIDE, Applicability.UNDECLARED):
        classification = envelope.classify(inside_coordinates, declared=declared)
        assert classification.verdict is EnvelopeVerdict.SUPPORTED

    assert gate_for(Applicability.INSIDE).passed

    outside = gate_for(Applicability.OUTSIDE)
    assert not outside.passed
    assert any("declared applicability" in item for item in outside.evidence["problems"])

    undeclared = gate_for(Applicability.UNDECLARED)
    assert not undeclared.passed
    assert any(
        "declared applicability" in item for item in undeclared.evidence["problems"]
    )

    # A policy may say otherwise, but it has to say so out loud.
    permissive = replace(
        MULTIPHYSICS_FULL_TRUST_POLICY,
        accepted_applicability=(
            Applicability.INSIDE.value,
            Applicability.UNDECLARED.value,
        ),
    )
    assert assess_authorized_multiphysics_run(
        authorized, policy=permissive, envelope=envelope,
        envelope_queries=(
            ValidationQueryPoint(
                "response", inside_coordinates, declared=Applicability.UNDECLARED
            ),
        ),
    ).gate(VALIDATION_ENVELOPE_SUPPORTED).passed


def test_an_inconclusive_numerical_check_does_not_cover_a_requirement():
    """Hole 4: 'performed and not violated' counted a study that settled nothing."""
    from engcore.scientific.corpus import NumericalEvidence

    authorized = _authorized("inconclusive")
    binding = _full_binding(authorized)

    inconclusive = NumericalEvidence(
        "electrothermal.coupling",
        (NumericalCheck.CONVERGENCE,),
        (
            NumericalCheckResult(
                NumericalCheck.CONVERGENCE, CheckOutcome.INCONCLUSIVE,
                "the residual history neither converged nor diverged in the "
                "window budget", 1e-5,
            ),
        ),
        binding=binding,
    )
    # It ran, and it is not violated -- the two conditions the old rule used.
    assert inconclusive.performed_checks == ("convergence",)
    assert inconclusive.violated_checks == ()
    # And it settled nothing, so it covers nothing.
    assert inconclusive.satisfied_checks == ()
    assert inconclusive.inconclusive_checks == ("convergence",)
    assert not inconclusive.satisfies((NumericalCheck.CONVERGENCE,))

    gate = assess_authorized_multiphysics_run(
        authorized, policy=MULTIPHYSICS_FULL_TRUST_POLICY, numerical=inconclusive
    ).gate(NUMERICAL_EVIDENCE_PRESENT)
    assert not gate.passed
    completeness = gate.evidence["completeness"]
    # The four states stay visible and separate.
    assert completeness["unresolved"] == ["convergence"]
    assert completeness["missing"] == []
    assert completeness["failed"] == []
    assert completeness["satisfied"] == []
    assert completeness["complete"] is False
