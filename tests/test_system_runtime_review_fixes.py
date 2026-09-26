"""BIG 12 review fixes: one regression per finding of the read-only scientific review (H1-H6, M1-M7, LOW)."""

from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from engcore.credibility.evidence import CredibilityVerdict
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.multiphysics.state import InitialStateValue
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind
from engcore.scientific.units.quantity import Quantity
from engcore.system_runtime import (
    ApplicabilityReport, AuthorityRef, Availability, CallbackAuthority, ExecutionCache, ExecutionProfile, ModelSelection, MultiphysicsAuthority,
    MultiscaleAuthority, NodeInput, NodeKind, NodeOutcome, NodeOutputSpec, NodeSpec, NodeStatus, OutputValue, OwnerState, PreflightStatus,
    ProviderRecordRef, RequestedObservable, ResumeRefused, RunStatus, SystemCheckpoint, SystemExecutor, SystemRunResult, SystemState, TermSource,
    compare_runs, compile_plan, preflight, trace_result, trust_handoff, verify_checkpoint,
)
from engcore.system_runtime._common import digest_of
from tests.system_runtime_fixtures import UNKNOWN, Knobs, build, material_property, sha
from tests.test_system_runtime_checkpoint import Counting, Incomplete, _with_authority
from tests.test_system_runtime_executor import FakeProviders, _prov


def _run(**kw):
    request, context, knobs = build(**kw)
    return request, context, knobs, SystemExecutor(context).run(request)


# ------------------------------------------------------------------------------------------------------------- H1 model selection
def test_h1_every_executable_component_needs_an_explicit_model_selection_and_only_real_instances_can_be_selected():
    from engcore.scientific.multiphysics import PortDefinition, PortDirection, PortKind
    from engcore.scientific.twins import ScientificTwin, TwinKind
    from engcore.systems import ComponentConnection, ComponentDefinition, ComponentInstance, SystemDefinition
    request, context, _ = build()
    ports = (PortDefinition("p", PortDirection.OUTPUT, PortKind.SCALAR, "temperature", "K"),)
    q = PortDefinition("q", PortDirection.INPUT, PortKind.SCALAR, "temperature", "K")
    t = lambda n: ScientificTwin(n, "1", TwinKind.CONCEPT).reference  # noqa: E731
    system = SystemDefinition("s", "1", (ComponentDefinition("a", "1", ports), ComponentDefinition("b", "1", (q,))),
                              (ComponentInstance("cell", "a", "1", t("ta"), participant_id="pa"), ComponentInstance("b1", "b", "1", t("tb"), participant_id="pb")),
                              (ComponentConnection("c", "e", "cell", "p", "b1", "q"),))
    context.system = system
    request = replace(request, system=replace(request.system, digest=system.digest))
    assert {"MODEL_SELECTION_MISSING"} <= set(preflight(request, compile_plan(request), context).codes())
    both = replace(request, model_selections=(ModelSelection("cell", "m", "1"), ModelSelection("b1", "n", "1")))
    assert "MODEL_SELECTION_MISSING" not in preflight(both, compile_plan(both), context).codes()
    ghost = replace(both, model_selections=both.model_selections + (ModelSelection("ghost", "m", "1"),))
    assert "UNKNOWN_MODEL_SELECTION_TARGET" in preflight(ghost, compile_plan(ghost), context).codes()


def test_h1_the_trust_handoff_refuses_a_request_that_is_not_the_one_the_result_came_from():
    request, context, knobs, result = _run()
    other = build(conductivity=99.0)[0]
    with pytest.raises(InvalidScientificProblem, match="not the one this result was produced for"):
        trust_handoff(result, other)


# ------------------------------------------------------------------------------------------------------------- H2 state uncertainty
class _Stub:
    def fingerprint(self):
        return sha("stub")


