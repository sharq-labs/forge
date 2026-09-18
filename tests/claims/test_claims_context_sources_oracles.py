"""CORE-9, CORE-11, CORE-12: context binding, evidence sources, trusted-oracle discovery."""

from __future__ import annotations

from dataclasses import replace

import pytest

from claims_support import t3_claim, t3_point
from engcore.claims import (
    SOURCE_ADAPTERS,
    CapabilityRegistry,
    ContextBindingError,
    DecisionBinding,
    OracleApplicability,
    RouteKind,
    SourceStatus,
    assemble_evidence,
    assess_claim,
    compile_claim,
    context_problems,
    discover_oracles,
    execute_plan,
    gather_evidence,
    plan_experiment,
    require_context,
)
from engcore.mcp.capabilities import NAFEMS_T3_CAPABILITY_ID, production_registry
from engcore.mcp.sria_bridge import CredibilityReportCritic
from engcore.scientific.units.quantity import Quantity
from engcore.sria import SourceClass
from engcore.sria.assurance import Arbiter, CriticClass, obligations_from_charter, trusting_authority
from engcore.sria.evidence import IMPLEMENTED_SOURCE_CLASSES
from engcore.sria.uncertainty import DiscrepancyKind, ModelDiscrepancy


@pytest.fixture(scope="module")
def registry():
    return production_registry()


def _planned(made, registry):
    compiled = compile_claim(made, registry)
    plan = plan_experiment(compiled, registry)
    execution = execute_plan(plan, registry, dict(made.supplied_inputs))
    evidence = assemble_evidence(plan, made, execution.report).evidence
    return plan, execution.report, evidence


# ---------------------------------------------------------------------------
# CORE-9: context of use
# ---------------------------------------------------------------------------


def test_evidence_belongs_to_the_plan_it_was_produced_for(registry) -> None:
    plan, report, evidence = _planned(t3_claim(), registry)
    assert context_problems(evidence, plan, report) == ()
    require_context(evidence, plan, report)


def test_the_same_number_made_for_another_decision_does_not_count_here(registry) -> None:
    plan_a, report_a, evidence_a = _planned(t3_claim(), registry)
    plan_b, report_b, _ = _planned(t3_claim(decision=DecisionBinding("d-2", "Release the solver for production use.")), registry)
    assert report_a.values == report_b.values  # identical numbers
    problems = context_problems(evidence_a, plan_b, report_b)
    assert any("context" in p for p in problems)
    with pytest.raises(ContextBindingError):
        require_context(evidence_a, plan_b, report_b)


def test_the_arbiter_alone_would_accept_foreign_context_which_is_why_the_claim_layer_checks(registry) -> None:
    """Audit finding N2 is closed on this path, not in the certified Arbiter: pin both halves."""
    plan_a, report_a, evidence_a = _planned(t3_claim(), registry)
    plan_b, _, _ = _planned(t3_claim(decision=DecisionBinding("d-2", "Another use.")), registry)
    obligations = obligations_from_charter(plan_b.charter, required_critics=(CriticClass.PROCESS,))
    critic = CredibilityReportCritic()
    arbiter = Arbiter(trusting_authority("n2", critics=(critic,), policies=(obligations,)), critics=(critic,))
    assessment = arbiter.run_critic(critic.critic_id, report_a, subject=evidence_a, assessment_id="n2",
                                    mandatory_checks=("validation_level:benchmark_validated",))
    decision = arbiter.decide(decision_id="n2", evidence=evidence_a, assessments=(assessment,), obligations=obligations)
    assert decision.verdict.value == "valid"  # SRIA does not compare context_ref with the charter
    assert context_problems(evidence_a, plan_b)  # the claim layer does


@pytest.mark.parametrize(
    "edit, fragment",
    [
        (lambda e: replace(e, claim_binding=replace(e.claim_binding, subject_ref="other_qoi"), content_hash=""), "QOI"),
        (lambda e: replace(e, provenance_ref="another-run"), "run"),
        (lambda e: replace(e, domain_pack_ref="capability:system.other@1", content_hash=""), "capability"),
        (lambda e: replace(e, claim_payload={**dict(e.claim_payload), "value": 300.0}, content_hash=""), "value"),
        (
            lambda e: replace(e, uncertainty=replace(e.uncertainty, discrepancy=ModelDiscrepancy(DiscrepancyKind.ZERO_DECLARED, rationale="x")), content_hash=""),
            "discrepancy",
        ),
    ],
    ids=["qoi", "run", "capability", "value", "discrepancy"],
)
def test_evidence_that_differs_from_the_plan_in_any_bound_fact_is_refused(registry, edit, fragment) -> None:
    plan, report, evidence = _planned(t3_claim(), registry)
    problems = context_problems(edit(evidence), plan, report)
    assert problems and any(fragment in p for p in problems)


