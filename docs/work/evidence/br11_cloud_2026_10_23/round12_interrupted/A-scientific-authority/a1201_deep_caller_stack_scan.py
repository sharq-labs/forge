"""Lens A r12: README §4 / owners.py docstring (round 11): 'When every attempt hits the interpreter's recursion limit,
the read-back is tried once more on a fresh thread (a shallow stack), so a verification's own deep call stack never
refuses an honest account for good.'

Real code, no monkeypatching: an honest experiment (the battery fixture's, plus one recorded evaluation with candidate
quantities, so its owner's from_dict parses units) is read back by a verification called from a caller stack of depth
k.  For each k we build a fresh following reader at shallow depth, record one more evaluation (so the read-back is not
served from the cache), then read at depth k.  We classify: READ, a RecursionError raised out of the reader
(documented: 'the caller's own stack exhausted inside the reader'), OwnerUnavailable for this verification only, or
REFUSED FOR GOOD (the account in reader._diverged).  Then, at shallow depth, a NEW reader reads the same account
(proving the owner reads it back)."""
import sys
from collections import Counter

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.units.quantity import Quantity

KIND = sys.argv[1] if len(sys.argv) > 1 else "experiment"


def depth():
    n, f = 0, sys._getframe()
    while f is not None:
        n, f = n + 1, f.f_back
    return n


def one(k):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    lid = next(x for x in o.ledgers if x.endswith(".solver"))
    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    if KIND == "experiment":
        exp = o.experiments[eid]
        var = exp.problem.design_variables[0] if exp.problem.design_variables else None
        cand = {}
        if var is not None:
            lo = var.lower if hasattr(var, "lower") else None
            cand = {}
        exp.record(ScientificEvaluation(f"deep.{k}", cand, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
        target = (OwnerKind.EXPERIMENT, eid)
    else:
        from engcore.sria.decision import ActionFamily
        o.ledgers[lid].settle(charge_id=f"deep.{k}", action_id="a", iteration=1, family=ActionFamily.EXPLORE,
                              realized=0.5)
        target = (OwnerKind.BUDGET_LEDGER, lid)

    def deep(n):
        return deep(n - 1) if n else reader.read(*target)

    try:
        rec = deep(k)
        out = "READ"
    except RecursionError as exc:
        out = "RecursionError raised out of the reader"
    except OwnerUnavailable as exc:
        msg = str(exc)
        out = "REFUSED FOR GOOD: " + msg[:200] if "from then on" in msg else "refused once: " + msg[:160]
    except Exception as exc:
        out = f"OTHER {type(exc).__name__}: {str(exc)[:160]}"
    good = (target[0].value if hasattr(target[0], "value") else str(target[0]), target[1]) and \
        any(True for key in reader._diverged)
    fresh = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments))).read(*target)
    return out, bool(reader._diverged), fresh is not None


base = depth()
limit = sys.getrecursionlimit()
results = Counter()
examples = {}
for k in range(limit - base - 260, limit - base - 2, 1):
    out, diverged, fresh_ok = one(k)
    label = out.split(":")[0]
    results[(label, diverged, fresh_ok)] += 1
    examples.setdefault((label, diverged, fresh_ok), (k, out))
print("kind", KIND, "recursion limit", limit, "base depth", base)
for key, n in sorted(results.items(), key=str):
    print(n, key, "e.g. k =", examples[key][0], "|", examples[key][1][:260])
