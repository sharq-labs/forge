"""BIG 13 round-5 review (BIG 14 14.1): one regression per fixed finding.

F1 a provider comparison is bound to the providers the run recorded (two executions of one provider relabelled as two providers are
refused) and its fields are strict; F2 an UNKNOWN-input entry cannot say "none"; F3 the trace is of a key output; F5 reference readers
refuse pre-coercible numbers; F8 a restated status basis, extra summary fields and a malformed manifest or plan are refusals.
"""

from __future__ import annotations

import json
import os
import shutil

import pytest

from engcore.engineering import BundleRefused, EnvelopeBound, EvidenceLink, UncertaintyStatement, verify_bundle
from engcore.engineering.ladder import check_provider_comparison
from engcore.engineering.reference import ReferenceCondition, ReferenceRecord
from engcore.scientific.errors import InvalidScientificProblem
from tests.test_engineering_contracts import _provider_record, _ref, _rewrite_summary, _run, _summary, _write

CAVITY = os.path.join(os.path.dirname(__file__), "..", "docs", "flagships", "runs", "cavity_re100")


# ------------------------------------------------------------------------------------------------ F1 provider comparisons
def test_f1_a_comparison_is_bound_to_the_providers_the_run_recorded_for_its_executions():
    run = {"a" * 64: "openfoam", "b" * 64: "su2", "c" * 64: "openfoam", "d" * 64: "fenicsx"}
    check_provider_comparison(_provider_record(), run)
    with pytest.raises(InvalidScientificProblem, match="one recorded provider"):
        check_provider_comparison(_provider_record(b="c" * 64), run)                    # two openfoam meshes relabelled openfoam / su2
    with pytest.raises(InvalidScientificProblem, match="provider labels"):
        check_provider_comparison(_provider_record(pa="su2", pb="openfoam"), run)       # labels swapped against what the run recorded
    check_provider_comparison(_provider_record(b="d" * 64, pb="fenicsx.dolfinx"), run)  # a qualified label of the recorded provider
    with pytest.raises(InvalidScientificProblem, match="provider labels"):
        check_provider_comparison(_provider_record(b="d" * 64, pb="fenicsxy"), run)     # a prefix that is not a qualification


@pytest.mark.parametrize("field, value, match", [
    ("post_hoc", "false", "boolean"),
    ("relative_tolerance", False, "relative tolerance"),
    ("relative_tolerance", "0.0", "relative tolerance"),
])
def test_f1_declaration_fields_are_strictly_typed(field, value, match):
    record = _provider_record()
    record["declaration"][field] = value
    with pytest.raises(InvalidScientificProblem, match=match):
        check_provider_comparison(record, {"a" * 64: "openfoam", "b" * 64: "su2"})


@pytest.mark.parametrize("raw", ["-1.0", 0.0009, " 0.0009", "9e-4", "nan", "inf"])
def test_f1_the_maximum_difference_must_be_canonical_finite_non_negative_text(raw):
    with pytest.raises(InvalidScientificProblem, match="maximum difference"):
        check_provider_comparison(_provider_record(max_absolute=raw), {"a" * 64: "openfoam", "b" * 64: "su2"})


def test_f1_a_consistently_rewritten_cavity_bundle_that_pairs_two_openfoam_meshes_as_openfoam_and_su2_is_refused(tmp_path):
    d = str(tmp_path / "cavity")
    shutil.copytree(CAVITY, d)
    verify_bundle(d)
    result = json.loads(open(os.path.join(d, "result.json"), "rb").read())
    openfoam = sorted(p["execution_identity_digest"] for p in result["provider_records"] if p["provider_id"] == "openfoam")
    assert len(openfoam) >= 2

    def relabel(w):
        level = w["verification"]["levels"][4]
        link = next(l for l in level["evidence"] if l["kind"] == "provider_comparison")
        record = dict(link["record"], a_identity=openfoam[0], b_identity=openfoam[1])      # labels stay "openfoam" / "su2"
        level["evidence"][level["evidence"].index(link)] = EvidenceLink.of_record(
            "provider_comparison", record, link["classification"], link["outcome"], link["note"]).to_dict()
    _rewrite_summary(d, relabel)
    with pytest.raises(BundleRefused, match="one recorded provider"):
        verify_bundle(d)


# ------------------------------------------------------------------------------------------------ F2 the UNKNOWN list names inputs
@pytest.mark.parametrize("entry", ["none", " None ", "n/a", "-", "", "  "])
def test_f2_an_unknown_input_entry_that_says_nothing_is_refused(entry):
    with pytest.raises(InvalidScientificProblem, match="must name"):
        UncertaintyStatement((), (entry,), "NOT QUANTIFIED", ("fixture",), "declared", "none used")
    UncertaintyStatement(("none",), ("ambient profile (declared)",), "NOT QUANTIFIED", ("fixture",), "declared", "none used")   # "none" KNOWN is honest


