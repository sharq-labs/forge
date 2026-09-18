"""Scientific core audit 2026-09-16, batch 3b: scoping validation, validity and uncertainty records to what they describe.

Findings CORE-009, CORE-014 and CORE-016 (docs/audits/CORE_SCIENTIFIC_AUDIT_2026-09-16.md), under
benchmarks/core_v4_false_confidence/BATCH3B_THRESHOLD_PROTOCOL.json. Recorded as strict xfails in commit 5b960db, each seen
failing, before the fix.
"""

from __future__ import annotations

import pytest

from engcore.scientific.models.definition import RangeCondition, ValidityAssessment, ValidityDomain, ValidityStatus
from engcore.scientific.oracles import OracleEvidenceSet, OracleKind, OracleObservation
from engcore.scientific.results.provenance import ProvenanceRecord
from engcore.scientific.results.result import ScientificResult
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind
from engcore.scientific.results.validation import ValidationOutcome
from engcore.scientific.units.quantity import Quantity

K = "kelvin"


# ---------------------------------------------------------------------------
# CORE-009: an experimental comparison carried no conditions
# ---------------------------------------------------------------------------
def _evidence(**observation):
    return OracleEvidenceSet.create(oracle_id="core009.rig", version="1", kind=OracleKind.EXPERIMENTAL_DATASET,
                                    reference="bench log 2026-09-16",
                                    observations=(OracleObservation("y", Quantity(1.0, "meter"), Quantity(0.01, "meter"),
                                                                    **observation),))


def test_core009_a_comparison_at_other_conditions_is_not_made():
    evidence = _evidence(conditions={"T": Quantity(300.0, K)})
    hot = evidence.compare({"y": Quantity(1.0, "meter")}, conditions={"T": Quantity(5000.0, K)})
    assert hot.outcome is ValidationOutcome.NOT_RUN and hot.establishes is None and "T" in hot.detail
    unstated = evidence.compare({"y": Quantity(1.0, "meter")})
    assert unstated.outcome is ValidationOutcome.NOT_RUN and unstated.establishes is None
    same = evidence.compare({"y": Quantity(1.0, "meter")}, conditions={"T": Quantity(300.0, K)})
    assert same.outcome is ValidationOutcome.PASS


def test_core009_evidence_without_conditions_keeps_its_content_digest():
    """The digest of every existing evidence set is unchanged: conditions are serialized only when declared."""
    evidence = _evidence()
    assert "conditions" not in evidence.observations[0].to_dict()
    assert evidence.compare({"y": Quantity(1.0, "meter")}).outcome is ValidationOutcome.PASS


# ---------------------------------------------------------------------------
# CORE-014: an assessment was not bound to the values it read
# ---------------------------------------------------------------------------
_DOMAIN = ValidityDomain(conditions=(RangeCondition("T", minimum=Quantity(250.0, K), maximum=Quantity(400.0, K)),))
_MODEL = ("m", "1")


def _result(assessment, temperature):
    return ScientificResult(result_id="r", values={"y": Quantity(1.0, "meter")}, models=(_MODEL,),
                            validity={_MODEL[0]: assessment},
                            provenance=ProvenanceRecord(run_id="r", models=(_MODEL,), inputs={"T": Quantity(temperature, K)}))


def test_core014_an_assessment_read_at_another_operating_point_is_refused():
    assessment = _DOMAIN.assess({"T": Quantity(300.0, K)}, record_values=True)
    assert assessment.status is ValidityStatus.IN_DOMAIN and assessment.evaluated["T"] == Quantity(300.0, K)
    assert _result(assessment, 300.0).validity[_MODEL[0]].status is ValidityStatus.IN_DOMAIN
    with pytest.raises(Exception, match="T"):
        _result(assessment, 5000.0)
    assert ValidityAssessment.from_dict(assessment.to_dict()).evaluated == assessment.evaluated


def test_core014_an_assessment_that_did_not_record_values_serializes_as_before():
    assessment = _DOMAIN.assess({"T": Quantity(300.0, K)})
    assert "evaluated" not in assessment.to_dict()


# ---------------------------------------------------------------------------
# CORE-016: uncertainty had no source
# ---------------------------------------------------------------------------
def test_core016_an_uncertainty_says_what_kind_of_uncertainty_it_is():
    from engcore.scientific.results.uncertainty import UncertaintySource

    numerical = Uncertainty(kind=UncertaintyKind.STANDARD, standard_uncertainty=Quantity(0.01, K),
                            method="mesh refinement", source_kind=UncertaintySource.NUMERICAL)
    assert numerical.to_dict()["source_kind"] == "numerical"
    assert Uncertainty.from_dict(numerical.to_dict()).source_kind is UncertaintySource.NUMERICAL
    plain = Uncertainty(kind=UncertaintyKind.STANDARD, standard_uncertainty=Quantity(0.01, K), method="m")
    assert plain.source_kind is UncertaintySource.UNSPECIFIED and "source_kind" not in plain.to_dict()
