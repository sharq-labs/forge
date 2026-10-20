"""Public-seed, trusted-built-in NON-FORMAL Blindfold rehearsal. No formal entrypoints."""
from __future__ import annotations

import argparse
import base64
import collections
import hashlib
import html
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ARMS = ("careful", "always_law", "always_insufficient")
PRESENTATIONS = ("anonymous", "paraphrased")
KINDS = ("confounded", "discoverable", "indistinguishable", "insufficient_evidence", "no_solution", "spurious_correlate")
PUBLIC_SEED = b"forge-blindfold-demo-public-seed-v1-2026-10-20"
LABELS = ("DEMO", "NON-FORMAL", "SECURITY_BOUNDARY_NOT_PROVEN")
MAX_TIMEOUT = 120


def checked(arm, presentation):
    if type(arm) is not str or arm not in ARMS:
        raise ValueError("Only trusted built-ins careful, always_law, always_insufficient are allowed")
    if presentation not in PRESENTATIONS:
        raise ValueError("Only anonymous (raw) and paraphrased presentations are allowed")


def worker(arm, presentation):
    """Fresh in-memory public fixtures only; answer-key derivation stays in harness."""
    checked(arm, presentation)
    from benchmarks.genesis_lite.v0_3 import harness, preregistration

    binding = harness.bind(preregistration.PREREG_PATH.read_bytes(), tier="development")
    record = harness.run_one(arm, binding=binding, master_seed=PUBLIC_SEED,
        campaign_id="public-demo-v1-" + presentation, presentation=presentation,
        seed=0, isolation="in_process")
    return record.to_dict()


def semantic(record):
    """Intentionally excludes ephemeral report signatures/digests and timings."""
    keys = ("arm", "seed", "campaign_id", "presentation", "status", "reasons", "key_digest",
            "presented_card_digests", "prereg_sha256", "harness", "tier_bound", "pair_bound",
            "environment_manifest_sha256", "arm_spec", "arm_code_sha256", "isolation",
            "observe_calls", "evaluator_status", "leakage_audit", "security_boundary")
    return {k: record.get(k, "UNKNOWN") for k in keys} | {"universes": [
        {k: v for k, v in row.items() if k != "proposer_seconds"}
        for row in record.get("universes", [])]}


def complete(record):
    rows = record.get("universes", [])
    return (record.get("status") == "VALID" and len(rows) == 6 and
            collections.Counter(r.get("kind") for r in rows) == collections.Counter(KINDS) and
            all(r.get("independent_agrees") is True for r in rows) and
            record.get("evaluator_status") == "VALID")


def execute(arm, presentation, timeout=30):
    checked(arm, presentation)
    if not 0 < timeout <= MAX_TIMEOUT:
        raise ValueError("timeout must be positive and at most 120 seconds per six-card run")
    argv = [sys.executable, str(Path(__file__).resolve()), "--worker", arm, presentation]
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src") + os.pathsep + str(ROOT))
    failure = dict(arm=arm, presentation=presentation, status="DEMO_EXECUTION_FAILED",
                   universes=[], evaluator_status="UNKNOWN", reasons=[])
    try:
        done = subprocess.run(argv, cwd=ROOT, env=env, text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        def text(value):
            return value.decode(errors="replace") if isinstance(value, bytes) else value
        return failure | dict(reasons=[f"Timeout after {timeout}s; worker terminated; card results UNKNOWN"],
                              stdout=text(exc.stdout), stderr=text(exc.stderr))
    except OSError as exc:
        return failure | dict(reasons=[f"Cannot start demo worker: {type(exc).__name__}: {exc}"])
    if done.returncode:
        return failure | dict(reasons=[f"Worker exited {done.returncode}"], stdout=done.stdout, stderr=done.stderr)
    try:
        result = json.loads(done.stdout)
        if not isinstance(result, dict) or result.get("arm") != arm or result.get("presentation") != presentation:
            raise ValueError("worker record identity mismatch")
        return result
    except (ValueError, TypeError) as exc:
        return failure | dict(reasons=[f"Invalid worker output: {exc}"], stdout=done.stdout, stderr=done.stderr)


def provenance():
    files = ("tools/forge_blindfold_demo.py", "tests/genesis_lite/test_blindfold_demo.py",
             "benchmarks/genesis_lite/v0_3/harness.py", "benchmarks/genesis_lite/v0_3/evaluator.py",
             "benchmarks/genesis_lite/v0_3/arms.py", "benchmarks/genesis_lite/harness.py",
             "benchmarks/genesis_lite/presentation.py", "src/engcore/blindfold/pair_bound.py",
             "benchmarks/genesis_lite/preregistration/genesis_lite_v0_3.json")
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, timeout=5)
    return dict(head=git.stdout.strip() if git.returncode == 0 else "UNKNOWN",
                python=sys.version, executable=sys.executable,
                source_sha256={name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files},
                local_diff="Uncommitted demo glue/tests/docs plus preserved checkpoint-2 work; HEAD alone is not source identity")


