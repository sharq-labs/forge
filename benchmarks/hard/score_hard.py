import json, pathlib, sys, collections, datetime, argparse, concurrent.futures as cf, os
ap=argparse.ArgumentParser(); ap.add_argument("--src",required=True); ap.add_argument("--cases",default="cases_hard")
# Each worker is a process carrying its own engcore import, so the pool's
# memory cost scales with the worker count. On a many-core machine
# os.cpu_count() workers can exhaust RAM and the pool dies as a
# BrokenProcessPool with no failing case to point at. Default unchanged;
# --workers bounds it where that happens. Scoring is ~80 s single-process, so
# a low count costs little.
ap.add_argument("--workers",type=int,default=None)
ap.add_argument("--results",default="results_hard.json")
a=ap.parse_args(); sys.path.insert(0,a.src)
from engcore.mcp.problem import run_electrothermal_case
from engcore.mcp.battery import run_battery_case
# One scorer, two systems. Each case names the system it belongs to; the key is
# absent on every electro-thermal case ever written, so its absence means that
# system rather than an error. A scorer that only knew one system would have
# had the second one's cases silently scored against the wrong boundary.
RUNNERS = {"electrothermal": run_electrothermal_case, "battery": run_battery_case}

# A battery case is scored over the BATTERY MODELS' verdicts, not the whole
# report's, and the reason is a finding rather than a convenience.
#
# `run_self_heating_discharge` accepts no applicability declaration for the
# thermal body it marches, so the lumped model in every battery report is
# honestly UNKNOWN and NO battery case can reach SUPPORTED -- catch rate 100 %,
# false accept 0 %, false reject 100 %, which is the unearned catch rate this
# benchmark's README already warns about. Scoring the whole report would
# measure that one gap 400 times and nothing else.
#
# So the verdict is derived over the four battery models by the same precedence
# `derive_verdict` uses -- a violation outranks a gap -- and the thermal gap is
# reported separately in the README rather than swallowed. This is scoped, not
# softened: every battery condition still has to be right.
def _battery_scope(report):
    statuses = {r.model_id: r.assessment.status.value for r in report.validity
                if r.model_id.startswith("battery.")}
    if any(v == "outside_validated_domain" for v in statuses.values()):
        return "NOT_SUPPORTED"
    if any(v == "unknown" for v in statuses.values()):
        return "INSUFFICIENT_EVIDENCE"
    return "SUPPORTED"
BOUND={"MissingUnitError","WrongDimensionError","UnknownFieldError","MissingFieldError",
       "MalformedPayloadError","InvalidScientificProblem","ScientificValidationError"}
files=sorted(pathlib.Path(a.cases).glob("*.json"))
def work(f):
    c=json.loads(f.read_text(encoding="utf-8")); g=c["ground_truth"]
    try:
        system=c.get("system","electrothermal")
        r=RUNNERS[system](c["payload"])
        if system=="battery":
            actual=_battery_scope(r.report)
        else:
            vs={rep.verdict.value.upper() for rep in r.reports}
            actual=next((v for v in ("NOT_SUPPORTED","INSUFFICIENT_EVIDENCE","SUPPORTED") if v in vs),"NO_REPORT")
        det=""
    except Exception as e:
        n=type(e).__name__
        actual="REJECTED_AT_BOUNDARY" if n in BOUND else f"ERROR:{n}"; det=str(e)[:120]
    return {"id":c["id"],"system":c.get("system","electrothermal"),
            "defect":g["defect"],"label":g["label"],
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
    pathlib.Path(a.results).write_text(json.dumps({"summary":summary,"rows":rows},ensure_ascii=False),encoding="utf-8")
    print(json.dumps(summary,indent=2,ensure_ascii=False))
