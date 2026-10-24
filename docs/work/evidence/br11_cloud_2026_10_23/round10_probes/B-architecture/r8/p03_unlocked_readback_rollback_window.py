"""Round 7 reads every account back with NO lock held and only compares under the lock.  So a verification T2 can READ
the spent state (after an executor's spend) and be preempted before it compares.  If the execution side rolls the
account back in that window, a re-dispatch of the executed action compares FIRST: the rolled-back state equals the
history observed so far, it is accepted, and the action is dispatched again.  T2 then compares the spent state as an
extension.  At 27b9f71 (round 6) read and compare were one critical section: once T2 has read the spent state it has
also observed it, and the re-dispatch is refused.

The interleaving is forced with sys.settrace in T2's thread only (a scheduling control: the OS scheduler can preempt T2
at the same point).  Nothing on the execution side is introspected or edited; the desk is used through its gateway."""
import inspect, sys, threading
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace
import engcore.mind.world.owners as owners_mod
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

HEAD_SEMANTICS = hasattr(BudgetReader, "_read_back")
SIM = ax.base("battery")["simulate_pulse"]
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
gw.dispatch(r.admitted)                                        # executed once: the executor spent the bound ledger
assert len(calls) == 1

src, start = inspect.getsourcelines(BudgetReader._observe_all)
if HEAD_SEMANTICS:     # round 7: pause after the unlocked read-back, before the locked comparison
    LINE = start + next(i for i, l in enumerate(src) if "observed: dict" in l)
    def should_pause(frame):
        return True
else:                  # round 6: the read is inside the lock; pause right after the ledger was read, before comparing
    LINE = start + next(i for i, l in enumerate(src) if "seen = self._seen.get" in l)
    def should_pause(frame):
        return frame.f_locals.get("key") == ("ledger", lid)
paused, resume = threading.Event(), threading.Event()


def tracer(frame, event, arg):
    if frame.f_code.co_name == "_observe_all" and frame.f_code.co_filename == owners_mod.__file__:
        def local(frame, event, arg):
            if event == "line" and frame.f_lineno == LINE and should_pause(frame) and not paused.is_set():
                paused.set(); resume.wait(10)
            return local
        return local


out = {}


def t2_verification():                                         # another admission on the same desk, concurrently
    sys.settrace(tracer)
    try:
        out["T2"] = gw.admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world)).status.value
    except Exception as exc:
        out["T2"] = repr(exc)[:120]


t2 = threading.Thread(target=t2_verification); t2.start()
assert paused.wait(10)                                         # T2 has READ the spent ledger (revision after the spend)
o.ledgers[lid] = BudgetLedger.from_dict(before.to_dict())      # the execution side restores the pre-spend ledger


def redispatch():
    try:
        gw.dispatch(r.admitted); out["redispatch"] = "DISPATCHED"
    except DispatchRefused as exc:
        out["redispatch"] = "refused: " + str(exc)[:110]


m = threading.Thread(target=redispatch, daemon=True); m.start()
m.join(3)
blocked = m.is_alive()
resume.set(); t2.join(10); m.join(10)
print(f"{'round-7 (HEAD)' if HEAD_SEMANTICS else 'round-6 (27b9f71)'}: T2 read the spent ledger before the rollback; "
      f"re-dispatch blocked behind T2: {blocked}; re-dispatch: {out.get('redispatch')}; T2: {out.get('T2')}; "
      f"executor calls: {len(calls)}")
try:
    reader.read(owners_mod.K.BUDGET_LEDGER, lid); later = "accepted"
except Exception as exc:
    later = str(exc)[:90]
print("the next read of the ledger:", later)
