"""Evaluate DEV cases independently, then compare with stored truth and Forge.

The ORDER matters and is enforced by construction: `independent_truth.evaluate`
is called with the payload alone and its result is complete before anything
reads `ground_truth` or runs Forge. The comparison lives in a separate section
of the output from the truth itself, so a reader cannot mistake one for the
other.

HOLD-OUT FIREWALL: reads `split_hard.json["dev"]` and touches nothing else.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from independent_truth import evaluate  # noqa: E402

BENCH = HERE.parent / "hard"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", required=True)
    parser.add_argument("--cases", default=str(BENCH / "cases_hard"))
    parser.add_argument("--out", required=True)
    parser.add_argument("--compare", action="store_true",
                        help="also run Forge and stored truth for comparison")
    args = parser.parse_args()

    split = json.loads((BENCH / "split_hard.json").read_text(encoding="utf-8"))
    dev = set(split["dev"])

    cases = {}
    for path in sorted(pathlib.Path(args.cases).glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        if case["id"] in dev:
            cases[case["id"]] = case

    # ---- STEP 1: independent truth, from payloads only ----------------
    truths = {}
    for case_id in sorted(cases):
        truths[case_id] = evaluate(
            case_id, cases[case_id]["payload"],
            cases[case_id].get("system", "electrothermal"),
        )

    truth_records = [truths[c].to_dict() for c in sorted(truths)]
    blob = json.dumps(truth_records, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()

    document = {
        "schema": "independent_case_truth/1",
        "truth_version": "2026-09-10.1",
        "split": "dev",
        "n_cases": len(truth_records),
        "truth_digest": digest,
        "note": (
            "Reconstructed from payloads alone by benchmarks/oracles/"
            "independent_truth.py, which imports nothing from engcore. No "
            "stored expected verdict, declared catcher or Forge result "
            "participated in producing anything in `truth`."
        ),
        "truth": truth_records,
    }

    # ---- STEP 2: comparison, in its own section -----------------------
    if args.compare:
        sys.path.insert(0, args.src)
        from engcore.mcp.problem import run_electrothermal_case

        comparison = []
        for case_id in sorted(cases):
            case = cases[case_id]
            stored = case["ground_truth"]["expected_verdict"]
            try:
                run = run_electrothermal_case(case["payload"], run_id=case_id)
                verdicts = {r.verdict.name for r in run.reports}
                actual = next(
                    (v for v in ("NOT_SUPPORTED", "INSUFFICIENT_EVIDENCE",
                                 "SUPPORTED") if v in verdicts),
                    "NO_REPORT",
                )
            except Exception as exc:      # noqa: BLE001 - recorded, not handled
                actual = f"ERROR:{type(exc).__name__}"

            independent = truths[case_id].independent_verdict
            resolvable = independent != "UNRESOLVED"
            if not resolvable:
                triage = "INDEPENDENT_UNRESOLVED"
            elif stored == independent == actual:
                triage = ("POLICY_DEPENDENT_AGREEMENT"
                          if truths[case_id].truth_class == "POLICY_DEPENDENT"
                          else "ALL_AGREE")
            elif independent == actual and stored != independent:
                triage = "STORED_TRUTH_DISAGREES"
            elif independent == stored and actual != independent:
                triage = "FORGE_DISAGREES"
            else:
                triage = "MIXED_AGREEMENT"

            comparison.append({
                "case_id": case_id,
                "defect": case["ground_truth"]["defect"],
                "stored": stored,
                "independent": independent,
                "forge": actual,
                "truth_class": truths[case_id].truth_class,
                "triage": triage,
            })
        document["comparison"] = comparison

    # write_bytes, not write_text: on Windows text mode translates every
    # newline to CRLF, which changes the file's bytes without changing its
    # content and makes the digest a property of the host.
    pathlib.Path(args.out).write_bytes(
        json.dumps(document, ensure_ascii=False, indent=1).encode("utf-8")
    )

    # ---- summary ------------------------------------------------------
    classes = collections.Counter(t["truth_class"] for t in truth_records)
    print(f"cases evaluated       : {len(truth_records)}")
    print(f"truth digest          : {digest}")
    print("truth classes:")
    for name, count in classes.most_common():
        print(f"    {name:<28}{count}")

    if args.compare:
        triage = collections.Counter(c["triage"] for c in document["comparison"])
        print("\ntriage:")
        for name, count in triage.most_common():
            print(f"    {name:<28}{count}")
        resolvable = [c for c in document["comparison"]
                      if c["independent"] != "UNRESOLVED"]
        if resolvable:
            stored_ok = sum(1 for c in resolvable if c["stored"] == c["independent"])
            forge_ok = sum(1 for c in resolvable if c["forge"] == c["independent"])
            print(f"\nindependently resolvable        : {len(resolvable)}"
                  f"/{len(document['comparison'])}")
            print(f"stored truth agrees             : {stored_ok}/{len(resolvable)}"
                  f" ({stored_ok / len(resolvable):.1%})")
            print(f"Forge agrees                    : {forge_ok}/{len(resolvable)}"
                  f" ({forge_ok / len(resolvable):.1%})")


if __name__ == "__main__":
    main()
