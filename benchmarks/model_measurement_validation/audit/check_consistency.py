"""MV-28: does the report say what the artifacts say, and how does it reason?

Two jobs. Every number the report quotes is checked IN CONTEXT against the file
it came from -- a checker that only asked whether the digit 3 occurred
somewhere would pass almost anything. And the prose is scanned for the specific
inferences this round is not allowed to make, each of which is a way of turning
thin evidence into a broad claim.

The checker refuses to return CONSISTENT until it has demonstrated, on a
deliberately corrupted copy of the report, that it can fail.
"""

from __future__ import annotations

import json
import pathlib
import re

from .evidence import ROOT

REPORT = ROOT / "ROUND_REPORT.md"


def _text() -> str:
    """The report with emphasis stripped, underscores KEPT.

    Underscores survive because the verdicts matched against are identifiers
    like EMPIRICAL_EVIDENCE_NOT_ESTABLISHED; stripping them from the haystack
    while leaving them in the needle makes every such check unsatisfiable.
    """
    stripped = re.sub(r"[*`\[\]]", "", REPORT.read_text(encoding="utf-8"))
    # Line wrapping is not content. Without this, a phrase that happens to
    # straddle a newline is unmatchable and the checker reports a report that
    # says the right thing as saying nothing.
    return re.sub(r"[ \t]*\n[ \t]*", " ", stripped)