def test_f2_a_bundle_whose_unknown_list_is_rewritten_to_none_is_refused(tmp_path):
    d, *_ = _write(tmp_path, "none")
    _rewrite_summary(d, lambda w: w["uncertainty"].update(unknown_input_uncertainty=["none"]))
    with pytest.raises(BundleRefused, match="uncertainty statement"):
        verify_bundle(d)


# ------------------------------------------------------------------------------------------------ F3 the trace is of a key output
def test_f3_the_trace_must_be_of_a_key_output_in_the_summary_and_in_the_bundle(tmp_path):
    request, context, result = _run()
    _summary(request, context, result)                                      # the helper traces a key output
    from engcore.engineering import build_summary
    from engcore.engineering.ladder import VerificationLadder, contract_integrity_entry
    ladder = VerificationLadder.of(l1=contract_integrity_entry(result.preflight, result))
    stmt = UncertaintyStatement((), ("all node outputs",), "NOT QUANTIFIED", ("fixture",), "declared", "none used")
    with pytest.raises(InvalidScientificProblem, match="not one of the key outputs"):
        build_summary("f", request, result, outputs=[("Peak", "peak_temperature")], ladder=ladder, uncertainty=stmt, trace_observable="heat_power")
    d, *_ = _write(tmp_path, "trace")
    _rewrite_summary(d, lambda w: w.update(trace_observable="heat_power"))
    with pytest.raises(BundleRefused, match="not one of its key outputs"):
        verify_bundle(d)


# ------------------------------------------------------------------------------------------------ F5 strict reference numbers
@pytest.mark.parametrize("wire", [True, 1.0, "1_00", " 1e2 ", "1e2", "nan"])
def test_f5_a_reference_condition_is_read_only_from_the_exact_text_to_dict_writes(wire):
    with pytest.raises(InvalidScientificProblem):
        ReferenceCondition.from_dict({"name": "reynolds", "value": wire, "unit": "dimensionless"})
    assert ReferenceCondition.from_dict({"name": "reynolds", "value": "100.0", "unit": "dimensionless"}).value == 100.0


@pytest.mark.parametrize("low", [True, "1", float("nan")])
def test_f5_an_envelope_bound_is_a_finite_number_not_a_truth_value_or_text(low):
    with pytest.raises(InvalidScientificProblem):
        EnvelopeBound("reynolds", low, 200.0, "dimensionless")
    with pytest.raises(InvalidScientificProblem):
        EnvelopeBound.from_dict({"name": "reynolds", "low": low if isinstance(low, str) else repr(low), "high": "1_00", "unit": "dimensionless"})


def test_f5_reference_data_values_are_read_strictly():
    payload = _ref().to_dict()
    ReferenceRecord.from_dict(payload)
    q, values = payload["data"][0]
    payload["data"][0] = [q, [float(values[0])] + list(values[1:])]
    with pytest.raises(InvalidScientificProblem):
        ReferenceRecord.from_dict(payload)


# ------------------------------------------------------------------------------------------------ F8 constants, fields, malformed files
def test_f8_a_restated_status_basis_or_an_extra_summary_field_is_refused(tmp_path):
    d, *_ = _write(tmp_path, "basis")
    _rewrite_summary(d, lambda w: w.update(scientific_status_basis="validated against experiment"))
    with pytest.raises(BundleRefused, match="basis"):
        verify_bundle(d)
    d, *_ = _write(tmp_path, "extra")
    _rewrite_summary(d, lambda w: w.update(validated=True))
    with pytest.raises(BundleRefused, match="other fields"):
        verify_bundle(d)


@pytest.mark.parametrize("name, content", [("manifest.json", b"[]"), ("manifest.json", b"{not json"), ("plan.json", b"{not json")])
def test_f8_a_malformed_manifest_or_plan_is_a_refusal_not_a_crash(tmp_path, name, content):
    d, *_ = _write(tmp_path, "malformed")
    open(os.path.join(d, name), "wb").write(content)
    with pytest.raises(BundleRefused):
        verify_bundle(d)


@pytest.mark.parametrize("bad", [True, "1", float("inf")])
def test_f5_reference_data_are_strict_when_a_record_is_built_in_memory(bad):
    import dataclasses
    good = _ref()
    q, values = good.data[0]
    with pytest.raises(InvalidScientificProblem):
        dataclasses.replace(good, data=((q, (bad,) + tuple(values[1:])),) + tuple(good.data[1:]))
