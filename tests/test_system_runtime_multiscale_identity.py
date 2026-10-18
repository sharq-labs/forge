"""OD-28: a multi-timescale node executes only under the scenario, timeline and environment its system call authorizes.

``MultiscaleAuthority`` used to carry ``runtime.identities()`` in its own identity but never compared the scenario /
timeline / environment digests in it with the call's context, so a node built on another scenario's environment could
run, expose outputs and commit slow state inside a request for a different scenario. Every runtime here is a genuine
BIG 10 ``MultiTimescaleRuntime`` over the heater/board reference system (a genuine BIG 9 coupled fast system per resolved
day); the adversaries are subclasses that substitute identity -- never stand-in record types.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from engcore.multiscale import MacroCheckpoint
from engcore.scientific.units.quantity import Quantity
from engcore.system_runtime import (
    ApplicabilityReport,
    CallbackAuthority,
    LiteralInput,
    NodeKind,
    NodeOutcome,
    NodeOutputSpec,
    NodeSpec,
    NodeStatus,
    OutputValue,
    RunStatus,
    SystemCheckpoint,
    SystemExecutor,
    compile_plan,
)
from tests import system_runtime_multiscale_fixtures as F
from tests.system_runtime_fixtures import UNKNOWN, sha

ENV, SCN = F.environment()
ENV_SCENARIO, SCN_OTHER = F.environment(scenario_version="2")      # another scenario; same horizon, history and initial state
ENV_TIMELINE, _ = F.environment(daily_rise=0.5)                    # same scenario, another chamber history -> another timeline
ENV_SOURCE, _ = F.environment(source_note="re-declared chamber program (other issuer)")   # same timeline, another environment
assert SCN_OTHER.digest != SCN.digest and ENV_TIMELINE.timeline.scenario_digest == SCN.digest
assert ENV_TIMELINE.timeline.digest != ENV.timeline.digest and ENV_SOURCE.timeline.digest == ENV.timeline.digest != ""
assert ENV_SOURCE.digest != ENV.digest


Counting = F.Counting


class Spies:
    """Callbacks that must never be reached when identity refuses."""

    def __init__(self):
        self.calls = {"extract": 0, "applicability": 0, "providers": 0}

    def extractors(self):
        def moisture(record):
            self.calls["extract"] += 1
            return F.moisture(record)
        def days(record):
            self.calls["extract"] += 1
            return F.represented_days(record)
        return {"moisture": moisture, "represented_days": days}

    def applicability(self, record, call):
        self.calls["applicability"] += 1
        return ()

    def providers(self, record):
        self.calls["providers"] += 1
        return ()                      # the request binds no provider; the call itself is what a refusal must never reach


def kit(runtime_env=ENV, *, cls=Counting, staged=False, spies=None, run_id="ms-identity", **auth_kwargs):
    rt = F.runtime(runtime_env, cls=cls, run_id=run_id)
    if spies is not None:
        auth_kwargs = dict(extractors=spies.extractors(), applicability=spies.applicability, providers=spies.providers, **auth_kwargs)
    auth = F.authority(rt, staged_env=runtime_env if staged else None, **auth_kwargs)
    return rt, auth


def codes(result):
    return sorted({f.code for f in result.preflight.blocking})


def assert_nothing_released(result, node_id, auth=None, spies=None):
    """A refused node exposes no output, commits no state, reports no evidence and promotes no checkpoint."""
    assert node_id not in result.node_outputs
    assert len(result.state_history) <= 1 and (result.final_state is None or result.final_state.sequence == 0)
    assert result.provider_records == ()
    for obs in result.observables:
        assert obs.value is None
    if result.node_receipts:
        receipt = result.receipt(node_id)
        assert receipt.status is not NodeStatus.SUCCEEDED and receipt.provider_records == () and receipt.applicability == ()
        assert receipt.output_digests == ()
    if auth is not None:
        assert auth._pending_checkpoint is None
    if spies is not None:
        assert spies.calls == {"extract": 0, "applicability": 0, "providers": 0}, spies.calls


direct_call = F.direct_call


def mutator(fn, *, depends_target):
    """A node that runs before ``depends_target`` and changes shared objects when it executes (after preflight)."""
    def execute(call):
        fn(call)
        return NodeOutcome("succeeded", {"done": OutputValue(Quantity(1.0, "dimensionless"), UNKNOWN, "mutator")})
    auth = CallbackAuthority("mutator", execute, config={"role": "changes shared objects after preflight"})
    node = NodeSpec("mutator", NodeKind.NUMERICAL_EXECUTION, auth.ref, (NodeOutputSpec("done", "dimensionless"),),
                    literals=(LiteralInput("x", Quantity(1.0, "dimensionless"), UNKNOWN),))
    return auth, node


# ---------------------------------------------------------------------------------------------------- A1 correct admission
def test_a1_a_runtime_bound_to_the_authorized_context_is_admitted_runs_and_commits():
    spies = Spies()
    rt, auth = kit(spies=spies)
    request, context = F.request(ENV, SCN, auth)
    plan_node = compile_plan(request).nodes[0]
    assert auth.preflight_findings(plan_node, context) == ()
    result = SystemExecutor(context).run(request)
    assert result.status is RunStatus.SUCCEEDED, [(r.node_id, r.reason) for r in result.node_receipts]
    moisture = result.observable("moisture").value.value.magnitude
    assert moisture > 0 and result.final_state.owner("board_slow").values[0].value.magnitude == pytest.approx(moisture)
    assert rt.runs == 1 and spies.calls["extract"] == 2 and spies.calls["applicability"] == 1 and spies.calls["providers"] == 1


def test_a1_staged_stages_on_the_authorized_context_resume_in_process():
    rt, auth = kit(staged=True)
    request, context = F.request(ENV, SCN, auth, staged=True)
    result = SystemExecutor(context).run(request)
    assert result.status is RunStatus.SUCCEEDED, [(r.node_id, r.reason) for r in result.node_receipts]
    assert (rt.runs, rt.resumes) == (1, 1)
    _, full = kit()
    full_request, full_context = F.request(ENV, SCN, full)
    full_result = SystemExecutor(full_context).run(full_request)
    assert result.observable("moisture").value.value.magnitude == pytest.approx(full_result.observable("moisture").value.value.magnitude,
                                                                                rel=1e-12)


# ---------------------------------------------------------------------------------------------------- A2-A4 other context
@pytest.mark.parametrize("runtime_env, named", [(ENV_SCENARIO, "scenario"), (ENV_TIMELINE, "timeline"), (ENV_SOURCE, "environment")],
                         ids=["other-scenario-identical-state", "other-timeline-same-scenario", "other-environment-same-timeline"])
def test_a2_a4_a_runtime_bound_to_another_context_is_refused_at_preflight_and_never_runs(runtime_env, named):
    spies = Spies()
    rt, auth = kit(runtime_env, spies=spies)
    request, context = F.request(ENV, SCN, auth)                    # the request is for ENV/SCN; the runtime is bound elsewhere
    result = SystemExecutor(context).run(request)
    assert result.status is RunStatus.REFUSED and codes(result) == ["MULTISCALE_IDENTITY_MISMATCH"]
    message = next(f.message for f in result.preflight.blocking if f.code == "MULTISCALE_IDENTITY_MISMATCH")
    assert named in message
    assert rt.runs == 0
    assert_nothing_released(result, "aging", auth, spies)


def test_a2_identical_initial_state_time_unit_and_model_names_do_not_stand_in_for_scenario_identity():
    _rt, auth = kit(ENV_SCENARIO)
    # the two runs are physically indistinguishable: same horizon, chamber history, slow state, units and model ids
    other = F.runtime(ENV_SCENARIO).run(initial_slow_state=F.R.initial_slow())
    mine = F.runtime(ENV).run(initial_slow_state=F.R.initial_slow())
    assert F.moisture(other) == F.moisture(mine) and other.reached == mine.reached
    request, context = F.request(ENV, SCN, auth)
    plan_node = compile_plan(request).nodes[0]
    assert [c for c, _ in auth.preflight_findings(plan_node, context)] == ["MULTISCALE_IDENTITY_MISMATCH"]


# ---------------------------------------------------------------------------------------------------- A5 missing identity
def test_a5_a_request_without_an_environment_cannot_admit_a_runtime_that_is_bound_to_one():
    rt, auth = kit()
    request, context = F.request(ENV, SCN, auth, with_environment=False)
    result = SystemExecutor(context).run(request)
    assert result.status is RunStatus.REFUSED and "MULTISCALE_IDENTITY_MISSING" in codes(result)
    assert rt.runs == 0
    assert_nothing_released(result, "aging", auth)


class DropsEnvironment(Counting):
    """A runtime whose identity omits the environment digest (its records then omit it too)."""

    def identities(self):
        ids = super().identities()
        ids.pop("environment")
        return ids


def test_a5_a_runtime_whose_identity_omits_a_bound_key_is_refused_never_inferred():
    rt, auth = kit(cls=DropsEnvironment)
    request, context = F.request(ENV, SCN, auth)
    result = SystemExecutor(context).run(request)
    assert result.status is RunStatus.REFUSED and codes(result) == ["MULTISCALE_IDENTITY_MISSING"]
    assert "environment" in result.preflight.blocking[0].message
    assert rt.runs == 0


# ---------------------------------------------------------------------------------------------------- A6/A7 changed identity
def test_a6_a_runtime_rebound_after_the_authority_was_constructed_is_refused_at_preflight():
    rt, auth = kit()
    rt.environment, rt.timeline = ENV_SOURCE, ENV_SOURCE.timeline              # rebound after construction
    request, context = F.request(ENV, SCN, auth)
    result = SystemExecutor(context).run(request)
    assert result.status is RunStatus.REFUSED and "MULTISCALE_RUNTIME_CHANGED" in codes(result)
    assert rt.runs == 0
    # also a structural change that leaves scenario/timeline/environment alone
    rt2, auth2 = kit()
    rt2.policy = F.R.policy(default_days=2, near_threshold=False)
    request2, context2 = F.request(ENV, SCN, auth2)
    result2 = SystemExecutor(context2).run(request2)
    assert result2.status is RunStatus.REFUSED and codes(result2) == ["MULTISCALE_RUNTIME_CHANGED"] and "policy" in result2.preflight.blocking[0].message


def test_a7_a_runtime_rebound_after_preflight_is_refused_before_it_runs():
    spies = Spies()
    rt, auth = kit(spies=spies)

    def rebind(call):
        rt.environment, rt.timeline = ENV_SOURCE, ENV_SOURCE.timeline
    mut, mut_node = mutator(rebind, depends_target="aging")
    request, context = F.request(ENV, SCN, auth, nodes=(mut_node, F.node(auth, depends_on=("mutator",))), extra_authorities=(mut,))
    result = SystemExecutor(context).run(request)
    receipt = result.receipt("aging")
    assert result.preflight.status.value != "refused"
    assert receipt.status is NodeStatus.FAILED and "changed since" in receipt.reason, receipt.reason
    assert rt.runs == 0
    assert_nothing_released(result, "aging", auth, spies)


def test_a7_a_context_swapped_after_preflight_is_refused_even_when_the_runtime_is_swapped_consistently():
    spies = Spies()
    rt, auth = kit(spies=spies)

    def swap(call):        # the context and the runtime both move to ENV_SCENARIO: consistent with each other, not with the request
        call.context.scenario, call.context.timeline, call.context.environment = SCN_OTHER, ENV_SCENARIO.timeline, ENV_SCENARIO
        rt.environment, rt.timeline = ENV_SCENARIO, ENV_SCENARIO.timeline
    mut, mut_node = mutator(swap, depends_target="aging")
    request, context = F.request(ENV, SCN, auth, nodes=(mut_node, F.node(auth, depends_on=("mutator",))), extra_authorities=(mut,))
    result = SystemExecutor(context).run(request)
    receipt = result.receipt("aging")
    assert receipt.status is NodeStatus.FAILED and "admitted at preflight" in receipt.reason, receipt.reason
    assert rt.runs == 0
    assert_nothing_released(result, "aging", auth, spies)


def test_a7_execute_without_preflight_admission_is_refused():
    rt, auth = kit()
    request, context = F.request(ENV, SCN, auth)
    outcome = auth.execute(direct_call(request, context, "aging"))
    assert outcome.status == "failed" and "not admitted" in outcome.reason
    assert rt.runs == 0 and outcome.outputs == {} and outcome.state_proposal is None
    assert auth.preflight_findings(compile_plan(request).nodes[0], context) == ()          # control: admitted, then it runs
    assert auth.execute(direct_call(request, context, "aging")).status == "succeeded" and rt.runs == 1


def test_a7_a_failed_admission_withdraws_an_earlier_one():
    rt, auth = kit()
    request, context = F.request(ENV, SCN, auth)
    plan_node = compile_plan(request).nodes[0]
    assert auth.preflight_findings(plan_node, context) == ()
    _, other_context = F.request(ENV_SOURCE, SCN, auth)
    assert [c for c, _ in auth.preflight_findings(plan_node, other_context)] == ["MULTISCALE_IDENTITY_MISMATCH"]
    outcome = auth.execute(direct_call(request, context, "aging"))                         # the earlier admission does not survive
    assert outcome.status == "failed" and "not admitted" in outcome.reason and rt.runs == 0


# ---------------------------------------------------------------------------------------------------- A8 substituted records
class Substituting(Counting):
    """Runs, then hands back a genuine record of another genuine run bound to another scenario (same run id)."""

    def run(self, **kw):
        super().run(**kw)
        return F.runtime(ENV_SCENARIO, run_id=self.run_id).run(**kw)


class Rewriting(Counting):
    """Runs, then hands back its own genuine record with one bound identity rewritten (the digest field is recomputed)."""

    key, value = "environment", ENV_SOURCE.digest

    def run(self, **kw):
        record = super().run(**kw)
        return replace(record, identities={**record.identities, self.key: self.value})


class RewritingToRuntime(Counting):
    """Rewrites the record AND reports the rewritten identity itself after the run (record == runtime, but not authorized)."""

    def run(self, **kw):
        record = super().run(**kw)
        self.environment, self.timeline = ENV_SOURCE, ENV_SOURCE.timeline
        return replace(record, identities=self.identities())


@pytest.mark.parametrize("cls, expected", [(Substituting, "scenario"), (Rewriting, "environment"), (RewritingToRuntime, "environment")],
                         ids=["substituted-record", "rewritten-record", "record-and-runtime-rebound-during-run"])
def test_a8_a_returned_record_bound_to_another_context_is_refused_before_any_output(cls, expected):
    spies = Spies()
    rt, auth = kit(cls=cls, spies=spies)
    request, context = F.request(ENV, SCN, auth)
    result = SystemExecutor(context).run(request)
    receipt = result.receipt("aging")
    assert receipt.status is NodeStatus.FAILED and expected in receipt.reason, receipt.reason
    assert rt.runs == 1
    assert_nothing_released(result, "aging", auth, spies)


class OtherRunId(Counting):
    def run(self, **kw):
        record = super().run(**kw)
        return replace(record, run_id="someone-else")


def test_a8_a_record_of_another_run_id_is_refused():
    spies = Spies()
    _rt, auth = kit(cls=OtherRunId, spies=spies)
    request, context = F.request(ENV, SCN, auth)
    result = SystemExecutor(context).run(request)
    assert result.receipt("aging").status is NodeStatus.FAILED and "run" in result.receipt("aging").reason
    assert_nothing_released(result, "aging", auth, spies)


class CheckpointElsewhere(Counting):
    """Returns its own record but with a last checkpoint taken from a run bound to another environment."""

    def run(self, **kw):
        record = super().run(**kw)
        foreign = F.runtime(ENV_SOURCE, run_id=self.run_id).run(**kw).checkpoints
        return replace(record, checkpoints=record.checkpoints[:-1] + foreign[-1:])


def test_a8_a_record_carrying_a_checkpoint_of_another_context_is_refused_and_the_checkpoint_never_held():
    spies = Spies()
    _rt, auth = kit(cls=CheckpointElsewhere, spies=spies)
    request, context = F.request(ENV, SCN, auth)
    result = SystemExecutor(context).run(request)
    assert result.receipt("aging").status is NodeStatus.FAILED and "checkpoint" in result.receipt("aging").reason
    assert auth._last_checkpoint is None
    assert_nothing_released(result, "aging", auth, spies)


# ---------------------------------------------------------------------------------------------------- A9 foreign checkpoint
@pytest.mark.parametrize("foreign_env, named", [(ENV_TIMELINE, "timeline"), (ENV_SOURCE, "environment")],
                         ids=["checkpoint-other-timeline", "checkpoint-other-environment"])
def test_a9_a_restored_checkpoint_from_another_timeline_or_environment_is_refused_before_resume(foreign_env, named):
    spies = Spies()
    rt, auth = kit(staged=True, spies=spies)
    request, context = F.request(ENV, SCN, auth, staged=True)
    foreign = F.runtime(foreign_env, run_id=rt.run_id).run(initial_slow_state=F.R.initial_slow(), until=F.until_day(foreign_env, 1))
    payload = json.loads(json.dumps(foreign.last_valid_checkpoint.serialize()))
    plan = compile_plan(request)
    assert auth.preflight_findings(next(n for n in plan.nodes if n.node_id == "aging_b"), context) == ()
    auth.restore(payload)
    auth.restored_from("aging_a")
    outcome = auth.execute(direct_call(request, context, "aging_b"))
    assert outcome.status == "failed" and "checkpoint" in outcome.reason and named in outcome.reason, outcome.reason
    assert rt.resumes == 0 and outcome.outputs == {} and outcome.state_proposal is None and outcome.provider_records == ()
    assert auth._pending_checkpoint is None and auth._last_checkpoint == payload            # the refused resume releases nothing
    assert spies.calls == {"extract": 0, "applicability": 0, "providers": 0}


# ---------------------------------------------------------------------------------------------------- A10 unrelated execution
def test_a10_a_held_checkpoint_is_resumed_only_for_the_execution_that_produced_it():
    rt, auth = kit(staged=True)
    request, context = F.request(ENV, SCN, auth, staged=True)
    part1 = SystemExecutor(context).run(request, stop_after="aging_a")
    assert part1.status is RunStatus.PAUSED and auth._last_checkpoint is not None
    held = dict(auth._last_checkpoint)
    plan_b = next(n for n in compile_plan(request).nodes if n.node_id == "aging_b")
    after_a = part1.final_state
    # an unrelated execution: another request on the same scenario/timeline/environment, never resumed by the executor
    unrelated, _ = F.request(ENV, SCN, auth, staged=True, initial=F.initial_state(moisture_content=0.001))
    assert unrelated.digest != request.digest
    assert auth.preflight_findings(plan_b, context) == ()
    outcome = auth.execute(direct_call(request, context, "aging_b", state=after_a, request_digest=unrelated.digest))
    assert outcome.status == "failed" and "another" in outcome.reason and "request" in outcome.reason, outcome.reason
    assert rt.resumes == 0 and outcome.outputs == {} and auth._last_checkpoint == held and auth._pending_checkpoint is None
    # control: the execution that produced it continues
    ok = auth.execute(direct_call(request, context, "aging_b", state=after_a, run_id=part1.run_id))
    assert ok.status == "succeeded", ok.reason
    assert rt.resumes == 1


# ---------------------------------------------------------------------------------------------------- A12 valid executor resume
def test_a12_an_executor_checkpoint_resumes_on_a_fresh_runtime_under_the_same_context():
    _rt, auth = kit(staged=True)
    request, context = F.request(ENV, SCN, auth, staged=True)
    part1 = SystemExecutor(context).run(request, stop_after="aging_a")
    checkpoint = SystemCheckpoint.from_dict(json.loads(json.dumps(part1.checkpoints[-1].to_dict(), sort_keys=True)))
    rt2, auth2 = kit(staged=True)                                                   # fresh objects across the process boundary
    request2, context2 = F.request(ENV, SCN, auth2, staged=True)
    assert request2.digest == request.digest
    resumed = SystemExecutor(context2).run(request2, resume=checkpoint)
    assert resumed.status is RunStatus.SUCCEEDED, [(r.node_id, r.reason) for r in resumed.node_receipts]
    assert (rt2.runs, rt2.resumes) == (0, 1)
    _, full = kit()
    full_request, full_context = F.request(ENV, SCN, full)
    expected = SystemExecutor(full_context).run(full_request).observable("moisture").value.value.magnitude
    assert resumed.observable("moisture").value.value.magnitude == pytest.approx(expected, rel=1e-12)


def test_a12_the_macro_checkpoint_carried_by_an_admitted_run_is_bound_to_the_authorized_context():
    _rt, auth = kit(staged=True)
    request, context = F.request(ENV, SCN, auth, staged=True)
    part1 = SystemExecutor(context).run(request, stop_after="aging_a")
    payload = next(a for a in part1.checkpoints[-1].authority_checkpoints if a.node_id == "aging_a").payload
    cp = MacroCheckpoint.deserialize(payload)
    assert {k: cp.identities[k] for k in ("scenario", "timeline", "environment")} == {
        "scenario": SCN.digest, "timeline": ENV.timeline.digest, "environment": ENV.digest}


def test_applicability_reports_from_an_admitted_run_still_gate_the_commit():
    """Unchanged path: identity admission does not replace the runtime applicability gate."""
    outside = lambda record, call: (ApplicabilityReport("bounds", "outside", sha("e"), "left"),)
    _rt, auth = kit(applicability=outside)
    request, context = F.request(ENV, SCN, auth, nodes=(replace(F.node(auth), applicability_waiver="", applicability_checks=("bounds",)),))
    result = SystemExecutor(context).run(request)
    assert result.receipt("aging").status is NodeStatus.REFUSED and len(result.state_history) == 1


# ---------------------------------------------------------------------------------------------------- review follow-ups
class _Wrap:
    """Forwards every attribute to a genuine record except ``last_valid_checkpoint`` (taken from another context)."""

    def __init__(self, record, foreign):
        self._record, self.last_valid_checkpoint = record, foreign

    def __getattr__(self, name):
        return getattr(self._record, name)


class WrapsRecord(Counting):
    def run(self, **kw):
        record = super().run(**kw)
        return _Wrap(record, F.runtime(ENV_SOURCE, run_id=self.run_id).run(**kw).checkpoints[-1])


def test_review_m1_a_record_lookalike_whose_last_checkpoint_resolves_elsewhere_is_refused():
    spies = Spies()
    _rt, auth = kit(cls=WrapsRecord, spies=spies)
    request, context = F.request(ENV, SCN, auth)
    result = SystemExecutor(context).run(request)
    assert result.receipt("aging").status is NodeStatus.FAILED and "MultiTimescaleRunRecord" in result.receipt("aging").reason
    assert auth._last_checkpoint is None and auth._last_binding is None
    assert_nothing_released(result, "aging", auth, spies)


class OverridesLastCheckpoint(Counting):
    """A genuine record subclass whose ``last_valid_checkpoint`` property points at another context's checkpoint."""

    def run(self, **kw):
        from dataclasses import fields

        from engcore.multiscale.runtime import MultiTimescaleRunRecord

        class ForeignLast(MultiTimescaleRunRecord):
            foreign = None

            @property
            def last_valid_checkpoint(self):
                return self.foreign

        record = super().run(**kw)
        forged = ForeignLast(**{f.name: getattr(record, f.name) for f in fields(record)})
        forged.foreign = F.runtime(ENV_SOURCE, run_id=self.run_id).run(**kw).checkpoints[-1]
        return forged


