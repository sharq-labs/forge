import sys,json,subprocess,os
from engcore.mind.world import owners
from engcore.sria.campaign.budget import BudgetLedger
from tests.mind.test_authority_review_r14 import _desk,_solver,_settle,_refused,ax
os.chdir("/home/dev_kaeem/forge-r17-review")
assert owners.__file__=="/home/dev_kaeem/forge-r17-review/src/engcore/mind/world/owners.py"
assert subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()=="98d72b2ef854012780f4222706884b911c4a2f03"
def recurse(n,reader):
    if n:return recurse(n-1,reader)
    return reader.pinned()
rows=[]
for depth in range(138,147):
    o=ax.owned("battery");lid=_solver(o);calls=[]
    def execute(auth):
        calls.append(1);_settle(o.ledgers[lid],f"run.{len(calls)}")
    reader,_,gateway,admitted=_desk(o,lambda:(o.ledgers,o.experiments),execute)
    checkpoint=BudgetLedger.from_dict(o.ledgers[lid].to_dict());gateway.dispatch(admitted.admitted)
    limit=sys.getrecursionlimit();error=None
    try:
        sys.setrecursionlimit(150);recurse(depth,reader)
    except RecursionError:error="RecursionError"
    finally:sys.setrecursionlimit(limit)
    pending=list(reader._uncompared.values()); raw=bool(pending and type(pending[0]) is tuple and pending[0][0] is o.ledgers)
    before=pending[0][0][lid].revision if raw else None
    o.ledgers[lid]=checkpoint
    after=pending[0][0][lid].revision if raw else None
    refused=_refused(gateway,admitted.admitted)
    row=dict(depth=depth,error=error,raw_returned_mapping=raw,before=before,after=after,refused=refused,calls=len(calls),sealed=reader._sealed)
    print(json.dumps(row));rows.append(row)
assert any(x["raw_returned_mapping"] and x["before"]>x["after"] and x["calls"]==2 and not x["refused"] for x in rows)
assert any(x["refused"] and x["calls"]==1 for x in rows)
