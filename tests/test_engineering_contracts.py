"""BIG 13 engineering layer contracts: references, ladder, summary, bundle, VTU.  No provider is needed here.

The adversarial cases are the point: a reference that does not apply is never read as met, solver agreement
cannot reach a reference level, a post-hoc comparison cannot reach a reference level, an edited bundle is
refused, a summary cannot omit model discrepancy.
"""

from __future__ import annotations

import json
import os

import numpy as np
import pytest

from engcore.engineering import (
    BundleRefused, EnvelopeBound, EvidenceLink, LevelEntry, LevelStatus, PredeclaredCriterion, ReferenceCondition, ReferenceRecord,
    UncertaintyStatement, VerificationLadder, build_summary, compare_to_reference, verify_bundle, write_bundle, write_vtu,
)
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.oracles import OracleKind
from engcore.scientific.units.quantity import Quantity
from engcore.system_runtime import SystemExecutor, assess_constraints
from tests.system_runtime_fixtures import build, sha


def _ref(kind=OracleKind.BENCHMARK_DATASET, *, envelope=(EnvelopeBound("reynolds", 99.0, 101.0, "dimensionless"),), data=None):
    return ReferenceRecord(
        "ghia-like", "A centreline benchmark", "Someone", "J. Test 1, 1982", "https://example.org/paper.pdf", "table values quoted with attribution", kind,
        (ReferenceCondition("reynolds", 100.0, "dimensionless"),), (("u", "dimensionless"),), data if data is not None else (("u", (0.0, 0.1, 1.0)),),
        sha("source bytes"), "typed from the published table", envelope)


def test_a_reference_states_its_kind_source_and_conditions_and_has_a_content_identity():
    ref = _ref()
    assert ref.kind is OracleKind.BENCHMARK_DATASET and ref.digest == _ref().digest and ref.digest != _ref(OracleKind.EXPERIMENTAL_DATASET).digest
    with pytest.raises(InvalidScientificProblem, match="https source"):
        ReferenceRecord("x", "t", "a", "p", "http://x", "l", OracleKind.BENCHMARK_DATASET, (ReferenceCondition("re", 1.0, "dimensionless"),), (), (), sha("s"), "e")
    with pytest.raises(InvalidScientificProblem, match="SHA-256"):
        ReferenceRecord("x", "t", "a", "p", "https://x", "l", OracleKind.BENCHMARK_DATASET, (ReferenceCondition("re", 1.0, "dimensionless"),), (), (), "", "e")
    with pytest.raises(InvalidScientificProblem, match="conditions"):
        ReferenceRecord("x", "t", "a", "p", "https://x", "l", OracleKind.EXPERIMENTAL_DATASET, (), (), (), sha("s"), "e")
    # an analytic reference may have neither a source file nor an https URL
    analytic = ReferenceRecord("closed-form", "sigma = -E alpha dT", "textbook", "-", "", "derived, not copied", OracleKind.ANALYTIC_REFERENCE, (), (), (), "", "closed form")
    assert analytic.kind is OracleKind.ANALYTIC_REFERENCE


def test_applicability_is_within_only_when_every_condition_is_known_and_inside():
    ref = _ref()
    assert ref.applicability({"reynolds": Quantity(100.0, "dimensionless")}).status == "within"
    assert ref.applicability({"reynolds": Quantity(10.0, "dimensionless")}).status == "outside"
    assert ref.applicability({}).status == "unknown"                                  # a missing condition is never "within"
    no_envelope = _ref(envelope=())
    assert no_envelope.applicability({"reynolds": Quantity(100.0, "dimensionless")}).status == "unknown"    # nor is a missing envelope


def test_a_reference_that_does_not_apply_is_neither_met_nor_unmet():
    crit = PredeclaredCriterion("c", "u", "max_abs", Quantity(0.01, "dimensionless"), "test file")
    good = compare_to_reference(_ref(), crit, {"reynolds": Quantity(100, "dimensionless")}, value=Quantity(0.004, "dimensionless"), compared_identity=sha("run"))
    bad = compare_to_reference(_ref(), crit, {"reynolds": Quantity(100, "dimensionless")}, value=Quantity(0.4, "dimensionless"), compared_identity=sha("run"))
    off = compare_to_reference(_ref(), crit, {"reynolds": Quantity(10, "dimensionless")}, value=Quantity(0.0, "dimensionless"), compared_identity=sha("run"))
    assert (good.outcome, bad.outcome, off.outcome) == ("met", "not_met", "not_applicable")
    assert off.value.magnitude == 0.0 and not off.within_tolerance                     # a perfect number does not rescue an inapplicable reference
    assert good.classification == "numerical_benchmark_comparison_not_validation_grant"
    post = compare_to_reference(_ref(), PredeclaredCriterion("c", "u", "max_abs", Quantity(0.01, "dimensionless"), "after seeing", post_hoc=True),
                                {"reynolds": Quantity(100, "dimensionless")}, value=Quantity(0.004, "dimensionless"), compared_identity=sha("run"))
    assert post.classification.startswith("post_hoc_")
    # a tolerance changed after the fact is a different criterion, so the original outcome stays attributable
    loose = PredeclaredCriterion("c", "u", "max_abs", Quantity(1.0, "dimensionless"), "test file")
    assert loose.digest != crit.digest


