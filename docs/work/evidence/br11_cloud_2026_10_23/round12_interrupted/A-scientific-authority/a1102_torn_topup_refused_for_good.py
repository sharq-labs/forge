"""Lens A r11: an honest in-place top-up (README §4: 'a top-up with the history unchanged is a move of the owner') that
a verification reads while it is being made.  The interleaving is forced deterministically with sys.settrace (it stands
for a thread switch on the verifying thread at one line of the owner's own to_dict): the execution side raises the
total and then the reservation (the only order in which each step is a valid ledger), and the verification's to_dict
read the total before and the reservation after.  The torn payload fails the owner's from_dict (ValueError), which
_written classifies as 'the state itself' (_Unreadable), not as 'moved while serialized'.
Claims tested (README §4, owners.py:325-328): 'a state that moved while it was serialized is refused for that
verification only'; 'Concurrent verifications never refuse for good an account that only moved forward'."""
import inspect, sys
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, FeasibleActionSpace, OwnerKind, admit
from engcore.sria.campaign.budget import BudgetLedger
from engcore.scientific.experiments.experiment import ScientificExperiment, ExperimentBudget
from engcore.scientific.experiments import EvaluationStatus, ScientificEvaluation

SIM = ax.base("battery")["simulate_pulse"]


def line_of(func, needle):
    src, start = inspect.getsourcelines(func)
    return next(start + i for i, s in enumerate(src) if needle in s)


def forced(target, func, needle, action):
    """Run ``action`` once, when ``func`` (on ``target``) reaches the line containing ``needle`` on this thread."""
    code, lineno, done = func.__code__, line_of(func, needle), []

    def local(frame, event, arg):
        if event == "line" and frame.f_lineno == lineno and not done:
            done.append(1)
            action()
        return local

    def tracer(frame, event, arg):
        if frame.f_code is code and frame.f_locals.get("self") is target and not done:
            return local
        return None
    return tracer, done


def run(label, o, target, func, needle, action, kind, rid):
    authorities = o.authorities()
    reader = next(r for r in authorities.readers if type(r) is BudgetReader)
    world = o.world
    r0 = admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world), authorities)
    tracer, done = forced(target, func, needle, action)
    sys.settrace(tracer)
    try:
        try:
            torn = reader.pinned().read(kind, rid)
            torn = f"read revision {torn.revision}"
        except Exception as exc:
            torn = f"{type(exc).__name__}: {str(exc)[:150]}"
    finally:
        sys.settrace(None)
    after = []
    for _ in range(3):                                      # no race any more: the account only moved forward
        try:
            rec = reader.pinned().read(kind, rid)
            after.append(f"read revision {rec.revision}")
        except Exception as exc:
            after.append(f"{type(exc).__name__}: {str(exc)[-140:]}")
    fresh = BudgetReader.following(lambda: (o.ledgers, o.experiments)).pinned().read(kind, rid)
    world2 = o.world
    r1 = admit(FeasibleActionSpace.build(world2), o.propose("simulate_pulse", *SIM, world=world2), authorities)
    print(f"== {label}")
    print("  baseline admission:", r0.status.value, "| interleaving forced:", bool(done))
    print("  torn verification:", torn)
    for a in after:
        print("  later verification:", a)
    print("  a NEW reader over the same accounts reads:", "revision", fresh.revision)
    print("  admission through the same desk readers after the top-up:", r1.status.value, r1.codes())


# 1. ledger: total raised, then reservation raised (each step a valid ledger)
o = ax.owned("battery")
lid = next(k for k in o.ledgers if k.endswith(".solver"))
led = o.ledgers[lid]
T0 = led.total_budget


def topup():
    led.total_budget = T0 + 100.0
    led.reserved_validation_budget = T0 + 10.0              # <= the new total; > the old total


run("ledger top-up read between total and reservation", o, led, BudgetLedger.to_dict, '"reserved_validation_budget"',
    topup, OwnerKind.BUDGET_LEDGER, lid)

# 2. experiment: budget raised, then one more evaluation recorded (each step a valid experiment)
o = ax.owned("battery")
eid = next(iter(o.experiments), None)
if eid is None:
    print("battery has no experiment")
else:
    exp = o.experiments[eid]
    b0 = exp.budget

    def more():
        exp.budget = ExperimentBudget(b0.max_observations + 5)
        while exp.remaining_observations > 4:               # fill the old budget, then one beyond it
            exp.record(ScientificEvaluation(f"x{exp.attempts}", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
        exp.record(ScientificEvaluation(f"x{exp.attempts}", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
    print("experiment budget", b0, "observations", exp.observations)
    run("experiment top-up + record read between budget and evaluations", o, exp, ScientificExperiment.to_dict,
        '"evaluations"', more, OwnerKind.EXPERIMENT, eid)
