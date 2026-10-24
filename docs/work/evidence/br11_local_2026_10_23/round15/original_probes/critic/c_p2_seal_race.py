"""R15-C probe 2: CRIT14-1's seal is checked only when a verification STARTS (owners.py pinned(): `if self._sealed`),
never when it compares.  A verification that started before the seal, and is handed a restore after it, accepts the
restore: the spend handed in a non-dict mapping (MappingProxyType, CRIT14-1's honest trigger) is re-authorized and
the same admitted action is dispatched again.  Control ('sequential'): the same steps with the slow verification
starting after the seal are refused."""
import sys, threading, types
from common import *

ORDER = sys.argv[1]
o = ax.owned("battery")
lid = next(k for k in o.ledgers if k.endswith(".solver"))
state = {"proxy": False}
go1, v1_asking = threading.Event(), threading.Event()


def accounts():
    if threading.current_thread().name == "V1":
        v1_asking.set()
        go1.wait(10)                          # V1's accounts() is slow (e.g. waits on the execution side's lock)
    ledgers = dict(o.ledgers)
    return (types.MappingProxyType(ledgers) if state["proxy"] else ledgers), dict(o.experiments)


calls = []
def executor(authorization):
    calls.append(1)
    o.ledgers[lid].settle(charge_id=f"run.{len(calls)}", action_id="simulate_pulse", iteration=len(calls),
                          family=ActionFamily.EXPLORE, realized=1.0)


reader, authorities, gateway, r = desk(o, accounts, executor)
s0 = BudgetLedger.from_dict(o.ledgers[lid].to_dict())          # checkpoint before the spend
gateway.dispatch(r.admitted)                                    # executes: run.1 (S1)
print("after first dispatch: executor calls", len(calls))

out = {}
def v1():                                                       # a second dispatch of the SAME admitted action
    try:
        gateway.dispatch(r.admitted)
        out["v1"] = "DISPATCHED AGAIN"
    except DispatchRefused as exc:
        out["v1"] = "dispatch refused: " + str(exc)[:220]

t1 = threading.Thread(target=v1, name="V1")
if ORDER == "concurrent":
    t1.start()
    assert v1_asking.wait(10)                                   # V1 passed the seal check and is asking accounts()
# V2: the spend S1 is handed in a MappingProxyType -> the reader seals
state["proxy"] = True
try:
    reader.read(OwnerKind.BUDGET_LEDGER, lid)
    print("V2: read?!")
except OwnerUnavailable as exc:
    print("V2:", str(exc)[:140])
print("sealed:", reader._sealed is not None)
state["proxy"] = False
o.ledgers[lid] = BudgetLedger.from_dict(s0.to_dict())          # checkpoint restore (sria.campaign pattern)
if ORDER != "concurrent":
    t1.start()
go1.set()
t1.join(15)
print("ORDER", ORDER, "| V1:", out.get("v1"), "| executor calls:", len(calls))
print("charge ids now:", [c.charge_id for c in o.ledgers[lid].charges])
try:
    reader.read(OwnerKind.BUDGET_LEDGER, lid)
    print("later read: served")
except OwnerUnavailable as exc:
    print("later read refused:", str(exc)[:100])
