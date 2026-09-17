"""Batch 19 of the 2026-09-16 core re-audit: the reach claim, made checkable (I-16).

This improvement fixes nothing about the science. It makes the REACH CLAIM checkable, which is this round's
central finding: the guards were not wrong, they were written where production does not go.

* `engcore.hybrid_uq` -- every V2 evidence gate the audit built -- had no caller in `src` outside its own
  package (R-02, fixed in batches 17-18).
* `record_values` had no caller at all, so the CORE-014 binding looped over an empty mapping on every
  production path (R-09, fixed in batch 14).
* `TrustedConsensusGate`, which requires byte-verified artifact independence before
  CROSS_SOLVER_VALIDATED, has no caller (R-21, open -- I-12).
* `UncertaintySource` has no producer, so `source_kind` is UNSPECIFIED on everything production makes
  (R-43, open -- I-25).
* The production electrothermal coupling passes bare point values and `UncertaintyTransfer` has no caller
  (R-58, open -- I-27).

`certification/guard_reach_ledger.json` declares, per guard family, whether a production entry point reaches
it; `tools/certification/guard_reach.py` refuses a ledger that is not self-consistent and implements the four
static bypass checks the audit names. Preregistered in
`benchmarks/core_v4_false_confidence/BATCH19_THRESHOLD_PROTOCOL.json`.

These reproductions were committed as strict xfails in `67aadd85`, before any of I-16 was written, and
each one was confirmed to fail on its own assertion there. The markers came off in the implementing
commit; one test was amended against its preregistered form and says so in its own docstring.
"""

from __future__ import annotations

import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
LEDGER = ROOT / "certification" / "guard_reach_ledger.json"


def _verifier():
    """Imported by name, so a reproduction fails on its own assertion."""
    import importlib

    try:
        return importlib.import_module("tools.certification.guard_reach")
    except ModuleNotFoundError:
        return None


def test_i16_the_ledger_exists_and_is_a_row_per_guard_family():
    assert LEDGER.exists(), f"{LEDGER} declares which guards production reaches"
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    rows = {row["problem"]: row for row in ledger["guards"]}
    assert {"R-02", "R-09", "R-21", "R-43", "R-58"} <= set(rows), sorted(rows)
    for row in rows.values():
        assert row["status"] in {"REACHED", "LIBRARY_ONLY", "LATENT"}, row
        assert row["why"].strip(), row
        assert row["rule"].strip() and (ROOT / row["rule"]).exists(), row


def test_i16_the_verifier_agrees_with_the_ledger_as_committed():
    """The whole of the improvement, in one call: the tree as it stands has no undeclared bypass."""
    verifier = _verifier()
    assert verifier is not None, "tools.certification.guard_reach exists"
    findings = verifier.verify()
    assert findings == [], findings


def test_i16_the_two_problems_this_round_fixed_are_recorded_as_reached():
    verifier = _verifier()
    assert verifier is not None, "tools.certification.guard_reach exists"
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    rows = {row["problem"]: row for row in ledger["guards"]}
    for problem in ("R-02", "R-09"):
        assert rows[problem]["audit_status"] == "FIXED", rows[problem]
        assert rows[problem]["status"] in {"REACHED", "LATENT"}, rows[problem]


def test_i16_the_three_it_did_not_fix_say_so_and_name_their_improvement():
    assert LEDGER.exists(), f"{LEDGER} declares which guards production reaches"
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    rows = {row["problem"]: row for row in ledger["guards"]}
    # R-21 left this list in batch 25: I-12 part B routed the production MCP path through
    # TrustedConsensusGate, so the gate stopped being a rule with no caller and the row moved to REACHED.
    # That is the ledger working -- a fix that reaches production and leaves the row saying LIBRARY_ONLY is
    # a fix nobody can check -- and it is why this test names the rows rather than counting them.
    for problem in ("R-43", "R-58"):
        assert rows[problem]["status"] == "LIBRARY_ONLY", rows[problem]
        assert rows[problem]["closed_by"].startswith("I-"), rows[problem]
    assert rows["R-21"]["status"] == "REACHED", rows["R-21"]


def test_i16_a_fixed_row_that_is_only_a_library_guard_is_refused():
    """The rule that makes the ledger worth having: a fix to an unreached rule is not a fix."""
    verifier = _verifier()
    assert verifier is not None, "tools.certification.guard_reach exists"
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    tampered = json.loads(json.dumps(ledger))
    for row in tampered["guards"]:
        if row["problem"] == "R-09":
            row["status"] = "LIBRARY_ONLY"
            row["closed_by"] = "I-11"
    findings = verifier.verify(ledger=tampered)
    assert any("R-09" in f and "FIXED" in f for f in findings), findings


