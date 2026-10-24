import sys, inspect
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
exp = ax.experiment("camp", 1000, 1)
nest = {"d": [1, 2, 3]}
for i in range(12):
    nest = {f"k{i}": nest}
exp.record(ScientificEvaluation("camp.2", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x", metadata={"run": nest}))
reader = BudgetReader.following(lambda: ({}, {"camp": exp}))
n = [2]
def deep(k):
    if k:
        return deep(k - 1)
    try:
        return "served " + reader.read(OwnerKind.EXPERIMENT, "camp").revision
    except OwnerUnavailable as exc:
        return "refused: " + str(exc)[:120]
    except RecursionError:
        return "RecursionError raised by the reader itself (caller's stack exhausted)"
base = len(inspect.stack(0))
out = {}
for margin in range(80, 10, -2):
    exp.record(ScientificEvaluation(f"camp.{n[0]+1}", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x")); n[0] += 1
    r = deep(sys.getrecursionlimit() - base - margin)
    out.setdefault(r.split(" ")[0], []).append(margin)
print({k: (min(v), max(v), len(v)) for k, v in out.items()})
print("later, at normal depth:", reader.read(OwnerKind.EXPERIMENT, "camp").revision, "| for good:", dict(reader._diverged))
