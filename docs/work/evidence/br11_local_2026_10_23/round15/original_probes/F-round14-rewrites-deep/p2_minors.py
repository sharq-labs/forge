"""R15-F probe 2: MINOR candidates in the round-14 rewrites.
 (a) the known-content shortcut (_seen_entries) is dropped whenever a read straddles an honest in-place settle
     (len(before) != len(after)); a later transient failure with NO new entry then records the entries, and an honest
     unchanged checkpoint restore retires the account for good (README section 4 says it does not).
 (b) the same after an unread object-replacing restore: read, restore (unchanged, not yet read), transient failure,
     restore again -> refused for good.
 (c) the before/after listing does not bind what the read-back read: a rollback undone before the after-listing clears
     the unread spend and the executed action is dispatched again (execution-side instance patch: MINOR class).
 (d) an asynchronous KeyboardInterrupt that lands while a well-formed pair of dicts is walked seals the reader for good
     with the text: handed over what is not a pair of account dicts."""
import sys, types
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.mind.world.authority import OwnerUnavailable
from engcore.mind.world import owners as OW
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]


def solver(o):
    return next(k for k in o.ledgers if k.endswith(".solver"))


def settle(L, cid, detail="observed"):
    L.settle(charge_id=cid, action_id="other", iteration=1, family=ActionFamily.EXPLORE, realized=0.25, detail=detail)


def read(reader, lid):
    try:
        reader.read(OwnerKind.BUDGET_LEDGER, lid)
        return "read back"
    except OwnerUnavailable as exc:
        return "REFUSED: " + str(exc)[:150]


def transient_once(L):
    real = type(L).to_dict
    state = {"n": 0}

    def moving(self):
        state["n"] += 1
        if state["n"] <= 3:          # the three attempts of ONE verification: the interpreter's mutation error
            raise RuntimeError("dictionary changed size during iteration")
        return real(self)
    object.__setattr__(L, "to_dict", types.MethodType(moving, L))


def unpatch(L):
    L.__dict__.pop("to_dict", None)


def case_a(straddle):
    o = ax.owned("battery")
    lid = solver(o)
    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    settle(o.ledgers[lid], "other.0")
    if straddle:                     # an honest settle lands during this verification's read-back
        orig = BudgetReader._account
        done = []

        def wrapped(self, key, _o=orig):
            if key == ("ledger", lid) and not done:
                done.append(1)
                settle(o.ledgers[lid], "other.1")    # stands in for another execution-side thread settling now
            return _o(self, key)
        BudgetReader._account = wrapped
        try:
            r1 = read(reader, lid)
        finally:
            BudgetReader._account = orig
    else:
        settle(o.ledgers[lid], "other.1")
        r1 = read(reader, lid)
    print(f"(a straddle={straddle}) read of the moving account: {r1}; known-content shortcut set: "
          f"{('ledger', lid) in reader._seen_entries}")
    r2 = read(reader, lid)           # the same content again
    print(f"   read again (no move): {r2}; shortcut set now: {('ledger', lid) in reader._seen_entries}")
    transient_once(o.ledgers[lid])
    r3 = read(reader, lid)           # transient failure, NO new entry
    unpatch(o.ledgers[lid])
    print(f"   transient failure (no new entry): {r3[:60]}; recorded: {('ledger', lid) in reader._unread_entries}")
    o.ledgers[lid] = BudgetLedger.from_dict(o.ledgers[lid].to_dict())      # honest unchanged checkpoint resume
    print(f"   after an unchanged checkpoint resume: {read(reader, lid)}")
    print(f"   refused for good: {('ledger', lid) in reader._diverged}")


