"""Manufacturer rating applicability: duration envelope, not a flight prediction."""

import dataclasses

import pytest

from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.knowledge import (
    KnowledgeSource,
    KnowledgeSourceClass,
    ManufacturerOperatingRating,
    MissionSupportability,
    RatingApplicability,
    RequestedOperatingCondition,
    assess_operating_rating,
    assess_operating_ratings,
)
from engcore.systems.products.drone_ratings import assess_manufacturer_rating_packet
from engcore.scientific.units.quantity import Quantity

REVISION = "a" * 40
RUN = "a1-5-operating-rating"


def _source(issuer: str = "KDE Direct") -> KnowledgeSource:
    return KnowledgeSource(
        "source-1", issuer, "ab" * 32, "1",
        "https://example.test/rating", KnowledgeSourceClass.MANUFACTURER_DATASHEET,
    )


def _rating(**overrides) -> ManufacturerOperatingRating:
    source = overrides.pop("source", _source())
    values = dict(
        source=source,
        source_digest_scope="source_document",
        component_id="motor-1",
        manufacturer=source.issuer,
        rating_type="maximum_current",
        rating_id="motor-1:180s",
        duration=Quantity(180, "second"),
        current=Quantity(32, "ampere"),
        power=Quantity(945, "watt"),
        current_is_maximum=True,
        power_is_maximum=True,
        stated_duty="maximum continuous current (180 s)",
    )
    values.update(overrides)
    return ManufacturerOperatingRating(**values)


def _request(**overrides) -> RequestedOperatingCondition:
    values = dict(
        requirement_id="mission-2700",
        duration=Quantity(2700, "second"),
    )
    values.update(overrides)
    return RequestedOperatingCondition(**values)


def _admitted(**overrides) -> RequestedOperatingCondition:
    values = dict(
        operating_point_admission_id="bracket-1",
        current=Quantity(10, "ampere"),
    )
    values.update(overrides)
    return _request(**values)


def test_a_short_published_duration_is_outside_the_envelope():
    rating = _rating()
    before = rating.to_dict()
    assessment = assess_operating_rating(rating, _request(), run_id=RUN, source_revision=REVISION)
    assert assessment.status is RatingApplicability.OUTSIDE_DURATION_ENVELOPE
    assert assessment.dimension("duration").status is RatingApplicability.OUTSIDE_DURATION_ENVELOPE
    assert rating.to_dict() == before
    assert "continuous" in (rating.stated_duty or "")
    assert assessment.provenance.git_commit == REVISION


def test_b_contained_duration_passes_when_every_published_limit_is_compared():
    rating = _rating(duration=Quantity(3600, "second"), rating_id="motor-1:3600s", stated_duty=None)
    covered = _admitted(power=Quantity(100, "watt"))
    assessment = assess_operating_rating(rating, covered, run_id=RUN, source_revision=REVISION)
    assert assessment.dimension("duration").status is RatingApplicability.SUPPORTED_WITHIN_RATING
    assert assessment.status is RatingApplicability.SUPPORTED_WITHIN_RATING
    omitted_power = assess_operating_rating(rating, _admitted(), run_id=RUN, source_revision=REVISION)
    assert omitted_power.dimension("duration").status is RatingApplicability.SUPPORTED_WITHIN_RATING
    assert omitted_power.status is not RatingApplicability.SUPPORTED_WITHIN_RATING
    assert omitted_power.dimension("power").status is RatingApplicability.CONDITIONAL_APPLICABILITY_UNRESOLVED
    bare = assess_operating_rating(rating, _request(), run_id=RUN, source_revision=REVISION)
    assert bare.dimension("duration").status is RatingApplicability.SUPPORTED_WITHIN_RATING
    assert bare.status is RatingApplicability.OPERATING_POINT_NOT_ESTABLISHED


def test_c_contained_duration_does_not_support_a_missing_operating_point():
    rating = _rating(duration=Quantity(3600, "second"), rating_id="motor-1:3600s", power=Quantity(330, "watt"))
    mission = assess_operating_ratings((rating,), _request(), run_id=RUN, source_revision=REVISION)
    assert mission.status is MissionSupportability.INSUFFICIENT_EVIDENCE
    assert mission.physical_infeasibility_claimed is False
    component = mission.component("motor-1")
    assert component.status is RatingApplicability.OPERATING_POINT_NOT_ESTABLISHED
    assert component.assessments[0].dimension("duration").status is RatingApplicability.SUPPORTED_WITHIN_RATING