def test_review_m1_a_record_subclass_that_overrides_its_last_checkpoint_is_refused():
    spies = Spies()
    _rt, auth = kit(cls=OverridesLastCheckpoint, spies=spies)
    request, context = F.request(ENV, SCN, auth)
    result = SystemExecutor(context).run(request)
    assert result.receipt("aging").status is NodeStatus.FAILED and "MultiTimescaleRunRecord" in result.receipt("aging").reason
    assert auth._last_checkpoint is None and auth._last_binding is None
    assert_nothing_released(result, "aging", auth, spies)


class _Masquerade:
    """Reports a genuine checkpoint's run id / identities but serializes another context's checkpoint."""

    def __init__(self, genuine, foreign):
        self._genuine, self._foreign = genuine, foreign

    def __getattr__(self, name):
        return getattr(self._genuine, name)

    def serialize(self):
        return self._foreign.serialize()


class MasqueradingCheckpoint(Counting):
    def run(self, **kw):
        record = super().run(**kw)
        foreign = F.runtime(ENV_SOURCE, run_id=self.run_id).run(**kw).checkpoints[-1]
        return replace(record, checkpoints=record.checkpoints[:-1] + (_Masquerade(record.checkpoints[-1], foreign),))


class SerializesElsewhere(Counting):
    """A genuine MacroCheckpoint subclass whose payload is another context's."""

    def run(self, **kw):
        from dataclasses import fields

        record = super().run(**kw)
        foreign = F.runtime(ENV_SOURCE, run_id=self.run_id).run(**kw).checkpoints[-1]

        class Forged(MacroCheckpoint):
            def serialize(self):
                return foreign.serialize()

        last = record.checkpoints[-1]
        return replace(record, checkpoints=record.checkpoints[:-1] + (Forged(**{f.name: getattr(last, f.name) for f in fields(last)}),))


