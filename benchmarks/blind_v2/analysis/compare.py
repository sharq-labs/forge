"""Compare the frozen independent truth to what the certified Core said.

Reads the sealed run and the frozen truth. Writes a comparison. It changes
neither, and it applies only the scoring rules registered in
CHALLENGE_SPEC.json before the corpus existed:

* **exact verdict** -- the Core's outcome is the one truth recorded;
* **acceptable verdict** -- the Core's outcome is in the set truth recorded as
  acceptable. That set is larger than one only where the challenge said before
  the run that it would be: a physically invalid but dimensionally legal
  declaration may be refused at construction or caught as a condition, and
  both are refusals;
* **safety** -- accept versus refuse, which is the axis a false accept lives
  on and the only one that can fail the gate on its own.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import statistics

BLIND = pathlib.Path(__file__).resolve().parent.parent

REFUSALS = {"NOT_SUPPORTED", "INSUFFICIENT_EVIDENCE", "REJECTED_AT_BOUNDARY"}


def load_jsonl(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def safety_cell(truth_outcome: str, forge_outcome: str, kind: str) -> str:
    if kind == "runner_error":
        return "RUNNER_ERROR"
    if forge_outcome == "CORE_ERROR":
        return "CORE_ERROR"
    truth_accepts = truth_outcome == "SUPPORTED"
    forge_accepts = forge_outcome == "SUPPORTED"
    if truth_accepts and forge_accepts:
        return "TRUE_ACCEPT"
    if not truth_accepts and forge_accepts:
        return "FALSE_ACCEPT"
    if not truth_accepts and not forge_accepts:
        return "TRUE_REJECT"
    return "FALSE_REJECT"


def reason_verdict(truth_record: dict, forge: dict) -> str:
    """How well the Core's mechanism set matches the independent one."""
    if truth_record["outcome"] == "SUPPORTED":
        return "NOT_APPLICABLE"
    if truth_record["reason_status"] == "CONTRACT_REFUSAL":
        return "NOT_APPLICABLE"
    if forge.get("outcome_kind") != "forge_verdict":
        return "NOT_APPLICABLE"
    expected = set(truth_record["valid_mechanisms"])
    got = set(forge.get("violated") or []) or set(forge.get("unknown") or [])
    if not expected:
        return "NOT_APPLICABLE"
    if got == expected:
        return "EXACT_REASON"
    if not got:
        return "MISSING_CAUSAL_REASON"
    if got & expected:
        if expected < got:
            return "VALID_BUT_REDUNDANT"
        if got < expected:
            return "VALID_ALTERNATE_REASON"
        return "VALID_ALTERNATE_REASON"
    return "WRONG_MECHANISM"


def causal_verdict(truth_record: dict, forge: dict) -> str:
    causal = truth_record["causal"]
    if causal["class"] in ("NOT_APPLICABLE", "UNRESOLVED"):
        return "NOT_APPLICABLE"
    if forge.get("outcome_kind") != "forge_verdict":
        return "NOT_APPLICABLE"
    catchers = set(causal["catchers"])
    got = set(forge.get("violated") or []) or set(forge.get("unknown") or [])
    if causal["class"] == "NO_UNIQUE_PRIMARY":
        return "NO_UNIQUE_PRIMARY"
    if not catchers:
        return "NOT_APPLICABLE"
    if catchers == got:
        return "EXACT_CAUSAL_MATCH"
    if catchers <= got:
        return "VALID_CAUSAL_PLUS_REDUNDANT"
    if got & catchers:
        return "MISSING_CAUSAL_MECHANISM"
    return "WRONG_CAUSAL_MECHANISM"


