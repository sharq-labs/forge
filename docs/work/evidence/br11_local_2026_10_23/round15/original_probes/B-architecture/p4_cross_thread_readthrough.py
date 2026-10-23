"""P4: accounts() (and, variant 2, an account's serialization) reads through the reader it feeds from ANOTHER thread
and joins it with no timeout.  The same-thread flag cannot see it; liveness must still be bounded (WAIT_S)."""
import threading, time
from common import *

def run(where):
    o = ax.owned("battery")
    lid = solver(o)
    box = {}
    depth = {"n": 0}
    def inner():
        try:
            box["inner"] = "served" if reader.read(OwnerKind.BUDGET_LEDGER, lid) is not None else "none"
        except OwnerUnavailable as e:
            box["inner"] = "refused: " + str(e)[:90]
    def cross():
        if depth["n"] == 0:
            depth["n"] += 1
            t = threading.Thread(target=inner); t.start(); t.join()      # no timeout
    class Note:
        def __str__(self):
            if armed["on"]:
                cross()
            return "note"
    armed = {"on": False}
    side = BudgetLedger(total_budget=10.0)
    side.settle(charge_id="c", action_id="x", iteration=1, family=ActionFamily.EXPLORE, realized=1.0, detail=Note())
    def accounts():
        if armed["on"] and where == "accounts":
            cross()
        return {**o.ledgers, "side.ledger": side}, dict(o.experiments)
    reader = BudgetReader.following(accounts)
    armed["on"] = True
    t0 = time.monotonic()
    try:
        outer = "served" if reader.read(OwnerKind.BUDGET_LEDGER, lid) is not None else "none"
    except OwnerUnavailable as e:
        outer = "refused: " + str(e)[:90]
    print(f"[{where}] outer: {outer} | inner: {box.get('inner')} | {time.monotonic()-t0:.2f}s | in_flight {reader._in_flight}"
          f" | diverged {list(reader._diverged)}")
    armed["on"] = False
    print(f"[{where}] next read:", reader.read(OwnerKind.BUDGET_LEDGER, lid) is not None)

run("accounts")
run("serialization")
