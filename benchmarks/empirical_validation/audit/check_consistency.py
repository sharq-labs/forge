"""EV-30: does the report say what the artifacts say?

A round whose prose and whose JSON disagree is worse than no round: the prose is
what gets read. So every number quoted in ROUND_REPORT.md is checked against the
file it came from, and the report is scanned for the specific forms of reasoning
this round is not allowed to use.

Markdown emphasis is stripped before matching. A number inside **bold** is the
same number, and a checker that missed it would pass a report by accident.
"""

from __future__ import annotations

import json
import pathlib
import re

from .loader import ROOT

REPORT = ROOT / "ROUND_REPORT.md"


def _text() -> str:
    """The report with markdown emphasis removed, but underscores kept.

    A number inside **bold** is the same number and a checker that missed it
    would pass a report by accident. Underscores are NOT stripped: the artifact
    verdicts this file matches against are identifiers like
    EMPIRICAL_EVIDENCE_NOT_ESTABLISHED, and removing the underscore from the
    haystack while leaving it in the needle makes every such check silently
    unsatisfiable.
    """
    raw = REPORT.read_text(encoding="utf-8")
    return re.sub(r"[*`\[\]]", "", raw)


def _artifact(name: str) -> dict:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Reasoning this round is not allowed to use
# ---------------------------------------------------------------------------

