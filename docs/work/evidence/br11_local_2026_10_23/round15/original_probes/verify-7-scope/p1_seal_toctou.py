"""P1: the seal (7b4a0de8) is checked once at the start of pinned(), outside the lock, and never again.
A verification that passed the check before another verification sealed the reader decides normally on what it
is handed later: a restore after the sealed (non-dict) handing of the spend is accepted and the SAME authorization
is dispatched again."""
import sys, threading, types
from common import *

def run(variant):
    o = ax.owned("battery")
    lid = solver(o)
    state = {"proxy": False}
    entered3, go3 = threading.Event(), threading.Event()

    def accounts():
        if threading.current_thread().name == "V3" and not entered3.is_set():
            entered3.set()
            go3.wait(10)                                   # V3 is in flight (past the seal check), inside accounts()
        ledgers = dict(o.ledgers)
        return (types.MappingProxyType(ledgers) if state["proxy"] else ledgers), dict(o.experiments)

    calls = []

    def executor(authorization):
        calls.append(threading.current_thread().name)
        settle(o.ledgers[lid], f"run.{len(calls)}")

    reader, authorities, gateway, r = desk(o, accounts, executor)
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(r.admitted)                           # executed once: the spend
    res = {}

    def v3():
        try:
            gateway.dispatch(r.admitted)
            res["v3"] = "DISPATCHED"
        except DispatchRefused as e:
            res["v3"] = "refused: " + str(e)[:160]

    if variant == "toctou":
        t = threading.Thread(target=v3, name="V3", daemon=True)
        t.start()
        assert entered3.wait(10)
    state["proxy"] = True                                  # V2: the spend handed in a MappingProxyType -> sealed
    try:
        reader.read(OwnerKind.BUDGET_LEDGER, lid)
        print("V2 read: NOT refused")
    except OwnerUnavailable as e:
        print("V2 read refused:", str(e)[:110])
    print("sealed:", reader._sealed is not None)
    o.ledgers[lid] = before                                # checkpoint restore, handed as a dict again
    state["proxy"] = False
    if variant == "toctou":
        go3.set()
        t.join(10)
    else:
        v3()
    print(f"[{variant}] V3 (re-dispatch of the same authorization):", res.get("v3"))
    print(f"[{variant}] executor calls:", calls)
    print(f"[{variant}] a later dispatch refused:", refused(gateway, r.admitted), "calls", len(calls))

run("control_after_seal")
print()
run("toctou")
