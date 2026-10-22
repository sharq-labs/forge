"""Comparability classes, baseline deltas and the versioned performance policy.

A percentage is only ever reported next to the class that makes it meaningful. Deltas exist for
EXACT_COMPARABLE pairs (a benchmark comparison) and for CODE_VARIANT pairs (the same workload on the
same machine, on different code -- how a regression across commits is seen); for every other class
there are no deltas and the performance reading is NOT_COMPARABLE. Performance and result are read
separately: a faster run that newly fails is PERFORMANCE_IMPROVED *and* result CHANGED.
"""

from __future__ import annotations

import copy

#: The default developer policy, versioned. It sits above measured noise: identical warm FAST runs
#: have differed by up to x1.25 in whole-run wall time on one machine (docs/TESTING.md), so a
#: smaller threshold would flag noise. A change is flagged only when it clears BOTH bars.
DEFAULT_POLICY = {
    "policy_id": "forge.run_observatory.performance_policy",
    "version": 1,
    "metric": "wall_seconds",
    "regression_threshold_pct": 25.0,
    "improvement_threshold_pct": 25.0,
    "min_absolute_seconds": 1.0,
    "basis": "docs/TESTING.md: identical warm FAST runs differed by up to x1.25 in whole-run wall time",
    "overrides": [],
}
_TUNABLE = ("regression_threshold_pct", "improvement_threshold_pct", "min_absolute_seconds")

DELTA_COMPARABLE = ("EXACT_COMPARABLE", "CODE_VARIANT")
_RESOURCE_DELTAS = ("cpu_seconds", "peak_rss_bytes", "io_read_bytes", "io_write_bytes")


def make_policy(base: dict | None = None, **overrides: float) -> dict:
    """The default policy with declared overrides; the receipt records which were overridden."""
    policy = copy.deepcopy(base or DEFAULT_POLICY)
    for key, value in overrides.items():
        if key not in _TUNABLE:
            raise ValueError(f"unknown performance policy setting {key!r}; tunable: {', '.join(_TUNABLE)}")
        if value is None:
            continue
        if float(value) < 0:
            raise ValueError(f"{key} must be non-negative")
        policy[key] = float(value)
        policy["overrides"] = sorted(set(policy.get("overrides", [])) | {key})
    return policy


def classify(candidate: dict, baseline: dict) -> tuple[str, list[str]]:
    """The comparability class of a pair, and every axis on which they differ."""
    if candidate.get("partial") or baseline.get("partial"):
        return "NOT_COMPARABLE", ["partial_run"]
    cw, bw = candidate.get("workload") or {}, baseline.get("workload") or {}
    if not cw.get("workload_id") or not bw.get("workload_id"):
        return "NOT_COMPARABLE", ["workload_unknown"]
    cc, bc = cw.get("components") or {}, bw.get("components") or {}
    differences = [f"workload.{name}" for name in ("command", "inputs", "declared") if cc.get(name) != bc.get(name)]
    if cc.get("config") != bc.get("config"):
        differences.append("workload.config")
    if (candidate.get("environment") or {}).get("environment_id") != (baseline.get("environment") or {}).get(
            "environment_id"):
        differences.append("environment")
    c_code, b_code = (candidate.get("git") or {}).get("code_identity"), (baseline.get("git") or {}).get("code_identity")
    code_unknown = c_code is None or b_code is None
    if not code_unknown and c_code != b_code:
        differences.append("code")
    if code_unknown:
        differences.append("code_unknown")

    if any(d in differences for d in ("workload.command", "workload.inputs", "workload.declared")):
        return "WORKLOAD_VARIANT", differences
    if cw.get("workload_id") != bw.get("workload_id") or "workload.config" in differences:
        return ("CONFIG_VARIANT" if "workload.config" in differences else "WORKLOAD_VARIANT"), differences
    if code_unknown:
        return "NOT_COMPARABLE", differences
    if "environment" in differences:
        return "ENVIRONMENT_VARIANT", differences
    if "code" in differences:
        return "CODE_VARIANT", differences
    return "EXACT_COMPARABLE", differences