def test_i16_a_row_whose_test_does_not_exist_is_refused():
    verifier = _verifier()
    assert verifier is not None, "tools.certification.guard_reach exists"
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    tampered = json.loads(json.dumps(ledger))
    tampered["guards"][0]["exercised_by"] = [
        "tests/test_nothing_here.py::test_that_does_not_exist"
    ]
    findings = verifier.verify(ledger=tampered)
    assert any("test_that_does_not_exist" in f for f in findings), findings


def test_i16_a_row_that_disagrees_with_the_audit_is_refused():
    verifier = _verifier()
    assert verifier is not None, "tools.certification.guard_reach exists"
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    tampered = json.loads(json.dumps(ledger))
    for row in tampered["guards"]:
        if row["problem"] == "R-09":
            row["audit_reached_in_production"] = "library-only"
    findings = verifier.verify(ledger=tampered)
    assert any("reached_in_production" in f for f in findings), findings


# =====================================================================
# The four static bypass checks the audit names
# =====================================================================
def test_i16_the_four_bypass_checks_are_implemented_and_all_declared():
    verifier = _verifier()
    assert verifier is not None, "tools.certification.guard_reach exists"
    implemented = set(verifier.BYPASS_CHECKS)
    assert implemented == {
        "RAW_POSTERIOR_GRID_CONSUMER",
        "ASSESS_VALIDITY_WITHOUT_RECORD_VALUES",
        "TO_CHECK_OUTSIDE_THE_GATE",
        "ROUTE_UNCERTAINTY_REBUILD_WITHOUT_MULTISTART",
    }, sorted(implemented)
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    declared = {name for row in ledger["guards"] for name in row.get("bypasses", ())}
    assert declared == implemented, sorted(declared ^ implemented)


def test_i16_an_undeclared_raw_posterior_grid_consumer_fails_the_build():
    verifier = _verifier()
    assert verifier is not None, "tools.certification.guard_reach exists"
    hits = verifier.raw_posterior_grid_consumers(allowed=())
    paths = {hit.split(":")[0] for hit in hits}
    assert "src/engcore/uq/predictive.py" in paths, sorted(paths)
    assert "src/engcore/hybrid_uq/predictive.py" in paths, sorted(paths)
    # and with the ledger's own allow-list nothing is left
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    allowed = _allowed(ledger, "RAW_POSTERIOR_GRID_CONSUMER")
    assert verifier.raw_posterior_grid_consumers(allowed=allowed) == [], (
        verifier.raw_posterior_grid_consumers(allowed=allowed))


def test_i16_an_assessment_without_record_values_fails_the_build():
    """Batch 14's one-off scan, promoted into a checker that runs on every commit.

    AMENDED against its preregistered form, and recorded as amendment 1 in BATCH19's protocol. The
    preregistration asserted that the tree as it stands has at least one hit and that the ledger's
    allow-list clears it. Neither half is true and both are good news: batch 14's I-11 closed every
    domain site, and `domains/derived_context.py` -- the one entry the preregistration expected on the
    allow-list -- forwards `record_values=record_values`, so the checker sees the name and the site is
    not a hit. The allow-list is therefore empty, and detection is shown on an INJECTED source, the way
    the `to_check` and rebuild reproductions below already had to be written. Asserting a hit in the
    tree would have been asserting that a fixed defect stays broken.
    """
    verifier = _verifier()
    assert verifier is not None, "tools.certification.guard_reach exists"
    assert verifier.assessments_without_record_values(allowed=()) == [], (
        verifier.assessments_without_record_values(allowed=()))
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    assert _allowed(ledger, "ASSESS_VALIDITY_WITHOUT_RECORD_VALUES") == (), (
        "an allow-list entry that is not needed is a hole nobody would notice")
    bypass = (
        "def assess():\n"
        "    return MODEL.assess_validity(declared={}, assembled=context())\n"
    )
    hits = verifier.assessments_without_record_values(
        allowed=(), sources={"src/engcore/domains/electrical/dc/models.py": bypass}
    )
    assert hits != [], "the checker must find an assessment that never considered the question"
    # and the same site, having considered it, is not a hit
    considered = bypass.replace("assembled=context()", "assembled=context(), record_values=True")
    assert verifier.assessments_without_record_values(
        allowed=(), sources={"src/engcore/domains/electrical/dc/models.py": considered}
    ) == []


def test_i16_an_unwrapped_to_check_outside_the_gate_fails_the_build():
    """The mcp call is level-WITHHELD, which is the mitigation; unwrapping it must fail."""
    verifier = _verifier()
    assert verifier is not None, "tools.certification.guard_reach exists"
    assert verifier.to_check_outside_the_gate() == [], verifier.to_check_outside_the_gate()
    unwrapped = "    return (consensus.to_check(name=CROSS_SOLVER_CHECK_NAME),)\n"
    assert verifier.to_check_outside_the_gate(
        sources={"src/engcore/mcp/problem.py": unwrapped}
    ) != []


