"""BIG 13 engineering layer contracts: references, ladder, summary, bundle, VTU.  No provider is needed here.

The adversarial cases are the point: a reference that does not apply is never read as met, solver agreement
cannot reach a reference level, a post-hoc comparison cannot reach a reference level, an edited bundle is
refused even when its manifest is regenerated, a summary cannot omit model discrepancy, an evidence link
cannot name a record it does not carry, a comparison cannot be hand-built.
"""

from __future__ import annotations

import hashlib
import json
import os

import numpy as np
import pytest

from engcore.engineering import (
    BundleRefused, EnvelopeBound, EvidenceLink, LevelEntry, LevelStatus, PredeclaredCriterion, ReferenceCondition, ReferenceRecord,
    UncertaintyStatement, VerificationLadder, build_summary, compare_to_reference, verify_bundle, write_bundle, write_vtu,
)
from engcore.engineering.bundle import _json_bytes, _sha
from engcore.engineering.reference import _ISSUER, ReferenceComparison
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.oracles import OracleKind
from engcore.scientific.units.quantity import Quantity
from engcore.system_runtime import SystemExecutor, assess_constraints
from tests.system_runtime_fixtures import build, sha

RE100 = {"reynolds": Quantity(100, "dimensionless")}
DIMLESS = "dimensionless"


def _ref(kind=OracleKind.BENCHMARK_DATASET, *, envelope=(EnvelopeBound("reynolds", 99.0, 101.0, "dimensionless"),), data=None, comparable=("u",)):
    return ReferenceRecord(
        "ghia-like", "A centreline benchmark", "Someone", "J. Test 1, 1982", "https://example.org/paper.pdf", "table values quoted with attribution", kind,
        (ReferenceCondition("reynolds", 100.0, "dimensionless"),), (("u", "dimensionless"),), data if data is not None else (("u", (0.0, 0.1, 1.0)),),
        sha("source bytes"), "typed from the published table", envelope, comparable_quantities=comparable)


def _crit(tol=0.01, post_hoc=False):
    return PredeclaredCriterion("c", "u", "max_abs", Quantity(tol, DIMLESS), "test file", post_hoc=post_hoc)


def _cmp(kind=OracleKind.BENCHMARK_DATASET, value=0.004, **kw):
    """A real comparison, issued by compare_to_reference (the only way to obtain one)."""
    return compare_to_reference(_ref(kind), kw.pop("criterion", _crit()), kw.pop("conditions", RE100), value=Quantity(value, DIMLESS), compared_identity=sha("run"))


def _link(cls, outcome="met", kind="probe", **extra):
    return EvidenceLink.of_record(kind, {"probe": kind, "class": cls, **extra}, cls, outcome)


def _provider_link(cls="solver_corroboration_not_validation", within=True):
    return EvidenceLink.of_record("provider_comparison", {"classification": cls, "within_tolerance": within}, cls, "met" if within else "not_met")


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
    crit = _crit()
    good = _cmp(value=0.004)
    bad = _cmp(value=0.4)
    off = _cmp(value=0.0, conditions={"reynolds": Quantity(10, "dimensionless")})
    assert (good.outcome, bad.outcome, off.outcome) == ("met", "not_met", "not_applicable")
    assert off.value.magnitude == 0.0 and off.within_tolerance is None                 # a perfect number does not rescue an inapplicable reference; nothing was judged
    assert good.classification == "numerical_benchmark_comparison_not_validation_grant"
    post = _cmp(criterion=_crit(post_hoc=True))
    assert post.classification.startswith("post_hoc_")
    # a tolerance changed after the fact is a different criterion, so the original outcome stays attributable
    assert _crit(tol=1.0).digest != crit.digest


