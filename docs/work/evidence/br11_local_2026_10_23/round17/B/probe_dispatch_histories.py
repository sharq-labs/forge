import itertools,json
from engcore.mind.world import BudgetReader
from engcore.sria.campaign.budget import BudgetLedger
from tests.mind.test_authority_review_r14 import _desk,_solver,_settle,_refused,_readmitted,ax
from tests.mind.test_authority_review_r16 import _interrupt_handing
rows=[]
for order in itertools.permutations(('base','spent','extended')):
 o=ax.owned('battery');lid=_solver(o);calls=[]
 def execute(auth):
  calls.append(1);_settle(o.ledgers[lid],f'run.{len(calls)}')
 def accounts():
  return {k:BudgetLedger.from_dict(v.to_dict()) for k,v in o.ledgers.items()},dict(o.experiments)
 reader,authority,gateway,r=_desk(o,accounts,execute)
 versions={'base':BudgetLedger.from_dict(o.ledgers[lid].to_dict())}
 gateway.dispatch(r.admitted);versions['spent']=BudgetLedger.from_dict(o.ledgers[lid].to_dict())
 _settle(o.ledgers[lid],'extra');versions['extended']=BudgetLedger.from_dict(o.ledgers[lid].to_dict())
 for label in order:
  o.ledgers[lid]=versions[label];_interrupt_handing(reader)
 o.ledgers[lid]=versions['base']
 refused=_refused(gateway,r.admitted);readmitted=_readmitted(o,authority,gateway)
 row=dict(order=order,refused=refused,readmitted=readmitted,calls=len(calls),diverged=bool(reader._diverged));rows.append(row)
 assert refused and not readmitted and len(calls)==1,row
print(json.dumps(rows,indent=2))
