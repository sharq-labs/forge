"""Probe 2 through the Mind-facing MindWorldPort.request_admission + execute (the slow verification is the port's execute)."""
import threading, types
from common import *
o = ax.owned("battery")
lid = next(k for k in o.ledgers if k.endswith(".solver"))
state = {"proxy": False}
go1, v1_asking = threading.Event(), threading.Event()
def accounts():
    if threading.current_thread().name == "V1":
        v1_asking.set(); go1.wait(10)
    ledgers = dict(o.ledgers)
    return (types.MappingProxyType(ledgers) if state["proxy"] else ledgers), dict(o.experiments)
calls = []
def executor(a):
    calls.append(1)
    o.ledgers[lid].settle(charge_id=f"run.{len(calls)}", action_id="simulate_pulse", iteration=len(calls),
                          family=ActionFamily.EXPLORE, realized=1.0)
reader, authorities, gateway, _ = desk(o, accounts, executor)
world = project_world(o.declaration, authorities)
port = MindWorldPort(FeasibleActionSpace.build(world))
res = port.request_admission(o.propose("simulate_pulse", *SIM, world=port.world), gateway)
s0 = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
port.execute(res.admitted, gateway)
out = {}
def v1():
    try:
        port.execute(res.admitted, gateway); out["v1"] = "DISPATCHED AGAIN"
    except DispatchRefused as exc:
        out["v1"] = "refused: " + str(exc)[:120]
t1 = threading.Thread(target=v1, name="V1"); t1.start(); assert v1_asking.wait(10)
state["proxy"] = True
try:
    reader.read(OwnerKind.BUDGET_LEDGER, lid)
except OwnerUnavailable as exc:
    print("V2:", str(exc)[:100])
state["proxy"] = False
o.ledgers[lid] = BudgetLedger.from_dict(s0.to_dict())
go1.set(); t1.join(15)
print("port execute in flight across the seal:", out.get("v1"), "| executor calls:", len(calls))
print("journal:", [j[0] for j in port.journal])
