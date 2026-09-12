"""ST-26/ST-27: reject a report that does not reconcile, or that confuses layers.

Two jobs. Every number in the report must be computable from an artifact. And
every conclusion of the form "X, therefore the equation is correct" must be
rejected, because each of them names two different assurance layers:

    MATHEMATICAL TRUTH        is this the right equation?
    IMPLEMENTATION CORRECTNESS does the code compute that equation?
    NUMERICAL ACCURACY         does the discretization converge to it?
    SCIENTIFIC VALIDITY        does the equation describe this regime?
    CONTRACT CONSISTENCY       does the record say what the runtime does?

The round's own history is the argument: five oracles in this audit were wrong
while every test passed, every record matched every runtime, and every
benchmark was unchanged.
"""

from __future__ import annotations

import json
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
ROUND = HERE.parent

#: Inferences that do not follow. Each may appear in the report only where it
#: is being rejected.
FORBIDDEN_INFERENCES = (
    "tests pass, therefore the equation is correct",
    "two solvers agree, therefore both are correct",
    "the record and the runtime agree, therefore the physics is correct",
    "the benchmark is unchanged, therefore the model is correct",
    "it is dimensionally valid, therefore it is scientifically valid",
    "it converged, therefore the governing equation is correct",
)

REQUIRED_PHRASES = (
    "SCIENTIFIC MODEL TRUTH VALIDATED",
    "does not validate",
    "Conclusions explicitly rejected",
    "audit mistakes",
)


def main() -> int:
    cases = json.loads((ROUND / "REFERENCE_CASES.json").read_text("utf-8"))
    surface = json.loads((ROUND / "MODEL_EQUATION_SURFACE.json").read_text("utf-8"))
    ledger = json.loads((ROUND / "EQUATION_LEDGER.json").read_text("utf-8"))
    indep = json.loads((ROUND / "SOLVER_INDEPENDENCE.json").read_text("utf-8"))
    props = json.loads((ROUND / "PROPERTY_TESTING.json").read_text("utf-8"))
    false_agreement = json.loads((ROUND / "FALSE_AGREEMENT_CASES.json").read_text("utf-8"))
    plants = json.loads((ROUND / "PLANTED_DEFECTS.json").read_text("utf-8"))
    gates = json.loads((ROUND / "SAFETY_GATES.json").read_text("utf-8"))
    report = (ROUND / "ROUND_REPORT.md").read_text("utf-8")
    plain = re.sub(r"[*_`]", "", report)
    lowered = plain.lower()

    problems: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        if not ok:
            problems.append(f"{name}: {detail}")

    # ---- arithmetic -------------------------------------------------------
    check("16 models in the surface", surface["model_count"] == 16)
    check("16 ledger entries", len(ledger["entries"]) == 16)
    check(
        "every model has oracle-backed rows",
        len(cases["by_model"]) == 16,
        f"{len(cases['by_model'])} models have rows",
    )
    check(
        "report states the row total",
        str(cases["total_rows"]) in plain,
        f"{cases['total_rows']} missing from the report",
    )
    check("zero disagreements", not cases["disagreements"])
    check("zero false-agreement cases", false_agreement["count"] == 0)
    check("no property violation", not props["violations"])
    check(
        "every generator rejected something",
        all(family["rejected"] > 0 for family in props["families"]),
        str([f["model"] for f in props["families"] if f["rejected"] == 0]),
    )
    draws = sum(family["generated"] for family in props["families"])
    check("report states the admitted draws", str(draws) in plain, str(draws))
    check(
        "all plants detected",
        plants["caught"] == plants["total"] and not plants["missed"],
        f"{plants['caught']}/{plants['total']}",
    )
    check("plant control green", plants["control"]["green"])
    check(
        "report states the plant count",
        f"{plants['caught']} planted scientific defects, {plants['caught']} detected"
        in plain
        or f"{plants['total']} planted scientific defects, {plants['caught']} detected" in plain,
    )
    check("all gates pass", gates["all_pass"])
    check(
        "no coupled independence pair",
        indep["counts"]["NO"] == 0,
        str(indep["counts"]),
    )
    check(
        "this audit's oracles are independent",
        all(
            row["verdict"] == "INDEPENDENT_OF_CORE"
            for row in indep["this_audits_oracles"]
        ),
    )
    check(
        "dimensional verdicts are all valid",
        ledger["dimensional_counts"].get("DIMENSIONAL_DEFECT", 0) == 0,
        str(ledger["dimensional_counts"]),
    )
    check(
        "the report does not claim a fix it did not make",
        "no file under" in lowered and "was changed" in lowered,
    )
    check("four assurance layers kept separate", len(gates["layers_kept_separate"]) == 4)

    # ---- the inferences that do not follow ---------------------------------
    for inference in FORBIDDEN_INFERENCES:
        for match in re.finditer(re.escape(inference.lower()), lowered):
            window = lowered[max(0, match.start() - 900) : match.end() + 400]
            rejected = any(
                marker in window
                for marker in (
                    "rejected", "does not follow", "none of these follows",
                    "not evidence", "which is why",
                )
            )
            check(
                f"'{inference}' appears only where it is rejected",
                rejected,
                f"...{plain[max(0, match.start() - 120) : match.end() + 100]}...",
            )

    for phrase in REQUIRED_PHRASES:
        check(f"report contains '{phrase}'", phrase.lower() in lowered)

    # ---- exactly one decision, and it matches the evidence ------------------
    decisions = (
        "scientific model truth validated",
        "scientific truth audit exposed core defects",
        "scientific truth audit inconclusive",
    )
    stated = [phrase for phrase in decisions if phrase in lowered]
    check("exactly one final decision", len(stated) == 1, str(stated))
    check(
        "the decision matches the evidence",
        (stated == ["scientific model truth validated"])
        == (not cases["disagreements"] and false_agreement["count"] == 0),
    )

    # ---- the audit's own mistakes are not hidden ---------------------------
    check(
        "the report records its own audit defects",
        lowered.count("sta-") >= 5,
        f"only {lowered.count('sta-')} audit-defect references",
    )

    print(f"{len(problems)} inconsistency(ies)")
    for problem in problems:
        print("  !!", problem)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
