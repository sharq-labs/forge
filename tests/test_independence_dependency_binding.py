"""Dependency evidence integrity: what counts as evidence for ONE declared dependency.

Round 1A of solver independence. The scientific contract these tests hold:

    A dependency identity counts as evidenced only after an artifact explicitly
    bound to that canonical dependency identity has been successfully re-hashed
    from supplied bytes, and one verified artifact byte identity cannot be
    presented as evidence for multiple distinct dependency identities within the
    same route.

Every case asserts the scientific property -- is the dependency covered, is the
route refused, is the level kept -- rather than how the code arrives at it.
The route-local rule (one artifact, one dependency) and the cross-route rule
(no shared verified artifact) are tested separately, because they are different
rules and each must hold when the other is not in play.

What these tests do not test, because Round 1A does not claim it: that a
solver actually loaded or executed the artifacts. The bytes here are presented
by the caller, exactly as they are in production.
"""

from __future__ import annotations

import json
import pathlib
import sys
import uuid

import pytest

from engcore.domains.electrical.dc_consensus import DC_CONSENSUS_THRESHOLDS
from engcore.execution.consensus import TrustedConsensusGate
from engcore.scientific.consensus import (
    CrossSolverConsensus,
    IndependenceDimension as D,
    RouteDependencies,
    SOLVER_INDEPENDENCE_DIMENSIONS,
    canonical_component_identity,
)
from engcore.scientific.errors import ScientificValidationError
from engcore.scientific.independence_evidence import (
    ArtifactFingerprint,
    RouteIndependenceEvidence,
    assess_independence_evidence,
)
from engcore.scientific.results.validation import ValidationLevel
from tests.route_declarations_for_tests import (  # noqa: F401 - autouse fixture
    bound_over,  # IND-02: a level needs results, not a mapping of numbers
    route,
    route_declarations_for_tests,
)

REPO = pathlib.Path(__file__).resolve().parents[1]
REFUSAL = "cannot establish more than one declared dependency"


def _evidence(route_record, overrides=None):
    """Distinct genuine artifacts per canonical identity, with dimensions replaceable.

    ``overrides[dimension]`` is a list of ``(name, payload, identity)`` or
    ``(name, payload, identity, kind)`` rows that replaces that dimension.
    """
    overrides = overrides or {}
    canonical = route_record.dependencies.canonical()
    artifacts, blobs = {}, {}
    for dimension in SOLVER_INDEPENDENCE_DIMENSIONS:
        rows = overrides.get(dimension)
        if rows is None:
            rows = [
                (f"{route_record.route_id}-{dimension.value}-{index}",
                 f"{route_record.route_id}:{dimension.value}:{identity}".encode(), identity)
                for index, identity in enumerate(sorted(canonical[dimension]))
            ]
        artifacts[dimension] = frozenset(
            ArtifactFingerprint.from_bytes(
                row[0], row[1], kind=row[3] if len(row) > 3 else "test-artifact",
                dependency_identity=row[2],
            )
            for row in rows
        )
        blobs[dimension] = {row[0]: row[1] for row in rows}
    return (
        RouteIndependenceEvidence(route_record.route_id, route_record.dependencies.digest, artifacts),
        blobs,
    )


def _identity(route_record, dimension):
    (identity,) = route_record.dependencies.canonical()[dimension]
    return identity


def _two_backend_route(route_id="a"):
    return route(route_id, backend={f"ext:test:{route_id}:backend", f"ext:test:{route_id}:runtime"})


def _pair(left_evidence, right_evidence, routes):
    (ev_a, bytes_a), (ev_b, bytes_b) = left_evidence, right_evidence
    return assess_independence_evidence(
        routes, (ev_a, ev_b), artifact_bytes={routes[0].route_id: bytes_a, routes[1].route_id: bytes_b}
    )


def _consensus(*routes):
    return bound_over(
        consensus_id="dependency-binding",
        routes=routes,
        values={item.route_id: {"x": 1.0, "y": 2.0} for item in routes},
        thresholds=DC_CONSENSUS_THRESHOLDS,
        tolerance_key="agreement_rel_tol",
        required_outputs=("x", "y"),
    )


