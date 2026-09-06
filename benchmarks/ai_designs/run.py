"""Run labelled designs through engcore and score the result honestly.

    python benchmarks/ai_designs/run.py --src src \
        --designs benchmarks/ai_designs/designs \
        --results benchmarks/ai_designs/results_ai_designs.json

What it does, in order
----------------------
1. Reads every labelled design. **A design with no label is skipped and
   counted**, because a label written after seeing the tool's answer is not a
   label, and the only way to enforce that here is to refuse to score what has
   not already been decided.
2. Converts each one under all three policies from ``convert.py``, logging every
   value the conversion had to supply.
3. Runs the convertible ones and records the verdict, the violated conditions
   and the unknown conditions per model.
4. Scores, and reports where the score comes from.

Two verdicts per run, and why
------------------------------
``whole_report`` is the verdict engcore returns for the report as a whole, and
is the number directly comparable with ``benchmarks/hard/score_hard.py``.

``violation_scoped`` collapses a report to NOT_SUPPORTED if any model reports a
violation, SUPPORTED if every model is in domain, and INSUFFICIENT_EVIDENCE
otherwise. It exists for the same reason ``score_hard.py`` scopes its battery
cases: **a design that never declares an emissivity leaves that condition
UNKNOWN, so a whole-report score over such designs measures one gap N times and
nothing else.** The frozen benchmark's README calls this the unearned catch
rate; scoping is how the two numbers are kept apart instead of one hiding
behind the other.

Both are reported. Neither is presented as the headline alone.

The check that keeps the scope honest
--------------------------------------
For every case scored as caught, ``verdict_rests_on_invention`` asks whether the
violated conditions were fed by a value nobody declared. A refusal decided by
the converter's own invention is a refusal of the converter. Those cases are
counted separately and named in the results file.
"""

from __future__ import annotations

import argparse
import collections
import datetime
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import convert as conv  # noqa: E402

#: label.verdict -> what a correct tool should return. Stated in
#: label_template.md as a claim rather than a definition.
EXPECTED = {
    "physically_sound": "SUPPORTED",
    "model_inapplicable": "NOT_SUPPORTED",
    "limit_exceeded": "NOT_SUPPORTED",
    "unit_or_sign_error": "NOT_SUPPORTED",
    "inconsistent_inputs": "NOT_SUPPORTED",
    "insufficient_input": "INSUFFICIENT_EVIDENCE",
}

#: Exceptions that mean the payload was refused at the boundary rather than
#: assessed. Same set the frozen scorer uses, so the two are comparable.
BOUNDARY = {
    "MissingUnitError", "WrongDimensionError", "UnknownFieldError",
    "MissingFieldError", "MalformedPayloadError", "InvalidScientificProblem",
    "ScientificValidationError",
}


def whole_report_verdict(run) -> str:
    verdicts = {r.verdict.value.upper() for r in run.reports}
    for v in ("NOT_SUPPORTED", "INSUFFICIENT_EVIDENCE", "SUPPORTED"):
        if v in verdicts:
            return v
    return "NO_REPORT"


def scope_report(run) -> tuple[str, list[str], list[str]]:
    """Violation-scoped verdict, plus the conditions behind it."""
    violated: list[str] = []
    unknown: list[str] = []
    for report in run.reports:
        for record in report.validity:
            violated += [f"{record.model_id}:{c}" for c in record.assessment.violated]
            unknown += [f"{record.model_id}:{c}" for c in record.assessment.unknown]
    if violated:
        return "NOT_SUPPORTED", violated, unknown
    if unknown:
        return "INSUFFICIENT_EVIDENCE", violated, unknown
    return "SUPPORTED", violated, unknown


