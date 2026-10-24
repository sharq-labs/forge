"""Round 9's ticket rule claims 'a spend a verification was handed is never overtaken by a rollback a later verification
reads' (README §4, owners.py:322-324).  _observe_all discards the verification's ticket FIRST (owners.py:419) and then
prunes the shared read-back cache by iterating it (owners.py:421), while another in-flight verification's UNLOCKED
read-back inserts into that same dict (owners.py:389, the dict handed over at owners.py:473).  When the iteration raises
RuntimeError('dictionary changed size during iteration'), the verification that was handed the spend records nothing
and its ticket is already gone, so a later verification handed the rolled-back account decides on it, and the executed
action is dispatched again.

The interleaving is forced with sys.settrace in T2's thread only, the scheduling control round 8's B p03 used (the OS
scheduler can preempt T2 at the same point).  The execution side: an executor that settles the bound ledger in place,
an object-replacing restore (as sria.campaign restores), and a campaign set that gains an experiment account at the
restore.  Nothing on the execution side is introspected; the desk is used through its gateway.
Run with NEW_ACCOUNT=0 for the control (same interleaving, no account added): the re-dispatch is refused."""
import os, sys, threading
import engcore.mind.world.owners as owners_mod
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

NEW_ACCOUNT = os.environ.get("NEW_ACCOUNT", "1") == "1"
SIM = ax.base("battery")["simulate_pulse"]
o = ax.owned("battery")
lid = next(k for k in o.ledgers if k.endswith(".solver"))
campaigns = {f"campaign.{i}": ax.experiment(f"campaign.{i}", 10, 1) for i in range(3)}   # unbound accounts
state = {"restored": False}
t3_started, t3_go = threading.Event(), threading.Event()

def accounts():
    if threading.current_thread().name == "T3" and not t3_go.is_set():
        t3_started.set(); t3_go.wait(10)                    # T3 has its ticket; it asks the store, which is slow
    extra = {"campaign.new": ax.experiment("campaign.new", 10, 0)} if (state["restored"] and NEW_ACCOUNT) else {}
    return o.ledgers, {**o.experiments, **campaigns, **extra}

reader = BudgetReader.following(accounts)
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
gw.dispatch(r.admitted)                                     # executed once: the executor spent the bound ledger
assert len(calls) == 1

PRUNE = next(i for i, l in enumerate(open(owners_mod.__file__).read().splitlines(), 1)
             if "self._readback = {k: v for k, v in snapshot._readback.items() if k in read}" in l)
paused, resume = threading.Event(), threading.Event()
hits = {"n": 0}

def tracer(frame, event, arg):
    if frame.f_code.co_name == "_observe_all" and frame.f_code.co_filename == owners_mod.__file__:
        def local(frame, event, arg):
            if event == "line" and frame.f_lineno == PRUNE and not paused.is_set():
                hits["n"] += 1
                if hits["n"] == 2:                          # inside the prune's iteration, holding the reader's lock
                    paused.set(); resume.wait(10)
            return local
        return local
    return None

out = {}
def t3():                                                   # a verification that started first (ticket 1 of the two)
    try:
        reader.pinned(); out["T3"] = "pinned"
    except Exception as exc:  # noqa: BLE001
        out["T3"] = f"{type(exc).__name__}: {str(exc)[:80]}"

def t2():                                                   # a verification handed the SPENT ledger
    sys.settrace(tracer)
    try:
        out["T2"] = gw.admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world)).status.value
    except Exception as exc:  # noqa: BLE001
        out["T2"] = f"{type(exc).__name__}: {str(exc)[:80]}"

a = threading.Thread(target=t3, name="T3"); a.start(); assert t3_started.wait(10)
b = threading.Thread(target=t2, name="T2"); b.start(); assert paused.wait(10)   # T2 read the spend; comparing
o.ledgers[lid] = BudgetLedger.from_dict(before.to_dict())   # the execution side restores the pre-spend ledger
state["restored"] = True                                    # ... and its campaign set now has one more account
t3_go.set()                                                 # T3's store answers: the restored ledger
import time; time.sleep(0.5)                                # T3 reads its accounts back (no lock) and waits for it
resume.set(); b.join(10); a.join(10)
try:
    gw.dispatch(r.admitted); out["re-dispatch"] = "DISPATCHED"
except DispatchRefused as exc:
    out["re-dispatch"] = "refused: " + str(exc)[:90]
print(f"NEW_ACCOUNT={int(NEW_ACCOUNT)}:", out, "| executor calls:", len(calls))