def test_the_ladder_cannot_claim_a_level_without_evidence_or_with_the_wrong_kind_of_evidence():
    with pytest.raises(InvalidScientificProblem, match="without evidence"):
        LevelEntry(3, LevelStatus.REACHED)
    corroboration = _provider_link()
    LevelEntry(5, LevelStatus.REACHED, (corroboration,))
    with pytest.raises(InvalidScientificProblem, match="numerical-benchmark comparison only"):
        LevelEntry(6, LevelStatus.REACHED, (corroboration,))                             # solver agreement is never a reference level
    benchmark_met = EvidenceLink.of_comparison(_cmp(OracleKind.BENCHMARK_DATASET, 0.004))
    benchmark_unmet = EvidenceLink.of_comparison(_cmp(OracleKind.BENCHMARK_DATASET, 0.4))
    with pytest.raises(InvalidScientificProblem, match="experimental-data comparison only"):
        LevelEntry(7, LevelStatus.REACHED, (benchmark_met,))                             # a numerical benchmark is never experimental validation
    with pytest.raises(InvalidScientificProblem, match="MET"):
        LevelEntry(6, LevelStatus.REACHED, (benchmark_unmet,))
    with pytest.raises(InvalidScientificProblem, match="post-hoc"):
        LevelEntry(5, LevelStatus.REACHED, (_provider_link("post_hoc_solver_corroboration_not_validation"),))
    assert LevelEntry(6, LevelStatus.REACHED, (benchmark_met,)).status is LevelStatus.REACHED
    assert LevelEntry(6, LevelStatus.ATTEMPTED_NOT_REACHED, (benchmark_unmet,)).evidence          # a failed attempt keeps its evidence
    assert LevelEntry(7, LevelStatus.REACHED, (EvidenceLink.of_comparison(_cmp(OracleKind.EXPERIMENTAL_DATASET, 0.004)),)).status is LevelStatus.REACHED


def test_ladder_reports_where_evidence_stops():
    l1 = LevelEntry(1, LevelStatus.REACHED, (_link("contract_integrity"),))
    l2 = LevelEntry(2, LevelStatus.REACHED, (_link("conservation_residual"),))
    l5 = LevelEntry(5, LevelStatus.REACHED, (_provider_link(),))
    ladder = VerificationLadder.of(a=l1, b=l2, c=l5)
    assert ladder.verification_reached == 2                                             # level 3 not reached, so 4 does not count
    assert ladder.corroboration_reached and ladder.reference_level_reached == "none"
    assert ladder.to_dict()["classification"] == "report_vocabulary_not_a_validation_grant"
    with pytest.raises(InvalidScientificProblem, match="every one of the seven levels"):
        VerificationLadder((l1,))
    with pytest.raises(InvalidScientificProblem, match="stated twice"):
        VerificationLadder.of(a=l1, b=LevelEntry(1, LevelStatus.ATTEMPTED_NOT_REACHED, (_link("contract_integrity", "not_met"),)))   # a later entry cannot silently replace an earlier one


def _run():
    request, context, knobs = build()
    result = SystemExecutor(context).run(request)
    return request, context, result


def _summary(request, context, result, ladder=None, **kw):
    ladder = ladder or VerificationLadder.of(a=LevelEntry(1, LevelStatus.REACHED, (_link("contract_integrity", kind="preflight_and_identity"),), "units and identities checked"))
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
    assert s.to_dict()["text_sha256"] == hashlib.sha256(text.encode()).hexdigest()       # the rendered text is bound to the record
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


def _run_with_artifact(payload=b"<fake/>"):
    from dataclasses import replace
    from engcore.system_runtime import ArtifactRef
    request, context, knobs = build()
    thermal = context.authorities._items["thermal-auth"]
    original = thermal._fn
    thermal._fn = lambda call: replace(original(call), artifacts=(ArtifactRef("field.vtu", "vtu", hashlib.sha256(payload).hexdigest(), "presentation"),))
    return request, context, SystemExecutor(context).run(request)


def test_a_bundle_verifies_and_any_edit_after_writing_is_refused(tmp_path):
    request, context, result = _run_with_artifact()
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
    _remanifest(d)
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


