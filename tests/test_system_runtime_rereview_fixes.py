"""BIG 12 third review (BIG 14 14.1): one regression per finding fixed in this batch.

(a) a validity record cannot attach to a model-selection label; R1 the pinned constraint definition must be the constraint the
node assesses; N1 a checkpoint taken after a failure is incomplete; N2 a multi-timescale run refuses a committed state it does not
start from; (c) a resume stage names the stage it continues and depends on it; LOW receipt completeness flags are strict booleans
and an unresolvable authority fails a checkpoint instead of skipping it.
"""

from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.multiphysics.state import InitialStateValue
from engcore.scientific.units.quantity import Quantity
from engcore.system_runtime import (
    CallbackAuthority, ConstraintObservation, LiteralInput, MultiscaleAuthority, NodeInput, NodeKind, NodeOutcome, NodeOutputSpec, NodeSpec, NodeStatus,
    OutputValue, PreflightStatus, ResumeRefused, SystemExecutor, compile_plan, preflight, trust_handoff, verify_checkpoint,
)
from engcore.system_runtime.records import AuthorityRegistry, NodeReceipt
from engcore.system_runtime._common import digest_of
from tests.system_runtime_fixtures import UNKNOWN, Knobs, build, sha
from tests.test_system_runtime_review_fixes import _stub_multiscale


# ------------------------------------------------------------------------------------------------ (a) model selection is a label
def test_a_validity_records_are_refused_while_model_selections_are_unbound_labels():
    request, context, _ = build()
    result = SystemExecutor(context).run(request)
    trust_handoff(result, request)                                   # the shipped path (no validity) still assembles
    with pytest.raises(InvalidScientificProblem, match="validity records are refused"):
        trust_handoff(result, request, validity=(object(),))


# ------------------------------------------------------------------------------------------------ R1 definition name
def test_r1_a_second_declared_constraint_of_the_same_dimension_cannot_stand_in_for_the_one_observed():
    from engcore.scientific.ir.constraints import ConstraintDefinition, ConstraintOperator
    from engcore.systems import SystemDefinition
    request, context, _ = build()
    system = context.system
    other = ConstraintDefinition("min_cell_temperature", "cell_temperature", ConstraintOperator.GREATER_EQUAL, Quantity(250.0, "K"))
    system = SystemDefinition(system.system_id, system.version, system.definitions, system.instances, system.connections, (), (),
                              system.constraint_bindings, system.constraints + (other,))
    other_digest = digest_of(other.to_dict())
    (obs,) = request.constraint_observations
    request = replace(request, system=replace(request.system, digest=system.digest),
                      constraint_observations=(ConstraintObservation(obs.binding_id, obs.constraint_id, other_digest, obs.observable_id),))
    context.system = system
    context.constraints = {**context.constraints, other_digest: other}
    report = preflight(request, compile_plan(request), context)
    assert report.status is PreflightStatus.REFUSED
    assert any("not the constraint 'max_cell_temperature'" in f.message for f in report.findings)


# ------------------------------------------------------------------------------------------------ N1 checkpoint after a failure
def _with_independent_node():
    request, context, knobs = build(knobs=Knobs(hot_limit_k=294.0))              # thermal (state-committing) is refused
    aux = CallbackAuthority("aux-auth", lambda call: NodeOutcome("succeeded", {"x": OutputValue(Quantity(1.0, "W"), UNKNOWN, "aux")}),
                            config={}, deterministic=True)
    context.authorities.register(aux)
    node = NodeSpec("zz_aux", NodeKind.NUMERICAL_EXECUTION, aux.ref, (NodeOutputSpec("x", "W"),),
                    inputs=(NodeInput("p", "heat", "power", "W"),), checkpointable=True)     # same plan level as thermal, ordered after it
    request = replace(request, nodes=request.nodes + (node,), profile=replace(request.profile, checkpoint_after=("zz_aux",)))
    return request, context