def test_the_ladder_cannot_claim_a_level_without_evidence_or_with_the_wrong_kind_of_evidence():
    with pytest.raises(InvalidScientificProblem, match="without evidence"):
        LevelEntry(3, LevelStatus.REACHED)
    corroboration = EvidenceLink("provider_comparison", sha("cmp"), "solver_corroboration_not_validation", "met")
    LevelEntry(5, LevelStatus.REACHED, (corroboration,))
    with pytest.raises(InvalidScientificProblem, match="numerical-benchmark comparison only"):
        LevelEntry(6, LevelStatus.REACHED, (corroboration,))                             # solver agreement is never a reference level
    with pytest.raises(InvalidScientificProblem, match="experimental-data comparison only"):
        LevelEntry(7, LevelStatus.REACHED, (EvidenceLink("reference_comparison", sha("c"), "numerical_benchmark_comparison_not_validation_grant", "met"),))
    with pytest.raises(InvalidScientificProblem, match="MET"):
        LevelEntry(6, LevelStatus.REACHED, (EvidenceLink("reference_comparison", sha("c"), "numerical_benchmark_comparison_not_validation_grant", "not_met"),))
    with pytest.raises(InvalidScientificProblem, match="post-hoc"):
        LevelEntry(5, LevelStatus.REACHED, (EvidenceLink("provider_comparison", sha("c"), "post_hoc_solver_corroboration_not_validation", "met"),))
    ok = LevelEntry(6, LevelStatus.REACHED, (EvidenceLink("reference_comparison", sha("c"), "numerical_benchmark_comparison_not_validation_grant", "met"),))
    assert ok.status is LevelStatus.REACHED
    failed = LevelEntry(6, LevelStatus.ATTEMPTED_NOT_REACHED, (EvidenceLink("reference_comparison", sha("c"), "numerical_benchmark_comparison_not_validation_grant", "not_met"),))
    assert failed.evidence                                                              # a failed attempt keeps its evidence


def test_ladder_reports_where_evidence_stops():
    l1 = LevelEntry(1, LevelStatus.REACHED, (EvidenceLink("contract", sha("a"), "contract_integrity", "met"),))
    l2 = LevelEntry(2, LevelStatus.REACHED, (EvidenceLink("balance", sha("b"), "conservation_residual", "met"),))
    l5 = LevelEntry(5, LevelStatus.REACHED, (EvidenceLink("provider_comparison", sha("c"), "solver_corroboration_not_validation", "met"),))
    ladder = VerificationLadder.of(a=l1, b=l2, c=l5)
    assert ladder.verification_reached == 2                                             # level 3 not reached, so 4 does not count
    assert ladder.corroboration_reached and ladder.validation_reached == "none"
    assert ladder.to_dict()["classification"] == "report_vocabulary_not_a_validation_grant"
    with pytest.raises(InvalidScientificProblem, match="every one of the seven levels"):
        VerificationLadder((l1,))


def _run():
    request, context, knobs = build()
    result = SystemExecutor(context).run(request)
    return request, context, result


def _summary(request, context, result, **kw):
    ladder = VerificationLadder.of(a=LevelEntry(1, LevelStatus.REACHED, (EvidenceLink("contract", sha("a"), "contract_integrity", "met"),), "units and identities checked"))
    stmt = kw.pop("uncertainty", UncertaintyStatement(("none",), ("all node outputs",), "NOT QUANTIFIED (unknown, not zero)", ("fixture",), "declared fixture range",
                                                     "no benchmark used"))
    return build_summary("fixture system", request, result, outputs=[("Peak temperature", "peak_temperature")],
                         constraints=assess_constraints(result, context.system, context.constraints), ladder=ladder, uncertainty=stmt,
                         trace_observable="peak_temperature", **kw)


def test_the_summary_reports_unknown_uncertainty_as_unknown_and_takes_its_status_from_the_credibility_authority():
    request, context, result = _run()
    s = _summary(request, context, result)
    text = s.render_text()
    assert "UNKNOWN (" in text and "INSUFFICIENT_EVIDENCE".lower() in s.scientific_status.lower()
    assert s.scientific_status == "insufficient_evidence" and s.trace_complete
    assert "model discrepancy: NOT QUANTIFIED" in text and "NOT AVAILABLE" in text       # no reference: stated, not omitted
    assert s.digest == _summary(request, context, result).digest                         # deterministic
    with pytest.raises(InvalidScientificProblem, match="must each be stated"):
        UncertaintyStatement((), (), "", (), "x", "y")                                   # model discrepancy cannot be left silent


