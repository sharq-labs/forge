"""P1b (control for P1): the same schedule, but the spend handed to V2 is a dict whose state is not read back
(its new charge's detail raises the interpreter's mutation error).  The not-read-back rule records it under the lock,
so the in-flight V3 that compares afterwards is refused.  Only the seal path loses the handed spend."""
import threading
from common import *

class SelfFilling:
    def __str__(self):
        c = {"a": 1}
        for k in c:
            c[k + "x"] = 2
        return "unreached"

o = ax.owned("battery")
lid = solver(o)
entered3, go3 = threading.Event(), threading.Event()

def accounts():
    if threading.current_thread().name == "V3" and not entered3.is_set():
        entered3.set(); go3.wait(10)
    return dict(o.ledgers), dict(o.experiments)

calls = []
def executor(a):
    calls.append(threading.current_thread().name)
    settle(o.ledgers[lid], f"run.{len(calls)}", SelfFilling())

reader, authorities, gateway, r = desk(o, accounts, executor)
before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
gateway.dispatch(r.admitted)
res = {}
def v3():
    try:
        gateway.dispatch(r.admitted); res["v3"] = "DISPATCHED"
    except DispatchRefused as e:
        res["v3"] = "refused: " + str(e)[:200]
t = threading.Thread(target=v3, name="V3", daemon=True); t.start(); assert entered3.wait(10)
try:
    reader.read(OwnerKind.BUDGET_LEDGER, lid); print("V2 read: served")
except OwnerUnavailable as e:
    print("V2 read refused:", str(e)[:100])
o.ledgers[lid] = before
go3.set(); t.join(10)
print("[unread-dict] V3:", res.get("v3")); print("[unread-dict] calls:", calls)