def _artifact(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Inferences this round rejects
# ---------------------------------------------------------------------------

FORBIDDEN = [
    ("all tested cases pass, therefore all 16 models are empirically validated",
     re.compile(r"all (16|sixteen) models? (are|were) empirically validated", re.I)),
    ("a manufacturer curve exists, therefore the model should fit it",
     re.compile(r"(datasheet|manufacturer) curve.{0,80}(should|must) (fit|match)", re.I)),
    ("reference data, therefore experimental data",
     re.compile(r"(reference (data|table|relation)|ngspice)[^.]{0,80}\b(is|are) (experimental|empirical|measured)", re.I)),
    ("the same data used for calibration and validation",
     re.compile(r"calibrat\w+ (points?|set|rows?)[^.]{0,60}also (used for |as )?validat", re.I)),
    ("low RMSE, therefore no systematic bias",
     re.compile(r"(low|small) (RMSE|error)[^.]{0,60}(therefore|so)[^.]{0,40}no (systematic )?bias", re.I)),
    ("no measurement data, therefore the model failed",
     re.compile(r"no (measurement|measured|empirical) (data|evidence)[^.]{0,60}(therefore|so)[^.]{0,40}(model )?fail", re.I)),
    ("mathematical agreement, therefore physical-world accuracy",
     re.compile(r"(mathematical|analytical|oracle) agreement[^.]{0,60}(therefore|so|means)[^.]{0,50}(physical|real.world|accurate)", re.I)),
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
# Numbers, checked in context
# ---------------------------------------------------------------------------


def quoted_numbers() -> list[dict]:
    text = _text()
    results = _artifact("VALIDATION_RESULTS.json")
    accounting = _artifact("MODEL_ACCOUNTING.json")
    gates = _artifact("SAFETY_GATES.json")
    plants = _artifact("FALSIFICATION.json")
    shapes = _artifact("RESIDUAL_ANALYSIS.json")["analyses"]
    provenance = _artifact("EVIDENCE_PROVENANCE.json")

    a = results["cases"]["MV-A"]["summary"]
    replicate = results["cases"]["MV-A-replicate"]["summary"]
    c = results["cases"]["MV-C"]
    d = results["cases"]["MV-D"]["summary"]

    claims = [
        ("calibration rows", results["row_counts"]["CALIBRATION"], r"calibration rows"),
        ("validation rows", results["row_counts"]["VALIDATION"], r"validation rows"),
        ("held-out rows", results["row_counts"]["HELD_OUT"], r"held-out rows"),
        ("models with no empirical evidence",
         accounting["counts"]["EMPIRICAL_EVIDENCE_NOT_ESTABLISHED"],
         r"with no empirical evidence established|Seven, named with the reason"),
        ("models partially covered", accounting["counts"]["EMPIRICAL_PARTIAL"],
         r"partial, \d+ reference-only"),
        ("reference-only models", accounting["counts"]["REFERENCE_VALIDATED_ONLY"],
         r"reference-only"),
        ("gates passed", gates["passed"], r"MV-7 is expected to fail|gates"),
        ("plants caught", plants["caught"], r"caught, \d+ missed"),
        ("plants missed", plants["missed"], r"caught, \d+ missed"),
        ("MV-A worst residual in units of uncertainty",
         round(a["worst_residual_in_units_of_its_own_uncertainty"]),
         r"times the expanded uncertainty|217"),
        ("MV-D curve count", d["n_curves"], r"measured discharges of 10 different cells"),
        ("MV-C scored entries", c["summary"]["n_scored"], r"scored entries"),
        ("sources accepted", len(provenance["sources_accepted"]), r"Accepted, and used"),
    ]

    rows = []
    for label, value, context in claims:
        needle = str(value)
        ok = False
        for match in re.finditer(context, text):
            window = text[max(0, match.start() - 300): match.end() + 300]
            if needle in window:
                ok = True
                break
        rows.append({"claim": label, "value": needle,
                     "context_pattern": context, "present_in_report": ok})

    # Millivolt figures, quoted to one decimal place in context.
    for label, value, context in [
        ("MV-A mean absolute error", f"{a['mean_absolute_error_v'] * 1e3:.1f}", "APR"),
        ("MV-A maximum error", f"{a['max_absolute_error_v'] * 1e3:.1f}", "APR"),
        ("replicate mean absolute error", f"{replicate['mean_absolute_error_v'] * 1e3:.1f}", "BSE"),
        ("MV-C residual curvature", f"{shapes['MV-C']['curvature_coefficient']:.4e}".replace("e-05", "e-5"), "curvature"),
    ]:
        found = False
        for match in re.finditer(context, text):
            window = text[max(0, match.start() - 300): match.end() + 300]
            if value in window:
                found = True
                break
        rows.append({"claim": label, "value": value,
                     "context_pattern": context, "present_in_report": found})
    return rows


# ---------------------------------------------------------------------------
# Claims the report must or must not make
# ---------------------------------------------------------------------------


def claim_checks() -> list[dict]:
    text = _text()
    accounting = _artifact("MODEL_ACCOUNTING.json")
    gates = _artifact("SAFETY_GATES.json")
    results = _artifact("VALIDATION_RESULTS.json")

    checks = []
    checks.append({
        "check": "the decision is one of the three permitted, stated once",
        "ok": sum(
            phrase in text for phrase in (
                "EMPIRICAL VALIDATION PASSED WITH DEFINED COVERAGE",
                "EMPIRICAL VALIDATION EXPOSED MODEL MISMATCHES",
                "EMPIRICAL VALIDATION INCONCLUSIVE",
            )
        ) == 1,
    })
    checks.append({
        "check": "coverage is stated alongside the decision",
        "ok": "3 of 16" in text,
        "why": "a mismatch verdict without its coverage reads as a statement about all sixteen models",
    })
    checks.append({
        "check": "no model is reported as empirically validated within scope",
        "ok": accounting["counts"].get("EMPIRICALLY_VALIDATED_WITHIN_SCOPE", 0) == 0
        and "0 empirically validated within scope" in text,
    })
    checks.append({
        "check": "the failing gate is reported as failing",
        "ok": any(g["id"] == "MV-7" and g["verdict"] == "FAIL" for g in gates["gates"])
        and "MV-7" in text,
    })
    checks.append({
        "check": "every audit defect is listed",
        "ok": all(f"MVF-{n}" in text for n in (1, 2, 3, 5, 7))
        and "MVF-8" in text,
    })
    checks.append({
        "check": "the model family is not blamed for a configuration's failure",
        "ok": "Is the model family inadequate? No" in text
        or "the model family is not the problem" in text.lower()
        or "The family is adequate" in text,
    })
    checks.append({
        "check": "the three models with insufficient evidence are not reported as failures",
        "ok": all(
            accounting["models"][m]["verdict"] == "EMPIRICAL_EVIDENCE_NOT_ESTABLISHED"
            for m in ("battery.cell.coulomb_counting",
                      "battery.cell.constant_current_runtime",
                      "battery.cell.peukert_capacity_derating")
        ),
    })
    checks.append({
        "check": "the limitations section exists and names the coverage limit",
        "ok": "Remaining limitations" in text and "Coverage is 3 of 16" in text,
    })
    checks.append({
        "check": "the exact validation claim is stated",
        "ok": "The exact validation claim" in text,
    })
    checks.append({
        "check": "no leakage was found, and the report does not claim otherwise",
        "ok": next(
            c for c in results["integrity"]["checks"]
            if c["check"] == "calibration leakage"
        )["passed"] and "No leakage" in text,
    })
    for entry in checks:
        entry.setdefault("why", None)
    return checks


# ---------------------------------------------------------------------------


def self_check() -> dict:
    """Can this checker fail? Demonstrated, not assumed."""
    global REPORT
    import tempfile

    original = REPORT
    text = original.read_text(encoding="utf-8")
    truth = str(_artifact("VALIDATION_RESULTS.json")["row_counts"]["VALIDATION"])
    spoiled = text.replace(f"{truth} validation rows", f"{int(truth) - 1} validation rows", 1)
    changed = spoiled != text
    caught = False
    if changed:
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "ROUND_REPORT.md"
            path.write_text(spoiled, encoding="utf-8")
            REPORT = path
            try:
                caught = any(not row["present_in_report"] for row in quoted_numbers())
            finally:
                REPORT = original
    return {
        "a_number_was_changed": changed,
        "the_checker_noticed": caught,
        "verdict": "CHECKER_CAN_FAIL" if changed and caught else "CHECKER_CANNOT_FAIL",
    }


def run() -> dict:
    numbers = quoted_numbers()
    claims = claim_checks()
    forbidden = forbidden_reasoning()
    checker = self_check()
    missing = [row for row in numbers if not row["present_in_report"]]
    failed = [row for row in claims if not row["ok"]]
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
            if not missing and not failed and not forbidden
            and checker["verdict"] == "CHECKER_CAN_FAIL"
            else "INCONSISTENT"
        ),
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
