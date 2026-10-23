"""B10-6 follow-up at aad2f69 (owners.py:529-531): pinned()'s finally calls _leave(ticket) FIRST -- which takes the
reader's lock (owners.py:496, interruptible by a signal on POSIX) -- and resets the thread's re-entrancy flag only after.
When a verification leaves WITHOUT comparing (accounts() raised, owners.py:524-525) its ticket is still in flight; a
KeyboardInterrupt raised while _leave waits for the lock (another verification's comparison holds it; simulated by
holding the private lock from another thread, as round 10's p14 did) leaves BOTH the ticket in flight for good and the
flag set on that thread.  Then: every later verification on that thread is refused 'read through' for good, and every
verification on any other thread that accepts an account waits WAIT_S and is refused, for good."""
import os, signal, threading, time
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable

o = ax.owned("battery")
state = {"down": False}

def holder():                               # stands for another verification's locked comparison
    with reader._lock:
        time.sleep(1.0)

def accounts():
    if state["down"]:
        threading.Thread(target=holder).start(); time.sleep(0.1)
        threading.Timer(0.3, lambda: os.kill(os.getpid(), signal.SIGINT)).start()
        raise ConnectionError("the ledger store is offline")
    return o.ledgers, o.experiments

reader = BudgetReader.following(accounts)
lid = next(iter(o.ledgers))
state["down"] = True
try:
    reader.pinned(); print("first pin returned")
except KeyboardInterrupt:
    print("first pin interrupted (Ctrl-C) in its finally, waiting for the reader's lock")
except OwnerUnavailable as exc:
    print("first pin refused (no interrupt landed in _leave):", str(exc)[:80])
state["down"] = False
time.sleep(1.2)
print("tickets in flight after:", sorted(reader._in_flight))
for i in range(2):
    t0 = time.perf_counter()
    try:
        reader.read(OwnerKind.BUDGET_LEDGER, lid); print(f"main-thread read {i}: served")
    except OwnerUnavailable as exc:
        print(f"main-thread read {i}: refused in {time.perf_counter()-t0:.2f}s: {str(exc)[:100]}")
def other():
    t0 = time.perf_counter()
    try:
        reader.read(OwnerKind.BUDGET_LEDGER, lid); print("other-thread read: served")
    except OwnerUnavailable as exc:
        print(f"other-thread read: refused in {time.perf_counter()-t0:.2f}s: {str(exc)[:100]}")
for _ in range(2):
    t = threading.Thread(target=other); t.start(); t.join()
