"""Lens A r12: the same claim as a1201 ('a verification's own deep call stack never refuses an honest account for
good'), with an honest evaluation that records a candidate quantity in a unit this process has not yet read back
(each k uses another SI-prefixed unit).  The execution side constructs the Quantity at shallow depth (its own spelling
is normalized and cached there); the read-back's from_dict normalizes the WRITTEN spelling, which may be a first parse.
The unit owner wraps every backend exception, RecursionError included, into UnitCompatibilityError
(quantity.py:591, :808), so a recursion limit hit inside the parse is not seen as recursion by _account."""
import sys
from collections import Counter

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.units.quantity import Quantity

PREFIX = ["y", "z", "a", "f", "p", "n", "u", "m", "c", "d", "da", "h", "k", "M", "G", "T", "P", "E", "Z", "Y"]
BASE = ["A", "V", "W", "s", "m", "g", "Hz", "ohm", "F", "H", "T", "Wb", "C", "Pa", "J", "N", "mol", "cd", "L", "S",
        "Gy", "Sv", "kat", "lm", "lx", "Bq", "bar", "eV"]
UNITS = []
for b in BASE:
    for p in PREFIX:
        try:
            Quantity(1.0, p + b)
        except Exception:
            continue
        UNITS.append(p + b)
# NOTE: constructing them above already normalized each spelling once (as the execution side would)


def depth():
    n, f = 0, sys._getframe()
    while f is not None:
        n, f = n + 1, f.f_back
    return n


def one(k, unit):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    exp = o.experiments[eid]
    exp.record(ScientificEvaluation(f"deep.{k}", {"x": Quantity(1.5, unit)}, status=EvaluationStatus.NOT_CONVERGED,
                                    detail="x"))

    def deep(n):
        return deep(n - 1) if n else reader.read(OwnerKind.EXPERIMENT, eid)

    try:
        deep(k)
        out = "READ"
    except RecursionError:
        out = "RecursionError raised out of the reader"
    except OwnerUnavailable as exc:
        msg = str(exc)
        out = ("REFUSED FOR GOOD: " if "from then on" in msg else "refused once: ") + msg[:300]
    except Exception as exc:
        out = f"OTHER {type(exc).__name__}: {str(exc)[:160]}"
    fresh = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments))).read(OwnerKind.EXPERIMENT, eid)
    return out, bool(reader._diverged), fresh is not None


base = depth()
limit = sys.getrecursionlimit()
print("units available", len(UNITS))
results, examples = Counter(), {}
ks = list(range(limit - base - 200, limit - base - 2))
for k, unit in zip(ks, UNITS):
    out, diverged, fresh_ok = one(k, unit)
    label = out.split(":")[0]
    results[(label, diverged, fresh_ok)] += 1
    examples.setdefault((label, diverged, fresh_ok), (k, unit, out))
for key, n in sorted(results.items(), key=str):
    print(n, key, "e.g. k =", examples[key][0], examples[key][1], "|", examples[key][2][:400])
