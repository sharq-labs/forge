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
import re
import statistics
from collections import Counter


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
    if len(runs) != summary.get("records", summary["completed"]) or manifest["dirty"]:
        raise ValueError(f"incomplete or dirty run: {directory}")
    return runs, summary, manifest


def key(run):
    return (run["arm"], run.get("seed", run.get("index")), run.get("campaign_id"))


def semantics(run):
    if "runtime_diagnostic" in run:
        if run["status"] != "PUBLIC_FIT_COMPLETED" or not run["runtime_diagnostic"]["equations"]:
            raise ValueError("incomplete public fit")
        return {"status": run["status"], "equations": run["runtime_diagnostic"]["equations"]}
    if run["status"] != "VALID":
        raise ValueError("non-VALID campaign cannot establish complete equivalence")
    fields = ("status", "reasons", "observe_calls", "universes", "key_digest", "presented_card_digests",
              "leakage_audit", "evaluator_status", "v3_total_credit", "config_digest", "escrow_rule",
              "proposer_kind", "budget_fraction", "library_versions")
    result = {field: run[field] for field in fields}
    expected = [u["universe_id"] for u in run["universes"]]
    timings = run["operator_timings"]
    seen = [t["universe_id"] for t in timings]
    if len(expected) != 6 or len(set(expected)) != 6 or sorted(seen) != sorted(expected):
        raise ValueError("missing or duplicate universe trace evidence")
    traces = []
    for timing in timings:
        query = timing["query_trace_without_transport_nonce_sha256"]
        if not isinstance(query, str) or not re.fullmatch("[0-9a-f]{64}", query):
            raise ValueError("missing/invalid query trace hash")
        proposal, failure = timing.get("proposal_sha256"), timing.get("proposer_failure")
        if proposal is not None:
            if failure is not None or not isinstance(proposal, str) or not re.fullmatch("[0-9a-f]{64}", proposal):
                raise ValueError("ambiguous/invalid proposal evidence")
        elif not (isinstance(failure, dict) and set(failure) == {"exception_type", "message"}
                  and all(isinstance(value, str) and value for value in failure.values())):
            raise ValueError("missing proposal/failure evidence")
        traces.append({"universe_id": timing["universe_id"], "query_sha256": query,
                       "proposal_sha256": proposal, "failure": failure})
    result["traces"] = sorted(traces, key=lambda t: t["universe_id"])
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
    def unique(records):
        indexed = {}
        for record in records:
            if key(record) in indexed:
                raise ValueError(f"duplicate comparison task: {key(record)}")
            indexed[key(record)] = record
        return indexed
    base, candidate = unique(reference), unique(runs)
    missing = sorted(set(base) - set(candidate))
    extra = sorted(set(candidate) - set(base))
    mismatches, incomplete, matched, ratios, clusters = [], [], 0, [], {}
    for run in runs:
        previous = base.get(key(run))
        if previous is None:
            continue
        if previous["status"] != run["status"]:
            mismatches.append({"key": key(run), "fields": ["status"]})
            continue
        try:
            before, after = semantics(previous), semantics(run)
        except (KeyError, ValueError, TypeError) as exc:
            incomplete.append({"key": key(run), "reason": str(exc)})
            continue
        different = [field for field in before if before[field] != after[field]]
        if different:
            mismatches.append({"key": key(run), "fields": different})
            continue
        matched += 1
        if "campaign_total_seconds" in run and "campaign_total_seconds" in previous:
            ratio = previous["campaign_total_seconds"] / run["campaign_total_seconds"]
            ratios.append(ratio)
            clusters.setdefault((run["seed"], run["campaign_id"]), []).append(ratio)
    interval = None
    if len(clusters) >= 3:
        rng = random.Random(20261031)
        groups = list(clusters.values())
        means = [statistics.mean([x for group in rng.choices(groups, k=len(groups)) for x in group])
                 for _ in range(10000)]
        interval = [quantile(means, .025), quantile(means, .975)]
    status = "FAIL" if mismatches else "UNKNOWN" if not matched or missing or extra or incomplete else "PASS"
    return {"equivalence_status": status, "exact_matching_campaigns": matched, "mismatches": mismatches,
            "incomplete_evidence": incomplete, "missing_reference_tasks": missing, "extra_candidate_tasks": extra,
            "paired_service_speedup": stats(ratios), "paired_bootstrap_95_percentile": interval,
            "bootstrap_clusters": len(clusters),
            "interval_scope": "clustered by public seed/world set; service-time sample only, not full-grid uncertainty"}


def summarize(directory, reference):
    runs, summary, manifest = read(directory)
    valid = sum(run["status"] == "VALID" for run in runs)
    arm_times = {arm: stats([r["campaign_total_seconds"] for r in runs if r["arm"] == arm and
                            "campaign_total_seconds" in r]) for arm in sorted({r["arm"] for r in runs})}
    startup = [t["launch_to_hello_seconds"] for r in runs for t in r.get("operator_timings", [])]
    lifetimes = [t["lifetime_seconds"] for r in runs for t in r.get("operator_timings", [])]
    resources, cpu = summary.get("resources"), summary.get("cpu")
    host_before, host_after = summary.get("host_before"), summary.get("host_after")
    changes = ({k: host_after[k] - host_before[k] for k in ("swap_in_pages", "swap_out_pages", "oom_kill")}
               if host_before is not None and host_after is not None else None)
    identities = [tuple(sorted(t["operator_process_identity"].items())) for r in runs
                  for t in r.get("operator_timings", []) if "operator_process_identity" in t]
    return {"directory": str(directory), "source_sha": manifest["git_head"], "workers": summary["workers"],
            "n": len(runs), "valid": valid, "elapsed_seconds": summary["elapsed_seconds"],
            "status_counts": dict(Counter(r["status"] for r in runs)),
            "failures": [{"key": key(r), "status": r["status"], "reasons": r.get("reasons", [])}
                         for r in runs if r["status"] not in ("VALID", "PUBLIC_FIT_COMPLETED")],
            "elapsed_includes_manifest_preflight": summary.get("elapsed_includes_manifest_preflight", False),
            "valid_campaigns_per_hour": (valid * 3600 / summary["elapsed_seconds"]
                                         if manifest["arguments"].get("mode") == "campaign" else None), "arm_seconds": arm_times,
            "parent_launch_to_python_hello_seconds": stats(startup), "universe_lifetime_seconds": stats(lifetimes),
            "parent_arrival_phase_durations_untrusted_labels": phase_durations(runs), "resources": resources,
            "cpu": cpu, "child_cpu_core_equivalents":
                ((cpu["cpu_user_seconds"] + cpu["cpu_system_seconds"]) / summary["elapsed_seconds"] if cpu else None),
            "memory_pressure_changes": changes, "host_before": host_before,
            "recorded_process_identities": len(identities), "distinct_process_identities": len(set(identities)),
            "host_after": host_after, "comparison": comparison(reference, runs),
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