# =============================================================================
# route-local integrity: one verified artifact, one dependency
# =============================================================================
def test_A_one_blob_under_one_name_cannot_evidence_two_identities_in_one_dimension():
    a, b = _two_backend_route(), route("b")
    blob = b"the only backend artifact route a presents"
    evidence = _evidence(a, {D.BACKEND: [
        ("backend.so", blob, "ext:test:a:backend"),
        ("backend.so", blob, "ext:test:a:runtime"),
    ]})
    assessment = evidence[0].assess(a, evidence[1])
    digest = next(iter(evidence[0].artifacts[D.BACKEND])).digest

    assert not assessment.verified
    refusal = [r for r in assessment.reasons if REFUSAL in r]
    assert len(refusal) == 1, assessment.reasons
    assert digest[:12] in refusal[0]
    assert "ext:test:a:backend" in refusal[0] and "ext:test:a:runtime" in refusal[0]
    assert assessment.artifact_identities[digest] == {"ext:test:a:backend", "ext:test:a:runtime"}
    assert not _pair(evidence, _evidence(b), (a, b)).strongly_independent


def test_B_one_blob_under_two_names_cannot_evidence_two_identities():
    a, b = _two_backend_route(), route("b")
    blob = b"single artifact, two names"
    evidence = _evidence(a, {D.BACKEND: [
        ("first.so", blob, "ext:test:a:backend", "binary"),
        ("second.dll", blob, "ext:test:a:runtime", "library"),
    ]})
    assessment = evidence[0].assess(a, evidence[1])
    assert any(REFUSAL in r and "ext:test:a:runtime" in r for r in assessment.reasons), assessment.reasons
    report = _pair(evidence, _evidence(b), (a, b))
    assert not report.all_routes_verified and not report.strongly_independent


def test_C_one_blob_cannot_evidence_identities_in_two_dimensions_of_one_route():
    a, b = route("a"), route("b")
    blob = b"one monolithic binary"
    implementation, backend = _identity(a, D.IMPLEMENTATION), _identity(a, D.BACKEND)
    evidence = _evidence(a, {
        D.IMPLEMENTATION: [("impl.bin", blob, implementation, "source")],
        D.BACKEND: [("runtime.bin", blob, backend, "binary")],
    })
    assessment = evidence[0].assess(a, evidence[1])
    refusal = [r for r in assessment.reasons if REFUSAL in r]
    assert len(refusal) == 1, assessment.reasons
    assert implementation in refusal[0] and backend in refusal[0]
    assert "implementation:impl.bin" in refusal[0] and "backend:runtime.bin" in refusal[0]
    assert not _pair(evidence, _evidence(b), (a, b)).strongly_independent


def test_one_identity_may_be_evidenced_by_several_distinct_artifacts():
    """The rule is one artifact per dependency, not one dependency per artifact count."""
    a, b = route("a"), route("b")
    backend = _identity(a, D.BACKEND)
    evidence = _evidence(a, {D.BACKEND: [
        ("lib.so", b"shared object", backend, "binary"),
        ("lib.py", b"python binding", backend, "source"),
    ]})
    assessment = evidence[0].assess(a, evidence[1])
    assert assessment.verified, assessment.reasons
    assert _pair(evidence, _evidence(b), (a, b)).strongly_independent


# =============================================================================
# coverage is counted only after the bytes verify
# =============================================================================
@pytest.mark.parametrize("tamper", ["D-absent", "E-wrong-bytes", "F-forged-digest", "not-bytes", "no-dimension-bytes"])
def test_DEF_a_bound_artifact_whose_bytes_do_not_verify_covers_nothing(tamper):
    a = _two_backend_route()
    evidence, blobs = _evidence(a)
    target = next(f for f in evidence.artifacts[D.BACKEND] if f.dependency_identity == "ext:test:a:runtime")
    artifacts = dict(evidence.artifacts)
    blobs = {dimension: dict(items) for dimension, items in blobs.items()}
    if tamper == "D-absent":
        del blobs[D.BACKEND][target.name]
    elif tamper == "E-wrong-bytes":
        blobs[D.BACKEND][target.name] = b"not the declared artifact"
    elif tamper == "F-forged-digest":
        forged = ArtifactFingerprint("f" * 64, target.name, kind=target.kind,
                                     dependency_identity=target.dependency_identity)
        artifacts[D.BACKEND] = frozenset((set(artifacts[D.BACKEND]) - {target}) | {forged})
    elif tamper == "not-bytes":
        blobs[D.BACKEND][target.name] = bytearray(blobs[D.BACKEND][target.name])
    else:
        del blobs[D.BACKEND]
    assessment = RouteIndependenceEvidence(a.route_id, a.dependencies.digest, artifacts).assess(a, blobs)

    assert "ext:test:a:runtime" not in assessment.covered[D.BACKEND]
    assert not assessment.verified
    assert any(
        "ext:test:a:runtime" in r and "was verified against supplied bytes" in r
        for r in assessment.reasons
    ), assessment.reasons
    if tamper != "no-dimension-bytes":
        assert assessment.covered[D.BACKEND] == {"ext:test:a:backend"}


