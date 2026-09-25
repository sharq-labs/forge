"""BIG 12 executor semantics with in-process authorities.

Gates A (request -> plan -> execution -> result -> receipt -> trace), D (failure propagation),
G (provider unavailable), H (runtime applicability rollback), J (exact reuse / stale protection),
L (trust separation), plus constraints, conservation, result integrity and tracing.
"""

from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from engcore.credibility.evidence import CredibilityVerdict
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.units.quantity import Quantity
from engcore.system_runtime import (
    Availability, BalanceSpec, CallbackAuthority, ExecutionCache, ExecutionProfile, NodeKind, NodeOutcome, NodeOutputSpec, NodeSpec, NodeInput, NodeStatus,
    OutputValue, PreflightStatus, ProviderBinding, ProviderRecordRef, RequestedObservable, RunStatus, SystemExecutor, SystemRunResult, TermSource, compile_plan,
    assess_conservation, assess_constraints, output_stamp, preflight, trace_result, trust_handoff,
)
from tests.system_runtime_fixtures import UNKNOWN, Knobs, build, sha


def _run(**kw):
    request, context, knobs = build(**kw)
    return request, context, knobs, SystemExecutor(context).run(request)


# ------------------------------------------------------------------------------------------------------- Gate A
def test_gate_a_request_to_plan_to_execution_to_result_to_receipt_to_trace():
    request, context, knobs, result = _run()
    assert result.status is RunStatus.SUCCEEDED
    assert result.request_digest == request.digest and result.plan_digest == compile_plan(request).digest
    assert [r.status for r in result.node_receipts] == [NodeStatus.SUCCEEDED] * 6
    peak = result.observable("peak_temperature")
    assert peak.availability is Availability.AVAILABLE and peak.value.value.magnitude == pytest.approx(295.0)   # ambient 293.15 + 37 W * 0.05
    assert result.observable("heat_power").value.value.magnitude == pytest.approx(37.0)
    # the state committed once (thermal), atomically, as a digest chain
    assert len(result.state_history) == 2 and result.final_state.previous_digest == result.initial_state.digest
    assert result.final_state.owner("cell").values[0].value.magnitude == pytest.approx(295.0)
    trace = trace_result(result, "peak_temperature")
    assert trace.complete and {"result", "node", "authority", "material", "environment", "state", "system", "scenario", "timeline"} <= set(trace.levels())
    # every number carries an explicit uncertainty statement: unknown stays unknown
    assert all(o.value.uncertainty.kind.value == "unknown" for o in result.observables)
    assert "peak_temperature" not in " ".join(result.trust_inputs.unknown_uncertainty_outputs)  # they are listed as node outputs
    assert any(name.endswith(".peak") for name in result.trust_inputs.unknown_uncertainty_outputs)


def test_the_executor_is_generic_no_domain_words_in_the_execution_code():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "engcore" / "system_runtime"
    text = "\n".join(p.read_text(encoding="utf-8").lower() for p in root.glob("*.py"))
    for word in ("battery", "pybamm", "tespy", "openfoam", "calculix", "electrochem", "cfd", "thermal_conductivity"):
        assert word not in text.replace("multiphysics", ""), word


# ------------------------------------------------------------------------------------------------------- Gate D
def _dag(k_fail: bool = True):
    """A -> B -> D and an independent C.  A fails; B and D depend on it; C does not."""
    request, context, knobs = build()
    ran = []

    def make(name, fail=False):
        def fn(call):
            ran.append(name)
            if fail:
                return NodeOutcome.failed(f"{name} failed on purpose")
            base = sum(v.value.magnitude for v in call.inputs.values()) if call.inputs else 1.0
            return NodeOutcome("succeeded", {"x": OutputValue(Quantity(base + 1.0, "K"), UNKNOWN, name)})
        return CallbackAuthority(f"auth-{name}", fn, config={"n": name, "fail": fail}, deterministic=True)

    auths = {n: make(n, fail=(n == "a" and k_fail)) for n in "abcd"}
    for a in auths.values():
        context.authorities.register(a)
    node = lambda n, **kw: NodeSpec(n, NodeKind.NUMERICAL_EXECUTION, auths[n].ref, (NodeOutputSpec("x", "K"),), **kw)  # noqa: E731
    nodes = (node("a"), node("b", inputs=(NodeInput("i", "a", "x", "K"),)), node("c"), node("d", inputs=(NodeInput("i", "b", "x", "K"),)))
    obs = tuple(RequestedObservable(f"o_{n}", n, "x", "K") for n in "abcd")
    request = replace(request, nodes=nodes, observables=obs, constraint_observations=(), profile=ExecutionProfile())
    return request, context, ran