def _coupled_stub(end_uncertainty):
    """A stand-in BIG 9 runtime that returns a converged run whose participant reports its own end-state uncertainty."""
    value = SimpleNamespace(variable_id="temperature", value=Quantity(305.0, "K"), uncertainty=end_uncertainty)
    run = SimpleNamespace(
        run_id="stub", final_outputs={"body.temperature": Quantity(305.0, "K").to_dict()}, windows=[SimpleNamespace(outcome=SimpleNamespace(value="converged"), iterations=[1])],
        state_transitions=[SimpleNamespace(participant_id="body", end_values=(value,))], ended_at=Quantity(1800, "s"), to_dict=lambda: {"stub": True})
    runtime = SimpleNamespace(graph=_Stub(), plan=_Stub(), run=lambda run_id, **kw: run)
    return runtime


def _state_commit_request(end_uncertainty, prior_uncertainty):
    request, context, knobs = build()
    auth = MultiphysicsAuthority("stub-coupled", _coupled_stub(end_uncertainty), run_kwargs=lambda c: {}, outputs={"temperature": "body.temperature"},
                                 state_owners={"body": "cell"},
                                 applicability=lambda run, call: (ApplicabilityReport("ok", "within", sha("e")),))
    context.authorities.register(auth)
    prior = OwnerState("cell", "component", (InitialStateValue("temperature", Quantity(300.0, "K"), prior_uncertainty),))
    node = NodeSpec("stub", NodeKind.MULTIPHYSICS_EXECUTION, auth.ref, (NodeOutputSpec("temperature", "K"),), commits_state=True, writes_owners=("cell",),
                    applicability_checks=("ok",))
    request = replace(request, nodes=(node,), observables=(RequestedObservable("t", "stub", "temperature", "K"),), constraint_observations=(),
                      initial_state=replace(request.initial_state, owners=(prior,)), profile=ExecutionProfile(("multiphysics",)))
    return request, context


def test_h2_the_committed_state_carries_the_participants_uncertainty_never_the_previous_valuess():
    known = Uncertainty(kind=UncertaintyKind.STANDARD, standard_uncertainty=Quantity(0.01, "K"), source="declared:initial", method="declared")
    request, context = _state_commit_request(Uncertainty.unknown("participant states none"), known)
    result = SystemExecutor(context).run(request)
    assert result.status is RunStatus.SUCCEEDED, [(r.node_id, r.reason) for r in result.node_receipts]
    committed = result.final_state.owner("cell").values[0]
    assert committed.value.magnitude == pytest.approx(305.0)
    assert committed.uncertainty.kind is UncertaintyKind.UNKNOWN            # the stale +-0.01 K did not survive a solve that states none


# ------------------------------------------------------------------------------------------------------------- H3 content by digest
def test_h3_supplied_content_must_have_the_digest_it_is_filed_under():
    request, context, _ = build()
    _, other = material_property(999.0)
    (key,) = context.resolved_properties
    context.resolved_properties = {key: other}                            # different content under the pinned digest key
    report = preflight(request, compile_plan(request), context)
    assert report.status is PreflightStatus.REFUSED and "CONTENT_DIGEST_MISMATCH" in report.codes()
    request, context, _ = build()
    (ckey,) = context.constraints
    from tests.system_runtime_fixtures import constraint
    context.constraints = {ckey: constraint(limit=1000.0)}                # a looser limit filed under the pinned key
    assert "CONTENT_DIGEST_MISMATCH" in preflight(request, compile_plan(request), context).codes()
    request, context, _ = build()
    state, _ = material_property()
    context.material_states = {sha("liar"): state}
    assert "CONTENT_DIGEST_MISMATCH" in preflight(request, compile_plan(request), context).codes()


def test_h3_a_material_property_must_belong_to_the_material_state_bound_to_its_owner():
    request, context, _ = build()
    node = next(n for n in request.nodes if n.node_id == "thermal")
    stranger = replace(node.material_refs[0], owner_id="cooler")            # the request binds no material state to 'cooler'
    request = replace(request, nodes=tuple(replace(node, material_refs=(stranger,)) if n.node_id == "thermal" else n for n in request.nodes))
    assert "MATERIAL_MISMATCH" in preflight(request, compile_plan(request), context).codes()


