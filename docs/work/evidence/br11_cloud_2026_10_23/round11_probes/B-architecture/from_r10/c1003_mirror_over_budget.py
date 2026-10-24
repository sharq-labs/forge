"""R10-C c1003: c1001 with a spend that EXHAUSTS the ledger (remaining 6 -> 1 < the action's 2 solver calls), so the
spent state refuses the action OVER_BUDGET.  Four orders of the same events, through the public desk gateway:

  seq-no-rollback : spend, then dispatch                                   -> refused (over budget)       [control]
  seq-rollback    : spend, a verification observes it, restore, dispatch    -> refused (behind)            [control]
  r9-order        : T2 starts and is handed the spend, restore, T1 starts   -> refused (earlier in flight)  [r9 test]
  mirror-order    : T1 starts (ticket 1, maps later), T2 starts and is handed the spend, restore, T1 maps the restore
                    and compares first, then T2 compares the spend         -> ?

T1 is always gateway.dispatch(r.admitted); T2 is reader.pinned() (any concurrent verification)."""
import threading

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, admit
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]


def scenario(order: str) -> str:
    o = ax.owned("battery")
    lid = next(k for k in o.ledgers if k.endswith(".solver"))
    t1_entered, t1_go = threading.Event(), threading.Event()
    t2_handed, t2_go = threading.Event(), threading.Event()
    concurrent = order in ("r9-order", "mirror-order")

    def accounts():
        name = threading.current_thread().name
        if concurrent and name == "T1" and order == "mirror-order" and not t1_go.is_set():
            t1_entered.set()
            t1_go.wait(10)
        mapping = (dict(o.ledgers), dict(o.experiments))
        if concurrent and name == "T2" and not t2_go.is_set():
            t2_handed.set()
            t2_go.wait(10)
        return mapping

    reader = BudgetReader.following(accounts)
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    assert r.admitted is not None, r.status
    calls = []
    gateway = ExecutionDesk(authorities, calls.append, accept_synthetic=True).gateway()
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(r.admitted)
    spent = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    spent.settle(charge_id="run-1", action_id="simulate_pulse", iteration=1, family=ActionFamily.EXPLORE, realized=5.0)
    o.ledgers[lid] = spent                                         # remaining 1 < 2: the spent state refuses the action
    out = {}

    def t1():
        try:
            gateway.dispatch(r.admitted)
            out["T1"] = "DISPATCHED"
        except DispatchRefused as exc:
            out["T1"] = f"refused ({str(exc)[:110]})"

    if order == "seq-no-rollback":
        t1()
    elif order == "seq-rollback":
        reader.pinned()                                            # a verification observes the spend
        o.ledgers[lid] = before
        t1()
    elif order == "r9-order":
        th2 = threading.Thread(target=reader.pinned, name="T2", daemon=True)
        th2.start()
        assert t2_handed.wait(10)
        o.ledgers[lid] = before
        th1 = threading.Thread(target=t1, name="T1", daemon=True)
        th1.start()
        th1.join(10)
        t2_go.set()
        th2.join(10)
    else:
        th1 = threading.Thread(target=t1, name="T1", daemon=True)
        th1.start()
        assert t1_entered.wait(10)
        th2 = threading.Thread(target=reader.pinned, name="T2", daemon=True)
        th2.start()
        assert t2_handed.wait(10)
        o.ledgers[lid] = before
        t1_go.set()
        th1.join(10)
        t2_go.set()
        th2.join(10)
    return f"{order:16s}: T1 {out.get('T1')} | executor ran {len(calls)} times (1 = only the first dispatch)"


for order in ("seq-no-rollback", "seq-rollback", "r9-order", "mirror-order"):
    print(scenario(order))
