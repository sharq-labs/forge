import json, pathlib, sys, collections, datetime, argparse, concurrent.futures as cf, os, hashlib
HERE = pathlib.Path(__file__).resolve().parent
ap=argparse.ArgumentParser(); ap.add_argument("--src",required=True); ap.add_argument("--cases",default="cases_hard")
# Each worker is a process carrying its own engcore import, so the pool's
# memory cost scales with the worker count. On a many-core machine
# os.cpu_count() workers can exhaust RAM and the pool dies as a
# BrokenProcessPool with no failing case to point at. Default unchanged;
# --workers bounds it where that happens. Scoring is ~80 s single-process, so
# a low count costs little.
ap.add_argument("--workers",type=int,default=None)
# Resolved against this file, not the caller's cwd. The old default wrote
# `results_hard.json` into the repo root, where .gitignore swallowed it, while
# the TRACKED benchmarks/hard/results_hard.json kept a baseline from a case set
# that no longer exists. The number a reader could see and the number the
# scorer produced were two different numbers for four rounds. One number, one
# place: the default now names the tracked file.
ap.add_argument("--results",default=str(HERE/"results_hard.json"))
# --- the hold-out seal ------------------------------------------------------
# The generator behind cases_hard has been corrected four times in response to
# what scoring it revealed, so every number from the development set is a
# number the generator has been tuned against. The hold-out is the only figure
# that is not, and it is worth exactly as much as the discipline that keeps it
# shut. That discipline is here rather than in a README: scoring anything that
# contains the sealed partition requires --open-holdout and appends a dated
# line to HOLDOUT_OPENINGS.log. See split_hard.py for the split rule.
ap.add_argument("--split",choices=("dev","holdout","all"),default="all",
                help="which partition to score. 'holdout' and 'all' both "
                     "contain sealed cases and require --open-holdout.")
ap.add_argument("--split-file",default=str(HERE/"split_hard.json"))
ap.add_argument("--open-holdout",action="store_true",
                help="break the seal deliberately, and record that it was broken")
ap.add_argument("--openings-log",default=str(HERE/"HOLDOUT_OPENINGS.log"))
ap.add_argument("--note",default="",help="why the seal was broken; goes in the log")
a=ap.parse_args(); sys.path.insert(0,a.src)
sys.path.insert(0,str(HERE))
from engcore.mcp.problem import run_electrothermal_case
from engcore.mcp.battery import run_battery_case
# The three questions a case answers, kept apart. See scoring.py for why a
# verdict match and a caught defect are not the same measurement.
from scoring import (
    ReportFacts, ScoredCase, per_family, score_case, scorecard,
)
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

def case_set_digest(paths):
    """Digest of the case set as bytes on disk: filename and content of each.

    Written into every summary. A run against a case set that gained, lost or
    edited one case now carries a different digest, so it is VISIBLY a
    different run rather than a silently different number. Kept identical to
    split_hard.case_set_digest -- the two must agree or the split does not
    describe these cases.
    """
    lines=[f"{p.name} {hashlib.sha256(p.read_bytes()).hexdigest()}" for p in paths]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()

FULL_DIGEST=case_set_digest(files)

# The split applies only if it was computed over exactly these bytes. A case
# set the split has never seen -- cases_battery, or a regenerated cases_hard --
# has no sealed partition to protect, so scoring it is unrestricted and says so.
split=None
sp=pathlib.Path(a.split_file)
if sp.exists():
    d=json.loads(sp.read_text(encoding="utf-8"))
    if d.get("case_set_digest")==FULL_DIGEST: split=d

