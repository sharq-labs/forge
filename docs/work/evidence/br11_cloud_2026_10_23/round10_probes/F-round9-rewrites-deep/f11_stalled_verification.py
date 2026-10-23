"""F10 f11: under the round-9 ticket rule, one verification whose accounts() stalls (an execution-side call that does not
return) refuses EVERY later-started verification of that reader, on every account, for as long as it stalls; the
account itself only moved forward.  (Round 8: a stalled accounts() held no lock and blocked nobody.)"""
import threading
import time

import engcore
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable

print("engcore from", engcore.__file__)
o = ax.owned("battery")
lid = next(k for k in o.ledgers if k.endswith(".solver"))
release = threading.Event()


def accounts():
    if threading.current_thread().name == "STALLED":
        release.wait(30)
    return o.ledgers, o.experiments


reader = BudgetReader.following(accounts)
t = threading.Thread(target=lambda: reader.pinned(), name="STALLED", daemon=True)
t.start()
time.sleep(0.2)
refused = 0
for i in range(20):
    try:
        reader.read(OwnerKind.BUDGET_LEDGER, lid)
    except OwnerUnavailable as exc:
        refused += 1
        msg = str(exc)
    time.sleep(0.1)
print(f"while one accounts() call stalls (2 s): {refused}/20 later verifications refused: {msg[:90]}")
release.set(); t.join(5)
print("after it returns:", reader.read(OwnerKind.BUDGET_LEDGER, lid).revision)