def case_a2():
    """As (a), but the transient failure comes right after the straddling read (no quiet read in between)."""
    o = ax.owned("battery")
    lid = solver(o)
    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    settle(o.ledgers[lid], "other.0")
    orig = BudgetReader._account
    done = []

    def wrapped(self, key, _o=orig):
        if key == ("ledger", lid) and not done:
            done.append(1)
            settle(o.ledgers[lid], "other.1")
        return _o(self, key)
    BudgetReader._account = wrapped
    try:
        r1 = read(reader, lid)
    finally:
        BudgetReader._account = orig
    transient_once(o.ledgers[lid])
    r3 = read(reader, lid)
    unpatch(o.ledgers[lid])
    print(f"(a2) straddling read: {r1}; transient failure (no new entry since that read): {r3[:50]}; recorded: "
          f"{('ledger', lid) in reader._unread_entries}")
    o.ledgers[lid] = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    print(f"   after an unchanged checkpoint resume: {read(reader, lid)}")
    print(f"   refused for good: {('ledger', lid) in reader._diverged}")


def case_b():
    o = ax.owned("battery")
    lid = solver(o)
    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    settle(o.ledgers[lid], "other.0")
    print(f"(b) read: {read(reader, lid)}")
    o.ledgers[lid] = BudgetLedger.from_dict(o.ledgers[lid].to_dict())      # resume 1 (unchanged), not read yet
    transient_once(o.ledgers[lid])
    print(f"   transient failure on the resumed object (no new entry): {read(reader, lid)[:60]}; recorded: "
          f"{('ledger', lid) in reader._unread_entries}")
    unpatch(o.ledgers[lid])
    o.ledgers[lid] = BudgetLedger.from_dict(o.ledgers[lid].to_dict())      # resume 2 (unchanged)
    print(f"   after a second unchanged checkpoint resume: {read(reader, lid)}")
    print(f"   refused for good: {('ledger', lid) in reader._diverged}")


class _SelfFillingNote:
    def __str__(self):
        cache = {"a": 1}
        for k in cache:
            cache[k + "x"] = 2
        return "unreached"


def case_c(undo):
    o = ax.owned("battery")
    lid = solver(o)
    calls = []

    def executor(a):
        calls.append(1)
        o.ledgers[lid].settle(charge_id=f"run.{len(calls)}", action_id="simulate_pulse", iteration=1,
                              family=ActionFamily.EXPLORE, realized=0.5, detail=_SelfFillingNote())
    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    gateway = ExecutionDesk(authorities, executor, accept_synthetic=True).gateway()
    live = o.ledgers[lid]
    earlier = live.charges
    gateway.dispatch(r.admitted)
    full = live.charges
    print(f"(c undo={undo}) spend not read back: {read(reader, lid)[:70]}; unread recorded: "
          f"{('ledger', lid) in reader._unread_entries}")
    real = type(live).to_dict

    def rolled(self):
        object.__setattr__(self, "charges", earlier)        # rolled back in place during its own read-back ...
        d = real(self)
        if undo:
            object.__setattr__(self, "charges", full)       # ... and forward again before the after-listing
        return d
    object.__setattr__(live, "to_dict", types.MethodType(rolled, live))
    try:
        gateway.dispatch(r.admitted)
        out = "DISPATCHED AGAIN"
    except DispatchRefused as exc:
        out = "refused: " + str(exc)[:100]
    print(f"   re-dispatch of the executed authorization: {out}; executor calls = {len(calls)}; unread record "
          f"cleared: {('ledger', lid) not in reader._unread_entries}")


def case_d():
    o = ax.owned("battery")
    lid = solver(o)
    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))

    def tracer(frame, event, arg):
        if event == "call" and frame.f_code is OW._items.__code__:
            sys.settrace(None)
            raise KeyboardInterrupt      # stands in for a ctrl-C landing at this bytecode
        return tracer
    sys.settrace(tracer)
    try:
        reader.pinned()
        out = "pinned"
    except KeyboardInterrupt:
        out = "KeyboardInterrupt re-raised"
    finally:
        sys.settrace(None)
    print(f"(d) a ctrl-C while a well-formed pair of dicts is walked: {out}; sealed: {reader._sealed}")
    print(f"   next verification (nothing wrong handed): {read(reader, lid)[:90]}")


case_a(False)
case_a(True)
case_a2()
case_b()
case_c(False)
case_c(True)
case_d()
