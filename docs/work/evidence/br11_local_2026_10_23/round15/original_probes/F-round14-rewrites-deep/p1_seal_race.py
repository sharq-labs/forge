"""R15-F probe 1: the seal (CRIT14-1 fix) is checked only when pinned() starts.  A verification already past that check
when another verification is handed a non-dict mapping (and seals the reader) still compares and decides after the seal.
If the sealing verification left before the in-flight one compared, nothing refuses: the executed action is dispatched
again through ExecutionDesk.gateway() after a restore.  Deterministic: events, no timing luck."""
import threading, types, sys
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.mind.world.authority import OwnerUnavailable
from engcore.mind.world.admission import AdmissionRecord
from engcore.mind.world.projection import project_world
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]

def run(mode):
    o = ax.owned("battery")
    lid = next(k for k in o.ledgers if k.endswith(".solver"))
    good_inside, good_go = threading.Event(), threading.Event()

    def accounts():
        name = threading.current_thread().name
        if name == "GOOD":
            good_inside.set()
            good_go.wait(10)                    # GOOD was past the seal check; it is handed the state after the restore
        ledgers = dict(o.ledgers)
        if name == "BAD":
            return types.MappingProxyType(ledgers), dict(o.experiments)    # an honest non-dict mapping: seals
        return ledgers, dict(o.experiments)

    calls = []
    def executor(authorization):
        calls.append(1)
        o.ledgers[lid].settle(charge_id=f"run.{len(calls)}", action_id="simulate_pulse", iteration=1,
                              family=ActionFamily.EXPLORE, realized=0.5, detail="plain")

    reader = BudgetReader.following(accounts)
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    assert r.admitted is not None
    gateway = ExecutionDesk(authorities, executor, accept_synthetic=True).gateway()
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())        # checkpoint S0
    gateway.dispatch(r.admitted)                                      # executes: S1 = S0 + run.1 (never read back)
    assert len(calls) == 1
    out = {}
    def good():
        try:
            if mode == "redispatch":
                gateway.dispatch(r.admitted)                          # the SAME authorization, re-dispatched
                out["good"] = "DISPATCHED AGAIN"
            else:
                rec = AdmissionRecord.of(r, authorities)
                out["good"] = "AdmissionRecord.of ACCEPTED the original admission (S0) after the seal"
        except (DispatchRefused, OwnerUnavailable, Exception) as exc:
            out["good"] = f"refused: {type(exc).__name__}: {str(exc)[:160]}"
    tg = threading.Thread(target=good, name="GOOD", daemon=True)
    tg.start()
    assert good_inside.wait(10)                                       # GOOD is past the seal check, in accounts()
    def bad():
        try:
            reader.pinned()
            out["bad"] = "pinned"
        except OwnerUnavailable as exc:
            out["bad"] = "refused: " + str(exc)[:110]
    tb = threading.Thread(target=bad, name="BAD"); tb.start(); tb.join(10)   # BAD is handed S1 in a proxy: sealed
    print(f"[{mode}] BAD: {out['bad']}")
    print(f"[{mode}] sealed: {reader._sealed is not None}")
    o.ledgers[lid] = before                                           # the campaign restores checkpoint S0
    good_go.set(); tg.join(10)
    print(f"[{mode}] GOOD (started before the seal, handed S0 after it): {out['good']}")
    print(f"[{mode}] executor calls = {len(calls)}")
    try:
        reader.pinned(); print(f"[{mode}] a new verification: pinned")
    except OwnerUnavailable as exc:
        print(f"[{mode}] a new verification after GOOD: refused ({str(exc)[:60]}...)")

for mode in ("redispatch", "record"):
    run(mode)
