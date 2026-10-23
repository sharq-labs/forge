import json, sys, subprocess
from unittest.mock import patch
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world import owners as ow
from engcore.mind.world.authority import OwnerUnavailable
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily
from tests.mind.test_authority_review_r14 import _desk, _solver, _settle, _refused, ax

print(json.dumps({"sha":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),"python":sys.executable,"owners":ow.__file__}))
assert ow.__file__ == "/home/dev_kaeem/forge-r16-review/src/engcore/mind/world/owners.py"
assert subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip() == "b8a65bb9d02b5a18e0a8b26779773c1552204dc1"

def pending_native_capture(failure, direct):
    o=ax.owned("battery")
    lid=_solver(o)
    calls=[]
    def execute(authorization):
        calls.append(1)
        _settle(o.ledgers[lid],f"run.{len(calls)}")
    def accounts():
        return (o.ledgers if direct else dict(o.ledgers)), dict(o.experiments)
    reader, authorities, gateway, admitted=_desk(o,accounts,execute)
    saved=BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(admitted.admitted)
    real=BudgetReader._retain_handing
    checkpoints=[]
    def interrupted(handed):
        if len(checkpoints)<2:
            checkpoints.append("before native snapshot")
            raise failure("explicit native-snapshot checkpoint")
        return real(handed)
    with patch.object(BudgetReader,"_retain_handing",staticmethod(interrupted)):
        try: reader.pinned()
        except failure: pass
        else: raise AssertionError("interrupted pin succeeded")
    retained=[type(v).__name__ for v in reader._uncompared.values()]
    o.ledgers[lid]=saved
    refused=_refused(gateway,admitted.admitted)
    print(json.dumps({"case":"pending_native_capture","failure":failure.__name__,"direct":direct,"checkpoints":len(checkpoints),"pending_type":retained,"refused":refused,"executions":len(calls),"sealed":reader._sealed,"diverged":reader._diverged}))

for failure in (KeyboardInterrupt,MemoryError,RecursionError):
    for direct in (False,True):
        pending_native_capture(failure,direct)

def normalization(iteration):
    account=BudgetLedger(total_budget=100.)
    _settle(account,"initial")
    held={"a":account}
    reader=BudgetReader.following(lambda:(held,{}))
    account.settle(charge_id="new",action_id="other",iteration=iteration,family=ActionFamily.EXPLORE,realized=.5)
    saved=BudgetLedger.from_dict(account.to_dict())
    real=BudgetReader._account
    armed=[True]
    def interrupted(self,key):
        if armed:
            armed.pop()
            raise KeyboardInterrupt("explicit read checkpoint")
        return real(self,key)
    with patch.object(BudgetReader,"_account",interrupted):
        try: reader.pinned()
        except KeyboardInterrupt: pass
    held["a"]=saved
    try:
        result=reader.read(OwnerKind.BUDGET_LEDGER,"a")
        outcome="accepted"
    except OwnerUnavailable as exc:
        outcome=str(exc)
    print(json.dumps({"case":"raw_history_normalization","iteration":iteration,"outcome":outcome,"diverged":{str(k):v for k,v in reader._diverged.items()}}))
for iteration in (1,1.0,"1"):
    normalization(iteration)
