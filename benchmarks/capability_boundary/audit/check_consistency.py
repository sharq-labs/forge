"""CB-18: reject a report that does not reconcile with its own artifacts.

Two jobs. The first is arithmetic: every number the report states must be
computable from a machine-readable file. The second is the one this round
turns on -- reject any sentence that treats software correctness or contract
consistency AS scientific validity, because all three defects this round found
lived inside perfect contract agreement with a green test suite.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROUND = HERE.parent

#: Conclusions that do not follow. Each is a real inference someone could draw
#: from this round's own evidence, and each is false.
FORBIDDEN = (
    ("record and runtime agree", "therefore scientifically correct"),
    ("tests pass", "therefore the claim is scientifically valid"),
    ("the model gives a number", "therefore the model applies"),
    ("digest unchanged", "therefore the capability claim is valid"),
    ("physically valid input", "therefore the model must support it"),
)

#: Phrasings that would overstate the round outright.
FORBIDDEN_PHRASES = (
    "scientifically correct",
    "full scientific correctness is certified",
    "all capability boundaries are known",
    "no capability boundary remains undiscovered",
    "16/16 exact",
)

#: Phrasings the report must contain, because leaving them out is how the
#: overstatement gets made by omission.
REQUIRED_PHRASES = (
    "does not certify",
    "SCIENTIFIC CAPABILITY AUDIT EXPOSED OVERCLAIMS",
    "bit-identical",
    "do not follow",
)


def main() -> int:
    surface = json.loads((ROUND / "MODEL_CAPABILITY_SURFACE.json").read_text("utf-8"))
    cases = json.loads((ROUND / "FALSE_CONFIDENCE_CASES.json").read_text("utf-8"))
    plants = json.loads((ROUND / "PLANTED_DEFECTS.json").read_text("utf-8"))
    gates = json.loads((ROUND / "SAFETY_GATES.json").read_text("utf-8"))
    assurance = json.loads((ROUND / "EXISTING_ASSURANCE.json").read_text("utf-8"))
    report = (ROUND / "ROUND_REPORT.md").read_text("utf-8")
    # Match the prose, not the markup. "does **not** certify" and "does not
    # certify" are the same sentence, and a checker that cannot see that is
    # checking the asterisks.
    plain = re.sub(r"[*_`]", "", report)
    lowered = plain.lower()

    problems: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        if not ok:
            problems.append(f"{name}: {detail}")

    # --- arithmetic -------------------------------------------------------
    check("model count", surface["model_count"] == 16, str(surface["model_count"]))
    check(
        "every model reviewed",
        all(m["status"] == "REVIEWED" for m in surface["models"]),
    )
    check(
        "report states the real-case total",
        str(surface["real_cases_reviewed"]) in plain,
        f"{surface['real_cases_reviewed']} missing from the report",
    )
    check(
        "report states the case count",
        f"{cases['cases_run']} adversarial" in lowered,
    )
    check(
        "findings reconcile",
        sorted(cases["findings"])
        == sorted(m["finding"] for m in surface["models"] if m["finding"]),
        f"{cases['findings']} vs surface",
    )
    check(
        "no NO case left unresolved",
        not surface["unresolved_no_cases"],
        str(surface["unresolved_no_cases"]),
    )
    check(
        "no false-confidence case left open",
        not cases["false_confidence_cases_still_open"],
        str(cases["false_confidence_cases_still_open"]),
    )
    check(
        "plants all caught",
        plants["caught"] == plants["total"] and not plants["survivors"],
        f"{plants['caught']}/{plants['total']} survivors={plants['survivors']}",
    )
    check("plant control green", plants["control"]["green"])
    check("gates all pass", gates["all_pass"])
    check(
        "assurance preserved",
        assurance["all_preserved"] is True,
        "EXISTING_ASSURANCE says otherwise",
    )
    check(
        "benchmarks re-run and identical",
        all(row.get("identical_ignoring_timestamp") for row in assurance["benchmarks"]),
        str(assurance["benchmarks"]),
    )
    mutation = assurance["assurance_layers"]["1_certified_executable_code_mutation"]
    check(
        "79-mutant suite re-run",
        mutation["detail"].get("killed") == 79
        and mutation["detail"].get("control_green"),
        mutation["result"],
    )
    check(
        "report states the mutation result",
        "79/79 red" in lowered,
        "the report does not state 79/79",
    )
    check(
        "assurance layers kept separate",
        len(assurance["assurance_layers"]) == 3,
    )

    # --- the inferences this round exists to reject ------------------------
    # The report names each forbidden inference in order to reject it, so the
    # test is not "is this string absent" -- it is "wherever this inference
    # appears, is it being rejected". A checker that could not tell the
    # difference would force the report to stop naming what it rejects, which
    # is the opposite of what CB-18 is for.
    for premise, conclusion in FORBIDDEN:
        joined = f"{premise}, {conclusion}"
        for match in re.finditer(re.escape(joined), lowered):
            window = lowered[max(0, match.start() - 700) : match.end() + 400]
            rejected = any(
                marker in window
                for marker in (
                    "do not follow",
                    "does not follow",
                    "rejected explicitly",
                    "not evidence",
                    "reject",
                )
            )
            check(
                f"'{premise} -> {conclusion}' appears only where it is rejected",
                rejected,
                f"...{plain[max(0, match.start() - 140) : match.end() + 120]}...",
            )
    for phrase in FORBIDDEN_PHRASES:
        # "scientifically correct" is allowed only where it is being DENIED.
        occurrences = [
            match.start() for match in re.finditer(re.escape(phrase), lowered)
        ]
        for start in occurrences:
            # A bullet list under "It does not certify:" puts the denial well
            # above the phrase, so the window has to reach the sentence that
            # governs the list rather than just the line.
            window = lowered[max(0, start - 900) : start + 160]
            denied = any(
                marker in window
                for marker in (
                    "not certify",
                    "does not",
                    "do not",
                    "never",
                    "reject",
                    "therefore",
                )
            )
            check(
                f"'{phrase}' appears only where it is denied",
                denied,
                f"...{plain[max(0, start - 120) : start + 90]}...",
            )
    for phrase in REQUIRED_PHRASES:
        check(f"report contains '{phrase}'", phrase.lower() in lowered)

    # --- the decision must match the evidence ------------------------------
    exposed = bool(cases["findings"])
    check(
        "decision matches the evidence",
        ("scientific capability audit exposed overclaims" in lowered) == exposed,
        "findings exist but the report does not use the exposed-overclaims decision",
    )
    check(
        "exactly one final decision is stated",
        sum(
            phrase in lowered
            for phrase in (
                "scientific capability boundaries certified",
                "scientific capability audit exposed overclaims",
                "scientific capability audit inconclusive",
            )
        )
        == 1,
    )

    print(f"{len(problems)} inconsistency(ies)")
    for problem in problems:
        print("  !!", problem)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
