"""Read-only diagnostic instrumentation around unchanged Mind/v0.3 development execution."""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = "forge-mind-trace-diagnosis-development-2026-10-20-v1"
JOBS = [(f"mind-trace-diagnosis-dev-{c}", p, 17)
        for c in range(3) for p in ("anonymous", "renamed", "paraphrased", "trap")]


def blob(x):
    return (json.dumps(x, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def pins():
    from tools.forge_mind_readiness import dependency_pins
    result = dependency_pins()
    for f in ("tools/forge_mind_diagnosis.py", "tools/forge_mind_readiness.py",
              "tools/forge_blindfold_demo.py", "tests/genesis_lite_mind/test_diagnosis.py"):
        result[f] = sha(ROOT / f)
    for p in (ROOT / "benchmarks/genesis_lite_mind").glob("*.py"):
        result[p.relative_to(ROOT).as_posix()] = sha(p)
    return result


def plan():
    from benchmarks.genesis_lite.v0_3 import harness, preregistration, environment
    b = harness.bind(preregistration.PREREG_PATH.read_bytes(), tier="development")
    return dict(status="DEVELOPMENT_DIAGNOSTIC_ONLY", namespace=NAMESPACE, jobs=JOBS,
                head=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                sources=pins(), prereg_sha256=b.prereg_sha256, pair_bound=b.pair_bound.to_dict(),
                environment=environment.build_manifest(), candidate="mind_full",
                primary_runs=12, primary_cards=72, target_cards=24,
                timeout_per_child_seconds=90, total_budget_seconds=900,
                protocol="12 fresh workers; all six kinds retained; export existing full traces. "
                         "Replay all 72 from recorded observations, with read-only refit snapshots. "
                         "One predeclared trace-disabled control: first job, same worlds. "
                         "No replacement seeds, retries, behavioral changes, baselines or lift inference.",
                isolation="trusted in_process per six-card run; fresh process and private temp per job; SECURITY_BOUNDARY_NOT_PROVEN",
                timeout_scope="subprocess timeout kills direct worker only; trusted worker does not launch proposers",
                root="public development namespace only; no formal root or admission",
                analysis="Diagnostic decision paths, not population rates or proven improvement. "
                         "No changes to thresholds, priors, scorer, candidate or certified source.")


def verify(doc):
    if blob(doc) != blob(plan()):
        raise ValueError("diagnostic plan/code/environment mismatch")


def join_traces(row, payloads):
    expected = row["presented_card_digests"]
    by_digest = {value: uid for uid, value in expected.items()}
    if len(by_digest) != len(expected):
        raise ValueError("ambiguous trace/card digests")
    found = {}
    from benchmarks.genesis_lite_mind.arm import card_digest
    for payload in payloads:
        card = payload["card"]
        # The public card's gl-* ID is deliberately different from the sealed bf-* ID.
        uid = by_digest.get(payload["card_digest"])
        if uid is None or uid in found or card_digest(card) != payload["card_digest"]:
            raise ValueError("trace/card identity mismatch or duplicate")
        found[uid] = payload
    if set(found) != set(expected) or len(found) != 6:
        raise ValueError("missing/extra traces")
    return found


def snapshot(comp):
    """Read-only posterior state; not a substitute conclusion rule."""
    w = comp.weights()
    settable = {x.name for x in comp.problem.inputs}
    return dict(n=len(comp.rows), noise=comp.noise.to_dict(),
                support="RAW_REFIT_POSTERIOR_BEFORE_CONCLUSION_FILTERS" if w else "UNAVAILABLE",
                null_mass=(sum(v for h, v in w.items()
                               if not set(comp.rivals[h].structure.linear) & settable) if w else None),
                inclusion={c: (sum(v for h, v in w.items() if c in comp.rivals[h].structure.linear) if w else None)
                           for c in comp.problem.covariates},
                weights=w,
                refuted=[h for h, r in comp.rivals.items() if r.hypothesis.status.value == "refuted"])


def analyze(payload):
    from benchmarks.genesis_lite_mind.arm import problem_from_card
    from engcore.mind.minimal.runner import run_mind, FULL
    from engcore.mind.minimal.competition import HypothesisCompetition
    from engcore.mind.minimal.trace import ReplayObserver, compare
    trace = payload["trace"]
    problem = problem_from_card(payload["card"])
    if problem.digest != trace["problem_digest"]:
        raise ValueError("trace problem mismatch")
    observer = ReplayObserver(trace["executions"], trace["observations"], trace.get("refusal"))
    trajectory = []

    def profile(frame, event, arg):
        if event == "return" and frame.f_code is HypothesisCompetition.refit.__code__:
            trajectory.append(snapshot(frame.f_locals["self"]))

    previous = sys.getprofile()
    try:
        sys.setprofile(profile)
        replayed = run_mind(problem, observer, seed=int(trace["seed"]), config=FULL)
    finally:
        sys.setprofile(previous)
    check = compare(trace, replayed.trace).to_dict()
    if check["status"] != "VERIFIED" or observer.calls != len(trace["observations"]):
        raise ValueError(f"diagnostic replay diverged: {check}")
    if trace["final_stop"] != replayed.trace["final_stop"] or trace["final_state"] != replayed.trace["final_state"]:
        raise ValueError("diagnostic replay diverged: final stop/state metadata")
    comp = replayed.competition
    rivals = {h: dict(structure=r.structure.to_dict(), log_prior=r.log_prior,
                     weight=r.weight, status=r.hypothesis.status.value,
                     decisive=comp.faced_decisive_test(h),
                     fit=None if r.fitted is None else r.fitted.summary())
              for h, r in comp.rivals.items()}
    covmodels = {c: dict(r2=m.r2, resid_var=m.resid_var, coef=list(m.coef))
                 for c, m in comp.covmodels.items()}
    return dict(replay=check, trajectory=trajectory, rivals=rivals, covmodels=covmodels,
                conclusion=replayed.trace["conclusion"], final_stop=replayed.trace["final_stop"],
                replay_scope="step chain, conclusion, final stop/state and observation consumption; multiplicity ledger excluded",
                budget=problem.budget, observations=len(trace["observations"]),
                selection_generators=dict(collections.Counter(
                    s["selection"]["selected"]["generator"] for s in trace["steps"]
                    if s["selection"].get("selected"))))


def worker(doc, index, out, no_trace=False):
    verify(doc)
    from benchmarks.genesis_lite.v0_3 import arms, harness, preregistration
    from benchmarks.genesis_lite_mind.arm import mind_full, TRACE_FOLDER
    b = harness.bind(preregistration.PREREG_PATH.read_bytes(), tier="development")
    arms.ARMS["mind_full"] = (mind_full, "unchanged diagnostic candidate", False, "candidate")
    campaign, presentation, seed = doc["jobs"][index]
    master = hashlib.sha256(f"{NAMESPACE}|{campaign}|{presentation}|{seed}".encode()).digest()
    out.mkdir()
    with tempfile.TemporaryDirectory(prefix="mind-diagnose-") as temp:
        os.environ.update(TMPDIR=temp, TMP=temp, TEMP=temp)
        folder = Path(temp) / TRACE_FOLDER
        if not no_trace:
            folder.mkdir()
        row = harness.run_one("mind_full", binding=b, master_seed=master, campaign_id=campaign,
                             presentation=presentation, seed=seed, isolation="in_process").to_dict()
        row["arm_spec"] = "benchmarks.genesis_lite_mind.arm:mind_full"
        row["diagnostic_plan_sha256"] = hashlib.sha256(blob(doc)).hexdigest()
        row["candidate_source_sha256"] = {k:v for k,v in doc["sources"].items()
                                        if k.startswith(("src/engcore/mind/minimal/", "benchmarks/genesis_lite_mind/"))}
        (out / "run.json").write_bytes(blob(row))
        if row["status"] != "VALID" or not all(u["independent_agrees"] for u in row["universes"]):
            raise ValueError("invalid run; retained, no replacement")
        if not no_trace:
            shutil.copytree(folder, out / "traces")
            payloads = [json.loads(p.read_bytes()) for p in sorted(folder.glob("*.json"))]
            joined = join_traces(row, payloads)
            diagnostics = []
            for u in row["universes"]:
                result = analyze(joined[u["universe_id"]])
                diagnostics.append(dict(universe=u, **result))
            (out / "diagnostics.json").write_bytes(blob(diagnostics))
    if pins() != doc["sources"]:
        raise ValueError("source changed during diagnostic execution")


def run(doc, plan_path, out):
    verify(doc)
    out.mkdir()
    start = time.monotonic()
    receipts = []
    for i in range(len(JOBS) + 1):
        control = i == len(JOBS)
        path = out / ("control" if control else f"job-{i:02}")
        args = [sys.executable, str(Path(__file__).resolve()), "--worker", str(plan_path),
                str(0 if control else i), str(path)] + (["--no-trace"] if control else [])
        remaining = 900 - (time.monotonic() - start)
        if remaining <= 0:
            raise TimeoutError("diagnostic budget exhausted; no retry")
        before = time.monotonic()
        try:
            with tempfile.TemporaryDirectory(prefix="mind-diagnostic-worker-") as cwd:
                env = dict(os.environ, PYTHONPATH=str(ROOT / "src")+os.pathsep+str(ROOT))
                proc = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=min(90, remaining))
            receipt = dict(argv=args, exit_code=proc.returncode, stdout=proc.stdout,
                           stderr=proc.stderr, seconds=time.monotonic()-before)
        except subprocess.TimeoutExpired:
            receipt = dict(argv=args, exit_code=None, status="TIMEOUT_NO_RETRY")
        receipts.append(receipt)
        (out / "receipts.json").write_bytes(blob(receipts))
        if receipt.get("exit_code") != 0:
            raise RuntimeError(f"job {i} failed; exact receipt retained")
        print(f"{path.name} complete", flush=True)
    from tools.forge_blindfold_demo import semantic
    a = json.loads((out / "job-00/run.json").read_bytes())
    b = json.loads((out / "control/run.json").read_bytes())
    if semantic(a) != semantic(b):
        raise ValueError("trace export altered semantic execution")
    rows = [json.loads((out / f"job-{i:02}/run.json").read_bytes()) for i in range(len(JOBS))]
    old = ROOT / "docs/work/evidence/mind_full_v03_readiness_2026_10_20_v1/v3/results/runs.jsonl"
    old_keys = {json.loads(l)["key_digest"] for l in old.read_text().splitlines()}
    keys = {r["key_digest"] for r in rows}
    if len(keys) != 12 or keys & old_keys:
        raise ValueError("duplicate or previously used world set")
    result = dict(status="DIAGNOSTIC_COMPLETE_NOT_FORMAL", runs=12, cards=72,
                  replayed_traces=72, trace_disabled_control="MATCH", distinct_new_world_sets=12,
                  development_only=True, elapsed_seconds=time.monotonic()-start)
    if pins() != doc["sources"]:
        raise ValueError("sources changed")
    (out / "summary.json").write_bytes(blob(result))
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--prepare", type=Path)
    p.add_argument("--plan", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--worker", nargs=3)
    p.add_argument("--no-trace", action="store_true")
    args = p.parse_args()
    if args.prepare:
        args.prepare.write_bytes(blob(plan()))
    elif args.worker:
        path, index, dest = args.worker
        worker(json.loads(Path(path).read_bytes()), int(index), Path(dest), args.no_trace)
    else:
        print(json.dumps(run(json.loads(args.plan.read_bytes()), args.plan.resolve(), args.output)))
