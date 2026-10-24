import json,sys,subprocess
from unittest.mock import patch
from engcore.mind.world import BudgetReader
from engcore.mind.world import owners
from engcore.sria.campaign.budget import BudgetLedger
from tests.mind.test_authority_review_r14 import _desk,_solver,_settle,_refused,ax
SHA=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
assert SHA=='b8a65bb9d02b5a18e0a8b26779773c1552204dc1'
assert owners.__file__=='/home/dev_kaeem/forge-r16-review/src/engcore/mind/world/owners.py'
print(json.dumps(dict(sha=SHA,owners=owners.__file__,python=sys.executable)))
def case(mode,detached=False,depth=None):
 o=ax.owned('battery'); lid=_solver(o); calls=[]; handed=[]
 def account():
  handed.append(o.ledgers[lid].revision)
  return (dict(o.ledgers),dict(o.experiments)) if detached else (o.ledgers,o.experiments)
 def execute(a):
  calls.append(1); _settle(o.ledgers[lid],f'run.{len(calls)}')
 reader,_,gateway,result=_desk(o,account,execute)
 checkpoint=BudgetLedger.from_dict(o.ledgers[lid].to_dict()); gateway.dispatch(result.admitted)
 count=[0]; original=BudgetReader._retain_handing
 def fail(mapping):
  count[0]+=1
  if count[0]<=int(mode): raise KeyboardInterrupt('S2 capture checkpoint')
  return original(mapping)
 def trace(frame,event,arg):
  if event=='line' and frame.f_code is BudgetReader.pinned.__code__ and frame.f_lineno==int(mode[1:]):
   sys.settrace(None); raise KeyboardInterrupt('S2 post-return checkpoint')
  return trace
 def deep(n):
  if n: return deep(n-1)
  return reader.pinned()
 error=None
 try:
  if mode.startswith('L'): sys.settrace(trace); reader.pinned()
  elif mode=='native': deep(depth)
  else:
   with patch.object(BudgetReader,'_retain_handing',staticmethod(fail)): reader.pinned()
 except BaseException as exc: error=type(exc).__name__
 finally: sys.settrace(None)
 pending=[type(v).__name__ for v in reader._uncompared.values()]
 last_handed=handed[-1]; checkpoint_revision=checkpoint.revision; o.ledgers[lid]=checkpoint
 refused=_refused(gateway,result.admitted)
 row=dict(mode=mode,detached=detached,depth=depth,error=error,interrupt_attempts=count[0],pending=pending,handed_revision=last_handed,checkpoint_revision=checkpoint_revision,calls=len(calls),refused=refused,sealed=reader._sealed)
 print(json.dumps(row),flush=True)
for mode in ['L974','L977','L978','L979','0','1','2']:
 case(mode)
case('2',True)
for n in range(989,997): case('native',depth=n)