def test_i16_a_rebuild_without_a_multistart_fails_the_build():
    """LATENT today: there is no production caller of `route_uncertainty` at all."""
    verifier = _verifier()
    assert verifier is not None, "tools.certification.guard_reach exists"
    assert verifier.rebuild_without_multistart() == []
    bypass = (
        "def run():\n"
        "    return route_uncertainty(calibration, observations, forward,\n"
        "                             rebuild=GridRebuildPolicy(), multistart=None)\n"
    )
    assert verifier.rebuild_without_multistart(
        sources={"src/engcore/mcp/problem.py": bypass}
    ) != []


# =====================================================================
# Every refusal the verifier implements, exercised once
# =====================================================================
# ADDED while running batch 19's guard mutations, not preregistered. Thirteen of the verifier's refusals
# had no reproduction at all: removing them left the whole suite green, so those mutations SURVIVED. A
# surviving mutation is a finding, and this is the guard the finding asked for. The reproductions above
# cover the refusals the preregistration named; this covers the rest of them, one tamper each, so a rule
# deleted from `verify` fails a test rather than quietly widening what the ledger may say.


def _tamper_status(ledger):
    _row(ledger, "R-02")["status"] = "REACHED_ISH"
    return "is not one of"


def _tamper_why(ledger):
    _row(ledger, "R-02")["why"] = "   "
    return "no reason given"


def _tamper_rule(ledger):
    _row(ledger, "R-02")["rule"] = "src/engcore/hybrid_uq/no_such_module.py"
    return "rule path"


def _tamper_entry_points(ledger):
    _row(ledger, "R-02")["entry_points"] = []
    return "names no production entry point"


def _tamper_exercised_by(ledger):
    _row(ledger, "R-02")["exercised_by"] = []
    return "names no test that exercises it"


def _tamper_closed_by(ledger):
    # R-43 rather than R-21, which stopped being LIBRARY_ONLY when I-12 part B landed (batch 25). The rule
    # under test only applies to a row that IS LIBRARY_ONLY.
    _row(ledger, "R-43")["closed_by"] = ""
    return "must name the improvement"


def _tamper_what_would_create_it(ledger):
    _row(ledger, "R-01")["what_would_create_it"] = ""
    return "what would create"


def _tamper_unknown_bypass(ledger):
    _row(ledger, "R-01")["bypasses"] = ["A_CHECK_NOBODY_WROTE"]
    return "does not implement"


def _tamper_undeclared_bypass(ledger):
    _row(ledger, "R-21")["bypasses"] = []
    return "no ledger row declares"


def _tamper_allow_list_reason(ledger):
    _row(ledger, "R-02")["bypass_allow_list_reasons"] = {}
    return "gives no reason"


def _tamper_allow_list_path(ledger):
    row = _row(ledger, "R-02")
    row["bypass_allow_lists"]["RAW_POSTERIOR_GRID_CONSUMER"].append("src/engcore/gone.py")
    row["bypass_allow_list_reasons"]["src/engcore/gone.py"] = "a module that was deleted under the list"
    return "does not exist"


def _tamper_no_guards(ledger):
    ledger["guards"] = []
    return "declares no guards"


TAMPERS = {
    "bad-status": _tamper_status,
    "no-why": _tamper_why,
    "missing-rule": _tamper_rule,
    "no-entry-point": _tamper_entry_points,
    "reached-with-no-test": _tamper_exercised_by,
    "library-only-with-no-improvement": _tamper_closed_by,
    "latent-with-no-shape": _tamper_what_would_create_it,
    "unknown-bypass": _tamper_unknown_bypass,
    "undeclared-bypass": _tamper_undeclared_bypass,
    "allow-list-without-a-reason": _tamper_allow_list_reason,
    "allow-list-path-that-does-not-exist": _tamper_allow_list_path,
    "no-guards": _tamper_no_guards,
}


@pytest.mark.parametrize("case", sorted(TAMPERS))
def test_i16_each_refusal_is_exercised(case):
    verifier = _verifier()
    assert verifier is not None, "tools.certification.guard_reach exists"
    tampered = json.loads(json.dumps(
        json.loads(LEDGER.read_text(encoding="utf-8"))))
    expected = TAMPERS[case](tampered)
    findings = verifier.verify(ledger=tampered)
    assert any(expected in finding for finding in findings), (case, expected, findings)


def _row(ledger, problem: str):
    for row in ledger["guards"]:
        if row["problem"] == problem:
            return row
    raise AssertionError(f"{problem} is not in the ledger")


def _allowed(ledger, check: str) -> tuple[str, ...]:
    for row in ledger["guards"]:
        for name, entries in (row.get("bypass_allow_lists") or {}).items():
            if name == check:
                return tuple(entries)
    return ()
