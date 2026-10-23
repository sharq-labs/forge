"""R11-C c1104: re-dispatch through ExecutionDesk.gateway() after a spend handed to another verification W, then a
restore (object replaced, sria.campaign style), in three W behaviours:
  slow   - W was handed the spend and its accounts() returns only after 1.6 s (> WAIT_S): the re-dispatch D compares
           while W is in flight, waits WAIT_S and must be refused; a later re-dispatch must be refused (behind).
  raises - W was handed the spend, then its accounts() raises: the documented residual ('the state of a verification
           whose accounts() raises' is never observed): D decides on the restore.
  bad    - W's accounts() returns the spend mapping with one extra account that is not exactly typed (a subclass): the
           reader refuses W's whole snapshot before reading it back; D decides on the restore?"""
import sys
import threading
import time

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, admit
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]


class SubLedger(BudgetLedger):
    pass


def run(mode):
    o = ax.owned("battery")
    lid = next(k for k in o.ledgers if k.endswith(".solver"))
    handed, resume = threading.Event(), threading.Event()

    def accounts():
        mapping = (dict(o.ledgers), dict(o.experiments))
        if threading.current_thread().name == "W":
            handed.set()
            if mode == "slow":
                time.sleep(1.6)
            else:
                resume.wait(10)
            if mode == "raises":
                raise RuntimeError("the execution side's store went away")
            if mode == "bad":
                mapping = ({**mapping[0], "extra": SubLedger(total_budget=1.0)}, mapping[1])
        return mapping

    reader = BudgetReader.following(accounts)
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    calls = []
    gateway = ExecutionDesk(authorities, calls.append, accept_synthetic=True).gateway()
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(r.admitted)
    o.ledgers[lid].settle(charge_id="run-1", action_id="simulate_pulse", iteration=1, family=ActionFamily.EXPLORE,
                          realized=2.0)                                   # the executor spends (in place)
    w_out = {}

    def w():
        try:
            reader.pinned()
            w_out["W"] = "pinned"
        except Exception as exc:  # noqa: BLE001
            w_out["W"] = f"{type(exc).__name__}"

    wt = threading.Thread(target=w, name="W", daemon=True)
    wt.start()
    assert handed.wait(10)                                                # W holds the spent ledger
    o.ledgers[lid] = before                                               # restore (object replaced)
    if mode != "slow":
        threading.Timer(0.2, resume.set).start()
    t0 = time.perf_counter()
    try:
        gateway.dispatch(r.admitted)
        d = "DISPATCHED AGAIN"
    except DispatchRefused as exc:
        d = f"refused ({str(exc)[:90]})"
    dt = time.perf_counter() - t0
    wt.join(10)
    try:
        gateway.dispatch(r.admitted)
        later = "DISPATCHED AGAIN"
    except DispatchRefused as exc:
        later = f"refused ({str(exc)[:70]})"
    print(f"{mode:6s} | D: {d} after {dt:.2f} s | W: {w_out.get('W')} | later: {later} | executor ran {len(calls)}")


for m in ("slow", "raises", "bad"):
    run(m)
