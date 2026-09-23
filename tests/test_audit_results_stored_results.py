"""Audit stream "results": the stored-result read boundary (RES-01, RES-02, RES-05).

Each test here was written against the unfixed reader and seen failing first.

RES-01  The silent-provenance read exemption applied to every declared version,
        including the current one, so a current payload could attribute itself
        to a fabricated model and solver while its provenance named nobody, and
        read back as usable and analytically verified -- and a credibility report
        around it was SUPPORTED. The constructor refuses the same record. The
        serialization contract is frozen (no version bump), so the payload still
        reads, but it is MARKED: ``stored_attribution_gap`` names the gap, the
        bytes round-trip as written, and a credibility report assembled around it
        carries a NOT_RUN check and cannot be SUPPORTED. Complete provenance is
        not marked; contradictory provenance is still refused.
RES-02  Relabelling a payload to an older version silently dropped content the
        older reader ignores by version (validity, data references, bindings);
        and a current payload with a required key deleted read as the older
        shape. A payload declaring a version may carry only keys that version's
        writer could emit, and must carry the keys it always emitted.
RES-05  A missing ``convergence`` or ``validation`` key fell back to the most
        permissive state, so a DIVERGED/FAIL result read back as usable.
"""

from __future__ import annotations

import copy
import json

import pytest

from tests.issued_levels import analytic_issuer_evidence
from engcore.domains.thermal_models.lumped import LUMPED_CAPACITY_MODEL
from engcore.mcp.evidence import (
    STORED_ATTRIBUTION_CHECK,
    CredibilityEvidenceReport,
    CredibilityVerdict,
)
from engcore.scientific.errors import ScientificCoreError
from engcore.scientific.ir.problem import ModelReference
from engcore.scientific.models.definition import ValidityAssessment, ValidityStatus
from engcore.scientific.results.data_reference import ScientificDataReference
from engcore.scientific.results.provenance import ExecutionBinding, ProvenanceRecord
from engcore.scientific.results.result import (
    RESULT_SCHEMA,
    SUPPORTED_RESULT_SCHEMAS,
    ScientificResult,
    stored_attribution_gap,
)
from engcore.scientific.results.validation import (
    ValidationCheck,
    ValidationLevel,
    ValidationOutcome,
    ValidationReport,
)
from engcore.scientific.solvers.protocol import ConvergenceState, SolverIdentity
from engcore.scientific.units.quantity import Quantity

MODEL = ModelReference(LUMPED_CAPACITY_MODEL.model_id, LUMPED_CAPACITY_MODEL.version)
SOLVER = SolverIdentity("audit.lumped_ode", "1")
FABRICATED_SOLVER = SolverIdentity("fabricated_solver", "9")
CONDITIONS = tuple(c.name for c in LUMPED_CAPACITY_MODEL.validity.conditions)


def _in_domain() -> ValidityAssessment:
    return ValidityAssessment(status=ValidityStatus.IN_DOMAIN, satisfied=CONDITIONS)


def _result(**overrides) -> ScientificResult:
    provenance = ProvenanceRecord(
        run_id="audit-run", bindings=(ExecutionBinding(model=MODEL, solver=SOLVER),)
    )
    # R-04 (core re-audit 2026-09-16): ANALYTICALLY_VERIFIED is held to its issuer's record now.
    # The level is this fixture's means and not its subject, so the check carries the two records a
    # genuine issuer writes. Every assertion below is unchanged.
    check = ValidationCheck(
        name="analytic",
        outcome=ValidationOutcome.PASS,
        establishes=ValidationLevel.ANALYTICALLY_VERIFIED,
        residual=1e-9,
        tolerance=1e-6,
        evidence=analytic_issuer_evidence(),
    )
    fields = dict(
        result_id="audit-result",
        values={"T": Quantity(350.0, "K")},
        provenance=provenance,
        models=(MODEL.key,),
        solver=SOLVER,
        convergence=ConvergenceState.CONVERGED,
        validation=ValidationReport(checks=(check,)),
        validity={MODEL.model_id: _in_domain()},
    )
    fields.update(overrides)
    return ScientificResult(**fields)


def _payload(**overrides) -> dict:
    return json.loads(json.dumps(_result(**overrides).to_dict()))


def _silenced(payload: dict) -> dict:
    """The fabricated-attribution shape from the audit probe: a model and a
    solver nothing ran, and a provenance that names no participant at all."""
    payload = copy.deepcopy(payload)
    payload["solver"] = FABRICATED_SOLVER.to_dict()
    payload["provenance"]["models"] = []
    payload["provenance"]["solvers"] = []
    payload["provenance"]["bindings"] = []
    return payload


# =====================================================================
# RES-01
# =====================================================================

def test_res01_the_frozen_format_does_not_move():
    assert RESULT_SCHEMA == "scientific_result/4"
    assert SUPPORTED_RESULT_SCHEMAS == (
        "scientific_result/1",
        "scientific_result/2",
        "scientific_result/3",
        "scientific_result/4",
    )
    assert _result().to_dict()["schema"] == "scientific_result/4"


