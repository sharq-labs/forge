"""P3 (prior closure R13-B-F4 / R14-B-F1 / R12-4): an unbound side ledger whose serialization exceeds the recursion
limit on the verifying threads and, on a fresh thread, blocks on a lock the execution side holds.  Concurrent
verifications from 6 threads, 3 rounds each: every verification must return within a bounded time, at most one fresh
read-back thread may run per account, and the bound accounts must still be served."""
import threading, time
from common import *

L = threading.Lock()
class Deep:
    def __str__(self):
        if threading.current_thread().name != "budget-read-back":
            raise RecursionError("maximum recursion depth exceeded (simulated caller stack)")
        with L:                                          # the execution side holds L
            return "deep"

o = ax.owned("battery")
lid = solver(o)
side = BudgetLedger(total_budget=10.0)
side.settle(charge_id="c", action_id="x", iteration=1, family=ActionFamily.EXPLORE, realized=1.0, detail=Deep())
reader = BudgetReader.following(lambda: ({**o.ledgers, "side.ledger": side}, dict(o.experiments)))
L.acquire()
lat, outcomes, alive = [], {}, []
def worker():
    for _ in range(3):
        t0 = time.monotonic()
        try:
            snap = reader.pinned()
            got = []
            for k in ("side.ledger", lid):
                try:
                    got.append("served" if snap.read(OwnerKind.BUDGET_LEDGER, k) is not None else "none")
                except OwnerUnavailable as e:
                    got.append("refused:" + str(e)[str(e).find("was not"):][:60])
            key = tuple(got)
        except OwnerUnavailable as e:
            key = ("pin refused", str(e)[:60])
        lat.append(time.monotonic() - t0)
        outcomes[key] = outcomes.get(key, 0) + 1
        alive.append(sum(1 for t in threading.enumerate() if t.name == "budget-read-back" and t.is_alive()))
ts = [threading.Thread(target=worker) for _ in range(6)]
t0 = time.monotonic()
[t.start() for t in ts]; [t.join(30) for t in ts]
print("all returned:", all(not t.is_alive() for t in ts), f"in {time.monotonic()-t0:.1f}s")
print("max latency s: %.2f  p50 %.2f" % (max(lat), sorted(lat)[len(lat)//2]))
print("max fresh read-back threads alive at once:", max(alive))
for k, v in outcomes.items():
    print(v, k)
L.release()
time.sleep(0.5)
print("after release, alive:", sum(1 for t in threading.enumerate() if t.name == "budget-read-back" and t.is_alive()))
print("next verification side.ledger:", end=" ")
try:
    print(reader.read(OwnerKind.BUDGET_LEDGER, "side.ledger") is not None)
except OwnerUnavailable as e:
    print("refused", str(e)[:120])
print("diverged:", list(reader._diverged))
