import json,sys,subprocess
from unittest.mock import patch
from engcore.mind.world import BudgetReader
from engcore.mind.world import owners
from engcore.sria.campaign.budget import BudgetLedger
from tests.mind.test_authority_review_r14 import _desk,_solver,_settle,_refused,_readmitted,ax
from tests.mind.test_authority_review_r16 import _interrupt_handing
SHA="cc7ef06b0d08398173d9448ff47d8abb7e375d44"
assert subprocess.check_output(["git","-C","/home/dev_kaeem/forge-r18-review","rev-parse","HEAD"],text=True).strip()==SHA
assert owners.__file__=="/home/dev_kaeem/forge-r18-review/src/engcore/mind/world/owners.py"
print(json.dumps(dict(sha=SHA,python=sys.version,owners=owners.__file__)))
def clone(x):
 return BudgetLedger.from_dict(json.loads(json.dumps(BudgetLedger.from_dict(x.to_dict()).to_dict(),sort_keys=True,default=str)))
def run(mode,detach=False,interrupts=0):
 o=ax.owned("battery");lid=_solver(o);calls=[]
 def accounts():
  return (dict(o.ledgers),dict(o.experiments)) if detach else (o.ledgers,o.experiments)
 def execute(auth):
  calls.append(1);_settle(o.ledgers[lid],f"run.{len(calls)}",{2:"a",10:"b"})
 reader,authority,gateway,r=_desk(o,accounts,execute)
 before=clone(o.ledgers[lid]);gateway.dispatch(r.admitted);spent=clone(o.ledgers[lid])
 if interrupts:
  real=BudgetReader._retain_handing;remaining=[interrupts]
  def fail(mapping):
   if remaining[0]:
    remaining[0]-=1;raise KeyboardInterrupt()
   return real(mapping)
  with patch.object(BudgetReader,"_retain_handing",staticmethod(fail)):
   try: reader.pinned()
   except KeyboardInterrupt: pass
 else: _interrupt_handing(reader)
 pending=len(reader._uncompared);unread=len(reader._unread_entries)
 if mode=="rollback": o.ledgers[lid]=before
 elif mode=="rewrite":
  _settle(before,"run.1",{2:"CHANGED",10:"b"});o.ledgers[lid]=clone(before)
 else: o.ledgers[lid]=spent
 refused=_refused(gateway,r.admitted)
 re_admitted=_readmitted(o,authority,gateway)
 row=dict(mode=mode,detach=detach,interrupts=interrupts,pending=pending,unread=unread,old_refused=refused,fresh_dispatched=re_admitted,calls=len(calls),sealed=reader._sealed,diverged=bool(reader._diverged))
 print(json.dumps(row),flush=True)
 if interrupts==2 and not detach and mode=="rollback": assert not refused and len(calls)>=2,row
 elif mode=="same": assert refused and re_admitted and len(calls)==2,row
 else: assert refused and not re_admitted and len(calls)==1,row
for m in ["same","rollback","rewrite"]:run(m)
for detached in [False,True]:
 for n in [1,2]:run("rollback",detached,n)