def test_G_one_verified_artifact_covers_exactly_the_identity_it_binds():
    a = _two_backend_route()
    evidence, blobs = _evidence(a, {D.BACKEND: [("backend.so", b"backend only", "ext:test:a:backend")]})
    assessment = evidence.assess(a, blobs)
    assert assessment.covered[D.BACKEND] == {"ext:test:a:backend"}
    assert not assessment.verified
    missing = [r for r in assessment.reasons if "was verified against supplied bytes" in r]
    assert len(missing) == 1 and "ext:test:a:runtime" in missing[0]


def test_H_distinct_verified_artifacts_for_distinct_identities_succeed():
    a, b = _two_backend_route("a"), _two_backend_route("b")
    left, right = _evidence(a), _evidence(b)
    assessment = left[0].assess(a, left[1])
    assert assessment.verified, assessment.reasons
    assert dict(assessment.covered) == {
        dimension: a.dependencies.canonical()[dimension] for dimension in SOLVER_INDEPENDENCE_DIMENSIONS
    }
    report = _pair(left, right, (a, b))
    assert report.all_routes_verified and report.artifact_disjoint and report.strongly_independent


# =============================================================================
# cross-route disjointness: a different rule, still enforced
# =============================================================================
def test_I_identical_verified_bytes_across_routes_are_shared_machinery():
    a, b = route("a"), route("b")
    shared = b"identical backend bytes"
    left = _evidence(a, {D.BACKEND: [("backend", shared, _identity(a, D.BACKEND))]})
    right = _evidence(b, {D.BACKEND: [("backend", shared, _identity(b, D.BACKEND))]})
    report = _pair(left, right, (a, b))
    assert report.all_routes_verified, "each route on its own is complete and verified"
    assert not report.artifact_disjoint and not report.strongly_independent
    assert report.shared_artifacts[0].routes == ("a", "b")


@pytest.mark.parametrize("left_dimension, right_dimension", [
    (D.IMPLEMENTATION, D.BACKEND),
    (D.BACKEND, D.NUMERICAL_METHOD),
    (D.PREPROCESSING, D.IMPLEMENTATION),
])
def test_J_shared_bytes_are_found_whatever_name_kind_dimension_or_identity(left_dimension, right_dimension):
    a, b = route("a"), route("b")
    shared = b"identical machinery, relabelled"
    left = _evidence(a, {left_dimension: [("wrapper-a.py", shared, _identity(a, left_dimension), "source")]})
    right = _evidence(b, {right_dimension: [("vendor-b.so", shared, _identity(b, right_dimension), "binary")]})
    report = _pair(left, right, (a, b))
    assert report.all_routes_verified and not report.strongly_independent
    assert len(report.shared_artifacts) == 1
    assert set(report.shared_artifacts[0].names) == {"wrapper-a.py", "vendor-b.so"}


# =============================================================================
# bindings that are not evidence
# =============================================================================
def test_K_legacy_unbound_fingerprints_stay_readable_and_establish_nothing():
    a, b = route("a"), route("b")
    evidence, blobs = _evidence(a)
    payload = json.loads(json.dumps(evidence.to_dict()))
    backend_rows = payload["artifacts"][D.BACKEND.value]
    del backend_rows[0]["dependency_identity"]  # written before bindings existed
    payload["artifacts"][D.IMPLEMENTATION.value][0]["dependency_identity"] = None

    restored = RouteIndependenceEvidence.from_dict(payload)
    assert {f.dependency_identity for f in restored.artifacts[D.BACKEND]} == {""}
    assert {f.dependency_identity for f in restored.artifacts[D.IMPLEMENTATION]} == {""}
    assert "dependency_identity" not in restored.to_dict()["artifacts"][D.BACKEND.value][0]
    assert RouteIndependenceEvidence.from_dict(restored.to_dict()) == restored

    assessment = restored.assess(a, blobs)
    assert assessment.covered[D.BACKEND] == frozenset()
    assert any("is not bound to a dependency identity" in r for r in assessment.reasons)
    assert not _pair((restored, blobs), _evidence(b), (a, b)).strongly_independent


