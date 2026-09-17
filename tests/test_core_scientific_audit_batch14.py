"""Batch 14 of the 2026-09-16 core re-audit: the operating-point binding, load-bearing (I-11, R-09, R-50).

CORE-014 bound an assessment to the values its conditions read. Batch 3b built the binding; this batch makes
it fire.

* **R-09** (reached in production) -- `record_values` defaults to False and NOTHING in src passes True, so
  every production assessment has an empty `evaluated` and the check in `ScientificResult` loops over
  nothing: a result whose provenance says alpha = -1e-5 m^2/s -- anti-diffusion, which the model's own
  condition forbids -- carries an IN_DOMAIN assessment made at +1e-5, constructs, and reports SUPPORTED. The
  model API cannot opt in either, because `assess_validity` has no such parameter. And when a caller does
  opt in, `ModelValidityRecord` rebuilds the assessment WITHOUT `evaluated`, so every credibility report
  loses the operating point -- which is where both production MCP tools form their verdict.
* **R-50** -- a `ValidityAssessment` carries no model id and no record of which conditions its domain
  decided, so an IN_DOMAIN assessment with `satisfied=('anything_at_all',)` is accepted by
  `ScientificResult`, round-trips, and reaches `Experiment.best`, the inference admission gate and
  `validity_of`. The MCP boundary added the check, but only there and only for models it can resolve.

Preregistered in `benchmarks/core_v4_false_confidence/BATCH14_THRESHOLD_PROTOCOL.json`, which also records
the one DECISION-NEEDED this improvement reaches (D-14-1: what an assessment whose condition values cannot be
bound to the provenance should count as).

Ten of these were audited reproductions, recorded as `xfail(strict=True)` in commit **3f957a94** and
confirmed there to fail ON THEIR OWN ASSERTIONS against the pre-batch tree (10 failed, 1 passed under
`--runxfail`). The markers came off with the implementation.
`test_r50_an_assessment_written_before_this_rule_is_still_accepted` was never marked: it is a
no-regression guard on records that predate the rule and it passes on both sides of the batch. The tests
after them are guards written against the new code, for the rules the reproductions do not reach by
themselves -- the report-side comparison, what it could not bind, and the serialized form.
"""

from __future__ import annotations

import json

import pytest

from engcore.scientific.models.definition import (
    RangeCondition,
    ScientificModelDefinition,
    ValidityAssessment,
    ValidityDomain,
    ValidityStatus,
)
from engcore.scientific.results.provenance import ProvenanceRecord
from engcore.scientific.results.result import ScientificResult
from engcore.scientific.units.quantity import Quantity

K = "kelvin"
ALPHA_UNIT = "meter ** 2 / second"
DOMAIN = ValidityDomain(conditions=(RangeCondition("T", minimum=Quantity(250.0, K), maximum=Quantity(400.0, K)),))
MODEL = ("batch14.model", "1")


def _definition():
    from engcore.scientific.models.definition import InputSourceKind, ModelInputSpec, ModelOutputSpec

    return ScientificModelDefinition(
        model_id=MODEL[0], version=MODEL[1], description="batch 14",
        inputs=(ModelInputSpec(name="T", unit_exemplar=K, source_kind=InputSourceKind.VARIABLE),),
        outputs=(ModelOutputSpec(metric="y", unit_exemplar="meter"),), validity=DOMAIN,
        exclusions=(), excludes_nothing_because="a fixture model with one range condition and one output")


def _takes_record_values() -> bool:
    """Whether the model API can opt in, read by name so a test fails on its own assertion."""
    import inspect

    return "record_values" in inspect.signature(ScientificModelDefinition.assess_validity).parameters


def _assessment_fields() -> frozenset[str]:
    import dataclasses

    return frozenset(f.name for f in dataclasses.fields(ValidityAssessment))


def _unknown_condition(name: str):
    from engcore.scientific.models.definition import UnknownCondition, UnknownReason

    return UnknownCondition(name=name, reason=UnknownReason.NOT_SUPPLIED)


