"""P2: the round-14 before/after check compares the container's entry objects with the unread record, never with the
history the read-back produced.  A read-back that reads a state other than the container (a to_dict that serializes the
pre-spend content while the container keeps the spend, or an in-place rollback and re-apply inside the read-back) clears
the unread record and is accepted: the same authorization is dispatched again."""
from common import *

class SelfFilling:
    def __str__(self):
        c = {"a": 1}
        for k in c:
            c[k + "x"] = 2
        return "unreached"

def run(variant):
    o = ax.owned("battery")
    lid = solver(o)
    calls = []
    def executor(a):
        calls.append(1)
        settle(o.ledgers[lid], f"run.{len(calls)}", SelfFilling())
    reader, authorities, gateway, r = desk(o, lambda: (dict(o.ledgers), dict(o.experiments)), executor)
    live = o.ledgers[lid]
    earlier_charges = live.charges
    earlier_dict = live.to_dict()
    gateway.dispatch(r.admitted)                         # the spend, never read back
    try:
        reader.read(OwnerKind.BUDGET_LEDGER, lid); print("unexpected: served")
    except OwnerUnavailable as e:
        print("not read back:", str(e)[:80])
    print("unread recorded:", lid in [k[1] for k in reader._unread_entries])
    real = type(live).to_dict
    if variant == "lie":
        object.__setattr__(live, "to_dict", lambda: earlier_dict)
    else:                                                # ABA inside the read-back: roll back, serialize, re-apply
        def aba():
            saved = object.__getattribute__(live, "charges")
            object.__setattr__(live, "charges", earlier_charges)
            try:
                return real(live)
            finally:
                object.__setattr__(live, "charges", saved)
        object.__setattr__(live, "to_dict", aba)
    print("container still holds the spend:", len(live.charges), ">", len(earlier_charges))
    re = not refused(gateway, r.admitted)
    print(f"[{variant}] same authorization dispatched again: {re}; executor calls {len(calls)}; unread now "
          f"{[k for k in reader._unread_entries]}; diverged {list(reader._diverged)}")

run("lie")
print()
run("aba")
