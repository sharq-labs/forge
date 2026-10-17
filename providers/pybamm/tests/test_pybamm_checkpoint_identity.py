"""EXECUTED PROVIDER: the PyBaMM cell participant restores only its own build's checkpoints.

Reproduced defect (fails on ``04b12344``): ``cell_participant``'s restore set the
held PyBaMM Solution to whatever token it was handed.  A checkpoint of a cell
built with ``capacity_fade=0.0`` (or model SPM) restored into a cell with the
same participant id built with ``capacity_fade=0.2`` (or SPMe) and the next
window continued that foreign state under the other parameters; the record
named no build.  The record now binds the PyBaMM build (library version and
digest, adapter, model, parameter set, declared configuration) and restore
refuses another build, a token it did not issue and a token whose state vector
does not hash to the record's digest.

Every test here runs the REAL PyBaMM library (IDAKLU solver); it skips when
PyBaMM is unavailable.  The 3.14 venv cannot install PyBaMM's provider stack, so
run it in the 3.13 provider env.  The mock-only counterpart for the generic
adapter is ``tests/test_provider_participant_checkpoints.py``.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from engcore.coupling import scalar_port
from engcore.execution.multiphysics import AdvanceRequest
from engcore.execution.multiphysics.participant import RuntimeCheckpoint
from engcore.providers import ProviderRegistry
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.multiphysics import ParticipantSpec
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.units.quantity import Quantity

REG = ProviderRegistry()
from forge_pybamm import descriptor as pbd  # first-party: a defect fails, it never reads as a missing provider
pbd.register(REG)
OK = REG.status("pybamm").available
assert not ("pybamm" in {c.capability.provider_id for c in REG.discover()} and REG.status("pybamm").found_but_refused), "PyBaMM present but refused"
pytestmark = pytest.mark.skipif(not OK, reason="PyBaMM is required (executed-provider test)")

WINDOW = 600.0


def _spec(solver_version=None):
    ports = (scalar_port("temperature", "input", "temperature", "K"), scalar_port("heat", "output", "heat_rate", "W"))
    return ParticipantSpec("cell", "cell-model", "1", "cell-real", "1", "pybamm",
                           REG.status("pybamm").version if solver_version is None else solver_version, "forge.coupling", "1", ports,
                           transient=True, checkpointable=True, deterministic_restore=True)


def _cell(**kw):
    from forge_pybamm.coupling import cell_participant
    return cell_participant(REG, _spec(), parameter_set_name="Chen2020", model=kw.pop("model", "SPM"),
                            initial_soc=kw.pop("initial_soc", 0.8), capacity_fade=kw.pop("capacity_fade", 0.0),
                            current_at=lambda _start: Quantity(2.5, "A"), **kw)


def _advance(cell, k):
    req = AdvanceRequest(Quantity(k * WINDOW, "s"), Quantity((k + 1) * WINDOW, "s"), {"temperature": Quantity(298.15, "K")},
                         {"temperature": Uncertainty.unknown("test input")})
    return cell.advance(req).outputs["heat"].to("W").magnitude


def _soc(cell):
    return cell.public_state(Quantity(0, "s"))[0].value.magnitude


@pytest.fixture(scope="module")
def reference():
    """One SPM / fade 0.0 cell advanced one window, with checkpoints at t=0 and t=WINDOW."""
    cell = _cell()
    cp0 = cell.checkpoint(Quantity(0, "s"))
    _advance(cell, 0)
    cp1 = cell.checkpoint(Quantity(WINDOW, "s"))
    return cell, cp0, cp1


def test_own_checkpoint_round_trip_reproduces_the_next_window(reference):
    cell, cp0, cp1 = reference
    cell.restore(cp1)
    first = _advance(cell, 1)
    cell.restore(cp1)
    assert cell.checkpoint(Quantity(WINDOW, "s")).record.state_digest == cp1.record.state_digest
    assert _advance(cell, 1) == first  # the window re-solved from the restored PyBaMM state
    cell.restore(cp0)  # the initial (no-solution) state restores too
    assert cell.checkpoint(Quantity(0, "s")).record.state_digest == cp0.record.state_digest
    assert _soc(cell) == pytest.approx(0.8)
    cell.restore(cp1)


def test_the_record_names_the_pybamm_build(reference):
    import json

    _, _, cp1 = reference
    scope, _, slot = cp1.record.provider_state_id.rpartition("#")
    build = json.loads(scope)
    status = REG.status("pybamm")
    assert slot == "completeness:declared_complete"
    assert (build["provider_id"], build["provider_version"], build["provider_digest"]) == ("pybamm", status.version, status.digest)
    assert build["configuration"]["model"] == "SPM" and build["configuration"]["capacity_fade"] == repr(0.0)
    assert build["build_basis"] == "provider_discovery" and build["declared_coupling_adapter"] == ["forge.coupling", "1"]


@pytest.mark.parametrize("other", [{"capacity_fade": 0.2}, {"model": "SPMe"}], ids=["fade", "model"])
def test_a_checkpoint_of_another_pybamm_build_never_restores(reference, other):
    _, _, cp1 = reference
    foreign = _cell(**other)
    _advance(foreign, 0)
    before = foreign.checkpoint(Quantity(WINDOW, "s")).record.state_digest
    with pytest.raises(InvalidScientificProblem, match="never restores another provider's or build's state"):
        foreign.restore(cp1)
    assert foreign.checkpoint(Quantity(WINDOW, "s")).record.state_digest == before


def test_a_checkpoint_of_the_same_build_from_another_cell_object_is_refused(reference):
    _, _, cp1 = reference
    twin = _cell()
    with pytest.raises(InvalidScientificProblem, match="not issued"):
        twin.restore(cp1)


def test_a_token_whose_state_vector_disagrees_with_the_record_is_refused(reference):
    cell, cp0, cp1 = reference
    with pytest.raises(InvalidScientificProblem, match="record and provider snapshot digest disagree"):
        cell.restore(RuntimeCheckpoint(replace(cp1.record, state_digest=cp0.record.state_digest), cp1.token))
    with pytest.raises(InvalidScientificProblem, match="record and provider snapshot digest disagree"):
        cell.restore(RuntimeCheckpoint(cp1.record, cp0.token))


def test_a_solution_edited_in_place_after_issue_never_restores():
    import hashlib

    import numpy as np

    cell = _cell()
    _advance(cell, 0)
    cp = cell.checkpoint(Quantity(WINDOW, "s"))
    y = cp.token.snapshot.last_state.y  # PyBaMM caches last_state: this is the array a continuation reads
    y[0] += 1e-3
    with pytest.raises(InvalidScientificProblem, match="changed after it was issued"):
        cell.restore(cp)
    edited = hashlib.sha256(np.ascontiguousarray(np.asarray(y, dtype="<f8")).tobytes()).hexdigest()
    with pytest.raises(InvalidScientificProblem, match="record and provider snapshot digest disagree"):
        cell.restore(RuntimeCheckpoint(replace(cp.record, state_digest=edited), cp.token))


@pytest.mark.parametrize("edit", ["all_ys", "t"])
def test_other_continuation_state_edited_in_place_never_restores(edit):
    # review R-2: all_ys backs the state vector; the clock (t) is outside the y-only state identity, and an
    # admitted clock edit moved the next window's heat (probe, 2026-10-17), so it is fingerprinted at issue
    cell = _cell()
    _advance(cell, 0)
    cp = cell.checkpoint(Quantity(WINDOW, "s"))
    sol = cp.token.snapshot
    if edit == "all_ys":
        sol.all_ys[-1][:, -1] *= 0.5
    else:
        sol.t[-1] += 100.0
    with pytest.raises(InvalidScientificProblem, match="changed after it was issued"):
        cell.restore(cp)


def test_a_bare_solution_is_not_a_checkpoint_token(reference):
    cell, _, cp1 = reference
    with pytest.raises(InvalidScientificProblem, match="not sealed"):
        cell.restore(RuntimeCheckpoint(cp1.record, getattr(cp1.token, "snapshot", cp1.token)))


def test_a_spec_declaring_another_solver_build_is_refused():
    from engcore.providers import ProviderRefusal
    from forge_pybamm.coupling import cell_participant

    with pytest.raises(ProviderRefusal, match="declares solver"):
        cell_participant(REG, _spec(solver_version="0.0.0-not-this-build"), parameter_set_name="Chen2020", model="SPM",
                         initial_soc=0.8, capacity_fade=0.0, current_at=lambda _start: Quantity(2.5, "A"))
