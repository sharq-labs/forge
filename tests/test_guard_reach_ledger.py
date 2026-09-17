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


@pytest.mark.xfail(strict=True, reason="I-16 not implemented yet (batch 19 preregistration)")
def test_i16_the_ledger_exists_and_is_a_row_per_guard_family():
    assert LEDGER.exists(), f"{LEDGER} declares which guards production reaches"
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    rows = {row["problem"]: row for row in ledger["guards"]}
    assert {"R-02", "R-09", "R-21", "R-43", "R-58"} <= set(rows), sorted(rows)
    for row in rows.values():
        assert row["status"] in {"REACHED", "LIBRARY_ONLY", "LATENT"}, row
        assert row["why"].strip(), row
        assert row["rule"].strip() and (ROOT / row["rule"]).exists(), row


@pytest.mark.xfail(strict=True, reason="I-16 not implemented yet (batch 19 preregistration)")
def test_i16_the_verifier_agrees_with_the_ledger_as_committed():
    """The whole of the improvement, in one call: the tree as it stands has no undeclared bypass."""
    verifier = _verifier()
    assert verifier is not None, "tools.certification.guard_reach exists"
    findings = verifier.verify()
    assert findings == [], findings


@pytest.mark.xfail(strict=True, reason="I-16 not implemented yet (batch 19 preregistration)")
def test_i16_the_two_problems_this_round_fixed_are_recorded_as_reached():
    verifier = _verifier()
    assert verifier is not None, "tools.certification.guard_reach exists"
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    rows = {row["problem"]: row for row in ledger["guards"]}
    for problem in ("R-02", "R-09"):
        assert rows[problem]["audit_status"] == "FIXED", rows[problem]
        assert rows[problem]["status"] in {"REACHED", "LATENT"}, rows[problem]


@pytest.mark.xfail(strict=True, reason="I-16 not implemented yet (batch 19 preregistration)")
def test_i16_the_three_it_did_not_fix_say_so_and_name_their_improvement():
    assert LEDGER.exists(), f"{LEDGER} declares which guards production reaches"
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    rows = {row["problem"]: row for row in ledger["guards"]}
    for problem in ("R-21", "R-43", "R-58"):
        assert rows[problem]["status"] == "LIBRARY_ONLY", rows[problem]
        assert rows[problem]["closed_by"].startswith("I-"), rows[problem]


@pytest.mark.xfail(strict=True, reason="I-16 not implemented yet (batch 19 preregistration)")
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


@pytest.mark.xfail(strict=True, reason="I-16 not implemented yet (batch 19 preregistration)")
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


@pytest.mark.xfail(strict=True, reason="I-16 not implemented yet (batch 19 preregistration)")
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
@pytest.mark.xfail(strict=True, reason="I-16 not implemented yet (batch 19 preregistration)")
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


@pytest.mark.xfail(strict=True, reason="I-16 not implemented yet (batch 19 preregistration)")
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


@pytest.mark.xfail(strict=True, reason="I-16 not implemented yet (batch 19 preregistration)")
def test_i16_an_assessment_without_record_values_fails_the_build():
    """Batch 14's one-off scan, promoted into a checker that runs on every commit."""
    verifier = _verifier()
    assert verifier is not None, "tools.certification.guard_reach exists"
    assert verifier.assessments_without_record_values(allowed=()) != []
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    allowed = _allowed(ledger, "ASSESS_VALIDITY_WITHOUT_RECORD_VALUES")
    assert verifier.assessments_without_record_values(allowed=allowed) == [], (
        verifier.assessments_without_record_values(allowed=allowed))


@pytest.mark.xfail(strict=True, reason="I-16 not implemented yet (batch 19 preregistration)")
def test_i16_an_unwrapped_to_check_outside_the_gate_fails_the_build():
    """The mcp call is level-WITHHELD, which is the mitigation; unwrapping it must fail."""
    verifier = _verifier()
    assert verifier is not None, "tools.certification.guard_reach exists"
    assert verifier.to_check_outside_the_gate() == [], verifier.to_check_outside_the_gate()
    unwrapped = "    return (consensus.to_check(name=CROSS_SOLVER_CHECK_NAME),)\n"
    assert verifier.to_check_outside_the_gate(
        sources={"src/engcore/mcp/problem.py": unwrapped}
    ) != []


@pytest.mark.xfail(strict=True, reason="I-16 not implemented yet (batch 19 preregistration)")
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


def _allowed(ledger, check: str) -> tuple[str, ...]:
    for row in ledger["guards"]:
        for name, entries in (row.get("bypass_allow_lists") or {}).items():
            if name == check:
                return tuple(entries)
    return ()
