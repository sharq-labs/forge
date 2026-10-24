"""R15-C probe 3: the read-back's history is never compared with the entry objects listed just before and just after
it.  An in-place rollback-and-reapply of the same entry object during the read-back (before == after, so the 7b4a0de8
after-listing sees nothing) makes the reader (a) serve the state the account moved past, and (b) record
_seen_entries holding run.1, whose content was never read; the 7b4a0de8 prefix exemption then records NOTHING for a
later state holding run.1 that is not read back, and a checkpoint restore re-dispatches the executed action.
modes: direct | exemption | control (exemption steps without the ABA verification)."""
import sys
from common import *

MODE = sys.argv[1]
o = ax.owned("battery")
lid = next(k for k in o.ledgers if k.endswith(".solver"))
ctl = {"aba": False, "moving": False, "armed": False, "run1": None}


class H0:                                   # detail of an earlier, observed charge: re-applies run.1 when armed
    def __str__(self):
        if ctl["armed"]:
            ctl["armed"] = False
            led = o.ledgers[lid]
            object.__setattr__(led, "charges", led.charges + (ctl["run1"],))
        return "other.0"


class H1:                                   # detail of the spend run.1
    def __str__(self):
        if ctl["aba"]:
            ctl["aba"] = False
            led = o.ledgers[lid]
            object.__setattr__(led, "charges", led.charges[:-1])   # roll back in place ...
            ctl["armed"] = True                                    # ... H0 re-applies it on the next attempt
            raise RuntimeError("dictionary changed size during iteration")
        if ctl["moving"]:
            raise RuntimeError("dictionary changed size during iteration")
        return "run.1"


o.ledgers[lid].settle(charge_id="other.0", action_id="other", iteration=0, family=ActionFamily.EXPLORE,
                      realized=0.5, detail=H0())
calls = []
def executor(authorization):
    calls.append(1)
    c = o.ledgers[lid].settle(charge_id=f"run.{len(calls)}", action_id="simulate_pulse", iteration=len(calls),
                              family=ActionFamily.EXPLORE, realized=1.0, detail=H1() if len(calls) == 1 else "")
    if len(calls) == 1:
        ctl["run1"] = c


reader, authorities, gateway, r = desk(o, lambda: (dict(o.ledgers), dict(o.experiments)), executor)
s0 = BudgetLedger.from_dict(o.ledgers[lid].to_dict())           # the checkpoint before the spend (D0)
gateway.dispatch(r.admitted)
ids = lambda: [c.charge_id for c in o.ledgers[lid].charges]
print("after first dispatch: calls", len(calls), ids())
if MODE == "direct":
    ctl["aba"] = True
    try:
        gateway.dispatch(r.admitted)
        print("direct: DISPATCHED AGAIN | calls", len(calls), ids())
    except DispatchRefused as exc:
        print("direct: refused", str(exc)[:160], "| calls", len(calls))
    sys.exit(0)
if MODE == "exemption":
    ctl["aba"] = True
    rec = reader.read(OwnerKind.BUDGET_LEDGER, lid)
    print("ABA verification served revision", rec.revision, "| account holds", ids())
    print("  _seen len", len(reader._seen[("ledger", lid)]), "_seen_entries len", len(reader._seen_entries.get(("ledger", lid), ())))
ctl["moving"] = True
try:
    reader.read(OwnerKind.BUDGET_LEDGER, lid)
    print("unread read served?!")
except OwnerUnavailable as exc:
    print("state holding run.1, not read back:", str(exc)[:80])
print("  _unread_entries:", {k: len(v) for k, v in reader._unread_entries.items()})
ctl["moving"] = False
o.ledgers[lid] = BudgetLedger.from_dict(s0.to_dict())           # checkpoint restore (object replaced), D0 content
try:
    gateway.dispatch(r.admitted)
    print(MODE, ": DISPATCHED AGAIN | calls", len(calls), ids())
except DispatchRefused as exc:
    print(MODE, ": dispatch refused:", str(exc)[:200], "| calls", len(calls))
