"""R10-C c1008: c1007 for the observation account.  ScientificEvaluation freezes its metadata (results.immutable.freeze:
a nested dict becomes FrozenMapping, a list FrozenList), and ScientificEvaluation.to_dict hands the frozen values on;
round 9 reads an experiment back only when exp.to_dict() is exactly plain JSON data (owners.py:376-379).  The executed
action records its observation as an evaluation carrying ordinary nested metadata; a verification is handed that
spend; the execution side restores the pre-spend experiment (object-replacing, as sria.campaign restores); re-dispatch.
Sequential: no concurrency.  Public paths only (BudgetReader.following + ExecutionDesk.gateway())."""
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.mind.world.authority import OwnerUnavailable
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ScientificExperiment

SIM = ax.base("battery")["simulate_pulse"]
VARIANTS = {
    "no metadata (control)": {},
    "metadata {'seeds': [1, 2]}": {"seeds": [1, 2]},
    "metadata {'run': {'host': 'a'}}": {"run": {"host": "a"}},
}


def run(label, meta):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    calls = []

    def executor(authorization):
        calls.append(authorization.admitted_digest)
        o.experiments[eid].record(ScientificEvaluation(f"run.{len(calls)}", {}, status=EvaluationStatus.NOT_CONVERGED,
                                                       detail="observed", metadata=meta))
        return "ran"

    gateway = ExecutionDesk(authorities, executor, accept_synthetic=True).gateway()
    before = ScientificExperiment.from_dict(o.experiments[eid].to_dict())
    gateway.dispatch(r.admitted)                                    # the executor records its evaluation (in place)
    owner = ScientificExperiment.from_dict(o.experiments[eid].to_dict())
    try:
        seen = f"read revision {reader.read(OwnerKind.EXPERIMENT, eid).revision}"
    except OwnerUnavailable as exc:
        seen = f"refused: {str(exc)[:80]}"
    o.experiments[eid] = before                                     # the execution side restores the experiment
    try:
        gateway.dispatch(r.admitted)
        after = "DISPATCHED AGAIN"
    except DispatchRefused as exc:
        after = "refused " + str(exc)[str(exc).find("("):][:60]
    print(f"{label:34s} | the owner reads the spend back: {len(owner.evaluations)} evaluations | follower on the "
          f"spend: {seen}\n{'':34s} | after the restore: {after} | executor ran {len(calls)}")


for label, meta in VARIANTS.items():
    run(label, meta)
