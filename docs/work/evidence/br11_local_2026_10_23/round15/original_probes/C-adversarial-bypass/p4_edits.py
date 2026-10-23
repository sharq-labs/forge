"""R15-C probe 4: in-place edits of minted records, suggestions_only, and the port path for the seal race."""
import dataclasses, types, threading
from common import *
from engcore.mind.world.admission import AdmittedAction, DispatchAuthorization, authorize_dispatch, verify_authorization

o = ax.owned("battery")
lid = next(k for k in o.ledgers if k.endswith(".solver"))
seen = []
def executor(a):
    seen.append(a)
reader, authorities, gateway, r = desk(o, lambda: (dict(o.ledgers), dict(o.experiments)), executor)
adm = r.admitted
print("configuration:", adm.configuration)

def attempt(label, fn):
    try:
        fn(); print(label, "-> DISPATCHED", len(seen))
    except Exception as exc:
        print(label, "-> refused:", type(exc).__name__, str(exc)[:110])

# 1. edit configuration in place to another value
name, val = adm.configuration[0]
try:
    newval = val * 2
except Exception:
    newval = val
cfg_edit = dataclasses.replace  # unused
a1 = r.admitted
object.__setattr__(a1, "configuration", ((name, newval),) + tuple(a1.configuration[1:]))
attempt("edited configuration", lambda: gateway.dispatch(a1))
r2 = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
a2 = r2.admitted
object.__setattr__(a2, "synthetic", False)
attempt("edited synthetic flag", lambda: gateway.dispatch(a2))
r3 = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
a3 = r3.admitted
object.__setattr__(a3, "observe", ())
attempt("edited observe", lambda: gateway.dispatch(a3))
# 2. a DispatchAuthorization edited in place and handed to authorize/verify
r4 = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
auth = authorize_dispatch(r4.admitted, authorities, accept_synthetic=True)
object.__setattr__(auth, "settings", types.MappingProxyType({}))
attempt("edited authorization verify()", lambda: verify_authorization(auth, authorities, accept_synthetic=True))
# 3. suggestions_only desk: a plain proposal
gw2 = ExecutionDesk(authorities, executor, accept_synthetic=True, suggestions_only=True).gateway()
attempt("suggestions_only admit plain", lambda: gw2.admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM)))
r5 = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
attempt("suggestions_only dispatch plain admitted", lambda: gw2.dispatch(r5.admitted))
print("executor calls total:", len(seen))
