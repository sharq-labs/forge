"""R11-C c1107 (adapts R10-C c1009): an experiment holding the core suite's canonical OK evaluations (ScientificResult,
objective values, constraint checks) through round 10's read-back: read, and is the read-back a fixed point (the same
content gives the same history and digest on a cold cache, i.e. from a second follower)?  A spend recorded and a restore
from the owner's checkpoint: is the spend observed and the restore refused (no re-dispatch-equivalent acceptance)?"""
import importlib.util
import json

spec = importlib.util.spec_from_file_location("tsc", "/home/user/forge/tests/test_scientific_core.py")
tsc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tsc)
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable
from engcore.scientific import to_json
from engcore.scientific.experiments.experiment import ExperimentBudget, ScientificExperiment

for label, kw in (("OK evaluation", {}), ("OK evaluation, validity assessed", {"assessed": True}),
                  ("NOT_CONVERGED-style (no result)", {"status": tsc.EvaluationStatus.NOT_CONVERGED})):
    exp = ScientificExperiment("exp-1", tsc.build_algebraic_problem(), ExperimentBudget(max_observations=5))
    exp.record(tsc._evaluation(1, 5.0, **kw))
    mapping = {"exp-1": exp}
    r1 = BudgetReader.following(lambda: ({}, mapping))
    r2 = BudgetReader.following(lambda: ({}, mapping))
    a = r1.read(OwnerKind.EXPERIMENT, "exp-1")
    b = r2.read(OwnerKind.EXPERIMENT, "exp-1")
    same = (a.record_digest == b.record_digest and r1._seen == r2._seen)
    rebuilt = ScientificExperiment.from_dict(json.loads(to_json(exp)))
    again = ScientificExperiment.from_dict(json.loads(to_json(rebuilt)))
    fixed = to_json(rebuilt) == to_json(again)
    checkpoint = exp.to_dict()
    exp.record(tsc._evaluation(2, 6.0, **kw))                           # the spend
    spent = r1.read(OwnerKind.EXPERIMENT, "exp-1").revision
    mapping["exp-1"] = ScientificExperiment.from_dict(checkpoint)         # the restore
    try:
        r1.read(OwnerKind.EXPERIMENT, "exp-1")
        after = "ACCEPTED (re-authorizes)"
    except OwnerUnavailable as exc:
        after = "refused: " + str(exc)[:60]
    print(f"{label:34s} read rev {a.revision}; cold-cache identical: {same}; read-back fixed point: {fixed}; "
          f"spend observed rev {spent}; restore: {after}")