# ---------------------------------------------------------------------------
# CORE-11: evidence sources
# ---------------------------------------------------------------------------


def test_there_is_one_adapter_per_sria_source_class_and_sria_decides_which_are_implemented() -> None:
    assert set(SOURCE_ADAPTERS) == set(SourceClass)
    for source, adapter in SOURCE_ADAPTERS.items():
        assert adapter.implemented == (source in IMPLEMENTED_SOURCE_CLASSES)
    assert SOURCE_ADAPTERS[SourceClass.SIMULATION].implemented


def test_unimplemented_sources_answer_explicitly_and_never_produce_evidence() -> None:
    outcomes = {o.source_class: o for o in gather_evidence({"simulation_evidence": None, "simulation_problem": "no run"})}
    assert outcomes[SourceClass.SIMULATION].status is SourceStatus.NO_EVIDENCE
    for source in (SourceClass.BENCHMARK, SourceClass.MEASUREMENT, SourceClass.LITERATURE):
        assert outcomes[source].status is SourceStatus.NOT_IMPLEMENTED
        assert outcomes[source].evidence is None and "not implemented" in outcomes[source].reason


def test_an_assessment_records_every_source_it_asked(registry) -> None:
    record = assess_claim(t3_claim(), registry).to_dict()
    statuses = {o["source_class"]: o["status"] for o in record["evidence_sources"]}
    assert statuses == {"simulation": "produced", "benchmark": "not_implemented", "measurement": "not_implemented", "literature": "not_implemented"}
    produced = next(o for o in record["evidence_sources"] if o["source_class"] == "simulation")
    assert produced["evidence_record_hash"] == record["evidence"]["record_hash"]


# ---------------------------------------------------------------------------
# CORE-12: trusted-oracle discovery
# ---------------------------------------------------------------------------


def test_the_trusted_t3_oracle_is_discovered_for_its_qoi_at_its_exact_conditions(registry) -> None:
    (match,) = discover_oracles(registry, qoi="temperature_at_probe", context=t3_point())
    assert match.trusted and match.applicability is OracleApplicability.EXACT
    assert match.establishes == "benchmark_validated" and match.kind == "benchmark_dataset"
    assert match.trusted_digest == "eb6e2daf9a6ad6a957576fc9d3462175edf0525ebeea68bcd74778868d875328"
    assert set(match.conditions) == set(t3_point())


def test_applicability_is_unknown_when_conditions_are_unstated_and_mismatch_when_they_differ(registry) -> None:
    (unstated,) = discover_oracles(registry, qoi="temperature_at_probe", context={})
    assert unstated.applicability is OracleApplicability.UNKNOWN and "conductivity" in unstated.unstated
    point = t3_point()
    point["conductivity"] = Quantity(36.0, "watt / meter / kelvin")
    (mismatch,) = discover_oracles(registry, qoi="temperature_at_probe", context=point)
    assert mismatch.applicability is OracleApplicability.MISMATCH and mismatch.mismatched == ("conductivity",)


def test_discovery_filters_by_quantity_and_kind(registry) -> None:
    assert discover_oracles(registry, qoi="final_temperature") == ()
    assert discover_oracles(registry, qoi="temperature_at_probe", kinds=("experimental_dataset",)) == ()
    assert len(discover_oracles(registry)) == 1


def test_an_oracle_whose_content_is_not_the_pinned_content_is_reported_untrusted(registry) -> None:
    from engcore.domains.thermal_models.nafems_t3_oracle import nafems_t3_evidence
    from engcore.scientific.oracles import OracleEvidenceSet

    genuine = nafems_t3_evidence()
    forged = OracleEvidenceSet.create(
        oracle_id=genuine.identity.oracle_id,
        version=genuine.identity.version,
        kind=genuine.identity.kind,
        reference=genuine.identity.reference,
        observations=(replace(genuine.observations[0], expected=Quantity(40.0, "degree_Celsius")),),
    )
    t3 = registry.get(NAFEMS_T3_CAPABILITY_ID)
    routes = tuple(
        replace(r, oracle_provider=lambda: forged) if r.kind is RouteKind.BENCHMARK else r for r in t3.routes
    )
    described = CapabilityRegistry((replace(t3, routes=routes, executor=None),))
    (match,) = discover_oracles(described, qoi="temperature_at_probe", context=t3_point())
    assert match.trusted is False


def test_an_assessment_lists_the_external_evidence_that_exists_for_its_claim(registry) -> None:
    record = assess_claim(t3_claim(), registry).to_dict()
    (oracle,) = record["external_evidence"]
    assert oracle["applicability"] == "exact" and oracle["trusted"] is True
    assert "external_evidence.exact" in {i["code"] for i in record["explanation"]}
