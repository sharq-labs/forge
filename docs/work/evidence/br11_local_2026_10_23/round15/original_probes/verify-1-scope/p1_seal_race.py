"""A verification in flight across the seal decides after it, on a restored checkpoint."""
import sys, threading, types
from common import *
print("owners:", owners_mod.__file__)

def run(mode):
    o = ax.owned("battery")
    lid = solver(o)
    state = {"proxy": False, "unread": False}
    gate, va_in = threading.Event(), threading.Event()

    def accounts():
        if threading.current_thread().name == "VA":
            va_in.set()
            gate.wait(10)
        ledgers = dict(o.ledgers)
        return (types.MappingProxyType(ledgers) if state["proxy"] else ledgers), dict(o.experiments)

    calls = []

    def executor(authorization):
        calls.append(1)
        if mode == "proxy":
            settle(o.ledgers[lid], f"run.{len(calls)}")
            if len(calls) == 1:
                state["proxy"] = True
        else:  # honest dict handing, state not read back (the control)
            settle(o.ledgers[lid], f"run.{len(calls)}", SelfFillingNote() if len(calls) == 1 else "x")

    reader, authorities, gateway, r = desk(o, accounts, executor)
    F = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(r.admitted)
    print(mode, "first dispatch, calls", len(calls))
    out = []

    def va():
        out.append(refused(gateway, r.admitted) or "DISPATCHED AGAIN")
    t = threading.Thread(target=va, name="VA", daemon=True)
    t.start()
    assert va_in.wait(10)
    try:
        reader.read(OwnerKind.BUDGET_LEDGER, lid)
        print(mode, "VB read: served")
    except OwnerUnavailable as exc:
        print(mode, "VB read refused:", str(exc)[:150])
    print(mode, "sealed:", reader._sealed is not None, "unread:", {k: len(v) for k, v in reader._unread_entries.items()})
    o.ledgers[lid] = F                       # restore the checkpoint the admission was made on
    state["proxy"] = False
    gate.set()
    t.join(10)
    print(mode, "VA (the same admitted action, dispatch started before the seal):", out)
    print(mode, "executor calls:", len(calls))
    print(mode, "later dispatch:", refused(gateway, r.admitted) or "DISPATCHED", "calls", len(calls))

for m in ("proxy", "unread_dict_control"):
    run(m)
    print("----")