def test_res01_construction_still_refuses_silent_provenance():
    silent = ProvenanceRecord(run_id="silent")
    with pytest.raises(ScientificCoreError, match="provenance does not name"):
        _result(provenance=silent)


def test_res01_complete_provenance_is_not_marked():
    record = ScientificResult.from_dict(_payload())
    assert stored_attribution_gap(record) == ()
    assert stored_attribution_gap(_result()) == ()


@pytest.mark.parametrize("version", [1, 2, 3, 4])
def test_res01_a_silent_payload_of_any_version_is_read_but_marked(version):
    payload = _silenced(_payload())
    payload["schema"] = f"scientific_result/{version}"
    for newer in {
        1: ("validity", "validity_not_assessed", "data_references"),
        2: ("validity", "validity_not_assessed"),
        3: ("validity_not_assessed",),
    }.get(version, ()):
        payload.pop(newer)
    record = ScientificResult.from_dict(payload)
    gap = stored_attribution_gap(record)
    assert any("model" in g for g in gap) and any("solver" in g for g in gap)


def test_res01_a_marked_current_record_round_trips_byte_identically():
    payload = _silenced(_payload())
    record = ScientificResult.from_dict(payload)
    assert record.to_dict() == payload
    again = ScientificResult.from_dict(json.loads(json.dumps(record.to_dict())))
    assert stored_attribution_gap(again) == stored_attribution_gap(record)
    assert json.dumps(again.to_dict(), sort_keys=True) == json.dumps(payload, sort_keys=True)


def test_res01_provenance_naming_the_model_but_no_solver_marks_the_solver():
    payload = _payload()
    payload["provenance"]["bindings"] = []
    payload["provenance"]["solvers"] = []
    payload["solver"] = FABRICATED_SOLVER.to_dict()
    gap = stored_attribution_gap(ScientificResult.from_dict(payload))
    assert len(gap) == 1 and "fabricated_solver" in gap[0]


def test_res01_provenance_naming_the_solver_but_no_model_marks_the_model():
    payload = _payload()
    payload["provenance"]["bindings"] = []
    payload["provenance"]["models"] = []
    payload["provenance"]["solvers"] = [list(SOLVER.key)]
    payload["models"] = [["fabricated.model", "9"]]
    payload["validity"] = {}
    payload["validity_not_assessed"] = {"fabricated.model": "not assessed"}
    gap = stored_attribution_gap(ScientificResult.from_dict(payload))
    assert len(gap) == 1 and "fabricated.model" in gap[0]


def test_res01_contradictory_provenance_is_still_refused():
    payload = _payload()
    payload["provenance"]["bindings"] = []
    payload["provenance"]["models"] = [["other.model", "1"]]
    with pytest.raises(ScientificCoreError, match="provenance does not name"):
        ScientificResult.from_dict(payload)
    payload = _payload()
    payload["provenance"]["bindings"] = []
    payload["provenance"]["solvers"] = [["other.solver", "1"]]
    with pytest.raises(ScientificCoreError, match="provenance does not name that solver"):
        ScientificResult.from_dict(payload)


def test_res01_a_credibility_report_cannot_launder_a_silent_record():
    control = ScientificResult.from_dict(_payload())
    assert (
        CredibilityEvidenceReport.from_result(control).verdict
        is CredibilityVerdict.SUPPORTED
    ), "the control must be SUPPORTED, or the refusal below proves nothing"

    silent = ScientificResult.from_dict(_silenced(_payload()))
    report = CredibilityEvidenceReport.from_result(silent, contributing_models=silent.models)
    assert report.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE
    assert report.not_run_checks == (STORED_ATTRIBUTION_CHECK,)
    # And the downgrade survives the report's own serialization boundary.
    again = CredibilityEvidenceReport.from_dict(json.loads(json.dumps(report.to_dict())))
    assert again.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE


# =====================================================================
# RES-02
# =====================================================================

def _outside_with_reference() -> dict:
    reference, _bytes = ScientificDataReference.for_values("T:field", [1.0, 2.0], unit="K")
    violated = CONDITIONS[:1]
    return _payload(
        validity={
            MODEL.model_id: ValidityAssessment(
                status=ValidityStatus.OUTSIDE_VALIDATED_DOMAIN,
                satisfied=CONDITIONS[1:],
                violated=violated,
            )
        },
        data_references=(reference,),
    )


@pytest.mark.parametrize("version", [1, 2, 3])
def test_res02_relabelling_to_an_older_version_is_refused_not_downgraded(version):
    payload = _outside_with_reference()
    payload["schema"] = f"scientific_result/{version}"
    with pytest.raises(ScientificCoreError, match="scientific_result/"):
        ScientificResult.from_dict(payload)


def test_res02_a_v3_payload_carrying_a_v4_key_is_refused():
    payload = _payload()
    payload["schema"] = "scientific_result/3"
    assert payload["validity_not_assessed"] == {}
    with pytest.raises(ScientificCoreError, match="validity_not_assessed"):
        ScientificResult.from_dict(payload)


