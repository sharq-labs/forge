"""P2b: the entries listed just before a read-back ('before') are compared with nothing but an unread record.  A
readable spend that is rolled back in place inside the verification's own read-back (listed in 'before', absent from
the history read back and from 'after') is accepted when no unread record exists, and the same authorization is
dispatched again.  Variant 'fail_then_rollback': the rollback happens in a failing attempt; the state is recorded from
the listing taken after the failure, so the spend listed in 'before' is never recorded either."""
from common import *

def run(variant):
    o = ax.owned("battery")
    lid = solver(o)
    calls = []
    def executor(a):
        calls.append(1)
        settle(o.ledgers[lid], f"run.{len(calls)}")
    reader, authorities, gateway, r = desk(o, lambda: (dict(o.ledgers), dict(o.experiments)), executor)
    live = o.ledgers[lid]
    earlier = live.charges
    gateway.dispatch(r.admitted)                          # the spend (readable), not yet observed
    real = type(live).to_dict
    state = {"n": 0}
    def rollback():
        state["n"] += 1
        object.__setattr__(live, "charges", earlier)      # in place, inside the read-back
        if variant == "fail_then_rollback" and state["n"] <= 3:
            raise RuntimeError("dictionary changed size during iteration")
        return real(live)
    object.__setattr__(live, "to_dict", rollback)
    again = not refused(gateway, r.admitted)
    print(f"[{variant}] same authorization dispatched again: {again}; executor calls {len(calls)}; "
          f"unread {list(reader._unread_entries)}; diverged {list(reader._diverged)}")

run("rollback_in_readback")
run("fail_then_rollback")