def test_h3_constraint_assessment_refuses_a_system_or_definition_that_is_not_the_runs():
    from engcore.system_runtime import assess_constraints
    request, context, knobs, result = _run()
    other_system = build(limit=300.0)[1].system
    with pytest.raises(InvalidScientificProblem, match="not the system this result was produced for"):
        assess_constraints(result, other_system, context.constraints)
    from tests.system_runtime_fixtures import constraint
    (key,) = context.constraints
    with pytest.raises(InvalidScientificProblem, match="does not have that digest"):
        assess_constraints(result, context.system, {key: constraint(limit=1000.0)})


# ------------------------------------------------------------------------------------------------------------- H4 consistent forgeries
def _paused():
    request, context, knobs = build(checkpoint_after=("thermal",))
    return request, context, SystemExecutor(context).run(request, stop_after="thermal")


def test_h4_a_self_consistent_checkpoint_from_another_initial_state_is_still_refused():
    request, context, part1 = _paused()
    cp = part1.checkpoints[-1]
    forged_spec = replace(request.initial_state, owners=(OwnerState("cell", "component", (InitialStateValue("temperature", Quantity(400.0, "K"), UNKNOWN),)),))
    s0 = SystemState.initial(forged_spec, request_digest=request.digest, system_digest=request.system.digest, environment_digest=request.environment.digest)
    s1 = s0.advance(time=Quantity(1800, "s"), updates=(OwnerState("cell", "component", (InitialStateValue("temperature", Quantity(295.0, "K"), UNKNOWN),)),),
                    produced_by="thermal")
    forged = replace(cp, state_history=(s0, s1), state=s1)                      # internally consistent: a valid digest chain
    with pytest.raises(ResumeRefused, match="does not start from this request's initial state|not the state after the last committed node"):
        verify_checkpoint(forged, request, compile_plan(request), (), context)


def test_h4_a_swapped_authority_payload_and_a_dishonest_completeness_flag_are_refused():
    request, context = _with_authority(Counting())
    part1 = SystemExecutor(context).run(request, stop_after="thermal")
    cp = part1.checkpoints[-1]
    acp = next(a for a in cp.authority_checkpoints if a.node_id == "heat")
    swapped = replace(cp, authority_checkpoints=(replace(acp, payload={"n": 99}),))
    with pytest.raises(ResumeRefused, match="not the one its receipt recorded"):
        verify_checkpoint(swapped, request, compile_plan(request), tuple(sorted(cp.context_digests)), context)
    lying = replace(cp, authority_checkpoints=(replace(acp, declared_complete=False),), complete=True, incomplete_reason="")
    with pytest.raises(ResumeRefused, match="completeness"):
        verify_checkpoint(lying, request, compile_plan(request), tuple(sorted(cp.context_digests)), context)


def test_h4_the_state_of_a_checkpoint_must_be_the_state_after_its_last_committed_node():
    request, context, part1 = _paused()
    cp = part1.checkpoints[-1]
    early = replace(cp, state=cp.state_history[0], state_history=(cp.state_history[0],))
    with pytest.raises(ResumeRefused, match="not the state after the last committed node"):
        verify_checkpoint(early, request, compile_plan(request), tuple(sorted(cp.context_digests)), context)


# ------------------------------------------------------------------------------------------------------------- H5 pending authority state
class _MacroCheckpoint:
    def serialize(self):
        return {"checkpoint": {"stub": True}, "digest": sha("stub-checkpoint")}