def run_demo(timeout=30):
    # This fixed matrix is not caller-provided; no plugins, custom callables, seed or mode selection.
    first, replay = [], []
    for target in (first, replay):
        for presentation in PRESENTATIONS:
            for arm in ARMS:
                target.append(execute(arm, presentation, timeout))
    comparisons = []
    for a, b in zip(first, replay, strict=True):
        status = "MATCH" if complete(a) and complete(b) and semantic(a) == semantic(b) else (
            "MISMATCH" if complete(a) and complete(b) else "UNKNOWN")
        comparisons.append(dict(arm=a["arm"], presentation=a["presentation"], status=status,
            meaning="Deterministic public-fixture semantic rerun, not cryptographic verification of archived records"))
    rows = [r for run in first for r in run.get("universes", [])]
    return dict(schema="forge.blindfold.public_demo/1", labels=list(LABELS),
        description="Public-seed rehearsal; trusted built-ins only; in-process development harness",
        exclusions="No formal root/registry/holdout access, lift, maturity, A2/B1, or formal discovery claim",
        public_seed_utf8=PUBLIC_SEED.decode(), arm_seed=0, planned_card_executions=36,
        planned_replay_executions=36, timeout_seconds_per_run=timeout,
        status="EXECUTION_COMPLETE" if all(c["status"] == "MATCH" for c in comparisons) else "EXECUTION_INCOMPLETE",
        provenance=provenance(), runs=first, replay_runs=replay, semantic_replay=comparisons,
        summary=dict(recorded_cards=len(rows), replay_cards=sum(len(r.get("universes", [])) for r in replay),
                     outcomes=dict(collections.Counter(r.get("outcome", "UNKNOWN") for r in rows)),
                     observation_calls=(sum(r["observe_calls"] for r in rows) if len(rows) == 36 and
                         all(type(r.get("observe_calls")) is int for r in rows) else "UNKNOWN"),
                     evaluator_agreement=dict(collections.Counter(str(r.get("independent_agrees", "UNKNOWN")) for r in rows))))


