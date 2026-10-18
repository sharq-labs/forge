"""ExternalSolverParticipant checkpoints hold ONE provider build's state.

Reproduced defect: a checkpoint taken from a participant running provider
``thermo@1.0`` was accepted by a participant with the same id running
``thermo@2.0``, whose session was handed the foreign snapshot; the checkpoint
record did not name the provider build at all.  The record now binds the build
and restore refuses any other.  These sessions are in-process MOCKS of an
external provider: no external program is executed here.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.execution.multiphysics import AdvanceRequest, AdvanceResult, InitializationResult, MultiphysicsRuntime
from engcore.execution.multiphysics.external import ExternalProviderIdentity, ExternalSnapshot, ExternalSolverParticipant
from engcore.execution.multiphysics.participant import RuntimeCheckpoint
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.multiphysics import (
    ConvergenceCriterion, CouplingEdge, CouplingPlan, CouplingScheme, IterationSemantics, ParticipantSpec, PhysicsGraph,
    PortDefinition, PortDirection, PortKind, PortRef, TimePolicy,
)
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.units.quantity import Quantity

UNKNOWN = Uncertainty.unknown("mock provider output uncertainty not quantified")


class MockSession:
    """A stateful mock provider: every advance adds one to ``steps`` (state a rollback must undo)."""

    snapshot_integrity_codec = ("mock.inline-ascii-step-count", "1")

    def snapshot_integrity_bytes(self, snapshot):
        # This mock restores only the complete step count encoded in token.
        return snapshot.token

    def __init__(self, provider_version="1.0", adapter_version="1", *, out, inp, fn):
        self._identity = ExternalProviderIdentity("thermo", provider_version, "thermo-adapter", adapter_version)
        self.out, self.inp, self.fn = out, inp, fn
        self.steps = 0
        self.restored = []

    @property
    def identity(self):
        return self._identity

    def initialize(self, _instant, _inputs, _uq):
        return InitializationResult({self.out: Quantity(0, "K")}, {self.out: UNKNOWN})

    def advance(self, request):
        self.steps += 1
        return AdvanceResult(request.end, {self.out: self.fn(request.inputs[self.inp])}, {self.out: UNKNOWN}, 1, True)

    def snapshot(self, _instant):
        digest = hashlib.sha256(f"{self._identity.provider_version}:{self.steps}".encode()).hexdigest()
        return ExternalSnapshot(digest, f"steps-{self.steps}", str(self.steps).encode("ascii"))

    def restore(self, snapshot):
        self.restored.append(snapshot)
        self.steps = int(snapshot.token)

    def finalize(self):
        pass


def _spec(pid, out, inp, provider_version="1.0", adapter_version="1"):
    return ParticipantSpec(pid, "m", "1", "r", "1", "thermo", provider_version, "thermo-adapter", adapter_version,
                           (PortDefinition(inp, PortDirection.INPUT, PortKind.SCALAR, "temperature", "K"),
                            PortDefinition(out, PortDirection.OUTPUT, PortKind.SCALAR, "temperature", "K")),
                           transient=True, checkpointable=True, deterministic_restore=True)


def _participant(provider_version="1.0", adapter_version="1", pid="a"):
    session = MockSession(provider_version, adapter_version, out="x", inp="y", fn=lambda y: y)
    return ExternalSolverParticipant(_spec(pid, "x", "y", provider_version, adapter_version), session), session


SCOPE_1 = '{"adapter_id":"thermo-adapter","adapter_version":"1","provider_id":"thermo","provider_version":"1.0"}'
SCOPE_2 = '{"adapter_id":"thermo-adapter","adapter_version":"1","provider_id":"thermo","provider_version":"2.0"}'


def test_checkpoint_record_names_the_provider_build_whose_state_it_holds():
    participant, _ = _participant()
    record = participant.checkpoint(Quantity(0, "s")).record
    assert record.provider_state_id == f"{SCOPE_1}#steps-0"


def test_same_participant_restores_its_own_checkpoint():
    participant, session = _participant()
    checkpoint = participant.checkpoint(Quantity(0, "s"))
    session.steps = 7
    participant.restore(checkpoint)
    assert session.steps == 0


@pytest.mark.parametrize("other", [dict(provider_version="2.0"), dict(adapter_version="2")])
def test_checkpoint_of_another_provider_build_is_refused(other):
    first, _ = _participant()
    second, session = _participant(**other)
    with pytest.raises(InvalidScientificProblem, match="never restores another provider's or build's state"):
        second.restore(first.checkpoint(Quantity(0, "s")))
    assert session.restored == []


def test_record_rebound_to_another_slot_is_refused():
    participant, session = _participant()
    checkpoint = participant.checkpoint(Quantity(0, "s"))
    forged = RuntimeCheckpoint(replace(checkpoint.record, provider_state_id=f"{SCOPE_1}#steps-9"), checkpoint.token)
    with pytest.raises(InvalidScientificProblem):
        participant.restore(forged)
    assert session.restored == []


def test_record_relabelled_to_the_restoring_build_is_refused():
    # review I-4: rewriting only the record string must not smuggle 1.0 state into a 2.0 session
    first, _ = _participant()
    second, session = _participant(provider_version="2.0")
    checkpoint = first.checkpoint(Quantity(0, "s"))
    relabelled = RuntimeCheckpoint(replace(checkpoint.record, provider_state_id=f"{SCOPE_2}#steps-0"), checkpoint.token)
    with pytest.raises(InvalidScientificProblem, match="never restores another provider's or build's state"):
        second.restore(relabelled)
    assert session.restored == []


def test_bare_provider_snapshot_token_is_refused():
    participant, session = _participant()
    checkpoint = participant.checkpoint(Quantity(0, "s"))
    bare = RuntimeCheckpoint(checkpoint.record, checkpoint.token.snapshot)
    with pytest.raises(InvalidScientificProblem, match="not sealed"):
        participant.restore(bare)
    assert session.restored == []


def test_session_identity_change_after_admission_is_refused():
    participant, session = _participant()
    checkpoint = participant.checkpoint(Quantity(0, "s"))
    session._identity = ExternalProviderIdentity("thermo", "2.0", "thermo-adapter", "1")
    with pytest.raises(InvalidScientificProblem, match="changed provider identity"):
        participant.restore(checkpoint)
    with pytest.raises(InvalidScientificProblem, match="changed provider identity"):
        participant.checkpoint(Quantity(0, "s"))
    request = AdvanceRequest(Quantity(0, "s"), Quantity(1, "s"), {"y": Quantity(1, "K")}, {"y": UNKNOWN})
    with pytest.raises(InvalidScientificProblem, match="changed provider identity"):
        participant.advance(request)  # 2.0 outputs are never recorded under the admitted 1.0 identity
    with pytest.raises(InvalidScientificProblem, match="changed provider identity"):
        participant.initialize(Quantity(0, "s"), {"y": Quantity(1, "K")}, {"y": UNKNOWN})
    assert session.restored == [] and session.steps == 0


def test_scope_does_not_collide_for_identities_that_concatenate_alike():
    # review I-4b: "a@b/c@d"-style concatenation maps these two identities to one string
    one = ExternalProviderIdentity("p", "1/x@2", "y", "3")
    two = ExternalProviderIdentity("p", "1", "x@2/y", "3")
    assert one.state_scope != two.state_scope


def test_record_without_provider_binding_is_refused():
    participant, session = _participant()
    checkpoint = participant.checkpoint(Quantity(0, "s"))
    legacy = RuntimeCheckpoint(replace(checkpoint.record, provider_state_id="steps-0"), checkpoint.token)
    with pytest.raises(InvalidScientificProblem):
        participant.restore(legacy)


def test_implicit_coupling_of_external_participants_rolls_back_provider_state_every_iteration():
    # x = y/2 + 5, y = x  ->  fixed point 10 K.  Every iteration re-advances both sessions from the
    # window start; without the restore each session's step counter would count every iteration.
    sa = MockSession(out="x", inp="y", fn=lambda y: Quantity(y.magnitude_in("K") / 2 + 5, "K"))
    sb = MockSession(out="y", inp="x", fn=lambda x: Quantity(x.magnitude_in("K"), "K"))
    pa, pb = ExternalSolverParticipant(_spec("a", "x", "y"), sa), ExternalSolverParticipant(_spec("b", "y", "x"), sb)
    graph = PhysicsGraph("ext-fp", (pa.spec, pb.spec), (CouplingEdge("e_x", PortRef("a", "x"), PortRef("b", "x")),
                                                       CouplingEdge("e_y", PortRef("b", "y"), PortRef("a", "y"))))
    plan = CouplingPlan("ext-fp", CouplingScheme.IMPLICIT, IterationSemantics.SERIAL,
                        TimePolicy(Quantity(0, "s"), Quantity(1, "s"), Quantity(1, "s")), ("a", "b"),
                        (ConvergenceCriterion("e_x", 0.0, Quantity(1e-6, "K")), ConvergenceCriterion("e_y", 0.0, Quantity(1e-6, "K"))),
                        max_iterations=100)
    store = InMemoryBulkStore()
    run = MultiphysicsRuntime(graph, plan, {"a": pa, "b": pb}, resolver=BulkDataResolver(store), store=store).run(
        "ext-fp", external_inputs={},
        initial_coupling_values={"e_x": Quantity(0, "K"), "e_y": Quantity(0, "K")},
        initial_coupling_uncertainty={"e_x": UNKNOWN, "e_y": UNKNOWN})
    window = run.windows[0]
    assert window.outcome.value == "converged"
    assert run.final_outputs["a.x"]["magnitude"] == pytest.approx(10.0, abs=1e-5)
    assert len(window.iterations) > 2
    # each iteration restored the window-start state: one window's worth of state, not one per iteration
    assert sa.steps == 1 and sb.steps == 1
    assert len(sa.restored) >= len(window.iterations)


class SwitchingSession(MockSession):
    """Switches provider build INSIDE a call (after admission, before returning)."""

    def __init__(self, switch_in):
        super().__init__(out="x", inp="y", fn=lambda y: y)
        self.switch_in = switch_in

    def _switch(self, where):
        if where == self.switch_in:
            self._identity = ExternalProviderIdentity("thermo", "2.0", "thermo-adapter", "1")

    def advance(self, request):
        self._switch("advance")
        return super().advance(request)

    def initialize(self, instant, inputs, uq):
        self._switch("initialize")
        return super().initialize(instant, inputs, uq)

    def snapshot(self, instant):
        self._switch("snapshot")
        return super().snapshot(instant)


@pytest.mark.parametrize("where", ["advance", "initialize", "snapshot"])
def test_build_switched_inside_a_call_is_refused_before_its_result_is_used(where):
    session = SwitchingSession(where)
    participant = ExternalSolverParticipant(_spec("a", "x", "y"), session)
    call = {
        "advance": lambda: participant.advance(
            AdvanceRequest(Quantity(0, "s"), Quantity(1, "s"), {"y": Quantity(1, "K")}, {"y": UNKNOWN})),
        "initialize": lambda: participant.initialize(Quantity(0, "s"), {"y": Quantity(1, "K")}, {"y": UNKNOWN}),
        "snapshot": lambda: participant.checkpoint(Quantity(0, "s")),
    }[where]
    with pytest.raises(InvalidScientificProblem, match="changed provider identity"):
        call()


def test_issued_token_under_a_record_with_another_digest_is_refused():
    participant, session = _participant()
    issued = participant.checkpoint(Quantity(0, "s"))
    other = hashlib.sha256(b"another state").hexdigest()
    with pytest.raises(InvalidScientificProblem, match="record and provider snapshot digest disagree"):
        participant.restore(RuntimeCheckpoint(replace(issued.record, state_digest=other), issued.token))
    assert session.restored == []


def test_wrapper_not_issued_by_the_participant_is_refused_even_with_its_scope():
    from engcore.execution.multiphysics.external import _ScopedSnapshot

    participant, session = _participant()
    issued = participant.checkpoint(Quantity(0, "s"))
    foreign = ExternalSnapshot(hashlib.sha256(b"foreign build state").hexdigest(), "steps-0", 99)
    forged_token = _ScopedSnapshot(issued.token.scope, foreign, issued.token.nonce)
    forged = RuntimeCheckpoint(replace(issued.record, state_digest=foreign.state_digest), forged_token)
    with pytest.raises(InvalidScientificProblem, match="not issued"):
        participant.restore(forged)
    assert session.restored == []


def test_payload_substituted_under_an_issued_digest_slot_and_nonce_is_refused():
    # confirmation review F-3: same digest and slot, different provider payload
    from engcore.execution.multiphysics.external import _ScopedSnapshot

    participant, session = _participant()
    issued = participant.checkpoint(Quantity(0, "s"))
    swapped = ExternalSnapshot(issued.token.snapshot.state_digest, "steps-0", 7)
    forged = RuntimeCheckpoint(issued.record, _ScopedSnapshot(issued.token.scope, swapped, issued.token.nonce))
    with pytest.raises(InvalidScientificProblem, match="not issued"):
        participant.restore(forged)
    assert session.restored == [] and session.steps == 0
    participant.restore(issued)  # the genuine checkpoint still restores
    assert session.steps == 0 and len(session.restored) == 1
