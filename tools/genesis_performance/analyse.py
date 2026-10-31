"""Summarize public software controls; never computes a Blindfold verdict.

Usage: python -m tools.genesis_performance.analyse BASELINE DIRECTORY ... --out JSON
Exact comparisons include query/response and complete proposal hashes. Runtime,
random transport/signature identities and clocks are reported separately.
"""
import argparse
import hashlib
import json
import math
import pathlib
import random
import statistics


def quantile(values, p):
    values = sorted(values)
    if not values:
        return None
    position = (len(values) - 1) * p
    lo, hi = math.floor(position), math.ceil(position)
    return values[lo] + (values[hi] - values[lo]) * (position - lo)


def stats(values):
    return {"n": len(values), "mean": statistics.mean(values) if values else None,
            "sd": statistics.stdev(values) if len(values) > 1 else None,
            "median": quantile(values, .5), "p95": quantile(values, .95),
            "min": min(values) if values else None, "max": max(values) if values else None}


def read(directory):
    directory = pathlib.Path(directory)
    raw = (directory / "runs.jsonl").read_bytes()
    summary = json.loads((directory / "summary.json").read_text())
    if hashlib.sha256(raw).hexdigest() != summary["runs_sha256"]:
        raise ValueError(f"runs digest mismatch: {directory}")
    runs = [json.loads(line) for line in raw.splitlines()]
    manifest = json.loads((directory / "manifest.json").read_text())
    if len(runs) != summary["completed"] or manifest["dirty"]:
        raise ValueError(f"incomplete or dirty run: {directory}")
    return runs, summary, manifest


def key(run):
    return (run["arm"], run.get("seed", run.get("index")), run.get("campaign_id"))


def semantics(run):
    if "runtime_diagnostic" in run:
        return {"status": run["status"], "equations": run["runtime_diagnostic"]["equations"]}
    fields = ("status", "reasons", "observe_calls", "universes", "key_digest", "presented_card_digests",
              "leakage_audit", "evaluator_status", "v3_total_credit", "config_digest", "escrow_rule",
              "proposer_kind", "budget_fraction", "library_versions")
    result = {field: run[field] for field in fields}
    result["traces"] = [{k: t.get(k) for k in ("universe_id", "proposal_sha256",
                        "query_trace_without_transport_nonce_sha256")} for t in run["operator_timings"]]
    return result


def phase_durations(runs):
    values = {}
    for run in runs:
        for timing in run.get("operator_timings", []):
            opened = {}
            for event in timing.get("diagnostic_events_untrusted", []):
                msg, timestamp = event["message"], event["parent_elapsed_seconds"]
                if msg["event"] == "call":
                    opened.setdefault(msg["label"], []).append(timestamp)
                elif msg["event"] == "return" and opened.get(msg["label"]):
                    values.setdefault(msg["label"], []).append(timestamp - opened[msg["label"]].pop())
    return {name: stats(samples) for name, samples in values.items()}


def comparison(reference, runs):
    base = {key(run): run for run in reference}
    mismatches, matched, ratios = [], 0, []
    for run in runs:
        previous = base.get(key(run))
        if previous is None:
            continue
        before, after = semantics(previous), semantics(run)
        different = [field for field in before if before[field] != after[field]]
        if different:
            mismatches.append({"key": key(run), "fields": different})
        else:
            matched += 1
        if "campaign_total_seconds" in run and "campaign_total_seconds" in previous:
            ratios.append(previous["campaign_total_seconds"] / run["campaign_total_seconds"])
    interval = None
    if len(ratios) >= 3:
        rng = random.Random(20261031)
        means = [statistics.mean(rng.choices(ratios, k=len(ratios))) for _ in range(10000)]
        interval = [quantile(means, .025), quantile(means, .975)]
    return {"exact_matching_campaigns": matched, "mismatches": mismatches,
            "unmatched_campaigns": len(runs) - matched - len(mismatches),
            "paired_service_speedup": stats(ratios), "paired_bootstrap_95_percentile": interval,
            "interval_scope": "public fixture service-time sample only; not full-grid uncertainty"}


def summarize(directory, reference):
    runs, summary, manifest = read(directory)
    valid = sum(run["status"] == "VALID" for run in runs)
    arm_times = {arm: stats([r["campaign_total_seconds"] for r in runs if r["arm"] == arm and
                            "campaign_total_seconds" in r]) for arm in sorted({r["arm"] for r in runs})}
    startup = [t["launch_to_hello_seconds"] for r in runs for t in r.get("operator_timings", [])]
    lifetimes = [t["lifetime_seconds"] for r in runs for t in r.get("operator_timings", [])]
    resources = summary["resources"]
    changes = {k: summary["host_after"][k] - summary["host_before"][k]
               for k in ("swap_in_pages", "swap_out_pages", "oom_kill")}
    identities = [tuple(sorted(t["operator_process_identity"].items())) for r in runs
                  for t in r.get("operator_timings", []) if "operator_process_identity" in t]
    return {"directory": str(directory), "source_sha": manifest["git_head"], "workers": summary["workers"],
            "n": len(runs), "valid": valid, "elapsed_seconds": summary["elapsed_seconds"],
            "elapsed_includes_manifest_preflight": summary.get("elapsed_includes_manifest_preflight", False),
            "valid_campaigns_per_hour": valid * 3600 / summary["elapsed_seconds"], "arm_seconds": arm_times,
            "parent_launch_to_python_hello_seconds": stats(startup), "universe_lifetime_seconds": stats(lifetimes),
            "parent_arrival_phase_durations_untrusted_labels": phase_durations(runs), "resources": resources,
            "cpu": summary["cpu"], "child_cpu_core_equivalents":
                (summary["cpu"]["cpu_user_seconds"] + summary["cpu"]["cpu_system_seconds"]) / summary["elapsed_seconds"],
            "memory_pressure_changes": changes, "host_before": summary["host_before"],
            "recorded_process_identities": len(identities), "distinct_process_identities": len(set(identities)),
            "host_after": summary["host_after"], "comparison": comparison(reference, runs),
            "runs_sha256": summary["runs_sha256"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline")
    parser.add_argument("directories", nargs="+")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    reference = read(args.baseline)[0]
    result = {"purpose": "PUBLIC DEVELOPMENT SOFTWARE CONTROL; no scientific validation/certification",
              "baseline": args.baseline, "rows": [summarize(path, reference) for path in args.directories]}
    pathlib.Path(args.out).write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"out": args.out, "rows": len(result["rows"])}))


if __name__ == "__main__":
    main()
