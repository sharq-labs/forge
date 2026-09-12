"""Parts F, G, H, I and P: serialization, identity, and determinism.

SERIALIZATION POLICY, stated rather than invented
--------------------------------------------------
This round does NOT add backward compatibility. It classifies what exists:

``SUPPORTED_CURRENT``
    61 FROZEN records with both ``to_dict`` and ``from_dict``. The current
    canonical format round-trips: ``from_dict(to_dict(x))`` produces a record
    whose ``to_dict`` is byte-identical to the first. (62 before Sprint 10's
    Part M reclassified ``FieldObservationOperator`` as EXPERIMENTAL; it still
    round-trips, the Core just no longer promises it.)

``SUPPORTED_CURRENT_EXPORT_ONLY``
    16 records with ``to_dict`` and no ``from_dict``. They are transport OUT --
    a summary, an audit, a provenance block -- and nothing in the repository
    reads them back. Recording that is the point: a caller must not assume a
    reader exists because a writer does.

``SUPPORTED_LEGACY``
    EIGHT frozen readers accept older schema versions, each through
    ``require_schema_any`` with an explicit tuple of exact version strings --
    never a range, never a migration framework:

    ==========================  ===========================================
    ``ScientificResult``        ``scientific_result/1`` .. ``/4``
    ``ProvenanceRecord``        ``provenance_record/1`` .. ``/4``
    ``CrossSolverConsensus``    ``cross_solver_consensus/1`` .. ``/3``
    ``RawSolverOutput``         ``raw_solver_output/1``, ``/2``
    ``ScientificModelDefinition`` ``scientific_model_definition/1``, ``/2``
    ``ValidityAssessment``      ``validity_assessment/1``, ``/2``
    ``QuantityDependency``      ``quantity_dependency/1``, ``/2``
    ``QuantityTransfer``        ``quantity_transfer/1``, ``/2``
    ==========================  ===========================================

    Loading real legacy payloads is exercised by the suites that own those
    records (``test_result_validity``, ``test_provenance_integrity``,
    ``test_consensus_integrity`` and others), not re-invented here. The table
    itself is pinned by the Core Freeze V1 manifest, which derives it from the
    ``from_dict`` source rather than from anyone's memory of it.

    CORRECTED IN SPRINT 11. This paragraph used to read "none. No legacy format
    is supported", which was false when it was written: every reader above
    already accepted its older versions. The behaviour was right and tested;
    the written policy was wrong, and a freeze cannot certify a contract whose
    own statement of itself is contradicted by the code. Found by the freeze
    procedure, recorded as FREEZE_BLOCKED on ``af43c89``, fixed here.

``UNSUPPORTED_LEGACY``
    any schema string a reader does not list. Refused explicitly, which the
    tests below demonstrate rather than assert.
"""

from __future__ import annotations

import copy
import importlib
import json
import pathlib
import subprocess
import sys

import pytest

from engcore import api_snapshot
from engcore.scientific.units.quantity import Quantity

REPO = pathlib.Path(__file__).resolve().parents[1]


def frozen_classes():
    for entry in api_snapshot.frozen_only()["symbols"]:
        if entry["kind"] in ("dataclass", "class"):
            yield entry, getattr(importlib.import_module(entry["module"]), entry["name"])


def round_trippable():
    return [
        (e, k) for e, k in frozen_classes()
        if hasattr(k, "to_dict") and hasattr(k, "from_dict")
    ]


def export_only():
    return [
        (e, k) for e, k in frozen_classes()
        if hasattr(k, "to_dict") and not hasattr(k, "from_dict")
    ]


# =====================================================================
# PART F -- the inventory, pinned
# =====================================================================

def test_the_serialization_inventory_is_what_the_policy_records():
    """A record gaining or losing `from_dict` changes what callers may do."""
    # 61, not 62: FieldObservationOperator round-trips and always did, but
    # Part M reclassified it EXPERIMENTAL, and this inventory is over the
    # FROZEN population -- what the Core PROMISES round-trips.
    assert len(round_trippable()) == 61
    assert len(export_only()) == 16


