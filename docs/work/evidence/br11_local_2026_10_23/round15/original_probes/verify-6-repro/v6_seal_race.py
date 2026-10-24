"""Skeptic re-run of B15-F1, written independently. Schedules:
  seq_proxy   : spend, V2 hands proxy (seal), restore, then V3 starts  -> expect refused
  race_proxy  : spend, V3 starts and blocks in accounts(), V2 hands proxy (seal), restore, V3 released
  race_dict   : same as race_proxy but V2 hands plain dicts (read back) -> expect V3 refused (behind)
  race_none   : same race, no V2 at all (spend and restore both unobserved; the accepted residual)
"""
import sys, threading, types
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.mind.world.authority import OwnerUnavailable
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]

def run(variant):
    o = ax.owned("battery")
    lid = next(k for k in o.ledgers if k.endswith(".solver"))
    mode = {"proxy": False}
    in3, go3 = threading.Event(), threading.Event()
    def accounts():
        if threading.current_thread().name == "V3" and not in3.is_set():
            in3.set(); go3.wait(10)
        led = dict(o.ledgers)
        return (types.MappingProxyType(led) if mode["proxy"] else led), dict(o.experiments)
    calls = []
    def executor(auth):
        calls.append(threading.current_thread().name)
        o.ledgers[lid].settle(charge_id=f"run.{len(calls)}", action_id="simulate_pulse", iteration=1,
                              family=ActionFamily.EXPLORE, realized=0.5, detail="observed")
    reader = BudgetReader.following(accounts)
    A = o.authorities()
    authorities = type(A).of(*(reader if type(r) is BudgetReader else r for r in A.readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    assert r.admitted is not None
    gw = ExecutionDesk(authorities, executor, accept_synthetic=True).gateway()
    pre = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gw.dispatch(r.admitted)
    assert len(o.ledgers[lid].charges) == len(pre.charges) + 1
    res = {}
    def v3():
        try:
            gw.dispatch(r.admitted); res["v3"] = "DISPATCHED"
        except DispatchRefused as e:
            res["v3"] = "refused: " + str(e)[:140]
    t = None
    if variant.startswith("race"):
        t = threading.Thread(target=v3, name="V3", daemon=True); t.start()
        assert in3.wait(10)
    v2 = "skipped"
    if variant != "race_none":
        mode["proxy"] = variant.endswith("proxy")
        try:
            reader.read(OwnerKind.BUDGET_LEDGER, lid); v2 = "read ok"
        except OwnerUnavailable as e:
            v2 = "refused: " + str(e)[:90]
        mode["proxy"] = False
    sealed = reader._sealed is not None
    o.ledgers[lid] = BudgetLedger.from_dict(pre.to_dict())      # checkpoint restore of the pre-spend ledger
    if t is not None:
        go3.set(); t.join(15)
    else:
        v3()
    print(f"[{variant}] V2: {v2} | sealed={sealed} | V3: {res.get('v3')} | executor calls={calls}")

for rep in range(3):
    for v in ("seq_proxy", "race_proxy", "race_dict", "race_none"):
        run(v)
    print()
