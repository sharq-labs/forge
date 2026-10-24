"""README §4 / owners.py:319-320 (round 9): 'no execution-side code ever runs under the reader's lock'.  The account
mapping's KEYS are not checked (BudgetReader.__init__ checks only the values' exact types), and the locked comparison
hashes and compares every key (owners.py:421 `k in read`, 431 `self._seen.get(key)`, 432 `key in self._diverged`,
443 `observed[key] = ...`).  An execution side that keys its accounts by an id class (here a str subclass with its own
__hash__/__eq__, e.g. an interned campaign id) runs that code under the follower's lock.  If it takes an execution-
side lock that a verifying thread holds, the two block each other (timeouts keep the probe finite).  The private
_lock is read only to observe."""
import threading, time
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader

L = threading.Lock()                     # an execution-side lock (e.g. the campaign registry's)
under_lock, waits = [], []
state = {"reader": None}

class CampaignId(str):
    def __hash__(self):
        r = state["reader"]
        if r is not None:
            under_lock.append(r._lock.locked())
            if r._lock.locked():
                if not L.acquire(timeout=1):
                    waits.append("key __hash__ waited 1 s for the execution side's lock, holding the reader's lock")
                else:
                    L.release()
        return str.__hash__(self)
    def __eq__(self, other):
        return str.__eq__(self, other)

o = ax.owned("battery")
extra = ax.experiment("campaign.notes", 10, 1)
experiments = dict(o.experiments)
experiments[CampaignId("campaign.notes")] = extra
reader = BudgetReader.following(lambda: (o.ledgers, experiments))
state["reader"] = reader
go = threading.Event()

def execution_side():                    # holds L while it asks for a verification
    with L:
        go.set()
        time.sleep(0.3)
        t0 = time.time()
        reader.pinned()
        waits.append(f"execution side's verification waited {time.time() - t0:.1f} s for the reader's lock")

def desk():
    go.wait()
    reader.pinned()

a = threading.Thread(target=desk); b = threading.Thread(target=execution_side)
a.start(); b.start(); a.join(); b.join()
print("key __hash__ ran with the reader's lock held:", any(under_lock), f"({sum(under_lock)} of {len(under_lock)} calls)")
print("blocking:", waits)
