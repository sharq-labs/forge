"""R15-C probe 5: an exact BudgetLedger whose instance-level to_dict (an instance attribute shadows the class method:
owners.py:476 calls ledger.to_dict(), not BudgetLedger.to_dict(ledger)) states the pre-spend payload.  The reader
lists 3 entry objects before and after its read-back and decides on a 2-entry history: it serves D0 and the executed
action is dispatched again.  No exception is raised anywhere."""
from common import *
o = ax.owned("battery")
lid = next(k for k in o.ledgers if k.endswith(".solver"))
calls = []
def executor(a):
    calls.append(1)
    led = o.ledgers[lid]
    if len(calls) == 1:
        d0 = led.to_dict()
        object.__setattr__(led, "to_dict", lambda: dict(d0))
    led.settle(charge_id=f"run.{len(calls)}", action_id="simulate_pulse", iteration=len(calls),
               family=ActionFamily.EXPLORE, realized=1.0)
reader, authorities, gateway, r = desk(o, lambda: (dict(o.ledgers), dict(o.experiments)), executor)
gateway.dispatch(r.admitted)
print("charges held:", len(o.ledgers[lid].charges), "revision:", o.ledgers[lid].revision)
try:
    gateway.dispatch(r.admitted); print("liar: DISPATCHED AGAIN | executor calls", len(calls))
except DispatchRefused as exc:
    print("liar: refused", str(exc)[:150])
print("  _seen len", len(reader._seen[("ledger", lid)]), "_seen_entries len", len(reader._seen_entries.get(("ledger", lid), ())))