@pytest.mark.parametrize("form", ["replaces-the-declared-binding", "beside-complete-coverage"])
def test_L_an_artifact_bound_to_an_undeclared_identity_is_refused(form):
    a, b = route("a"), route("b")
    backend = _identity(a, D.BACKEND)
    rows = [("undeclared.so", b"bytes for something not declared", "ext:not-declared:anywhere")]
    if form == "beside-complete-coverage":
        rows.append(("backend.so", b"the declared backend", backend))
    evidence = _evidence(a, {D.BACKEND: rows})
    assessment = evidence[0].assess(a, evidence[1])
    assert "ext:not-declared:anywhere" not in assessment.covered[D.BACKEND]
    assert any("binds undeclared dependency identity" in r for r in assessment.reasons)
    report = _pair(evidence, _evidence(b), (a, b))
    assert not report.all_routes_verified and not report.strongly_independent


def test_M_an_identity_declared_in_another_dimension_is_refused():
    a, b = route("a"), route("b")
    method = _identity(a, D.NUMERICAL_METHOD)
    evidence = _evidence(a, {D.BACKEND: [("method-as-backend", b"x", method)]})
    assessment = evidence[0].assess(a, evidence[1])
    assert assessment.covered[D.BACKEND] == frozenset()
    assert assessment.covered[D.NUMERICAL_METHOD] == {method}
    assert any("backend artifact 'method-as-backend' binds undeclared" in r for r in assessment.reasons)
    assert not _pair(evidence, _evidence(b), (a, b)).strongly_independent


@pytest.mark.parametrize("value", [False, True, 0, 1, 1.5, [], ["ext:a"], {}, b"ext:a", bytearray(b"ext:a")])
def test_N_non_string_bindings_are_refused_not_read_as_unbound(value):
    with pytest.raises(ScientificValidationError, match="dependency_identity must be a string"):
        ArtifactFingerprint("0" * 64, "artifact", dependency_identity=value)
    payload = ArtifactFingerprint.from_bytes("artifact", b"x").to_dict()
    payload["dependency_identity"] = value
    with pytest.raises(ScientificValidationError, match="dependency_identity must be a string"):
        ArtifactFingerprint.from_dict(payload)


@pytest.mark.parametrize("value, stored", [(None, ""), ("", ""), ("   ", ""), ("  ext:a  ", "ext:a")])
def test_N_none_and_strings_are_the_accepted_binding_forms(value, stored):
    assert ArtifactFingerprint("0" * 64, "artifact", dependency_identity=value).dependency_identity == stored


# =============================================================================
# the audit record carries the binding
# =============================================================================
def test_O_trusted_evidence_lines_record_the_exact_canonical_identity_of_every_artifact():
    a, b = _two_backend_route("a"), route("b")
    left, right = _evidence(a), _evidence(b)
    decision = TrustedConsensusGate().assess(
        _consensus(a, b), (left[0], right[0]), artifact_bytes={"a": left[1], "b": right[1]}
    )
    assert decision.validated
    for route_record, (evidence, _) in ((a, left), (b, right)):
        for dimension in SOLVER_INDEPENDENCE_DIMENSIONS:
            for artifact in evidence.artifacts[dimension]:
                expected = (
                    f"route {route_record.route_id} {dimension.value} artifact "
                    f"{artifact.kind}:{artifact.name} sha256:{artifact.digest} "
                    f"evidences {artifact.canonical_dependency_identity()}"
                )
                assert expected in decision.check.evidence, expected


def test_O_unbound_unresolvable_and_unassessed_artifacts_say_so_in_the_record():
    a, b = route("a"), route("b")
    evidence, blobs = _evidence(a)
    artifacts = dict(evidence.artifacts)
    artifacts[D.IMPLEMENTATION] = frozenset({ArtifactFingerprint.from_bytes("legacy", b"legacy")})
    artifacts[D.PREPROCESSING] = frozenset({ArtifactFingerprint.from_bytes(
        "gone", b"gone", dependency_identity="py:forge_module_that_is_not_installed:Thing")})
    artifacts[D.PROBLEM_DECLARATION] = frozenset({ArtifactFingerprint.from_bytes(
        "problem", b"problem", dependency_identity="ext:test:one-problem")})
    record = RouteIndependenceEvidence(a.route_id, a.dependencies.digest, artifacts)
    decision = TrustedConsensusGate().assess(
        _consensus(a, b), (record, _evidence(b)[0]), artifact_bytes={"a": blobs, "b": _evidence(b)[1]}
    )
    lines = "\n".join(decision.check.evidence)
    assert not decision.validated
    assert "implementation artifact artifact:legacy" in lines and "evidences no dependency identity (unbound" in lines
    assert "binds unresolvable dependency identity 'py:forge_module_that_is_not_installed:Thing'" in lines
    assert "(not assessed: problem_declaration is not a solver-independence dimension)" in lines