@pytest.mark.parametrize(
    "version, key",
    [
        ("scientific_result/4", "validity"),
        ("scientific_result/4", "validity_not_assessed"),
        ("scientific_result/4", "data_references"),
        ("scientific_result/3", "validity"),
        ("scientific_result/2", "data_references"),
    ],
)
def test_res02_a_key_the_declared_version_always_wrote_is_required(version, key):
    payload = _payload()
    payload["schema"] = version
    for newer in {
        "scientific_result/2": ("validity", "validity_not_assessed"),
        "scientific_result/3": ("validity_not_assessed",),
    }.get(version, ()):
        payload.pop(newer)
    del payload[key]
    with pytest.raises(ScientificCoreError, match=key):
        ScientificResult.from_dict(payload)


def test_res02_a_provenance_relabelled_v1_while_carrying_bindings_is_refused():
    payload = _payload()
    payload["schema"] = "scientific_result/4"
    payload["solver"] = FABRICATED_SOLVER.to_dict()
    payload["provenance"]["solvers"] = [list(SOLVER.key), list(FABRICATED_SOLVER.key)]
    payload["provenance"]["schema"] = "provenance_record/1"
    with pytest.raises(ScientificCoreError, match="bindings"):
        ProvenanceRecord.from_dict(payload["provenance"])
    with pytest.raises(ScientificCoreError, match="bindings"):
        ScientificResult.from_dict(payload)


def test_res02_a_current_provenance_with_its_bindings_key_deleted_is_refused():
    payload = _payload()
    del payload["provenance"]["bindings"]
    with pytest.raises(ScientificCoreError, match="bindings"):
        ProvenanceRecord.from_dict(payload["provenance"])


@pytest.mark.parametrize("version", [1, 2])
def test_res02_an_older_provenance_carrying_transfers_is_refused(version):
    payload = _payload()["provenance"]
    payload["schema"] = f"provenance_record/{version}"
    if version == 1:
        del payload["bindings"]
    with pytest.raises(ScientificCoreError, match="transfers"):
        ProvenanceRecord.from_dict(payload)


def test_res02_an_older_provenance_carrying_a_non_quantity_input_is_refused():
    from engcore.scientific.ir.values import BooleanValue

    record = ProvenanceRecord(run_id="typed", inputs={"steady_state": BooleanValue(True)})
    payload = json.loads(json.dumps(record.to_dict()))
    payload["schema"] = "provenance_record/3"
    with pytest.raises(ScientificCoreError, match="provenance_record/3"):
        ProvenanceRecord.from_dict(payload)


def test_res02_honest_older_payloads_still_load():
    payload = _payload()
    for version, drop in (
        ("scientific_result/4", ()),
        ("scientific_result/3", ("validity_not_assessed",)),
        ("scientific_result/2", ("validity", "validity_not_assessed")),
        ("scientific_result/1", ("validity", "validity_not_assessed", "data_references")),
    ):
        older = copy.deepcopy(payload)
        older["schema"] = version
        for key in drop:
            del older[key]
        assert ScientificResult.from_dict(older).result_id == "audit-result"
    provenance = _payload()["provenance"]
    for version, drop in (
        ("provenance_record/3", ()),
        ("provenance_record/2", ("transfers",)),
        ("provenance_record/1", ("transfers", "bindings")),
    ):
        older = copy.deepcopy(provenance)
        older["schema"] = version
        for key in drop:
            del older[key]
        if "bindings" in drop:
            older["solvers"] = []
        assert ProvenanceRecord.from_dict(older).run_id == "audit-run"


# =====================================================================
# RES-05
# =====================================================================

def _bad_payload() -> dict:
    return _payload(
        convergence=ConvergenceState.DIVERGED,
        validation=ValidationReport(
            checks=(
                ValidationCheck(
                    name="energy", outcome=ValidationOutcome.FAIL, residual=1.0, tolerance=1e-3
                ),
            )
        ),
    )


@pytest.mark.parametrize("key", ["convergence", "validation"])
@pytest.mark.parametrize("version", [1, 2, 3, 4])
def test_res05_a_missing_convergence_or_validation_is_refused(key, version):
    payload = _bad_payload()
    assert ScientificResult.from_dict(payload).is_usable is False
    payload["schema"] = f"scientific_result/{version}"
    for newer in {
        1: ("validity", "validity_not_assessed", "data_references"),
        2: ("validity", "validity_not_assessed"),
        3: ("validity_not_assessed",),
    }.get(version, ()):
        payload.pop(newer)
    del payload[key]
    with pytest.raises(ScientificCoreError, match=key):
        ScientificResult.from_dict(payload)


def test_res05_a_null_validation_is_refused_too():
    payload = _bad_payload()
    payload["validation"] = None
    with pytest.raises(ScientificCoreError, match="validation"):
        ScientificResult.from_dict(payload)
