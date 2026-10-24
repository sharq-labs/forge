import json,sys,subprocess
from engcore.mind.world import owners as ow
from engcore.sria.campaign.budget import BudgetLedger
from tests.mind.test_authority_review_r14 import _desk,_solver,_settle,_refused,ax
print(json.dumps({"sha":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),"owners":ow.__file__,"python":sys.executable}))
assert ow.__file__ == "/home/dev_kaeem/forge-r16-review/src/engcore/mind/world/owners.py"
assert subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip() == "b8a65bb9d02b5a18e0a8b26779773c1552204dc1"
for line in (974,977,978,979):
    o=ax.owned("battery")
    lid=_solver(o)
    calls=[]
    def execute(authorization):
        calls.append(1)
        _settle(o.ledgers[lid],f"run.{len(calls)}")
    reader,authorities,gateway,admitted=_desk(o,lambda:(o.ledgers,o.experiments),execute)
    saved=BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(admitted.admitted)
    hits=[]
    def trace(frame,event,arg):
        if event=="line" and frame.f_code.co_filename==ow.__file__ and frame.f_lineno==line:
            hits.append(line)
            raise KeyboardInterrupt("one asynchronous checkpoint")
        return trace
    sys.settrace(trace)
    try:reader.pinned()
    except KeyboardInterrupt:pass
    finally:sys.settrace(None)
    assert hits==[line]
    pending=len(reader._uncompared)
    unread={str(k):len(v) for k,v in reader._unread_entries.items()}
    o.ledgers[lid]=saved
    refused=_refused(gateway,admitted.admitted)
    print(json.dumps({"line":line,"pending":pending,"unread":unread,"refused":refused,"executions":len(calls)}))