def _result(assessment, temperature, *, models=(MODEL,), key=MODEL[0]):
    return ScientificResult(
        result_id="r", values={"y": Quantity(1.0, "meter")}, models=models, validity={key: assessment},
        provenance=ProvenanceRecord(run_id="r", models=models, inputs={"T": Quantity(temperature, K)}))


# =====================================================================
# R-09: the binding fires on the paths a verdict is formed on
# =====================================================================
def test_r09_the_model_api_can_opt_in():
    """Domains assess through `ScientificModelDefinition.assess_validity`, which had no way to opt in."""
    assert _takes_record_values(), "assess_validity takes record_values, so a domain can opt in"
    assessment = _definition().assess_validity({"T": Quantity(300.0, K)}, record_values=True)
    assert assessment.status is ValidityStatus.IN_DOMAIN
    assert assessment.evaluated.get("T") == Quantity(300.0, K), assessment.evaluated
    assert _definition().assess_validity({"T": Quantity(300.0, K)}).evaluated == {}, "the default is additive"


def test_r09_the_derived_context_records_its_operating_point_by_default():
    """The path battery, electrical and repair all assess through."""
    from engcore.domains.derived_context import DomainValidityContext

    context = DomainValidityContext(declared={"T": Quantity(300.0, K)}, assembled={})
    assessment = context.assess(_definition())
    assert assessment.evaluated.get("T") == Quantity(300.0, K), assessment.evaluated


def test_r09_the_production_conduction_models_record_their_operating_point():
    """The audited case: a result at alpha = -1e-5 with an assessment made at +1e-5 reads SUPPORTED.

    The conduction paths assess their own models directly rather than through the derived context, so the
    call sites are what have to pass the flag. The models and the value they read are the production ones.
    """
    from engcore.domains.thermal.conduction1d.problem import CONDUCTION_MODELS

    alpha = Quantity(1.0e-5, ALPHA_UNIT)
    for model in CONDUCTION_MODELS:
        assessment = model.validity.assess({"alpha": alpha}, record_values=True)
        assert assessment.evaluated.get("alpha") == alpha, (model.model_id, assessment.evaluated)
    # and the site itself: every direct `validity.assess(` under domains/ passes it
    import pathlib
    import re

    unflagged = []
    for path in pathlib.Path("src/engcore/domains").rglob("*.py"):
        if "/thermal/" in path.as_posix():
            continue  # SHA-256 pinned by the frozen thermal experiments; not edited
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"\.validity\.assess\((?![^()]*record_values)[^()]*\)", text, re.S):
            unflagged.append(f"{path.as_posix()}: {match.group(0)[:60]}")
    assert not unflagged, unflagged


def test_r09_the_report_keeps_the_operating_point():
    from engcore.mcp.evidence import ModelValidityRecord

    assessment = DOMAIN.assess({"T": Quantity(300.0, K)}, record_values=True)
    record = ModelValidityRecord(model_id="x", version="1", assessment=assessment)
    assert record.assessment.evaluated.get("T") == Quantity(300.0, K), record.assessment.evaluated
    payload = json.loads(json.dumps(record.to_dict()))
    assert ModelValidityRecord.from_dict(payload).assessment.evaluated.get("T") == Quantity(300.0, K)


# =====================================================================
# R-50: an assessment names the model and the conditions it assessed
# =====================================================================
def test_r50_the_domain_records_the_conditions_it_decided():
    assessment = DOMAIN.assess({"T": Quantity(300.0, K)})
    assert tuple(getattr(assessment, "declared_conditions", ())) == ("T",), assessment
    keyed = _definition().assess_validity({"T": Quantity(300.0, K)})
    assert getattr(keyed, "model_id", "") == MODEL[0] and getattr(keyed, "model_version", "") == MODEL[1]


