"""An honest transient failure followed by a checkpoint restore of UNCHANGED content (object replaced, as
sria.campaign restores) refuses the account for good."""
from common import *
o = ax.owned("battery")
eid = next(iter(o.experiments))
lid = next(k for k in o.ledgers if k.endswith(".solver"))
reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
led = o.ledgers[lid]
led.settle(charge_id="x.1", action_id="x", iteration=1, family=ActionFamily.EXPLORE, realized=1.0)
real = led.to_dict
state = {"moving": True}
def mutating():
    if state["moving"]:
        raise RuntimeError("dictionary changed size during iteration")
    return real()
object.__setattr__(led, "to_dict", mutating)
try:
    reader.read(OwnerKind.BUDGET_LEDGER, lid); print("unexpected read")
except OwnerUnavailable as e:
    print("transient:", str(e)[:90])
state["moving"] = False
o.ledgers[lid] = BudgetLedger.from_dict(real())          # restore of the same content, new objects
try:
    print("after restore:", reader.read(OwnerKind.BUDGET_LEDGER, lid).revision)
except OwnerUnavailable as e:
    print("after restore refused:", str(e)[:120], "| diverged:", bool(reader._diverged))
