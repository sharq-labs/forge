"""RecursionError is classified 'for good' (owners.py:116-117) as a property of the state, but whether the owner's
serialization hits the recursion limit also depends on how deep the VERIFYING call stack already is.  Scan: verify an
honest, ordinarily readable experiment (nested evaluation metadata) from a call stack with less and less headroom;
report what each verification gets, and whether a later verification at normal depth is then refused for good."""
import sys
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation

exp = ax.experiment("camp", 1000, 1)
nest = {"d": [1, 2, 3]}
for i in range(int(sys.argv[1]) if len(sys.argv) > 1 else 12):
    nest = {f"k{i}": nest}
exp.record(ScientificEvaluation("camp.2", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x", metadata={"run": nest}))
reader = BudgetReader.following(lambda: ({}, {"camp": exp}))
print("at normal depth:", reader.read(OwnerKind.EXPERIMENT, "camp").revision)
n = [2]

def deep(k):
    if k:
        return deep(k - 1)
    n[0] += 1
    exp.record(ScientificEvaluation(f"camp.{n[0]}", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))  # moves on
    try:
        return "served " + reader.read(OwnerKind.EXPERIMENT, "camp").revision
    except OwnerUnavailable as exc:
        return "refused: " + str(exc)
    except RecursionError as exc:
        return "raw RecursionError escaped the reader"

base = len(__import__("inspect").stack(0))
seen = set()
for margin in range(80, 0, -2):
    r = deep(sys.getrecursionlimit() - base - margin)
    kind = r.split(":")[0].split(" ")[0]
    if kind not in seen:
        seen.add(kind); print(f"headroom {margin}:", r[:170])
    if "from then on" in r:
        break
try:
    print("later, at normal depth:", reader.read(OwnerKind.EXPERIMENT, "camp").revision)
except OwnerUnavailable as exc:
    print("later, at normal depth: refused:", str(exc)[:220])