# ------------------------------------------------------------------------------------------------------------------------ review round
def test_every_reached_level_needs_met_evidence_of_its_own_class_and_no_post_hoc_reading():
    ok = {1: "contract_integrity", 2: "conservation_residual", 3: "analytic_limit_comparison_verifies_implementation_only", 4: "discretisation_convergence"}
    for level, cls in ok.items():
        LevelEntry(level, LevelStatus.REACHED, (_link(cls),))
        with pytest.raises(InvalidScientificProblem, match="MET"):
            LevelEntry(level, LevelStatus.REACHED, (_link(cls, "not_met"),))
        with pytest.raises(InvalidScientificProblem, match="MET"):
            LevelEntry(level, LevelStatus.REACHED, (_link(cls, "n/a"),))
        with pytest.raises(InvalidScientificProblem, match="post-hoc"):
            LevelEntry(level, LevelStatus.REACHED, (_link("post_hoc_" + cls),))
        with pytest.raises(InvalidScientificProblem, match="does not accept evidence"):
            LevelEntry(level, LevelStatus.REACHED, (_link("contract_integrity" if level != 1 else "conservation_residual"),))
    # a level that is NOT reached may carry any reading, post hoc included, beside its original outcome
    LevelEntry(4, LevelStatus.ATTEMPTED_NOT_REACHED, (_link("discretisation_convergence", "not_met"), _link("post_hoc_discretisation_convergence", "met", kind="post")))
    # a mixed REACHED level is refused: one unmet link is enough
    with pytest.raises(InvalidScientificProblem, match="MET"):
        LevelEntry(2, LevelStatus.REACHED, (_link("conservation_residual"), _link("conservation_residual", "not_met", kind="other")))


def test_level_one_is_not_reached_by_a_refused_preflight_or_run():
    from engcore.engineering import contract_integrity_entry
    request, context, result = _run()
    from engcore.system_runtime import compile_plan, preflight
    good = contract_integrity_entry(preflight(request, compile_plan(request), context), result)
    assert good.status is LevelStatus.REACHED and "deferred to the solved state" in good.note
    assert good.evidence[0].record["status"] in ("ready", "deferred_checks")               # the link carries the preflight report it names
    context.providers = None
    bad_request, bad_context, _ = build()
    from dataclasses import replace
    from engcore.system_runtime import ProviderBinding
    node = replace(next(n for n in bad_request.nodes if n.node_id == "thermal"), provider_binding_ids=("b",))
    bad_request = replace(bad_request, nodes=tuple(node if n.node_id == "thermal" else n for n in bad_request.nodes), provider_bindings=(ProviderBinding("b", "pybamm", "26.8"),))
    refused = SystemExecutor(bad_context).run(bad_request)
    entry = contract_integrity_entry(refused.preflight, refused)
    assert refused.status.value == "refused" and entry.status is LevelStatus.ATTEMPTED_NOT_REACHED and entry.evidence[0].outcome == "not_met"


def test_a_level_one_that_was_admitted_but_refused_on_the_solved_state_names_the_refused_nodes():
    from engcore.engineering import contract_integrity_entry
    from engcore.system_runtime import compile_plan, preflight
    from tests.system_runtime_fixtures import Knobs
    request, context, knobs = build(knobs=Knobs(omit_applicability=True))
    result = SystemExecutor(context).run(request)
    entry = contract_integrity_entry(preflight(request, compile_plan(request), context), result)
    assert result.receipt("thermal").status.value == "refused" and entry.status is LevelStatus.REACHED       # the REQUEST was admissible
    assert "REFUSED on the solved state" in entry.note and "thermal" in entry.note                            # and the note does not hide that the solved state was not


def test_a_comparison_value_is_a_non_negative_magnitude_and_a_reference_that_does_not_apply_judges_nothing():
    with pytest.raises(InvalidScientificProblem, match="non-negative"):
        _cmp(value=-0.5)
    off = _cmp(value=0.0, conditions={"reynolds": Quantity(10, "dimensionless")})
    assert off.to_dict()["within_tolerance"] is None and off.outcome == "not_applicable"
    with pytest.raises(InvalidScientificProblem, match="judges nothing"):
        ReferenceComparison(off.reference_digest, off.reference_kind, off.applicability, _crit(), sha("r"), Quantity(0.0, DIMLESS), False, "not_applicable", issued_by=_ISSUER)


