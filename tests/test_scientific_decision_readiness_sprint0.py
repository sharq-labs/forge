"""Sprint 0 — structural pins for decision-to-evidence closure.

These are strict expected failures, not implementation tests.  They encode
surviving audit findings without prescribing the concrete adapter/class that
will eventually close them.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from engcore.scientific import oracles
from engcore.sria.assurance.arbiter import Arbiter


@pytest.mark.xfail(
    strict=True,
    reason=(
        "SDR-01: production Scientific Core/MCP does not yet bridge into SRIA "
        "evidence/decision assurance"
    ),
)
def test_sdr01_production_tree_has_a_sria_bridge() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "engcore"
    imports: list[str] = []
    patterns = (
        re.compile(r"\bfrom\s+engcore\.sria\b"),
        re.compile(r"\bimport\s+engcore\.sria\b"),
        re.compile(r"\bfrom\s+\.\.sria\b"),
        re.compile(r"\bfrom\s+\.sria\b"),
    )

    for path in root.rglob("*.py"):
        # The bridge must be outside SRIA; SRIA importing itself proves nothing.
        if "sria" in path.relative_to(root).parts:
            continue
        source = path.read_text(encoding="utf-8")
        if any(pattern.search(source) for pattern in patterns):
            imports.append(str(path.relative_to(root)))

    assert imports, (
        "no production module outside src/engcore/sria imports SRIA; "
        "ScientificResult/CredibilityEvidenceReport cannot currently enter "
        "the SRIA evidence/decision path"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "SDR-03: obligations_from_charter records required ValidationLevel "
        "tokens, but Arbiter.decide explicitly cannot evaluate them"
    ),
)
def test_sdr03_arbiter_can_evaluate_charter_validation_levels() -> None:
    source = inspect.getsource(Arbiter.decide)
    assert "validation-level obligations are recorded but not evaluated" not in source
    assert "obligation {target} is not evaluable in M3" not in source


@pytest.mark.xfail(
    strict=True,
    reason=(
        "SDR-06: production trusted-oracle authority is intentionally empty "
        "until reviewed external evidence is admitted"
    ),
)
def test_sdr06_production_has_reviewed_trusted_external_oracle() -> None:
    registry = oracles._TRUSTED_ORACLE_DECLARATIONS
    assert registry, (
        "the trusted production oracle registry is empty; benchmark and "
        "experimental validation are representable but no external oracle "
        "currently has repository-pinned authority"
    )


# ---------------------------------------------------------------------------
# Pass 2 — executable production traces
# ---------------------------------------------------------------------------

import dataclasses

from engcore.mcp import (
    CredibilityVerdict,
    example_electrothermal_payload,
    run_electrothermal_case,
)
from engcore.mcp.battery import example_battery_payload, run_battery_case


def test_sdr04_verification_only_support_cannot_satisfy_a_validated_use() -> None:
    """The MCP layer already owns the right fail-closed evidence-basis rule.

    This is a CLOSED sub-invariant of SDR-04 and must survive the future bridge:
    a numerically credible result is not silently upgraded to evidence that the
    model matches the world.
    """
    outcome = run_electrothermal_case(example_electrothermal_payload())
    report = outcome.reports[0]

    assert report.verdict is CredibilityVerdict.SUPPORTED
    assert report.evidence_basis == "VERIFICATION_ONLY"

    decision_grade = dataclasses.replace(
        report,
        required_evidence_basis="VALIDATED",
    )
    assert (
        decision_grade.verdict
        is CredibilityVerdict.INSUFFICIENT_EVIDENCE
    )
    assert decision_grade.missing_evidence_basis == "VALIDATED"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "SDR-05: the production battery report emits quantitative values but "
        "does not yet carry per-value uncertainty declarations"
    ),
)
def test_sdr05_battery_quantitative_values_close_the_uncertainty_chain() -> None:
    """Every quantitative value used by a later claim needs an uncertainty state.

    UNKNOWN is acceptable.  Silence is not: an absent entry cannot be mapped
    honestly into SRIA's decomposed uncertainty budget without inventing what
    the solver never declared.
    """
    report = run_battery_case(example_battery_payload()).report

    missing = sorted(set(report.values) - set(report.uncertainty))
    assert not missing, (
        "battery report has quantitative values with no uncertainty record: "
        f"{missing}"
    )


from engcore.sria import (
    ClaimBinding,
    ClaimType,
    DiscrepancyKind,
    Evidence,
    ModelDiscrepancy,
    SourceClass,
    SubjectModel,
    UncertaintyDeclaration,
)


def _audit_uncertainty() -> UncertaintyDeclaration:
    """Minimal explicit declaration for structural evidence-identity probes."""
    return UncertaintyDeclaration(
        subject_model=SubjectModel.PREDICTION_MODEL,
        discrepancy=ModelDiscrepancy(kind=DiscrepancyKind.ZERO_DECLARED),
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "SDR-02: evidence content identity includes context_ref but belief_key "
        "does not, so different contexts currently share one contribution key"
    ),
)
def test_sdr02_belief_key_separates_different_contexts() -> None:
    base = dict(
        source_class=SourceClass.SIMULATION,
        claim_type=ClaimType.QOI_VALUE,
        claim_binding=ClaimBinding(subject_kind="qoi", subject_ref="temperature"),
        claim_payload={"value": 350.0, "units": "kelvin"},
        uncertainty=_audit_uncertainty(),
        provenance_ref="run-1",
        domain_pack_ref="thermal",
    )
    screening = Evidence(
        evidence_id="screening",
        context_ref="context:screening",
        **base,
    )
    certification = Evidence(
        evidence_id="certification",
        context_ref="context:certification",
        **base,
    )

    # Context already changes scientific-content identity: that part is good.
    assert screening.content_hash != certification.content_hash

    # The surviving gap: contribution grouping is still context-blind.
    assert screening.belief_key != certification.belief_key


@pytest.mark.xfail(
    strict=True,
    reason=(
        "SDR-07: Evidence has no first-class dependency/ancestor closure, so "
        "two derived records cannot prove whether they share observations"
    ),
)
def test_sdr07_evidence_records_source_dependency_closure() -> None:
    fields = Evidence.__dataclass_fields__
    dependency_fields = {
        name
        for name in fields
        if any(token in name for token in ("depend", "ancestor", "parent", "source_record"))
    }
    assert dependency_fields, (
        "Evidence records provenance_ref but no first-class evidence ancestry; "
        "shared source observations cannot be detected generically"
    )
