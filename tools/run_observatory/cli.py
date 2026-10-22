"""Command line: ``python -m tools.run_observatory [--run-root DIR] <command> ...``.

    run [options] -- <command> [args...]   execute under observation; exits with the child's code
    show RUN_ID                            print one receipt
    verify [RUN_ID ...] [--all]            check seals and the ledger's digests (exit 1 on any failure)
    list [--kind K] [--workload W] [--sha S] [--failed] [--limit N]
    history WORKLOAD_ID                    performance history of one workload, oldest first
    fastest RUN_ID                         the fastest run exactly comparable to RUN_ID
    compare CANDIDATE BASELINE             comparability class, deltas and readings for two runs
    recover [--force]                      seal pending receipts left behind by a killed observer
    reindex                                rebuild ledger.sqlite from the receipt files

The run root is ``--run-root``, else ``$FORGE_RUN_ROOT``, else ``~/.forge-run-ledger``.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import sys
from typing import Sequence

from tools.run_observatory import RUN_KINDS, compare, receipt as receipt_mod, runner
from tools.run_observatory.ledger import Ledger


def default_run_root() -> Path:
    configured = os.environ.get("FORGE_RUN_ROOT")
    return Path(configured) if configured else Path.home() / ".forge-run-ledger"


def _key_value(text: str) -> tuple[str, str]:
    key, sep, value = text.partition("=")
    if not sep or not key:
        raise argparse.ArgumentTypeError(f"expected KEY=VALUE, got {text!r}")
    return key, value


def _counter(text: str) -> tuple[str, float]:
    key, value = _key_value(text)
    try:
        number = int(value)
    except ValueError:
        try:
            number = float(value)
        except ValueError:
            raise argparse.ArgumentTypeError(f"counter {key!r} needs a number, got {value!r}") from None
    return key, number


def _policy(args: argparse.Namespace) -> dict:
    base = None
    if getattr(args, "policy", None):
        loaded = json.loads(Path(args.policy).read_text(encoding="utf-8"))
        unknown = set(loaded) - set(compare.DEFAULT_POLICY)
        if unknown:
            raise ValueError(f"unknown policy fields {sorted(unknown)}")
        base = {**compare.DEFAULT_POLICY, **loaded}
    return compare.make_policy(base, regression_threshold_pct=args.regression_threshold_pct,
                               improvement_threshold_pct=args.improvement_threshold_pct,
                               min_absolute_seconds=args.min_absolute_seconds)


def _add_policy_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--policy", help="JSON performance policy (fields of the default policy)")
    parser.add_argument("--regression-threshold-pct", type=float)
    parser.add_argument("--improvement-threshold-pct", type=float)
    parser.add_argument("--min-absolute-seconds", type=float)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tools.run_observatory",
                                     description="FORGE Run Observatory: an immutable ledger of runs. "
                                                 "Developer telemetry -- not scientific evidence, not certification.")
    parser.add_argument("--run-root", type=Path, default=None, help="ledger directory (outside any repository)")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="execute a command under observation: run [options] -- CMD ARGS...")
    run.add_argument("--kind", default=None, choices=RUN_KINDS)
    run.add_argument("--name")
    run.add_argument("--tag", action="append", default=[])
    run.add_argument("--parent", help="parent run id")
    run.add_argument("--group", help="declared comparison group")
    run.add_argument("--adapter", default="generic", help="generic (default) or pytest")
    run.add_argument("--cwd", type=Path)
    run.add_argument("--repo", type=Path, help="repository whose identity binds the run (default: --cwd)")
    run.add_argument("--input", action="append", default=[], type=Path, help="dataset file/dir or input manifest")
    run.add_argument("--config", action="append", default=[], type=Path)
    run.add_argument("--seed", action="append", default=[])
    run.add_argument("--declare", action="append", default=[], type=_key_value,
                     help="KEY=VALUE workload identity (plan id, provider/model version)")
    run.add_argument("--workload-env", action="append", default=[], help="bind a variable into the workload by hash")
    run.add_argument("--counter", action="append", default=[], type=_counter, help="NAME=NUMBER, a trusted counter")
    run.add_argument("--artifact", action="append", default=[], type=Path, help="declared output to hash after the run")
    run.add_argument("--output-identity")
    run.add_argument("--trace-identity")
    run.add_argument("--replay-of", help="run id of the original run this one replays")
    run.add_argument("--cost-compute", type=float)
    run.add_argument("--cost-storage", type=float)
    run.add_argument("--currency")
    run.add_argument("--cost-model")
    run.add_argument("--baseline", default="auto", help="auto (default), none, or a run id")
    _add_policy_options(run)
    run.add_argument("--sample-interval", type=float, default=0.1)
    run.add_argument("--grace-seconds", type=float, default=10.0)
    run.add_argument("--no-logs", action="store_true", help="do not store (redacted) stdout/stderr")
    run.add_argument("--no-env-cache", action="store_true", help="probe the environment instead of using the cache")
    run.add_argument("--refresh-env-cache", action="store_true", help="probe the environment and rewrite its cache")
    run.add_argument("--quiet", action="store_true", help="do not pass the child's output through")

    show = sub.add_parser("show")
    show.add_argument("run_id")
    verify = sub.add_parser("verify")
    verify.add_argument("run_ids", nargs="*")
    verify.add_argument("--all", action="store_true")
    verify.add_argument("--json", action="store_true")
    listing = sub.add_parser("list")
    listing.add_argument("--kind")
    listing.add_argument("--workload")
    listing.add_argument("--sha")
    listing.add_argument("--failed", action="store_true")
    listing.add_argument("--limit", type=int, default=20)
    listing.add_argument("--json", action="store_true")
    history = sub.add_parser("history")
    history.add_argument("workload_id")
    history.add_argument("--json", action="store_true")
    fastest = sub.add_parser("fastest")
    fastest.add_argument("run_id")
    fastest.add_argument("--json", action="store_true")
    comparing = sub.add_parser("compare")
    comparing.add_argument("candidate")
    comparing.add_argument("baseline")
    comparing.add_argument("--json", action="store_true")
    _add_policy_options(comparing)
    recover = sub.add_parser("recover")
    recover.add_argument("--force", action="store_true", help="also seal runs whose observer still seems alive")
    recover.add_argument("--json", action="store_true")
    reindex = sub.add_parser("reindex")
    reindex.add_argument("--json", action="store_true")
    return parser


def _install_signal_handlers() -> dict:
    """Interrupts stop the child during a run and are deferred while a receipt is sealed; returns the old handlers."""
    def handler(signum, frame):  # noqa: ARG001
        if runner.PHASE["value"] == "SEAL":
            runner.LATE_SIGNALS.append(signum)
            return
        raise runner.Interrupted(signum)

    previous = {}
    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        if hasattr(signal, name):
            previous[getattr(signal, name)] = signal.signal(getattr(signal, name), handler)
    return previous


def _rows(rows: list[dict], as_json: bool) -> None:
    if as_json:
        print(json.dumps(rows, indent=2))
        return
    for row in rows:
        wall = row.get("wall_seconds")
        print(f"{row['run_id']}  {row.get('run_kind', ''):<13} {row.get('status', ''):<15} "
              f"{'-' if wall is None else f'{wall:9.3f}s'}  {(row.get('workload_id') or '')[:12]}  "
              f"{(row.get('git_sha') or '')[:10]}  {row.get('name') or ''}")


def _cmd_run(args: argparse.Namespace, child: list[str], run_root: Path) -> int:
    if not child:
        print("run: give the command after '--'", file=sys.stderr)
        return 2
    cost = {k: v for k, v in (("compute_cost_estimate", args.cost_compute), ("storage_cost_estimate", args.cost_storage),
                               ("currency", args.currency), ("cost_model_id", args.cost_model)) if v is not None}
    request = runner.RunRequest(
        argv=child, run_root=run_root, cwd=args.cwd, repo=args.repo,
        kind=args.kind or ("TEST" if args.adapter.lower() == "pytest" else "UTILITY"), name=args.name, tags=args.tag,
        parent=args.parent, group=args.group, adapter=args.adapter, inputs=args.input, configs=args.config,
        seeds=args.seed, declared=dict(args.declare), workload_env=args.workload_env, counters=dict(args.counter),
        artifacts=args.artifact, output_identity=args.output_identity, trace_identity=args.trace_identity,
        replay_of=args.replay_of, cost=cost, baseline=args.baseline, policy=_policy(args),
        sample_interval=args.sample_interval, persist_logs=not args.no_logs, env_cache=not args.no_env_cache,
        refresh_env_cache=args.refresh_env_cache, quiet=args.quiet,
        grace_seconds=args.grace_seconds)
    previous = _install_signal_handlers()
    try:
        outcome = runner.execute(request)
    except runner.RunRootInsideRepository as exc:
        print(f"run_observatory: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"run_observatory: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("run_observatory: interrupted before the command started; nothing ran", file=sys.stderr)
        return 130
    finally:
        for signum, old in previous.items():
            signal.signal(signum, old)
    for warning in outcome.warnings:
        print(f"run_observatory: warning: {warning}", file=sys.stderr)
    sys.stderr.write(runner.summary_text(outcome.receipt, outcome.receipt_path))
    sys.stderr.flush()
    return outcome.exit_code


def _cmd_verify(args: argparse.Namespace, book: Ledger) -> int:
    paths = list(book.receipt_files()) if args.all or not args.run_ids else [
        book.root / "receipts" / f"{run_id}.json" for run_id in args.run_ids]
    report = []
    for path in paths:
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
            verdict = book.verify_receipt(rec)
        except (OSError, ValueError):
            rec, verdict = {}, "UNREADABLE"
        report.append({"run_id": rec.get("run_id", path.stem), "path": str(path), "verdict": verdict})
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for entry in report:
            print(f"{entry['verdict']:<16} {entry['run_id']}")
    return 0 if all(e["verdict"] == "VALID" for e in report) else 1


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    child: list[str] = []
    if "--" in argv:
        split = argv.index("--")
        argv, child = argv[:split], argv[split + 1:]
    args = build_parser().parse_args(argv)
    run_root = (args.run_root or default_run_root()).resolve()
    if args.command == "run":
        try:
            return _cmd_run(args, child, run_root)
        except (ValueError, OSError) as exc:
            print(f"run_observatory: {exc}", file=sys.stderr)
            return 2
    if args.command == "recover":
        report = runner.recover(run_root, force=args.force)
        print(json.dumps(report, indent=2) if args.json else
              "\n".join(f"{k}: {', '.join(v) or '-'}" for k, v in report.items()))
        return 0
    book = Ledger(run_root)
    if args.command == "verify":
        return _cmd_verify(args, book)
    if args.command == "show":
        rec = book.load_receipt(args.run_id)
        if rec is None:
            print(f"no receipt for {args.run_id}", file=sys.stderr)
            return 1
        print(json.dumps(rec, indent=2, sort_keys=True))
        return 0
    if args.command == "list":
        if args.failed:
            rows = book.failed(args.limit)
        elif args.kind:
            rows = book.by_kind(args.kind, args.limit)
        elif args.workload:
            rows = book.by_workload(args.workload, args.limit)
        elif args.sha:
            rows = book.by_git_sha(args.sha, args.limit)
        else:
            rows = book.latest(args.limit)
        _rows(rows, args.json)
        return 0
    if args.command == "history":
        _rows(book.history(args.workload_id), args.json)
        return 0
    if args.command == "fastest":
        row = book.fastest_exact_comparable(args.run_id)
        _rows([row] if row else [], args.json)
        return 0 if row else 1
    if args.command == "compare":
        candidate, baseline = book.load_receipt(args.candidate), book.load_receipt(args.baseline)
        for run_id, rec in ((args.candidate, candidate), (args.baseline, baseline)):
            if rec is None or not receipt_mod.verify(rec):
                print(f"receipt for {run_id} is missing or does not verify", file=sys.stderr)
                return 1
        result = compare.compare(candidate, baseline, _policy(args))
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"COMPARABILITY = {result['comparability']}  PERFORMANCE = {result['performance']}  "
                  f"RESULT_DELTA = {result['result_delta']}  FAILURE_SET = {result['failure_set']}")
            for name, d in (result["deltas"] or {}).items():
                if d["pct"] is not None:
                    print(f"  {name}: {d['baseline']:.6g} -> {d['candidate']:.6g} ({d['pct']:+.1f}%, {d['comparability']})")
        return 0
    if args.command == "reindex":
        report = book.reindex()
        print(json.dumps(report, indent=2) if args.json else f"indexed {report['indexed']}, rejected {report['rejected']}")
        return 0
    return 2