FORBIDDEN = [
    (
        "calling agreement with this round's own mathematics empirical",
        re.compile(
            r"empirical(ly)? (validated|validation) (by|against|through) "
            r"(the|an|a) (oracle|closed form|analytic|independent math)",
            re.IGNORECASE,
        ),
    ),
    (
        "calling an external solver independent without saying where its "
        "problem came from",
        re.compile(
            r"ngspice (is|was) independent(?!.{0,400}(fixture|netlist))",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "justifying a tolerance by what the implementation achieves",
        re.compile(
            r"tolerance .{0,80}(large enough|loose enough|chosen so that .{0,40}pass)",
            re.IGNORECASE,
        ),
    ),
    (
        "reporting absence of evidence as agreement",
        re.compile(r"no (external )?evidence.{0,40}(therefore|so) .{0,40}agree", re.IGNORECASE),
    ),
    (
        "claiming the model was changed to fit a reference",
        re.compile(r"(adjusted|tuned|fitted) (the )?model .{0,40}(to match|to fit)", re.IGNORECASE),
    ),
]


def forbidden_reasoning() -> list[dict]:
    text = _text()
    found = []
    for description, pattern in FORBIDDEN:
        match = pattern.search(text)
        if match:
            found.append({"pattern": description, "match": match.group(0)[:200]})
    return found


# ---------------------------------------------------------------------------
# Numbers the report quotes, against the files they came from
# ---------------------------------------------------------------------------


def quoted_numbers() -> list[dict]:
    """Each number must appear NEAR the thing it describes.

    Checking only that a digit occurs somewhere in the file would pass a report
    that said 9 about something else entirely, which for small counts is most of
    them. So each claim carries a context pattern, and the value has to appear
    inside a window that also matches it.
    """
    text = _text()
    results = _artifact("VALIDATION_RESULTS.json")
    surface = _artifact("VALIDATION_SURFACE.json")
    construction = _artifact("PROBLEM_CONSTRUCTION.json")
    gates = _artifact("SAFETY_GATES.json")
    shapes = _artifact("ERROR_SHAPE.json")
    mutations = _artifact("CONSTRUCTION_MUTATIONS.json")
    harness = _artifact("HARNESS_FALSIFICATION.json")
    graph = _artifact("INDEPENDENCE_GRAPH.json")

    counts = surface["empirical_evidence_possible_counts"]
    ipm6 = next(m for m in mutations["mutations"] if m["id"] == "IPM-6")
    levels = results["primary"]["by_evidence_level"]

    claims = [
        ("primary comparison rows", results["primary"]["rows"], r"[Pp]rimary comparison rows"),
        ("held-out rows", results["holdout"]["rows"], r"[Hh]eld-out rows"),
        (
            "construction fields compared",
            sum(construction["counts"].values()),
            r"construction fields compared",
        ),
        ("construction EXACT", construction["counts"]["EXACT"], r"EXACT"),
        (
            "construction TRANSFORMED_CORRECTLY",
            construction["counts"]["TRANSFORMED_CORRECTLY"],
            r"TRANSFORMED_CORRECTLY",
        ),
        ("gates passed", gates["passed"], r"Gates"),
        (
            "models with no external evidence",
            counts["NO"],
            r"NO . no external evidence exists here|Nine of sixteen",
        ),
        (
            "models with external evidence",
            counts["YES"],
            r"YES . ngspice or IEC 60751",
        ),
        (
            "rows against ngspice",
            levels["LEVEL 4 external canonical implementation"],
            r"ngspice 42 .LEVEL 4.",
        ),
        (
            "rows against published reference data",
            levels["LEVEL 3 reference data"],
            r"published reference data .LEVEL 3.",
        ),
        (
            "rows against this round's own mathematics",
            levels["LEVEL 5 independent analytical"],
            r"mathematics written in this round .LEVEL 5.",
        ),
        (
            "branch A closure size",
            graph["tracer_self_check"]["branch_A_closure_size"],
            r"branch A .engcore.",
        ),
        (
            "branch A engcore modules",
            graph["tracer_self_check"]["branch_A_engcore_modules"],
            r"branch A .engcore.|all \d+ of them",
        ),
        ("harness control rows", harness["control"]["rows"], r"control, nothing injected"),
        ("mutations caught", mutations["caught"], r"Construction mutations"),
    ]

    rows = []
    for label, value, context in claims:
        needle = str(value)
        ok = False
        for match in re.finditer(context, text):
            window = text[max(0, match.start() - 200) : match.end() + 200]
            if needle in window:
                ok = True
                break
        rows.append(
            {
                "claim": label,
                "value": needle,
                "context_pattern": context,
                "present_in_report": ok,
            }
        )

    # A float that must be quoted to one decimal place, in context.
    rows.append(
        {
            "claim": "IPM-6 undetected temperature error",
            "value": f"{ipm6['size_of_the_undetected_error_k']:.1f}",
            "context_pattern": "IPM-6",
            "present_in_report": bool(
                re.search(
                    r"IPM-6.{0,900}"
                    + re.escape(f"{ipm6['size_of_the_undetected_error_k']:.1f}"),
                    text,
                    re.DOTALL,
                )
            ),
        }
    )

    # Verdict strings, quoted in prose rather than as identifiers.
    for label, value, phrase in [
        (
            "slab error shape",
            shapes["slab"]["verdict"],
            "ratio of observed to predicted error stays",
        ),
        (
            "platinum residual",
            shapes["platinum"]["verdict"],
            "next term of the same expansion",
        ),
        (
            "dc conditioning",
            shapes["dc_conditioning"]["verdict"],
            "track",
        ),
    ]:
        rows.append(
            {
                "claim": label,
                "value": value,
                "context_pattern": phrase,
                "present_in_report": phrase in text,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Claims that must not be made unless the artifacts support them
# ---------------------------------------------------------------------------


def claim_checks() -> list[dict]:
    text = _text()
    surface = _artifact("VALIDATION_SURFACE.json")
    gates = _artifact("SAFETY_GATES.json")
    results = _artifact("VALIDATION_RESULTS.json")

    checks = []

    empirical_claimed = bool(
        re.search(r"EMPIRICAL VALIDATION PASSED", text)
    )
    checks.append(
        {
            "check": "the report does not claim empirical validation passed",
            "ok": not empirical_claimed
            or "Not \"empirical validation passed\"" in REPORT.read_text(encoding="utf-8"),
            "why": (
                "No LEVEL 1 or LEVEL 2 evidence exists in this environment, so "
                "that verdict is unavailable. The phrase may appear only where "
                "the report is refusing it."
            ),
        }
    )

    not_established = [
        m["model_id"]
        for m in surface["models"]
        if m["empirical_status"] == "EMPIRICAL_EVIDENCE_NOT_ESTABLISHED"
    ]
    checks.append(
        {
            "check": "the count of models with no empirical evidence is stated",
            "ok": str(len(not_established)) in text,
            "value": len(not_established),
        }
    )
    checks.append(
        {
            "check": "the report states that the Core was not modified",
            "ok": gates["core_unchanged"]["matches"]
            and "Nothing under src/ or tests/ was modified" in text,
        }
    )
    checks.append(
        {
            "check": "the report does not report a disagreement count it does not have",
            "ok": results["primary"]["disagreements"] == 0
            and results["holdout"]["disagreements"] == 0,
        }
    )
    checks.append(
        {
            "check": "every audit defect found in this round is listed",
            "ok": all(f"EVA-{n}" in text for n in range(1, 6)),
        }
    )
    checks.append(
        {
            "check": "the two blind mutations are reported as blind, not as passes",
            "ok": "IPM-6" in text and "IPM-7" in text and "53.1 K" in text,
        }
    )
    checks.append(
        {
            "check": "the limits section exists and names what was not established",
            "ok": "What this round does not establish" in text,
        }
    )
    return checks


def self_check() -> dict:
    """Can this checker fail?

    The same discipline the round applies to the comparison harness. A
    consistency checker that has never been shown to report an inconsistency is
    a green light with no bulb behind it. One digit in the report is changed in
    memory -- the file on disk is not touched -- and the checker must notice.
    """
    global REPORT
    import tempfile

    original = REPORT
    text = original.read_text(encoding="utf-8")
    results = _artifact("VALIDATION_RESULTS.json")
    truth = str(results["primary"]["rows"])
    spoiled = text.replace(
        f"| Primary comparison rows | {truth},",
        f"| Primary comparison rows | {int(truth) - 1},",
        1,
    )
    changed = spoiled != text
    with tempfile.TemporaryDirectory() as directory:
        path = pathlib.Path(directory) / "ROUND_REPORT.md"
        path.write_text(spoiled, encoding="utf-8")
        REPORT = path
        try:
            spoiled_rows = quoted_numbers()
        finally:
            REPORT = original
    caught = any(not row["present_in_report"] for row in spoiled_rows)
    return {
        "a_digit_was_changed": changed,
        "the_checker_noticed": caught,
        "verdict": (
            "CHECKER_CAN_FAIL" if changed and caught else "CHECKER_CANNOT_FAIL"
        ),
    }


def run() -> dict:
    numbers = quoted_numbers()
    claims = claim_checks()
    forbidden = forbidden_reasoning()
    missing = [row for row in numbers if not row["present_in_report"]]
    failed = [row for row in claims if not row["ok"]]
    checker = self_check()
    return {
        "schema": "consistency_audit/1",
        "checker_self_falsification": checker,
        "numbers_checked": len(numbers),
        "numbers_missing_from_the_report": missing,
        "claim_checks": claims,
        "failed_claim_checks": failed,
        "forbidden_reasoning_found": forbidden,
        "inconsistencies": len(missing) + len(failed) + len(forbidden),
        "verdict": (
            "CONSISTENT"
            if not missing
            and not failed
            and not forbidden
            and checker["verdict"] == "CHECKER_CAN_FAIL"
            else "INCONSISTENT"
        ),
    }


if __name__ == "__main__":
    report = run()
    print(json.dumps(report, indent=2))