def test_gate_d_failure_blocks_dependents_but_independent_branches_still_succeed():
    request, context, ran = _dag()
    result = SystemExecutor(context).run(request)
    status = {r.node_id: r.status for r in result.node_receipts if not r.node_id.startswith(("env.", "mat.", "constraint."))}
    assert status == {"a": NodeStatus.FAILED, "b": NodeStatus.BLOCKED, "c": NodeStatus.SUCCEEDED, "d": NodeStatus.BLOCKED}
    assert ran == ["a", "c"]                                             # B and D were never executed: no failed output leaked downstream
    assert result.status is RunStatus.PARTIAL                            # partial results never read as a whole run
    o = {x.observable_id: x for x in result.observables}
    assert o["o_a"].availability is Availability.FAILED and o["o_c"].availability is Availability.AVAILABLE
    assert o["o_b"].availability is Availability.BLOCKED and o["o_b"].root_causes == ("a",)
    assert o["o_d"].availability is Availability.BLOCKED and o["o_d"].root_causes == ("a",)  # the root cause, not the intermediate node
    assert o["o_d"].dependency_path == ("a", "b", "d") and o["o_d"].value is None
    assert set(result.node_outputs) == {"c"}


def test_gate_d_a_request_that_forbids_partial_results_blocks_everything_after_the_first_failure():
    request, context, ran = _dag()
    request = replace(request, profile=ExecutionProfile(allow_partial=False))
    result = SystemExecutor(context).run(request)
    assert ran == ["a"] and result.status is RunStatus.FAILED
    assert {r.node_id: r.status for r in result.node_receipts}["c"] is NodeStatus.BLOCKED


def test_gate_d_a_raising_authority_is_a_failed_node_that_exposes_nothing_and_blocks_its_dependents():
    request, context, knobs, result = _run(knobs=Knobs(thermal_raises=True))
    assert result.receipt("thermal").status is NodeStatus.FAILED and "solver blew up" in result.receipt("thermal").reason
    assert result.observable("peak_temperature").availability is Availability.BLOCKED
    assert result.observable("heat_power").availability is Availability.AVAILABLE      # independent of thermal
    assert "thermal" not in result.node_outputs and len(result.state_history) == 1     # no state advance either


def test_a_dishonest_outcome_shape_is_a_failed_node():
    for knobs, fragment in ((Knobs(extra_output=True), "differ from the declared"), (Knobs(propose_bad_owner=True), "not allowed to write")):
        request, context, k, result = _run(knobs=knobs)
        thermal = result.receipt("thermal")
        assert thermal.status is NodeStatus.FAILED and fragment in thermal.reason, thermal.reason
        assert len(result.state_history) == 1 and "thermal" not in result.node_outputs


# ------------------------------------------------------------------------------------------------------- Gate G
class FakeProviders:
    def __init__(self, **items):
        self.items = items

    def status(self, provider_id):
        if provider_id not in self.items:
            raise KeyError(provider_id)
        return self.items[provider_id]


def _prov(available=True, version="26.8", digest=None, reason=""):
    return SimpleNamespace(available=available, version=version, digest=digest or sha("build"),
                           availability=SimpleNamespace(value="available" if available else "unavailable"), reason=reason)


def _with_provider(binding: ProviderBinding, providers):
    request, context, knobs = build()
    thermal = replace(request.nodes[[n.node_id for n in request.nodes].index("thermal")], provider_binding_ids=("b",))
    nodes = tuple(thermal if n.node_id == "thermal" else n for n in request.nodes)
    request = replace(request, nodes=nodes, provider_bindings=(binding,))
    context.providers = providers
    return request, context, knobs