def test_a_comparison_cannot_be_built_by_hand_and_its_outcome_cannot_disagree_with_its_value():
    good = _cmp()
    with pytest.raises(InvalidScientificProblem, match="issued by compare_to_reference"):
        ReferenceComparison(good.reference_digest, good.reference_kind, good.applicability, good.criterion, sha("r"), good.value, True, "met")       # fabricated: no issuer
    # a forged 'met' for a value beyond the tolerance is refused by the re-derivation, even with the issuer token
    with pytest.raises(InvalidScientificProblem, match="does not follow from the value"):
        ReferenceComparison(good.reference_digest, good.reference_kind, good.applicability, _crit(0.01), sha("r"), Quantity(0.4, DIMLESS), True, "met", issued_by=_ISSUER)
    with pytest.raises(InvalidScientificProblem, match="SHA-256"):
        ReferenceComparison("not-a-digest", good.reference_kind, good.applicability, _crit(), sha("r"), good.value, True, "met", issued_by=_ISSUER)


def test_a_tolerance_on_an_offset_unit_reads_a_difference_as_a_spread_not_an_absolute_temperature():
    """A 5 K difference against a 1 degC tolerance is NOT met (read as an absolute value it converts to -268 degC and would pass)."""
    ref = ReferenceRecord("t-limit", "a temperature limit", "textbook", "-", "", "derived", OracleKind.ANALYTIC_REFERENCE, (), (("dT", "K"),), (), "", "closed form",
                          comparable_quantities=("dT",))
    crit = PredeclaredCriterion("dt", "dT", "max_abs", Quantity(1.0, "degC"), "test")
    assert compare_to_reference(ref, crit, {}, value=Quantity(5.0, "K"), compared_identity=sha("r")).applicability.status == "unknown"   # no envelope: not compared at all
    with_env = ReferenceRecord("t-limit", "a temperature limit", "textbook", "-", "", "derived", OracleKind.ANALYTIC_REFERENCE, (ReferenceCondition("x", 1.0, "dimensionless"),),
                               (("dT", "K"),), (), "", "closed form", (EnvelopeBound("x", 0.0, 2.0, "dimensionless"),), comparable_quantities=("dT",))
    cond = {"x": Quantity(1.0, "dimensionless")}
    assert compare_to_reference(with_env, crit, cond, value=Quantity(5.0, "K"), compared_identity=sha("r")).outcome == "not_met"
    assert compare_to_reference(with_env, crit, cond, value=Quantity(0.5, "K"), compared_identity=sha("r")).outcome == "met"


def test_a_criterion_may_only_bind_to_a_quantity_the_reference_declares_comparable():
    with pytest.raises(InvalidScientificProblem, match="does not declare as comparable"):
        compare_to_reference(_ref(comparable=("something_else",)), _crit(), RE100, value=Quantity(0.0, DIMLESS), compared_identity=sha("r"))
    with pytest.raises(InvalidScientificProblem, match="does not declare as comparable"):
        compare_to_reference(_ref(comparable=()), _crit(), RE100, value=Quantity(0.0, DIMLESS), compared_identity=sha("r"))


def test_a_data_consistency_reference_is_classified_apart_from_an_implementation_limit():
    ref = _ref(OracleKind.ANALYTIC_REFERENCE, envelope=(EnvelopeBound("reynolds", 99.0, 101.0, "dimensionless"),), data=())
    from dataclasses import replace
    data_ref = replace(ref, role="data_consistency")
    a = compare_to_reference(ref, _crit(), RE100, value=Quantity(0.0, DIMLESS), compared_identity=sha("r"))
    b = compare_to_reference(data_ref, _crit(), RE100, value=Quantity(0.0, DIMLESS), compared_identity=sha("r"))
    assert a.classification == "analytic_limit_comparison_verifies_implementation_only"
    assert b.classification == "reference_data_consistency_check_not_validation"
    LevelEntry(3, LevelStatus.REACHED, (EvidenceLink.of_comparison(b),))


