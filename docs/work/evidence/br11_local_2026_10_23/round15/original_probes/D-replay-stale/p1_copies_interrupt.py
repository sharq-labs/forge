"""P1: an execution side whose accounts() hands detached copies (a persisted / checkpoint-backed store) loses an account
for good after ONE interrupted read-back of a state with NO new entry; the same side handing its live objects does not.

Both sides are honest and single-threaded.  The interrupt is a KeyboardInterrupt raised once inside the read-back
(standing in for Ctrl-C arriving while the read-back runs; the reader treats a KeyboardInterrupt from content as an
interrupt, re-raised after comparing).  No charge is settled between the last good read and the end of the probe."""
import sys

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, ExecutionDesk, FeasibleActionSpace, admit
from engcore.mind.world.authority import OwnerUnavailable
from engcore.mind.world.projection import project_world
from engcore.scientific.experiments.experiment import ScientificExperiment
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]


class Flaky:
    """A charge detail that renders as 'note' always, except once, when armed (the Ctrl-C stand-in)."""
    armed = False

    def __str__(self):
        if Flaky.armed:
            Flaky.armed = False
            raise KeyboardInterrupt
        return "note"


def run(copies: bool):
    o = ax.owned("battery")
    lid = next(k for k in o.ledgers if k.endswith(".solver"))
    o.ledgers[lid].settle(charge_id="setup", action_id="other", iteration=1, family=ActionFamily.EXPLORE,
                          realized=0.1, detail=Flaky())

    def accounts():
        if copies:   # the store hands what a checkpoint restore of each account gives
            return ({k: BudgetLedger.from_dict(v.to_dict()) for k, v in o.ledgers.items()},
                    {k: ScientificExperiment.from_dict(v.to_dict()) for k, v in o.experiments.items()})
        return dict(o.ledgers), dict(o.experiments)

    reader = BudgetReader.following(accounts)
    base = o.authorities()
    authorities = type(base).of(*(reader if type(r) is BudgetReader else r for r in base.readers))
    gateway = ExecutionDesk(authorities, lambda a: None, accept_synthetic=True).gateway()

    def attempt(tag):
        try:
            world = project_world(o.declaration, authorities)
        except OwnerUnavailable as exc:
            print(f"  [{tag}] projection refused: {str(exc)[:150]}")
            return
        r = gateway.admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world))
        why = [rr.detail.get("why", "")[:150] for rr in r.reasons if rr.code.startswith("AUTHORITY")]
        print(f"  [{tag}] {r.status.value} {why}")

    print(f"copies={copies}")
    attempt("before")
    attempt("before-2")
    Flaky.armed = True
    try:
        attempt("interrupted")
    except KeyboardInterrupt:
        print("  [interrupted] KeyboardInterrupt re-raised to the caller (caught, as an interactive session does)")
    for i in range(3):
        attempt(f"after-{i}")
    print("  diverged:", {k: v[:80] for k, v in reader._diverged.items()})


run(copies=False)
run(copies=True)