@pytest.mark.parametrize("cls", [MasqueradingCheckpoint, SerializesElsewhere], ids=["look-alike-checkpoint", "checkpoint-subclass"])
def test_review_m1b_the_held_payload_must_be_the_checkpoint_that_was_verified(cls):
    spies = Spies()
    _rt, auth = kit(cls=cls, spies=spies)
    request, context = F.request(ENV, SCN, auth)
    result = SystemExecutor(context).run(request)
    assert result.receipt("aging").status is NodeStatus.FAILED and "checkpoint" in result.receipt("aging").reason
    assert auth._last_checkpoint is None and auth._last_binding is None
    assert_nothing_released(result, "aging", auth, spies)


def test_review_a_runtime_that_starts_lying_after_preflight_is_refused_before_it_runs():
    spies = Spies()
    rt, auth = kit(cls=LiesAfterPreflight, spies=spies)

    def rebind(call):
        rt.lie = True
        rt.environment, rt.timeline = ENV_SOURCE, ENV_SOURCE.timeline
    mut, mut_node = mutator(rebind, depends_target="aging")
    request, context = F.request(ENV, SCN, auth, nodes=(mut_node, F.node(auth, depends_on=("mutator",))), extra_authorities=(mut,))
    result = SystemExecutor(context).run(request)
    receipt = result.receipt("aging")
    assert receipt.status is NodeStatus.FAILED and "self-reported" in receipt.reason, receipt.reason
    assert rt.runs == 0
    assert_nothing_released(result, "aging", auth, spies)


