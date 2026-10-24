"""Probe 1 again, the re-admission made through the Mind-facing MindWorldPort (request_admission + execute)."""
import threading, time
from common import *


class SlowMovingNote:
    def __str__(self):
        if threading.current_thread().name == "V1":
            time.sleep(0.2)
        cache = {"a": 1}
        for k in cache:
            cache[k + "x"] = 2
        return "unreached"


o = ax.owned("battery")
lid = next(k for k in o.ledgers if k.endswith(".solver"))
calls, v1_handed = [], threading.Event()
def accounts():
    m = (dict(o.ledgers), dict(o.experiments))
    if threading.current_thread().name == "V1":
        v1_handed.set()
    return m
def executor(a):
    calls.append(1)
    o.ledgers[lid].settle(charge_id=f"run.{len(calls)}", action_id="simulate_pulse", iteration=len(calls),
                          family=ActionFamily.EXPLORE, realized=1.0, detail=SlowMovingNote() if len(calls) == 1 else "")
reader, authorities, gateway, r = desk(o, accounts, executor)
s0 = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
gateway.dispatch(r.admitted)
t1 = threading.Thread(target=lambda: _ign(), name="V1")
def _ign():
    try:
        reader.read(OwnerKind.BUDGET_LEDGER, lid)
    except OwnerUnavailable:
        pass
t1 = threading.Thread(target=_ign, name="V1"); t1.start(); assert v1_handed.wait(10)
o.ledgers[lid] = BudgetLedger.from_dict(s0.to_dict())
for i in (1, 2):
    o.ledgers[lid].settle(charge_id=f"other.{i}", action_id="other", iteration=1 + i, family=ActionFamily.EXPLORE, realized=0.5)
print("port re-admission:", readmit_via_port(o, authorities, gateway), "| executor calls:", len(calls))
t1.join(10)
print("charge ids now:", [c.charge_id for c in o.ledgers[lid].charges])
