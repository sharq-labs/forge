"""Round 9 moved the experiment read-back out of the follower's lock but kept ONE mutable cache dict shared by the
follower and every in-flight snapshot (owners.py:473 `current._readback = self._readback`).  A snapshot's unlocked
read-back INSERTS into that dict (owners.py:389) while another verification's locked comparison ITERATES it to prune
(owners.py:421).  CPython raises RuntimeError('dictionary changed size during iteration') in the comparing thread; the
error is not OwnerUnavailable, escapes pinned() (only self._follow() is wrapped), and reaches the caller raw.
Only the shipped public API is used (BudgetReader.following, reader.pinned()); the execution side hands over a
changing set of experiment accounts (campaigns come and go)."""
import collections, sys, threading
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader
from engcore.mind.world.authority import OwnerUnavailable

sys.setswitchinterval(1e-6)
POOL = [ax.experiment(f"camp{j}", 400, 3) for j in range(60)]
calls = {"n": 0}
lock = threading.Lock()

def accounts():
    with lock:
        calls["n"] += 1
        n = calls["n"]
    # a changing campaign set: every call hands 30 accounts, under ids that depend on the call
    return {}, {f"c{(n + j) % 97}": POOL[(n + j) % 60] for j in range(30)}

reader = BudgetReader.following(accounts)
outcomes = collections.Counter()

def worker():
    for _ in range(150):
        try:
            reader.pinned()
            outcomes["pinned"] += 1
        except OwnerUnavailable:
            outcomes["OwnerUnavailable"] += 1
        except Exception as exc:  # noqa: BLE001
            outcomes[f"{type(exc).__name__}: {exc}"] += 1

ts = [threading.Thread(target=worker) for _ in range(4)]
[t.start() for t in ts]; [t.join() for t in ts]
print(dict(outcomes))
print("tickets left in flight:", len(getattr(reader, "_in_flight", ())))
