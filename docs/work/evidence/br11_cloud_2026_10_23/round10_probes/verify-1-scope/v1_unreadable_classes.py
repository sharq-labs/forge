"""verify-1-scope: does the outcome class 'a handed spend the follower cannot read back is never recorded, so a
restore over it is re-dispatched' exist at ceaf8cd for states that were ALREADY unreadable before round 9's plain rule?
Same sequence as R10-C c1008, with metadata values that the pre-round-9 read-back could not serialize/read back."""
import datetime, decimal, sys
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.mind.world.authority import OwnerUnavailable
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ScientificExperiment

SIM = ax.base("battery")["simulate_pulse"]
VARIANTS = {
    "control {}": {},
    "nested list {'seeds':[1,2]}": {"seeds": [1, 2]},
    "nan float": {"x": float("nan")},
    "datetime": {"t": datetime.datetime(2026, 1, 1)},
    "bytes": {"b": b"ab"},
    "set": {"s": {1, 2}},
    "Decimal": {"d": decimal.Decimal("1.5")},
    "int key": {"m": {1: "a"}},
    "object()": {"o": object()},
}


def run(label, meta):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    calls = []

    def executor(authorization):
        calls.append(1)
        o.experiments[eid].record(ScientificEvaluation(f"run.{len(calls)}", {}, status=EvaluationStatus.NOT_CONVERGED,
                                                       detail="observed", metadata=meta))
        return "ran"

    try:
        gateway = ExecutionDesk(authorities, executor, accept_synthetic=True).gateway()
        before = ScientificExperiment.from_dict(o.experiments[eid].to_dict())
        gateway.dispatch(r.admitted)
    except Exception as exc:  # noqa: BLE001
        print(f"{label:30s} | setup/record failed: {type(exc).__name__}: {str(exc)[:80]}")
        return
    try:
        owner_back = len(ScientificExperiment.from_dict(o.experiments[eid].to_dict()).evaluations)
    except Exception as exc:  # noqa: BLE001
        owner_back = f"owner from_dict fails: {type(exc).__name__}"
    try:
        seen = f"read revision {reader.read(OwnerKind.EXPERIMENT, eid).revision}"
    except OwnerUnavailable as exc:
        seen = f"refused: {str(exc)[60:140]}"
    o.experiments[eid] = before
    try:
        gateway.dispatch(r.admitted)
        after = "DISPATCHED AGAIN"
    except DispatchRefused as exc:
        after = "refused " + str(exc)[str(exc).find("("):][:60]
    print(f"{label:30s} | owner read-back: {owner_back} | follower: {seen}\n{'':30s} | after restore: {after} | ran {len(calls)}")


for label, meta in VARIANTS.items():
    run(label, meta)
