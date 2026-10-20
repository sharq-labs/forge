"""Bounded v0.3 public development screen. Never formal admission or freeze."""
from __future__ import annotations
import argparse
import collections
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import statistics
import signal
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
PUBLIC_SEED="forge-mind-full-v03-development-readiness-2026-10-20-v1"
CANDIDATE="mind_full"
PRESENTATIONS=("anonymous","renamed","paraphrased","trap")
CAMPAIGNS=tuple("mind-readiness-development-v1-"+str(i) for i in range(5))
SEEDS=(0,1)
TIMEOUT=60
TOTAL_SECONDS=1200


def canonical(value):
    return (json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+"\n").encode()


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_pins():
    names=["tools/forge_mind_readiness.py","tests/genesis_lite_mind/test_readiness_v03.py",
           "tools/forge_blindfold_demo.py",
           "benchmarks/genesis_lite_mind/arm.py","benchmarks/genesis_lite_mind/__init__.py"]
    names += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT/"src/engcore/mind/minimal").glob("*.py"))]
    return {n:digest(ROOT/n) for n in names}

def dependency_pins():
    return {p.relative_to(ROOT).as_posix():digest(p) for folder in
            (ROOT/"src/engcore",ROOT/"benchmarks/genesis_lite") for p in sorted(folder.rglob("*.py"))}


def plan():
    from benchmarks.genesis_lite.v0_3 import arms, harness, preregistration, environment
    binding=harness.bind(preregistration.PREREG_PATH.read_bytes(),tier="development")
    manifest=environment.build_manifest()
    return dict(schema="forge.mind.development_readiness/1",status="DEVELOPMENT_PLAN_NOT_FORMAL_FREEZE",
        labels=["NON-FORMAL","SECURITY_BOUNDARY_NOT_PROVEN"],public_seed=PUBLIC_SEED,candidate=CANDIDATE,
        candidate_origin="20069cc2e9aadea6c5662a872626c1b8ef3dadd0",sources=source_pins(),
        dependency_sha256=hashlib.sha256(canonical(dependency_pins())).hexdigest(),
        prereg_sha256=binding.prereg_sha256,pair_bound=binding.pair_bound.to_dict(),
        environment_manifest=manifest,environment_manifest_sha256=environment.manifest_digest(manifest),
        arms=sorted(arms.ARMS)+[CANDIDATE],roles={k:v[3] for k,v in arms.ARMS.items()},
        campaigns=list(CAMPAIGNS),presentations=list(PRESENTATIONS),seeds=list(SEEDS),world_sets=40,
        master_derivation="sha256(public_seed | campaign | presentation | seed); new namespace, independent of demo/pilot",
        expected_runs=840,expected_cards=5040,workers=4,timeout_seconds=TIMEOUT,total_seconds=TOTAL_SECONDS,
        budget_scope="1200s for scheduled workers including replay; preparation/analysis excluded; process-group kill then communicate bounded to5s; outer command cap1500s",
        isolation="fresh worker and private temp directory per six-card run; trusted code in_process; module state can persist across six cards, unlike formal per-card processes; no security claim",
        replay="mind_full only: first campaign/seed0 for each presentation, same public fixtures",
        decision="All existing v0.3 directional performance checks (pooled lower95>0, pooled Holm, presentation and kind noninferiority) plus complete valid data and matching replay => PROMISING_FOR_FORMAL_PREPARATION only. Otherwise IMPROVEMENT_OR_MORE_EVIDENCE_NEEDED. Invalid/incomplete execution => BLOCKED_EXECUTION.",
        limits=["40 development world sets, 10 per presentation; not a power guarantee",
                "all repeated lookups, ranks, confidence bounds and p values exploratory",
                "no tuning, seed replacement, retry or hidden/formal root access",
                "candidate not yet chosen for formal freeze; external evaluator remains owner's choice",
                "same generator family as prior development, not independent real-world validation",
                "v0.3 analysis caps/thresholds unchanged; final lift_claimed must remain false"])


def verify_plan(doc):
    if doc != plan(): raise ValueError("plan/code/environment mismatch; no execution")


def worker(doc,arm,presentation,campaign,seed):
    verify_plan(doc)
    if arm not in doc["arms"] or presentation not in PRESENTATIONS or campaign not in CAMPAIGNS or seed not in SEEDS:
        raise ValueError("outside fixed development matrix")
    from benchmarks.genesis_lite.v0_3 import arms,harness,preregistration
    binding=harness.bind(preregistration.PREREG_PATH.read_bytes(),tier="development")
    if arm==CANDIDATE:
        from benchmarks.genesis_lite_mind.arm import mind_full
        # Development-only registry insertion after binding, in this fresh worker.
        # File registry/scoring/preregistration remain untouched; candidate source
        # is separately measured against the prewritten development plan.
        arms.ARMS[CANDIDATE]=(mind_full,"fixed Minimal Mind FULL development candidate",False,"candidate")
        if mind_full.__module__!="benchmarks.genesis_lite_mind.arm":
            raise ValueError("candidate callable identity mismatch")
    master=hashlib.sha256(f"{PUBLIC_SEED}|{campaign}|{presentation}|{seed}".encode()).digest()
    result=harness.run_one(arm,binding=binding,master_seed=master,campaign_id=campaign,
                          presentation=presentation,seed=seed,isolation="in_process").to_dict()
    if source_pins()!=doc["sources"]: raise ValueError("candidate/driver changed during run")
    result["development_source_pins"]=doc["sources"]
    result["actual_import_locations"]={"harness":str(Path(harness.__file__).resolve())}
    if arm==CANDIDATE:
        import benchmarks.genesis_lite_mind.arm as candidate_module
        result["arm_spec"]="benchmarks.genesis_lite_mind.arm:mind_full"
        result["arm_code_sha256"]={k:v for k,v in doc["sources"].items() if k.startswith(("src/","benchmarks/"))}
        result["actual_import_locations"]["candidate"]=str(Path(candidate_module.__file__).resolve())
    return result


