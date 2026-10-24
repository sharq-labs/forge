from pathlib import Path
import json, sys, subprocess, traceback
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world import owners
from engcore.mind.world.authority import OwnerUnavailable
from engcore.sria.campaign.budget import BudgetLedger
from tests.mind.test_authority_review_r14 import _desk, _solver, _settle, _refused, ax
SHA="b8a65bb9d02b5a18e0a8b26779773c1552204dc1"
ROOT="/home/dev_kaeem/forge-r16-review"
assert subprocess.check_output(["git","-C",ROOT,"rev-parse","HEAD"],text=True).strip()==SHA
assert owners.__file__==ROOT+"/src/engcore/mind/world/owners.py"
print(json.dumps({"identity":{"sha":SHA,"python":sys.version,"owners":owners.__file__}}),flush=True)
rows=[]
def emit(row):
 rows.append(row); print(json.dumps(row),flush=True)
def scenario(kind, checkpoint=None, failures=0, failure=KeyboardInterrupt, detached=False, restore=True, depth=None, fresh_object=False):
 o=ax.owned("battery"); lid=_solver(o); calls=[]; handed=[]
 def accounts():
  handed.append(len(o.ledgers[lid].charges))
  return (dict(o.ledgers),dict(o.experiments)) if detached else (o.ledgers,o.experiments)
 def executor(authorization):
  if fresh_object:
   o.ledgers[lid]=BudgetLedger.from_dict(o.ledgers[lid].to_dict())
  calls.append(authorization)
  _settle(o.ledgers[lid],f"run.{len(calls)}")
 reader,authorities,gateway,result=_desk(o,accounts,executor)
 saved=BudgetLedger.from_dict(o.ledgers[lid].to_dict())
 gateway.dispatch(result.admitted)
 initial_charge_count=len(saved.charges); spent_charge_count=len(o.ledgers[lid].charges)
 assert spent_charge_count==initial_charge_count+1
 original=BudgetReader._retain_handing; hits=[]; caught=None
 def trace(frame,event,arg):
  if event=="line" and frame.f_code is BudgetReader.pinned.__code__ and frame.f_lineno==checkpoint and not hits:
   hits.append({"line":checkpoint,"handed":frame.f_locals["handed"],"mapping_in_locals":"mapping" in frame.f_locals,"callback_charge_count":handed[-1]})
   raise KeyboardInterrupt("single transition checkpoint")
  return trace
 def fail_capture(value):
  if len(hits)<failures:
   hits.append({"attempt":len(hits)+1})
   raise failure("native capture checkpoint")
  return original(value)
 def descend(n):
  if n: return descend(n-1)
  return reader.pinned()
 try:
  if kind=="line": sys.settrace(trace)
  if kind=="capture": BudgetReader._retain_handing=staticmethod(fail_capture)
  try:
   descend(depth) if depth is not None else reader.pinned()
  except BaseException as exc:
   caught=type(exc).__name__
 finally:
  sys.settrace(None); BudgetReader._retain_handing=staticmethod(original)
 before={"pending":[type(v).__name__ for v in reader._uncompared.values()],"unread":{str(k):len(v) for k,v in reader._unread_entries.items()},"sealed":reader._sealed,"diverged":list(map(str,reader._diverged)),"in_flight":list(reader._in_flight)}
 if restore: o.ledgers[lid]=saved
 refused=_refused(gateway,result.admitted)
 current_readable=True
 try: reader.read(OwnerKind.BUDGET_LEDGER,lid)
 except OwnerUnavailable: current_readable=False
 row={"kind":kind,"checkpoint":checkpoint,"failure":failure.__name__,"failures":failures,"detached":detached,"restore":restore,"depth":depth,"fresh_object":fresh_object,"caught":caught,"hits":hits,"callback_charge_count":handed[-2] if len(handed)>1 else None,"initial_charge_count":initial_charge_count,"spent_charge_count":spent_charge_count,"before":before,"redispatch_refused":refused,"executor_calls":len(calls),"current_readable":current_readable}
 if kind=="line":
  assert len(hits)==1 and hits[0]["mapping_in_locals"] and hits[0]["callback_charge_count"]==spent_charge_count
 emit(row)
for line in [974,977,978,979]: scenario("line",checkpoint=line)
for detached in [False,True]:
 for failure in [KeyboardInterrupt,MemoryError,RecursionError]:
  for failures in [0,1,2]: scenario("capture",failures=failures,failure=failure,detached=detached)
for checkpoint in [974,977]: scenario("line",checkpoint=checkpoint,restore=False)
for failures in [1,2]: scenario("capture",failures=failures,restore=False)
# A normal owner may replace an account before settle too: the reader's initial account is not a history journal.
scenario("capture",failures=2,fresh_object=True)
for depth in range(985,998): scenario("native",depth=depth)
Path("/home/dev_kaeem/br11-review/r16/S1/probe_rows.json").write_text(json.dumps(rows,indent=2))
