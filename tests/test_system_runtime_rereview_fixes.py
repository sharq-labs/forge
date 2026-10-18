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
    CallbackAuthority, ConstraintObservation, LiteralInput, NodeInput, NodeKind, NodeOutcome, NodeOutputSpec, NodeSpec, NodeStatus,
    OutputValue, PreflightStatus, ResumeRefused, SystemExecutor, compile_plan, preflight, trust_handoff, verify_checkpoint,
)
from engcore.system_runtime.records import AuthorityRegistry, NodeReceipt
from engcore.system_runtime._common import digest_of
from tests import system_runtime_multiscale_fixtures as MSF
from tests.system_runtime_fixtures import UNKNOWN, Knobs, build, sha


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
# Genuine BIG 10 runtimes on the request's own scenario / timeline / environment (OD-28 refuses any other, and any stub).
MS_ENV, MS_SCN = MSF.environment()


def _multiscale_on_state(moisture_content):
    runtime = MSF.runtime(MS_ENV, cls=MSF.Counting)
    auth = MSF.authority(runtime, authority_id="ms-n2")                      # starts from moisture 0.0, drift 0.0
    request, context = MSF.request(MS_ENV, MS_SCN, auth, initial=MSF.initial_state(moisture_content=moisture_content))
    return request, context, runtime


def test_n2_a_multi_timescale_run_refuses_a_committed_state_other_than_the_one_it_starts_from():
    request, context, runtime = _multiscale_on_state(0.05)
    result = SystemExecutor(context).run(request)
    receipt = result.receipt("aging")
    assert receipt.status is NodeStatus.FAILED and "not the state this multi-timescale run starts from" in receipt.reason
    assert runtime.runs == 0
    request, context, runtime = _multiscale_on_state(0.0)                       # control: the same state is accepted
    assert SystemExecutor(context).run(request).receipt("aging").status is NodeStatus.SUCCEEDED
    assert runtime.runs == 1


# ------------------------------------------------------------------------------------------------ (c) resume source is declared
def test_c_a_resume_stage_must_name_and_depend_on_the_stage_it_continues():
    runtime = MSF.runtime(MS_ENV)
    _, context = MSF.request(MS_ENV, MS_SCN, MSF.authority(runtime, authority_id="ms-c0"))   # an authorized context for admission
    no_owners = {"initial_slow_state": {}, "extractors": {}, "slow_state_owners": {}}
    unnamed = MSF.authority(runtime, authority_id="ms-c1", stages={"b": {"until": None, "resume": True}}, **no_owners)
    assert [c for c, _ in unnamed.preflight_findings(SimpleNamespace(node_id="b", depends_on=("a",), visible_owners=()), context)] == ["INVALID_STAGE"]
    named = MSF.authority(runtime, authority_id="ms-c2", stages={"b": {"until": None, "resume": True, "from": "a"}}, **no_owners)
    assert named.identity_digest != unnamed.identity_digest
    assert "does not depend" in named.preflight_findings(SimpleNamespace(node_id="b", depends_on=(), visible_owners=()), context)[0][1]
    assert named.preflight_findings(SimpleNamespace(node_id="b", depends_on=("a",), visible_owners=()), context) == ()
    plain = MSF.authority(runtime, authority_id="ms-c3", stages={"a": {"until": None, "resume": False}}, **no_owners)
    assert plain.preflight_findings(SimpleNamespace(node_id="a", depends_on=(), visible_owners=()), context) == ()


def _staged(authority_id, **kw):
    """A genuine staged authority whose two nodes are named exactly 'a' (day 1, fresh) and 'b' (resume a to the end)."""
    runtime = MSF.runtime(MS_ENV, cls=MSF.Counting)
    auth = MSF.authority(runtime, authority_id=authority_id, stages={"a": {"until": MSF.until_day(MS_ENV, 1), "resume": False},
                                                                     "b": {"until": None, "resume": True, "from": "a"}}, **kw)
    request, context = MSF.request(MS_ENV, MS_SCN, auth, nodes=(MSF.node(auth, "a"), MSF.node(auth, "b", depends_on=("a",))))
    for node in compile_plan(request).nodes:                                    # admitted exactly as the executor's preflight admits them
        assert auth.preflight_findings(node, context) == ()
    return runtime, auth, request, context


