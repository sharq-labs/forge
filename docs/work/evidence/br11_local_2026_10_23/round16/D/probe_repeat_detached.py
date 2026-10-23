import json,sys,subprocess
from unittest.mock import patch
from engcore.mind.world import BudgetReader,OwnerKind
from engcore.mind.world import owners as ow
from engcore.mind.world.authority import OwnerUnavailable
from engcore.sria.campaign.budget import BudgetLedger
from tests.mind.test_authority_review_r14 import _settle
print(json.dumps({"sha":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),"owners":ow.__file__,"python":sys.executable}))
assert ow.__file__ == "/home/dev_kaeem/forge-r16-review/src/engcore/mind/world/owners.py"
assert subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip() == "b8a65bb9d02b5a18e0a8b26779773c1552204dc1"
for detached in (False,True):
    for interruptions in (1,2):
        account=BudgetLedger(total_budget=100.)
        _settle(account,"initial")
        held={"a":account}
        def accounts():
            return ({"a":BudgetLedger.from_dict(account.to_dict())} if detached else held),{}
        reader=BudgetReader.following(accounts)
        _settle(account,"new")
        real=BudgetReader._handed.__func__
        for i in range(interruptions):
            armed=[True]
            def interrupted(cls,*args):
                if armed:
                    armed.pop()
                    raise KeyboardInterrupt("at handed parsing")
                return real(cls,*args)
            with patch.object(BudgetReader,"_handed",classmethod(interrupted)):
                try:reader.pinned()
                except KeyboardInterrupt:pass
        try:
            record=reader.read(OwnerKind.BUDGET_LEDGER,"a")
            outcome="accepted"
        except OwnerUnavailable as exc:
            outcome=str(exc)
        print(json.dumps({"detached":detached,"interruptions":interruptions,"outcome":outcome,"diverged":{str(k):v for k,v in reader._diverged.items()},"sealed":reader._sealed}))