def test_n1_a_checkpoint_taken_after_a_refused_node_is_incomplete_and_is_never_resumed():
    request, context = _with_independent_node()
    order = [n.node_id for n in compile_plan(request).nodes]
    assert order.index("thermal") < order.index("zz_aux")
    result = SystemExecutor(context).run(request)
    assert result.receipt("thermal").status is NodeStatus.REFUSED
    cp = result.checkpoints[-1]
    assert cp.complete is False and "thermal" in cp.incomplete_reason
    with pytest.raises(ResumeRefused, match="incomplete"):
        SystemExecutor(context).run(request, resume=cp)


# ------------------------------------------------------------------------------------------------ N2 multiscale starts from its own state
def _multiscale_on_heat(initial_temperature):
    runtime, calls = _stub_multiscale()
    auth = MultiscaleAuthority("stub-ms-n2", runtime, initial_slow_state={"cell": {"temperature": InitialStateValue("temperature", Quantity(300.0, "K"), UNKNOWN)}},
                               extractors={"power": lambda r: Quantity(1.0, "W")}, slow_state_owners={"cell": "cell"})
    request, context, _ = build(initial_temperature=initial_temperature)
    context.authorities.register(auth)
    heat = replace(next(n for n in request.nodes if n.node_id == "heat"), authority=auth.ref, literals=())
    request = replace(request, nodes=tuple(heat if n.node_id == "heat" else n for n in request.nodes),
                      profile=replace(request.profile, requested_modes=("multiscale",)))
    return request, context, calls


def test_n2_a_multi_timescale_run_refuses_a_committed_state_other_than_the_one_it_starts_from():
    request, context, calls = _multiscale_on_heat(350.0)
    result = SystemExecutor(context).run(request)
    receipt = result.receipt("heat")
    assert receipt.status is NodeStatus.FAILED and "not the state this multi-timescale run starts from" in receipt.reason
    assert calls["run"] == 0
    request, context, calls = _multiscale_on_heat(300.0)                         # control: the same state is accepted
    assert SystemExecutor(context).run(request).receipt("heat").status is NodeStatus.SUCCEEDED
    assert calls["run"] == 1


# ------------------------------------------------------------------------------------------------ (c) resume source is declared
def test_c_a_resume_stage_must_name_and_depend_on_the_stage_it_continues():
    runtime, _ = _stub_multiscale()
    unnamed = MultiscaleAuthority("ms-c1", runtime, initial_slow_state={}, extractors={}, stages={"b": {"until": None, "resume": True}})
    assert [c for c, _ in unnamed.preflight_findings(SimpleNamespace(node_id="b", depends_on=("a",)), None)] == ["INVALID_STAGE"]
    named = MultiscaleAuthority("ms-c2", runtime, initial_slow_state={}, extractors={}, stages={"b": {"until": None, "resume": True, "from": "a"}})
    assert named.identity_digest != unnamed.identity_digest
    assert "does not depend" in named.preflight_findings(SimpleNamespace(node_id="b", depends_on=()), None)[0][1]
    assert named.preflight_findings(SimpleNamespace(node_id="b", depends_on=("a",)), None) == ()
    plain = MultiscaleAuthority("ms-c3", runtime, initial_slow_state={}, extractors={}, stages={"a": {"until": None, "resume": False}})
    assert plain.preflight_findings(SimpleNamespace(node_id="a", depends_on=()), None) == ()


def test_c_a_held_checkpoint_from_another_stage_or_restored_without_its_origin_is_not_resumed():
    runtime, calls = _stub_multiscale()
    auth = MultiscaleAuthority("ms-c4", runtime, initial_slow_state={}, extractors={}, stages={"b": {"until": None, "resume": True, "from": "a"}})
    call = SimpleNamespace(node=SimpleNamespace(node_id="b", commits_state=False), state=None)
    auth.restore({"checkpoint": {"stub": True}})                                   # a payload of unknown origin
    outcome = auth.execute(call)
    assert outcome.status == "failed" and "not from the stage 'a'" in outcome.reason
    auth.restored_from("x")                                                       # restored, but from another node
    assert auth.execute(call).status == "failed"
    auth.restored_from("a")                                                       # the right origin passes the gate (the stub payload
    with pytest.raises(InvalidScientificProblem, match="checkpoint payload"):     # then reaches MacroCheckpoint, which refuses it)
        auth.execute(call)


