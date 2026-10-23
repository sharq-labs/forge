"""verify-3-scope s01: independent reproduction of R10-C-F2's mirror order, plus the same events WITHOUT the later
verification T2 (does T2's presence change T1's outcome at all?), plus what the reader does afterwards."""
import threading

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.mind.world.authority import OwnerUnavailable
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]


def run(with_t2: bool):
    o = ax.owned("battery")
    lid = next(k for k in o.ledgers if k.endswith(".solver"))
    t1_in, t1_go = threading.Event(), threading.Event()
    t2_in, t2_go = threading.Event(), threading.Event()
    log = []

    def accounts():
        n = threading.current_thread().name
        if n == "T1" and not t1_go.is_set():
            t1_in.set(); t1_go.wait(10)                 # T1 has its ticket; its mapping is taken later
        m = (dict(o.ledgers), dict(o.experiments))
        log.append((n, m[0][lid].revision))
        if n == "T2" and not t2_go.is_set():
            t2_in.set(); t2_go.wait(10)                 # T2 holds the spend, not yet compared
        return m

    reader = BudgetReader.following(accounts)
    auth = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), auth)
    calls = []
    gw = ExecutionDesk(auth, calls.append, accept_synthetic=True).gateway()
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gw.dispatch(r.admitted)
    spent = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    spent.settle(charge_id="run-1", action_id="simulate_pulse", iteration=1, family=ActionFamily.EXPLORE, realized=5.0)
    o.ledgers[lid] = spent
    out = {}

    def t1():
        try:
            gw.dispatch(r.admitted); out["T1"] = "DISPATCHED"
        except DispatchRefused as e:
            out["T1"] = "refused: " + str(e)[:90]

    def t2():
        try:
            out["T2"] = "pinned rev " + reader.pinned().read(OwnerKind.BUDGET_LEDGER, lid).revision
        except OwnerUnavailable as e:
            out["T2"] = "refused: " + str(e)[:90]

    th1 = threading.Thread(target=t1, name="T1"); th1.start(); assert t1_in.wait(10)
    if with_t2:
        th2 = threading.Thread(target=t2, name="T2"); th2.start(); assert t2_in.wait(10)
    o.ledgers[lid] = before                             # the execution side restores (object replaced)
    t1_go.set(); th1.join(10)
    if with_t2:
        t2_go.set(); th2.join(10)
    after = {}
    try:
        after["next verification"] = "rev " + reader.read(OwnerKind.BUDGET_LEDGER, lid).revision
    except OwnerUnavailable as e:
        after["next verification"] = "refused: " + str(e)[:80]
    print(f"with_t2={with_t2}: accounts log {log}")
    print(f"   T1 {out.get('T1')} | T2 {out.get('T2')} | executor ran {len(calls)} | {after}")


run(False)
run(True)
