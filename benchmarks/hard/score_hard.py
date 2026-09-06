import json, pathlib, sys, collections, datetime, argparse, concurrent.futures as cf, os
ap=argparse.ArgumentParser(); ap.add_argument("--src",required=True); ap.add_argument("--cases",default="cases_hard")
# Each worker is a process carrying its own engcore import, so the pool's
# memory cost scales with the worker count. On a many-core machine
# os.cpu_count() workers can exhaust RAM and the pool dies as a
# BrokenProcessPool with no failing case to point at. Default unchanged;
# --workers bounds it where that happens. Scoring is ~80 s single-process, so
# a low count costs little.
ap.add_argument("--workers",type=int,default=None)
a=ap.parse_args(); sys.path.insert(0,a.src)
from engcore.mcp.problem import run_electrothermal_case
BOUND={"MissingUnitError","WrongDimensionError","UnknownFieldError","MissingFieldError",
       "MalformedPayloadError","InvalidScientificProblem","ScientificValidationError"}
files=sorted(pathlib.Path(a.cases).glob("*.json"))
def work(f):
    c=json.loads(f.read_text(encoding="utf-8")); g=c["ground_truth"]
    try:
        r=run_electrothermal_case(c["payload"])
        vs={rep.verdict.value.upper() for rep in r.reports}
        actual=next((v for v in ("NOT_SUPPORTED","INSUFFICIENT_EVIDENCE","SUPPORTED") if v in vs),"NO_REPORT")
        det=""
    except Exception as e:
        n=type(e).__name__
        actual="REJECTED_AT_BOUNDARY" if n in BOUND else f"ERROR:{n}"; det=str(e)[:120]
    return {"id":c["id"],"defect":g["defect"],"label":g["label"],
            "expected":g["expected_verdict"],"actual":actual,
            "match":actual==g["expected_verdict"],"detail":det}
# The driver is guarded because this pool uses the "spawn" start method on
# Windows: each child re-imports this module, and without the guard that
# re-entered the pool construction below and died as a BrokenProcessPool.
# Everything above stays at module level precisely so the children can import
# `work` and reach engcore through the same sys.path insertion.
if __name__ == "__main__":
    with cf.ProcessPoolExecutor(max_workers=a.workers or os.cpu_count()) as ex:
        rows=list(ex.map(work,files,chunksize=40))
    hit=sum(r["match"] for r in rows)
    unsound=[r for r in rows if r["label"]!="valid"]; sound=[r for r in rows if r["label"]=="valid"]
    fa=[r for r in unsound if r["actual"]=="SUPPORTED"]
    fr=[r for r in sound if r["actual"]!="SUPPORTED"]
    caught=[r for r in unsound if r["actual"]!="SUPPORTED"]
    summary={"generated":datetime.datetime.now().isoformat(timespec="seconds"),"total":len(rows),
     "sound":len(sound),"unsound":len(unsound),
     "exact_verdict_match":f"{hit}/{len(rows)} ({hit/len(rows):.1%})",
     "catch_rate":f"{len(caught)}/{len(unsound)} ({len(caught)/len(unsound):.1%})",
     "false_accept":f"{len(fa)}/{len(unsound)} ({len(fa)/len(unsound):.2%})",
     "false_reject":f"{len(fr)}/{len(sound)} ({len(fr)/len(sound):.1%})",
     "false_accept_ids":[r["id"] for r in fa][:60],
     "errors":dict(collections.Counter(r["actual"] for r in rows if r["actual"].startswith("ERROR")))}
    pathlib.Path("results_hard.json").write_text(json.dumps({"summary":summary,"rows":rows},ensure_ascii=False),encoding="utf-8")
    print(json.dumps(summary,indent=2,ensure_ascii=False))
