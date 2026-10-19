"""Observe approved negative-control line reachability; no runtime changes."""
import hashlib,json,sys
from pathlib import Path
import pytest
ROOT=Path('D:/forge-main-337519d1')
TASK=ROOT/'.pytest-review-temp/final-integration-approved-2026-10-18'
FILES={str((ROOT/p).resolve()).lower():p for p in ('tests/test_capability_completion.py','tests/test_m1a_mesh_lineage.py','tools/capability_maturity.py','src/engcore/numerical/mesh_adaptation.py','src/engcore/numerical/interval_transfer.py')}
RECORDS={}
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    selected=any(s in item.nodeid for s in ('test_a_gate_cannot_be_decided_before_its_required_gate_is_ready','test_every_decided_gate_needs_evidence_and_blocked_follows_a_failed_requirement','test_nested_record_tampering_poisoned_lineage_is_fail_closed'))
    if not selected:
        yield
        return
    lines={}
    def trace(frame,event,arg):
        path=FILES.get(str(Path(frame.f_code.co_filename).resolve()).lower())
        if path and event=='line':
            counts=lines.setdefault(path,{})
            counts[str(frame.f_lineno)]=counts.get(str(frame.f_lineno),0)+1
        return trace
    previous=sys.gettrace()
    sys.settrace(trace)
    try:
        yield
    finally:
        sys.settrace(previous)
        RECORDS[item.nodeid]=lines
def pytest_sessionfinish(session,exitstatus):
    (TASK/'negative-control-paths.json').write_text(json.dumps({'exit_status':exitstatus,'records':RECORDS,'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES.values()}},indent=2)+'\n',encoding='utf-8')
