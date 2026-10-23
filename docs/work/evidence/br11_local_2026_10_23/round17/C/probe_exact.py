import sys,json,subprocess
from engcore.mind.world import owners,BudgetReader
from engcore.sria.campaign.budget import BudgetLedger
from tests.mind.test_authority_review_r14 import _desk,_solver,_settle,_refused,ax
assert owners.__file__=="/home/dev_kaeem/forge-r17-review/src/engcore/mind/world/owners.py"
assert subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()=="98d72b2ef854012780f4222706884b911c4a2f03"
def deep(n,r):
    if n:return deep(n-1,r)
    return r.pinned()
o=ax.owned("battery");lid=_solver(o);calls=[]
def execute(auth):
    calls.append(1);_settle(o.ledgers[lid],f"run.{len(calls)}")
r,_,gateway,admitted=_desk(o,lambda:(o.ledgers,o.experiments),execute)
saved=BudgetLedger.from_dict(o.ledgers[lid].to_dict());gateway.dispatch(admitted.admitted)
spent=o.ledgers[lid];limit=sys.getrecursionlimit()
try:
    sys.setrecursionlimit(150);deep(145,r)
except RecursionError:pass
finally:sys.setrecursionlimit(limit)
pending=list(r._uncompared.values())
assert len(pending)==1 and type(pending[0]) is tuple
assert pending[0][0] is o.ledgers and pending[0][0][lid] is spent
before=spent.revision;o.ledgers[lid]=saved
after=pending[0][0][lid].revision
refused=_refused(gateway,admitted.admitted)
row=dict(pending_returned_mapping_is_owner_mapping=True,pending_spent_revision=before,pending_after_restore_revision=after,restored_revision=saved.revision,refused=refused,executor_calls=len(calls),sealed=r._sealed)
print(json.dumps(row));assert not refused and len(calls)==2
