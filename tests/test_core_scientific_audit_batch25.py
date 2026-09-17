"""Batch 25 of the 2026-09-16 core re-audit: how a cross-solver level is earned (I-12 part B).

Part A corrected what KIND of evidence cross-solver agreement is. **R-21** is three separate claims about how
the level is earned and what a disagreement is worth:

* **(a)** hand-written consensus evidence lines earn the level and survive a result round trip. ALREADY
  CLOSED, by VAL-01's `_consensus_issuer_gap`, and pinned here so the closure cannot be lost.
* **(b)** `TrustedConsensusGate` -- the only thing in the tree that requires BYTE-VERIFIED artifact
  independence -- has no caller. The one production consensus check is minted in `engcore.mcp.problem` from
  `consensus.to_check(...)` and never reaches the gate.
* **(c)** routes 33% apart that are not verified independent give WARNING, and the verdict stays SUPPORTED.

The improvement's own brief says the added basis is ADDITIVE, and that is the shape of this part: the
artifact-verified basis is added beside the declared one, every check carrying the level has to say WHICH
basis it rests on, and the production path is routed through the gate.

Preregistered in `benchmarks/core_v4_false_confidence/BATCH25_THRESHOLD_PROTOCOL.json`. No threshold: one
outcome reclassified, one required declaration with two enumerated values, and a call site moved.

The ten reproductions that reproduced were committed as strict xfails in `09e78111`, before any of part B
was written, and each was confirmed there to fail on its own assertion. The markers came off in the
implementing commit. The other three held already and were unmarked at preregistration.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib

import pytest

from engcore.execution.consensus import TrustedConsensusGate
from engcore.scientific.errors import ScientificValidationError
from engcore.scientific.results.validation import (
    ValidationCheck,
    ValidationLevel,
    ValidationOutcome,
    ValidationReport,
)
from tests.route_declarations_for_tests import (  # noqa: F401 - autouse fixture
    route_declarations_for_tests,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _prefix():
    """The required basis line's prefix, asserted rather than assumed."""
    from engcore.scientific import consensus as module

    value = getattr(module, "INDEPENDENCE_BASIS_EVIDENCE_PREFIX", None)
    assert value is not None, (
        "engcore.scientific.consensus.INDEPENDENCE_BASIS_EVIDENCE_PREFIX is what part B adds")
    return value


def _basis_lines(check):
    prefix = _prefix()
    return [line[len(prefix):] for line in check.evidence if line.startswith(prefix)]


def _shared_disagreement():
    """Two routes that share a dependency and report 1.0 against 1.5 for the same quantity."""
    from test_cross_solver_consensus import ALPHA, BETA, _consensus, _route

    return _consensus((_route("a", ALPHA, "shared"), _route("b", BETA, "shared")),
                      {"a": {"x": 1.0}, "b": {"x": 1.5}})


def _independent_pair(*, agree=True):
    from test_trusted_consensus_gate import _consensus, _evidence_for

    consensus = _consensus(agree=agree)
    evidence, artifact_bytes = _evidence_for(consensus)
    return consensus, evidence, artifact_bytes


# =====================================================================
# R-21 (a): already closed, and pinned so it stays closed
# =====================================================================
def test_r21_a_hand_written_check_cannot_carry_the_level():
    """VAL-01 closed this before this batch. It is pinned here because R-21 names it.

    `ValidationCheck(PASS, establishes=CROSS_SOLVER_VALIDATED, evidence=("trust me",))` was attained and
    survived a round trip. It is now refused at construction: the level has no verifiable issuer.
    """
    with pytest.raises(ScientificValidationError, match="no verifiable issuer"):
        ValidationCheck("forged", ValidationOutcome.PASS,
                        establishes=ValidationLevel.CROSS_SOLVER_VALIDATED,
                        residual=1e-6, tolerance=1e-3, evidence=("trust me",))


# =====================================================================
# R-21 (c): a disagreement is a finding whether or not the routes are independent
# =====================================================================
def test_r21_a_disagreement_between_non_independent_routes_fails_rather_than_warns():
    """Awarding a level and reporting a disagreement are not the same authority."""
    check = _shared_disagreement().to_check()
    assert check.outcome is ValidationOutcome.FAIL, check.detail
    assert check.residual == pytest.approx(1.0 / 3.0)


def test_r21_the_verdict_no_longer_stays_supported_over_such_a_disagreement():
    report = ValidationReport(checks=(_shared_disagreement().to_check(),))
    assert report.status is ValidationOutcome.FAIL
    # FAIL is what every consumer reads as "do not rely on this": the MCP verdict, the execution gate's
    # `_attested_run_reached_a_usable_end`, and the SRIA components all key on the status word.
    assert [check.name for check in report.failures] == ["cross_solver_agreement"], report.failures
    assert report.attained_levels == frozenset(), report.attained_levels


# Already held at the baseline and unmarked at preregistration: a disagreement establishes nothing in either
# direction, and a stricter OUTCOME must not become a claim. Kept because that is the one thing this change
# could get wrong.
def test_r21_a_disagreement_still_establishes_nothing():
    consensus = _shared_disagreement()
    assert consensus.establishes is None
    assert consensus.to_check().establishes is None