def test_gate_g_a_required_provider_that_is_unavailable_refuses_the_run_and_nothing_is_substituted():
    request, context, knobs = _with_provider(ProviderBinding("b", "pybamm", "26.8"), FakeProviders(tespy=_prov(version="0.11")))  # an alternative EXISTS
    report = preflight(request, compile_plan(request), context)
    assert report.status is PreflightStatus.REFUSED and "PROVIDER_UNAVAILABLE" in report.codes()
    result = SystemExecutor(context).run(request)
    assert result.status is RunStatus.REFUSED
    assert knobs.calls == {"heat": 0, "thermal": 0, "report": 0}                        # nothing ran, in particular no fallback
    assert all(o.availability is Availability.REFUSED for o in result.observables) and result.node_outputs == {}
    assert result.initial_state is None and result.final_state is None


@pytest.mark.parametrize("providers,code", [
    (FakeProviders(pybamm=_prov(available=False, reason="library missing")), "PROVIDER_UNAVAILABLE"),
    (FakeProviders(pybamm=_prov(version="26.9")), "PROVIDER_VERSION_MISMATCH"),
])
def test_gate_g_unavailable_or_wrong_version_providers_refuse(providers, code):
    request, context, knobs = _with_provider(ProviderBinding("b", "pybamm", "26.8"), providers)
    assert code in preflight(request, compile_plan(request), context).codes()


def test_gate_g_a_pinned_build_digest_must_match_and_a_matching_provider_is_admitted():
    request, context, _ = _with_provider(ProviderBinding("b", "pybamm", "26.8", sha("other build")), FakeProviders(pybamm=_prov()))
    assert "PROVIDER_DIGEST_MISMATCH" in preflight(request, compile_plan(request), context).codes()
    request, context, _ = _with_provider(ProviderBinding("b", "pybamm", "26.8", sha("build")), FakeProviders(pybamm=_prov()))
    assert preflight(request, compile_plan(request), context).status is PreflightStatus.DEFERRED_CHECKS


def test_a_node_cannot_use_a_provider_the_request_did_not_bind_or_a_different_version():
    ref = ProviderRecordRef("tespy", "0.11", sha("d"), sha("identity"), sha("record"), True)
    request, context, knobs = build(knobs=Knobs(provider_ref=ref))
    result = SystemExecutor(context).run(request)
    assert result.receipt("thermal").status is NodeStatus.FAILED and "no substitute provider" in result.receipt("thermal").reason
    request, context, _ = _with_provider(ProviderBinding("b", "pybamm", "26.8"), FakeProviders(pybamm=_prov()))
    wrong = ProviderRecordRef("pybamm", "26.7", sha("d"), sha("identity"), sha("record"), True)
    context.authorities.register(CallbackAuthority("x", lambda c: NodeOutcome.failed("unused")))
    request2, context2, _ = build(knobs=Knobs(provider_ref=wrong))
    thermal = replace(next(n for n in request2.nodes if n.node_id == "thermal"), provider_binding_ids=("b",))
    request2 = replace(request2, nodes=tuple(thermal if n.node_id == "thermal" else n for n in request2.nodes), provider_bindings=(ProviderBinding("b", "pybamm", "26.8"),))
    context2.providers = FakeProviders(pybamm=_prov())
    result2 = SystemExecutor(context2).run(request2)
    assert result2.receipt("thermal").status is NodeStatus.FAILED and "requires '26.8'" in result2.receipt("thermal").reason


def test_missing_authorities_and_authority_identity_changes_refuse_before_execution():
    request, context, knobs = build()
    context.authorities = type(context.authorities)()
    assert "AUTHORITY_UNAVAILABLE" in preflight(request, compile_plan(request), context).codes()
    request, context, knobs = build()
    other = CallbackAuthority("thermal-auth2", lambda c: NodeOutcome.failed("x"))
    changed = replace(next(n for n in request.nodes if n.node_id == "thermal"), authority=replace(other.ref, authority_id="thermal-auth"))
    request = replace(request, nodes=tuple(changed if n.node_id == "thermal" else n for n in request.nodes))
    assert "AUTHORITY_IDENTITY_MISMATCH" in preflight(request, compile_plan(request), context).codes()


