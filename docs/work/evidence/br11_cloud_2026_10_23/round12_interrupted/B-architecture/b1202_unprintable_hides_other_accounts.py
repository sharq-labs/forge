"""R12-B b1202: the b1201 escape also (1) makes every admission raise while an account NO world reads holds such a
value (README/docstring: 'an account no world reads refuses nothing'), and (2) hides a spend on ANOTHER, well-formed
account handed to the same verification (the F11-2 consequence): the executor records an observation on the bound
experiment and writes a run note into an unbound side ledger; verifications raise; the execution side restores its
pre-run checkpoint (both accounts); the admitted action is re-dispatched.  Controls: the same with a renderable
failure, and with a plain str note."""
import copy

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, admit
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ScientificExperiment
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]


class Unprintable(LookupError):
    def __str__(self):
        raise LookupError("message not available")


class Note:
    def __init__(self, exc):
        self.exc = exc

    def __str__(self):
        if self.exc is None:
            return "plain note"
        raise self.exc


def desk(o, executor):
    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    auth = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    space = FeasibleActionSpace.build(o.world)
    r = admit(space, o.propose("simulate_pulse", *SIM), auth)
    assert r.admitted is not None, r.status
    return reader, space, ExecutionDesk(auth, executor, accept_synthetic=True).gateway(), r


def unbound(exc, label):
    o = ax.owned("battery")
    reader, space, gw, r = desk(o, lambda a: None)
    side = BudgetLedger(total_budget=5.0, cost_unit="hour")
    side.settle(charge_id="note", action_id="log", iteration=0, family=ActionFamily.EXPLORE, realized=0.0,
                detail=Note(exc))
    o.ledgers["side.notes"] = side            # an account no world reads
    try:
        a = gw.admit(space, o.propose("simulate_pulse", *SIM))
        out = f"{a.status.value} {a.codes()}"
    except Exception as e:  # noqa: BLE001
        out = f"RAISED {type(e).__name__}"
    print(f"(1) [{label}] unbound side ledger; admission of a world that never reads it -> {out}")


def other(exc, label):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    o.ledgers["side.notes"] = BudgetLedger(total_budget=5.0, cost_unit="hour")
    calls = []

    def executor(a):
        calls.append(1)
        o.experiments[eid].record(ScientificEvaluation(f"run.{len(calls)}", {}, status=EvaluationStatus.NOT_CONVERGED,
                                                       detail="observed"))
        o.ledgers["side.notes"].settle(charge_id=f"note.{len(calls)}", action_id="log", iteration=1,
                                       family=ActionFamily.EXPLORE, realized=0.0, detail=Note(exc))

    reader, space, gw, r = desk(o, executor)
    exp_before = ScientificExperiment.from_dict(o.experiments[eid].to_dict())
    side_before = BudgetLedger.from_dict(copy.deepcopy(o.ledgers["side.notes"].to_dict()))
    gw.dispatch(r.admitted)
    spent_len = len(o.experiments[eid].evaluations)
    seen = []
    for _ in range(2):
        try:
            a = gw.admit(space, o.propose("simulate_pulse", *SIM))
            seen.append(f"{a.status.value} {a.codes()}")
        except Exception as e:  # noqa: BLE001
            seen.append(f"RAISED {type(e).__name__}")
    recorded = len(reader._seen.get(("experiment", eid), ()))
    o.experiments[eid] = exp_before          # restore the pre-run checkpoint (objects replaced)
    o.ledgers["side.notes"] = side_before
    try:
        gw.dispatch(r.admitted)
        again = "DISPATCHED AGAIN"
    except DispatchRefused as e:
        again = "refused: " + str(e)[:60]
    except Exception as e:  # noqa: BLE001
        again = f"RAISED {type(e).__name__}"
    print(f"(2) [{label}] admissions on the spent state: {seen}; experiment history recorded: {recorded} evaluations "
          f"(the spent state handed: {spent_len}); re-dispatch after the restore: {again}; executor ran "
          f"{len(calls)}")


for exc, label in ((Unprintable(), "unrenderable failure"), (TypeError("plain"), "control: renderable failure"),
                   (None, "control: str note")):
    unbound(exc, label)
for exc, label in ((Unprintable(), "unrenderable failure"), (TypeError("plain"), "control: renderable failure"),
                   (None, "control: str note")):
    other(exc, label)
