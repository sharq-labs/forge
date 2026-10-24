"""R12-B b1201: _read_once's classifying handler formats the caught exception (f"{type(exc).__name__}: {exc}" and,
for an exact RuntimeError, _moving's str(exc)).  An exception raised inside the owner's serialization whose own
__str__ raises makes the HANDLER raise: the new exception is not _Failed, so it leaves _account, _read_back
(catches only _Unreadable / OwnerUnavailable), _observe_all and pinned().  Round 11's fix asked (R11-C-F1) that
any Exception from an account's read-back become a classified refusal.  Checked: the escape, its effect on every
admission, and the re-dispatch after a restore (the R11-C-F1 consequence), with controls."""
import copy
import sys

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.mind.world.authority import OwnerUnavailable
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]


class Unprintable(Exception):
    def __str__(self):                    # an exception whose message cannot be rendered
        raise ValueError("message not available")


class DetailA:                            # stringifying it raises an exception whose message cannot be rendered
    def __str__(self):
        raise Unprintable()


class Arg:
    def __str__(self):
        raise ValueError("arg not printable")


class DetailB:                            # an exact RuntimeError whose argument cannot be rendered (_moving's str)
    def __str__(self):
        raise RuntimeError(Arg())


class DetailC:                            # control: an ordinary failure (TypeError with a message)
    def __str__(self):
        raise TypeError("plain failure")


def run(detail_cls, label):
    o = ax.owned("battery")
    lid = next(k for k in o.ledgers if k.endswith(".solver"))
    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    auth = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    space = FeasibleActionSpace.build(o.world)
    r = admit(space, o.propose("simulate_pulse", *SIM), auth)
    assert r.admitted is not None, r.status
    calls = []
    before = BudgetLedger.from_dict(copy.deepcopy(o.ledgers[lid].to_dict()))

    def executor(a):
        calls.append(1)
        o.ledgers[lid].settle(charge_id=f"run.{len(calls)}", action_id="simulate_pulse", iteration=1,
                              family=ActionFamily.EXPLORE, realized=1.0, detail=detail_cls())

    gw = ExecutionDesk(auth, executor, accept_synthetic=True).gateway()
    gw.dispatch(r.admitted)
    seen = []
    for _ in range(2):
        try:
            reader.pinned()
            seen.append("pinned ok")
        except OwnerUnavailable as e:
            seen.append("OwnerUnavailable" + (" FOR GOOD" if "from then on" in str(e) else ""))
        except Exception as e:  # noqa: BLE001
            seen.append(f"RAISED {type(e).__name__}")
    adm = []
    for _ in range(2):
        try:
            a = gw.admit(space, o.propose("simulate_pulse", *SIM))
            adm.append(f"{a.status.value} {a.codes()}")
        except Exception as e:  # noqa: BLE001
            adm.append(f"RAISED {type(e).__name__}: {e!r}"[:80])
    hist = reader._seen.get(("ledger", lid))
    o.ledgers[lid] = before                       # the execution side restores the pre-run ledger (object replaced)
    try:
        gw.dispatch(r.admitted)
        again = "DISPATCHED AGAIN"
    except DispatchRefused as e:
        again = "refused: " + str(e)[:70]
    except Exception as e:  # noqa: BLE001
        again = f"RAISED {type(e).__name__}"
    print(f"[{label}] pins on the spent state: {seen}\n   admissions on the spent state: {adm}\n   history recorded "
          f"for the ledger: {len(hist) if hist else hist} charges; diverged: {('ledger', lid) in reader._diverged}\n"
          f"   re-dispatch after the restore: {again}; executor ran {len(calls)}")


print(sys.version.split()[0])
run(DetailA, "A: str(detail) raises an exception whose __str__ raises")
run(DetailB, "B: str(detail) raises RuntimeError(arg) whose arg's __str__ raises")
run(DetailC, "C control: str(detail) raises TypeError('plain failure')")
