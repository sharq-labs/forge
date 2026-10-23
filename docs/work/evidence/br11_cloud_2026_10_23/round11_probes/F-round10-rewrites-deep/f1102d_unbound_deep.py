"""R11-F f1102d: an UNBOUND experiment (no world reads it) whose metadata nests 600 deep, handed to a following reader
after construction: does an admission of a world that never reads it refuse nothing (README §4), or raise?"""
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, ExecutionDesk, FeasibleActionSpace, admit
from engcore.scientific.experiments.experiment import ExperimentBudget, ScientificExperiment
from engcore.scientific.ir.problem import ScientificProblem
SIM = ax.base("battery")["simulate_pulse"]
o = ax.owned("battery")
side = ScientificExperiment("other.campaign", ScientificProblem("other.problem"), ExperimentBudget(5))
reader = BudgetReader.following(lambda: (o.ledgers, {**o.experiments, "other.campaign": side}))
auth = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
for depth in (3, 600):
    x = {"leaf": 1}
    for i in range(depth):
        x = {f"k{i}": x}
    side.metadata["trace"] = x
    try:
        r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), auth)
        print(depth, "admission of a world that never reads 'other.campaign':", r.status.value)
    except BaseException as exc:  # noqa: BLE001
        print(depth, "admission of a world that never reads 'other.campaign': RAISED", type(exc).__name__)
