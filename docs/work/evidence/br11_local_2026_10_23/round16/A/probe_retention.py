import json, sys, subprocess
from unittest.mock import patch
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world import owners as ow
from engcore.sria.campaign.budget import BudgetLedger
from tests.mind.test_authority_review_r14 import _desk, _solver, _settle, _refused, ax
SHA = "b8a65bb9d02b5a18e0a8b26779773c1552204dc1"
assert subprocess.check_output(["git", "-C", "/home/dev_kaeem/forge-r16-review", "rev-parse", "HEAD"], text=True).strip() == SHA
assert ow.__file__ == "/home/dev_kaeem/forge-r16-review/src/engcore/mind/world/owners.py"
print(json.dumps({"sha": SHA, "owners": ow.__file__, "python": sys.version, "executable":sys.executable}))

def scenario(failures, failure_type=KeyboardInterrupt):
    o = ax.owned("battery")
    lid = _solver(o)
    calls = []
    def executor(authorization):
        calls.append(1)
        _settle(o.ledgers[lid], f"run.{len(calls)}")
    reader, authorities, gateway, result = _desk(o, lambda: (o.ledgers, o.experiments), executor)
    checkpoint = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(result.admitted)
    actual = BudgetReader._retain_handing
    armed = list(range(failures))
    def interrupted(handed):
        if armed:
            armed.pop()
            raise failure_type("deterministic interruption before native retention")
        return actual(handed)
    first = None
    with patch.object(BudgetReader, "_retain_handing", staticmethod(interrupted)):
        try: reader.pinned()
        except BaseException as exc: first = type(exc).__name__
    pending = [(k, type(v).__name__) for k, v in reader._uncompared.items()]
    seen = {str(k): len(v) for k,v in reader._seen.items()}
    unread = {str(k):len(v) for k,v in reader._unread_entries.items()}
    o.ledgers[lid] = checkpoint
    refused = _refused(gateway, result.admitted)
    got = {"failures":failures, "failure_type": failure_type.__name__, "first":first,"pending_before_restore":pending,"seen_before_restore":seen,"unread_before_restore":unread,"redispatch_refused":refused,"calls":len(calls),"sealed":reader._sealed}
    print(json.dumps(got))
    return got

out = [scenario(n) for n in (0,1,2)]
out += [scenario(2,t) for t in (MemoryError,RecursionError)]
assert out[0]["calls"] == out[1]["calls"] == 1
assert all(x["calls"] == 2 for x in out[2:]), "hypothesis did not reproduce"
