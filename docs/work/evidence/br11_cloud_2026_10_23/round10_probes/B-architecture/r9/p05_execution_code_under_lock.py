"""Round 8 moved the read-back back under the follower's lock (B8-m1).  The read-back is owner code, except that an
experiment's metadata VALUES are execution-side objects: ScientificExperiment.to_dict/from_dict copy metadata
shallowly, json.dumps (sort_keys) calls a dict subclass's items(), and the reader's copy.deepcopy(back) calls the value's
__deepcopy__.  So execution-side code runs under the follower's lock.  If that code takes an execution-side lock L that
another thread holds while it admits (the B7-m3 pattern), the two block each other.  Acquire timeouts keep the probe
finite; a real lock without a timeout would hang.  The account is an UNBOUND experiment handed to the follower (it is
read back at every verification, whatever world is verified)."""
import threading, time
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader

L = threading.Lock()                         # an execution-side lock
held_under_reader_lock = []
timeouts = []


class Notes(dict):                           # an execution-side metadata value (JSON-writable: a dict)
    def __deepcopy__(self, memo):
        held_under_reader_lock.append(reader._lock.locked())
        if not L.acquire(timeout=2):         # the execution side guards its notes with its own lock
            timeouts.append("deepcopy waited 2 s for the execution side's lock")
        else:
            L.release()
        return Notes(self)


o = ax.owned("battery")
extra = ax.experiment("campaign.notes", 10, 1)
extra.metadata["notes"] = Notes(owner="campaign")
experiments = dict(o.experiments, **{"campaign.notes": extra})
reader = BudgetReader.following(lambda: (o.ledgers, experiments))

go = threading.Event()


def execution_side():                         # holds L while it asks for a verification (admits under its own lock)
    with L:
        go.set()
        time.sleep(0.2)                       # A is now inside the read-back, holding the reader's lock
        t0 = time.time()
        reader.pinned()
        timeouts.append(f"execution side's verification waited {time.time() - t0:.1f} s for the follower's lock")


b = threading.Thread(target=execution_side)
b.start(); go.wait()
reader.pinned()                               # thread A: a verification on the desk
b.join()
print("execution-side __deepcopy__ ran with the follower's lock held:", held_under_reader_lock[:3])
print("blocking:", timeouts)
