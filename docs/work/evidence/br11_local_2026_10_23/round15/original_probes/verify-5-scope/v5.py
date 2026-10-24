"""Skeptic re-run of F15-F1 with controls. Modes:
 seal_race      : BAD hands a MappingProxyType (seals) while GOOD is in accounts(); restore S0 by replacement; GOOD re-dispatches
 seal_race_norestore : same, but no restore (GOOD handed S1 as dict) -> expected refused (spend observed)
 raise_race     : BAD's accounts() raises (accepted residual: nothing handed) -> compare outcome
 seq_seal       : BAD seals first, GOOD starts afterwards (round-14 control) -> expected refused
"""
import threading, types
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, admit
from engcore.mind.world.authority import OwnerUnavailable
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]

def run(mode):
    o = ax.owned("battery")
    lid = next(k for k in o.ledgers if k.endswith(".solver"))
    good_inside, good_go = threading.Event(), threading.Event()
    def accounts():
        name = threading.current_thread().name
        if name == "GOOD" and mode != "seq_seal":
            good_inside.set(); good_go.wait(10)
        ledgers = dict(o.ledgers)
        if name == "BAD":
            if mode == "raise_race":
                raise RuntimeError("cannot state")
            return types.MappingProxyType(ledgers), dict(o.experiments)
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
    s0 = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(r.admitted)
    assert len(calls) == 1
    out = {}
    def good():
        try:
            gateway.dispatch(r.admitted); out["good"] = "DISPATCHED AGAIN"
        except Exception as exc:
            out["good"] = f"refused: {type(exc).__name__}: {str(exc)[:140]}"
    def bad():
        try:
            reader.pinned(); out["bad"] = "pinned"
        except OwnerUnavailable as exc:
            out["bad"] = "refused: " + str(exc)[:90]
    tg = threading.Thread(target=good, name="GOOD", daemon=True)
    tb = threading.Thread(target=bad, name="BAD")
    if mode == "seq_seal":
        tb.start(); tb.join(10)
        o.ledgers[lid] = s0
        tg.start(); tg.join(10)
    else:
        tg.start(); assert good_inside.wait(10)
        tb.start(); tb.join(10)
        if mode != "seal_race_norestore":
            o.ledgers[lid] = s0
        good_go.set(); tg.join(10)
    print(f"[{mode}] BAD: {out.get('bad')} | sealed={reader._sealed is not None}")
    print(f"[{mode}] GOOD: {out.get('good')}")
    print(f"[{mode}] executor calls = {len(calls)}")

for m in ("seal_race", "seal_race_norestore", "raise_race", "seq_seal"):
    run(m)
# repeat the race 20 times for determinism
n = 0
import io, contextlib
for i in range(20):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        run("seal_race")
    n += "executor calls = 2" in buf.getvalue()
print("seal_race redispatch in", n, "of 20")
