"""R15-F probe 3: README section 4 (F14-F5 restatement) says an interrupt inside the read-back is re-raised only after
the comparison.  The 'before' listing (owners.py:607) runs outside _read_back's try, so a ctrl-C landing as it is called
for the SECOND handed account escapes _read_back: the first account's read state (holding the spend) is never compared,
and after a restore the executed action is dispatched again.  The same ctrl-C landing one call later (inside _account)
is caught and the spend is recorded.  The ctrl-C is placed deterministically with sys.settrace."""
import sys
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.mind.world.authority import OwnerUnavailable
from engcore.mind.world import owners as OW
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]


def run(target):
    o = ax.owned("battery")
    lid = next(k for k in o.ledgers if k.endswith(".solver"))
    calls = []

    def executor(a):
        calls.append(1)
        o.ledgers[lid].settle(charge_id=f"run.{len(calls)}", action_id="simulate_pulse", iteration=1,
                              family=ActionFamily.EXPLORE, realized=0.5, detail="plain")
    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    gateway = ExecutionDesk(authorities, executor, accept_synthetic=True).gateway()
    s0 = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(r.admitted)                     # S1 = S0 + run.1
    code = OW.BudgetReader._entries.__code__ if target == "listing" else OW.BudgetReader._account.__code__
    state = {"armed": True}

    def tracer(frame, event, arg):
        if event == "call" and state["armed"] and frame.f_code is code and frame.f_locals.get("key", ("",))[0] == "experiment":
            if target == "listing" and frame.f_back.f_code is not OW.BudgetReader._read_back.__code__:
                return tracer
            state["armed"] = False
            sys.settrace(None)
            raise KeyboardInterrupt
        return tracer
    sys.settrace(tracer)
    try:
        reader.pinned()
        out = "pinned"
    except KeyboardInterrupt:
        out = "KeyboardInterrupt"
    finally:
        sys.settrace(None)
    seen = len(reader._seen[("ledger", lid)])
    print(f"[ctrl-C at the {target} call for the 2nd account] verification: {out}; ledger history recorded with the "
          f"spend: {seen == len(o.ledgers[lid].charges)}")
    o.ledgers[lid] = s0                               # restore S0
    try:
        gateway.dispatch(r.admitted)
        res = "DISPATCHED AGAIN"
    except DispatchRefused as exc:
        res = "refused: " + str(exc)[:80]
    print(f"   after restoring S0, re-dispatch: {res}; executor calls = {len(calls)}")


run("listing")
run("account")
