"""Lens A r12: the round-11 rule 'failures that differ ... are an account moving while it was serialized, refused to that
verification only' (owners.py _account).  An honest campaign records an evaluation while each of three read-backs is
serializing the experiment (simulated: the accounting is taken after the record, the evaluations before it, as a
thread switch inside to_dict would give).  The three failures have the SAME message and DIFFERENT texts.  Expected at
a96baa6: refused for that verification only, then read.  Mutants 'differ_not_moving' / 'why_only' refuse it for good
and pass the whole BR1.1 suite (mut_*.txt)."""
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation

o = ax.owned("battery")
eid = next(iter(o.experiments))
exp = o.experiments[eid]
reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
real = exp.to_dict
n = {"calls": 0}


def torn():
    out = real()
    n["calls"] += 1
    if n["calls"] <= 3:                                     # a record lands mid-serialization, three times running
        exp.record(ScientificEvaluation(f"camp.{n['calls']}", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
        out["accounting"] = real()["accounting"]
    return out


exp.to_dict = torn
for i in range(2):
    try:
        rec = reader.read(OwnerKind.EXPERIMENT, eid)
        print(f"verification {i + 1}: read revision {rec.revision}")
    except OwnerUnavailable as exc:
        s = str(exc)
        print(f"verification {i + 1}: {'REFUSED FOR GOOD' if 'from then on' in s else 'refused once'}: {s[:150]}")
print("refused for good by this reader:", ("experiment", eid) in reader._diverged)
