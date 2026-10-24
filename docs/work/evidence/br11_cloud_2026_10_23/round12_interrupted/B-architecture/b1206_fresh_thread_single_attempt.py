"""R12-B b1206: _account's fresh-thread retry (taken when all three attempts hit RecursionError) is ONE attempt whose
failure is classified for good unless it is the interpreter's mutation error: a verification on a deep call stack
whose fresh-thread read-back is torn by an honest concurrent top-up (the owner's own ValueError, which the three-attempt
rule would have retried) refuses the honest account for good.  Simulated the way the r11 tests do (an instance
to_dict that raises RecursionError when the caller's stack is deep, and returns one torn dict on the fresh thread,
standing for a read across the two steps of a top-up)."""
import sys
import threading

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable

o = ax.owned("battery")
lid = next(k for k in o.ledgers if k.endswith(".solver"))
live = o.ledgers[lid]
real = live.to_dict


def depth():
    n, frame = 0, sys._getframe()
    while frame is not None:
        n, frame = n + 1, frame.f_back
    return n


shallow = depth() + 40
torn = {"n": 0}


def to_dict():
    if threading.current_thread().name != "budget-read-back" and depth() > shallow:
        raise RecursionError("maximum recursion depth exceeded")     # the caller's deep stack
    out = real()
    if threading.current_thread().name == "budget-read-back" and torn["n"] == 0:
        torn["n"] += 1                                                 # the fresh thread reads across a top-up
        out["reserved_validation_budget"] = out["total_budget"] + 1.0
    return out


reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
object.__setattr__(live, "to_dict", to_dict) if False else setattr(live, "to_dict", to_dict)


def deep(k):
    return deep(k - 1) if k else reader.read(OwnerKind.BUDGET_LEDGER, lid)


for label, call in (("deep-stack verification (fresh-thread retry torn once)", lambda: deep(60)),
                    ("later verification at normal depth, account at rest", lambda: reader.read(OwnerKind.BUDGET_LEDGER,
                                                                                               lid))):
    try:
        print(label, "-> served revision", call().revision)
    except OwnerUnavailable as e:
        print(label, "->", "FOR GOOD:" if "from then on" in str(e) else "refused once:", str(e)[:160])
print("owner reads the account back at rest:", type(live).from_dict(real()).revision)
