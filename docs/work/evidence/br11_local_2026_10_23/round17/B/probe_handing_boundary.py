import json, sys, traceback
from pathlib import Path
from engcore.mind.world import BudgetReader
from engcore.mind.world import owners as ow
from engcore.sria.campaign.budget import BudgetLedger
from tests.mind.test_authority_review_r14 import _desk, _solver, _settle, _refused, ax

print("IDENTITY", sys.version, ow.__file__, flush=True)

def run(label, line=None, retention_interrupts=0):
    o = ax.owned("battery")
    lid = _solver(o)
    calls = []
    def accounts():
        return o.ledgers, o.experiments
    def executor(authorization):
        calls.append(authorization.action_id if hasattr(authorization, "action_id") else "executed")
        _settle(o.ledgers[lid], f"run.{len(calls)}")
    reader, authorities, gateway, result = _desk(o, accounts, executor)
    checkpoint = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(result.admitted)
    spent = o.ledgers[lid]
    events = []
    real_retain = BudgetReader._retain_handing
    if retention_interrupts:
        remaining = [retention_interrupts]
        def retain(handed):
            if remaining[0]:
                remaining[0] -= 1
                events.append("interrupt at native retention entry")
                raise KeyboardInterrupt("deterministic interruption checkpoint")
            return real_retain(handed)
        BudgetReader._retain_handing = staticmethod(retain)
    if line:
        def trace(frame, event, arg):
            if event == "line" and frame.f_code is BudgetReader.pinned.__code__ and frame.f_lineno == line:
                events.append(f"interrupt at pinned:{line}; mapping already handed={frame.f_locals.get('mapping') is not None}")
                sys.settrace(None)
                raise KeyboardInterrupt("deterministic interruption checkpoint")
            return trace
        sys.settrace(trace)
    try:
        reader.pinned()
        events.append("pin returned")
    except BaseException as exc:
        events.append(type(exc).__name__)
    finally:
        sys.settrace(None)
        BudgetReader._retain_handing = staticmethod(real_retain)
    pending = {str(k):type(v).__name__ for k,v in reader._uncompared.items()}
    unread_before_restore = {str(k):len(v) for k,v in reader._unread_entries.items()}
    o.ledgers[lid] = checkpoint
    refused = _refused(gateway, result.admitted)
    out = dict(label=label, events=events, calls=len(calls), refused=refused,
               spent_revision=spent.revision, restored_revision=checkpoint.revision,
               pending_before_restore=pending, unread_before_restore=unread_before_restore,
               sealed=reader._sealed, diverged=list(reader._diverged),
               pending_after_dispatch={str(k):type(v).__name__ for k,v in reader._uncompared.items()})
    print(json.dumps(out), flush=True)

for label, line, count in [
    ("positive_control_handing_seen", None, 1),
    ("interrupt_after_accounts_return", 996, 0),
    ("interrupt_after_handed_flag", 998, 0),
    ("interrupt_before_registry_store", 999, 0),
    ("retention_and_cleanup_interrupted", None, 2),
]:
    run(label, line, count)
