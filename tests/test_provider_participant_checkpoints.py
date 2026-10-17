"""``provider_participant`` checkpoints hold ONE provider build's state, issued by ONE participant.

Reproduced defects (each test below fails on ``04b12344``):

* restore took ``cp.token`` as the held state without comparing it with the
  record: a token whose state digest differs from ``cp.record.state_digest``
  was accepted whenever ``deterministic_restore`` was False (the runtime's
  re-checkpoint comparison only runs for deterministic participants);
* the ``CheckpointRecord`` named no provider build, and a checkpoint taken by a
  participant declaring solver ``thermo@1.0`` restored into one declaring
  ``thermo@2.0`` with the same participant id.

The fix reuses ``ExternalSolverParticipant``'s seal (``engcore.execution.
multiphysics.external.CheckpointSeal``): canonical-JSON build scope bound into
``provider_state_id`` (labelled as the spec's declaration), a participant-issued
token registry holding the issued state and the record issued with it, and a
digest recomputed from the token's own state.  The ``CheckpointSeal`` section
tests the seal directly, on states this adapter cannot produce (mutable, None).

Every solve here is an in-process MOCK (a closure returning a stub record): no
provider library or external program is executed.  The executed-provider
counterpart for the PyBaMM adapter is
``providers/pybamm/tests/test_pybamm_checkpoint_identity.py``.
"""

from __future__ import annotations

import copy
import gc
import hashlib
import json
from dataclasses import replace
from types import MappingProxyType

import pytest

from engcore.coupling import provider_participant, scalar_port
from engcore.coupling.adapters import CouplingRefusal
from engcore.data import InMemoryBulkStore
from engcore.execution.multiphysics import AdvanceRequest, InitialStateValue
from engcore.execution.multiphysics.external import CheckpointSeal, _ScopedSnapshot
from engcore.execution.multiphysics.participant import RuntimeCheckpoint
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.multiphysics import InitialStateDefinition, ParticipantSpec
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.units.quantity import Quantity

U = Uncertainty.unknown("mock state uncertainty not quantified")


class _Rec:
    succeeded, reason, execution_identity, digest = True, "", "mock-execution", "mock-record"


def _spec(solver_version="1.0", *, deterministic=False, pid="p"):
    return ParticipantSpec(pid, "m", "1", "r", "1", "thermo", solver_version, "thermo-adapter", "1",
                           (scalar_port("f", "input", "temperature", "K"), scalar_port("x", "output", "temperature", "K")),
                           transient=True, checkpointable=True, deterministic_restore=deterministic)


def _participant(solver_version="1.0", *, deterministic=False):
    """A MOCK stateful provider participant: every solve adds 5 K to its evolved state ``t``."""

    def solve(inputs, start, end, uq, state):
        return _Rec(), {"x": inputs["f"]}, {"t": Quantity(state["t"].value.magnitude + 5, "K")}

    p = provider_participant(_spec(solver_version, deterministic=deterministic), solve=solve,
                             initial_outputs=lambda: {"x": Quantity(0, "K")}, store=InMemoryBulkStore(),
                             state_definitions=(InitialStateDefinition("t", "K"),), evolved_state=("t",))
    p.initialize_state(Quantity(0, "s"), {"t": InitialStateValue("t", Quantity(300, "K"), U)}, {}, {})
    return p


def _advance(p, start=0.0, end=1.0):
    return p.advance(AdvanceRequest(Quantity(start, "s"), Quantity(end, "s"), {"f": Quantity(1, "K")},
                                    {"f": Uncertainty.unknown("mock input")}, Quantity(end - start, "s")))


def _held_t(p):
    return {v.variable_id: v.value.magnitude for v in p.public_state(Quantity(0, "s"))}["t"]


def _scope(solver_version):
    return json.dumps({"adapter_id": "thermo-adapter", "adapter_version": "1", "provider_id": "thermo",
                       "provider_version": solver_version, "build_basis": "participant_spec_declaration"},
                      sort_keys=True, separators=(",", ":"))


# ---- controls: a participant's own checkpoints still restore ---------------------------------------


@pytest.mark.parametrize("deterministic", [False, True])
def test_own_checkpoint_restores_the_state_it_recorded(deterministic):
    p = _participant(deterministic=deterministic)
    cp = p.checkpoint(Quantity(0, "s"))
    _advance(p)
    assert _held_t(p) == 305
    p.restore(cp)
    assert _held_t(p) == 300
    assert p.checkpoint(Quantity(0, "s")).record.state_digest == cp.record.state_digest
    p.restore(cp)  # a checkpoint restores more than once (implicit iterations re-enter the same window)
    assert _held_t(p) == 300


def test_the_record_names_the_provider_build_and_the_completeness_slot():
    record = _participant("1.0").checkpoint(Quantity(0, "s")).record
    assert record.provider_state_id == f"{_scope('1.0')}#completeness:not_established"


# ---- defect (a): token state is never taken on trust -----------------------------------------------


def test_a_token_whose_digest_differs_from_the_record_is_refused_without_deterministic_restore():
    p = _participant(deterministic=False)
    cp0 = p.checkpoint(Quantity(0, "s"))
    _advance(p)
    cp1 = p.checkpoint(Quantity(1, "s"))
    assert cp0.record.state_digest != cp1.record.state_digest
    forged = RuntimeCheckpoint(cp0.record, cp1.token)  # record says t=300 K, token holds t=305 K
    with pytest.raises(InvalidScientificProblem, match="digest disagree"):
        p.restore(forged)
    assert _held_t(p) == 305  # nothing was restored


