"""Exact-source reproduction using CPython tracing/profile exception checkpoints.
No monkeypatching: both BudgetReader and native mapping helpers are unmodified.
"""
import json, os, pathlib, subprocess, sys
from engcore.mind.world import BudgetReader
from engcore.mind.world import owners as ow
from engcore.sria.campaign.budget import BudgetLedger
from tests.mind.test_authority_review_r14 import _desk, _solver, _settle, _refused, ax
root = pathlib.Path("/home/dev_kaeem/forge-r16-review")
sha = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
assert sha == "b8a65bb9d02b5a18e0a8b26779773c1552204dc1"
assert ow.__file__ == str(root / "src/engcore/mind/world/owners.py")
print("identity", sha, ow.__file__, sys.executable)
o = ax.owned("battery")
lid = _solver(o)
calls = []
def executor(authorization):
    calls.append(1)
    _settle(o.ledgers[lid], f"run.{len(calls)}")
reader, authorities, gateway, result = _desk(o, lambda: (o.ledgers, o.experiments), executor)
checkpoint = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
gateway.dispatch(result.admitted)
items_code = ow._items.__code__
recover_code = BudgetReader._recover_handing.__code__
injections = []
def is_recovery(frame):
    frame = frame.f_back
    while frame:
        if frame.f_code is recover_code:
            return True
        frame = frame.f_back
    return False
def trace(frame, event, arg):
    if event == "call" and frame.f_code is items_code and frame.f_locals["mapping"] is o.experiments and not injections:
        injections.append("native capture via sys.settrace")
        raise KeyboardInterrupt("initial native capture")
    return trace
def profile(frame, event, arg):
    if event == "call" and frame.f_code is items_code and frame.f_locals["mapping"] is o.experiments and len(injections) == 1 and is_recovery(frame):
        injections.append("immediate recovery via sys.setprofile")
        raise KeyboardInterrupt("immediate native recovery")
sys.setprofile(profile)
sys.settrace(trace)
try:
    reader.pinned()
except KeyboardInterrupt:
    print("pin raised KeyboardInterrupt")
finally:
    sys.settrace(None)
    sys.setprofile(None)
print("injections", injections)
print("pending", [type(x).__name__ for x in reader._uncompared.values()])
assert len(injections) == 2
assert reader._uncompared
assert reader._sealed is None
o.ledgers[lid] = checkpoint
refused = _refused(gateway, result.admitted)
print("dispatch_refused", refused, "executor_calls", len(calls))
assert refused and len(calls) == 1, "handed spend lost after interrupted retention and restore"
