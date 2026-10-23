"""R10-C c1012: the c1001 mirror without any pause: an execution side whose accounts() takes its own state lock L (as
a thread-safe execution side does), whose executor settles under L and whose restorer restores under L (object
replaced).  Per trial: dispatch once; then threads T1 (re-dispatch), T2 (another verification) and R (spend, then
restore) race.  Oracle (from the execution side's own log of every mapping handed by accounts(), in L order): a
re-dispatch that executed while some verification had been handed the spent ledger BEFORE T1 was handed the restore.
Counts also the residual cases (the spend was handed to no verification), which are documented."""
import random
import sys
import threading
import time

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, admit
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]
sys.setswitchinterval(1e-6)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 300
rng = random.Random(3)
stats = {"trials": 0, "redispatched": 0, "redispatched_after_spend_was_handed": 0, "residual": 0}
t0 = time.time()
for trial in range(N):
    o = ax.owned("battery")
    lid = next(k for k in o.ledgers if k.endswith(".solver"))
    L = threading.Lock()
    log = []

    def accounts():
        with L:
            m = (dict(o.ledgers), dict(o.experiments))
            log.append((threading.current_thread().name, m[0][lid].revision))
        for _ in range(rng.randint(0, 3)):
            time.sleep(0)
        return m

    reader = BudgetReader.following(accounts)
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    calls = []
    gateway = ExecutionDesk(authorities, calls.append, accept_synthetic=True).gateway()
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(r.admitted)
    log.clear()
    base_rev = before.revision
    out = {}

    def t1():
        for _ in range(rng.randint(0, 40)):
            time.sleep(0)
        try:
            gateway.dispatch(r.admitted)
            out["T1"] = True
        except DispatchRefused:
            out["T1"] = False

    def t2():
        for _ in range(rng.randint(0, 40)):
            time.sleep(0)
        reader.pinned()

    def restorer():
        spent = BudgetLedger.from_dict(before.to_dict())
        spent.settle(charge_id="run-1", action_id="simulate_pulse", iteration=1, family=ActionFamily.EXPLORE,
                     realized=2.0)
        with L:
            o.ledgers[lid] = spent
            log.append(("SPEND", spent.revision))
        for _ in range(rng.randint(0, 40)):
            time.sleep(0)
        with L:
            o.ledgers[lid] = before
            log.append(("RESTORE", before.revision))

    ths = [threading.Thread(target=f, name=n) for f, n in ((t1, "T1"), (t2, "T2"), (restorer, "R"))]
    rng.shuffle(ths)
    for th in ths:
        th.start()
    for th in ths:
        th.join()
    stats["trials"] += 1
    if out.get("T1"):
        stats["redispatched"] += 1
        t1_idx = max(i for i, (n, _) in enumerate(log) if n == "T1")
        handed_spend = any(n not in ("SPEND", "RESTORE", "T1") and rev > base_rev for n, rev in log[:t1_idx])
        if handed_spend:
            stats["redispatched_after_spend_was_handed"] += 1
            if stats["redispatched_after_spend_was_handed"] <= 3:
                print("example log:", log)
        else:
            stats["residual"] += 1
print(stats, f"{time.time() - t0:.0f}s")
