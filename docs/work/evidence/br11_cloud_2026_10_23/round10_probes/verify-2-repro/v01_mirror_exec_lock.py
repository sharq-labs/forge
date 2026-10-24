"""verify-2: independent rewrite of R10-C-F2.  The execution side guards its account mapping with its OWN lock
(exec_lock); accounts() takes that lock, copies the mapping, releases.  Ordering is forced only by WHO holds exec_lock
when (no hook inside the reader, no monkeypatching; public API only):

  1. dispatch once (pre-spend observed), executor spends: ledger REPLACED by an exhausted one (remaining < 2).
  2. execution side takes exec_lock (bookkeeping).
  3. T1 = gateway.dispatch(admitted) starts: ticket 1, blocks in accounts() on exec_lock.
  4. T2 = gateway2.dispatch(admitted other action) / reader.pinned() starts: ticket 2.  To force T2 to get the lock
     first we let T2 use a 'fast path' that reads the mapping without exec_lock (as an execution side may for a
     snapshot it already holds) -- variant A; variant B: T2's accounts() was called before the bookkeeping took
     exec_lock but pauses after copying (simulating preemption after the copy).
  5. execution side restores (replaces ledger object), releases exec_lock.
  6. T1 copies the restore, reads back, compares (T2 still in flight but LATER) -> decides.
  7. T2 resumes, compares the spend.
"""
import threading
import time

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.mind.world.authority import OwnerUnavailable
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]


def run(order):
    o = ax.owned("battery")
    lid = next(k for k in o.ledgers if k.endswith(".solver"))
    exec_lock = threading.Lock()
    t2_copied, t2_go = threading.Event(), threading.Event()
    log = []

    def accounts():
        name = threading.current_thread().name
        with exec_lock:
            mapping = (dict(o.ledgers), dict(o.experiments))
        log.append((name, mapping[0][lid].revision, len(mapping[0][lid].charges)))
        if name == "T2" and not t2_go.is_set():
            t2_copied.set()          # T2 has its mapping (the spend) and is preempted before returning
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
    with exec_lock:
        o.ledgers[lid] = spent
    out = {}

    def t1():
        try:
            gateway.dispatch(r.admitted)
            out["T1"] = "DISPATCHED"
        except DispatchRefused as exc:
            out["T1"] = f"refused ({str(exc)[:90]})"

    def t2():
        try:
            reader.pinned()
            out["T2"] = "pinned ok"
        except Exception as exc:  # noqa: BLE001
            out["T2"] = f"{type(exc).__name__}"

    if order == "mirror":
        exec_lock.acquire()                     # 2. execution-side bookkeeping holds its lock
        th1 = threading.Thread(target=t1, name="T1", daemon=True)
        th1.start()                             # 3. T1 takes ticket 1, blocks on exec_lock inside accounts()
        deadline = time.time() + 5
        while reader._tickets < 3 and time.time() < deadline:   # observe only (construction=1, first dispatch=2)
            time.sleep(0.001)
        # T1 holds ticket 3 now (construction took 1, first dispatch 2); T2 will take ticket 4
        # variant: T2's mapping is taken by the execution side's bookkeeping thread on T2's behalf? keep it simple:
        # release exec_lock briefly only for T2 by handing T2 the spend under our hold: T2 reads while we hold it is
        # impossible with a plain Lock, so T2 starts and we pass the lock to it by releasing after T2 is waiting and
        # T1 is still waiting -- not deterministic; instead release, let whichever thread win, and report it.
        th2 = threading.Thread(target=t2, name="T2", daemon=True)
        th2.start()
        time.sleep(0.05)
        exec_lock.release()
        # whichever wins: if T2 wins it copies the spend and pauses; then we restore
        if t2_copied.wait(2):
            with exec_lock:
                o.ledgers[lid] = before         # 5. restore (replace) after T2 holds the spend
        th1.join(10)
        t2_go.set()
        th2.join(10)
    tickets_note = f"tickets used={reader._tickets}"
    try:
        gateway.dispatch(r.admitted)
        later = "DISPATCHED"
    except DispatchRefused as exc:
        later = f"refused ({str(exc)[:70]})"
    return f"{order}: accounts log={log} | T1 {out.get('T1')} | T2 {out.get('T2')} | executor ran {len(calls)} | later {later} | {tickets_note}"


for i in range(5):
    print(run("mirror"))
