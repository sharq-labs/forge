"""Freeze independent reason/catcher truth, then compare it with intent and Forge.

The order is the method. Step 1 builds and digests the truth from payloads
alone. Steps 2 and 3 read benchmark intent and run Forge, and write their
findings into a SEPARATE section. Nothing in `truth` can have seen either.

HOLD-OUT FIREWALL: reads `split_hard.json["dev"]` only.
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

from independent_reason import analyse  # noqa: E402

BENCH = HERE.parent / "hard"

#: Forge and this analyser name exactly ONE mechanism differently. Forge's
#: `coupling_transfer_refused` check fails when the coupled transfer reached no
#: self-consistent operating point; this analyser's
#: `thermal_runaway_no_steady_state` asserts the loop has no steady state.
#: Those are the same proposition about the same fixed point.
#:
#: Every other name matches literally -- including
#: `declared_limits_are_mutually_consistent`, which Forge reports through the
#: validation-check channel rather than as a validity condition, and which an
#: earlier version of this script missed for exactly that reason.
#:
#: This table is the ONLY place a name difference is allowed to count as
#: agreement, so both a strict and a mechanism-level figure are reported below
#: and the difference between them is auditable.
MECHANISM_EQUIVALENCE = {
    "thermal_runaway_no_steady_state": frozenset({"coupling_transfer_refused"}),
}

#: The one benchmark intent written as prose instead of as a condition name.
#: Reading it is a COMPARISON step -- the truth section never reads intent --
#: and it lets the runaway cases be checked rather than dismissed as having no
#: machine-checkable intent.
INTENT_PROSE = {"thermal runaway": "thermal_runaway_no_steady_state"}


def _expand(fired):
    """Forge's fired names, plus this analyser's name for anything equivalent.

    The direction matters: the table is keyed by THIS analyser's name, so the
    lookup has to run from the values to the key, not the other way round.
    """
    out = set(fired)
    for name, equivalents in MECHANISM_EQUIVALENCE.items():
        if out & equivalents:
            out.add(name)
    return out


def _forge_fired(payload, case_id, runner):
    """What Forge's report actually says failed. Comparison only.

    Reads BOTH channels. A failing validation check is a mechanism as much as a
    violated validity condition is, and reading only the latter made fifteen
    `melt_below_ceiling` cases look as though Forge had found nothing when it
    had named the defect precisely.
    """
    try:
        run = runner(payload, run_id=case_id)
    except Exception as exc:            # noqa: BLE001 - recorded, not handled
        return {"error": type(exc).__name__}
    violated, unknown, checks = set(), set(), set()
    for report in run.reports:
        for record in report.validity:
            violated.update(record.assessment.violated)
            unknown.update(record.assessment.unknown)
        for check in report.validation:
            if check.outcome.value in ("fail", "not_run"):
                checks.add(check.name)
    verdicts = {r.verdict.name for r in run.reports}
    verdict = next(
        (v for v in ("NOT_SUPPORTED", "INSUFFICIENT_EVIDENCE", "SUPPORTED")
         if v in verdicts), "NO_REPORT",
    )
    return {
        "verdict": verdict,
        "violated": sorted(violated),
        "unknown": sorted(unknown),
        "failed_checks": sorted(checks),
    }


def _classify_forge(mine, fired, forge_verdict):
    """How Forge's reported mechanism stands to the causal one.

    The cascade separates "Forge named something other than the causal
    mechanism" from "there IS no unique causal mechanism". The first is a
    shortfall in Forge; the second is a property of the case, and charging
    Forge for it would be measuring the benchmark instead.
    """
    causal = set(mine["causal_catchers"])
    redundant = set(mine["redundant_catchers"])
    valid = set(mine["valid_reasons"])

    if not valid:
        return "NOT_APPLICABLE"
    if causal:
        if causal <= fired:
            return "EXACT_CAUSAL_MATCH"
        if causal & fired:
            return "PARTIAL_CAUSAL_MATCH"
        if (redundant | valid) & fired:
            # A causal mechanism existed and Forge reported a different, valid
            # one instead. This is the genuine shortfall case.
            return "VALID_BUT_REDUNDANT"
    else:
        if valid <= fired:
            return "ALL_VALID_REASONS_REPORTED"
        if valid & fired:
            return "VALID_SUBSET_REPORTED"
    if forge_verdict == mine["independent_verdict"]:
        return "CORRECT_VERDICT_WRONG_MECHANISM"
    return "MISSING_CAUSAL_REASON"


def _classify_intent(intent_condition, mine):
    """How the benchmark's declared catcher stands to the causal one."""
    if not intent_condition:
        return "NO_MACHINE_CHECKABLE_INTENT"
    if intent_condition in set(mine["causal_catchers"]):
        return "INTENT_IS_CAUSAL"
    if intent_condition in set(mine["redundant_catchers"]):
        return "INTENT_IS_REDUNDANT"
    if intent_condition in set(mine["valid_reasons"]):
        return "INTENT_IS_VALID_NOT_CAUSAL"
    if intent_condition in set(mine["undefined_catchers"]):
        return "INTENT_COUNTERFACTUAL_UNDEFINED"
    # A condition left UNDECIDABLE did fail, as a gap. It is not a reason for
    # a NOT_SUPPORTED verdict, but an intent naming it was not simply wrong
    # either, and reporting both as "did not fail" hides the difference.
    if intent_condition in set(mine.get("gap_conditions", ())):
        return "INTENT_IS_A_GAP_NOT_A_REASON"
    if mine["independent_verdict"] == "SUPPORTED":
        # Nothing failed at all, so an intent naming a condition is not a
        # failed catcher claim. These are the `*_in@*` families, which place a
        # value just INSIDE a bound and name the condition the case is about;
        # the field is being used as "what this case is testing", not "what
        # must fire". Scoring that as a miss would penalise the benchmark for
        # saying what it meant. Read from THIS analyser's verdict rather than
        # the stored one, so no benchmark answer enters the classification.
        return "INTENT_NAMES_A_NEAR_MISS"
    return "INTENT_DID_NOT_FAIL"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", required=True)
    parser.add_argument("--cases", default=str(BENCH / "cases_hard"))
    parser.add_argument("--out", required=True)
    parser.add_argument("--compare", action="store_true")
    args = parser.parse_args()

    dev = set(json.loads(
        (BENCH / "split_hard.json").read_text(encoding="utf-8")
    )["dev"])
    cases = {}
    for path in sorted(pathlib.Path(args.cases).glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        if case["id"] in dev:
            cases[case["id"]] = case

    # ---- STEP 1: truth, from payloads alone ---------------------------
    truth = [analyse(cid, cases[cid]["payload"]) for cid in sorted(cases)]
    blob = json.dumps(truth, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()

    document = {
        "schema": "independent_reason_truth/1",
        "truth_version": "2026-09-10.1",
        "split": "dev",
        "n_cases": len(truth),
        "truth_digest": digest,
        "note": (
            "Reason sets and causal catchers reconstructed from payloads alone "
            "by benchmarks/oracles/independent_reason.py. Causality is decided "
            "by counterfactual repair, not by which condition Forge reported. "
            "No stored catcher, acceptable catcher, expected reason, expected "
            "verdict or Forge output participated in producing `truth`."
        ),
        "truth": truth,
    }

    # ---- STEPS 2 and 3: intent and Forge, kept apart ------------------
    if args.compare:
        sys.path.insert(0, args.src)
        from engcore.mcp.problem import run_electrothermal_case

        by_id = {t["case_id"]: t for t in truth}
        comparison = []
        for case_id in sorted(cases):
            ground = cases[case_id]["ground_truth"]
            intent = (ground.get("should_be_caught_by") or "").strip()
            expects_gap = "-> UNKNOWN" in intent
            intent_condition = INTENT_PROSE.get(intent) or (
                intent.replace(" -> UNKNOWN", "")
                      .replace(" (alt route remains)", "")
                      .strip()
            )
            mine = by_id[case_id]
            forge = _forge_fired(
                cases[case_id]["payload"], case_id, run_electrothermal_case
            )

            strict = (set(forge.get("violated", ()))
                      | set(forge.get("unknown", ()))
                      | set(forge.get("failed_checks", ())))
            comparison.append({
                "case_id": case_id,
                "defect": ground["defect"],
                "benchmark_intent": intent,
                "intent_expects_gap": expects_gap,
                "intent_class": _classify_intent(intent_condition, mine),
                "forge_class": _classify_forge(
                    mine, _expand(strict), forge.get("verdict")
                ),
                "forge_class_strict": _classify_forge(
                    mine, strict, forge.get("verdict")
                ),
                "forge_verdict": forge.get("verdict"),
                "forge_violated": forge.get("violated", []),
                "forge_failed_checks": forge.get("failed_checks", []),
                "independent_verdict": mine["independent_verdict"],
                "causal_catchers": mine["causal_catchers"],
                "primary_status": mine["primary_status"],
                "reason_truth_class": mine["reason_truth_class"],
            })
        document["mechanism_equivalence"] = {
            k: sorted(v) for k, v in MECHANISM_EQUIVALENCE.items()
        }
        document["comparison"] = comparison

    pathlib.Path(args.out).write_bytes(
        json.dumps(document, ensure_ascii=False, indent=1).encode("utf-8")
    )

    print(f"cases            : {len(truth)}")
    print(f"truth digest     : {digest}")
    for label, key in (("primary status", "primary_status"),
                       ("reason class", "reason_truth_class")):
        print(f"\n{label}:")
        for name, count in collections.Counter(
            t[key] for t in truth
        ).most_common():
            print(f"    {name:<34}{count}")

    if args.compare:
        for label, key in (("benchmark intent vs causal", "intent_class"),
                           ("Forge vs causal (mechanism)", "forge_class"),
                           ("Forge vs causal (strict names)",
                            "forge_class_strict")):
            print(f"\n{label}:")
            for name, count in collections.Counter(
                c[key] for c in document["comparison"]
            ).most_common():
                print(f"    {name:<34}{count}")


if __name__ == "__main__":
    main()