def render(report):
    esc = lambda value: html.escape(str(value))
    embedded = base64.b64encode(json.dumps(report, indent=2, sort_keys=True).encode()).decode("ascii")
    def pretty(value):
        return esc(json.dumps(value, indent=2, ensure_ascii=False))
    cards, failures = [], []
    for run in report["runs"]:
        title = run["arm"] + " / " + ("raw (anonymous)" if run["presentation"] == "anonymous" else run["presentation"])
        if run.get("reasons") or run.get("status") != "VALID":
            failures.append("<article><h3>"+esc(title)+"</h3><pre>"+pretty(run)+"</pre></article>")
        for row in run.get("universes", []):
            cards.append("<article class='card'><header>"+esc(title)+"</header><h3>"+esc(row.get("kind", "UNKNOWN"))+"</h3>"
                +"<p class='outcome'>"+esc(row.get("outcome", "UNKNOWN"))+"</p><dl>"
                +"".join("<dt>"+esc(k)+"</dt><dd>"+esc(row.get(k, "UNKNOWN"))+"</dd>" for k in
                          ("answer", "credit", "observe_calls", "independent_agrees", "universe_id"))
                +"</dl><details><summary>Sealed proposal / refusal</summary><pre>"+pretty(row.get("proposal", "UNKNOWN"))
                +"</pre></details></article>")
    replay = "".join("<tr><td>"+esc(c["arm"])+"</td><td>"+esc(c["presentation"])+"</td><td>"+esc(c["status"])+"</td></tr>"
                     for c in report["semantic_replay"])
    return """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Blindfold public demonstration</title><style>
body{font:16px/1.5 system-ui,sans-serif;background:#101821;color:#e6eef7;max-width:1300px;margin:auto;padding:32px}
h1{font-size:2.7rem;line-height:1.1}.banner{border:2px solid #ffc56d;padding:16px;color:#ffd59a;border-radius:12px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:16px}.card,article{background:#192735;padding:20px;border-radius:12px}
header{color:#9dc7e2;font-size:.9rem}.outcome{font-weight:700;color:#ffd59a}dt{color:#a5b6c7}dd{margin:0 0 8px;overflow-wrap:anywhere}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:.85rem}table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:10px;border-bottom:1px solid #41515f}
summary{cursor:pointer}a{color:#9ed9ff}section{margin:32px 0}
</style><body><p>FORGE · BLINDFOLD</p><h1>A public-seed rehearsal</h1>""" + (
        "<p class='banner'>"+esc(" / ".join(report["labels"]))+"</p><p>"+esc(report["description"])+"</p><p>"+esc(report["exclusions"])+"</p>"
        +"<p>Execution: <strong>"+esc(report["status"])+"</strong>. This label describes execution only.</p>"
        +"<section><h2>What happened</h2><p>Fixed seed: <code>"+esc(report["public_seed_utf8"])+"</code></p><pre>"+pretty(report["summary"])+"</pre>"
        +"<p>Six synthetic world kinds × two presentations × three built-ins. Refusals and failures remain visible; UNKNOWN is not success.</p></section>"
        +"<section><h2>Card outcomes</h2><div class='grid'>"+"".join(cards)+"</div></section>"
        +"<section><h2>Run failures / diagnostics</h2>"+("".join(failures) or "<p>No run-level failures recorded. Individual card refusals and outcomes appear above.</p>")+"</section>"
        +"<section><h2>Semantic replay</h2><p>Fresh deterministic public-fixture rerun; not cryptographic verification of archived records. Comparison excludes timing and ephemeral report signatures.</p>"
        +"<table><tr><th>Built-in</th><th>Presentation</th><th>Replay</th></tr>"+replay+"</table></section>"
        +"<section><h2>Provenance and full records</h2><p><a download='records.json' href='data:application/json;base64,"
        +embedded+"'>Save embedded JSON records</a></p><details><summary>Source / environment</summary><pre>"
        +pretty(report["provenance"])+"</pre></details></section></body></html>")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--output", type=Path, help="New output directory (must not exist)")
    parser.add_argument("--timeout", type=float, default=30, help="Seconds per six-card run, maximum 120")
    parser.add_argument("--worker", nargs=2, metavar=("BUILTIN", "PRESENTATION"), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not 0 < args.timeout <= MAX_TIMEOUT:
        parser.error("timeout must be positive and <=120 seconds")
    if args.worker:
        if args.output is not None:
            parser.error("worker mode cannot accept output paths")
        try:
            checked(*args.worker)
        except ValueError as exc:
            parser.error(str(exc))
        print(json.dumps(worker(*args.worker), sort_keys=True))
        return 0
    if args.output is None:
        parser.error("--output NEW_DIRECTORY is required")
    args.output.mkdir(parents=True, exist_ok=False)
    report = run_demo(args.timeout)
    (args.output/"records.json").write_bytes((json.dumps(report, indent=2, sort_keys=True)+"\n").encode())
    (args.output/"index.html").write_bytes(render(report).encode())
    print(json.dumps(dict(status=report["status"], summary=report["summary"], output=str(args.output.resolve()))))
    return 0 if report["status"] == "EXECUTION_COMPLETE" else 1


if __name__ == "__main__":
    sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
    raise SystemExit(main())
