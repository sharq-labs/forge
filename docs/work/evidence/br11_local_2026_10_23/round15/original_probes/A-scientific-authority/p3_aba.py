"""R14-C-F2's control rolls back in place during the read-back and leaves it rolled back.  Variant: roll back during
the read-back and roll FORWARD again before it ends (before == after, history = the rolled-back state)."""
from common import *
print("owners:", owners_mod.__file__)

def run(aba):
    o = ax.owned("battery")
    lid = solver(o)
    calls = []
    def executor(authorization):
        calls.append(1)
        settle(o.ledgers[lid], f"run.{len(calls)}", SelfFillingNote())
    reader, authorities, gateway, r = desk(o, lambda: (dict(o.ledgers), dict(o.experiments)), executor)
    live = o.ledgers[lid]
    earlier = live.charges
    gateway.dispatch(r.admitted)
    try:
        reader.read(OwnerKind.BUDGET_LEDGER, lid)
    except OwnerUnavailable as exc:
        print("spend not read back:", str(exc)[:60])
    print("unread recorded:", {k: len(v) for k, v in reader._unread_entries.items()})
    real = type(live).to_dict
    def rolled(self):
        held = self.charges
        object.__setattr__(self, "charges", earlier)
        try:
            return real(self)
        finally:
            if aba:
                object.__setattr__(self, "charges", held)
    object.__setattr__(live, "to_dict", __import__("types").MethodType(rolled, live))
    print("aba" if aba else "rollback (R14 control)", "->", refused(gateway, r.admitted) or "DISPATCHED AGAIN",
          "calls", len(calls), "| container holds run.1:", any(c.charge_id == "run.1" for c in live.charges))

run(False)
run(True)
