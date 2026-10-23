"""36 bounded lifetime transition traces extending the historical 54 traces.

Event words are explicit; no timing or random seeds. Tests exercise executor call
counts, not merely private state. This finite product is not exhaustive proof.
"""
from itertools import product
from unittest.mock import patch
import pytest
from engcore.mind.world import BudgetReader
from engcore.mind.world.authority import OwnerUnavailable
from engcore.sria.campaign.budget import BudgetLedger
from tests.mind.test_authority_review_r14 import _desk, _solver, _settle, _refused, _SelfFillingNote, ax

TRACES = tuple(product(("before_handoff", "capture"), ("unspent", "spent", "unknown"), (1, 2),
                       ("restore", "seal", "retire")))

@pytest.mark.parametrize("phase,effect,interruptions,ending", TRACES)
def test_lifetime_trace(phase, effect, interruptions, ending):
    o = ax.owned("battery")
    lid = _solver(o)
    calls = []
    def execute(authorization):
        calls.append(1)
        _settle(o.ledgers[lid], f"dispatch.{len(calls)}")
    # Alternate native and detached bindings, retaining the same owner objects.
    def accounts():
        return (o.ledgers if interruptions == 1 else dict(o.ledgers)), dict(o.experiments)
    reader, _, gateway, admitted = _desk(o, accounts, execute)
    saved = o.ledgers[lid].to_dict()
    assert reader.pinned()  # publish, capture, reconcile
    if effect != "unspent":
        gateway.dispatch(admitted.admitted)  # actual spend, not a caller assertion
    if effect == "unknown":
        _settle(o.ledgers[lid], "unknown-history", _SelfFillingNote())
    if phase == "capture":
        original = BudgetReader._retain_handing
        remaining = [interruptions]
        def stop(value):
            if remaining[0]:
                remaining[0] -= 1
                raise KeyboardInterrupt()
            return original(value)
        with patch.object(BudgetReader, "_retain_handing", staticmethod(stop)):
            with pytest.raises(KeyboardInterrupt):
                reader.pinned()
        assert remaining == [0]
    else:
        with patch.object(reader, "_follow", side_effect=KeyboardInterrupt):
            for _ in range(interruptions):
                with pytest.raises(KeyboardInterrupt):
                    reader.pinned()
    for _ in range(2):
        o.ledgers[lid] = BudgetLedger.from_dict(saved)  # detach, restore, repeat
        try:
            reader.pinned()  # reconcile; unknown may refuse here or at account read
        except OwnerUnavailable:
            pass
    if ending != "restore":
        reader._source.close()  # seal all dependent readers
        if ending == "retire":
            reader._source.retire()  # completed pins: proven quiescence
    if effect == "unspent" and ending == "restore":
        gateway.dispatch(admitted.admitted)
        assert calls == [1]
    else:
        assert _refused(gateway, admitted.admitted)
        assert calls == ([] if effect == "unspent" else [1])
