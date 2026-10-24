from pathlib import Path
import json,sys,subprocess,gc,weakref
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world import owners
from engcore.mind.world.authority import OwnerUnavailable
from engcore.sria.campaign.budget import BudgetLedger,BudgetCharge
from engcore.sria.decision import ActionFamily
from tests.mind.test_authority_review_r14 import _desk,_solver,_settle,_refused,ax
ROOT="/home/dev_kaeem/forge-r16-review"
assert subprocess.check_output(["git","-C",ROOT,"rev-parse","HEAD"],text=True).strip()=="b8a65bb9d02b5a18e0a8b26779773c1552204dc1"
assert owners.__file__==ROOT+"/src/engcore/mind/world/owners.py"
print(json.dumps({"sha":"b8a65bb9d02b5a18e0a8b26779773c1552204dc1","python":sys.version,"owners":owners.__file__}))
rows=[]
def emit(row): rows.append(row);print(json.dumps(row),flush=True)
def trace_capture(second_map=False,repeated=True):
 o=ax.owned("battery");lid=_solver(o);calls=[]
 def executor(a): calls.append(a);_settle(o.ledgers[lid],f"run.{len(calls)}")
 reader,authorities,gateway,result=_desk(o,lambda:(o.ledgers,o.experiments),executor)
 saved=BudgetLedger.from_dict(o.ledgers[lid].to_dict());gateway.dispatch(result.admitted)
 target=o.experiments if second_map else o.ledgers
 hits=[]
 def trace(frame,event,arg):
  if event=="call" and frame.f_code is owners._items.__code__ and frame.f_locals["mapping"] is target and len(hits)<(2 if repeated else 1):
   hits.append(len(hits)+1);raise KeyboardInterrupt("trace native capture")
  return trace
 def profile(frame,event,arg):
  if event=="call" and frame.f_code is BudgetReader._recover_handing.__code__:
   sys.settrace(trace)
 sys.setprofile(profile);sys.settrace(trace)
 try:
  try: reader.pinned()
  except KeyboardInterrupt: pass
 finally: sys.settrace(None);sys.setprofile(None)
 pending=[type(v).__name__ for v in reader._uncompared.values()]
 o.ledgers[lid]=saved
 refused=_refused(gateway,result.admitted)
 assert len(hits)==(2 if repeated else 1)
 assert len(calls)==(2 if repeated else 1)
 emit({"case":"production_unmodified_trace_profile","second_map":second_map,"repeated":repeated,"hits":hits,"pending":pending,"redispatch_refused":refused,"executor_calls":len(calls)})
for second_map in [False,True]:
 for repeated in [False,True]: trace_capture(second_map,repeated)

def normalize(iteration=1,constructor_numeric=False,interrupt=True):
 initial=BudgetLedger(total_budget=100.);_settle(initial,"initial")
 held={"a":initial};reader=BudgetReader.following(lambda:(held,{}))
 if constructor_numeric:
  held["a"]=BudgetLedger(total_budget=100.,charges=initial.charges+(BudgetCharge(charge_id="next",action_id="other",iteration=1,family=ActionFamily.EXPLORE,realized=1,from_general_pool=1),))
 else:
  held["a"].settle(charge_id="next",action_id="other",iteration=iteration,family=ActionFamily.EXPLORE,realized=.5)
 payload=held["a"].to_dict();hits=[]
 def trace(frame,event,arg):
  if event=="call" and frame.f_code is BudgetReader._account.__code__ and not hits:
   hits.append(1);raise KeyboardInterrupt("interrupt before owner readback")
  return trace
 if interrupt:sys.settrace(trace)
 try:
  try:reader.pinned()
  except KeyboardInterrupt:pass
 finally:sys.settrace(None)
 held["a"]=BudgetLedger.from_dict(payload)
 refusal=None
 try:reader.read(OwnerKind.BUDGET_LEDGER,"a")
 except OwnerUnavailable as exc:refusal=str(exc)
 emit({"case":"normalization","iteration":iteration,"constructor_numeric":constructor_numeric,"interrupt":interrupt,"refusal":refusal,"permanent":bool(reader._diverged)})
for it in [1,1.0,"1"]:
 for interrupted in [False,True]:normalize(it,interrupt=interrupted)
for interrupted in [False,True]:normalize(constructor_numeric=True,interrupt=interrupted)

def detached_interrupted(detached,count):
 account=BudgetLedger(total_budget=100.);_settle(account,"initial")
 held={"a":account}
 def accounts():return ({k:BudgetLedger.from_dict(v.to_dict()) for k,v in held.items()} if detached else held),{}
 reader=BudgetReader.following(accounts);_settle(account,"next")
 for _ in range(count):
  hits=[]
  def trace(frame,event,arg):
   if event=="call" and frame.f_code is BudgetReader._handed.__func__.__code__ and not hits:
    hits.append(1);raise KeyboardInterrupt("interrupted detached parse")
   return trace
  sys.settrace(trace)
  try:
   try:reader.pinned()
   except KeyboardInterrupt:pass
  finally:sys.settrace(None)
 refusal=None
 try:reader.read(OwnerKind.BUDGET_LEDGER,"a")
 except OwnerUnavailable as exc:refusal=str(exc)
 emit({"case":"detached_interrupt","detached":detached,"count":count,"refusal":refusal,"permanent":bool(reader._diverged)})
for detached in [False,True]:
 for count in [1,2]:detached_interrupted(detached,count)

# Show why retaining the construction-time account cannot recover a never-captured replacement.
# All accounting mutations use the public owner API; private fields below are read only.
def indistinguishable(spend):
 initial=BudgetLedger(total_budget=100.);_settle(initial,"initial")
 held={"a":initial};reader=BudgetReader.following(lambda:(held,{}));reader.pinned()
 baseline=initial.to_dict()
 replacement=BudgetLedger.from_dict(baseline)
 if spend:_settle(replacement,"spend")
 victim=weakref.ref(replacement);held["a"]=replacement;del replacement
 original=BudgetReader._retain_handing;hits=[]
 def fault(value):
  if len(hits)<2:hits.append(1);raise KeyboardInterrupt("pre-capture interruption")
  return original(value)
 BudgetReader._retain_handing=staticmethod(fault)
 try:
  try:reader.pinned()
  except KeyboardInterrupt:pass
 finally:BudgetReader._retain_handing=staticmethod(original)
 held["a"]=BudgetLedger.from_dict(baseline);gc.collect()
 state={"seen":{str(k):v for k,v in reader._seen.items()},"unread":reader._unread_entries,"diverged":reader._diverged,"pending":[[type(v).__name__,v[0]["a"].to_dict()] for v in reader._uncompared.values()],"initial_account":reader._ledgers["a"].to_dict(),"tickets":reader._tickets,"in_flight":list(reader._in_flight),"sealed":reader._sealed,"replacement_gone":victim() is None}
 accepted=reader.read(OwnerKind.BUDGET_LEDGER,"a") is not None
 emit({"case":"indistinguishable","spent":spend,"state":state,"accepted":accepted})
 return state
assert indistinguishable(False)==indistinguishable(True)
Path("/home/dev_kaeem/br11-review/r16/S1/followup_rows.json").write_text(json.dumps(rows,indent=2))