# ------------------------------------------------------------------------------------------------ LOW receipts and resolution
def test_low_a_non_boolean_completeness_declaration_is_refused_on_an_outcome_and_on_a_loaded_receipt():
    with pytest.raises(InvalidScientificProblem, match="boolean"):
        NodeOutcome("succeeded", {}, authority_checkpoint=(sha("cp"), "false"))
    request, context, _ = build()
    wire = json.loads(json.dumps(SystemExecutor(context).run(request).receipt("thermal").to_dict()))
    wire["authority_checkpoint"] = [sha("cp"), "false"]
    with pytest.raises(InvalidScientificProblem, match="boolean"):
        NodeReceipt.from_dict(wire)
    wire["authority_checkpoint"] = [sha("cp"), True]
    assert NodeReceipt.from_dict(wire).authority_checkpoint == (sha("cp"), True)


def test_low_a_checkpoint_whose_authority_cannot_be_resolved_is_refused_not_skipped():
    request, context, _ = build(checkpoint_after=("thermal",))
    cp = SystemExecutor(context).run(request, stop_after="thermal").checkpoints[-1]
    context.authorities = AuthorityRegistry(())
    with pytest.raises(ResumeRefused, match="cannot be resolved"):
        verify_checkpoint(cp, request, compile_plan(request), tuple(sorted(cp.context_digests)), context)


# ------------------------------------------------------------------------------------------------ second review of this batch
def test_n1_a_flipped_completeness_flag_cannot_hide_a_node_that_did_not_succeed():
    from engcore.system_runtime import SystemCheckpoint
    request, context = _with_independent_node()
    cp = SystemExecutor(context).run(request).checkpoints[-1]
    forged = SystemCheckpoint.from_dict({**cp.to_dict(), "complete": True, "incomplete_reason": ""})
    with pytest.raises(ResumeRefused, match="precede completed nodes but did not complete"):
        verify_checkpoint(forged, request, compile_plan(request), tuple(sorted(forged.context_digests)), context)


def test_n2_a_resume_stage_refuses_a_committed_state_other_than_the_one_its_checkpoint_continues(monkeypatch):
    from engcore import multiscale
    from engcore.system_runtime import SystemState
    runtime, calls = _stub_multiscale()
    start = {"cell": {"temperature": InitialStateValue("temperature", Quantity(300.0, "K"), UNKNOWN)}}
    auth = MultiscaleAuthority("ms-n2r", runtime, initial_slow_state=start, extractors={}, slow_state_owners={"cell": "cell"},
                               stages={"b": {"until": None, "resume": True, "from": "a"}})
    monkeypatch.setattr(multiscale.MacroCheckpoint, "deserialize", classmethod(lambda cls, payload: SimpleNamespace(slow_state=start)))
    auth.restore({"checkpoint": {}, "digest": sha("x")})
    auth.restored_from("a")
    for temperature, expected in ((350.0, "failed"), (300.0, "succeeded")):       # another node moved the owner to 350 K after stage a
        request, _, _ = build(initial_temperature=temperature)
        state = SystemState.initial(request.initial_state, request_digest=request.digest, system_digest=request.system.digest,
                                    environment_digest=request.environment.digest)
        outcome = auth.execute(SimpleNamespace(node=SimpleNamespace(node_id="b", commits_state=False), state=state))
        assert outcome.status == expected, outcome.reason
        assert expected == "succeeded" or "macro checkpoint continues from" in outcome.reason