def test_a_record_re_made_around_an_issued_token_is_refused():
    p = _participant(deterministic=False)
    _advance(p)
    cp = p.checkpoint(Quantity(1, "s"))
    with pytest.raises(InvalidScientificProblem, match="not issued with its token"):
        p.restore(RuntimeCheckpoint(replace(cp.record, instant=Quantity(0, "s")), cp.token))
    p.restore(RuntimeCheckpoint(replace(cp.record), cp.token))  # an equal record is the issued record


def test_a_bare_state_mapping_is_not_a_checkpoint_token():
    p = _participant()
    cp = p.checkpoint(Quantity(0, "s"))
    bare = RuntimeCheckpoint(cp.record, {"t": InitialStateValue("t", Quantity(300, "K"), U)})
    with pytest.raises(InvalidScientificProblem, match="not sealed"):
        p.restore(bare)


def test_issued_state_cannot_be_edited_in_place():
    p = _participant()
    cp = p.checkpoint(Quantity(0, "s"))
    with pytest.raises(TypeError):
        cp.token.snapshot["t"] = InitialStateValue("t", Quantity(999, "K"), U)


# ---- defect (b): another build's (or another participant's) state never restores ------------------


def test_a_checkpoint_of_build_1_never_restores_into_build_2():
    one, two = _participant("1.0"), _participant("2.0")
    _advance(two)
    with pytest.raises(InvalidScientificProblem, match="never restores another provider's or build's state"):
        two.restore(one.checkpoint(Quantity(0, "s")))
    assert _held_t(two) == 305


def test_a_relabelled_record_is_refused():
    p = _participant("1.0")
    cp = p.checkpoint(Quantity(0, "s"))
    relabelled = RuntimeCheckpoint(replace(cp.record, provider_state_id=f"{_scope('2.0')}#completeness:not_established"), cp.token)
    with pytest.raises(InvalidScientificProblem, match="never restores another provider's or build's state"):
        p.restore(relabelled)
    legacy = RuntimeCheckpoint(replace(cp.record, provider_state_id="completeness:not_established"), cp.token)
    with pytest.raises(InvalidScientificProblem, match="never restores another provider's or build's state"):
        p.restore(legacy)


def test_a_checkpoint_of_the_same_build_from_another_participant_object_is_refused():
    one, other = _participant("1.0"), _participant("1.0")
    _advance(other)
    with pytest.raises(InvalidScientificProblem, match="not issued"):
        other.restore(one.checkpoint(Quantity(0, "s")))
    assert _held_t(other) == 305


def test_an_equal_state_re_wrapped_under_an_issued_nonce_is_refused():
    p = _participant()
    cp = p.checkpoint(Quantity(0, "s"))
    copy_of_state = MappingProxyType(dict(cp.token.snapshot))
    with pytest.raises(InvalidScientificProblem, match="not issued"):
        p.restore(RuntimeCheckpoint(cp.record, _ScopedSnapshot(cp.token.scope, copy_of_state, cp.token.nonce)))
    with pytest.raises(InvalidScientificProblem, match="not issued"):
        p.restore(RuntimeCheckpoint(cp.record, _ScopedSnapshot(cp.token.scope, copy_of_state, "0" * 32)))


def test_a_checkpoint_of_another_participant_id_is_refused():
    p = _participant()
    cp = p.checkpoint(Quantity(0, "s"))
    with pytest.raises((CouplingRefusal, InvalidScientificProblem), match="another participant"):
        p.restore(RuntimeCheckpoint(replace(cp.record, participant_id="q"), cp.token))


# ---- CheckpointSeal directly (the primitive all three adapters share) ------------------------------


def _digest(state):
    return hashlib.sha256(repr(state).encode()).hexdigest()


def _seal(state):
    seal = CheckpointSeal("p", '{"build":"b"}')
    return seal, seal.seal(Quantity(0, "s"), state_digest=_digest(state), deterministic_restore=False, slot="s", state=state)


def _admit(seal, cp):
    return seal.admit(cp, slot_of=lambda _s: "s", digest_of=_digest)


def test_state_edited_in_place_after_issue_never_restores_even_with_a_re_digested_record():
    seal, cp = _seal([1.0])
    assert _admit(seal, cp) == [1.0]
    cp.token.snapshot.append(2.0)  # a mutable issued state, edited by whoever holds the token
    with pytest.raises(InvalidScientificProblem, match="changed after it was issued"):
        _admit(seal, cp)
    with pytest.raises(InvalidScientificProblem, match="digest disagree"):
        _admit(seal, RuntimeCheckpoint(replace(cp.record, state_digest=_digest([1.0, 2.0])), cp.token))


def test_a_forged_none_state_never_matches_the_registry_sentinel():
    seal, cp = _seal(None)
    assert _admit(seal, cp) is None
    with pytest.raises(InvalidScientificProblem, match="not issued"):
        _admit(seal, RuntimeCheckpoint(cp.record, _ScopedSnapshot(seal.scope, None, "f" * 32)))
    stale = copy.copy(cp.token)  # the same None under the same nonce: admitted only while the issued token lives
    assert _admit(seal, RuntimeCheckpoint(cp.record, stale)) is None
    record = cp.record
    del cp
    gc.collect()
    with pytest.raises(InvalidScientificProblem, match="not issued"):
        _admit(seal, RuntimeCheckpoint(record, stale))


def test_the_registry_drops_an_entry_when_its_token_dies():
    seal, cp = _seal([1.0])
    assert len(seal._issued) == 1
    del cp
    gc.collect()
    assert seal._issued == {}