def test_the_summary_refuses_a_discrepancy_that_reads_as_zero_and_an_empty_unknown_list_when_outputs_are_unknown():
    request, context, result = _run()
    for bad in ("negligible", "0", "none", "small"):
        with pytest.raises(InvalidScientificProblem, match="UNKNOWN / NOT QUANTIFIED"):
            UncertaintyStatement(("x",), ("y",), bad, (), "a", "b")
    with pytest.raises(InvalidScientificProblem, match="UNKNOWN input uncertainty"):
        _summary(request, context, result, uncertainty=UncertaintyStatement((), (), "NOT QUANTIFIED", (), "a", "b"))


# ------------------------------------------------------------------------------------------ evidence links carry the record they name
def test_an_evidence_link_carries_its_record_and_its_digest_is_derived_from_it():
    a = _link("conservation_residual", n=1)
    assert a.digest == _link("conservation_residual", n=1).digest and a.digest != _link("conservation_residual", n=2).digest
    assert a.to_dict()["record"]["n"] == 1 and a.to_dict()["digest"] == a.digest
    assert EvidenceLink.from_dict(json.loads(json.dumps(a.to_dict()))).digest == a.digest          # survives a JSON round trip
    tampered = json.loads(json.dumps(a.to_dict()))
    tampered["record"]["n"] = 99
    with pytest.raises(InvalidScientificProblem, match="does not have the digest"):
        EvidenceLink.from_dict(tampered)                                                             # a link cannot claim a record it does not carry
    with pytest.raises(InvalidScientificProblem, match="non-empty record"):
        EvidenceLink.of_record("k", {}, "contract_integrity", "met")
    with pytest.raises(InvalidScientificProblem, match="finite JSON"):
        EvidenceLink.of_record("k", {"x": float("inf")}, "contract_integrity", "met")
    # a comparison link must repeat the classification and outcome of the comparison it carries: the outcome text cannot be flipped
    c = _cmp(value=0.4)
    with pytest.raises(InvalidScientificProblem, match="classification and outcome of the comparison"):
        EvidenceLink("reference_comparison", c.classification, "met", c.to_dict())


def test_a_ladder_read_back_from_a_summary_re_validates_every_guard():
    ladder = VerificationLadder.of(a=LevelEntry(1, LevelStatus.REACHED, (_link("contract_integrity"),)), b=LevelEntry(6, LevelStatus.REACHED, (EvidenceLink.of_comparison(_cmp()),)))
    wire = json.loads(json.dumps(ladder.to_dict()))
    assert VerificationLadder.from_dict(wire).reference_level_reached == "published_numerical_benchmark"
    flipped = json.loads(json.dumps(wire))
    flipped["levels"][5]["evidence"][0]["outcome"] = "not_met"                                       # edit only the outcome text
    with pytest.raises(InvalidScientificProblem):
        VerificationLadder.from_dict(flipped)
    lied = json.loads(json.dumps(wire))
    lied["reference_level_reached"] = "experimental_data"                                            # the derived field cannot claim more than the levels give
    with pytest.raises(InvalidScientificProblem, match="reference_level_reached"):
        VerificationLadder.from_dict(lied)


def test_a_summary_refuses_a_ladder_that_cites_a_comparison_it_does_not_contain_and_a_comparison_whose_reference_is_not_supplied():
    request, context, result = _run()
    cmp_ = _cmp()
    ladder = VerificationLadder.of(a=LevelEntry(6, LevelStatus.REACHED, (EvidenceLink.of_comparison(cmp_),)))
    with pytest.raises(InvalidScientificProblem, match="not among the summary's comparisons"):
        _summary(request, context, result, ladder=ladder, comparisons=(), references=(_ref(),))
    with pytest.raises(InvalidScientificProblem, match="not supplied with the summary"):
        _summary(request, context, result, ladder=ladder, comparisons=(cmp_,), references=())
    ok = _summary(request, context, result, ladder=ladder, comparisons=(cmp_,), references=(_ref(),))
    assert ok.scientific_status == "insufficient_evidence" and ok.ladder.reference_level_reached == "published_numerical_benchmark"    # the ladder never moves the credibility verdict