def test_a_summary_refuses_a_request_that_is_not_the_runs():
    request, context, result = _run()
    other = build(conductivity=99.0)[0]
    with pytest.raises(InvalidScientificProblem, match="not the one this result"):
        _summary(other, context, result)


def test_a_refused_step_still_summarises_with_the_output_unavailable_never_a_number():
    from tests.system_runtime_fixtures import Knobs
    request, context, knobs = build(knobs=Knobs(omit_applicability=True))              # the solved state never establishes its applicability
    result = SystemExecutor(context).run(request)
    assert result.receipt("thermal").status.value == "refused"
    s = _summary(request, context, result)
    (out,) = s.key_outputs
    assert out.value is None and out.availability in ("blocked", "refused") and "UNAVAILABLE" in s.render_text().upper()
    assert all(c.status == "unavailable" for c in s.constraints)                       # a missing result is never a pass
    assert s.scientific_status == "insufficient_evidence" and s.execution in ("partial", "failed")


def test_a_bundle_verifies_and_any_edit_after_writing_is_refused(tmp_path):
    request, context, result = _run()
    s = _summary(request, context, result)
    d = str(tmp_path / "b")
    manifest = write_bundle(d, name="fixture", request=request, result=result, summary=s, references=[_ref()], artifacts={"field.vtu": b"<fake/>"})
    assert verify_bundle(d).digest == manifest.digest
    assert {"request.json", "plan.json", "result.json", "summary.json", "summary.txt", "references/ghia-like.json", "artifacts/field.vtu"} <= {f for f, _ in manifest.files}
    # bulk data is a file with a digest, never inlined
    assert b"<fake/>" not in open(os.path.join(d, "result.json"), "rb").read()
    with open(os.path.join(d, "artifacts", "field.vtu"), "ab") as fh:
        fh.write(b" ")
    with pytest.raises(BundleRefused, match="changed after the bundle was written"):
        verify_bundle(d)
    with open(os.path.join(d, "artifacts", "field.vtu"), "wb") as fh:
        fh.write(b"<fake/>")
    verify_bundle(d)
    # editing the result value AND its file hash in the manifest is still refused: the result re-derives its own digest
    path = os.path.join(d, "result.json")
    wire = json.loads(open(path, "rb").read())
    wire["observables"][0]["value"]["value"]["magnitude"] += 5.0
    open(path, "wb").write((json.dumps(wire, sort_keys=True, indent=1) + "\n").encode())
    mpath = os.path.join(d, "manifest.json")
    m = json.loads(open(mpath, "rb").read())
    import hashlib
    m["files"] = [[f, hashlib.sha256(open(os.path.join(d, *f.split("/")), "rb").read()).hexdigest()] for f, _ in m["files"]]
    m.pop("bundle_digest")
    from engcore.engineering.bundle import _json_bytes, _sha
    m["bundle_digest"] = _sha(_json_bytes(m))
    open(mpath, "wb").write(_json_bytes(m))
    with pytest.raises(Exception, match="does not carry the value"):
        verify_bundle(d)


def test_a_bundle_refuses_files_that_are_not_in_the_manifest(tmp_path):
    request, context, result = _run()
    d = str(tmp_path / "b")
    write_bundle(d, name="fixture", request=request, result=result, summary=_summary(request, context, result))
    open(os.path.join(d, "artifacts_extra.txt"), "wb").write(b"planted")
    with pytest.raises(BundleRefused, match="not in the manifest"):
        verify_bundle(d)


def test_vtu_is_written_with_identity_and_units_and_refuses_bad_fields():
    from engcore.spatial.mesh import CellType, CoordinateFrame, GroupKind, PhysicalGroup, SpatialMesh
    coords = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
    mesh = SpatialMesh(coordinates=coords, cells=np.array([[0, 1, 2], [0, 2, 3]]), cell_type=CellType.TRIANGLE, frame=CoordinateFrame("xy", 2, description="t"),
                       cell_tags=np.ones(2, dtype=int), groups=(PhysicalGroup("all", GroupKind.CELLS, 1),))
    data = write_vtu(mesh, point_data={"temperature": ("K", [300.0, 301.0, 302.0, 303.0]), "displacement": ("m", np.ones((4, 2)) * 1e-6)},
                     cell_data={"stress": ("Pa", [1.0, 2.0])}, metadata={"run": sha("r"), "provider": "fenicsx 0.11"})
    text = data.decode()
    assert mesh.digest in text and "temperature [K]" in text and "displacement [m]" in text and "not evidence" in text and "\r" not in text
    assert write_vtu(mesh, point_data={"temperature": ("K", [300.0, 301.0, 302.0, 303.0])}, metadata={"run": sha("r")}) == write_vtu(
        mesh, point_data={"temperature": ("K", [300.0, 301.0, 302.0, 303.0])}, metadata={"run": sha("r")})       # byte-stable
    with pytest.raises(InvalidScientificProblem, match="finite entries"):
        write_vtu(mesh, point_data={"t": ("K", [1.0, float("nan"), 2.0, 3.0])}, metadata={})
