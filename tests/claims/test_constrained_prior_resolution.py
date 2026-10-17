"""Review 3 A2-F10: a constrained prior supports a discrepancy demand only when something resolves it.

Before: ``model_discrepancy_check`` passed any CONSTRAINED_PRIOR whose
``reference`` was a non-empty string, and nothing ever looked the reference up,
so ``reference="doi:10.0/t3-prior"`` turned a claim that demanded supported
discrepancy from INSUFFICIENT_EVIDENCE into SUPPORTED. The end-to-end form of
that is in ``test_claims_assessment.py``; this file holds the rule itself:

- the SRIA helper treats a prior exactly like an unsupported zero until its
  caller passes what the prior was resolved to;
- the claims runtime resolves a prior to one thing only -- the MODEL_FORM
  interval the run's own model-form study promoted under a pinned producer
  qualification, filed as the evidence's MODEL_FORM channel;
- the compiler stops predicting a prior as supported unless that study is
  part of the plan.
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from claims_support import battery_inputs, claim, t3_claim
from engcore.claims import (
    CapabilityRegistry,
    ClaimTarget,
    GapKind,
    QuantityOfInterest,
    UncertaintyCapability,
    UncertaintyDemand,
    assess_claim,
    compile_claim,
)
from engcore.claims.assessment import resolved_prior
from engcore.claims.uq_studies import StudyOutcome
from engcore.mcp.capabilities import production_registry
from engcore.scientific.ir.constraints import ConstraintOperator
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind, UncertaintySource
from engcore.scientific.units.quantity import Quantity
from engcore.sria.assurance import budget_from_declaration, model_discrepancy_check
from engcore.sria.assurance.assessment import CriticVerdict, FindingImpact
from engcore.sria.uncertainty import (
    DiscrepancyKind,
    ModelDiscrepancy,
    SubjectModel,
    UncertaintyChannel,
    UncertaintyDeclaration,
)

PRIOR = ModelDiscrepancy(DiscrepancyKind.CONSTRAINED_PRIOR, reference="doi:10.0/anything", rationale="bounded")
DIGEST = "ab" * 32


def _budget(discrepancy: ModelDiscrepancy):
    declaration = UncertaintyDeclaration(subject_model=SubjectModel.PREDICTION_MODEL, discrepancy=discrepancy)
    return budget_from_declaration("q", declaration)


def _model_form(half_width: float = 0.05) -> Uncertainty:
    return Uncertainty(
        kind=UncertaintyKind.INTERVAL,
        lower=Quantity(3.9 - half_width, "volt"),
        upper=Quantity(3.9 + half_width, "volt"),
        method="authorized held-out discrepancy",
        source_kind=UncertaintySource.MODEL_FORM,
    )


def _study(*, trusted: bool = True, problem: str | None = None, digest: str | None = DIGEST) -> dict:
    return {
        "channel": UncertaintyChannel.MODEL_FORM.value,
        "kind": "model_form_empirical",
        "problem": problem,
        "qualification_trusted": trusted,
        "qualification_digest": digest,
    }


def _evidence(channels: dict) -> SimpleNamespace:
    return SimpleNamespace(
        uncertainty=UncertaintyDeclaration(
            subject_model=SubjectModel.PREDICTION_MODEL, discrepancy=PRIOR, channels=channels
        )
    )


# ---------------------------------------------------------------------------
# The SRIA helper
# ---------------------------------------------------------------------------


def test_an_unresolved_prior_is_inconclusive_like_an_unsupported_zero() -> None:
    prior, prior_findings = model_discrepancy_check(_budget(PRIOR), mandatory=True)
    zero, _ = model_discrepancy_check(_budget(ModelDiscrepancy(DiscrepancyKind.ZERO_DECLARED)), mandatory=True)
    assert prior.outcome is CriticVerdict.INCONCLUSIVE is zero.outcome
    (finding,) = prior_findings
    assert finding.code == "domain.constrained_prior_unresolved"
    assert finding.impact is FindingImpact.ASSURANCE_BLOCKING and finding.invalidates_subject is False
    assert "doi:10.0/anything" in finding.message


def test_a_prior_passes_only_on_what_its_caller_resolved_it_to() -> None:
    record, findings = model_discrepancy_check(
        _budget(PRIOR), supported_by="model_form_qualification:x", mandatory=True
    )
    assert record.outcome is CriticVerdict.PASS and findings == ()
    # The record names what supported it and says the citation itself was not checked (review finding F2).
    assert "supported by model_form_qualification:x" in record.detail
    assert "'doi:10.0/anything' was not itself checked" in record.detail


def test_a_contradicted_prior_still_fails() -> None:
    record, findings = model_discrepancy_check(
        _budget(PRIOR), supported_by="anything", contradicted_by="held-out data disagrees", mandatory=True
    )
    assert record.outcome is CriticVerdict.FAIL and findings[0].invalidates_subject is True


# ---------------------------------------------------------------------------
# What the claims runtime resolves a prior to
# ---------------------------------------------------------------------------


def test_a_promoted_model_form_interval_under_a_pinned_qualification_resolves_the_prior() -> None:
    interval = _model_form()
    studies = StudyOutcome((_study(),), {UncertaintyChannel.MODEL_FORM: interval})
    resolution = resolved_prior(
        t3_claim(discrepancy=PRIOR), _evidence({UncertaintyChannel.MODEL_FORM: interval}), studies
    )
    assert resolution.startswith(f"model_form_qualification:{DIGEST}")


@pytest.mark.parametrize(
    "studies, filed, why",
    [
        (None, {}, "no study ran"),
        (StudyOutcome((_study(),), {}), {}, "the study quantified nothing"),
        (StudyOutcome((_study(trusted=False),), {UncertaintyChannel.MODEL_FORM: _model_form()}), None, "unpinned qualification"),
        (StudyOutcome((_study(problem="stopped"),), {UncertaintyChannel.MODEL_FORM: _model_form()}), None, "the study stopped"),
        (StudyOutcome((_study(digest=None),), {UncertaintyChannel.MODEL_FORM: _model_form()}), None, "no qualification"),
        (StudyOutcome((_study(),), {UncertaintyChannel.MODEL_FORM: _model_form()}), {UncertaintyChannel.MODEL_FORM: _model_form(0.5)}, "evidence carries another interval"),
    ],
)
def test_nothing_else_resolves_a_prior(studies, filed, why) -> None:
    if filed is None:
        filed = dict(studies.channel_records)
    assert resolved_prior(t3_claim(discrepancy=PRIOR), _evidence(filed), studies) == "", why


def test_a_resolution_never_lends_itself_to_a_declared_zero() -> None:
    interval = _model_form()
    studies = StudyOutcome((_study(),), {UncertaintyChannel.MODEL_FORM: interval})
    zero = ModelDiscrepancy(DiscrepancyKind.ZERO_DECLARED, rationale="stated")
    assert resolved_prior(t3_claim(discrepancy=zero), _evidence({UncertaintyChannel.MODEL_FORM: interval}), studies) == ""


# ---------------------------------------------------------------------------
# What the compiler predicts
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def model_form_registry():
    """The battery capability with MODEL_FORM declared for open-circuit voltage, so the study can be planned."""
    base = production_registry()
    battery = base.get("system.battery")
    quantified = {k: set(v) for k, v in battery.uncertainty.quantified.items()}
    quantified["open_circuit_voltage"] = quantified.get("open_circuit_voltage", set()) | {UncertaintyChannel.MODEL_FORM}
    battery = replace(battery, uncertainty=UncertaintyCapability(quantified, battery.uncertainty.basis))
    return CapabilityRegistry([battery if d.capability_id == "system.battery" else d for d in base])


def _ocv_claim(channels: frozenset) -> object:
    return claim(
        statement="The open-circuit voltage stays below 4.0 V.",
        qoi=QuantityOfInterest("open_circuit_voltage", "volt"),
        operator=ConstraintOperator.LESS_THAN,
        target=ClaimTarget(value=Quantity(4.0, "volt")),
        operating_context={},
        known_inputs=battery_inputs(),
        uncertainty=UncertaintyDemand(channels, None, True),
        discrepancy=PRIOR,
    )


def _gaps(compiled) -> set:
    return {g.kind for g in compiled.predicted_gaps}


def test_a_prior_is_predicted_unsupported_unless_the_plan_runs_a_model_form_study(model_form_registry) -> None:
    t3 = compile_claim(t3_claim(uncertainty=UncertaintyDemand(frozenset(), None, True), discrepancy=PRIOR), production_registry())
    assert GapKind.DISCREPANCY_UNSUPPORTED in _gaps(t3)
    with_study = compile_claim(_ocv_claim(frozenset({UncertaintyChannel.MODEL_FORM})), model_form_registry)
    assert GapKind.DISCREPANCY_UNSUPPORTED not in _gaps(with_study)
    # the production battery declaration cannot plan the study, so the prior stays predicted unsupported there
    production = compile_claim(_ocv_claim(frozenset({UncertaintyChannel.MODEL_FORM})), production_registry())
    assert GapKind.DISCREPANCY_UNSUPPORTED in _gaps(production)


def test_a_discrepancy_demand_with_a_prior_implies_the_model_form_channel(model_form_registry) -> None:
    """Review finding F3: a claim that also names MODEL_FORM -- strictly more demanding -- planned the study and
    could be SUPPORTED where the same claim without it never could. The demand now implies the channel, so the two
    are one claim and asking for more cannot firm up the answer."""
    implied, named = _ocv_claim(frozenset()), _ocv_claim(frozenset({UncertaintyChannel.MODEL_FORM}))
    assert UncertaintyChannel.MODEL_FORM in implied.uncertainty.required_channels
    assert implied.to_dict() == named.to_dict()
    assert type(implied).from_dict(implied.to_dict()) == implied
    assert _gaps(compile_claim(implied, model_form_registry)) == _gaps(compile_claim(named, model_form_registry))
    a, b = (assess_claim(c, model_form_registry).to_dict() for c in (implied, named))
    assert a["verdict"] == b["verdict"] == "insufficient_evidence"
    # Nothing else implies a channel: a zero or unknown declaration, or a prior nobody demanded support for.
    for discrepancy, require in (
        (ModelDiscrepancy(DiscrepancyKind.ZERO_DECLARED, rationale="stated"), True),
        (ModelDiscrepancy(DiscrepancyKind.UNKNOWN, rationale="stated"), True),
        (PRIOR, False),
    ):
        made = t3_claim(uncertainty=UncertaintyDemand(frozenset(), None, require), discrepancy=discrepancy)
        assert made.uncertainty.required_channels == frozenset()
