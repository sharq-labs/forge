from __future__ import annotations
import json,sys,traceback
from engcore.mind.world import BudgetReader
from engcore.sria.campaign.budget import BudgetLedger
from tests.mind.test_authority_review_r14 import _desk, _solver, _settle, _refused, ax

def deep(n,reader):
    if n:
        return deep(n-1,reader)
    return reader.pinned()

for depth in range(144,147):
    o=ax.owned("battery")
    lid=_solver(o)
    calls=[]
    def executor(auth):
        calls.append(1)
        _settle(o.ledgers[lid],f"run.{len(calls)}")
    reader,authorities,gateway,result=_desk(o,lambda:(dict(o.ledgers),dict(o.experiments)),executor)
    checkpoint=BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(result.admitted)
    limit=sys.getrecursionlimit()
    exc=None
    try:
        sys.setrecursionlimit(150)
        deep(depth,reader)
    except BaseException as e:
        exc=e
    finally:
        sys.setrecursionlimit(limit)
    retained=[type(x).__name__ for x in reader._uncompared.values()]
    frames=[f.name for f in traceback.extract_tb(exc.__traceback__)][-12:] if exc else []
    o.ledgers[lid]=checkpoint
    refused=_refused(gateway,result.admitted)
    print(json.dumps(dict(depth=depth,limit=150,exception=type(exc).__name__ if exc else None,frames=frames,
                         pending_types=retained,redispatch_refused=refused,executor_calls=len(calls),
                         sealed=reader._sealed,diverged=list(reader._diverged))),flush=True)