if split is None:
    if a.split!="all":
        # The regeneration line is deliberately last and deliberately qualified.
        # It is the instruction this refusal hands over, and following it on a
        # case set that has NOT changed reallocates the sealed seats: cases move
        # from holdout into dev and the next --split dev run scores them, with no
        # --open-holdout and no line in the openings log. Read the
        # "REGENERATING AN EXISTING SPLIT OPENS THE HOLD-OUT" section of
        # split_hard.py before acting on it.
        sys.exit(f"--split {a.split} needs a split file matching these cases.\n"
                 f"  cases           {a.cases}\n  digest          {FULL_DIGEST[:16]}\n"
                 f"  split file      {sp} ({'digest mismatch' if sp.exists() else 'absent'})\n"
                 f"Check the digest above against the split file before doing anything:\n"
                 f"  python benchmarks/hard/split_hard.py --cases {a.cases} --verify\n"
                 f"ONLY if the case set really changed, regenerate. Regenerating an\n"
                 f"unchanged set reallocates the sealed seats -- cases move from holdout\n"
                 f"into dev and get scored, which opens the hold-out without saying so.\n"
                 f"See split_hard.py, 'REGENERATING AN EXISTING SPLIT OPENS THE HOLD-OUT'.\n"
                 f"  python benchmarks/hard/split_hard.py --cases {a.cases}")
    scope="all (no split defined for this case set)"
else:
    if a.split in ("holdout","all") and not a.open_holdout:
        sys.exit(
            f"REFUSED: --split {a.split} scores the sealed hold-out.\n\n"
            f"  {split['n_holdout']} of {split['n_total']} cases are sealed under rule "
            f"{split['rule_id']}, seed {split['seed']}.\n"
            f"  They exist so that one figure from this benchmark is not a figure its\n"
            f"  generator was tuned against. Scoring them during development is how that\n"
            f"  stops being true.\n\n"
            f"  Development runs:   --split dev\n"
            f"  Final evaluation:   --split {a.split} --open-holdout --note \"why\"\n"
            f"                      (appends a dated record to {pathlib.Path(a.openings_log).name})")
    ids={"dev":set(split["dev"]),"holdout":set(split["holdout"]),
         "all":set(split["dev"])|set(split["holdout"])}[a.split]
    # Filtered on the filename, not by parsing every case: this module is
    # re-imported by every spawned worker, so the filter runs once per process.
    # The stem IS the id -- checked here rather than assumed, because a case
    # set where it stopped being true would silently score the wrong partition.
    files=[f for f in files if f.stem in ids]
    if len(files)!=len(ids):
        sys.exit(f"split names {len(ids)} ids but {len(files)} case files matched; "
                 f"the split does not describe {a.cases}")
    scope=a.split

def _condition_facts(reports, scope=None):
    """Pool every condition name by what the run did with it.

    Across every model of every report, because `should_be_caught_by` names a
    condition and never says which model declares it -- so a scorer that looked
    in one model would miss a catcher that fired in another and call it a miss.
    `scope` restricts the models considered, which is how a battery case is
    read over the battery models the way its verdict already is.
    """
    violated, unknown, satisfied = set(), set(), set()
    for rep in reports:
        for record in rep.validity:
            if scope is not None and not record.model_id.startswith(scope):
                continue
            violated.update(record.assessment.violated)
            unknown.update(record.assessment.unknown)
            satisfied.update(record.assessment.satisfied)
    return violated, unknown, satisfied


def work(f):
    c=json.loads(f.read_text(encoding="utf-8")); g=c["ground_truth"]
    system=c.get("system","electrothermal")
    try:
        r=RUNNERS[system](c["payload"])
        if system=="battery":
            actual=_battery_scope(r.report)
            reports=(r.report,)
            # Same scope as the verdict: a battery case is answered over the
            # battery models, so its catcher is looked for there too.
            violated,unknown,satisfied=_condition_facts(reports,scope="battery.")
            refused=False
        else:
            reports=r.reports
            vs={rep.verdict.value.upper() for rep in reports}
            actual=next((v for v in ("NOT_SUPPORTED","INSUFFICIENT_EVIDENCE","SUPPORTED") if v in vs),"NO_REPORT")
            violated,unknown,satisfied=_condition_facts(reports)
            refused=r.run.outcome.name=="TRANSFER_REFUSED"
        det=""
    except Exception as e:
        n=type(e).__name__
        actual="REJECTED_AT_BOUNDARY" if n in BOUND else f"ERROR:{n}"; det=str(e)[:120]
        violated=unknown=satisfied=set(); refused=False
    facts=ReportFacts(verdict=actual,violated=frozenset(violated),
                      unknown=frozenset(unknown),satisfied=frozenset(satisfied),
                      coupling_refused=refused,error=det)
    row=score_case(g,c["id"],system,facts).as_row()
    row["detail"]=det
    return row