def _delta(base, cand, comparability: str) -> dict:
    out = {"baseline": base, "candidate": cand, "delta": None, "pct": None, "comparability": comparability}
    if base is not None and cand is not None:
        out["delta"] = cand - base
        out["pct"] = (cand - base) / base * 100.0 if base else None
    return out


def _value(rec: dict, name: str):
    return ((rec.get("resources") or {}).get(name) or {}).get("value")


def _performance(wall: dict | None, policy: dict) -> str:
    if wall is None or wall["delta"] is None:
        return "NOT_COMPARABLE"
    if abs(wall["delta"]) < policy["min_absolute_seconds"] or wall["pct"] is None:
        return "UNCHANGED"
    if wall["pct"] >= policy["regression_threshold_pct"]:
        return "PERFORMANCE_REGRESSION"
    if wall["pct"] <= -policy["improvement_threshold_pct"]:
        return "PERFORMANCE_IMPROVED"
    return "UNCHANGED"


def _result_delta(candidate: dict, baseline: dict) -> tuple[str, dict]:
    cr, br = candidate.get("result") or {}, baseline.get("result") or {}
    keys = ("passed", "failed", "errors", "skipped", "xfailed")
    co, bo = cr.get("adapter_outcomes") or {}, br.get("adapter_outcomes") or {}
    same = cr.get("status") == br.get("status") and cr.get("exit_code") == br.get("exit_code")
    if co and bo:
        same = same and all(co.get(k) == bo.get(k) for k in keys)
    detail = {"baseline": {"status": br.get("status"), "exit_code": br.get("exit_code")},
              "candidate": {"status": cr.get("status"), "exit_code": cr.get("exit_code")}}
    return ("UNCHANGED" if same else "CHANGED"), detail


def _failure_sets(candidate: dict, baseline: dict, comparability: str) -> dict:
    co = (candidate.get("result") or {}).get("adapter_outcomes") or {}
    bo = (baseline.get("result") or {}).get("adapter_outcomes") or {}
    if comparability not in DELTA_COMPARABLE or "failure_set" not in co or "failure_set" not in bo:
        return {"failure_set": "NOT_CHECKED", "new_failures": None, "resolved_failures": None}
    new = sorted(set(co["failure_set"]) - set(bo["failure_set"]))
    resolved = sorted(set(bo["failure_set"]) - set(co["failure_set"]))
    return {"failure_set": "NEW_FAILURES" if new else "NO_NEW_FAILURES", "new_failures": new,
            "resolved_failures": resolved}


def compare(candidate: dict, baseline: dict, policy: dict | None = None) -> dict:
    policy = policy or DEFAULT_POLICY
    comparability, differences = classify(candidate, baseline)
    deltas = None
    if comparability in DELTA_COMPARABLE:
        deltas = {"wall_seconds": _delta((baseline.get("timing") or {}).get("wall_seconds"),
                                         (candidate.get("timing") or {}).get("wall_seconds"), comparability)}
        for name in _RESOURCE_DELTAS:
            deltas[name] = _delta(_value(baseline, name), _value(candidate, name), comparability)
        c_derived = (candidate.get("counters") or {}).get("derived") or {}
        b_derived = (baseline.get("counters") or {}).get("derived") or {}
        for name in sorted(set(c_derived) & set(b_derived)):
            deltas[name] = _delta(b_derived[name].get("value"), c_derived[name].get("value"), comparability)
    result_delta, result_detail = _result_delta(candidate, baseline)
    return {
        "baseline_run_id": baseline.get("run_id"),
        "comparability": comparability,
        "differences": differences,
        "benchmark_speedup": comparability == "EXACT_COMPARABLE",
        "deltas": deltas,
        "performance": _performance(deltas["wall_seconds"] if deltas else None, policy),
        "policy": policy,
        "result_delta": result_delta,
        "result": result_detail,
        **_failure_sets(candidate, baseline, comparability),
    }


def no_baseline(policy: dict | None, reason: str) -> dict:
    return {"baseline_run_id": None, "comparability": "NOT_COMPARABLE", "differences": [reason],
            "benchmark_speedup": False, "deltas": None, "performance": "NOT_COMPARABLE",
            "policy": policy or DEFAULT_POLICY, "result_delta": "NOT_CHECKED", "result": None,
            "failure_set": "NOT_CHECKED", "new_failures": None, "resolved_failures": None}