# ------------------------------------------------------------------------------------------------------- Gate H
def test_gate_h_leaving_applicability_on_the_solved_state_rolls_back_and_blocks_downstream():
    request, context, knobs, result = _run(knobs=Knobs(hot_limit_k=294.0))     # solved T = 295 K > 294 K
    thermal = result.receipt("thermal")
    assert thermal.status is NodeStatus.REFUSED and "left applicability" in thermal.reason and "not committed" in thermal.reason
    assert len(result.state_history) == 1 and result.final_state.digest == result.initial_state.digest     # previous state stays authoritative
    assert result.final_state.owner("cell").values[0].value.magnitude == pytest.approx(300.0)
    assert "thermal" not in result.node_outputs                                                             # the solved value is not exposed
    assert result.observable("peak_temperature").availability is Availability.BLOCKED
    assert result.observable("peak_temperature").root_causes == ("thermal",)
    assert result.receipt("report").status is NodeStatus.BLOCKED and result.receipt("constraint.b_tmax").status is NodeStatus.BLOCKED
    assert result.observable("heat_power").availability is Availability.AVAILABLE
    assert thermal.applicability[0].status == "outside" and thermal.state_after_digest == ""


def test_gate_h_a_declared_runtime_check_that_is_not_established_never_passes():
    request, context, knobs, result = _run(knobs=Knobs(omit_applicability=True))
    assert result.receipt("thermal").status is NodeStatus.REFUSED and "not established" in result.receipt("thermal").reason
    assert len(result.state_history) == 1


def test_a_deferred_check_is_listed_by_preflight_not_treated_as_passed():
    request, context, knobs = build()
    report = preflight(request, compile_plan(request), context)
    assert report.status is PreflightStatus.DEFERRED_CHECKS and [(d.node_id, d.check_id) for d in report.deferred_checks] == [("thermal", "temp_in_range")]
    assert report.to_dict()["classification"] == "preflight_admission_not_scientific_support"


# ------------------------------------------------------------------------------------------------------- preflight refusals
def test_preflight_refuses_what_is_knowable_in_advance():
    request, context, knobs = build()
    assert preflight(request, compile_plan(request), context).status is PreflightStatus.DEFERRED_CHECKS
    cases = {
        "MISSING_CONTENT": lambda r, c: setattr(c, "timeline", None),
        "CONTENT_DIGEST_MISMATCH": lambda r, c: setattr(c, "scenario", build(scn_version="2")[1].scenario),
        "MISSING_MATERIAL": lambda r, c: setattr(c, "resolved_properties", {}),
        "INITIAL_TIME_OUTSIDE_SCENARIO": lambda r, c: None,
        "TIME_BASIS_MISMATCH": lambda r, c: setattr(c, "timeline", build(ambient=(1.0, 2.0))[1].timeline),
        "INVALID_CONSTRAINT_BINDING": lambda r, c: setattr(c, "constraints", {}),
    }
    for code, mutate in cases.items():
        request, context, _ = build()
        if code == "INITIAL_TIME_OUTSIDE_SCENARIO":
            request = replace(request, initial_state=replace(request.initial_state, time=Quantity(9999, "s")))
        mutate(request, context)
        assert code in preflight(request, compile_plan(request), context).codes(), code


def test_preflight_refuses_an_unknown_material_and_a_missing_environment_channel_and_an_undeclared_environment():
    from tests.system_runtime_fixtures import material_property
    request, context, _ = build()
    _, unknown = material_property(known=False)
    node = next(n for n in request.nodes if n.node_id == "thermal")
    ref = replace(node.material_refs[0], resolved_digest=unknown.digest)
    request = replace(request, nodes=tuple(replace(node, material_refs=(ref,)) if n.node_id == "thermal" else n for n in request.nodes))
    context.resolved_properties = {unknown.digest: unknown}
    assert "MATERIAL_UNKNOWN" in preflight(request, compile_plan(request), context).codes()       # UNKNOWN is never defaulted
    request, context, _ = build()
    absent = replace(request, environment=None, environment_absent_reason="none")
    assert {"MISSING_ENVIRONMENT", "UNDECLARED_ENVIRONMENT"} <= set(preflight(absent, compile_plan(absent), context).codes())


