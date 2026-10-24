"""R11-C c1102: an account that only moved FORWARD (a budget top-up, then one recorded observation, by the execution
side on another thread) is refused by the following reader FOR GOOD when a verification serializes it while it moves.

round 10's _written / _account classify every failure of the owner's from_dict on the account's own text as
_Unreadable (refused for good, like a rewrite); only a RuntimeError, or a torn accounting check that runs AFTER from_dict
succeeded, is 'moved while serialized' (this verification only).  A to_json(exp) taken across a top-up + record writes
the OLD budget (serialized before the evaluations) with the NEW evaluation: the owner's from_dict replays record() under
the old budget and raises 'observation budget exhausted' -> _Unreadable -> _diverged for good.

README section 4 claims 'Concurrent verifications never refuse for good an account that only moved forward', and the
_written docstring claims a RuntimeError is the only 'moved while serialized' failure.  The race is forced
deterministically: sys.settrace on the verifying thread pauses it at its first ScientificEvaluation.to_dict call (the
budget is already written) and lets the execution-side thread top up and record, then resumes.  Public API only:
the fixture's own live authorities (BudgetReader.following), ExecutionDesk(...).gateway(), project_world, admit."""
import sys
import threading

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import ExecutionDesk, FeasibleActionSpace, project_world
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ExperimentBudget

SIM = ax.base("battery")["simulate_pulse"]


def scenario(race: bool) -> None:
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    exp = o.experiments[eid]
    while exp.remaining_observations:                                    # the study used its whole budget
        exp.record(ScientificEvaluation(f"pre.{exp.attempts}", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
    auth = o.authorities()
    gateway = ExecutionDesk(auth, lambda a: "ran", accept_synthetic=True).gateway()

    def top_up_and_record():                                             # the execution side: top-up, then one run
        exp.budget = ExperimentBudget(exp.budget.max_observations + 10)
        exp.record(ScientificEvaluation("run.after-top-up", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))

    go, done = threading.Event(), threading.Event()
    other = threading.Thread(target=lambda: (go.wait(10), top_up_and_record(), done.set()), daemon=True)
    other.start()
    target = ScientificEvaluation.to_dict.__code__
    fired = {"n": 0}

    def tracer(frame, event, arg):
        if event == "call" and frame.f_code is target and not fired["n"]:
            fired["n"] = 1
            go.set()                                                     # the other thread moves the account now
            done.wait(10)
        return None

    world = o.world
    if race:
        sys.settrace(tracer)
        try:
            r1 = gateway.admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM))
        finally:
            sys.settrace(None)
    else:
        top_up_and_record()
        r1 = gateway.admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM))
    other.join(5)
    print(f"  the verification during the move: {r1.status.value} {r1.codes()}")
    print(f"  account now: {exp.budget}, observations {exp.observations} (history only extended)")
    for k in range(2):
        try:
            fresh = project_world(o.declaration, auth)
            r = gateway.admit(FeasibleActionSpace.build(fresh), o.propose("simulate_pulse", *SIM, world=fresh))
            why = [c.detail.get("why", "")[:110] for c in r.verification.checks if c.status.name != "VERIFIED"]
            print(f"  later admission {k + 1} on a fresh projection: {r.status.value} {r.codes()} {why}")
        except Exception as exc:  # noqa: BLE001
            print(f"  later projection {k + 1}: {type(exc).__name__}: {str(exc)[:200]}")


print("control (top-up and record with no verification in between):")
scenario(False)
print("race (a verification serializes the experiment while it is topped up and one observation is recorded):")
scenario(True)