# The driver is guarded because this pool uses the "spawn" start method on
# Windows: each child re-imports this module, and without the guard that
# re-entered the pool construction below and died as a BrokenProcessPool.
# Everything above stays at module level precisely so the children can import
# `work` and reach engcore through the same sys.path insertion.
if __name__ == "__main__":
    with cf.ProcessPoolExecutor(max_workers=a.workers or os.cpu_count()) as ex:
        rows=list(ex.map(work,files,chunksize=40))
    # Rebuilt from the rows rather than recomputed, so the JSON a reader sees
    # and the numbers below it are the same objects.
    scored=[ScoredCase(case_id=r["id"],system=r["system"],defect=r["defect"],
                       label=r["label"],expected_verdict=r["expected"],
                       actual_verdict=r["actual"],verdict_match=r["match"],
                       catcher_raw=r["catcher"],catcher_form=r["catcher_form"],
                       catcher_name=None,
                       declared_catcher_status=r["catcher_status"],
                       catch_type=r["catch_type"],reason_match=r["reason_match"],
                       false_accept=r["false_accept"],false_reject=r["false_reject"],
                       deciding_conditions=tuple(r["deciding"])) for r in rows]
    card=scorecard(scored)
    summary={"generated":datetime.datetime.now().isoformat(timespec="seconds"),
     "scorecard_version":2,
     # Identity of the thing measured, carried next to the measurement. Without
     # these three fields a number in this file is unattributable: it could
     # have come from any case set, any partition, any commit.
     "cases_dir":pathlib.Path(a.cases).name,
     "case_set_digest":FULL_DIGEST,
     "split":scope,
     "split_rule":(f"{split['rule_id']} seed {split['seed']}" if split else None),
     "split_digest":(split["holdout_digest"] if a.split=="holdout" else
                     split["dev_digest"] if split and a.split=="dev" else None),
     "scored":f"{len(files)} of {len(list(pathlib.Path(a.cases).glob('*.json')))} cases on disk",
     **card,
     "errors":dict(collections.Counter(r["actual"] for r in rows if r["actual"].startswith("ERROR")))}
    families=per_family(scored)
    pathlib.Path(a.results).write_text(
        json.dumps({"summary":summary,"families":families,"rows":rows},
                   ensure_ascii=False,sort_keys=False),encoding="utf-8")
    # A seal that leaves no trace when it is broken is not a seal. The log is
    # append-only and tracked, so an opening is a line in the history rather
    # than a claim in a README, and a second opening cannot be mistaken for the
    # first.
    if split is not None and a.split in ("holdout","all"):
        # newline="" so the record lands LF-terminated on every platform.
        # Text mode on Windows wrote CRLF for the first opening and every
        # other tracked artifact here is LF; an append-only log that
        # changes line ending with the host is one more thing a reader has
        # to discount.
        with open(a.openings_log,"a",encoding="utf-8",newline="") as fh:
            fh.write(json.dumps({
                "opened_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                "split":a.split,"cases_dir":summary["cases_dir"],
                "case_set_digest":FULL_DIGEST,
                "holdout_digest":split["holdout_digest"],
                "scored":summary["scored"],
                "exact_verdict_match":summary["exact_verdict_match"],
                "catch_rate":summary["catch_rate"],
                "false_accept":summary["false_accept"],
                "false_reject":summary["false_reject"],
                "note":a.note or "(none given)"},ensure_ascii=False)+"\n")
        print(f"# SEAL OPENED -- recorded in {a.openings_log}",file=sys.stderr)
    print(json.dumps(summary,indent=2,ensure_ascii=False))
