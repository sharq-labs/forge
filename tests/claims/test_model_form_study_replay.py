"""A model-form empirical study record survives object -> dict -> JSON -> object -> verify.

No production capability declares MODEL_FORM, so no other test ever replays a
``model_form_empirical`` record carrying a PairedObservation. Two defects hid on
that path (review finding B2): ``PairedObservation.from_dict`` named ``Mapping``
without importing it, and ``verify_study_records`` read the recorded producer
qualification only on the branch that reaches promotion. Either one turned a
genuine record into a crash on read-back instead of a re-derivation.

The registry here adds MODEL_FORM for the battery's open-circuit voltage so
that the study is planned; the observations are the repository-pinned S-OCV
records. Nothing here can promote model-form uncertainty: no qualification is
supplied, so the channel must stay UNKNOWN.
"""

from __future__ import annotations

import copy
import json
from dataclasses import replace

import pytest

from claims_support import battery_inputs, claim
from engcore.claims import (
    AssessmentForgeryError,
    CapabilityRegistry,
    ClaimTarget,
    QuantityOfInterest,
    UncertaintyCapability,
    UncertaintyDemand,
    assess_claim,
    verify_assessment,
)
from engcore.claims.analysis.model_discrepancy import PairedObservation
from engcore.claims.empirical_uq_trust import PRODUCTION_EMPIRICAL_RECORDS
from engcore.claims.measurement_dataset import DatasetSplit
from engcore.mcp.capabilities import production_registry
from engcore.scientific.ir.constraints import ConstraintOperator
from engcore.scientific.units.quantity import Quantity
from engcore.sria.uncertainty import UncertaintyChannel as C


@pytest.fixture(scope="module")
def registry():
    base = production_registry()
    battery = base.get("system.battery")
    quantified = {k: set(v) for k, v in battery.uncertainty.quantified.items()}
    quantified["open_circuit_voltage"] = (
        quantified.get("open_circuit_voltage", set()) | {C.MODEL_FORM}
    )
    battery = replace(
        battery,
        uncertainty=UncertaintyCapability(quantified, battery.uncertainty.basis),
    )
    return CapabilityRegistry(
        [battery if d.capability_id == "system.battery" else d for d in base]
    )


def _ocv_claim():
    return claim(
        statement="The open-circuit voltage stays below 4.0 V.",
        qoi=QuantityOfInterest("open_circuit_voltage", "volt"),
        operator=ConstraintOperator.LESS_THAN,
        target=ClaimTarget(value=Quantity(4.0, "volt")),
        operating_context={},
        known_inputs=battery_inputs(),
        uncertainty=UncertaintyDemand(frozenset({C.MODEL_FORM}), None, False),
    )


def _record(registry, observations):
    return assess_claim(
        _ocv_claim(), registry, empirical_observations=tuple(observations)
    ).to_dict()


def _study(record):
    (study,) = [
        s for s in record["uncertainty_studies"]
        if s["kind"] == "model_form_empirical"
    ]
    return study


@pytest.fixture(scope="module")
def all_pinned(registry):
    return _record(registry, PRODUCTION_EMPIRICAL_RECORDS)


@pytest.fixture(scope="module")
def held_out_only(registry):
    # The SOC = 1 calibration runs leave the validated domain; the SOC 0.5/0.6
    # held-out runs do not, so this record reaches the discrepancy estimate.
    return _record(registry, [
        item for item in PRODUCTION_EMPIRICAL_RECORDS
        if item.split is DatasetSplit.VALIDATION
    ])


def test_a_paired_observation_round_trips_through_json(all_pinned) -> None:
    pairs = _study(all_pinned)["pairs"]
    assert pairs
    for payload in pairs:
        back = PairedObservation.from_dict(json.loads(json.dumps(payload)))
        assert back.to_dict() == payload


def test_a_study_stopped_by_unusable_runs_replays_with_its_pairs(
    registry, all_pinned
) -> None:
    study = _study(all_pinned)
    assert study["pairs"]
    assert "prediction run is unusable" in study["problem"]
    assert study["qualification"] is None
    assert study["uncertainty"]["kind"] == "unknown"
    back = verify_assessment(json.loads(json.dumps(all_pinned)), registry)
    assert back.to_dict() == all_pinned


def test_a_study_that_reaches_the_discrepancy_estimate_replays(
    registry, held_out_only
) -> None:
    study = _study(held_out_only)
    assert study["pairs"] and study["discrepancy"] is not None
    assert "qualification" in study["problem"]
    assert study["uncertainty"]["kind"] == "unknown"
    back = verify_assessment(json.loads(json.dumps(held_out_only)), registry)
    assert back.to_dict() == held_out_only


@pytest.mark.parametrize("fixture", ["all_pinned", "held_out_only"])
def test_an_edited_pair_is_refused_on_replay(registry, fixture, request) -> None:
    record = copy.deepcopy(request.getfixturevalue(fixture))
    pair = _study(record)["pairs"][0]
    pair["observed"]["magnitude"] = pair["observed"]["magnitude"] + 0.01
    with pytest.raises(AssessmentForgeryError, match="observed value"):
        verify_assessment(json.loads(json.dumps(record)), registry)


def test_a_flipped_qualification_trust_flag_is_refused(registry, all_pinned) -> None:
    record = copy.deepcopy(all_pinned)
    study = _study(record)
    assert study["qualification_trusted"] is False
    study["qualification_trusted"] = True
    with pytest.raises(AssessmentForgeryError, match="re-derive"):
        verify_assessment(json.loads(json.dumps(record)), registry)


@pytest.mark.parametrize("qualification", [{"producer_id": "x"}, "not an object", []])
def test_a_malformed_qualification_on_an_early_stop_record_is_a_forgery(
    registry, all_pinned, qualification
) -> None:
    record = copy.deepcopy(all_pinned)
    _study(record)["qualification"] = qualification
    with pytest.raises(AssessmentForgeryError, match="qualification is not readable"):
        verify_assessment(json.loads(json.dumps(record)), registry)


def test_a_qualification_that_differs_from_its_canonical_form_is_refused(
    registry, all_pinned
) -> None:
    # from_dict normalises (e.g. strips whitespace), so without a canonical
    # comparison a record could display text other than what was digested.
    from engcore.uq.model_form.qualification import ProducerQualification

    qualification = ProducerQualification(
        "producer.b2", "method.b2", "a" * 64, "reviewer", "b" * 64,
        ("open_circuit_voltage",),
    ).to_dict()
    record = copy.deepcopy(all_pinned)
    padded = dict(qualification, independent_reviewer_id=" reviewer ")
    _study(record)["qualification"] = padded
    with pytest.raises(AssessmentForgeryError, match="digest was computed from"):
        verify_assessment(json.loads(json.dumps(record)), registry)
