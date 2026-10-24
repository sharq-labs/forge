"""R12-B b1203 (adapted from r11 p28): verify an honest experiment (nested evaluation metadata) from call stacks with
less and less headroom; the account moves forward before each verification (recorded OUTSIDE the deep stack).  Report
what each verification gets (served / refused for this verification / refused for good / an exception escaping the
reader), and whether a later verification at normal depth is then refused for good (B11-1 / round-11 fresh-thread
retry)."""
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
    try:
        return "served " + reader.read(OwnerKind.EXPERIMENT, "camp").revision
    except OwnerUnavailable as exc:
        return ("FOR GOOD " if "from then on" in str(exc) else "refused once ") + str(exc)
    except BaseException as exc:  # noqa: BLE001
        return f"ESCAPED {type(exc).__name__}"


base = len(__import__("inspect").stack(0))
seen = {}
for margin in range(120, 0, -1):
    n[0] += 1
    exp.record(ScientificEvaluation(f"camp.{n[0]}", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
    try:
        r = deep(sys.getrecursionlimit() - base - margin)
    except RecursionError:
        r = "ESCAPED RecursionError (outside)"
    kind = r.split(" ")[0]
    seen.setdefault(kind, (margin, r[:150]))
for k, (m, r) in seen.items():
    print(f"first at headroom {m}: {r}")
try:
    print("later, at normal depth:", reader.read(OwnerKind.EXPERIMENT, "camp").revision, "diverged:", reader._diverged)
except OwnerUnavailable as exc:
    print("later, at normal depth: refused:", str(exc)[:220])
print("in flight:", reader._in_flight)