def _stub_multiscale(status="completed", reached=1800, resume_ok=True):
    calls = {"run": 0, "resume": 0}
    record = lambda: SimpleNamespace(  # noqa: E731
        run_id="ms", status=status, reason="stub", reached=SimpleNamespace(seconds=reached, quantity=Quantity(reached, "s")),
        final_slow_state={}, steps=(), last_valid_checkpoint=_MacroCheckpoint(), accounting={"represented_seconds": "0/1"}, digest=sha("ms-record"))
    def run(**kw):
        calls["run"] += 1
        return record()
    runtime = SimpleNamespace(identities=lambda: {"id": "stub"}, run=run, resume=lambda cp, until=None: record(), set_declared_fast_state=lambda s: None)
    return runtime, calls


def test_h5_a_checkpoint_from_a_refused_stage_is_never_promoted_and_a_fresh_run_never_inherits_one():
    runtime, calls = _stub_multiscale()
    outside = lambda record, call: (ApplicabilityReport("bounds", "outside", sha("e"), "left"),)   # noqa: E731
    auth = MultiscaleAuthority("stub-ms", runtime, initial_slow_state={}, extractors={"power": lambda r: Quantity(1.0, "W")}, applicability=outside)
    request, context, knobs = build()
    context.authorities.register(auth)
    heat = replace(next(n for n in request.nodes if n.node_id == "heat"), authority=auth.ref, applicability_checks=("bounds",), literals=())
    request = replace(request, nodes=tuple(heat if n.node_id == "heat" else n for n in request.nodes), profile=ExecutionProfile(("multiscale",)))
    request = replace(request, nodes=tuple(replace(n, authority=n.authority) for n in request.nodes))
    result = SystemExecutor(context).run(replace(request, profile=ExecutionProfile(("multiscale",))))
    assert result.receipt("heat").status is NodeStatus.REFUSED                         # applicability refused AFTER the authority executed
    assert auth._last_checkpoint is None and auth._pending_checkpoint is not None      # pending, not promoted
    within = lambda record, call: (ApplicabilityReport("bounds", "within", sha("e")),)  # noqa: E731
    ok = MultiscaleAuthority("stub-ms2", runtime, initial_slow_state={}, extractors={"power": lambda r: Quantity(1.0, "W")}, applicability=within)
    request2, context2, _ = build()
    context2.authorities.register(ok)
    heat2 = replace(next(n for n in request2.nodes if n.node_id == "heat"), authority=ok.ref, applicability_checks=("bounds",), literals=())
    request2 = replace(request2, nodes=tuple(heat2 if n.node_id == "heat" else n for n in request2.nodes), profile=ExecutionProfile(("multiscale",)))
    SystemExecutor(context2).run(request2)
    assert ok._last_checkpoint == {"checkpoint": {"stub": True}, "digest": sha("stub-checkpoint")}     # a committed stage IS promoted


# ------------------------------------------------------------------------------------------------------------- H6 uncertainty propagation
def test_h6_a_quantified_output_uncertainty_from_unknown_inputs_is_refused_unless_the_authority_declares_it_accounts_for_them():
    quantified = Uncertainty(kind=UncertaintyKind.STANDARD, standard_uncertainty=Quantity(0.1, "W"), source="declared", method="declared")
    def make(accounts):
        fn = lambda call: NodeOutcome("succeeded", {"power": OutputValue(Quantity(37.0, "W"), quantified, "claimed")})  # noqa: E731
        auth = CallbackAuthority(f"claims-{accounts}", fn, config={"a": accounts}, deterministic=True)
        auth.accounts_for_input_uncertainty = accounts
        return auth
    for accounts, expected in ((False, NodeStatus.FAILED), (True, NodeStatus.SUCCEEDED)):
        request, context, knobs = build()
        auth = make(accounts)
        context.authorities.register(auth)
        heat = replace(next(n for n in request.nodes if n.node_id == "heat"), authority=auth.ref)
        request = replace(request, nodes=tuple(heat if n.node_id == "heat" else n for n in request.nodes))
        result = SystemExecutor(context).run(request)
        assert result.receipt("heat").status is expected, result.receipt("heat").reason
        if not accounts:
            assert "UNKNOWN in, UNKNOWN out" in result.receipt("heat").reason