def test_every_export_only_record_is_deliberate():
    """Named individually, so one silently joining the list is a decision."""
    assert {f"{e['module']}.{e['name']}" for e, _ in export_only()} == {
        "engcore.adequacy.ModelScoreComparison",
        "engcore.execution.SweepSummary",
        "engcore.inference.AdmissibleAnalyticPrediction",
        "engcore.inference.AdmissibleNumericalPrediction",
        "engcore.inference.CalibrationProvenance",
        "engcore.inference.CalibrationResult",
        "engcore.inference.CalibrationSpec",
        "engcore.inference.GaussianObservation",
        "engcore.inference.IdentifiabilityReport",
        "engcore.inference.NoiseModel",
        "engcore.inference.ObservationSet",
        "engcore.inference.ObservationSplit",
        "engcore.scientific.ConversionOutcome",
        "engcore.scientific.OptimizerAdapter",
        "engcore.uq.PredictiveAdmissionAudit",
        "engcore.uq.QuantifiedPredictiveResult",
    }


# =====================================================================
# PART G -- canonical fixtures round-trip
# =====================================================================

def fixtures():
    """One representative instance per frozen record family that persists.

    Built rather than stored as JSON on purpose: a stored fixture that was
    generated by the same code it tests proves only that the code agrees with
    itself. These are constructed through the public constructors, so a
    constructor that stopped accepting what it used to fails here first.
    """
    from engcore.adequacy import PredictiveEvidenceIdentity
    from engcore.inference import (
        CalibrationParameterSet, FieldObservationOperator, ParameterBounds,
        ParameterEstimate, ParameterIdentity,
    )
    from engcore.scientific import (
        ModelReference, ProvenanceRecord, Quantity as Q, SolverIdentity,
        TwinReference, ValidationReport,
    )
    from engcore.scientific.fields.mesh import StructuredMesh
    from engcore.inference.field_observation import FieldObservationKind

    model = ModelReference(model_id="m.demo", version="1.0.0")
    twin = TwinReference(twin_id="t.demo", version="1")
    mesh = StructuredMesh(
        mesh_id="plate", length_x=Q(0.04, "meter"), length_y=Q(0.04, "meter"),
        nodes_x=5, nodes_y=5,
    )
    parameter = ParameterIdentity(
        name="reference_resistance", unit="ohm", model=model,
        bounds=ParameterBounds(Q(0.0, "ohm"), Q(10.0, "ohm")),
    )
    return {
        "Quantity": Q(1.5, "ohm"),
        "ModelReference": model,
        "TwinReference": twin,
        "SolverIdentity": SolverIdentity("s.demo", "1.0"),
        "ValidationReport": ValidationReport(),
        "ProvenanceRecord": ProvenanceRecord(run_id="r-1"),
        "ParameterIdentity": parameter,
        "ParameterEstimate": ParameterEstimate(parameter, 2.5),
        "CalibrationParameterSet": CalibrationParameterSet((parameter,)),
        "PredictiveEvidenceIdentity": PredictiveEvidenceIdentity(
            observation_key="c:y", observed_value=1.0, unit="ohm",
            likelihood_sigma=0.1, heldout_dataset_id="h", posterior_dataset_id="p",
            twin=twin,
        ),
        "FieldObservationOperator": FieldObservationOperator(
            operator_id="probe", kind=FieldObservationKind.PROBE_AT_LOCATION,
            field_id="temperature", mesh_fingerprint=mesh.fingerprint(),
            unit="kelvin", probe_x=Q(0.02, "meter"), probe_y=Q(0.01, "meter"),
        ),
    }


@pytest.mark.parametrize("name", sorted(fixtures()))
def test_the_current_canonical_format_round_trips(name):
    """`from_dict(to_dict(x)).to_dict()` must be byte-identical to `to_dict(x)`."""
    record = fixtures()[name]
    first = record.to_dict()
    restored = type(record).from_dict(copy.deepcopy(first))
    second = restored.to_dict()
    assert json.dumps(first, sort_keys=True, allow_nan=False) == json.dumps(
        second, sort_keys=True, allow_nan=False
    ), name


@pytest.mark.parametrize("name", sorted(fixtures()))
def test_every_canonical_payload_is_strict_json(name):
    """A record that serializes to something no reader accepts has no provenance."""
    payload = json.dumps(fixtures()[name].to_dict(), sort_keys=True, allow_nan=False)
    assert json.loads(payload) is not None


@pytest.mark.parametrize("name", sorted(fixtures()))
def test_an_unknown_schema_version_is_refused_explicitly(name):
    """UNSUPPORTED_LEGACY, demonstrated.

    Not every record carries a schema marker; those that do must refuse a
    version they did not write rather than reading it hopefully. A record
    without a marker is skipped and that is visible in the count.
    """
    record = fixtures()[name]
    payload = record.to_dict()
    if "schema" not in payload:
        pytest.skip(f"{name} carries no schema marker")
    payload = dict(payload)
    payload["schema"] = payload["schema"] + ".from-the-future"
    with pytest.raises(Exception) as caught:
        type(record).from_dict(payload)
    assert "schema" in str(caught.value).lower() or "version" in str(caught.value).lower()


