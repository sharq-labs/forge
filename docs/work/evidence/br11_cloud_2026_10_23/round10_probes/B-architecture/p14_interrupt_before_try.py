"""owners.py:466-468: pinned() sets the thread-local re-entrancy flag and takes its ticket BEFORE entering the try whose
finally resets them.  A KeyboardInterrupt (or any BaseException) raised while _ticket() waits for the reader's lock --
which another verification's comparison holds, here simulated by holding the private lock from another thread -- leaves
the flag set on that thread: every later verification on that thread is refused, for good, with the message that the
execution side 'read through the budget reader it feeds'.  (Python's Lock.acquire is interruptible by signals.)"""
import os, signal, threading, time
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable

o = ax.owned("battery")
reader = BudgetReader.following(lambda: (o.ledgers, o.experiments))
lid = next(iter(o.ledgers))

def comparison_elsewhere():                 # stands for another verification's locked comparison (a long one)
    with reader._lock:
        time.sleep(1.0)

threading.Thread(target=comparison_elsewhere).start()
time.sleep(0.1)
threading.Timer(0.3, lambda: os.kill(os.getpid(), signal.SIGINT)).start()
try:
    reader.pinned()
    print("first pin returned")
except KeyboardInterrupt:
    print("first pin interrupted (Ctrl-C) while waiting for the reader's lock")
time.sleep(1.2)
for i in range(3):
    try:
        reader.read(OwnerKind.BUDGET_LEDGER, lid)
        print(f"later read {i}: served")
    except OwnerUnavailable as exc:
        print(f"later read {i}: OwnerUnavailable: {str(exc)[:110]}")
t = threading.Thread(target=lambda: print("read on another thread:", reader.read(OwnerKind.BUDGET_LEDGER, lid).revision))
t.start(); t.join()
print("tickets in flight:", sorted(reader._in_flight))