# =============================================================================
# reading a record is not executing it
# =============================================================================
def test_reading_evidence_imports_nothing_the_record_names(tmp_path, monkeypatch):
    module_name = f"forge_binding_probe_{uuid.uuid4().hex}"
    marker = tmp_path / "imported.txt"
    (tmp_path / f"{module_name}.py").write_bytes(
        f"import pathlib\npathlib.Path({str(marker)!r}).write_bytes(b'imported')\n\nclass Thing:\n    pass\n".encode()
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    identity = f"py:{module_name}:Thing"
    record = RouteIndependenceEvidence(
        "a", "0" * 64,
        {D.BACKEND: frozenset({ArtifactFingerprint.from_bytes("thing", b"thing", dependency_identity=identity)})},
    )

    restored = RouteIndependenceEvidence.from_dict(json.loads(json.dumps(record.to_dict())))
    (fingerprint,) = restored.artifacts[D.BACKEND]
    assert fingerprint.dependency_identity == identity
    assert module_name not in sys.modules and not marker.exists(), "reading the record imported it"

    try:
        assert fingerprint.canonical_dependency_identity() == identity  # the trust boundary resolves it
        assert marker.exists()
    finally:
        sys.modules.pop(module_name, None)


def test_evidence_naming_an_unavailable_dependency_stays_readable_and_is_refused_when_assessed():
    a = route("a")
    evidence, blobs = _evidence(a)
    artifacts = dict(evidence.artifacts)
    artifacts[D.BACKEND] = frozenset({ArtifactFingerprint.from_bytes(
        "solver.so", b"solver", dependency_identity="py:forge_dependency_absent_here:Solver")})
    blobs = {**blobs, D.BACKEND: {"solver.so": b"solver"}}
    payload = RouteIndependenceEvidence(a.route_id, a.dependencies.digest, artifacts).to_dict()

    restored = RouteIndependenceEvidence.from_dict(payload)
    assessment = restored.assess(a, blobs)
    assert assessment.covered[D.BACKEND] == frozenset()
    assert any("cannot be canonicalised" in r for r in assessment.reasons)


# =============================================================================
# canonical identity: real Python aliases, and the limit of the canonical form
# =============================================================================
REEXPORT = "py:engcore.domains.electrical.dc:ElectricalDCSolver"
DEFINING = "py:engcore.domains.electrical.dc.solver:ElectricalDCSolver"


@pytest.mark.parametrize("declared, bound", [(REEXPORT, DEFINING), (DEFINING, REEXPORT)])
def test_a_re_export_and_its_defining_module_evidence_the_same_dependency(declared, bound):
    assert REEXPORT != DEFINING and canonical_component_identity(REEXPORT) == DEFINING
    a, b = route("a", implementation=declared), route("b")
    evidence = _evidence(a, {D.IMPLEMENTATION: [("dc-solver.py", b"solver source", bound, "source")]})
    assessment = evidence[0].assess(a, evidence[1])
    assert assessment.verified, assessment.reasons
    assert assessment.covered[D.IMPLEMENTATION] == {DEFINING}
    assert _pair(evidence, _evidence(b), (a, b)).strongly_independent


def test_two_spellings_of_one_python_dependency_are_one_identity_never_two():
    """A raw spelling cannot open a second dependency slot for relabelled evidence."""
    both = RouteDependencies({
        **{d: {f"ext:test:x:{d.value}"} for d in D},
        D.IMPLEMENTATION: {REEXPORT, DEFINING},
    })
    one = RouteDependencies({**{d: {f"ext:test:x:{d.value}"} for d in D}, D.IMPLEMENTATION: {DEFINING}})
    assert both.canonical()[D.IMPLEMENTATION] == {DEFINING}
    assert both.digest == one.digest

    a = route("a", implementation=[REEXPORT, DEFINING])
    blob = b"solver source"
    evidence = _evidence(a, {D.IMPLEMENTATION: [
        ("via-package.py", blob, REEXPORT, "source"),
        ("via-module.py", blob, DEFINING, "source"),
    ]})
    assessment = evidence[0].assess(a, evidence[1])
    assert assessment.covered[D.IMPLEMENTATION] == {DEFINING}
    assert assessment.artifact_identities[next(iter(evidence[0].artifacts[D.IMPLEMENTATION])).digest] == {DEFINING}


def test_alias_spellings_across_routes_do_not_make_one_implementation_two():
    a = route("a", implementation=REEXPORT)
    b = route("b", implementation=DEFINING)
    assert _consensus(a, b).establishes is not ValidationLevel.CROSS_SOLVER_VALIDATED

    shared = b"one solver source"
    left = _evidence(a, {D.IMPLEMENTATION: [("solver.py", shared, REEXPORT, "source")]})
    right = _evidence(b, {D.IMPLEMENTATION: [("solver_impl.py", shared, DEFINING, "source")]})
    report = _pair(left, right, (a, b))
    assert not report.strongly_independent and report.shared_artifacts


def test_distinct_lambdas_and_closures_collapse_to_one_identity__documented_limitation(tmp_path, monkeypatch):
    """KNOWN LIMITATION of ``canonical_component_identity``, pinned so a fix is deliberate.

    The canonical form is the resolved object's ``__module__`` and
    ``__qualname__``. Two distinct lambdas share ``<lambda>``, and two closures
    made by one factory share ``factory.<locals>.inner``, so a declaration naming
    both counts one dependency and needs one artifact. No production declaration
    uses such an object (the next test enforces that). Distinguishing them needs
    an identity contract that is not a qualified name -- a separate change.
    """
    module_name = f"forge_lambda_probe_{uuid.uuid4().hex}"
    (tmp_path / f"{module_name}.py").write_bytes(
        b"first = lambda x: x + 1\nsecond = lambda x: x * 2\n\n"
        b"def factory(scale):\n    def inner(x):\n        return scale * x\n    return inner\n\n"
        b"residual = factory(1.0)\njacobian = factory(2.0)\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        assert canonical_component_identity(f"py:{module_name}:first") == \
            canonical_component_identity(f"py:{module_name}:second") == f"py:{module_name}:<lambda>"
        assert canonical_component_identity(f"py:{module_name}:residual") == \
            canonical_component_identity(f"py:{module_name}:jacobian")
    finally:
        sys.modules.pop(module_name, None)


def test_no_production_route_declaration_depends_on_an_identity_the_canonical_form_conflates():
    from engcore.domains.electrical.dc_consensus import (
        EXTERNAL_ROUTE_DEPENDENCIES,
        NATIVE_ROUTE_DEPENDENCIES,
    )
    from engcore.domains.kinetics.cstr.validation import INTEGRATION_ROUTE_DEPENDENCIES

    declaring_files = sorted(
        path.relative_to(REPO).as_posix()
        for path in (REPO / "src" / "engcore" / "domains").rglob("*.py")
        if "RouteDependencies(" in path.read_text(encoding="utf-8-sig")
    )
    assert declaring_files == [
        "src/engcore/domains/electrical/dc_consensus.py",
        "src/engcore/domains/kinetics/cstr/validation.py",
    ], "a new production declaration file must be added to this guard"

    declarations = [NATIVE_ROUTE_DEPENDENCIES, EXTERNAL_ROUTE_DEPENDENCIES, *INTEGRATION_ROUTE_DEPENDENCIES.values()]
    for declaration in declarations:
        canonical = declaration.canonical()
        for dimension, identities in declaration.identities.items():
            assert len(canonical[dimension]) == len(identities), (dimension, identities)
            for identity in canonical[dimension]:
                assert "<lambda>" not in identity and "<locals>" not in identity, identity
                assert canonical_component_identity(identity) == identity, identity


# =============================================================================
# record identity
# =============================================================================
def test_same_bytes_bound_to_two_dependencies_remain_two_evidence_records():
    """Two records, so an assessment can see and name the double use -- and refuse it."""
    payload = b"one binary presented for two declared dependencies"
    first = ArtifactFingerprint.from_bytes(
        "binary-as-implementation",
        payload,
        dependency_identity="ext:route:implementation",
    )
    second = ArtifactFingerprint.from_bytes(
        "binary-as-backend",
        payload,
        dependency_identity="ext:route:backend",
    )

    assert first.digest == second.digest
    assert first.dependency_identity != second.dependency_identity
    assert len(frozenset({first, second})) == 2


def test_existing_positional_fingerprint_constructor_keeps_its_name_slot():
    fingerprint = ArtifactFingerprint("0" * 64, "legacy-name", kind="source")

    assert fingerprint.name == "legacy-name"
    assert fingerprint.kind == "source"
    assert fingerprint.dependency_identity == ""
