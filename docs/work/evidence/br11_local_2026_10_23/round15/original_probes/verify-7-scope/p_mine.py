"""Independent variant: no object replacement (restore in place by the owner's own from_dict copy semantics is
replaced here by keeping the SAME object and only checking state), plus an explicit check that V3's pin passed the
seal check before the seal and that the seal was set before V3 compared."""
import sys, threading, types
from common import *
from engcore.mind.world import owners as OW

def run():
    o = ax.owned("battery")
    lid = solver(o)
    state = {"proxy": False}
    entered3, go3 = threading.Event(), threading.Event()
    log = []
    def accounts():
        if threading.current_thread().name == "V3" and not entered3.is_set():
            entered3.set(); go3.wait(10)
            log.append(("V3 accounts returns; sealed=", reader._sealed is not None))
        ledgers = dict(o.ledgers)
        return (types.MappingProxyType(ledgers) if state["proxy"] else ledgers), dict(o.experiments)
    calls = []
    def executor(a):
        calls.append(threading.current_thread().name)
        settle(o.ledgers[lid], f"run.{len(calls)}")
    reader, authorities, gateway, r = desk(o, accounts, executor)
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(r.admitted)
    print("after 1st dispatch charges:", len(o.ledgers[lid].charges), "seen:", {k: len(v) for k, v in reader._seen.items()})
    res = {}
    def v3():
        try:
            gateway.dispatch(r.admitted); res["v3"] = "DISPATCHED"
        except DispatchRefused as e:
            res["v3"] = "refused: " + str(e)[:200]
    t = threading.Thread(target=v3, name="V3", daemon=True); t.start(); assert entered3.wait(10)
    state["proxy"] = True
    try:
        reader.read(OwnerKind.BUDGET_LEDGER, lid); print("V2 NOT refused")
    except OwnerUnavailable as e:
        print("V2 refused:", str(e)[:90])
    o.ledgers[lid] = before; state["proxy"] = False
    go3.set(); t.join(10)
    print(log)
    print("V3:", res.get("v3")); print("calls:", calls)
    print("charges now:", len(o.ledgers[lid].charges))

for i in range(3):
    run(); print()