def test_at_least_half_the_fixtures_carry_a_schema_marker():
    """Otherwise the test above would be vacuous for most of them."""
    marked = sum(1 for r in fixtures().values() if "schema" in r.to_dict())
    assert marked >= len(fixtures()) // 2, marked


# =====================================================================
# PART H -- material vs non-material identity
# =====================================================================

def test_material_a_different_model_is_a_different_parameter():
    from engcore.inference import ParameterBounds, ParameterIdentity
    from engcore.scientific import ModelReference

    bounds = ParameterBounds(Quantity(0.0, "ohm"), Quantity(10.0, "ohm"))
    a = ParameterIdentity("r", "ohm", ModelReference("m.a", "1"), bounds)
    b = ParameterIdentity("r", "ohm", ModelReference("m.b", "1"), bounds)
    assert a.digest != b.digest, "the model is MATERIAL to a parameter's identity"


def test_material_a_different_unit_is_a_different_parameter():
    from engcore.inference import ParameterBounds, ParameterIdentity
    from engcore.scientific import ModelReference

    model = ModelReference("m.a", "1")
    a = ParameterIdentity(
        "r", "ohm", model, ParameterBounds(Quantity(0.0, "ohm"), Quantity(10.0, "ohm"))
    )
    b = ParameterIdentity(
        "r", "milliohm", model,
        ParameterBounds(Quantity(0.0, "milliohm"), Quantity(10.0, "milliohm")),
    )
    assert a.digest != b.digest, "the unit is MATERIAL"


def test_non_material_the_same_range_in_another_unit_is_the_same_parameter():
    """Identity is PHYSICAL, so the spelling of an equal bound must not split it.

    The converse of the test above, and the one that is easy to get wrong in
    the other direction: a digest that called these two different would be as
    wrong as one that called ohm and milliohm the same, and harder to notice --
    two declarations of identical science failing to compare equal.
    """
    from engcore.inference import ParameterBounds, ParameterIdentity
    from engcore.scientific import ModelReference

    model = ModelReference("m.a", "1")
    a = ParameterIdentity(
        "r", "ohm", model, ParameterBounds(Quantity(0.0, "ohm"), Quantity(10.0, "ohm"))
    )
    b = ParameterIdentity(
        "r", "ohm", model,
        ParameterBounds(Quantity(0.0, "milliohm"), Quantity(10_000.0, "milliohm")),
    )
    assert a.digest == b.digest, "an equal range in another unit is NON-MATERIAL"


def test_non_material_a_display_description_does_not_move_a_field_operator_digest():
    """`description` is prose for a reader. If it entered the digest, editing a
    comment would invalidate every record that cited the operator."""
    from engcore.inference.field_observation import (
        FieldObservationKind, FieldObservationOperator,
    )
    from engcore.scientific.fields.mesh import StructuredMesh

    mesh = StructuredMesh(
        mesh_id="plate", length_x=Quantity(0.04, "meter"),
        length_y=Quantity(0.04, "meter"), nodes_x=5, nodes_y=5,
    )
    common = dict(
        operator_id="probe", kind=FieldObservationKind.PROBE_AT_LOCATION,
        field_id="temperature", mesh_fingerprint=mesh.fingerprint(), unit="kelvin",
        probe_x=Quantity(0.02, "meter"), probe_y=Quantity(0.01, "meter"),
    )
    assert (
        FieldObservationOperator(**common, description="thermocouple A").digest
        == FieldObservationOperator(**common, description="rewritten note").digest
    )


def test_material_a_different_mesh_is_a_different_field_operator():
    from engcore.inference.field_observation import (
        FieldObservationKind, FieldObservationOperator,
    )
    from engcore.scientific.fields.mesh import StructuredMesh

    def operator(nodes):
        mesh = StructuredMesh(
            mesh_id="plate", length_x=Quantity(0.04, "meter"),
            length_y=Quantity(0.04, "meter"), nodes_x=nodes, nodes_y=nodes,
        )
        return FieldObservationOperator(
            operator_id="probe", kind=FieldObservationKind.PROBE_AT_LOCATION,
            field_id="temperature", mesh_fingerprint=mesh.fingerprint(),
            unit="kelvin", probe_x=Quantity(0.02, "meter"),
            probe_y=Quantity(0.01, "meter"),
        )

    assert operator(5).digest != operator(9).digest