def test_preflight_refuses_a_disconnected_topology_and_unknown_state_owners_and_impossible_checkpoints():
    from engcore.scientific.multiphysics import PortDefinition, PortDirection, PortKind
    from engcore.systems import ComponentConnection, ComponentDefinition, ComponentInstance, SystemDefinition
    from engcore.scientific.twins import ScientificTwin, TwinKind
    request, context, _ = build()
    ports = (PortDefinition("p", PortDirection.OUTPUT, PortKind.SCALAR, "temperature", "K"),)
    t = lambda n: ScientificTwin(n, "1", TwinKind.CONCEPT).reference  # noqa: E731
    disconnected = SystemDefinition("s", "1", (ComponentDefinition("a", "1", ports), ComponentDefinition("b", "1", ports)),
                                    (ComponentInstance("a1", "a", "1", t("ta"), participant_id="pa"), ComponentInstance("b1", "b", "1", t("tb"), participant_id="pb")))
    context.system = disconnected
    request = replace(request, system=replace(request.system, digest=disconnected.digest))
    assert {"DISCONNECTED_TOPOLOGY", "UNKNOWN_STATE_OWNER"} <= set(preflight(request, compile_plan(request), context).codes())
    request, context, _ = build(checkpoint_after=("report",))
    assert "CHECKPOINT_IMPOSSIBLE" in preflight(request, compile_plan(request), context).codes()      # 'report' is not checkpointable


# ------------------------------------------------------------------------------------------------------- Gate J
def test_gate_j_a_failed_rerun_exposes_no_output_from_an_earlier_success():
    request, context, knobs = build()
    executor = SystemExecutor(context)
    ok = executor.run(request)
    assert ok.status is RunStatus.SUCCEEDED
    before = dict(knobs.calls)
    knobs.heat_fails = True                                                    # the very same authorities, now failing
    failed = executor.run(request)
    assert failed.receipt("heat").status is NodeStatus.FAILED
    assert failed.node_outputs.keys() == {"env.thermal.ambient", "mat.thermal.k"}      # only branches that did not depend on heat
    assert failed.observable("peak_temperature").availability is Availability.BLOCKED and failed.observable("peak_temperature").value is None
    assert knobs.calls["thermal"] == before["thermal"] and knobs.calls["report"] == before["report"]   # nothing downstream ran
    assert ok.observable("peak_temperature").value is not None                # the old result object is the old run, never merged into the new one


def test_gate_j_stored_outputs_are_verified_and_foreign_stale_or_modified_values_are_refused():
    request, context, knobs = build()
    executor = SystemExecutor(context)
    result = executor.run(request)
    plan = compile_plan(request)
    heat_out, heat_receipt = dict(result.node_outputs["heat"]), result.receipt("heat")
    good = executor._verify_stored(plan, result.run_id, "heat", heat_out, heat_receipt)
    assert good == ""
    assert "another run" in executor._verify_stored(plan, "run-someone-else", "heat", heat_out, heat_receipt)
    forged = {"power": OutputValue(Quantity(1.0, "W"), UNKNOWN, "forged")}
    assert "modified after execution" in executor._verify_stored(plan, result.run_id, "heat", forged, heat_receipt)
    assert "not a SUCCEEDED receipt of that node" in executor._verify_stored(plan, result.run_id, "thermal", heat_out, heat_receipt)
    other_plan = compile_plan(build(conductivity=99.0)[0])
    assert "another plan" in executor._verify_stored(other_plan, result.run_id, "heat", heat_out, heat_receipt)
    assert heat_receipt.stamp == output_stamp(result.run_id, plan.digest, "heat", heat_receipt.execution_identity_digest)


def test_gate_j_a_consumer_refuses_an_output_stamped_for_another_run():
    request, context, knobs = build()
    executor = SystemExecutor(context)
    first = executor.run(request)
    plan = compile_plan(request)
    store = {n: (dict(first.node_outputs[n]), first.receipt(n)) for n in ("heat", "env.thermal.ambient", "mat.thermal.k")}
    state = first.initial_state
    status, receipt, outputs, new_state, _ = executor._run_node(plan.node("thermal"), plan, request, state, store, "a-different-run", 1)
    assert status is NodeStatus.FAILED and "another run" in receipt.reason and outputs == {} and new_state is None