# --------------------------------------------------------------------------------------------------------------- bundle re-manifest attacks
def _remanifest(d, **changes):
    """What an editor who understands the manifest would do: re-hash every file, refresh the digests the manifest states, re-derive its own digest."""
    mpath = os.path.join(d, "manifest.json")
    m = json.loads(open(mpath, "rb").read())
    m["files"] = [[f, _sha(open(os.path.join(d, *f.split("/")), "rb").read())] for f, _ in m["files"]]
    from engcore.scenarios.timeline import canonical_digest
    m["summary_digest"] = canonical_digest(json.loads(open(os.path.join(d, "summary.json"), "rb").read()))
    m.update(changes)
    m.pop("bundle_digest")
    m["bundle_digest"] = _sha(_json_bytes(m))
    open(mpath, "wb").write(_json_bytes(m))


def _write(tmp_path, name, *, ladder=None, comparisons=(), references=(), **kw):
    request, context, result = _run_with_artifact()
    s = _summary(request, context, result, ladder=ladder, comparisons=comparisons, references=references)
    d = str(tmp_path / name)
    write_bundle(d, name="fixture", request=request, result=result, summary=s, references=[_ref()] if not references else references, artifacts={"field.vtu": b"<fake/>"}, **kw)
    return d, request, result, s


def test_a_regenerated_manifest_cannot_launder_an_edited_summary_reference_or_artifact_or_a_refused_nodes_file(tmp_path):
    from engcore.engineering.bundle import committed_artifacts
    request, context, result = _run_with_artifact()
    s = _summary(request, context, result)

    def fresh(name):
        d = str(tmp_path / name)
        write_bundle(d, name="fixture", request=request, result=result, summary=s, references=[_ref()], artifacts={"field.vtu": b"<fake/>"})
        return d

    d = fresh("summary")
    wire = json.loads(open(os.path.join(d, "summary.json"), "rb").read())
    wire["scientific_status"] = "supported"
    open(os.path.join(d, "summary.json"), "wb").write(_json_bytes(wire))
    with pytest.raises(BundleRefused, match="summary.json"):
        verify_bundle(d)                                                                             # the manifest was not touched
    d = fresh("reference")
    wire = json.loads(open(os.path.join(d, "references", "ghia-like.json"), "rb").read())
    wire["title"] = "a different benchmark"
    open(os.path.join(d, "references", "ghia-like.json"), "wb").write(_json_bytes(wire))
    _remanifest(d)
    with pytest.raises(BundleRefused, match="reference 'ghia-like'"):
        verify_bundle(d)
    d = fresh("artifact")
    open(os.path.join(d, "artifacts", "field.vtu"), "wb").write(b"<edited/>")
    _remanifest(d)
    with pytest.raises(BundleRefused, match="not an artifact referenced"):
        verify_bundle(d)
    # a file no SUCCEEDED node references cannot even be written
    with pytest.raises(BundleRefused, match="not referenced by any SUCCEEDED node"):
        write_bundle(str(tmp_path / "stray"), name="f", request=request, result=result, summary=s, artifacts={"stray.vtu": b"x"})
    assert set(committed_artifacts(result, {"field.vtu": b"<fake/>", "stray.vtu": b"x"})) == {"field.vtu"}
    d = fresh("nodigest")
    m = json.loads(open(os.path.join(d, "manifest.json"), "rb").read())
    m.pop("bundle_digest")
    open(os.path.join(d, "manifest.json"), "wb").write(_json_bytes(m))
    with pytest.raises(BundleRefused, match="digest of itself"):
        verify_bundle(d)