def test_d1_a_committing_node_refused_by_the_wall_budget_taints_later_commits():
    import sys
    from engcore.execution.orchestration.resources import ResourceBudget

    def clock():                                   # past the budget exactly at the budget check before 'thermal'
        frame = sys._getframe(1)
        node = frame.f_locals.get("node") if frame.f_code.co_name == "run" else None
        return 100.0 if node is not None and getattr(node, "node_id", "") == "thermal" else 0.0

    request, context, _ = build()
    thermal = next(n for n in request.nodes if n.node_id == "thermal")
    second = replace(thermal, node_id="thermal2", inputs=(NodeInput("heat_in", "heat", "power", "W"),), material_refs=(), environment_requirements=(),
                     literals=(LiteralInput("ambient", Quantity(293.15, "K"), UNKNOWN),))
    request = replace(request, nodes=request.nodes + (second,),
                      operational=replace(request.operational, resource_budget=ResourceBudget(max_wall_seconds=10.0)))
    result = SystemExecutor(context, clock=clock).run(request)
    assert result.receipt("thermal").status is NodeStatus.REFUSED and "wall-time budget" in result.receipt("thermal").reason
    assert result.receipt("thermal2").status is NodeStatus.BLOCKED and "did not succeed" in result.receipt("thermal2").reason


def test_a_request_labels_are_kept_as_requested_selections_never_as_executed_models():
    from engcore.system_runtime import ModelSelection
    request, context, _ = build()
    result = SystemExecutor(context).run(request)
    report = trust_handoff(result, request)
    assert report.provenance.models == ()
    labelled = replace(request, model_selections=(ModelSelection("cell", "m", "1"),))
    result = SystemExecutor(context).run(labelled)
    report = trust_handoff(result, labelled)
    assert report.provenance.models == () and report.provenance.metadata["requested_model_selections"] == "cell=m@1"


def test_n2_two_slow_owner_domains_are_compared_on_the_fresh_and_the_resume_path(monkeypatch):
    """Re-review of this batch: the comparison loop shadowed its own argument, so a second domain raised instead of being compared."""
    from engcore import multiscale
    runtime, _ = _stub_multiscale()
    v = lambda name, x, unit: InitialStateValue(name, Quantity(x, unit), UNKNOWN)                     # noqa: E731
    start = {"cell": {"fade": v("fade", 0.0, "dimensionless")}, "pack": {"temperature": v("temperature", 300.0, "K")}}
    owners = {"c1": (v("fade", 0.0, "dimensionless"),), "c2": (v("temperature", 300.0, "K"),)}

    def state(pack_k):
        held = dict(owners, c2=(v("temperature", pack_k, "K"),))
        return SimpleNamespace(owner=lambda oid: SimpleNamespace(values=held[oid], role="component"))

    fresh = MultiscaleAuthority("ms-2d", runtime, initial_slow_state=start, extractors={}, slow_state_owners={"cell": "c1", "pack": "c2"})
    call = lambda pack_k, node="n": SimpleNamespace(node=SimpleNamespace(node_id=node, commits_state=False), state=state(pack_k))  # noqa: E731
    assert fresh.execute(call(300.0)).status == "succeeded"
    out = fresh.execute(call(301.0))
    assert out.status == "failed" and "c2.temperature" in out.reason
    resume = MultiscaleAuthority("ms-2d-r", runtime, initial_slow_state=start, extractors={}, slow_state_owners={"cell": "c1", "pack": "c2"},
                                 stages={"b": {"until": None, "resume": True, "from": "a"}})
    monkeypatch.setattr(multiscale.MacroCheckpoint, "deserialize", classmethod(lambda cls, payload: SimpleNamespace(slow_state=start)))
    resume.restore({"checkpoint": {}, "digest": sha("x")})
    resume.restored_from("a")
    assert resume.execute(call(300.0, "b")).status == "succeeded"
    out = resume.execute(call(301.0, "b"))
    assert out.status == "failed" and "c2.temperature" in out.reason