# ------------------------------------------------------------------------------------------------------------- M1 applicability
def test_m1_a_state_committing_node_must_declare_applicability_checks_or_state_why_none_apply():
    request, context, _ = build()
    node = next(n for n in request.nodes if n.node_id == "thermal")
    with pytest.raises(InvalidScientificProblem, match="missing applicability is never read as 'applicable'"):
        replace(node, applicability_checks=())
    waived = replace(node, applicability_checks=(), applicability_waiver="linear response over the declared load range; no runtime bound applies")
    assert compile_plan(replace(request, nodes=tuple(waived if n.node_id == "thermal" else n for n in request.nodes))).node("thermal").applicability_waiver
    with pytest.raises(InvalidScientificProblem, match="both declares"):
        replace(node, applicability_waiver="also waived")
    assert waived.digest if hasattr(waived, "digest") else True


def test_m1_a_within_report_must_carry_the_evidence_it_was_decided_on():
    with pytest.raises(InvalidScientificProblem, match="must carry the digest of the evidence"):
        ApplicabilityReport("c", "within")
    assert ApplicabilityReport("c", "outside", reason="x").status == "outside"


# ------------------------------------------------------------------------------------------------------------- M2 trust handoff
def test_m2_a_partial_run_is_not_silently_assembled_into_a_credibility_report():
    from tests.test_system_runtime_executor import _dag
    request, context, ran = _dag()
    result = SystemExecutor(context).run(request)
    assert result.status is RunStatus.PARTIAL
    with pytest.raises(InvalidScientificProblem, match="dropping its unavailable observables would lower the evidence bar"):
        trust_handoff(result, request)
    report = trust_handoff(result, request, allow_partial=True)
    assert report.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE and "UNAVAILABLE observables" in report.notes and "o_b=blocked" in report.notes


# ------------------------------------------------------------------------------------------------------------- M3 providers
def test_m3_a_provider_record_is_matched_against_its_own_providers_bindings_and_never_against_another_providers():
    from engcore.system_runtime import ProviderBinding

    def run(ref_digest):
        ref = ProviderRecordRef("pybamm", "26.8", ref_digest, sha("id"), sha("rec"), True)
        request, context, _ = build(knobs=Knobs(provider_ref=ref))
        bindings = (ProviderBinding("b1", "pybamm", "26.8", sha("d2")), ProviderBinding("b2", "tespy", "0.9", sha("t1")))
        node = replace(next(n for n in request.nodes if n.node_id == "thermal"), provider_binding_ids=("b1", "b2"), configuration_digest=sha("cfg"))
        request = replace(request, nodes=tuple(node if n.node_id == "thermal" else n for n in request.nodes), provider_bindings=bindings)
        context.providers = FakeProviders(pybamm=_prov(version="26.8", digest=sha("d2")), tespy=_prov(version="0.9", digest=sha("t1")))
        return SystemExecutor(context).run(request)
    assert run(sha("d2")).receipt("thermal").status is NodeStatus.SUCCEEDED
    bad = run(sha("d3"))                                                    # right provider, wrong build: the tespy binding cannot excuse it
    assert bad.receipt("thermal").status is NodeStatus.FAILED and "no authorising binding matches" in bad.receipt("thermal").reason


