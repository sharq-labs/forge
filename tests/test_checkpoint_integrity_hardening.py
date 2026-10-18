"""R1/R2/R5 adversarial contracts. Written under Build-First; NOT RUN.

All sessions here are mocks. No external provider or physical validation claim.
"""
import hashlib
import json
from dataclasses import replace

import pytest

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.execution.multiphysics import (
    AdvanceRequest, AdvanceResult, CallbackParticipant, InitializationResult, MultiphysicsRuntime,
)
from engcore.execution.multiphysics.external import (
    ExternalProviderFailure, ExternalProviderIdentity, ExternalSnapshot, ExternalSolverParticipant,
)
from engcore.execution.multiphysics.participant import CheckpointIntegrityError, RuntimeCheckpoint
from engcore.execution.multiphysics.runtime import MultiphysicsExecutionError
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.multiphysics import (
    CheckpointRecord, ConvergenceCriterion, CouplingEdge, CouplingPlan, CouplingScheme,
    IterationSemantics, ParticipantSpec, PhysicsGraph, PortDefinition, PortDirection, PortKind, PortRef, TimePolicy,
)
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.units.quantity import Quantity

U = Uncertainty.unknown("mock; uncertainty is not quantified")


def spec(pid="a"):
    return ParticipantSpec(pid, "m", "1", "r", "1", "mock", "1", "adapter", "1",
                           (PortDefinition("in", PortDirection.INPUT, PortKind.SCALAR, "temperature", "K"),
                            PortDefinition("out", PortDirection.OUTPUT, PortKind.SCALAR, "temperature", "K")),
                           transient=True, checkpointable=True, deterministic_restore=True)


