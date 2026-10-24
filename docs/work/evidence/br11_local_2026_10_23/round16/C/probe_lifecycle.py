from __future__ import annotations
import json
from unittest.mock import patch
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable
from engcore.sria.campaign.budget import BudgetLedger
from tests.mind.test_authority_review_r14 import _desk, _solver, _settle, _refused, ax
from tests.mind.test_authority_review_r15 import _simple


def interrupted_buffer(phase):
    o = ax.owned("battery")
    lid = _solver(o)
    calls = []
    def executor(authorization):
        calls.append(1)
        _settle(o.ledgers[lid], f"run.{len(calls)}")
    reader, authorities, gateway, result = _desk(o, lambda: (o.ledgers, o.experiments), executor)
    checkpoint = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(result.admitted)
    armed = [2]
    real = getattr(BudgetReader, phase)
    def interrupt(*args):
        if armed[0]:
            armed[0] -= 1
            raise KeyboardInterrupt("deterministic handing/recovery checkpoint")
        return real(*args)
    with patch.object(BudgetReader, phase, staticmethod(interrupt)):
        try:
            reader.pinned()
        except KeyboardInterrupt:
            pass
        else:
            raise AssertionError("interrupted pin succeeded")
    retained = [type(v).__name__ for v in reader._uncompared.values()]
    o.ledgers[lid] = checkpoint
    refused = _refused(gateway, result.admitted)
    return dict(phase=phase, consumed_interruptions=2-armed[0], pending_types=retained,
                redispatch_refused=refused, executor_calls=len(calls),
                sealed=reader._sealed, diverged=list(reader._diverged), in_flight=list(reader._in_flight))


def two_honest_detached_interruptions():
    account, held, mode, reader = _simple()
    reader._follow = lambda: ({k:BudgetLedger.from_dict(v.to_dict()) for k,v in held.items()}, {})
    real = BudgetReader._handed
    outcomes=[]
    for n in range(2):
        armed=[True]
        def interrupt(*args):
            if armed[0]:
                armed[0]=False
                raise KeyboardInterrupt("one interruption per independent verification")
            return real(*args)
        with patch.object(BudgetReader, "_handed", staticmethod(interrupt)):
            try:
                reader.pinned()
            except KeyboardInterrupt:
                outcomes.append("KeyboardInterrupt")
        outcomes.append(dict(diverged=list(reader._diverged), unread=list(reader._unread_entries)))
    try:
        reader.read(OwnerKind.BUDGET_LEDGER,"a")
        final="accepted"
    except OwnerUnavailable as e:
        final=str(e)
    return dict(case="unchanged_detached_two_interruptions",outcomes=outcomes,final=final,sealed=reader._sealed)

if __name__ == "__main__":
    for phase in ("_retain_handing", "_handed"):
        print(json.dumps(interrupted_buffer(phase)),flush=True)
    print(json.dumps(two_honest_detached_interruptions()),flush=True)