# ------------------------------------------------------------------------------------------------------------- M4 restore order
def test_m4_authorities_are_restored_in_execution_order_so_the_latest_checkpoint_wins():
    class Shared(Counting):
        authority_id, identity_digest = "shared-auth", sha("shared-auth-identity")
    request, context, knobs = build()
    shared = Shared()
    context.authorities.register(shared)
    ref = AuthorityRef(shared.authority_id, shared.kind, shared.identity_digest)
    first = NodeSpec("zeta", NodeKind.NUMERICAL_EXECUTION, ref, (NodeOutputSpec("power", "W"),), checkpointable=True)
    second = NodeSpec("alpha", NodeKind.NUMERICAL_EXECUTION, ref, (NodeOutputSpec("power", "W"),), depends_on=("zeta",), checkpointable=True)
    request = replace(request, nodes=(first, second), observables=(RequestedObservable("p", "alpha", "power", "W"),), constraint_observations=(),
                      profile=ExecutionProfile((), "off", True, ("alpha",)))
    part1 = SystemExecutor(context).run(request, stop_after="alpha")
    cp = SystemCheckpoint.from_dict(json.loads(json.dumps(part1.checkpoints[-1].to_dict())))
    assert {a.node_id: a.payload for a in cp.authority_checkpoints} == {"zeta": {"n": 1}, "alpha": {"n": 2}}
    fresh = Shared()
    context2 = build()[1]
    context2.authorities.register(fresh)
    order = []
    original = fresh.restore
    fresh.restore = lambda payload: (order.append(dict(payload)), original(payload))[1]
    SystemExecutor(context2).run(request, resume=cp)
    assert order == [{"n": 1}, {"n": 2}] and fresh.n == 2                                    # plan order, not alphabetical (alpha < zeta)


# ------------------------------------------------------------------------------------------------------------- M5 time bound / paused
def test_m5_a_state_time_beyond_the_scenario_or_not_finite_is_a_failed_node_not_a_crash():
    def thermal_with_time(seconds):
        request, context, knobs = build()
        auth = context.authorities._items["thermal-auth"]
        original = auth._fn
        def fn(call):
            out = original(call)
            return replace(out, state_proposal=replace(out.state_proposal, time=Quantity(seconds, "s")))
        auth._fn = fn
        return SystemExecutor(context).run(request)
    late = thermal_with_time(1.0e9)
    assert late.receipt("thermal").status is NodeStatus.FAILED and "beyond the scenario end" in late.receipt("thermal").reason
    nan = thermal_with_time(float("nan"))
    assert nan.receipt("thermal").status is NodeStatus.FAILED and len(nan.state_history) == 1


def test_m5_a_multi_timescale_run_that_paused_short_of_the_requested_instant_is_not_exposed_as_complete():
    from engcore.scenarios import TimePoint
    runtime, calls = _stub_multiscale(status="paused", reached=100)
    until = TimePoint("sys", Quantity(1800, "s"))
    auth = MultiscaleAuthority("stub-ms3", runtime, initial_slow_state={}, extractors={"power": lambda r: Quantity(1.0, "W")}, until=until)
    request, context, _ = build()
    context.authorities.register(auth)
    heat = replace(next(n for n in request.nodes if n.node_id == "heat"), authority=auth.ref, literals=())
    request = replace(request, nodes=tuple(heat if n.node_id == "heat" else n for n in request.nodes), profile=ExecutionProfile(("multiscale",)))
    result = SystemExecutor(context).run(request)
    assert result.receipt("heat").status is NodeStatus.FAILED and "paused before the instant" in result.receipt("heat").reason


# ------------------------------------------------------------------------------------------------------------- M6 commit taint
def test_m6_after_a_refused_state_commit_a_later_committing_node_is_blocked_not_run_on_the_stale_state():
    request, context, knobs = build(knobs=Knobs(hot_limit_k=294.0))                       # thermal is refused (applicability)
    node = next(n for n in request.nodes if n.node_id == "thermal")
    second = replace(node, node_id="thermal2", inputs=(NodeInput("heat_in", "heat", "power", "W"),), material_refs=(), environment_requirements=())
    second = replace(second, inputs=(NodeInput("heat_in", "heat", "power", "W"),))
    request = replace(request, nodes=request.nodes + (second,), profile=ExecutionProfile())
    # thermal2 needs its own 'ambient' input: give it a literal instead
    from engcore.system_runtime import LiteralInput
    second = replace(second, literals=(LiteralInput("ambient", Quantity(293.15, "K"), UNKNOWN),))
    request = replace(request, nodes=tuple(second if n.node_id == "thermal2" else n for n in request.nodes))
    result = SystemExecutor(context).run(request)
    assert result.receipt("thermal").status is NodeStatus.REFUSED
    assert result.receipt("thermal2").status is NodeStatus.BLOCKED and "did not succeed" in result.receipt("thermal2").reason
    assert len(result.state_history) == 1