def test_r50_an_assessment_over_conditions_the_model_does_not_have_is_refused():
    """The audited case: `satisfied=('anything_at_all',)` is accepted, round-trips and reaches `validity_of`."""
    assert "declared_conditions" in _assessment_fields(), "an assessment records the conditions it decided"
    stray = ValidityAssessment(status=ValidityStatus.IN_DOMAIN, satisfied=("anything_at_all",),
                               declared_conditions=("T",))
    with pytest.raises(Exception, match="(?i)anything_at_all|condition"):
        _result(stray, 300.0)


def test_r50_an_assessment_that_leaves_a_declared_condition_out_is_refused():
    assert "declared_conditions" in _assessment_fields(), "an assessment records the conditions it decided"
    partial = ValidityAssessment(status=ValidityStatus.IN_DOMAIN, satisfied=("T",),
                                 declared_conditions=("T", "pressure"))
    with pytest.raises(Exception, match="(?i)pressure|condition"):
        _result(partial, 300.0)


def test_r50_an_assessment_filed_under_another_model_is_refused():
    assert "model_id" in _assessment_fields(), "an assessment names the model it is about"
    assessment = _definition().assess_validity({"T": Quantity(300.0, K)})
    # The result declares ONLY the other model, so the mismatch is the single thing wrong with it.
    # A first draft declared both and passed on the "says nothing about whether they applied" rule
    # instead -- which a mutation of `assess_validity`'s model key survived, because the test was
    # never reading that key. (Guard mutation B14b, batch 14.)
    other = ("batch14.other", "1")
    with pytest.raises(Exception, match="carries an assessment of model 'batch14.model'"):
        _result(assessment, 300.0, models=(other,), key=other[0])


def test_r50_an_assessment_whose_version_is_not_the_declared_one_is_refused():
    assert "model_version" in _assessment_fields(), "an assessment names the model it is about"
    assessment = _definition().assess_validity({"T": Quantity(300.0, K)})
    with pytest.raises(Exception, match="(?i)version|2"):
        _result(assessment, 300.0, models=((MODEL[0], "2"),))


def test_r50_an_assessment_written_before_this_rule_is_still_accepted():
    """No-regression: a record with no declared_conditions and no model key carries no claim to check."""
    old = ValidityAssessment(status=ValidityStatus.IN_DOMAIN, satisfied=("T",))
    assert _result(old, 300.0).validity[MODEL[0]].status is ValidityStatus.IN_DOMAIN
    assert "declared_conditions" not in old.to_dict()
    assert "model_id" not in old.to_dict()


def test_r50_the_new_keys_round_trip_and_are_written_only_when_present():
    assert _takes_record_values(), "assess_validity takes record_values, so a domain can opt in"
    assessment = _definition().assess_validity({"T": Quantity(300.0, K)}, record_values=True)
    payload = json.loads(json.dumps(assessment.to_dict()))
    assert payload["declared_conditions"] == ["T"] and payload["model_id"] == MODEL[0]
    back = ValidityAssessment.from_dict(payload)
    assert tuple(back.declared_conditions) == ("T",) and back.model_id == MODEL[0]
    assert back.evaluated == assessment.evaluated


# =====================================================================
# Guards added while implementing, on the rules the reproductions above do not
# reach by themselves. Not reproductions: they were written against the new code
# rather than against the pre-batch tree, and every one of them is verified by
# its own mutation in `BATCH14_MUTATIONS.log`.
# =====================================================================
def _report(assessment, temperature, *, supplied=True):
    from engcore.mcp.evidence import CredibilityEvidenceReport, ModelValidityRecord

    provenance = ProvenanceRecord(run_id="r", models=(MODEL,), inputs={"T": Quantity(temperature, K)})
    record = ModelValidityRecord(model_id=MODEL[0], version=MODEL[1], assessment=assessment)
    return CredibilityEvidenceReport(
        run_id="r", values={"y": Quantity(1.0, "meter")}, provenance=provenance,
        validity=(record,) if supplied else (), contributing_models=(MODEL,))


