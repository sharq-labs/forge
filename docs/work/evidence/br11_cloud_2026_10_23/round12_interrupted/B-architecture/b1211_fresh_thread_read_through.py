"""R12-B b1211: the fresh-thread retry runs 'under the same-thread read-through flag' (owners.py _at_baseline_depth).
A verification on a deep stack (three RecursionErrors on the calling thread) whose account serialization reads
through the same reader on the fresh thread: on HEAD the read-through is refused at once (one nested call); without the
flag (mutant fresh_thread_no_flag, which passes the whole BR1.1 suite) it nests a whole verification inside the
read-back.  Simulated as the r11 tests do (an instance to_dict that raises RecursionError when the caller's stack is
deep)."""
import sys
import threading
import time

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable

o = ax.owned("battery")
eid = next(iter(o.experiments))
live = o.experiments[eid]
real = live.to_dict
nested = {"n": 0, "threads": set()}


def depth():
    n, frame = 0, sys._getframe()
    while frame is not None:
        n, frame = n + 1, frame.f_back
    return n


shallow = depth() + 40


def to_dict():
    if threading.current_thread().name != "budget-read-back" and depth() > shallow:
        raise RecursionError("maximum recursion depth exceeded")
    if threading.current_thread().name == "budget-read-back" and nested["n"] < 50:
        nested["n"] += 1
        nested["threads"].add(threading.get_ident())
        try:
            reader.read(OwnerKind.BUDGET_LEDGER, next(iter(o.ledgers)))     # a read-through hook
        except OwnerUnavailable:
            pass
    return real()


reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
live.to_dict = to_dict


def deep(k):
    return deep(k - 1) if k else reader.read(OwnerKind.EXPERIMENT, eid)


t0 = time.perf_counter()
try:
    out = "served revision " + deep(60).revision
except OwnerUnavailable as e:
    out = ("FOR GOOD: " if "from then on" in str(e) else "refused once: ") + str(e)[:100]
except BaseException as e:  # noqa: BLE001
    out = f"ESCAPED {type(e).__name__}"
print(f"deep-stack verification: {out} ({time.perf_counter() - t0:.2f} s); read-throughs on fresh threads: "
      f"{nested['n']}; tickets issued: {reader._tickets}; in flight after: {sorted(reader._in_flight)}")
