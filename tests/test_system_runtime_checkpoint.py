"""BIG 12 checkpoint / resume / replay (Gate E in the core environment) and their refusal semantics.

Agreement between a resumed and an uninterrupted run is reproducibility, never validation.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.units.quantity import Quantity
from engcore.system_runtime import (
    AuthorityRegistry, NodeAuthority, NodeOutcome, NodeStatus, OutputValue, ProviderBinding, ProviderRecordRef, ResumeRefused, RunStatus, SystemCheckpoint,
    SystemExecutor, compare_runs, compile_plan,
)
from engcore.system_runtime._common import digest_of
from tests.system_runtime_fixtures import UNKNOWN, Knobs, build, sha
from tests.test_system_runtime_executor import FakeProviders, _prov


def _paused(**kw):
    request, context, knobs = build(checkpoint_after=("thermal",), **kw)
    result = SystemExecutor(context).run(request, stop_after="thermal")
    return request, context, knobs, result


# ---------------------------------------------------------------------------------------------------------- Gate E
def test_gate_e_checkpoint_serialize_fresh_runtime_resume_finish_matches_the_uninterrupted_run():
    request, context, knobs, part1 = _paused()
    assert part1.status is RunStatus.PAUSED
    assert {r.node_id: r.status for r in part1.node_receipts}["report"] is NodeStatus.PENDING
    assert part1.observable("peak_temperature").availability.value == "unknown"          # not run yet, not failed
    wire = json.dumps(part1.checkpoints[-1].to_dict(), sort_keys=True)                    # serialize...
    checkpoint = SystemCheckpoint.from_dict(json.loads(wire))                             # ...and load into a "fresh process"
    assert checkpoint.digest == part1.checkpoints[-1].digest and checkpoint.complete
    assert checkpoint.classification == "checkpoint_reproducibility_not_validation"

    request2, context2, knobs2 = build(checkpoint_after=("thermal",))                    # a fresh runtime: new objects, new authorities
    resumed = SystemExecutor(context2).run(request2, resume=checkpoint)
    assert resumed.status is RunStatus.SUCCEEDED
    assert knobs2.calls == {"heat": 0, "thermal": 0, "report": 1}                         # completed nodes were NOT executed again

    request3, context3, knobs3 = build(checkpoint_after=("thermal",))
    uninterrupted = SystemExecutor(context3).run(request3)
    comparison = compare_runs(uninterrupted, resumed, rel_tol=0.0)
    assert comparison.identity_replay and comparison.bitwise_identical and comparison.numerical_reproducibility
    assert comparison.classification == "reproducibility_not_validation" and comparison.scientific_validation == "not_assessed"
    assert resumed.scientific_digest == uninterrupted.scientific_digest
    assert [s.digest for s in resumed.state_history] == [s.digest for s in uninterrupted.state_history]


def test_a_checkpoint_only_holds_succeeded_nodes_and_is_bound_to_the_run_that_made_it():
    request, context, knobs, part1 = _paused()
    cp = part1.checkpoints[-1]
    assert {r.node_id for r in cp.completed_receipts} == {"env.thermal.ambient", "heat", "mat.thermal.k", "thermal"}
    assert cp.run_id == part1.run_id and cp.state.digest == part1.final_state.digest
    request2, context2, _ = build(checkpoint_after=("thermal",))
    with pytest.raises(InvalidScientificProblem, match="keeps the run id"):
        SystemExecutor(context2).run(request2, resume=cp, run_id="a-different-run")


# ---------------------------------------------------------------------------------------------------------- refusals
def _resume_into(request, context, checkpoint, **kw):
    return SystemExecutor(context).run(request, resume=checkpoint, **kw)


def test_resume_refuses_every_change_to_what_the_run_means():
    request, context, knobs, part1 = _paused()
    cp = part1.checkpoints[-1]
    changes = {
        "the request changed": dict(initial_temperature=310.0),
        "the plan changed": None,
        "scenario changed": dict(scn_version="2"),
        "material": dict(conductivity=17.0),
        "environment changed": dict(ambient=(293.15, 297.15)),
    }
    for expected, kw in changes.items():
        if kw is None:
            continue
        r2, c2, _ = build(checkpoint_after=("thermal",), **kw)
        with pytest.raises(ResumeRefused, match="checkpoint refused"):
            _resume_into(r2, c2, cp)
    # a different plan for the SAME request is a different plan
    r3, c3, _ = build(checkpoint_after=("thermal",))
    swapped = _resume_into(r3, c3, cp, plan=replace(compile_plan(r3), allow_partial=False))
    assert swapped.status is RunStatus.REFUSED and "PLAN_REQUEST_MISMATCH" in swapped.preflight.codes()      # refused before anything resumes
    with pytest.raises(ResumeRefused, match="the plan changed"):
        from engcore.system_runtime import verify_checkpoint
        verify_checkpoint(cp, r3, replace(compile_plan(r3), allow_partial=False), (), c3)
    # an authority (provider) identity change
    r4, c4, _ = build(checkpoint_after=("thermal",), knobs=Knobs(volts=3.8))
    with pytest.raises(ResumeRefused, match="request changed|authority"):
        _resume_into(r4, c4, cp)


def test_resume_refuses_a_provider_build_change_that_leaves_the_request_unchanged():
    def with_provider(digest):
        ref = ProviderRecordRef("pybamm", "26.8", digest, sha("identity"), sha("record"), True)
        request, context, knobs = build(checkpoint_after=("thermal",), knobs=Knobs(provider_ref=ref))
        thermal = replace(next(n for n in request.nodes if n.node_id == "thermal"), provider_binding_ids=("b",))
        request = replace(request, nodes=tuple(thermal if n.node_id == "thermal" else n for n in request.nodes),
                          provider_bindings=(ProviderBinding("b", "pybamm", "26.8"),))
        context.providers = FakeProviders(pybamm=_prov(digest=digest))
        return request, context
    request, context = with_provider(sha("build-1"))
    part1 = SystemExecutor(context).run(request, stop_after="thermal")
    cp = part1.checkpoints[-1]
    assert cp.complete
    same_request, changed_context = with_provider(sha("build-2"))
    assert same_request.digest == request.digest
    with pytest.raises(ResumeRefused, match="provider:pybamm changed"):
        _resume_into(same_request, changed_context, cp)
    # ...and the unchanged provider resumes fine
    ok_request, ok_context = with_provider(sha("build-1"))
    assert _resume_into(ok_request, ok_context, cp).status is RunStatus.SUCCEEDED


class Counting(NodeAuthority):
    """A stateful authority that CAN declare its state: it must be restored on resume."""
    authority_id, kind = "counter-auth", "callback"
    identity_digest = sha("counter-auth-identity")
    supports_checkpoint = True
    stateless = False
    deterministic = False

    def __init__(self):
        self.n = 0
        self.restored = None

    def execute(self, call):
        self.n += 1
        return NodeOutcome("succeeded", {"power": OutputValue(Quantity(37.0, "W"), UNKNOWN, "counter")}, authority_checkpoint=(digest_of({"n": self.n}), True))

    def checkpoint_payload(self):
        return {"n": self.n}

    def restore(self, payload):
        self.restored = dict(payload)
        self.n = payload["n"]


class Incomplete(Counting):
    """Holds state and says, honestly, that the checkpoint it can offer is NOT complete."""
    authority_id, identity_digest = "incomplete-auth", sha("incomplete-auth-identity")

    def execute(self, call):
        self.n += 1
        return NodeOutcome("succeeded", {"power": OutputValue(Quantity(37.0, "W"), UNKNOWN, "incomplete")}, authority_checkpoint=(digest_of({"n": self.n}), False))


def _with_authority(authority, node_id="heat", **build_kw):
    from engcore.system_runtime import AuthorityRef
    request, context, knobs = build(checkpoint_after=("thermal",), **build_kw)
    ref = AuthorityRef(authority.authority_id, authority.kind, authority.identity_digest)
    node = replace(next(n for n in request.nodes if n.node_id == node_id), authority=ref, checkpointable=True)
    request = replace(request, nodes=tuple(node if n.node_id == node_id else n for n in request.nodes))
    context.authorities.register(authority)
    return request, context


def test_resume_refuses_an_incomplete_checkpoint_where_a_participant_did_not_declare_its_state():
    request, context = _with_authority(Incomplete())
    part1 = SystemExecutor(context).run(request, stop_after="thermal")
    cp = part1.checkpoints[-1]
    assert not cp.complete and "did not declare its state complete" in cp.incomplete_reason
    request2, context2 = _with_authority(Incomplete())
    with pytest.raises(ResumeRefused, match="incomplete"):
        _resume_into(request2, context2, cp)


def test_a_tampered_checkpoint_is_refused():
    request, context, knobs, part1 = _paused()
    cp = part1.checkpoints[-1]
    wire = json.loads(json.dumps(cp.to_dict()))
    wire["outputs"]["heat"]["power"]["value"]["magnitude"] = 1.0
    with pytest.raises(InvalidScientificProblem, match="do not match its receipt"):
        SystemCheckpoint.from_dict(wire)
    wire = json.loads(json.dumps(cp.to_dict()))
    wire["state_history"][1]["previous_digest"] = "0" * 64
    with pytest.raises(InvalidScientificProblem, match="digest chain|last of its state history"):
        SystemCheckpoint.from_dict(wire)
    wire = json.loads(json.dumps(cp.to_dict()))
    wire["completed_receipts"][0]["status"] = "failed"
    with pytest.raises(InvalidScientificProblem, match="only SUCCEEDED"):
        SystemCheckpoint.from_dict(wire)
    wire = json.loads(json.dumps(cp.to_dict()))
    wire["classification"] = "validated"
    with pytest.raises(InvalidScientificProblem, match="reproducibility, never validation"):
        SystemCheckpoint.from_dict(wire)
    # a checkpoint whose recorded context digest was edited no longer matches the context it is resumed into
    wire = json.loads(json.dumps(cp.to_dict()))
    wire["context_digests"] = [[k, sha("x") if k == "system" else v] for k, v in wire["context_digests"]]
    edited = SystemCheckpoint.from_dict(wire)
    request2, context2, _ = build(checkpoint_after=("thermal",))
    with pytest.raises(ResumeRefused, match="system changed"):
        _resume_into(request2, context2, edited)
    # a receipt whose node definition changed
    wire = json.loads(json.dumps(cp.to_dict()))
    wire["completed_receipts"][2]["node_digest"] = sha("another definition")
    with pytest.raises(Exception):
        _resume_into(request2, context2, SystemCheckpoint.from_dict(wire))


def test_a_checkpoint_after_a_node_that_cannot_declare_its_state_is_refused_up_front():
    request, context, knobs = build(checkpoint_after=("thermal",))
    authority = context.authorities._items["thermal-auth"]
    authority.supports_checkpoint, authority.stateless = False, False     # it holds state it cannot declare
    from engcore.system_runtime import preflight
    assert "CHECKPOINT_IMPOSSIBLE" in preflight(request, compile_plan(request), context).codes()


# ---------------------------------------------------------------------------------------------------------- authority state
def test_an_authority_that_declares_its_state_is_checkpointed_and_restored():
    counter = Counting()
    request, context = _with_authority(counter)
    part1 = SystemExecutor(context).run(request, stop_after="thermal")
    cp = part1.checkpoints[-1]
    assert cp.complete and next(a for a in cp.authority_checkpoints if a.node_id == "heat").payload == {"n": 1}
    fresh = Counting()
    context2 = build(checkpoint_after=("thermal",))[1]
    context2.authorities.register(fresh)
    resumed = SystemExecutor(context2).run(request, resume=SystemCheckpoint.from_dict(json.loads(json.dumps(cp.to_dict()))))
    assert resumed.status is RunStatus.SUCCEEDED and fresh.restored == {"n": 1} and fresh.n == 1     # restored, and not executed again


# ---------------------------------------------------------------------------------------------------------- replay
def test_exact_identity_replay_numerical_reproducibility_and_validation_are_three_separate_claims():
    r1, c1, _ = build()
    r2, c2, _ = build()
    a, b = SystemExecutor(c1).run(r1), SystemExecutor(c2).run(r2)
    cmp = compare_runs(a, b, rel_tol=0.0)
    assert cmp.identity_replay and cmp.identity_differences == () and cmp.bitwise_identical and cmp.numerical_reproducibility
    assert cmp.scientific_validation == "not_assessed" and cmp.classification == "reproducibility_not_validation"
    assert a.scientific_digest == b.scientific_digest and a.digest != "" and cmp.to_dict()["scientific_validation"] == "not_assessed"


def test_a_numerical_difference_is_judged_only_against_a_declared_tolerance():
    a = SystemExecutor(build()[1]).run(build()[0])
    request, context, _ = build(knobs=Knobs(thermal_gain=0.0501))
    # same request digest would differ (authority config): compare the numbers of two runs of DIFFERENT setups explicitly
    b = SystemExecutor(context).run(request)
    cmp = compare_runs(a, b, rel_tol=1e-6)
    assert not cmp.identity_replay and "request digest" in cmp.identity_differences
    assert not cmp.numerical_reproducibility and not cmp.bitwise_identical
    loose = compare_runs(a, b, rel_tol=1e-2)
    assert loose.numerical_reproducibility and not loose.bitwise_identical       # within tolerance, but still not identical
    with pytest.raises(InvalidScientificProblem, match="declared"):
        compare_runs(a, b, rel_tol=-1.0)


def test_a_run_comparison_can_never_claim_validation():
    from engcore.system_runtime import RunComparison
    with pytest.raises(InvalidScientificProblem, match="never assesses validation"):
        RunComparison(True, (), True, True, (), (), scientific_validation="validated")
