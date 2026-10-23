"""Fixed five paired runs, alternating order. Synthetic affected paths only."""
from pathlib import Path
import json, os, statistics, subprocess, sys, time, threading, types, hashlib

ROOT = Path("/home/dev_kaeem/forge-gen2-authority-v1")
EV = ROOT/"docs/work/evidence/br11_local_2026_10_23/round15"
if len(sys.argv) == 1:
    rows=[]
    for repetition in range(5):
        for label in (("pre","post") if repetition%2==0 else ("post","pre")):
            tree=Path("/home/dev_kaeem/forge-r15-review") if label=="pre" else ROOT
            env=dict(os.environ,PYTHONPATH=f"{tree}/src:{tree}",PYTHONDONTWRITEBYTECODE="1")
            command=[str(ROOT/".venv/bin/python"),str(Path(__file__).resolve()),"child"]
            r=subprocess.run(command,cwd=tree,env=env,text=True,capture_output=True,check=True)
            row=dict(label=label,repetition=repetition,tree=str(tree),command=command,**json.loads(r.stdout))
            rows.append(row)
            print(label,repetition,row["medians_us"],row["contention"],flush=True)
    summary={}
    for metric in rows[0]["medians_us"]:
        values={label:[r["medians_us"][metric] for r in rows if r["label"]==label] for label in ("pre","post")}
        overlap=max(min(values["pre"]),min(values["post"])) <= min(max(values["pre"]),max(values["post"]))
        summary[metric]={"pre_range_us":[min(values["pre"]),max(values["pre"])],
                         "post_range_us":[min(values["post"]),max(values["post"])],
                         "verdict":"NO SPEED DIFFERENCE ESTABLISHED" if overlap else "NONOVERLAPPING RANGES IN THIS BOUNDED MEASUREMENT"}
    (EV/"performance.json").write_text(json.dumps(dict(fixed_repetitions=5,rows=rows,summary=summary),indent=2)+"\n")
    print(json.dumps(summary,indent=2))
    raise SystemExit()
from engcore.mind.world import BudgetReader,OwnerKind,FeasibleActionSpace,admit
from engcore.mind.world.admission import authorize_dispatch
from engcore.mind.world.authority import OwnerUnavailable
from engcore.mind.world import owners as ow
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
K=OwnerKind.BUDGET_LEDGER
ledger=BudgetLedger(total_budget=100.)
for i in range(5):
    ledger.settle(charge_id=str(i),action_id="synthetic",iteration=i,family=ActionFamily.EXPLORE,realized=.1)
reader=BudgetReader.following(lambda:({"a":ledger},{}))
def measured(fn,n):
    samples=[]
    for _ in range(n):
        start=time.perf_counter_ns();fn();samples.append((time.perf_counter_ns()-start)/1000)
    return statistics.median(samples)
times={}
times["verification_pin"]=measured(reader.pinned,100)
snapshot=reader.pinned()
read=snapshot._read_back()
snapshot._read_back=lambda:read
def comparison():
    ticket=reader._ticket()
    try:reader._observe_all(snapshot,ticket)
    finally:reader._leave(ticket,False)
times["comparison_pre_read_snapshot"]=measured(comparison,100)
seals=[]
for _ in range(30):
    state={"bad":False}
    r=BudgetReader.following(lambda:((types.MappingProxyType({"a":ledger}) if state["bad"] else {"a":ledger}),{}))
    state["bad"]=True
    start=time.perf_counter_ns()
    try:r.pinned()
    except OwnerUnavailable:pass
    else:raise AssertionError("seal accepted")
    seals.append((time.perf_counter_ns()-start)/1000)
times["seal"]=statistics.median(seals)
o=ax.owned("battery")
budget=BudgetReader.following(lambda:(dict(o.ledgers),dict(o.experiments)))
authorities=type(o.authorities()).of(*(budget if type(r) is BudgetReader else r for r in o.authorities().readers))
sim=ax.base("battery")["simulate_pulse"]
admitted=admit(FeasibleActionSpace.build(o.world),o.propose("simulate_pulse",*sim),authorities).admitted
assert admitted is not None
times["dispatch_authorization"]=measured(lambda:authorize_dispatch(admitted,authorities,accept_synthetic=True),20)
waits=[]
for _ in range(5):
    ready,release=threading.Event(),threading.Event()
    def accounts():
        if threading.current_thread().name=="blocked":
            ready.set()
            assert release.wait(10)
        return {"a":ledger},{}
    r=BudgetReader.following(accounts);r.WAIT_S=.002
    thread=threading.Thread(target=r.pinned,name="blocked")
    thread.start();assert ready.wait(10)
    start=time.perf_counter_ns()
    try:r.read(K,"a")
    except OwnerUnavailable:pass
    else:raise AssertionError("in-flight comparison accepted")
    waits.append((time.perf_counter_ns()-start)/1000)
    release.set();thread.join(10);assert not thread.is_alive()
times["wait_2ms_bound"]=statistics.median(waits)
barrier=threading.Barrier(4); counts=[]; latencies=[]
def contend():
    served=refused=0
    for _ in range(8):
        barrier.wait(timeout=10)
        start=time.perf_counter_ns()
        try:reader.read(K,"a");served+=1
        except OwnerUnavailable:refused+=1
        latencies.append((time.perf_counter_ns()-start)/1000)
    counts.append((served,refused))
threads=[threading.Thread(target=contend) for _ in range(4)]
for t in threads:t.start()
for t in threads:t.join(20);assert not t.is_alive()
times["contention_pin"]=statistics.median(latencies)
print(json.dumps({"medians_us":times,"contention":{"served":sum(x[0] for x in counts),"refused":sum(x[1] for x in counts)},
 "source_sha256":hashlib.sha256(Path(ow.__file__).read_bytes()).hexdigest(),"python":sys.version,
 "source_file":ow.__file__}))