def execute(plan_path,job,deadline):
    arm,presentation,campaign,seed=job
    failed=dict(arm=arm,presentation=presentation,campaign_id=campaign,seed=seed,status="DEVELOPMENT_EXECUTION_FAILED",
                universes=[],reasons=[],evaluator_status="UNKNOWN")
    remaining=deadline-time.monotonic()
    if remaining<=0: return failed|dict(reasons=["total development wall budget exhausted; NOT RUN"])
    argv=[sys.executable,str(Path(__file__).resolve()),"--worker",str(plan_path),arm,presentation,campaign,str(seed)]
    env=dict(os.environ,PYTHONPATH=str(ROOT/"src")+os.pathsep+str(ROOT),OMP_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1")
    with tempfile.TemporaryDirectory(prefix="mind-ready-dev-") as temp:
        env.update(TMPDIR=temp,TMP=temp,TEMP=temp)
        p=subprocess.Popen(argv,cwd=temp,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
        try: stdout,stderr=p.communicate(timeout=min(TIMEOUT,remaining))
        except subprocess.TimeoutExpired:
            os.killpg(p.pid,signal.SIGKILL)
            try:stdout,stderr=p.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                return failed|dict(reasons=["worker killed but cleanup did not finish within5s; no retry"])
            return failed|dict(reasons=["worker process group timeout; terminated; no retry"],stdout=stdout,stderr=stderr)
    if p.returncode: return failed|dict(reasons=[f"worker exit {p.returncode}"],stderr=stderr,stdout=stdout)
    try: return json.loads(stdout)
    except ValueError: return failed|dict(reasons=["malformed worker JSON"],stdout=stdout,stderr=stderr)


def semantic(row):
    from tools.forge_blindfold_demo import semantic as view
    return view(row)


def summarize(rows,replays,doc):
    from benchmarks.genesis_lite.v0_3 import analysis as a
    grid=frozenset((p,c,s) for p in PRESENTATIONS for c in CAMPAIGNS for s in SEEDS)
    required=[arm for arm,role in doc["roles"].items() if role in a.NON_ADVERSARIAL_ROLES]+[CANDIDATE]
    screened=a.screened_world_sets(rows,required)&grid
    retained=[r for r in rows if (r["presentation"],r["campaign_id"],r["seed"]) not in screened]
    expected={(arm,p,c,s) for arm in doc["arms"] for p in PRESENTATIONS for c in CAMPAIGNS for s in SEEDS}
    actual=[(r["arm"],r["presentation"],r["campaign_id"],r["seed"]) for r in rows]
    complete=(len(actual)==len(expected) and set(actual)==expected and all(
        r["status"]=="VALID" and len(r.get("universes",[]))==6 and all(u.get("independent_agrees") is True
        for u in r["universes"]) for r in retained))
    pairs=collections.defaultdict(set)
    for row in retained:
        pairs[(row["presentation"],row["campaign_id"],row["seed"])].add(row.get("key_digest","UNKNOWN"))
    pairing_ok=(len(pairs)==40-len(screened) and all(len(v)==1 and "UNKNOWN" not in v for v in pairs.values()) and
                len(set().union(*pairs.values()))==40-len(screened))
    complete=complete and pairing_ok
    replay=[]
    for rep in replays:
        matches=[r for r in rows if all(r.get(k)==rep.get(k) for k in ("arm","presentation","campaign_id","seed"))]
        expected_screen=(rep["presentation"],rep["campaign_id"],rep["seed"]) in screened
        replay.append(dict(presentation=rep["presentation"],status="MATCH" if len(matches)==1 and
            (rep["status"]=="VALID" or expected_screen and rep["status"]=="INVALID_BENCHMARK") and
            semantic(matches[0])==semantic(rep) else "UNKNOWN_OR_MISMATCH"))
    replay_ok=(len(replay)==4 and {r["presentation"] for r in replay}==set(PRESENTATIONS) and
               all(r["status"]=="MATCH" for r in replay))
    complete=complete and replay_ok and len(screened)<=2
    result=dict(labels=doc["labels"],formal_lift_claimed=False,complete=complete,pairing_ok=pairing_ok,replay=replay,
                screened_world_sets=sorted(screened),screen_cap_exceeded=len(screened)>2,replay_ok=replay_ok,
                recorded_runs=len(rows),invalid_runs=[{k:r.get(k) for k in ("arm","presentation","campaign_id","seed","reasons")}
                    for r in rows if r["status"]!="VALID"],candidate=CANDIDATE)
    by_arm={}
    for arm in doc["arms"]:
        rs=[r for r in retained if r["arm"]==arm];us=[u for r in rs for u in r.get("universes",[])]
        by_arm[arm]=dict(valid_runs=sum(r["status"]=="VALID" for r in rs),recorded_cards=len(us),
            mean_six_kind_credit=statistics.mean(sum(u["credit"] for u in r["universes"]) for r in rs) if complete else None,
            total_seconds=sum(r.get("wall_seconds",0) for r in rs),observations=sum(u.get("observe_calls",0) for u in us),
            outcomes=dict(collections.Counter(u["outcome"] for u in us)),
            kinds={k:dict(mean_credit=statistics.mean(u["credit"] for u in us if u["kind"]==k) if complete else None,
                outcomes=dict(collections.Counter(u["outcome"] for u in us if u["kind"]==k)),
                reasons=dict(collections.Counter((u.get("proposal") or {}).get("rationale","UNKNOWN") for u in us if u["kind"]==k))) for k in a.KINDS})
    result["arms"]=by_arm
    if not complete:
        result["recommendation"]="BLOCKED_EXECUTION";return result
    decision=a.lift_decision(rows,CANDIDATE,grid=grid)
    assert decision["lift_claimed"] is False,"development must never claim formal lift"
    result["exploratory_v03_analysis"]=decision
    checks=dict(positive_pooled_lower95=decision["primary"]["pooled"]["lower95"]>0,
                pooled_holm=decision["holm_significant"]["pooled"],
                presentation_noninferiority=all(decision["presentation_noninferiority"].values()),
                kind_noninferiority=all(v["ok"] for v in decision["kind_noninferiority"].values()),
                replay=len(replay)==4 and all(r["status"]=="MATCH" for r in replay))
    result["development_checks"]=checks
    result["recommendation"]="PROMISING_FOR_FORMAL_PREPARATION" if all(checks.values()) else "IMPROVEMENT_OR_MORE_EVIDENCE_NEEDED"
    return result


def run(plan_path,out):
    doc=json.loads(plan_path.read_bytes());verify_plan(doc);out.mkdir(parents=True,exist_ok=False)
    deps=dependency_pins()
    expected_deps=json.loads(plan_path.with_name("dependency-pins.json").read_bytes())
    if deps!=expected_deps:raise ValueError("transitive first-party dependency identity mismatch")
    (out/"plan.json").write_bytes(canonical(doc))
    jobs=[(arm,p,c,s) for p in PRESENTATIONS for c in CAMPAIGNS for s in SEEDS for arm in doc["arms"]]
    deadline=time.monotonic()+TOTAL_SECONDS;started=time.monotonic();rows=[]
    with (out/"runs.jsonl").open("wb") as sink,ThreadPoolExecutor(max_workers=4) as pool:
        tasks=[pool.submit(execute,plan_path,job,deadline) for job in jobs]
        for task in as_completed(tasks):
            row=task.result();rows.append(row);sink.write(canonical(row).replace(b"\n",b" ")+b"\n");sink.flush()
            if len(rows)%40==0:print(f"Completed {len(rows)}/{len(jobs)} development runs",flush=True)
    replays=[execute(plan_path,(CANDIDATE,p,CAMPAIGNS[0],0),deadline) for p in PRESENTATIONS]
    (out/"replay.json").write_bytes(canonical(replays))
    result=summarize(rows,replays,doc);result["elapsed_seconds"]=time.monotonic()-started
    result["dependencies_unchanged"]=dependency_pins()==deps
    if not result["dependencies_unchanged"]:
        result["recommendation"]="BLOCKED_DEPENDENCY_CHANGED";result["complete"]=False
    result["plan_sha256"]=digest(plan_path)
    (out/"summary.json").write_bytes(canonical(result))
    print(json.dumps({k:result[k] for k in ("recommendation","complete","recorded_runs","elapsed_seconds")}))
    return 0 if result["complete"] else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument("--prepare",type=Path);parser.add_argument("--plan",type=Path);parser.add_argument("--output",type=Path)
    parser.add_argument("--worker",nargs=5,help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.worker:
        path,arm,p,c,s=args.worker
        print(json.dumps(worker(json.loads(Path(path).read_bytes()),arm,p,c,int(s)),sort_keys=True));return 0
    if args.prepare:
        if args.plan or args.output:parser.error("prepare only")
        deps=dependency_pins()
        with args.prepare.with_name("dependency-pins.json").open("xb") as f:f.write(canonical(deps))
        with args.prepare.open("xb") as f:f.write(canonical(plan()))
        print(digest(args.prepare));return 0
    if not args.plan or not args.output:parser.error("--plan and new --output required")
    return run(args.plan.resolve(),args.output)


if __name__=="__main__":
    sys.path[:0]=[str(ROOT/"src"),str(ROOT)]
    raise SystemExit(main())