def test_a_fully_regenerated_manifest_still_cannot_launder_an_edited_status_request_plan_text_or_evidence(tmp_path):
    """Review finding H-B: the manifest is regenerated AND the digests it states are refreshed; the bundle must still be refused."""
    d, request, result, s = _write(tmp_path, "ok")
    verify_bundle(d)

    # 1. the scientific status edited, summary digest refreshed
    d, *_ = _write(tmp_path, "status")
    wire = json.loads(open(os.path.join(d, "summary.json"), "rb").read())
    wire["scientific_status"] = "supported"
    open(os.path.join(d, "summary.json"), "wb").write(_json_bytes(wire))
    _remanifest(d)
    with pytest.raises(BundleRefused, match="scientific status"):
        verify_bundle(d)                                                                             # re-derived by the existing credibility authority

    # 2. summary.txt edited (text no longer the text the summary states)
    d, *_ = _write(tmp_path, "text")
    open(os.path.join(d, "summary.txt"), "ab").write(b"  L7 reached: experimental validation\n")
    _remanifest(d)
    with pytest.raises(BundleRefused, match="summary.txt"):
        verify_bundle(d)

    # 3. request.json replaced by another VALID request, the manifest's request digest refreshed with it
    d, *_ = _write(tmp_path, "request")
    other = build(conductivity=99.0)[0]
    open(os.path.join(d, "request.json"), "wb").write(_json_bytes(other.to_dict()))
    _remanifest(d, request_digest=other.digest)
    with pytest.raises(BundleRefused, match="identities the manifest states|request.json"):
        verify_bundle(d)

    # 4. plan.json edited
    d, *_ = _write(tmp_path, "plan")
    plan = json.loads(open(os.path.join(d, "plan.json"), "rb").read())
    plan["tampered"] = True
    open(os.path.join(d, "plan.json"), "wb").write(_json_bytes(plan))
    _remanifest(d)
    with pytest.raises(BundleRefused, match="plan.json"):
        verify_bundle(d)

    # 5. an evidence record edited inside summary.json (the level still says REACHED): the link no longer has the digest of the record it carries
    ladder = VerificationLadder.of(a=LevelEntry(2, LevelStatus.REACHED, (_link("conservation_residual", n=1),), "balance closed"))
    d, *_ = _write(tmp_path, "evidence", ladder=ladder)
    wire = json.loads(open(os.path.join(d, "summary.json"), "rb").read())
    wire["verification"]["levels"][1]["evidence"][0]["record"]["n"] = 2
    open(os.path.join(d, "summary.json"), "wb").write(_json_bytes(wire))
    _remanifest(d)
    with pytest.raises(BundleRefused, match="ladder does not re-validate"):
        verify_bundle(d)

    # 6. a level promoted in summary.json (status flipped to REACHED with a not-met link): every guard runs again on read-back
    ladder = VerificationLadder.of(a=LevelEntry(6, LevelStatus.ATTEMPTED_NOT_REACHED, (EvidenceLink.of_comparison(_cmp(value=0.4)),), "criterion not met"))
    d, *_ = _write(tmp_path, "promoted", ladder=ladder, comparisons=(_cmp(value=0.4),), references=(_ref(),))
    verify_bundle(d)                                                                                 # the honest bundle verifies
    wire = json.loads(open(os.path.join(d, "summary.json"), "rb").read())
    level6 = wire["verification"]["levels"][5]
    level6["status"] = "reached"
    wire["verification"]["reference_level_reached"] = "published_numerical_benchmark"
    open(os.path.join(d, "summary.json"), "wb").write(_json_bytes(wire))
    _remanifest(d)
    with pytest.raises(BundleRefused, match="ladder does not re-validate"):
        verify_bundle(d)


def test_a_bundle_needs_the_reference_of_every_comparison_it_reports(tmp_path):
    request, context, result = _run_with_artifact()
    cmp_ = _cmp()
    s = _summary(request, context, result, ladder=VerificationLadder.of(a=LevelEntry(6, LevelStatus.REACHED, (EvidenceLink.of_comparison(cmp_),))), comparisons=(cmp_,), references=(_ref(),))
    with pytest.raises(BundleRefused, match="references that are not supplied"):
        write_bundle(str(tmp_path / "noref"), name="f", request=request, result=result, summary=s, references=[], artifacts={"field.vtu": b"<fake/>"})
    d = str(tmp_path / "ok")
    write_bundle(d, name="f", request=request, result=result, summary=s, references=[_ref()], artifacts={"field.vtu": b"<fake/>"})
    verify_bundle(d)
    os.remove(os.path.join(d, "references", "ghia-like.json"))                                       # a comparison whose reference file is gone cannot be checked
    with pytest.raises(BundleRefused):
        verify_bundle(d)
