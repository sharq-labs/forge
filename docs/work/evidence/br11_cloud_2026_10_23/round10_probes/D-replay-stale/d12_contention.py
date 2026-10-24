"""R10-D d12: availability of the ticket rule.
(a) the r7 test's pattern (an execution side that verifies under the lock its accounts() takes), 20 runs: how often is
    B (the execution side's own verification) refused?
(b) an execution side that dispatches under its lock while proposer threads keep requesting admission (their
    accounts() waits on that lock): how many of the execution side's dispatch attempts succeed?
(c) the r6 stress pattern (4 verifier threads in a loop, no spender): fraction refused 'in flight'."""
import threading, time, collections
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, FeasibleActionSpace, OwnerKind, admit, ExecutionDesk, DispatchRefused
from engcore.mind.world.authority import OwnerUnavailable

SIM = ax.base("battery")["simulate_pulse"]


def followed(o, accounts):
    reader = BudgetReader.following(accounts)
    return reader, type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))


# (a)
res = collections.Counter()
for run in range(20):
    o = ax.owned("battery")
    lock = threading.RLock()
    inside = threading.Event()

    def accounts():
        if threading.current_thread().name == "A":
            inside.set()
            time.sleep(0.05)
        with lock:
            return o.ledgers, o.experiments
    reader, a = followed(o, accounts)
    world, out = o.world, {}

    def A():
        out["A"] = admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world), a).status.value

    def B():
        inside.wait(2)
        with lock:
            out["B"] = admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world), a).status.value
    ts = [threading.Thread(target=A, name="A"), threading.Thread(target=B, name="B")]
    [t.start() for t in ts]; [t.join(10) for t in ts]
    res[(out.get("A"), out.get("B"))] += 1
print("(a) r7 pattern (A, B) outcomes over 20 runs:", dict(res))

# (b)
o = ax.owned("battery")
lock = threading.RLock()


def accounts():
    with lock:
        return dict(o.ledgers), dict(o.experiments)
reader, a = followed(o, accounts)
world = o.world
r = admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world), a)
assert r.admitted is not None
calls = []
gw = ExecutionDesk(a, calls.append, accept_synthetic=True).gateway()
stop = threading.Event()
props = collections.Counter()


def proposer():
    while not stop.is_set():
        props[admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world), a).status.value] += 1
ps = [threading.Thread(target=proposer, daemon=True) for _ in range(2)]
[p.start() for p in ps]
time.sleep(0.3)
ok = refused = 0
reasons = collections.Counter()
t0 = time.time()
for i in range(30):
    with lock:                                            # the execution step: dispatch under its own lock
        try:
            gw.dispatch(r.admitted); ok += 1
        except DispatchRefused as e:
            refused += 1
            reasons["in flight" if "in flight" in str(e) else str(e)[:80]] += 1
    time.sleep(0.01)                                      # releases the lock between steps
stop.set(); [p.join(5) for p in ps]
print(f"(b) execution-side dispatch under its lock with 2 busy proposers: {ok} dispatched, {refused} refused "
      f"in {time.time()-t0:.1f}s; reasons {dict(reasons)}; proposer outcomes {dict(props)}")

# (c)
o = ax.owned("battery")
lid = next(k for k in o.ledgers if k.endswith(".solver"))
reader, a = followed(o, lambda: (o.ledgers, o.experiments))
cnt = collections.Counter()
stop = threading.Event()


def verify():
    while not stop.is_set():
        try:
            reader.pinned().read(OwnerKind.BUDGET_LEDGER, lid); cnt["ok"] += 1
        except OwnerUnavailable as e:
            cnt["in flight" if "in flight" in str(e) else "other"] += 1
ts = [threading.Thread(target=verify) for _ in range(4)]
[t.start() for t in ts]; time.sleep(2); stop.set(); [t.join() for t in ts]
print("(c) 4 verifier threads, 2 s, no spender:", dict(cnt), f"refused fraction {1 - cnt['ok']/sum(cnt.values()):.2f}")
