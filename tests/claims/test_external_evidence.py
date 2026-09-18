"""External evidence -- benchmark, measurement and literature evidence: ingested, judged, never promoted to validation."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from claims_support import t3_claim, t3_point
from engcore.claims import (
    AssessmentForgeryError,
    ClaimContractError,
    ExternalStanding,
    LiteratureRecord,
    MeasurementRecord,
    TrustedExternalRegistry,
    TrustedPin,
    assess_benchmark,
    assess_claim,
    assess_literature,
    assess_measurement,
    discover_oracles,
    verify_assessment,
)
from engcore.mcp.capabilities import production_registry
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind, UncertaintySource
from engcore.scientific.units.quantity import Quantity
from engcore.sria.evidence import IMPLEMENTED_SOURCE_CLASSES, SourceClass

K = "kelvin"
QOI = "temperature_at_probe"


@pytest.fixture(scope="module")
def registry():
    return production_registry()


def _interval(lo, hi, source=UncertaintySource.MEASUREMENT):
    return Uncertainty(kind=UncertaintyKind.INTERVAL, lower=Quantity(lo, K), upper=Quantity(hi, K), method="calibrated thermocouple, 95%", source_kind=source)


def _measurement(**kw):
    fields = dict(
        quantity=QOI, value=Quantity(309.76, K), uncertainty=_interval(309.66, 309.86), calibration_ref="cal:tc-17@2026-03",
        provenance_ref="lab:run-4411", conditions=dict(t3_point()), dataset_version="v2", observed_at="2026-04-02T10:00:00Z",
        independence_roots=("instrument:tc-17", "lab:thermal-a"),
    )
    fields.update(kw)
    return MeasurementRecord(**fields)


def _literature(**kw):
    fields = dict(
        citation_id="doi:10.0000/nafems.t3.reference", extracted_claim="T at x=0.08 m, t=32 s is 36.6 C",
        quantity=QOI, value=Quantity(309.75, K), uncertainty=_interval(309.70, 309.80, UncertaintySource.NUMERICAL),
        conditions=dict(t3_point()), extracted_by="curator:a", extraction_method="manual, table 3",
    )
    fields.update(kw)
    return LiteratureRecord(**fields)


def _pinned(*records, source=SourceClass.MEASUREMENT):
    return TrustedExternalRegistry(tuple(TrustedPin(r.digest, source, "curator:test", "reviewed") for r in records))


# ---------------------------------------------------------------------------
# Ingestion contracts
# ---------------------------------------------------------------------------


def test_every_source_class_now_has_an_ingestion_path() -> None:
    assert IMPLEMENTED_SOURCE_CLASSES == frozenset(SourceClass)


def test_records_round_trip_and_are_digest_identified() -> None:
    for record, cls in ((_measurement(), MeasurementRecord), (_literature(), LiteratureRecord)):
        back = cls.from_dict(json.loads(json.dumps(record.to_dict())))
        assert back == record and back.digest == record.digest
    assert _measurement().digest != _measurement(value=Quantity(309.77, K)).digest


def test_a_measurement_needs_calibration_and_provenance() -> None:
    with pytest.raises(ClaimContractError):
        _measurement(calibration_ref="  ")
    with pytest.raises(ClaimContractError):
        _measurement(provenance_ref="")


# ---------------------------------------------------------------------------
# Standing: the caller calling it a measurement is not enough
# ---------------------------------------------------------------------------


def test_an_unpinned_measurement_is_weak_however_good_it_looks() -> None:
    claim = t3_claim()
    result = assess_measurement(_measurement(), claim, context_ref="ctx", trust=TrustedExternalRegistry())
    assert result.standing is ExternalStanding.WEAK
    assert any("caller's statement" in r["reason"] for r in result.reasons)
    assert result.evidence.source_class is SourceClass.MEASUREMENT  # ingested as what it is, not as simulation
    assert result.comparison is None


def test_a_pinned_applicable_quantified_measurement_is_admissible_and_still_not_validation() -> None:
    claim = t3_claim()
    m = _measurement()
    result = assess_measurement(m, claim, context_ref="ctx", trust=_pinned(m), simulated=(Quantity(309.7501, K), (0.004, 0.004)))
    assert result.standing is ExternalStanding.ADMISSIBLE
    assert result.to_dict()["is_validation_level"] is False
    assert result.comparison["outcome"] == "consistent"
    far = assess_measurement(m, claim, context_ref="ctx", trust=_pinned(m), simulated=(Quantity(310.2, K), (0.004, 0.004)))
    assert far.comparison["outcome"] == "inconsistent"
    unknown_sim = assess_measurement(m, claim, context_ref="ctx", trust=_pinned(m), simulated=(Quantity(309.7501, K), None))
    assert unknown_sim.comparison["outcome"] == "undecided"


@pytest.mark.parametrize(
    "edit, standing, fragment",
    [
        (dict(quantity="final_temperature"), ExternalStanding.UNUSABLE, "not the claim's QOI"),
        (dict(value=Quantity(1.0, "meter")), ExternalStanding.UNUSABLE, "value is"),
        (dict(conditions={**t3_point(), "conductivity": Quantity(40.0, "watt / meter / kelvin")}), ExternalStanding.UNUSABLE, "another operating point"),
        (dict(uncertainty=_interval(309.66, 309.86, UncertaintySource.PARAMETER)), ExternalStanding.UNUSABLE, "attributed to MEASUREMENT"),
        (dict(uncertainty=Uncertainty.unknown("not reported")), ExternalStanding.WEAK, "UNKNOWN"),
        (dict(conditions={}), ExternalStanding.WEAK, "no operating conditions"),
    ],
    ids=["other_qoi", "other_dimension", "other_point", "misattributed", "unknown_uncertainty", "no_conditions"],
)
def test_a_pinned_measurement_falls_short_for_exactly_the_stated_reason(edit, standing, fragment) -> None:
    m = _measurement(**edit)
    result = assess_measurement(m, t3_claim(), context_ref="ctx", trust=_pinned(m))
    assert result.standing is standing
    assert any(fragment in r["reason"] for r in result.reasons)


def test_unstated_claim_conditions_leave_applicability_unknown() -> None:
    m = _measurement()
    point = dict(t3_point())
    point.pop("conductivity")
    result = assess_measurement(m, t3_claim(operating_context=point), context_ref="ctx", trust=_pinned(m))
    assert result.standing is ExternalStanding.WEAK


def test_a_pin_for_another_source_class_does_not_trust_the_record() -> None:
    m = _measurement()
    result = assess_measurement(m, t3_claim(), context_ref="ctx", trust=_pinned(m, source=SourceClass.LITERATURE))
    assert result.standing is ExternalStanding.WEAK


def test_literature_is_never_validation_and_is_weak_without_value_or_uncertainty() -> None:
    lit = _literature()
    ok = assess_literature(lit, t3_claim(), context_ref="ctx", trust=_pinned(lit, source=SourceClass.LITERATURE))
    assert ok.standing is ExternalStanding.ADMISSIBLE and ok.to_dict()["is_validation_level"] is False
    assert ok.evidence.source_class is SourceClass.LITERATURE
    for weak in (_literature(value=None), _literature(uncertainty=Uncertainty.unknown("not reported"))):
        r = assess_literature(weak, t3_claim(), context_ref="ctx", trust=_pinned(weak, source=SourceClass.LITERATURE))
        assert r.standing is ExternalStanding.WEAK
    unpinned = assess_literature(lit, t3_claim(), context_ref="ctx", trust=TrustedExternalRegistry())
    assert unpinned.standing is ExternalStanding.WEAK


def test_a_benchmark_is_admissible_only_when_trusted_and_exactly_applicable(registry) -> None:
    claim = t3_claim()
    (match,) = discover_oracles(registry, qoi=QOI, context=claim.supplied_inputs)
    ok = assess_benchmark(match, claim, context_ref="ctx")
    assert ok.standing is ExternalStanding.ADMISSIBLE and ok.evidence.source_class is SourceClass.BENCHMARK
    assert dict(ok.evidence.uncertainty.channels) == {}  # the acceptance tolerance is not an uncertainty
    assert assess_benchmark(replace(match, trusted=False), claim, context_ref="ctx").standing is ExternalStanding.UNUSABLE
    point = dict(t3_point())
    point.pop("density")
    (partial,) = discover_oracles(registry, qoi=QOI, context=point)
    assert assess_benchmark(partial, t3_claim(operating_context=point), context_ref="ctx").standing is ExternalStanding.WEAK


# ---------------------------------------------------------------------------
# In the assessment
# ---------------------------------------------------------------------------


def test_offered_external_evidence_never_changes_the_verdict_or_the_levels(registry) -> None:
    claim = t3_claim()
    base = assess_claim(claim, registry).to_dict()
    m, lit = _measurement(), _literature()
    trust = TrustedExternalRegistry((TrustedPin(m.digest, SourceClass.MEASUREMENT, "c", "r"), TrustedPin(lit.digest, SourceClass.LITERATURE, "c", "r")))
    with_external = assess_claim(claim, registry, external=(m, lit), trust=trust).to_dict()
    assert with_external["verdict"] == base["verdict"]
    assert with_external["validation"] == base["validation"] and with_external["verification"] == base["verification"]
    standings = {a["source_class"]: a["standing"] for a in with_external["external_evidence_assessments"]}
    assert standings == {"benchmark": "admissible", "measurement": "admissible", "literature": "admissible"}
    produced = {s["source_class"]: s["status"] for s in with_external["evidence_sources"]}
    assert produced == {"simulation": "produced", "measurement": "produced", "literature": "produced", "benchmark": "produced"}
    verify_assessment(json.loads(json.dumps(with_external)), registry, trust=trust)


def test_external_evidence_is_bound_to_the_plan_context(registry) -> None:
    m = _measurement()
    a = assess_claim(t3_claim(), registry, external=(m,), trust=_pinned(m))
    (ingested,) = [x for x in a.to_dict()["external_evidence_assessments"] if x["source_class"] == "measurement"]
    assert a.evidence.context_ref == a.plan.context_ref
    assert ingested["evidence_record_hash"] is not None


def test_an_edited_standing_or_a_different_trust_registry_is_refused(registry) -> None:
    m = _measurement()
    trust = _pinned(m)
    record = assess_claim(t3_claim(), registry, external=(m,), trust=trust).to_dict()
    forged = json.loads(json.dumps(record))
    for a in forged["external_evidence_assessments"]:
        if a["source_class"] == "measurement":
            a["record"]["value"]["magnitude"] = 309.70  # edited after pinning: no longer the pinned record
    with pytest.raises(AssessmentForgeryError):
        verify_assessment(forged, registry, trust=trust)
    promoted = json.loads(json.dumps(assess_claim(t3_claim(), registry, external=(m,)).to_dict()))
    for a in promoted["external_evidence_assessments"]:
        if a["source_class"] == "measurement":
            assert a["standing"] == "weak"
            a["standing"] = "admissible"
    with pytest.raises(AssessmentForgeryError):
        verify_assessment(promoted, registry)
    with pytest.raises(AssessmentForgeryError):
        verify_assessment(json.loads(json.dumps(record)), registry)  # judged under another registry


def test_an_unreadable_external_record_is_refused_at_read_back(registry) -> None:
    record = assess_claim(t3_claim(), registry, external=(_measurement(),)).to_dict()
    for a in record["external_evidence_assessments"]:
        if a["source_class"] == "measurement":
            a["record"]["surprise"] = 1
    with pytest.raises(AssessmentForgeryError):
        verify_assessment(record, registry)
