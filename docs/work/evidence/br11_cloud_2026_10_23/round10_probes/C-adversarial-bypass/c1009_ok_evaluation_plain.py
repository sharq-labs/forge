"""R10-C c1009: is an experiment holding ordinary OK evaluations (the core test suite's own canonical evaluation, with a
ScientificResult, objective values and a constraint check) plain JSON data to round 9's follower?"""
import importlib.util, sys
spec = importlib.util.spec_from_file_location("tsc", "/home/user/forge/tests/test_scientific_core.py")
tsc = importlib.util.module_from_spec(spec); spec.loader.exec_module(tsc)
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable
from engcore.mind.world.owners import _plain
from engcore.scientific.experiments.experiment import ExperimentBudget, ScientificExperiment

def walk(x, path="$"):
    t = type(x)
    if t is dict:
        for k, v in x.items():
            r = walk(v, f"{path}.{k}")
            if r: return r
    elif t in (list, tuple):
        for i, v in enumerate(x):
            r = walk(v, f"{path}[{i}]")
            if r: return r
    elif t not in (str, int, float, bool, type(None)):
        return f"{path}: {t.__name__}"
    return None

for label, kw in (("OK evaluation", {}), ("OK evaluation, validity assessed", {"assessed": True}),
                  ("NOT_CONVERGED-style (no result)", {"status": tsc.EvaluationStatus.NOT_CONVERGED})):
    exp = ScientificExperiment("exp-1", tsc.build_algebraic_problem(), ExperimentBudget(max_observations=5))
    exp.record(tsc._evaluation(1, 5.0, **kw))
    payload = exp.to_dict()
    try:
        BudgetReader({}, {"exp-1": exp}).read(OwnerKind.EXPERIMENT, "exp-1")
        res = "READ"
    except OwnerUnavailable as exc:
        res = "REFUSED (" + str(exc)[-60:] + ")"
    print(f"{label:34s} plain={_plain(payload)} first non-plain: {walk(payload)} | BudgetReader: {res}")