class LiesAboutIdentity(Counting):
    """Executes on ENV_SOURCE but reports ENV's environment digest (its records and checkpoints then carry the lie too)."""

    def identities(self):
        return {**super().identities(), "environment": ENV.digest}


def test_review_l1_a_self_reported_identity_does_not_stand_in_for_the_environment_the_run_reads():
    rt, auth = kit(ENV_SOURCE, cls=LiesAboutIdentity)
    request, context = F.request(ENV, SCN, auth)
    result = SystemExecutor(context).run(request)
    assert result.status is RunStatus.REFUSED and codes(result) == ["MULTISCALE_IDENTITY_MISMATCH"]
    assert "self-reported" in result.preflight.blocking[0].message
    assert rt.runs == 0


class LiesAfterPreflight(Counting):
    """Honest until ``lie`` is set; then it keeps reporting ENV's identities whatever it executes on."""

    lie = False

    def identities(self):
        ids = super().identities()
        if self.lie:
            ids.update(scenario=SCN.digest, timeline=ENV.timeline.digest, environment=ENV.digest)
        return ids


class RewritesPolicy(Counting):
    def run(self, **kw):
        record = super().run(**kw)
        return replace(record, identities={**record.identities, "policy": sha("another policy")})


class RecordDropsEnvironment(Counting):
    def run(self, **kw):
        record = super().run(**kw)
        return replace(record, identities={k: v for k, v in record.identities.items() if k != "environment"})


@pytest.mark.parametrize("cls, expected", [(RewritesPolicy, "is not the runtime's"), (RecordDropsEnvironment, "carries no ['environment']")],
                         ids=["record-other-non-bound-key", "record-missing-bound-key"])
def test_review_l2_a_record_differing_from_its_runtime_in_any_identity_is_refused(cls, expected):
    spies = Spies()
    _rt, auth = kit(cls=cls, spies=spies)
    request, context = F.request(ENV, SCN, auth)
    result = SystemExecutor(context).run(request)
    assert result.receipt("aging").status is NodeStatus.FAILED and expected in result.receipt("aging").reason, result.receipt("aging").reason
    assert_nothing_released(result, "aging", auth, spies)


def test_review_l2_a_runtime_renamed_after_construction_is_refused():
    rt, auth = kit()
    rt.run_id = "renamed-run"
    request, context = F.request(ENV, SCN, auth)
    result = SystemExecutor(context).run(request)
    assert result.status is RunStatus.REFUSED and codes(result) == ["MULTISCALE_RUNTIME_CHANGED"] and "run_id" in result.preflight.blocking[0].message
    assert rt.runs == 0
