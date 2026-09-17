"""The guard reach ledger's verifier (I-16, core re-audit 2026-09-16).

WHAT THIS IS FOR. The 2026-09-16 re-audit's central finding is not that individual guards were wrong. It is
that guards were written where production does not go:

* ``engcore.hybrid_uq`` -- every V2 evidence gate the audit built -- had no caller in ``src`` outside its own
  package, so the one production study ran none of them (R-02);
* ``record_values`` had no caller at all, so the CORE-014 operating-point binding looped over an empty
  mapping on every production path (R-09);
* ``TrustedConsensusGate``, which requires byte-verified artifact independence before
  CROSS_SOLVER_VALIDATED, has no caller (R-21);
* ``UncertaintySource`` has no producer, so ``source_kind`` is UNSPECIFIED on everything production makes
  (R-43);
* the production electrothermal coupling passes bare point values, and ``UncertaintyTransfer`` -- which
  would bind them -- has no caller (R-58).

A guard whose reach nobody states is a guard whose reach nobody can lose. So reach is DECLARED, in
``certification/guard_reach_ledger.json``, and this module refuses a declaration that is not checkable and
finds the four bypasses the audit named by reading the code.

WHY SYNTACTIC AND NOT A CALL GRAPH. A name-resolved call graph over this tree would be a second
implementation of Python's import semantics, and its false negatives would be invisible -- which is exactly
the failure mode this round is about. Each of the four bypasses is a SHAPE the audit identified by reading
the source; a syntactic check finds every instance of that shape, and the ledger says per row what the check
cannot see.

    python -m tools.certification.guard_reach --verify
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
from typing import Iterable, Mapping, Sequence

ROOT = pathlib.Path(__file__).resolve().parents[2]
LEDGER_PATH = ROOT / "certification" / "guard_reach_ledger.json"
AUDIT_PATH = ROOT / "benchmarks" / "core_v4_false_confidence" / "REAUDIT_2026-09-16.json"
SRC = ROOT / "src" / "engcore"

#: The declared statuses. REACHED -- a production entry point reaches the rule and a named test exercises it
#: there. LIBRARY_ONLY -- the rule exists and nothing in production reaches it, which is a FINDING and must
#: name the improvement that will close it. LATENT -- the rule guards a shape that does not occur in the tree
#: at all, which is not the same as unreached, and must say what would create it.
STATUSES = ("REACHED", "LIBRARY_ONLY", "LATENT")

#: The four bypasses the audit named. A hit that no ledger row allows fails the build.
BYPASS_CHECKS = (
    "RAW_POSTERIOR_GRID_CONSUMER",
    "ASSESS_VALIDITY_WITHOUT_RECORD_VALUES",
    "TO_CHECK_OUTSIDE_THE_GATE",
    "ROUTE_UNCERTAINTY_REBUILD_WITHOUT_MULTISTART",
)


def _production_sources() -> dict[str, str]:
    """Every production module, by repository-relative path. ``src/engcore`` only.

    A bypass in ``benchmarks/``, in a test or in a script is not production and is not checked; the ledger
    says so as a residual rather than this function pretending otherwise.
    """
    out: dict[str, str] = {}
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        out[path.relative_to(ROOT).as_posix()] = path.read_text(encoding="utf-8")
    return out


def _call_spans(text: str, pattern: str) -> list[tuple[int, str]]:
    """Every call matching ``pattern``, with its FULL argument list, and its 1-based line number.

    Balanced-paren scanning rather than a regex over the arguments: these calls span line breaks in this
    tree, and a line-based match would miss a keyword on the next line -- which is the difference between
    finding a bypass and reporting one that is not there.
    """
    found: list[tuple[int, str]] = []
    for match in re.finditer(pattern, text):
        start = text.index("(", match.start())
        depth = 0
        for index in range(start, len(text)):
            if text[index] == "(":
                depth += 1
            elif text[index] == ")":
                depth -= 1
                if depth == 0:
                    found.append((text.count("\n", 0, match.start()) + 1,
                                  text[match.start():index + 1]))
                    break
        else:  # pragma: no cover - an unbalanced call would not import
            found.append((text.count("\n", 0, match.start()) + 1, text[match.start():]))
    return found


def _strip_comments_and_strings(text: str) -> str:
    """Docstrings, comments and string literals blanked, so a MENTION is never a call.

    Every one of these four names appears in prose in this tree -- the modules explain themselves at
    length -- and a checker that counted those would be unusable. Line structure is preserved so reported
    line numbers stay true.
    """
    import io
    import tokenize

    out = list(text)
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError):  # pragma: no cover - a file that does not tokenize
        return text
    lines = [0]
    for line in text.split("\n"):
        lines.append(lines[-1] + len(line) + 1)
    for token in tokens:
        if token.type not in (tokenize.COMMENT, tokenize.STRING):
            continue
        start = lines[token.start[0] - 1] + token.start[1]
        end = lines[token.end[0] - 1] + token.end[1]
        for index in range(start, min(end, len(out))):
            if out[index] != "\n":
                out[index] = " "
    return "".join(out)


def raw_posterior_grid_consumers(
    *, allowed: Sequence[str] = (), sources: Mapping[str, str] | None = None
) -> list[str]:
    """Production calls to the frozen ``posterior_predictive_uq`` (R-02's shape).

    That function applies only the grid-resolution refusal: no goodness of fit (CORE-001), no containment
    (CORE-002), no prior uniformity (CORE-010), no prediction-domain statement (CORE-006). A production
    consumer calling it directly gets an interval with none of those applied, which is how a box over the
    posterior mean +/- 0.6 sd reported a parameter sd of 0.34x and was still used for a decisive comparison.
    ``hybrid_uq.grid_predictive_uncertainty`` calls the same function AFTER judging the grid, which is why it
    is an allowed caller and the point of the fix.
    """
    hits = []
    for path, text in (sources or _production_sources()).items():
        if path in set(allowed):
            continue
        code = _strip_comments_and_strings(text)
        for line, _ in _call_spans(code, r"\bposterior_predictive_uq\s*(?=\()"):
            hits.append(f"{path}:{line}: calls posterior_predictive_uq")
    return sorted(hits)


def assessments_without_record_values(
    *, allowed: Sequence[str] = (), sources: Mapping[str, str] | None = None
) -> list[str]:
    """Domain assessments that do not record the operating point they were made at (R-09's shape).

    Batch 14's one-off scan, promoted into a check that runs on every commit. ``record_values`` defaults to
    False on the V1-frozen ``assess_validity``, so a site that does not pass it produces an assessment whose
    ``evaluated`` mapping is empty -- and the CORE-014 binding then compares nothing, which is the state the
    re-audit found the whole tree in.

    The allow-list is EMPTY as committed. The preregistration expected ``domains/derived_context.py`` on
    it, because that helper's own default is True; it is not needed, because the helper forwards
    ``record_values=record_values`` and so the name is in the argument list the checker reads. An
    allow-list entry that is not needed is a hole nobody would notice.
    """
    allow = set(allowed)
    hits = []
    for path, text in (sources or _production_sources()).items():
        if not path.startswith("src/engcore/domains/") or path in allow:
            continue
        code = _strip_comments_and_strings(text)
        for line, call in _call_spans(code, r"\.validity\.assess\s*(?=\()|\.assess_validity\s*(?=\()"):
            if "record_values" not in call:
                hits.append(f"{path}:{line}: {' '.join(call.split())[:70]}")
    return sorted(hits)


def to_check_outside_the_gate(
    *, sources: Mapping[str, str] | None = None
) -> list[str]:
    """Consensus checks minted outside ``TrustedConsensusGate`` and not level-withheld (R-21's shape).

    ``CrossSolverConsensus.to_check`` awards CROSS_SOLVER_VALIDATED on the scientific comparison alone;
    ``TrustedConsensusGate.assess`` is what additionally requires byte-verified artifact independence, and it
    has no caller in ``src``. The one production call is in ``mcp/problem.py`` and is wrapped by
    ``_withhold_level``, which strips the level -- a real mitigation, and the reason that call is not a hole.
    This check is written so that UNWRAPPING it fails the build.
    """
    hits = []
    for path, text in (sources or _production_sources()).items():
        if path == "src/engcore/execution/consensus.py":
            continue
        code = _strip_comments_and_strings(text)
        for line, call in _call_spans(code, r"\.to_check\s*(?=\()"):
            start = code.rindex(call, 0, code.index(call) + len(call))
            prefix = code[max(0, start - 40):start]
            if "_withhold_level(" in prefix:
                continue
            hits.append(f"{path}:{line}: {' '.join(call.split())[:70]} not level-withheld")
    return sorted(hits)


def rebuild_without_multistart(
    *, sources: Mapping[str, str] | None = None
) -> list[str]:
    """A grid rebuild routed without a search for second modes (I-01's shape).

    ``route_uncertainty`` rebuilds a grid from a local posterior, and batch 6 made it refuse to do so on a
    posterior whose uniqueness word is NOT_ASSESSED -- running the canonical ``MultistartPolicy()`` itself
    where a grid route is in play and the caller supplied none. A call that passes a rebuild policy together
    with ``multistart=None`` asks for the rebuild while declining the search, which is the audited shape.
    There is no production caller of ``route_uncertainty`` at all today, which is what makes this LATENT.
    """
    hits = []
    for path, text in (sources or _production_sources()).items():
        code = _strip_comments_and_strings(text)
        for line, call in _call_spans(code, r"\broute_uncertainty\s*(?=\()"):
            if "rebuild" not in call:
                continue
            if "multistart=None" in call.replace(" ", "") or "multistart" not in call:
                hits.append(f"{path}:{line}: {' '.join(call.split())[:70]}")
    return sorted(hits)


_RUNNERS = {
    "RAW_POSTERIOR_GRID_CONSUMER": raw_posterior_grid_consumers,
    "ASSESS_VALIDITY_WITHOUT_RECORD_VALUES": assessments_without_record_values,
    "TO_CHECK_OUTSIDE_THE_GATE": to_check_outside_the_gate,
    "ROUTE_UNCERTAINTY_REBUILD_WITHOUT_MULTISTART": rebuild_without_multistart,
}


def _test_exists(reference: str) -> bool:
    path, _, name = reference.partition("::")
    file = ROOT / path
    if not file.exists():
        return False
    return not name or f"def {name}(" in file.read_text(encoding="utf-8")


def verify(*, ledger: Mapping | None = None) -> list[str]:
    """Every finding about the ledger and the tree, or an empty list.

    Returns rather than raises, so a caller can report all of them at once: a verifier that stopped at the
    first finding would make a reader fix them one commit at a time.
    """
    findings: list[str] = []
    if ledger is None:
        if not LEDGER_PATH.exists():
            return [f"{LEDGER_PATH.relative_to(ROOT).as_posix()} does not exist"]
        ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    reached_by_problem = {p["id"]: p["reached_in_production"] for p in audit["problems"]}

    rows = list(ledger.get("guards", ()))
    if not rows:
        findings.append("the ledger declares no guards")
    declared_bypasses: set[str] = set()
    allow_lists: dict[str, list[str]] = {name: [] for name in BYPASS_CHECKS}

    for row in rows:
        problem = row.get("problem", "<unnamed>")
        status = row.get("status")
        if status not in STATUSES:
            findings.append(f"{problem}: status {status!r} is not one of {list(STATUSES)}")
        if not str(row.get("why", "")).strip():
            findings.append(f"{problem}: no reason given for status {status!r}")
        rule = str(row.get("rule", "")).strip()
        if not rule or not (ROOT / rule).exists():
            findings.append(f"{problem}: rule path {rule!r} does not exist")
        for key in ("exercised_by", "exercised_by_in_library"):
            for reference in row.get(key, ()) or ():
                if not _test_exists(reference):
                    findings.append(f"{problem}: {key} names {reference!r}, which does not exist")
        if status in ("REACHED", "LIBRARY_ONLY") and not (row.get("entry_points") or ()):
            findings.append(f"{problem}: {status} names no production entry point")
        if status == "REACHED" and not (row.get("exercised_by") or ()):
            findings.append(f"{problem}: REACHED names no test that exercises it in production")
        if status == "LIBRARY_ONLY" and not str(row.get("closed_by", "")).startswith("I-"):
            findings.append(
                f"{problem}: LIBRARY_ONLY is a finding and must name the improvement that closes it")
        if status == "LATENT" and not str(row.get("what_would_create_it", "")).strip():
            findings.append(f"{problem}: LATENT must say what would create the shape it guards")
        # The rule that makes the ledger worth having.
        if row.get("audit_status") == "FIXED" and status not in ("REACHED", "LATENT"):
            findings.append(
                f"{problem}: audit_status FIXED with reach {status} -- a fix to a rule production does not "
                f"reach is not a fix to a production problem")
        declared = row.get("audit_reached_in_production")
        expected = reached_by_problem.get(problem)
        if expected is not None and declared != expected:
            findings.append(
                f"{problem}: audit_reached_in_production {declared!r} disagrees with the audit's "
                f"{expected!r}")
        for name in row.get("bypasses", ()) or ():
            if name not in BYPASS_CHECKS:
                findings.append(f"{problem}: names bypass {name!r}, which this checker does not implement")
            declared_bypasses.add(name)
        reasons = row.get("bypass_allow_list_reasons") or {}
        for name, entries in (row.get("bypass_allow_lists") or {}).items():
            if name not in BYPASS_CHECKS:
                findings.append(f"{problem}: allow-list for unknown bypass {name!r}")
                continue
            for entry in entries:
                if not isinstance(entry, str) or not entry.strip():
                    findings.append(f"{problem}: empty allow-list entry for {name}")
                    continue
                # An allow-list entry is a hole in a guard. The preregistered rule is that each one
                # carries a reason, because a path on a list nobody justified is the defect this
                # ledger is about, one level up.
                if not str(reasons.get(entry, "")).strip():
                    findings.append(
                        f"{problem}: allow-list entry {entry!r} for {name} gives no reason")
                if not (ROOT / entry).exists():
                    findings.append(
                        f"{problem}: allow-list entry {entry!r} for {name} does not exist")
                allow_lists[name].append(entry)

    missing = set(BYPASS_CHECKS) - declared_bypasses
    if missing:
        findings.append(
            f"this checker implements {sorted(missing)}, which no ledger row declares -- a guard nobody "
            f"declared is the defect this ledger is about")

    for name, runner in _RUNNERS.items():
        hits = runner(allowed=allow_lists[name]) if name in (
            "RAW_POSTERIOR_GRID_CONSUMER", "ASSESS_VALIDITY_WITHOUT_RECORD_VALUES") else runner()
        for hit in hits:
            findings.append(f"{name}: {hit}")
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    findings = verify()
    if findings:
        print("guard reach ledger: FINDINGS")
        for finding in findings:
            print(f"  {finding}")
        return 1
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    rows = ledger["guards"]
    by_status: dict[str, list[str]] = {}
    for row in rows:
        by_status.setdefault(row["status"], []).append(row["problem"])
    print(f"guard reach ledger: clean over {len(rows)} guard(s)")
    for status in STATUSES:
        if status in by_status:
            print(f"  {status}: {sorted(by_status[status])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