def test_d_unknown_mission_cooling_stays_conditional():
    rating = _rating(
        duration=Quantity(3600, "second"),
        rating_id="motor-1:3600s",
        cooling_requirement="consistent open airflow (5 mph or greater)",
    )
    assessment = assess_operating_rating(rating, _admitted(), run_id=RUN, source_revision=REVISION)
    assert assessment.status is RatingApplicability.CONDITIONAL_APPLICABILITY_UNRESOLVED
    assert assessment.dimension("cooling").status is RatingApplicability.CONDITIONAL_APPLICABILITY_UNRESOLVED
    assert assessment.dimension("duration").status is RatingApplicability.SUPPORTED_WITHIN_RATING


def test_e_missing_duration_is_insufficient_and_not_unlimited():
    rating = _rating(duration=None, rating_id="motor-1:undated", stated_duty="continuous")
    assessment = assess_operating_rating(rating, _admitted(), run_id=RUN, source_revision=REVISION)
    assert assessment.status is RatingApplicability.INSUFFICIENT_EVIDENCE
    assert assessment.dimension("duration").status is RatingApplicability.INSUFFICIENT_EVIDENCE


def test_f_assessment_does_not_mutate_source_evidence():
    rating = _rating()
    before = rating.to_dict()
    assess_operating_rating(rating, _request(), run_id=RUN, source_revision=REVISION)
    assert rating.to_dict() == before
    with pytest.raises(dataclasses.FrozenInstanceError):
        rating.duration = Quantity(3600, "second")  # type: ignore[misc]


def test_g_provenance_replay_identity_is_deterministic():
    rating = _rating()
    request = _request()
    first = assess_operating_rating(rating, request, run_id=RUN, source_revision=REVISION)
    second = assess_operating_rating(rating, request, run_id=RUN, source_revision=REVISION)
    assert first.digest == second.digest
    restored = type(first).from_dict(first.to_dict())
    assert restored.digest == first.digest
    assert restored.provenance.git_commit == REVISION
    assert restored.provenance.software_version.startswith("engcore.scientific.knowledge.operating_rating/")
    assert restored.source_document_digest == rating.source.document_digest
    with pytest.raises(InvalidScientificProblem):
        assess_operating_rating(rating, request, run_id=RUN, source_revision="")


def test_duration_refusals_do_not_make_the_mission_physically_impossible():
    short = _rating()
    long = _rating(
        component_id="motor-2",
        rating_id="motor-2:3600s",
        duration=Quantity(3600, "second"),
        source=_source(issuer="MAD Components"),
        manufacturer="MAD Components",
        power=Quantity(330, "watt"),
        current=None,
    )
    mission = assess_operating_ratings((short, long), _request(), run_id=RUN, source_revision=REVISION)
    assert mission.status is MissionSupportability.INSUFFICIENT_EVIDENCE
    assert mission.physical_infeasibility_claimed is False
    assert mission.component("motor-1").status is RatingApplicability.OUTSIDE_DURATION_ENVELOPE
    assert mission.component("motor-2").status is RatingApplicability.OPERATING_POINT_NOT_ESTABLISHED
    assert "physical-impossibility" in mission.reason