class MutableSession:
    identity = ExternalProviderIdentity("mock", "1", "adapter", "1", mock=True)
    snapshot_integrity_codec = ("fixture.complete-json-state", "1")

    def __init__(self, *, fail_restore=False):
        self.state = {"steps": 0, "time": 0.0}
        self.fail_restore = fail_restore
        self.restores = 0

    def snapshot_integrity_bytes(self, snapshot):
        # Read the actual continuation payload, including its clock, every time.
        return json.dumps(snapshot.token, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")

    def initialize(self, instant, inputs, uq):
        return InitializationResult({"out": Quantity(1, "K")}, {"out": U})

    def advance(self, request):
        self.state = {"steps": self.state["steps"] + 1, "time": request.end.magnitude_in("s")}
        return AdvanceResult(request.end, {"out": Quantity(1, "K")}, {"out": U}, 1, True)

    def snapshot(self, instant):
        token = dict(self.state)
        # This stored scientific digest deliberately does not identify the clock.
        return ExternalSnapshot(hashlib.sha256(str(token["steps"]).encode("ascii")).hexdigest(), "state", token)

    def restore(self, snapshot):
        self.restores += 1
        self.state = dict(snapshot.token)
        if self.fail_restore:
            self.state["steps"] = 999  # mutation before a failure is unsafe
            raise OSError("restore crashed after mutation")

    def finalize(self):
        pass


def participant(session=None, pid="a"):
    return ExternalSolverParticipant(spec(pid), session or MutableSession())


def request():
    return AdvanceRequest(Quantity(0, "s"), Quantity(1, "s"), {"in": Quantity(1, "K")}, {"in": U})


@pytest.mark.parametrize("field,value", [("steps", 7), ("time", 100.0)])
def test_mutable_payload_change_is_refused_even_when_stored_digest_is_unchanged(field, value):
    session = MutableSession()
    p = participant(session)
    cp = p.checkpoint(Quantity(0, "s"))
    cp.token.snapshot.token[field] = value
    with pytest.raises(InvalidScientificProblem, match="changed after it was issued"):
        p.restore(cp)
    assert session.restores == 0 and session.state == {"steps": 0, "time": 0.0}


def test_missing_integrity_codec_refuses_opaque_payload_before_any_restore():
    session = MutableSession()
    session.snapshot_integrity_codec = None
    session.snapshot_integrity_bytes = None
    p = participant(session)
    with pytest.raises(InvalidScientificProblem, match="requires a versioned provider integrity codec"):
        p.checkpoint(Quantity(0, "s"))
    assert session.restores == 0


def test_bytes_are_not_inferred_to_be_self_contained_state():
    session = MutableSession()
    session.snapshot_integrity_codec = None
    session.snapshot_integrity_bytes = None
    session.snapshot = lambda instant: ExternalSnapshot("a" * 64, "file", b"checkpoint.dat")
    with pytest.raises(InvalidScientificProblem, match="requires a versioned provider integrity codec"):
        participant(session).checkpoint(Quantity(0, "s"))


def test_content_addressed_codec_checks_referenced_bytes_on_every_restore():
    session = MutableSession()
    payload = b"complete continuation state at physical zero"
    digest = hashlib.sha256(payload).hexdigest()
    blobs = {digest: payload}
    session.snapshot_integrity_codec = ("mock.verified-content-addressed-state", "1")
    session.snapshot = lambda instant: ExternalSnapshot(digest, "blob", digest.encode("ascii"))
    def encode(snapshot):
        key = snapshot.token.decode("ascii")
        actual = blobs[key]
        if hashlib.sha256(actual).hexdigest() != key:
            raise InvalidScientificProblem("referenced checkpoint content is corrupt")
        return actual
    session.snapshot_integrity_bytes = encode
    p = participant(session)
    cp = p.checkpoint(Quantity(0, "s"))
    blobs[digest] = b"corrupt substituted state"
    with pytest.raises(CheckpointIntegrityError, match="could not be established") as caught:
        p.restore(cp)
    assert "content is corrupt" in str(caught.value.__cause__)
    assert session.restores == 0
    with pytest.raises(InvalidScientificProblem, match="unusable"):
        p.advance(request())


def test_provider_qualified_inline_bytes_support_repeated_rollback():
    session = MutableSession()
    session.snapshot_integrity_codec = ("mock.inline-ascii-steps-only", "1")
    session.snapshot = lambda instant: ExternalSnapshot("a" * 64, "steps", str(session.state["steps"]).encode("ascii"))
    session.snapshot_integrity_bytes = lambda snapshot: snapshot.token
    # This fixture's continuation state is exactly a step count; no external reference.
    session.restore = lambda snapshot: session.state.update(steps=int(snapshot.token))
    p = participant(session)
    cp = p.checkpoint(Quantity(0, "s"))
    session.state["steps"] = 9
    p.restore(cp)
    assert session.state["steps"] == 0


@pytest.mark.parametrize("bad", ["claimed-digest", bytearray(b"mutable"), None])
def test_codec_must_return_exact_immutable_bytes(bad):
    session = MutableSession()
    session.snapshot_integrity_bytes = lambda snapshot: bad
    with pytest.raises(InvalidScientificProblem, match="immutable payload bytes"):
        participant(session).checkpoint(Quantity(0, "s"))


def test_codec_failure_is_a_classified_refusal_without_restore():
    session = MutableSession()
    p = participant(session)
    cp = p.checkpoint(Quantity(0, "s"))
    def fail(snapshot):
        raise FileNotFoundError("content-addressed payload unavailable")
    session.snapshot_integrity_bytes = fail
    with pytest.raises(CheckpointIntegrityError) as caught:
        p.restore(cp)
    assert isinstance(caught.value.__cause__, ExternalProviderFailure)
    assert caught.value.__cause__.phase == "snapshot_integrity" and session.restores == 0
    with pytest.raises(InvalidScientificProblem, match="unusable"):
        p.advance(request())


def test_codec_identity_drift_is_refused():
    session = MutableSession()
    p = participant(session)
    cp = p.checkpoint(Quantity(0, "s"))
    session.snapshot_integrity_codec = ("fixture.complete-json-state", "2")
    with pytest.raises(CheckpointIntegrityError, match="could not be established") as caught:
        p.restore(cp)
    assert "codec changed" in str(caught.value.__cause__)
    assert session.restores == 0
    with pytest.raises(InvalidScientificProblem, match="unusable"):
        p.advance(request())


def test_same_object_rollback_reproduces_state_and_can_be_repeated():
    session = MutableSession()
    p = participant(session)
    cp = p.checkpoint(Quantity(0, "s"))
    for _ in range(2):
        p.advance(request())
        assert session.state["steps"] == 1
        p.restore(cp)
        assert session.state == {"steps": 0, "time": 0.0}


def test_record_substitution_does_not_restore_and_the_genuine_checkpoint_still_works():
    session = MutableSession()
    p = participant(session)
    cp = p.checkpoint(Quantity(0, "s"))
    for record in (replace(cp.record, instant=Quantity(1, "s")), replace(cp.record, state_digest="f" * 64)):
        with pytest.raises(InvalidScientificProblem):
            p.restore(RuntimeCheckpoint(record, cp.token))
    assert session.restores == 0
    p.restore(cp)


def test_cross_object_restore_is_refused_for_the_same_provider_build():
    first, second = participant(), participant()
    cp = first.checkpoint(Quantity(0, "s"))
    with pytest.raises(InvalidScientificProblem, match="not issued"):
        second.restore(cp)


def runtime(participants):
    graph = PhysicsGraph("repair", tuple(p.spec for p in participants.values()), (
        CouplingEdge("ab", PortRef("a", "out"), PortRef("b", "in")),
        CouplingEdge("ba", PortRef("b", "out"), PortRef("a", "in")),
    ))
    plan = CouplingPlan("repair", CouplingScheme.IMPLICIT, IterationSemantics.SERIAL,
                        TimePolicy(Quantity(0, "s"), Quantity(1, "s"), Quantity(1, "s")), ("a", "b"),
                        (ConvergenceCriterion("ba", 0.0, Quantity(1e-6, "K")),), max_iterations=5)
    store = InMemoryBulkStore()
    return MultiphysicsRuntime(graph, plan, participants, resolver=BulkDataResolver(store), store=store)


def test_restore_failure_after_first_participant_restores_retires_runtime_and_sessions():
    a, b = MutableSession(), MutableSession(fail_restore=True)
    participants = {"a": participant(a, "a"), "b": participant(b, "b")}
    rt = runtime(participants)
    with pytest.raises(ExternalProviderFailure, match="restore crashed"):
        rt.run("unsafe", external_inputs={})
    assert a.restores == 1 and b.restores == 1 and b.state["steps"] == 999
    with pytest.raises(MultiphysicsExecutionError, match="unusable"):
        rt.run("retry", external_inputs={})
    for p in participants.values():
        with pytest.raises(InvalidScientificProblem, match="unusable"):
            p.advance(request())
        with pytest.raises(InvalidScientificProblem, match="unusable"):
            p.initialize(Quantity(0, "s"), {"in": Quantity(1, "K")}, {"in": U})
    with pytest.raises(MultiphysicsExecutionError, match="unusable"):
        runtime(participants).run("fresh-runtime-same-unsafe-sessions", external_inputs={})


def test_failed_callback_restore_also_retires_previously_restored_callback():
    states, restored = {"a": 5, "b": 6}, []
    participants = {}
    for pid in states:
        def checkpoint(instant, pid=pid):
            return RuntimeCheckpoint(CheckpointRecord(pid, instant, hashlib.sha256(bytes([states[pid]])).hexdigest(), True), states[pid])
        def restore(cp, pid=pid):
            restored.append(pid)
            states[pid] = cp.token
            if pid == "b":
                raise InvalidScientificProblem("callback failed after mutation")
        participants[pid] = CallbackParticipant(spec(pid),
            initialize=lambda *args: InitializationResult({"out": Quantity(1, "K")}, {"out": U}),
            advance=lambda req: AdvanceResult(req.end, {"out": Quantity(1, "K")}, {"out": U}, 1, True),
            checkpoint=checkpoint, restore=restore)
    rt = runtime(participants)
    cp = rt._checkpoint_all(Quantity(0, "s"))
    with pytest.raises(InvalidScientificProblem, match="callback failed"):
        rt._restore_all(cp)
    assert restored == ["a", "b"]
    with pytest.raises(InvalidScientificProblem, match="unusable"):
        participants["a"].advance(request())
    with pytest.raises(MultiphysicsExecutionError, match="unusable"):
        rt.run("unsafe", external_inputs={})


def test_direct_external_restore_failure_retires_participant():
    session = MutableSession(fail_restore=True)
    p = participant(session)
    cp = p.checkpoint(Quantity(0, "s"))
    with pytest.raises(ExternalProviderFailure):
        p.restore(cp)
    with pytest.raises(InvalidScientificProblem, match="unusable"):
        p.advance(request())


def test_direct_callback_restore_failure_retires_the_callback():
    state = {"steps": 0}
    def restore(cp):
        state["steps"] = 999
        raise RuntimeError("callback application failed")
    p = CallbackParticipant(spec(),
        initialize=lambda *args: InitializationResult({"out": Quantity(1, "K")}, {"out": U}),
        advance=lambda req: AdvanceResult(req.end, {"out": Quantity(1, "K")}, {"out": U}, 1, True),
        checkpoint=lambda instant: RuntimeCheckpoint(CheckpointRecord("a", instant, "a" * 64, True), 0),
        restore=restore)
    with pytest.raises(RuntimeError, match="application failed"):
        p.restore(p.checkpoint(Quantity(0, "s")))
    assert state["steps"] == 999
    with pytest.raises(InvalidScientificProblem, match="unusable"):
        p.advance(request())


def test_declaration_only_native_adapter_does_not_claim_an_observed_build():
    from types import SimpleNamespace
    from engcore.coupling.adapters import provider_participant
    p = provider_participant(spec(),
        solve=lambda *args: (SimpleNamespace(succeeded=True, reason="", execution_identity="native", digest="record"),
                              {"out": Quantity(1, "K")}),
        initial_outputs=lambda: {"out": Quantity(1, "K")}, store=InMemoryBulkStore())
    p.advance(request())
    cp = p.checkpoint(Quantity(1, "s"))
    assert '"build_basis":"participant_spec_declaration"' in cp.record.provider_state_id
    assert ";build:" not in cp.record.provider_state_id
    p.restore(cp)


def test_required_provider_identity_cannot_be_replaced_by_a_native_declaration():
    from types import SimpleNamespace
    from engcore.coupling.adapters import CouplingRefusal, provider_participant
    p = provider_participant(spec(),
        solve=lambda *args: (SimpleNamespace(succeeded=True, reason="", execution_identity="native", digest="record"),
                              {"out": Quantity(1, "K")}),
        initial_outputs=lambda: {"out": Quantity(1, "K")}, store=InMemoryBulkStore(),
        expected_build={"provider_id": "mock", "provider_version": "1", "provider_digest": "a" * 64,
                        "adapter_id": "adapter", "adapter_version": "1"})
    with pytest.raises(CouplingRefusal, match="no complete provider build"):
        p.advance(request())


@pytest.mark.parametrize("weakrefable", [False, True])
def test_custom_participant_without_retirement_hooks_cannot_enter_a_fresh_runtime(weakrefable):
    class Custom:
        __slots__ = ("inner", "__weakref__") if weakrefable else ("inner",)

        def __init__(self, inner):
            self.inner = inner

        @property
        def spec(self):
            return self.inner.spec

        def initialize(self, *args):
            return self.inner.initialize(*args)

        def advance(self, req):
            return self.inner.advance(req)

        def checkpoint(self, instant):
            return self.inner.checkpoint(instant)

        def restore(self, cp):
            return self.inner.restore(cp)

        def finalize(self):
            self.inner.finalize()

    a, b = MutableSession(), MutableSession(fail_restore=True)
    participants = {"a": Custom(participant(a, "a")), "b": Custom(participant(b, "b"))}
    rt = runtime(participants)
    with pytest.raises(ExternalProviderFailure):
        rt.run("failed", external_inputs={})
    assert a.restores == b.restores == 1
    with pytest.raises(MultiphysicsExecutionError, match="unusable"):
        runtime(participants).run("fresh", external_inputs={})