def test_r09_the_report_refuses_a_supplied_assessment_made_at_another_operating_point():
    """The route both production MCP assemblers take: a record handed in, never checked."""
    from engcore.mcp.evidence import CredibilityEvidenceError

    assessment = DOMAIN.assess({"T": Quantity(300.0, K)}, record_values=True)
    with pytest.raises(CredibilityEvidenceError, match="another operating point"):
        _report(assessment, 380.0)


def test_r09_a_report_whose_assessment_agrees_with_its_provenance_is_still_assembled():
    """No-regression: the binding refuses a DISAGREEMENT, and agreement is the production case."""
    assessment = DOMAIN.assess({"T": Quantity(300.0, K)}, record_values=True)
    report = _report(assessment, 300.0)
    assert report.validity[0].assessment.evaluated["T"] == Quantity(300.0, K)
    assert report.unbound_assessment_values == ()


def test_r09_the_report_records_the_names_its_provenance_cannot_bind():
    """D-14-1's residual, stated in the record rather than left as silence."""
    assessment = DOMAIN.assess({"T": Quantity(300.0, K)}, record_values=True)
    provenance_without_it = _report(assessment, 300.0)
    assert provenance_without_it.unbound_assessment_values == ()
    from engcore.mcp.evidence import CredibilityEvidenceReport, ModelValidityRecord

    report = CredibilityEvidenceReport(
        run_id="r", values={"y": Quantity(1.0, "meter")},
        provenance=ProvenanceRecord(run_id="r", models=(MODEL,), inputs={"other": Quantity(1.0, K)}),
        validity=(ModelValidityRecord(model_id=MODEL[0], version=MODEL[1], assessment=assessment),),
        contributing_models=(MODEL,))
    assert report.unbound_assessment_values == ((MODEL[0], MODEL[1], "T"),)
    # and it lowers nothing (D-14-1 option (a)): the same report whose assessment recorded no value
    # at all reaches the identical verdict, so an unbound name is stated and not counted as a gap.
    without = CredibilityEvidenceReport(
        run_id="r", values={"y": Quantity(1.0, "meter")},
        provenance=ProvenanceRecord(run_id="r", models=(MODEL,), inputs={"other": Quantity(1.0, K)}),
        validity=(ModelValidityRecord(model_id=MODEL[0], version=MODEL[1],
                                      assessment=DOMAIN.assess({"T": Quantity(300.0, K)})),),
        contributing_models=(MODEL,))
    assert without.unbound_assessment_values == ()
    assert report.verdict is without.verdict


def test_r09_the_serialized_report_keeps_the_operating_point():
    from engcore.mcp.evidence import CredibilityEvidenceReport

    report = _report(DOMAIN.assess({"T": Quantity(300.0, K)}, record_values=True), 300.0)
    payload = json.loads(json.dumps(report.to_dict()))
    assert payload["validity"][0]["assessment"]["evaluated"]["T"]["magnitude"] == 300.0
    back = CredibilityEvidenceReport.from_dict(payload)
    assert back.validity[0].assessment.evaluated["T"] == Quantity(300.0, K)


def test_r50_an_assessment_that_reports_one_condition_twice_is_refused():
    both = ValidityAssessment(status=ValidityStatus.UNKNOWN, satisfied=("T",), unknown=("T",),
                              unknown_reasons=(_unknown_condition("T"),), declared_conditions=("T",))
    with pytest.raises(Exception, match="more than once"):
        _result(both, 300.0)


def test_r50_a_version_without_a_model_id_is_refused_on_the_assessment_itself():
    """A version alone names nothing and cannot be compared with the key it is filed under."""
    with pytest.raises(Exception, match="(?i)version and no model id"):
        ValidityAssessment(status=ValidityStatus.IN_DOMAIN, satisfied=("T",), model_version="1")


def test_r09_the_production_electrical_assessments_record_their_operating_point():
    """The other production family, read through its own entry points rather than by grep."""
    from engcore.domains.electrical.dc.models import assess_kcl_validity

    assessment = assess_kcl_validity()
    assert assessment.evaluated, assessment
    assert assessment.model_id and assessment.declared_conditions
