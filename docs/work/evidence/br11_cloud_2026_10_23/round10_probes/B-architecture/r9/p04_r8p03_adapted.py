"""Round-8 p03 adapted to ceaf8cd.  Two pause points in T2 (a concurrent admission on the same desk), forced with
sys.settrace in T2's thread only:
  READ: inside _observe_all, under the lock, right after the spent ledger was read back, before it is compared
        (B8-m1's window: must now be closed - the re-dispatch waits for the lock and sees the rollback as behind);
  HANDED: after accounts() returned the spent ledger object, before the locked read-back (the documented residual:
        nothing has read the spend yet, so a spend and a rollback look like no change)."""
import inspect, sys, threading
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace
import engcore.mind.world.owners as owners_mod
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]


def run(point):
    o = ax.owned("battery")
    lid = next(k for k in o.ledgers if k.endswith(".solver"))
    reader = BudgetReader.following(lambda: (o.ledgers, o.experiments))
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    calls = []

    def executor(auth):
        calls.append(auth.action_id)
        o.ledgers[lid].settle(charge_id=f"run-{len(calls)}", action_id=auth.action_id, iteration=len(calls),
                              family=ActionFamily.EXPLORE, realized=1.0)

    gw = ExecutionDesk(authorities, executor, accept_synthetic=True).gateway()
    world = o.world
    r = gw.admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world))
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gw.dispatch(r.admitted)
    assert len(calls) == 1
    src, start = inspect.getsourcelines(BudgetReader._observe_all)
    if point == "READ":
        LINE = start + next(i for i, l in enumerate(src) if "seen = self._seen.get" in l)
        fn = "_observe_all"
        cond = lambda f: f.f_locals.get("key") == ("ledger", lid)
    else:
        LINE = start + next(i for i, l in enumerate(src) if "observed: dict" in l)
        fn = "_observe_all"
        cond = lambda f: True
    paused, resume = threading.Event(), threading.Event()

    def tracer(frame, event, arg):
        if frame.f_code.co_name == fn and frame.f_code.co_filename == owners_mod.__file__:
            def local(frame, event, arg):
                if event == "line" and frame.f_lineno == LINE and cond(frame) and not paused.is_set():
                    paused.set(); resume.wait(10)
                return local
            return local

    out = {}

    def t2():
        sys.settrace(tracer)
        try:
            out["T2"] = gw.admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world)).status.value
        except Exception as exc:
            out["T2"] = repr(exc)[:120]

    th = threading.Thread(target=t2); th.start()
    assert paused.wait(10)
    o.ledgers[lid] = BudgetLedger.from_dict(before.to_dict())          # the execution side rolls back (replace)

    def redispatch():
        try:
            gw.dispatch(r.admitted); out["re"] = "DISPATCHED"
        except DispatchRefused as exc:
            out["re"] = "refused: " + str(exc)[:100]
    m = threading.Thread(target=redispatch, daemon=True); m.start(); m.join(2)
    blocked = m.is_alive()
    resume.set(); th.join(10); m.join(10)
    print(f"{point}: re-dispatch blocked behind T2: {blocked}; re-dispatch: {out.get('re')}; T2: {out.get('T2')}; "
          f"executor calls: {len(calls)}")


run("READ")
run("HANDED")
