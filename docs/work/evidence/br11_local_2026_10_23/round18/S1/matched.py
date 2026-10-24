import json, sys, subprocess, traceback
from engcore.mind.world import BudgetReader
from engcore.mind.world import owners as ow
from engcore.sria.campaign.budget import BudgetLedger
from tests.mind.test_authority_review_r14 import _desk, _solver, _settle, _refused, ax
SHA="cc7ef06b0d08398173d9448ff47d8abb7e375d44"
assert subprocess.check_output(["git","-C","/home/dev_kaeem/forge-r18-review","rev-parse","HEAD"],text=True).strip()==SHA
assert ow.__file__=="/home/dev_kaeem/forge-r18-review/src/engcore/mind/world/owners.py"
print(json.dumps({"sha":SHA,"owners":ow.__file__,"python":sys.version,"executable":sys.executable,"recursion_limit":sys.getrecursionlimit()}))
def deep(n, reader):
    if n: return deep(n-1,reader)
    return reader.pinned()
def run(depth, detached):
    o=ax.owned("battery")
    lid=_solver(o)
    calls=[]
    def executor(authorization):
        calls.append(1)
        _settle(o.ledgers[lid],f"run.{len(calls)}")
    reader, authorities, gateway, result=_desk(o,lambda:(dict(o.ledgers),dict(o.experiments)) if detached else (o.ledgers,o.experiments),executor)
    checkpoint=BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(result.admitted)
    failure=None
    try: deep(depth,reader)
    except BaseException as exc:
        failure={"type":type(exc).__name__,"message":str(exc),"tail":[[x.name,x.lineno] for x in traceback.extract_tb(exc.__traceback__)[-8:]]}
    pending=[(k,type(v).__name__) for k,v in reader._uncompared.items()]
    unread={str(k):len(v) for k,v in reader._unread_entries.items()}
    o.ledgers[lid]=checkpoint
    try: refused=_refused(gateway,result.admitted)
    except BaseException as exc: refused=type(exc).__name__
    out={"detached":detached,"depth":depth,"failure":failure,"pending_before_restore":pending,"unread_before_restore":unread,"redispatch_refused":refused,"calls":len(calls),"sealed":reader._sealed,"inflight":list(reader._in_flight)}
    print(json.dumps(out),flush=True)
    return out

sys.setrecursionlimit(150)
results=[]
for detached in (False, True):
    for depth in range(140,147):
        results.append(run(depth,detached))
live=[r for r in results if not r['detached'] and r['pending_before_restore'] and r['calls']==2]
assert live, results
for bad in live:
    control=next(r for r in results if r['detached'] and r['depth']==bad['depth'])
    assert control['pending_before_restore'] and control['calls']==1 and control['redispatch_refused'] is True, control
print(json.dumps({'matched_defect_depths':[r['depth'] for r in live],'controls':'refuse'}))
