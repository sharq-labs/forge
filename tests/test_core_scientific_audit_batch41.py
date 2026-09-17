"""Core re-audit 2026-09-16, batch 41: a record that carries a new binding says so in its version.

Problem R-45 (the audit's finding 90, items 2 and 3), improvement I-20 part C of three, under
benchmarks/core_v4_false_confidence/BATCH41_THRESHOLD_PROTOCOL.json.

Part B fixed the direction where a new reader refuses an old record. This is the other direction, and it is
the dangerous one: a record carrying a NEW binding under an UNCHANGED version string is accepted by an older
reader, which drops the binding and re-emits something that reads as a default rather than as a loss. The
audit followed it through: an assessment bound to 300 K, re-emitted once, admitted a result at 5000 K as
IN_DOMAIN, because `evaluated` was gone and the CORE-014 refusal had nothing to fire on.

Recorded as strict xfails in commit 329dcd77, each seen failing on its own assertion, before the fix.
"""

from __future__ import annotations


import pytest

from engcore.scientific.errors import ScientificCoreError
from engcore.scientific.models import definition as D
from engcore.scientific.results import uncertainty as U
from engcore.scientific.serialization import require_schema
from engcore.scientific.units import Quantity


def _older_reader(payload, version):
    """An older reader is exactly this: one that knows a single version string.

    If it accepts the payload, it goes on to read the fields it knows and drops every other key -- which is
    what the audit reproduced, and why the version, not the key, is what has to change.
    """
    require_schema(payload, version)


# ---------------------------------------------------------------------------
# uncertainty: CORE-016's source_kind
# ---------------------------------------------------------------------------
def _uncertainty(**kw):
    return U.Uncertainty(kind=U.UncertaintyKind.STANDARD,
                         standard_uncertainty=Quantity(0.5, "kelvin"),
                         method="grid convergence study", source="mesh refinement", **kw)


def test_r45_an_uncertainty_that_records_where_the_number_came_from_declares_a_new_version():
    bound = _uncertainty(source_kind=U.UncertaintySource.NUMERICAL)
    payload = bound.to_dict()
    assert payload["source_kind"] == "numerical"
    assert payload["schema"] == "uncertainty/2", (
        "the record carries CORE-016's binding under the version string that predates it, so an older "
        "reader accepts it and drops the key")
    with pytest.raises(ScientificCoreError):
        _older_reader(payload, "uncertainty/1")
    assert U.Uncertainty.from_dict(payload) == bound


def test_r45_an_uncertainty_that_records_nothing_new_keeps_its_bytes():
    """The control: a record carrying no new binding keeps its version, its bytes and its digest."""
    plain = _uncertainty()
    payload = plain.to_dict()
    assert payload["schema"] == "uncertainty/1" and "source_kind" not in payload
    _older_reader(payload, "uncertainty/1")
    assert U.Uncertainty.from_dict(payload) == plain


def test_r45_the_old_version_carrying_the_new_key_is_refused():
    payload = _uncertainty(source_kind=U.UncertaintySource.NUMERICAL).to_dict()
    payload["schema"] = "uncertainty/1"
    with pytest.raises(ScientificCoreError, match="source_kind"):
        U.Uncertainty.from_dict(payload)


# ---------------------------------------------------------------------------
# validity_assessment: CORE-014's evaluated, and I-11's model binding
# ---------------------------------------------------------------------------
def _assessment(**kw):
    return D.ValidityAssessment(status=D.ValidityStatus.IN_DOMAIN, satisfied=("T_range",), **kw)


def test_r45_an_assessment_bound_to_an_operating_point_declares_a_new_version():
    bound = _assessment(evaluated={"T": Quantity(300.0, "kelvin")})
    payload = bound.to_dict()
    assert "evaluated" in payload
    assert payload["schema"] == "validity_assessment/3", (
        "this is the record the audit re-emitted through an older reader: the operating point was dropped "
        "and a result 4700 K away then read IN_DOMAIN")
    with pytest.raises(ScientificCoreError):
        _older_reader(payload, "validity_assessment/2")
    assert D.ValidityAssessment.from_dict(payload) == bound


def test_r45_an_assessment_naming_its_model_declares_it_too():
    bound = _assessment(model_id="thermal.slab", model_version="1")
    assert bound.to_dict()["schema"] == "validity_assessment/3"


def test_r45_an_assessment_that_binds_nothing_keeps_its_bytes():
    """The control, and the reason the bump is conditional: no committed digest moves."""
    plain = _assessment()
    payload = plain.to_dict()
    assert payload["schema"] == "validity_assessment/2"
    assert not {"evaluated", "model_id", "model_version", "declared_conditions"} & set(payload)
    _older_reader(payload, "validity_assessment/2")
    assert D.ValidityAssessment.from_dict(payload) == plain


def test_r45_an_older_assessment_version_carrying_a_binding_is_refused():
    payload = _assessment(evaluated={"T": Quantity(300.0, "kelvin")}).to_dict()
    payload["schema"] = "validity_assessment/2"
    with pytest.raises(ScientificCoreError, match="evaluated"):
        D.ValidityAssessment.from_dict(payload)


def test_r45_a_genuine_older_assessment_still_reads():
    """The control for the refusal above: `/2` without the new keys is exactly what the older tree wrote."""
    payload = _assessment().to_dict()
    payload["schema"] = "validity_assessment/2"
    assert D.ValidityAssessment.from_dict(payload).status is D.ValidityStatus.IN_DOMAIN


