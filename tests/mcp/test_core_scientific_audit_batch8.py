"""Batch 8 of the 2026-09-16 core re-audit: qualify SUPPORTED where agents read it (I-09, part A of two).

Closes the adoption half of R-04 -- every SUPPORTED verdict either MCP tool can return is VERIFICATION_ONLY
by construction, and the block an agent reads first never said so -- and R-47, where the exported
``derive_verdict`` read ``passed`` and ``establishes`` off any object. Preregistered in
`benchmarks/core_v4_false_confidence/BATCH8_THRESHOLD_PROTOCOL.json`.

R-04's issuer half (a registered reference id and digest for ANALYTICALLY_VERIFIED) is batch 9: it moves the
one SUPPORTED report on the production MCP path and needs the hard benchmark re-scored.

Every test here was committed as `xfail(strict=True)` first and run with `--runxfail` at 763c37b to watch it
fail; the markers came off in the implementation commit, and the xfail commit is 03da331. What each failed on there, recorded so the evidence
is not overstated: 3 on an assertion (the production `means` prose, the empty `other_findings`, and the rule
table naming the convergence gap only as an unnamed NOT_RUN check), 5 on ``DID NOT RAISE`` (the refusals this
batch adds, which is an assertion about a refusal that is absent), and 7 on a ``KeyError``/``TypeError`` for a
block key, field or argument that did not exist at 763c37b. ``test_r47_a_real_check_is_unaffected`` already
held and carries no xfail: it is the guard that every genuine ValidationCheck gives the same answer as before.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from engcore.mcp.battery import example_battery_payload
from engcore.mcp.errors import CredibilityEvidenceError
from engcore.mcp.evidence import (
    CredibilityEvidenceReport,
    CredibilityVerdict,
    ModelValidityRecord,
    derive_verdict,
)
from engcore.mcp.problem import example_electrothermal_payload, run_electrothermal_case
from engcore.mcp.server import describe_capabilities, run_battery, run_electrothermal
from engcore.scientific.models.definition import ValidityAssessment, ValidityStatus
from engcore.scientific.results.validation import (
    ValidationCheck,
    ValidationLevel,
    ValidationOutcome,
)


def _electrothermal_stage():
    response = run_electrothermal(example_electrothermal_payload())
    return response["stages"][0]


def _supported_report():
    """The production electrothermal report: SUPPORTED on `analytically_verified` alone."""
    report = run_electrothermal_case(example_electrothermal_payload(), run_id="batch8").reports[0]
    assert report.verdict is CredibilityVerdict.SUPPORTED
    assert report.validation_report().evidence_basis == "VERIFICATION_ONLY"
    return report


# =====================================================================
# R-04: the block an agent reads first
# =====================================================================
def test_r04_the_verdict_block_names_its_evidence_basis():
    """The audited record: 'evidence_basis' or 'verification' in verdict block: False False."""
    block = _electrothermal_stage()["verdict"]
    assert block["value"] == "supported"
    assert block["evidence_basis"] == "VERIFICATION_ONLY"
    assert block["attained_levels"] == ["analytically_verified"]


def test_r04_a_verification_only_support_does_not_read_as_validation():
    """The audited `means`: 'Nothing in this report argues against relying on the result, and at least one
    check both passed and established an evidentiary level.' Nothing in it says the levels attained compare
    the model only with itself."""
    block = _electrothermal_stage()["verdict"]
    prose = " ".join(str(block[key]) for key in ("means", "does_not_mean", "action"))
    assert "verification" in prose.lower() or "solved correctly" in prose.lower()
    assert "not" in prose.lower() and ("world" in prose.lower() or "reality" in prose.lower()
                                       or "measurement" in prose.lower())


def test_r04_a_withheld_level_is_recorded_where_a_reader_finds_it():
    """The MCP problem runner strips the level off its only cross-solver check on purpose, and the reason
    reached a reader only inside a detail sentence.

    Exercised on ``_withhold_level`` and a report around its output rather than through a production run:
    the cross-solver route needs the external ngspice provider, which this batch's environment cannot
    launch (see the expensive tier's recorded baseline), and the rule under test is the recording, not the
    route.
    """
    from engcore.mcp.problem import _withhold_level

    # DIMENSIONALLY_VALID and not the production case's CROSS_SOLVER_VALIDATED, because VAL-01 refuses a
    # hand-built check claiming that level -- only a pinned consensus can write its record -- which is
    # itself the rule this batch leaves in place. What is under test is the recording of a withheld level,
    # and that rule is the same whichever level is withheld.
    genuine = ValidationCheck(name="cross_solver", outcome=ValidationOutcome.PASS,
                              establishes=ValidationLevel.DIMENSIONALLY_VALID,
                              residual=1e-9, tolerance=1e-6, evidence=("two independent routes",))
    stripped = _withhold_level(genuine)
    assert stripped.establishes is None
    assert f"level-withheld:{ValidationLevel.DIMENSIONALLY_VALID.value}" in stripped.evidence
    assert "two independent routes" in stripped.evidence, "the issuer's own account still reaches the reader"

    report = _supported_report()
    carrying = CredibilityEvidenceReport(
        run_id=report.run_id, values=dict(report.values), provenance=report.provenance,
        validity=report.validity, validation=(*report.validation, stripped),
        contributing_models=report.contributing_models, coupling=report.coupling,
        convergence=report.convergence)
    assert carrying.levels_withheld == (("cross_solver", ValidationLevel.DIMENSIONALLY_VALID.value),)
    wire = json.loads(json.dumps(carrying.to_dict()))
    assert wire["verdict_qualifiers"]["levels_withheld"] == [
        ["cross_solver", ValidationLevel.DIMENSIONALLY_VALID.value]]


def test_r04_the_block_carries_the_warnings_supported_absorbs():
    block = _electrothermal_stage()["verdict"]
    assert isinstance(block["warning_checks"], list)


def test_r04_a_non_deciding_verification_only_rule_fires():
    """The audited record: verdict_reasons [] and other_findings [] on a VERIFICATION_ONLY SUPPORTED."""
    block = _electrothermal_stage()["verdict"]
    rules = {entry["rule"]: entry for entry in block["other_findings"]}
    assert "verification_only" in rules, block["other_findings"]
    assert rules["verification_only"]["produces"] is None


def test_r04_describe_capabilities_explains_the_evidence_basis():
    """The audited record: 'evidence_basis' anywhere in describe_capabilities: False."""
    capabilities = describe_capabilities()
    supported = [v for v in capabilities["verdicts"] if v["value"] == "supported"][0]
    bases = {entry["evidence_basis"]: entry for entry in supported["by_evidence_basis"]}
    assert set(bases) == {"VALIDATED", "VERIFICATION_ONLY", "NONE"}
    for entry in bases.values():
        assert entry["means"] and entry["does_not_mean"] and entry["action"]
    assert bases["VALIDATED"]["means"] != bases["VERIFICATION_ONLY"]["means"]


def test_r04_a_caller_can_demand_a_basis_it_did_not_get():
    report = _supported_report()
    demanding = CredibilityEvidenceReport(
        run_id=report.run_id, values=dict(report.values), provenance=report.provenance,
        validity=report.validity, validation=report.validation,
        contributing_models=report.contributing_models, coupling=report.coupling,
        convergence=report.convergence, required_evidence_basis="VALIDATED")
    assert demanding.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE
    assert demanding.missing_evidence_basis == "VALIDATED"


def test_r04_demanding_the_basis_a_report_has_changes_nothing():
    report = _supported_report()
    for basis in ("VERIFICATION_ONLY", "NONE"):
        demanding = CredibilityEvidenceReport(
            run_id=report.run_id, values=dict(report.values), provenance=report.provenance,
            validity=report.validity, validation=report.validation,
            contributing_models=report.contributing_models, coupling=report.coupling,
            convergence=report.convergence, required_evidence_basis=basis)
        assert demanding.verdict is CredibilityVerdict.SUPPORTED, basis


def test_r04_derive_verdict_reads_a_required_basis_on_its_own():
    validity = [ModelValidityRecord(model_id="m", version="1",
                                    assessment=ValidityAssessment(status=ValidityStatus.IN_DOMAIN,
                                                                  satisfied=("c",)))]
    verified = [ValidationCheck(name="analytic", outcome=ValidationOutcome.PASS,
                                establishes=ValidationLevel.ANALYTICALLY_VERIFIED,
                                residual=1e-9, tolerance=1e-6)]
    assert derive_verdict(validity=validity, validation=verified) is CredibilityVerdict.SUPPORTED
    assert derive_verdict(validity=validity, validation=verified,
                          required_evidence_basis="VERIFICATION_ONLY") is CredibilityVerdict.SUPPORTED
    assert derive_verdict(validity=validity, validation=verified,
                          required_evidence_basis="VALIDATED") is CredibilityVerdict.INSUFFICIENT_EVIDENCE


def test_r04_a_payload_with_the_evidence_basis_removed_is_refused():
    """The audited record: _require_qualifiers_as_derived compares only the keys present, so a report JSON
    with evidence_basis -- or the whole verdict_qualifiers -- removed is accepted."""
    payload = json.loads(json.dumps(_supported_report().to_dict()))
    stripped = json.loads(json.dumps(payload))
    del stripped["verdict_qualifiers"]["evidence_basis"]
    with pytest.raises(CredibilityEvidenceError, match="evidence_basis"):
        CredibilityEvidenceReport.from_dict(stripped)
    without = json.loads(json.dumps(payload))
    del without["verdict_qualifiers"]
    with pytest.raises(CredibilityEvidenceError, match="verdict_qualifiers"):
        CredibilityEvidenceReport.from_dict(without)
    # the unedited record still reads
    assert CredibilityEvidenceReport.from_dict(payload).verdict is CredibilityVerdict.SUPPORTED


def test_r04_the_battery_verdict_block_is_qualified_too():
    block = run_battery(example_battery_payload())["verdict"]
    assert block["evidence_basis"] in ("VALIDATED", "VERIFICATION_ONLY", "NONE")
    assert isinstance(block["attained_levels"], list)


# =====================================================================
# R-47: the exported verdict function trusted any object
# =====================================================================
def test_r47_derive_verdict_refuses_a_duck_typed_check():
    """The audited record: a SimpleNamespace claiming EXPERIMENTALLY_VALIDATED satisfies required_levels and
    returns SUPPORTED, while ValidationReport refuses the same object."""
    validity = [ModelValidityRecord(model_id="m", version="1",
                                    assessment=ValidityAssessment(status=ValidityStatus.IN_DOMAIN,
                                                                  satisfied=("c",)))]
    claimed = SimpleNamespace(outcome=ValidationOutcome.PASS, passed=True,
                              establishes=ValidationLevel.EXPERIMENTALLY_VALIDATED,
                              residual=None, tolerance=None, evidence=("trust me",), name="claimed")
    with pytest.raises(CredibilityEvidenceError):
        derive_verdict(validity=validity, validation=[claimed],
                       required_levels=[ValidationLevel.EXPERIMENTALLY_VALIDATED])


def test_r47_derive_verdict_refuses_an_object_missing_the_fields_the_rule_reads():
    validity = [ModelValidityRecord(model_id="m", version="1",
                                    assessment=ValidityAssessment(status=ValidityStatus.IN_DOMAIN,
                                                                  satisfied=("c",)))]
    thin = SimpleNamespace(outcome=ValidationOutcome.PASS, passed=True,
                           establishes=ValidationLevel.DIMENSIONALLY_VALID)
    with pytest.raises(CredibilityEvidenceError):
        derive_verdict(validity=validity, validation=[thin])


def test_r47_a_pass_with_a_level_and_nothing_compared_establishes_nothing():
    """GUARD 2's rule, re-applied here rather than taken from the object: the core's ValidationReport already
    refuses this check, and derive_verdict read it as an attained level."""
    validity = [ModelValidityRecord(model_id="m", version="1",
                                    assessment=ValidityAssessment(status=ValidityStatus.IN_DOMAIN,
                                                                  satisfied=("c",)))]
    claimed = SimpleNamespace(name="claimed", outcome=ValidationOutcome.PASS, passed=True,
                              establishes=ValidationLevel.NUMERICALLY_CONVERGED,
                              residual=None, tolerance=None, evidence=())
    with pytest.raises(CredibilityEvidenceError):
        derive_verdict(validity=validity, validation=[claimed])


def test_r47_a_real_check_is_unaffected():
    """The route that must keep working: every genuine ValidationCheck gives the same answer as before."""
    validity = [ModelValidityRecord(model_id="m", version="1",
                                    assessment=ValidityAssessment(status=ValidityStatus.IN_DOMAIN,
                                                                  satisfied=("c",)))]
    real = ValidationCheck(name="analytic", outcome=ValidationOutcome.PASS,
                           establishes=ValidationLevel.ANALYTICALLY_VERIFIED, residual=1e-9, tolerance=1e-6)
    assert derive_verdict(validity=validity, validation=[real]) is CredibilityVerdict.SUPPORTED
    assert derive_verdict(validity=validity, validation=[real],
                          required_levels=[ValidationLevel.ANALYTICALLY_VERIFIED]) is CredibilityVerdict.SUPPORTED


# =====================================================================
# I-10's named rule, completed here
# =====================================================================
def test_the_rule_table_names_a_solver_that_did_not_finish():
    from engcore.mcp.server import _fired_rules

    report = _supported_report()
    unfinished = SimpleNamespace(
        verdict=CredibilityVerdict.INSUFFICIENT_EVIDENCE, coupling=report.coupling,
        validity=report.validity, validation=report.validation, run_id=report.run_id,
        violated_conditions=(), failed_checks=(), not_run_checks=("solver_did_not_converge",),
        unassessed_models=(), unattributed_assessments=(), attained_levels=report.attained_levels,
        missing_required_levels=(), warning_checks=(), levels_withheld=(),
        missing_evidence_basis=None, evidence_basis="VERIFICATION_ONLY",
        convergence=__import__("engcore.scientific.solvers.protocol",
                               fromlist=["ConvergenceState"]).ConvergenceState.DIVERGED,
        validation_report=report.validation_report)
    rules = {entry["rule"]: entry for entry in _fired_rules(unfinished)}
    assert "solver_did_not_converge" in rules
    assert rules["solver_did_not_converge"]["produces"] == "insufficient_evidence"
    assert rules["solver_did_not_converge"]["detail"]["convergence"] == "diverged"