def test_c_a_held_checkpoint_from_another_stage_or_restored_without_its_origin_is_not_resumed():
    runtime, auth, request, context = _staged("ms-c4")
    call = MSF.direct_call(request, context, "b")
    auth.restore({"checkpoint": {"stub": True}})                                   # a payload of unknown origin
    outcome = auth.execute(call)
    assert outcome.status == "failed" and "not from the stage 'a'" in outcome.reason
    auth.restored_from("x")                                                       # restored, but from another node
    assert auth.execute(call).status == "failed"
    auth.restored_from("a")                                                       # the right origin passes the gate (the forged
    with pytest.raises(InvalidScientificProblem, match="checkpoint payload"):     # payload then reaches MacroCheckpoint, which refuses it)
        auth.execute(call)
    assert runtime.resumes == 0


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


def _after_stage_a(authority_id):
    """A genuine staged authority after its stage 'a' ran (day 1) and was committed: it holds a real macro checkpoint."""
    runtime, auth, request, context = _staged(authority_id)
    first = auth.execute(MSF.direct_call(request, context, "a"))
    assert first.status == "succeeded", first.reason
    auth.committed(MSF.direct_call(request, context, "a"), first)
    return runtime, auth, request, context, MSF.slow_values(auth._last_checkpoint)


def test_n2_a_resume_stage_refuses_a_committed_state_other_than_the_one_its_checkpoint_continues():
    runtime, auth, request, context, (moisture, drift) = _after_stage_a("ms-n2r")
    for held, expected in ((moisture + 0.01, "failed"), (moisture, "succeeded")):  # another node moved the owner after stage a
        state = MSF.state_at(request, moisture_content=held, drift=drift)
        outcome = auth.execute(MSF.direct_call(request, context, "b", state=state))
        assert outcome.status == expected, outcome.reason
        assert expected == "succeeded" or "macro checkpoint continues from" in outcome.reason
    assert runtime.resumes == 1


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
                     literals=(LiteralInput("ambient", Quantity(293.15, "K"), UNKNOWN),), writes_owners=("cooler",), depends_on=("thermal",))
    from engcore.system_runtime import OwnerState
    initial = replace(request.initial_state, owners=request.initial_state.owners + (
        OwnerState("cooler", "component", (InitialStateValue("temperature", Quantity(300.0, "K"), UNKNOWN),)),))
    request = replace(request, nodes=request.nodes + (second,), initial_state=initial,
                      operational=replace(request.operational, resource_budget=ResourceBudget(max_wall_seconds=10.0)))
    result = SystemExecutor(context, clock=clock).run(request)
    assert result.receipt("thermal").status is NodeStatus.REFUSED and "wall-time budget" in result.receipt("thermal").reason
    assert result.receipt("thermal2").status is NodeStatus.BLOCKED and "thermal" in result.receipt("thermal2").reason


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


def test_n2_two_slow_owner_domains_are_compared_on_the_fresh_and_the_resume_path():
    """Re-review of this batch: the comparison loop shadowed its own argument, so a second domain raised instead of being compared.

    The genuine runtime has two slow domains (electrical -> heater_slow, thermal -> board_slow; compared in that order), so a
    perturbation of the SECOND one (board_slow) is what this regression must catch on both paths."""
    fresh_runtime = MSF.runtime(MS_ENV, cls=MSF.Counting)
    fresh = MSF.authority(fresh_runtime, authority_id="ms-2d")
    request, context = MSF.request(MS_ENV, MS_SCN, fresh)
    assert fresh.preflight_findings(compile_plan(request).nodes[0], context) == ()
    call = lambda request, node, **held: MSF.direct_call(request, context, node, state=MSF.state_at(request, **held))   # noqa: E731
    assert fresh.execute(call(request, "aging", moisture_content=0.0, drift=0.0)).status == "succeeded"
    out = fresh.execute(call(request, "aging", moisture_content=0.001, drift=0.0))
    assert out.status == "failed" and "board_slow.moisture_content" in out.reason
    _runtime, resume, staged_request, staged_context, (moisture, drift) = _after_stage_a("ms-2d-r")
    call = lambda held: MSF.direct_call(staged_request, staged_context, "b", state=MSF.state_at(staged_request, moisture_content=held, drift=drift))  # noqa: E731
    assert resume.execute(call(moisture)).status == "succeeded"
    out = resume.execute(call(moisture + 0.001))
    assert out.status == "failed" and "board_slow.moisture_content" in out.reason
