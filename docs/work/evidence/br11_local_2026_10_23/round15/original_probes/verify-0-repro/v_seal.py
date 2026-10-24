"""Independent skeptic probe for R15-A-F1: a verification in flight across the seal."""
import threading, types, sys
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.mind.world.authority import OwnerUnavailable
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily
import engcore.mind.world.owners as om
print("owners from:", om.__file__)
SIM = ax.base("battery")["simulate_pulse"]

def scenario(mode, restore):
    o = ax.owned("battery")
    lid = next(k for k in o.ledgers if k.endswith(".solver"))
    st = {"nondict": False, "hold_next": False}
    held, release = threading.Event(), threading.Event()
    def accounts():
        if st["hold_next"]:
            st["hold_next"] = False          # hold exactly one call (VA's), no thread-name gating
            held.set(); release.wait(10)
        led = dict(o.ledgers)
        if st["nondict"]:
            led = types.MappingProxyType(led) if mode == "proxy" else led
        return led, dict(o.experiments)
    calls = []
    def executor(auth):
        calls.append(1)
        o.ledgers[lid].settle(charge_id=f"run.{len(calls)}", action_id="simulate_pulse", iteration=1,
                              family=ActionFamily.EXPLORE, realized=0.5, detail="spent")
    reader = BudgetReader.following(accounts)
    auths = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), auths)
    assert r.admitted is not None
    gw = ExecutionDesk(auths, executor, accept_synthetic=True).gateway()
    F = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gw.dispatch(r.admitted)
    out = []
    st["hold_next"] = True
    def va():
        try:
            gw.dispatch(r.admitted); out.append("DISPATCHED AGAIN")
        except DispatchRefused as e:
            out.append("REFUSED " + str(e)[:110])
    t = threading.Thread(target=va, daemon=True); t.start()
    assert held.wait(10)
    st["nondict"] = True
    try:
        reader.read(OwnerKind.BUDGET_LEDGER, lid); vb = "served"
    except OwnerUnavailable as e:
        vb = "refused: " + str(e)[:70]
    st["nondict"] = False
    sealed = reader._sealed is not None
    if restore:
        o.ledgers[lid] = F
    release.set(); t.join(15)
    # a verification that STARTS after the seal
    try:
        gw.dispatch(r.admitted); later = "DISPATCHED"
    except DispatchRefused as e:
        later = "REFUSED"
    print(f"mode={mode:5} restore={restore!s:5} VB={vb!r} sealed={sealed} VA={out} later={later} executor_calls={len(calls)}")

for mode in ("proxy", "dict"):
    for restore in (True, False):
        scenario(mode, restore)
