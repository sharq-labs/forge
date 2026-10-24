import sys, json, subprocess
from engcore.mind.world import owners, BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable
from engcore.sria.campaign.budget import BudgetLedger
from engcore.scientific import to_json
from engcore.scientific.experiments.experiment import ScientificExperiment
from engcore.scientific.experiments.evaluation import ScientificEvaluation, EvaluationStatus
from tests.mind.test_authority_review_r14 import _desk, _solver, _settle, _refused, ax
sha=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
assert sha=="98d72b2ef854012780f4222706884b911c4a2f03"
assert owners.__file__=="/home/dev_kaeem/forge-r17-review/src/engcore/mind/world/owners.py"
print(json.dumps(dict(sha=sha,import_path=owners.__file__,python=sys.version)))
def recurse(n, reader):
    if n:return recurse(n-1,reader)
    return reader.pinned()
rows=[]
for depth in range(138,149):
    o=ax.owned("battery"); lid=_solver(o); calls=[]
    def execute(auth):
        calls.append(1); _settle(o.ledgers[lid],"s1."+str(len(calls)))
    reader,_,gateway,admitted=_desk(o,lambda:(o.ledgers,o.experiments),execute)
    old=BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(admitted.admitted)
    spent=o.ledgers[lid]; prior=sys.getrecursionlimit(); error=None
    try:
        sys.setrecursionlimit(150); recurse(depth,reader)
    except BaseException as e:error=type(e).__name__
    finally:sys.setrecursionlimit(prior)
    pending=list(reader._uncompared.values())
    raw=bool(len(pending)==1 and type(pending[0]) is tuple and pending[0][0] is o.ledgers and pending[0][0][lid] is spent)
    spent_rev=spent.revision
    o.ledgers[lid]=old
    restored=old.revision
    refused=_refused(gateway,admitted.admitted)
    row=dict(depth=depth,error=error,raw_returned_handing=raw,pending_types=[type(x).__name__ for x in pending],spent_revision=spent_rev,restored_revision=restored,refused=refused,calls=len(calls),sealed=reader._sealed)
    rows.append(row);print(json.dumps(row))
assert any(r['raw_returned_handing'] and not r['refused'] and r['calls']==2 for r in rows)
assert any(r['refused'] and r['calls']==1 for r in rows)
# Independent one-shot post-retention interrupt, then owner JSON detachment.
normal=[]
for kind in ['ledger','experiment']:
    if kind=='ledger':
        a=BudgetLedger(total_budget=100.); key='account';held=[a]
        follow=lambda:({key:held[0]}, {})
        k=OwnerKind.BUDGET_LEDGER
    else:
        o=ax.owned('battery');key,a=next(iter(o.experiments.items()));held=[a]
        follow=lambda:({}, {key:held[0]})
        k=OwnerKind.EXPERIMENT
    r=BudgetReader.following(follow)
    if kind=='ledger':
        a.settle(charge_id='numeric',action_id='numeric',iteration=1,family='explore',realized=1.,detail={2:'a',10:'b'})
        clone=lambda:BudgetLedger.from_dict(json.loads(json.dumps(a.to_dict(),sort_keys=True,default=str)))
    else:
        a.record(ScientificEvaluation('numeric',{},status=EvaluationStatus.NOT_CONVERGED,metadata={'keys':{2:'a',10:'b'}}))
        clone=lambda:ScientificExperiment.from_dict(json.loads(to_json(a)))
    hit=[]
    def trace(frame,event,arg):
        if event=='call' and frame.f_code is BudgetReader._handed.__func__.__code__ and not hit:
            hit.append(1);raise KeyboardInterrupt()
        return trace
    sys.settrace(trace)
    try:r.pinned()
    except KeyboardInterrupt:pass
    finally:sys.settrace(None)
    assert hit and r._unread_entries
    held[0]=clone()
    fresh=BudgetReader.following(follow)
    assert fresh.read(k,key) is not None
    try:r.read(k,key); outcome='accepted'
    except OwnerUnavailable as e:outcome=str(e)
    assert r._diverged and 'rewrote' in outcome
    row=dict(kind=kind,fresh_accepts=True,interrupted_original=outcome,permanent_divergence=bool(r._diverged));normal.append(row);print(json.dumps(row))
print('S1 counterexamples confirmed: native lost handing and both numeric-key owner histories')