def test_material_the_observed_value_is_material_to_evidence_identity():
    from engcore.adequacy import PredictiveEvidenceIdentity
    from engcore.scientific import TwinReference

    common = dict(
        observation_key="c:y", unit="ohm", likelihood_sigma=0.1,
        heldout_dataset_id="h", posterior_dataset_id="p",
        twin=TwinReference("t", "1"),
    )
    a = PredictiveEvidenceIdentity(observed_value=1.0, **common)
    b = PredictiveEvidenceIdentity(observed_value=1.0000001, **common)
    assert a.digest != b.digest


def test_non_material_declaration_order_does_not_move_a_parameter_set_digest():
    """A set built from the same members must hash the same however it was
    assembled -- except where ORDER is contractual, and for a parameter set it
    IS: the order is the grid's column order. So this asserts the opposite of
    the usual rule, deliberately."""
    from engcore.inference import CalibrationParameterSet, ParameterBounds, ParameterIdentity
    from engcore.scientific import ModelReference

    model = ModelReference("m.a", "1")
    r = ParameterIdentity(
        "r", "ohm", model, ParameterBounds(Quantity(0.0, "ohm"), Quantity(10.0, "ohm"))
    )
    a = ParameterIdentity(
        "a", "1/kelvin", model,
        ParameterBounds(Quantity(-0.01, "1/kelvin"), Quantity(0.01, "1/kelvin")),
    )
    assert CalibrationParameterSet((r, a)).digest != CalibrationParameterSet((a, r)).digest


# =====================================================================
# PART I / P -- determinism across fresh processes
# =====================================================================

_DIGEST_PROBE = """
import json, sys
sys.path.insert(0, sys.argv[1])
from engcore.inference import ParameterBounds, ParameterIdentity, CalibrationParameterSet
from engcore.adequacy import PredictiveEvidenceIdentity
from engcore.scientific import ModelReference, TwinReference
from engcore.scientific.units.quantity import Quantity

model = ModelReference("m.a", "1")
p = ParameterIdentity("r", "ohm", model,
                      ParameterBounds(Quantity(0.0, "ohm"), Quantity(10.0, "ohm")))
e = PredictiveEvidenceIdentity(observation_key="c:y", observed_value=1.0, unit="ohm",
                               likelihood_sigma=0.1, heldout_dataset_id="h",
                               posterior_dataset_id="p", twin=TwinReference("t", "1"))
print(json.dumps({
    "parameter": p.digest,
    "parameter_set": CalibrationParameterSet((p,)).digest,
    "evidence": e.digest,
}))
"""


def _digests_in_fresh_process(hashseed: str, cwd: pathlib.Path) -> dict:
    import os

    out = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", _DIGEST_PROBE, str(REPO / "src")],
        capture_output=True, text=True, check=True, cwd=str(cwd),
        env=dict(os.environ, PYTHONHASHSEED=hashseed),
    )
    return json.loads(out.stdout)


def test_scientific_digests_are_identical_across_fresh_processes():
    """Different hash seeds and different working directories, same digests.

    A digest that moved with PYTHONHASHSEED would be reading set or dict
    iteration order; one that moved with cwd would be reading a path.
    """
    results = [
        _digests_in_fresh_process("0", REPO),
        _digests_in_fresh_process("1", REPO),
        _digests_in_fresh_process("random", REPO),
        _digests_in_fresh_process("random", REPO.parent),
    ]
    assert all(r == results[0] for r in results), results


def test_the_same_digest_is_produced_twice_in_one_process():
    from engcore.inference import ParameterBounds, ParameterIdentity
    from engcore.scientific import ModelReference

    def build():
        return ParameterIdentity(
            "r", "ohm", ModelReference("m.a", "1"),
            ParameterBounds(Quantity(0.0, "ohm"), Quantity(10.0, "ohm")),
        )

    assert build().digest == build().digest


def test_no_digest_payload_contains_a_path_or_an_address():
    for name, record in fixtures().items():
        blob = json.dumps(record.to_dict(), sort_keys=True, allow_nan=False)
        for forbidden in ("0x", "C:\\", "/home/", "site-packages", ".venv"):
            assert forbidden not in blob, f"{name} carries {forbidden!r}"
