"""verify-2: independent rewrite of R10-C-F2, ordering produced only by LATENCY inside the execution side's
accounts() (no events, no monkeypatching, no private member touched; public API only):
  - T1's accounts() does 0.20 s of execution-side work (e.g. I/O) BEFORE it copies the mapping;
  - T2's accounts() copies the mapping at once and then takes 0.50 s (e.g. I/O) before it returns it;
  - the execution side restores the ledger (replaces the object) at ~0.10 s.
T1 = gateway.dispatch(admitted simulate_pulse) started first; T2 = a second gateway.dispatch of ANOTHER admitted
action (so both verifications go through the Mind-facing desk) or reader.pinned()."""
import sys
import threading
import time

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]


def run(t2_kind, exhaust, mode):
    o = ax.owned("battery")
    lid = next(k for k in o.ledgers if k.endswith(".solver"))
    exec_lock = threading.Lock()
    log = []
    armed = {"on": False}

    def accounts():
        name = threading.current_thread().name
        if armed["on"] and name == "T1":
            time.sleep(0.20)
        with exec_lock:
            mapping = (dict(o.ledgers), dict(o.experiments))
        log.append((name, round(time.monotonic() - t0, 3), len(mapping[0][lid].charges)))
        if armed["on"] and name == "T2":
            time.sleep(0.50)
        return mapping

    reader = BudgetReader.following(accounts)
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    space = FeasibleActionSpace.build(o.world)
    r = admit(space, o.propose("simulate_pulse", *SIM), authorities)
    assert r.admitted is not None, r.status
    calls = []
    gateway = ExecutionDesk(authorities, calls.append, accept_synthetic=True).gateway()
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(r.admitted)
    if mode == "replace":
        spent = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
        spent.settle(charge_id="run-1", action_id="simulate_pulse", iteration=1, family=ActionFamily.EXPLORE,
                     realized=5.0 if exhaust else 2.0)
        with exec_lock:
            o.ledgers[lid] = spent
    else:
        o.ledgers[lid].settle(charge_id="run-1", action_id="simulate_pulse", iteration=1, family=ActionFamily.EXPLORE,
                              realized=5.0 if exhaust else 2.0)
    out = {}
    calls_before = len(calls)

    def t1():
        try:
            gateway.dispatch(r.admitted)
            out["T1"] = "DISPATCHED"
        except DispatchRefused as exc:
            out["T1"] = f"refused ({str(exc)[60:130]})"

    def t2():
        try:
            if t2_kind == "pinned":
                reader.pinned()
                out["T2"] = "pinned"
            else:
                gateway.dispatch(r.admitted)
                out["T2"] = "DISPATCHED"
        except DispatchRefused as exc:
            out["T2"] = f"refused ({str(exc)[60:130]})"
        except Exception as exc:  # noqa: BLE001
            out["T2"] = type(exc).__name__

    global t0
    t0 = time.monotonic()
    armed["on"] = True
    th1 = threading.Thread(target=t1, name="T1", daemon=True)
    th2 = threading.Thread(target=t2, name="T2", daemon=True)
    th1.start()
    time.sleep(0.02)
    th2.start()
    time.sleep(0.08)
    with exec_lock:
        o.ledgers[lid] = before                       # restore (replace) at ~0.10 s
    th1.join(5)
    th2.join(5)
    armed["on"] = False
    try:
        gateway.dispatch(r.admitted)
        later = "DISPATCHED"
    except DispatchRefused as exc:
        later = "refused"
    return (f"T2={t2_kind:6s} exhaust={exhaust!s:5s} mode={mode:7s}: log={log[-3:]} | T1 {out.get('T1')} | "
            f"T2 {out.get('T2')} | executor ran {len(calls)} (re-dispatches in window: {len(calls)-calls_before}) | later {later}")


t0 = 0.0
for t2_kind in ("pinned", "dispatch"):
    for exhaust in (True, False):
        for mode in ("replace", "inplace"):
            print(run(t2_kind, exhaust, mode))