def test_gate_j_exact_reuse_only_of_identical_identity_never_new_evidence():
    request, context, knobs = build(cache="exact")
    cache = ExecutionCache()
    executor = SystemExecutor(context, cache=cache)
    first = executor.run(request)
    second = executor.run(request)
    assert second.scientific_digest == first.scientific_digest
    reused = [r for r in second.node_receipts if r.cache_hit]
    assert reused and all(r.original_receipt_digest for r in reused)          # a hit references the original receipt
    assert cache.hits == len(reused) and knobs.calls["heat"] == 1              # the authority ran once
    assert second.trust_inputs.validation_evidence == ()                       # a hit is not evidence
    # a materially different input does NOT hit
    request2, context2, knobs2 = build(cache="exact", conductivity=17.0)
    executor2 = SystemExecutor(context2, cache=cache)
    third = executor2.run(request2)
    assert knobs2.calls["thermal"] == 1


def test_gate_j_the_cache_never_stores_failures_and_never_serves_non_deterministic_authorities():
    request, context, knobs = build(cache="exact", knobs=Knobs(heat_fails=True))
    cache = ExecutionCache()
    SystemExecutor(context, cache=cache).run(request)
    assert all(v[0].status == "succeeded" for v in cache._items.values()) and "heat" not in str(cache._items.keys())
    knobs.heat_fails = False
    ran = SystemExecutor(context, cache=cache).run(request)
    assert knobs.calls["heat"] == 2                                              # the earlier failure was not cached
    request3, context3, knobs3 = build(cache="exact")
    for a in context3.authorities._items.values():
        a.deterministic = False
    c3 = ExecutionCache()
    SystemExecutor(context3, cache=c3).run(request3)
    SystemExecutor(context3, cache=c3).run(request3)
    assert knobs3.calls["heat"] == 2 and knobs3.calls["thermal"] == 2 and knobs3.calls["report"] == 2   # only the deterministic built-ins were cached


# ------------------------------------------------------------------------------------------------------- Gate L
def test_gate_l_successful_execution_is_not_scientific_support():
    request, context, knobs, result = _run()
    assert result.status is RunStatus.SUCCEEDED
    report = trust_handoff(result, request)
    assert report.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE           # decided by the EXISTING derive_verdict
    assert result.trust_inputs.assessment == "not_assessed_by_runtime" and result.trust_inputs.validation_evidence == ()
    assert result.classification == "system_execution_not_scientific_support"
    with pytest.raises(InvalidScientificProblem, match="cannot supply validation evidence"):
        replace(result.trust_inputs, validation_evidence=("something",))
    with pytest.raises(InvalidScientificProblem, match="no scientific assessment"):
        replace(result.trust_inputs, assessment="supported")


# ------------------------------------------------------------------------------------------------------- constraints / conservation
def _definitions(context):
    return dict(context.constraints)


def test_constraints_are_assessed_on_actual_results_and_missing_results_are_unavailable():
    request, context, knobs, result = _run()
    (a,) = assess_constraints(result, context.system, _definitions(context))
    assert a.status == "satisfied" and a.check.margin.magnitude == pytest.approx(373.15 - 295.0) and a.uncertainty_status == "unknown"
    request, context, knobs, result = _run(limit=290.0)
    (v,) = assess_constraints(result, context.system, _definitions(context))
    assert result.status is RunStatus.SUCCEEDED and v.status == "violated" and v.check.margin.magnitude == pytest.approx(-5.0)   # ran fine, constraint violated
    request, context, knobs, result = _run(knobs=Knobs(heat_fails=True))
    (u,) = assess_constraints(result, context.system, _definitions(context))
    assert u.status == "unavailable" and u.check is None and "blocked" in u.reason            # UNAVAILABLE, never a pass
    assert result.receipt("constraint.b_tmax").status is NodeStatus.BLOCKED


def test_the_constraint_margin_is_a_spread_not_an_absolute_temperature():
    request, context, knobs, result = _run()
    margin = result.node_outputs["constraint.b_tmax"]["margin"].value
    assert margin.units == "kelvin" and margin.magnitude == pytest.approx(78.15)