def compare(run_path: pathlib.Path, truth_path: pathlib.Path, cases_path: pathlib.Path) -> dict:
    run = json.loads(run_path.read_text(encoding="utf-8"))
    truth = {t["case_id"]: t for t in load_jsonl(truth_path)}
    cases = {c["case_id"]: c for c in load_jsonl(cases_path)}
    rows = []
    for record in run["records"]:
        case_id = record["case_id"]
        truth_record = truth[case_id]
        case = cases[case_id]
        forge_outcome = record.get("forge_outcome", "CORE_ERROR")
        rows.append(
            {
                "case_id": case_id,
                "system": record["system"],
                "family": case["family"],
                "truth_outcome": truth_record["outcome"],
                "acceptable": truth_record["acceptable_outcomes"],
                "forge_outcome": forge_outcome,
                "outcome_kind": record["outcome_kind"],
                "exact": forge_outcome == truth_record["outcome"],
                "acceptable_match": forge_outcome in truth_record["acceptable_outcomes"],
                "safety": safety_cell(truth_record["outcome"], forge_outcome, record["outcome_kind"]),
                "truth_class": truth_record["truth_class"],
                "dual_oracle": truth_record["oracle"]["dual_oracle"],
                "independence_level": truth_record["oracle"]["independence_level"],
                "worst_route_gap": truth_record["oracle"]["worst_route_gap"],
                "precedence_dependent": truth_record["precedence_dependent"],
                "channel_ambiguous": truth_record["channel_ambiguous"],
                "boundary_kind": truth_record["boundary"]["kind"],
                "reason": reason_verdict(truth_record, record),
                "causal": causal_verdict(truth_record, record),
                "truth_mechanisms": truth_record["valid_mechanisms"],
                "forge_violated": record.get("violated"),
                "forge_unknown": record.get("unknown"),
                "exception_type": record.get("exception_type"),
                "detail": record.get("detail"),
                "runtime_s": record.get("runtime_s"),
                "refusal_stage_truth": truth_record["refusal_stage"],
                "refusal_stage_forge": record.get("refusal_stage"),
            }
        )
    return {"run": run_path.name, "rows": rows}


def summarise(rows: list[dict]) -> dict:
    def bucket(key):
        return dict(sorted(collections.Counter(r[key] for r in rows).items()))

    decided = [r for r in rows if r["truth_outcome"] != "REJECTED_AT_BOUNDARY"]
    per_system: dict[str, dict] = {}
    for system in sorted({r["system"] for r in rows}):
        subset = [r for r in rows if r["system"] == system]
        sub_decided = [r for r in subset if r["truth_outcome"] != "REJECTED_AT_BOUNDARY"]
        per_system[system] = {
            "cases": len(subset),
            "decided": len(sub_decided),
            "exact": sum(1 for r in subset if r["exact"]),
            "acceptable": sum(1 for r in subset if r["acceptable_match"]),
            "false_accept": sum(1 for r in subset if r["safety"] == "FALSE_ACCEPT"),
            "false_reject": sum(1 for r in subset if r["safety"] == "FALSE_REJECT"),
            "core_error": sum(1 for r in subset if r["safety"] == "CORE_ERROR"),
            "insufficient_disagreement": sum(
                1
                for r in subset
                if r["truth_outcome"] == "INSUFFICIENT_EVIDENCE" and not r["exact"]
            ),
            "boundary_disagreement": sum(
                1
                for r in subset
                if r["truth_outcome"] == "REJECTED_AT_BOUNDARY" and not r["acceptable_match"]
            ),
            "reason": dict(sorted(collections.Counter(r["reason"] for r in subset).items())),
            "causal": dict(sorted(collections.Counter(r["causal"] for r in subset).items())),
        }

    per_class: dict[str, dict] = {}
    for klass in sorted({r["truth_class"] for r in rows}):
        subset = [r for r in rows if r["truth_class"] == klass]
        per_class[klass] = {
            "cases": len(subset),
            "exact": sum(1 for r in subset if r["exact"]),
            "acceptable": sum(1 for r in subset if r["acceptable_match"]),
            "false_accept": sum(1 for r in subset if r["safety"] == "FALSE_ACCEPT"),
            "false_reject": sum(1 for r in subset if r["safety"] == "FALSE_REJECT"),
        }

    dual = [r for r in rows if r["dual_oracle"]]
    gaps = [r["worst_route_gap"] for r in dual if r["worst_route_gap"] is not None]
    runtimes = sorted(r["runtime_s"] for r in rows if r["runtime_s"] is not None)

    def pct(values, fraction):
        if not values:
            return None
        index = min(len(values) - 1, int(round(fraction * (len(values) - 1))))
        return values[index]

    return {
        "total": len(rows),
        "decided_denominator": len(decided),
        "unresolved_truth": sum(1 for r in rows if r["truth_class"] == "UNRESOLVED"),
        "exact_verdict_agreement": sum(1 for r in rows if r["exact"]),
        "acceptable_verdict_agreement": sum(1 for r in rows if r["acceptable_match"]),
        "truth_outcomes": bucket("truth_outcome"),
        "forge_outcomes": bucket("forge_outcome"),
        "safety_matrix": bucket("safety"),
        "outcome_kinds": bucket("outcome_kind"),
        "families": bucket("family"),
        "per_system": per_system,
        "per_truth_class": per_class,
        "dual_oracle": {
            "cases": len(dual),
            "exact": sum(1 for r in dual if r["exact"]),
            "acceptable": sum(1 for r in dual if r["acceptable_match"]),
            "false_accept": sum(1 for r in dual if r["safety"] == "FALSE_ACCEPT"),
            "false_reject": sum(1 for r in dual if r["safety"] == "FALSE_REJECT"),
            "independence_levels": dict(
                sorted(collections.Counter(r["independence_level"] for r in dual).items())
            ),
            "mean_route_gap": statistics.fmean(gaps) if gaps else None,
            "worst_route_gap": max(gaps) if gaps else None,
        },
        "reason_audit": bucket("reason"),
        "causal_audit": bucket("causal"),
        "boundary_kinds": dict(
            sorted(collections.Counter(r["boundary_kind"] for r in rows if r["boundary_kind"]).items())
        ),
        "precedence_dependent": sum(1 for r in rows if r["precedence_dependent"]),
        "channel_ambiguous": sum(1 for r in rows if r["channel_ambiguous"]),
        "performance": {
            "median_s": statistics.median(runtimes) if runtimes else None,
            "p95_s": pct(runtimes, 0.95),
            "p99_s": pct(runtimes, 0.99),
            "worst_s": runtimes[-1] if runtimes else None,
        },
    }