def load_designs(directory: pathlib.Path) -> tuple[list[dict], list[str]]:
    designs, unlabelled = [], []
    for path in sorted(directory.glob("**/*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        label = doc.get("label", {}).get("verdict")
        if label not in EXPECTED:
            unlabelled.append(doc.get("id", path.name))
            continue
        designs.append(doc)
    return designs, unlabelled


def score_one(design: dict, components: dict, policy: str, runner) -> dict:
    conversion = conv.convert(design, components, policy)
    label = design["label"]["verdict"]
    row = {
        "id": design["id"],
        "prompt_id": design.get("prompt_id"),
        "source_kind": design.get("source", {}).get("kind"),
        "label": label,
        "expected": EXPECTED[label],
        "policy": policy,
        "conversion_notes": conversion.notes,
        "value_classes_used": sorted(conversion.classes_used()),
        "invented_fields": sorted(conversion.invented_fields()),
    }
    if not conversion.ok:
        row.update({
            "outcome": "unconvertible",
            "whole_report": "UNCONVERTIBLE",
            "violation_scoped": "UNCONVERTIBLE",
            "unconvertible_because": conversion.unconvertible_because,
        })
        return row
    try:
        run = runner(conversion.payload)
    except Exception as exc:                      # noqa: BLE001 - reported, not raised
        name = type(exc).__name__
        row.update({
            "outcome": ("rejected_at_boundary" if name in BOUNDARY
                        else f"exception:{name}"),
            "whole_report": ("REJECTED_AT_BOUNDARY" if name in BOUNDARY
                             else f"ERROR:{name}"),
            "violation_scoped": ("REJECTED_AT_BOUNDARY" if name in BOUNDARY
                                 else f"ERROR:{name}"),
            "detail": str(exc)[:200],
        })
        return row

    scoped, violated, unknown = scope_report(run)
    bare = [v.split(":", 1)[1] for v in violated]
    row.update({
        "outcome": "ran",
        "whole_report": whole_report_verdict(run),
        "violation_scoped": scoped,
        "violated": violated,
        "unknown_count": len(unknown),
        "unknown": sorted(set(unknown))[:20],
        "violations_fed_by_an_invented_value":
            conv.verdict_rests_on_invention(conversion, bare),
    })
    return row


def summarise(rows: list[dict], key: str) -> dict:
    """Catch rate, false accept, false reject and the per-class breakdown.

    Same shape as ``benchmarks/hard/score_hard.py`` so the two can be read side
    by side. ``unconvertible`` cases are excluded from the rates and reported as
    their own count -- folding them into either numerator would be scoring a
    design the harness never posed.
    """
    scored = [r for r in rows if r["outcome"] != "unconvertible"]
    unconvertible = [r for r in rows if r["outcome"] == "unconvertible"]
    sound = [r for r in scored if r["label"] == "physically_sound"]
    unsound = [r for r in scored if r["label"] != "physically_sound"]

    caught = [r for r in unsound if r[key] == "NOT_SUPPORTED"]
    false_accept = [r for r in unsound if r[key] == "SUPPORTED"]
    false_reject = [r for r in sound if r[key] != "SUPPORTED"]
    exact = [r for r in scored if r[key] == r["expected"]]

    by_class: dict[str, dict] = {}
    for r in scored:
        d = by_class.setdefault(
            r["label"], {"n": 0, "caught": 0, "accepted": 0,
                         "insufficient": 0, "exact": 0,
                         "decided_by_an_invented_value": 0}
        )
        d["n"] += 1
        if r[key] == "NOT_SUPPORTED":
            d["caught"] += 1
        elif r[key] == "SUPPORTED":
            d["accepted"] += 1
        elif r[key] == "INSUFFICIENT_EVIDENCE":
            d["insufficient"] += 1
        if r[key] == r["expected"]:
            d["exact"] += 1
        if r.get("violations_fed_by_an_invented_value"):
            d["decided_by_an_invented_value"] += 1

    def pct(a, b):
        return f"{a}/{b} ({a / b:.1%})" if b else f"{a}/0 (n/a)"

    return {
        "scored_on": key,
        "total": len(rows),
        "unconvertible": len(unconvertible),
        "unconvertible_ids": [r["id"] for r in unconvertible][:40],
        "scored": len(scored),
        "sound": len(sound),
        "unsound": len(unsound),
        "exact_verdict_match": pct(len(exact), len(scored)),
        "catch_rate": pct(len(caught), len(unsound)),
        "false_accept": pct(len(false_accept), len(unsound)),
        "false_reject": pct(len(false_reject), len(sound)),
        "false_accept_ids": [r["id"] for r in false_accept][:40],
        "false_reject_ids": [r["id"] for r in false_reject][:40],
        "caught_but_decided_by_an_invented_value":
            sum(1 for r in caught if r.get("violations_fed_by_an_invented_value")),
        "by_failure_class": by_class,
        "top_violated_conditions": collections.Counter(
            c for r in scored for c in r.get("violated", [])
        ).most_common(12),
        "outcomes": dict(collections.Counter(r["outcome"] for r in rows)),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", required=True)
    ap.add_argument("--designs", default=str(HERE / "designs"))
    ap.add_argument("--components", default=str(HERE / "components.json"))
    ap.add_argument("--results", default=str(HERE / "results_ai_designs.json"))
    ap.add_argument("--policy", action="append", choices=list(conv.POLICIES),
                    help="repeatable; default is all three")
    args = ap.parse_args()

    sys.path.insert(0, args.src)
    from engcore.mcp.problem import run_electrothermal_case

    components = conv.load_components(args.components)
    designs, unlabelled = load_designs(pathlib.Path(args.designs))
    policies = args.policy or list(conv.POLICIES)

    out = {
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "designs_read": len(designs) + len(unlabelled),
        "designs_scored": len(designs),
        "skipped_unlabelled": unlabelled,
        "sources": dict(collections.Counter(
            d.get("source", {}).get("kind") for d in designs
        )),
        "policies": {},
    }
    for policy in policies:
        rows = [score_one(d, components, policy, run_electrothermal_case)
                for d in designs]
        out["policies"][policy] = {
            "whole_report": summarise(rows, "whole_report"),
            "violation_scoped": summarise(rows, "violation_scoped"),
            "rows": rows,
        }

    pathlib.Path(args.results).write_text(
        json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    for policy in policies:
        print(f"\n===== policy: {policy} =====")
        for scope in ("whole_report", "violation_scoped"):
            s = dict(out["policies"][policy][scope])
            s.pop("by_failure_class", None)
            s.pop("top_violated_conditions", None)
            print(json.dumps(s, indent=2, ensure_ascii=False))
    print(f"\nwrote {args.results}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