# ------------------------------------------------------------------------------------------------------------- M7 cache
def test_m7_exact_reuse_works_across_runs_for_dependent_nodes_and_says_so_in_the_trace():
    request, context, knobs = build(cache="exact")
    cache = ExecutionCache()
    first = SystemExecutor(context, cache=cache).run(request, run_id="run-one")
    second = SystemExecutor(context, cache=cache).run(request, run_id="run-two")               # a DIFFERENT run id
    assert knobs.calls == {"heat": 1, "thermal": 1, "report": 1}                               # dependents were reused, not re-executed
    assert all(second.receipt(n).cache_hit for n in ("heat", "thermal", "report"))
    trace = trace_result(second, "peak_temperature")
    assert any(link.level == "reuse" and "NOT executed in this run" in link.detail for link in trace.links)
    assert second.scientific_digest == first.scientific_digest


def test_m7_a_stateful_authority_is_never_served_from_the_cache_so_its_own_state_advances():
    counter = Counting()
    counter.deterministic = True           # deterministic but STATEFUL: reuse would skip the execution that advances its state
    request, context = _with_authority(counter)
    request = replace(request, profile=ExecutionProfile((), "exact", True, ()))
    cache = ExecutionCache()
    SystemExecutor(context, cache=cache).run(request)
    SystemExecutor(context, cache=cache).run(request)
    assert counter.n == 2


# ------------------------------------------------------------------------------------------------------------- LOW
def test_low_replay_compares_execution_identity_and_uncertainty_kind():
    a = _run()[3]
    b = _run(knobs=Knobs(current_a=11.0))[3]
    cmp = compare_runs(a, b, rel_tol=1.0)
    assert not cmp.identity_replay and any("execution identity" in d or "request digest" in d for d in cmp.identity_differences)


def test_low_a_balance_term_scale_cannot_erase_a_term():
    for bad in (0.0, float("nan"), float("inf"), True):
        with pytest.raises(InvalidScientificProblem, match="finite non-zero"):
            TermSource("t", "peak_temperature", bad)


def test_low_stop_after_a_node_the_checkpoint_already_completed_is_refused():
    request, context, part1 = _paused()
    cp = part1.checkpoints[-1]
    request2, context2, _ = build(checkpoint_after=("thermal",))
    with pytest.raises(InvalidScientificProblem, match="already completed"):
        SystemExecutor(context2).run(request2, resume=cp, stop_after="thermal")


def test_low_a_loaded_result_cannot_carry_derived_collections_that_its_receipts_do_not_support():
    request, context, knobs, result = _run()
    wire = json.loads(json.dumps(result.to_dict()))
    wire["provider_records"] = [{"schema": "forge.system_runtime.provider_record_ref/1", "provider_id": "pybamm", "provider_version": "1", "provider_digest": "",
                                 "execution_identity_digest": sha("x"), "record_digest": "", "succeeded": True}]
    with pytest.raises(InvalidScientificProblem, match="provider records differ"):
        SystemRunResult.from_dict(wire)
    wire = json.loads(json.dumps(result.to_dict()))
    wire["trust_inputs"]["execution_status"] = "partial"
    with pytest.raises(InvalidScientificProblem, match="trust inputs differ"):
        SystemRunResult.from_dict(wire)
    wire = json.loads(json.dumps(result.to_dict()))
    wire["preflight"]["status"] = "ready"                                   # a report with a deferred check cannot claim READY
    with pytest.raises(InvalidScientificProblem, match="disagrees with its findings"):
        SystemRunResult.from_dict(wire)