def shadow_comparison(shadow_run: pathlib.Path, primary_run: pathlib.Path,
                      shadows_path: pathlib.Path) -> dict:
    """A shadow must agree with its parent, unless it declared it would not."""
    parent = {
        r["case_id"]: r
        for r in json.loads(primary_run.read_text(encoding="utf-8"))["records"]
    }
    shadow_records = {s["shadow_id"]: s for s in load_jsonl(shadows_path)}
    rows = []
    for record in json.loads(shadow_run.read_text(encoding="utf-8"))["records"]:
        shadow = shadow_records[record["case_id"]]
        parent_record = parent[shadow["parent_case_id"]]
        same = record.get("forge_outcome") == parent_record.get("forge_outcome")
        same_mechanisms = sorted(record.get("violated") or []) == sorted(
            parent_record.get("violated") or []
        ) and sorted(record.get("unknown") or []) == sorted(
            parent_record.get("unknown") or []
        )
        rows.append(
            {
                "shadow_id": record["case_id"],
                "parent_case_id": shadow["parent_case_id"],
                "system": shadow["system"],
                "transformation": shadow["transformation"],
                "semantics_preserving": shadow["semantics_preserving"],
                "parent_outcome": parent_record.get("forge_outcome"),
                "shadow_outcome": record.get("forge_outcome"),
                "same_outcome": same,
                "same_mechanisms": same_mechanisms,
                "violation": shadow["semantics_preserving"] and not same,
                "mechanism_drift": shadow["semantics_preserving"] and same and not same_mechanisms,
                "detail": record.get("detail"),
                "exception_type": record.get("exception_type"),
            }
        )
    per_transformation = {}
    for name in sorted({r["transformation"] for r in rows}):
        subset = [r for r in rows if r["transformation"] == name]
        per_transformation[name] = {
            "pairs": len(subset),
            "same_semantic_outcome": sum(1 for r in subset if r["same_outcome"]),
            "different_semantic_outcome": sum(1 for r in subset if not r["same_outcome"]),
            "justified_differences": sum(
                1 for r in subset if not r["semantics_preserving"] and not r["same_outcome"]
            ),
            "unjustified_violations": sum(1 for r in subset if r["violation"]),
            "mechanism_drift": sum(1 for r in subset if r["mechanism_drift"]),
        }
    return {"rows": rows, "per_transformation": per_transformation}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="FIRST_RUN")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    runs = BLIND / "runs"
    primary = compare(
        runs / f"{args.label}_primary.json",
        BLIND / "truth" / "truth.jsonl",
        BLIND / "cases" / "primary.jsonl",
    )
    summary = summarise(primary["rows"])
    shadows = shadow_comparison(
        runs / f"{args.label}_shadows.json",
        runs / f"{args.label}_primary.json",
        BLIND / "cases" / "shadows.jsonl",
    )
    payload = {
        "schema": "blind_v2_comparison/1",
        "label": args.label,
        "summary": summary,
        "shadows": shadows["per_transformation"],
        "rows": primary["rows"],
        "shadow_rows": shadows["rows"],
    }
    pathlib.Path(args.out).write_text(
        json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=1))
    print("shadows:", json.dumps(shadows["per_transformation"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