def test_packet_keeps_a_long_rating_unresolved_when_the_operating_point_is_absent():
    packet = {
        "packet_id": "fixture-mission",
        "mission": {
            "minimum_hover_duration_s": 2700,
        },
        "records": [
            {
                "record_id": "kde-4012",
                "manufacturer": "KDE Direct",
                "source_page": "https://www.kdedirect.com/products/kde4012xf-400",
                "stated_fields": {
                    "maximum_continuous_current": "32 A (180 s)",
                    "maximum_continuous_power": "945 W (180 s)",
                    "cooling_note": "consistent open airflow (5 mph or greater)",
                },
            },
            {
                "record_id": "tmotor-mn4010-kv370",
                "manufacturer": "T-Motor",
                "source_page": "https://store.tmotor.com/product/mn4010-kv370-motor-navigator-type.html",
                "stated_fields": {
                    "max_continuous_current_180s": "20 A",
                    "max_power_180s": "450 W",
                    "example_measured_row": {"power_w": 37.0, "thrust_g": 500},
                    "test_note": "motor surface temperature at 100% throttle while the motor run 10min",
                },
            },
            {
                "record_id": "mad-5010-240-eee",
                "manufacturer": "MAD Components",
                "source_page": "http://madcomponents.co/index.php/mad5010-240kv/",
                "stated_fields": {
                    "continuous_power_60_min_w": 330,
                    "maximum_power_60_s_w": 720,
                    "maximum_current_60_s_a": 24,
                    "heat_dissipation": "Passive",
                    "efficiency_at_750g_thrust_g_per_w": 15.2,
                    "thrust_current_rpm_table_on_page": False,
                },
            },
            {
                "record_id": "mad-5008-400-eee",
                "manufacturer": "MAD Components",
                "source_page": "http://www.madcomponents.co/download/MAD5008_400KV.pdf",
                "stated_fields": {
                    "continuous_power_60_min": None,
                    "maximum_power_180_s_w": 800,
                    "maximum_current_180_s_a": 30,
                },
            },
        ],
    }
    mission = assess_manufacturer_rating_packet(packet, run_id=RUN, source_revision=REVISION)
    assert mission.status is MissionSupportability.INSUFFICIENT_EVIDENCE
    assert mission.physical_infeasibility_claimed is False
    assert mission.component("kde-4012").status is RatingApplicability.OUTSIDE_DURATION_ENVELOPE
    assert mission.component("tmotor-mn4010-kv370").status is RatingApplicability.OUTSIDE_DURATION_ENVELOPE
    assert mission.component("mad-5008-400-eee").status is RatingApplicability.OUTSIDE_DURATION_ENVELOPE
    mad = mission.component("mad-5010-240-eee")
    assert mad.status is RatingApplicability.OPERATING_POINT_NOT_ESTABLISHED
    assert all(item.rating.undated_magnitude is False for item in mad.assessments)
    durations = sorted(
        assessment.dimension("duration").status
        for assessment in mad.assessments
    )
    assert RatingApplicability.SUPPORTED_WITHIN_RATING in durations
    assert RatingApplicability.OUTSIDE_DURATION_ENVELOPE in durations
    assert all(
        assessment.provenance.git_commit == REVISION
        for component in mission.components
        for assessment in component.assessments
    )
    assert not any("10min" == assessment.rating_id.split(":")[-1] for component in mission.components for assessment in component.assessments)
    assert any(
        item.dimension == "environment"
        for item in mad.assessments[0].dimensions
    )


def test_a_rewritten_support_status_is_refused():
    rating = _rating()
    assessment = assess_operating_rating(rating, _request(), run_id=RUN, source_revision=REVISION)
    payload = assessment.to_dict()
    payload["status"] = RatingApplicability.SUPPORTED_WITHIN_RATING.value
    with pytest.raises(InvalidScientificProblem, match="not entailed"):
        type(assessment).from_dict(payload)


def test_disagreeing_maxima_are_not_collapsed_to_the_larger_one():
    packet = {
        "packet_id": "limits",
        "mission": {"minimum_hover_duration_s": 30},
        "records": [{
            "record_id": "motor-1",
            "manufacturer": "Example",
            "source_page": "https://example.test/motor",
            "stated_fields": {
                "max_power_60_s_w": 900,
                "maximum_power_60_s_w": 330,
            },
        }],
    }
    mission = assess_manufacturer_rating_packet(
        packet, run_id=RUN, source_revision=REVISION
    )
    assessment = mission.component("motor-1").assessments[0]
    assert assessment.status is not RatingApplicability.SUPPORTED_WITHIN_RATING
    assert assessment.rating.power is None
    assert assessment.rating.limit_conflict is True


def test_a_temperature_qualifier_withholds_support():
    rating = _rating(
        duration=Quantity(3600, "second"),
        rating_id="motor-1:3600s",
        temperature_qualifier="published only at 25 C",
        stated_duty=None,
    )
    assessment = assess_operating_rating(rating, _admitted(), run_id=RUN, source_revision=REVISION)
    assert assessment.status is RatingApplicability.CONDITIONAL_APPLICABILITY_UNRESOLVED
    assert assessment.dimension("temperature").status is RatingApplicability.CONDITIONAL_APPLICABILITY_UNRESOLVED


