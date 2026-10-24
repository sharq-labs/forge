"""Content raising KeyboardInterrupt: every verification re-raises it; is the account ever refused for good?"""
from common import *
from engcore.mind.world.authority import OwnerUnavailable
o = ax.owned("battery")
lid = next(k for k in o.ledgers if k.endswith(".solver"))
class KBI:
    def __str__(self):
        raise KeyboardInterrupt("from content")
side = BudgetLedger(total_budget=10.0)
side.settle(charge_id="c", action_id="x", iteration=1, family=ActionFamily.EXPLORE, realized=1.0, detail="ok")
reader = BudgetReader.following(lambda: ({**o.ledgers, "side.ledger": side}, dict(o.experiments)))
side.settle(charge_id="d", action_id="x", iteration=2, family=ActionFamily.EXPLORE, realized=1.0, detail=KBI())
for i in range(4):
    try:
        reader.read(OwnerKind.BUDGET_LEDGER, lid)
        print(i, "served the solver ledger")
    except KeyboardInterrupt as e:
        print(i, "KeyboardInterrupt escaped the read of an UNRELATED account:", e)
    except OwnerUnavailable as e:
        print(i, "refused:", str(e)[:100])
print("diverged:", list(reader._diverged), "unread:", {k: len(v) for k, v in reader._unread_entries.items()})
