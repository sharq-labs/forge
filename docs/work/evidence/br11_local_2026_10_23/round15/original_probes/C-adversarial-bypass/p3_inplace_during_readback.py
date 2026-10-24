"""A state handed to ONE verification whose entries the reader listed ('before') is rewritten in place during that
verification's read-back (attempt 1's content rolls the handed ledger back and charges another action); attempt 2 reads
the rewrite back and it is accepted: the listed entries are never compared with what was read back."""
from common import *

o = ax.owned("battery")
lid = next(k for k in o.ledgers if k.endswith(".solver"))
calls = []
s0 = None


class RollbackNote:
    fired = False
    def __str__(self):
        if not RollbackNote.fired and s0 is not None:
            RollbackNote.fired = True
            led = o.ledgers[lid]
            other = BudgetLedger(total_budget=led.total_budget)
            other.settle(charge_id="other.1", action_id="other", iteration=2, family=ActionFamily.EXPLORE, realized=0.5)
            object.__setattr__(led, "charges", tuple(s0.charges) + other.charges)   # in place: back, plus another
            raise RuntimeError("dictionary changed size during iteration")
        return "note"


def executor(a):
    calls.append(1)
    o.ledgers[lid].settle(charge_id=f"run.{len(calls)}", action_id="simulate_pulse", iteration=len(calls),
                          family=ActionFamily.EXPLORE, realized=1.0, detail=RollbackNote() if len(calls) == 1 else "")
reader, authorities, gateway, r = desk(o, lambda: (dict(o.ledgers), dict(o.experiments)), executor)
s0 = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
gateway.dispatch(r.admitted)
print("handed S1 charge ids:", [c.charge_id for c in o.ledgers[lid].charges])
rec = reader.read(OwnerKind.BUDGET_LEDGER, lid)          # V1: handed S1, listed its entries, reads back the rewrite
print("V1 served revision", rec.revision, "charge ids now:", [c.charge_id for c in o.ledgers[lid].charges],
      "diverged:", list(reader._diverged), "unread:", reader._unread_entries)
print("re-admission:", readmit_via_port(o, authorities, gateway), "| executor calls:", len(calls))