def test_conservation_closes_only_from_computed_terms_and_never_invents_a_zero():
    request, context, knobs, result = _run()
    tol = Quantity(1.0, "W")
    closed = assess_conservation(result, (BalanceSpec("power", (TermSource("electrical", "heat_power"),), (TermSource("thermal", "heat_power"),), tol),))
    assert closed[0].status == "closed"
    off = assess_conservation(result, (BalanceSpec("power", (TermSource("electrical", "heat_power"),), (TermSource("thermal", "heat_power", 0.5),), tol),))
    assert off[0].status == "not_closed" and off[0].residual.magnitude == pytest.approx(18.5)
    request, context, knobs, blocked = _run(knobs=Knobs(heat_fails=True))
    inc = assess_conservation(blocked, (BalanceSpec("power", (TermSource("electrical", "heat_power"),), (TermSource("loss", "peak_temperature"),), tol),))
    assert inc[0].status == "incomplete" and len(inc[0].missing_terms) == 2 and inc[0].residual is None


# ------------------------------------------------------------------------------------------------------- result integrity
def test_the_result_round_trips_and_its_digest_is_stable():
    request, context, knobs, result = _run()
    wire = json.loads(json.dumps(result.to_dict()))
    restored = SystemRunResult.from_dict(wire)
    assert restored.digest == result.digest and restored.scientific_digest == result.scientific_digest


@pytest.mark.parametrize("mutate,match", [
    (lambda w: w["observables"][0]["value"]["value"].update(magnitude=1.0e6) or w["observables"][1]["value"]["value"].update(magnitude=1.0e6), "does not carry the value"),
    (lambda w: w["node_receipts"][3].update(status="failed"), "exposes outputs"),
    (lambda w: w["node_outputs"].pop("heat"), "do not match its receipt"),
    (lambda w: w["state_history"][1].update(previous_digest="0" * 64), "digest chain"),
    (lambda w: w["node_receipts"].pop(), "exactly one receipt per plan node"),
    (lambda w: w.update(classification="validated"), "never scientific support"),
    (lambda w: w["plan"].update(request_digest="1" * 64), "does not match the plan"),
    (lambda w: w.update(surprise=1), "unknown"),
])
def test_a_tampered_result_is_refused(mutate, match):
    request, context, knobs, result = _run()
    wire = json.loads(json.dumps(result.to_dict()))
    mutate(wire)
    with pytest.raises(Exception, match=match):
        SystemRunResult.from_dict(wire)


def test_a_partial_result_cannot_claim_a_blocked_observable_is_available():
    request, context, knobs, result = _run(knobs=Knobs(heat_fails=True))
    wire = json.loads(json.dumps(result.to_dict()))
    wire["observables"] = [dict(o, availability="available", value=None) if o["observable_id"] == "peak_temperature" else o for o in wire["observables"]]
    with pytest.raises(InvalidScientificProblem, match="exactly when it is AVAILABLE"):
        SystemRunResult.from_dict(wire)


# ------------------------------------------------------------------------------------------------------- tracing
def test_the_trace_reports_gaps_instead_of_inventing_lineage():
    request, context, knobs, result = _run(knobs=Knobs(heat_fails=True))
    trace = trace_result(result, "peak_temperature")
    assert not trace.complete and "blocked" in trace.gaps[0]
    request, context, knobs, ok = _run()
    wire = json.loads(json.dumps(ok.to_dict()))
    wire["provenance"] = [p for p in wire["provenance"] if p[0] != "scenario"]
    partial = SystemRunResult.from_dict(wire)
    assert any("scenario" in g for g in trace_result(partial, "peak_temperature").gaps)


def test_a_node_with_provider_bindings_and_no_provider_record_is_a_lineage_gap():
    request, context, knobs = _with_provider(ProviderBinding("b", "pybamm", "26.8"), FakeProviders(pybamm=_prov()))
    result = SystemExecutor(context).run(request)
    assert result.status is RunStatus.SUCCEEDED
    gaps = trace_result(result, "peak_temperature").gaps
    # lineage is transitive: 'thermal' (upstream of 'report') names a provider binding but recorded no execution
    assert any("node 'thermal' names provider bindings but its receipt records no provider execution" in g for g in gaps)
    request2 = replace(request, observables=(RequestedObservable("t", "thermal", "temperature", "K"),), constraint_observations=())
    r2 = SystemExecutor(context).run(request2)
    assert any("names provider bindings but its receipt records no provider execution" in g for g in trace_result(r2, "t").gaps)