def test_a_boolean_mission_duration_is_refused():
    packet = {
        "packet_id": "bad-duration",
        "mission": {"minimum_hover_duration_s": True},
        "records": [],
    }
    with pytest.raises(InvalidScientificProblem, match="finite number"):
        assess_manufacturer_rating_packet(packet, run_id=RUN, source_revision=REVISION)


def test_an_undeclared_maximum_does_not_ignore_a_larger_request():
    rating = _rating(
        duration=Quantity(3600, "second"),
        rating_id="motor-1:3600s",
        current_is_maximum=False,
        stated_duty=None,
    )
    request = _admitted(current=Quantity(100, "ampere"))
    assessment = assess_operating_rating(rating, request, run_id=RUN, source_revision=REVISION)
    assert assessment.status is not RatingApplicability.SUPPORTED_WITHIN_RATING
    assert assessment.dimension("current").status is RatingApplicability.CONDITIONAL_APPLICABILITY_UNRESOLVED


def test_an_undated_magnitude_blocks_a_dated_sibling_rating():
    packet = {
        "packet_id": "undated",
        "mission": {"minimum_hover_duration_s": 60, "operating_point_admission_id": "bracket-1"},
        "records": [{
            "record_id": "motor-1",
            "manufacturer": "Example",
            "source_page": "https://example.test/motor",
            "stated_fields": {
                "max_power_3600_s_w": 100,
                "maximum_continuous_current": "5 A",
            },
        }],
    }
    mission = assess_manufacturer_rating_packet(packet, run_id=RUN, source_revision=REVISION)
    assessment = mission.component("motor-1").assessments[0]
    assert assessment.rating.undated_magnitude is True
    assert assessment.rating.current is None
    direct = assess_operating_rating(
        assessment.rating,
        _admitted(current=None, power=Quantity(50, "watt")),
        run_id=RUN,
        source_revision=REVISION,
    )
    assert direct.dimension("duration").status is RatingApplicability.SUPPORTED_WITHIN_RATING
    assert direct.status is RatingApplicability.INSUFFICIENT_EVIDENCE


# ---- landing review 2026-10-16: a caller label is not an operating point ---------------------------------------------
def test_an_admission_id_with_no_published_limit_to_compare_establishes_nothing():
    """Reviewer counterexample: no published magnitude, a huge requested current and an admission id was SUPPORTED."""
    rating = _rating(duration=Quantity(3600, "second"), current=None, power=None, voltage=None,
                     rating_id="motor-1:3600s", stated_duty=None)
    request = _admitted(duration=Quantity(60, "second"), current=Quantity(1000, "ampere"),
                        operating_point_admission_id="x")
    assessment = assess_operating_rating(rating, request, run_id=RUN, source_revision=REVISION)
    assert assessment.status is not RatingApplicability.SUPPORTED_WITHIN_RATING
    assert assessment.dimension("operating_point").status is RatingApplicability.OPERATING_POINT_NOT_ESTABLISHED
    assert assessment.dimension("current").status is RatingApplicability.CONDITIONAL_APPLICABILITY_UNRESOLVED
    mission = assess_operating_ratings((rating,), request, run_id=RUN, source_revision=REVISION)
    assert mission.status is not MissionSupportability.SUPPORTED


def test_the_operating_point_needs_a_compared_published_limit_of_the_same_kind():
    # the rating publishes a current maximum only; the request states power only -> nothing compared
    rating = _rating(duration=Quantity(3600, "second"), power=None, rating_id="motor-1:3600s", stated_duty=None)
    request = _admitted(duration=Quantity(60, "second"), current=None, power=Quantity(100, "watt"))
    assessment = assess_operating_rating(rating, request, run_id=RUN, source_revision=REVISION)
    assert assessment.dimension("operating_point").status is RatingApplicability.OPERATING_POINT_NOT_ESTABLISHED
    assert assessment.dimension("power").status is RatingApplicability.CONDITIONAL_APPLICABILITY_UNRESOLVED
    # the same request with a current inside the published maximum is established on that comparison
    within = _admitted(duration=Quantity(60, "second"), current=Quantity(10, "ampere"))
    ok = assess_operating_rating(rating, within, run_id=RUN, source_revision=REVISION)
    assert ok.dimension("operating_point").status is RatingApplicability.SUPPORTED_WITHIN_RATING
    assert "current" in ok.dimension("operating_point").reason