# Already held at the baseline and unmarked at preregistration: agreement between routes that share their
# machinery is still a PASS that establishes nothing. The outcome and the level are allowed to disagree, and
# this batch changes only the disagreement branch.
def test_r21_agreement_between_non_independent_routes_is_still_a_pass_that_earns_nothing():
    from test_cross_solver_consensus import ALPHA, BETA, _consensus, _route

    consensus = _consensus((_route("a", ALPHA, "shared"), _route("b", BETA, "shared")),
                           {"a": {"x": 1.0}, "b": {"x": 1.0}})
    check = consensus.to_check()
    assert check.outcome is ValidationOutcome.PASS
    assert check.establishes is None


# =====================================================================
# R-21 (a)/(b): every level says which independence basis it rests on
# =====================================================================
def test_r21_the_consensus_names_the_declared_basis_it_rests_on():
    consensus, _evidence, _bytes = _independent_pair()
    check = consensus.to_check()
    assert check.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED, check.detail
    assert _basis_lines(check) == ["declared"], check.evidence


def test_r21_the_gate_names_the_artifact_verified_basis_when_the_bytes_agree():
    consensus, evidence, artifact_bytes = _independent_pair()
    decision = TrustedConsensusGate().assess(consensus, evidence, artifact_bytes=artifact_bytes)
    assert decision.independence.strongly_independent, decision.independence.reason
    assert decision.check.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED, decision.check.detail
    assert _basis_lines(decision.check) == ["artifact-verified"], decision.check.evidence


def test_r21_the_gate_withholds_the_level_when_no_artifact_evidence_is_offered():
    from engcore.mcp.problem import WITHHELD_LEVEL_EVIDENCE_PREFIX

    consensus, _evidence, _bytes = _independent_pair()
    decision = TrustedConsensusGate().assess(consensus, ())
    assert decision.independence.strongly_independent is False
    assert decision.check.establishes is None, decision.check.detail
    assert _basis_lines(decision.check) == [], decision.check.evidence
    # ADDED while running batch 25's guard mutations, not preregistered. B25g removed the gate's record of
    # the level it NEARLY awarded and survived, because the idempotence test below reaches `_withhold_level`
    # with a check that still CARRIES the level -- so the line it asserts is the boundary's, not the gate's.
    # What a run came within one artifact digest of establishing has to reach a reader structurally, which
    # is R-04's finding, here one layer up.
    withheld = [line[len(WITHHELD_LEVEL_EVIDENCE_PREFIX):] for line in decision.check.evidence
                if line.startswith(WITHHELD_LEVEL_EVIDENCE_PREFIX)]
    assert withheld == [ValidationLevel.CROSS_SOLVER_VALIDATED.value], decision.check.evidence


def test_r21_a_check_claiming_the_level_without_a_basis_is_refused():
    """The rule is enforced where the level becomes a claim, the way VAL-01's threshold record is."""
    consensus, _evidence, _bytes = _independent_pair()
    check = consensus.to_check()
    prefix = _prefix()
    # Refused at the constructor, which is where VAL-01's threshold record is refused too -- so the level
    # never reaches a report at all. The rule is re-applied on the report for a check nobody constructed.
    with pytest.raises(ScientificValidationError, match="no verifiable issuer"):
        dataclasses.replace(
            check, evidence=tuple(line for line in check.evidence if not line.startswith(prefix)))


def test_r21_two_basis_lines_are_not_a_basis_either():
    consensus, _evidence, _bytes = _independent_pair()
    check = consensus.to_check()
    with pytest.raises(ScientificValidationError, match="no verifiable issuer"):
        dataclasses.replace(check, evidence=(*check.evidence, f"{_prefix()}artifact-verified"))


# =====================================================================
# R-21 (b): the production path goes through the gate
# =====================================================================
def test_r21_the_production_cross_solver_check_is_built_by_the_gate():
    """The gate stops being a rule with no caller: it is what the MCP electrothermal route now uses."""
    import inspect

    from engcore.mcp import problem as module

    source = inspect.getsource(module)
    assert "TrustedConsensusGate" in source, (
        "engcore.mcp.problem builds its cross-solver check through the gate")
    assert "_withhold_level(consensus.to_check(" not in source, (
        "the production path no longer mints the check from the consensus alone")


def test_r21_withholding_a_level_nobody_awarded_adds_no_second_line_and_no_second_sentence():
    """Two rules withhold the level for two different reasons, and neither may say it twice."""
    from engcore.mcp.problem import WITHHELD_LEVEL_EVIDENCE_PREFIX, _withhold_level

    consensus, _evidence, _bytes = _independent_pair()
    once = _withhold_level(consensus.to_check())
    twice = _withhold_level(once)
    assert twice.evidence == once.evidence
    assert twice.detail == once.detail
    assert sum(1 for line in once.evidence
               if line.startswith(WITHHELD_LEVEL_EVIDENCE_PREFIX)) == 1, once.evidence


# =====================================================================
# The ledger moves with the fix
# =====================================================================
def test_r21_the_guard_reach_ledger_records_the_gate_as_reached():
    """A fix that reaches production and leaves the ledger saying LIBRARY_ONLY is a fix nobody can check."""
    from tools.certification import guard_reach

    ledger = json.loads((ROOT / "certification" / "guard_reach_ledger.json").read_text(encoding="utf-8"))
    row = next(entry for entry in ledger["guards"] if entry["problem"] == "R-21")
    assert row["status"] == "REACHED", row
    assert row["audit_status"] == "FIXED", row
    assert row["exercised_by"], row
    assert guard_reach.verify() == [], guard_reach.verify()
