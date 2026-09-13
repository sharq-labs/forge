"""Reproducible execution-manifest and artifact-attestation invariants."""

from __future__ import annotations

import pytest

from engcore.scientific.errors import ScientificCoreError
from engcore.scientific.ir.problem import ScientificProblem
from engcore.scientific.results.execution_manifest import (
    ArtifactDigest,
    ExecutionManifest,
    canonical_record_digest,
)
from engcore.scientific.solvers.protocol import (
    ConvergenceState,
    PreparedSolve,
    RawSolverOutput,
    SolverIdentity,
    SolverSettings,
)


def _prepared(*, option: int = 4, note: str = "assembled") -> PreparedSolve:
    return PreparedSolve(
        problem=ScientificProblem(problem_id="case-1", metadata={"campaign": "A"}),
        solver=SolverIdentity("closed_form", "1.2.3", backend="python"),
        settings=SolverSettings(
            tolerances={"rtol": 1e-9}, options={"quadrature_order": option}
        ),
        payload=object(),  # deliberately opaque; only explicit bytes can attest it
        notes=(note,),
    )


def _raw(*, value: float = 12.5, artifact: bool = True) -> RawSolverOutput:
    return RawSolverOutput(
        convergence=ConvergenceState.NOT_APPLICABLE,
        values={"answer": value},
        residuals={"balance": 0.0},
        artifacts=("report.json",) if artifact else (),
        diagnostics={"route": "analytic"},
    )


def test_manifest_is_deterministic_across_environment_mapping_order():
    first = ExecutionManifest.from_execution(
        _prepared(),
        _raw(),
        artifact_bytes={"report.json": b'{"ok":true}'},
        environment={"python": "3.12", "solver_image": "sha256:abc"},
    )
    second = ExecutionManifest.from_execution(
        _prepared(),
        _raw(),
        artifact_bytes={"report.json": b'{"ok":true}'},
        environment={"solver_image": "sha256:abc", "python": "3.12"},
    )
    assert first == second
    assert first.manifest_digest == second.manifest_digest


def test_artifact_bytes_are_bound_and_a_changed_byte_changes_the_manifest():
    original = ExecutionManifest.from_execution(
        _prepared(), _raw(), artifact_bytes={"report.json": b"abc"}
    )
    changed = ExecutionManifest.from_execution(
        _prepared(), _raw(), artifact_bytes={"report.json": b"abd"}
    )
    assert original.artifacts[0].digest != changed.artifacts[0].digest
    assert original.manifest_digest != changed.manifest_digest


def test_declared_artifacts_must_be_covered_exactly_fail_closed():
    with pytest.raises(ScientificCoreError, match="missing=.*report.json"):
        ExecutionManifest.from_execution(_prepared(), _raw(), artifact_bytes={})

    with pytest.raises(ScientificCoreError, match="extra=.*ghost.bin"):
        ExecutionManifest.from_execution(
            _prepared(),
            _raw(),
            artifact_bytes={"report.json": b"ok", "ghost.bin": b"not-declared"},
        )


def test_problem_settings_and_raw_output_are_each_independently_bound():
    base = ExecutionManifest.from_execution(
        _prepared(option=4), _raw(value=12.5), artifact_bytes={"report.json": b"x"}
    )
    changed_settings = ExecutionManifest.from_execution(
        _prepared(option=8), _raw(value=12.5), artifact_bytes={"report.json": b"x"}
    )
    changed_output = ExecutionManifest.from_execution(
        _prepared(option=4), _raw(value=12.6), artifact_bytes={"report.json": b"x"}
    )
    changed_problem = PreparedSolve(
        problem=ScientificProblem(problem_id="case-1", metadata={"campaign": "B"}),
        solver=_prepared().solver,
        settings=_prepared().settings,
    )
    changed_problem_manifest = ExecutionManifest.from_execution(
        changed_problem, _raw(value=12.5), artifact_bytes={"report.json": b"x"}
    )

    assert base.settings_digest != changed_settings.settings_digest
    assert base.raw_output_digest != changed_output.raw_output_digest
    assert base.problem_digest != changed_problem_manifest.problem_digest


def test_opaque_prepared_payload_is_not_claimed_unless_bytes_are_supplied():
    unbound = ExecutionManifest.from_execution(
        _prepared(), _raw(), artifact_bytes={"report.json": b"x"}
    )
    bound = ExecutionManifest.from_execution(
        _prepared(),
        _raw(),
        artifact_bytes={"report.json": b"x"},
        prepared_payload_bytes=b"canonical assembled matrix bytes",
    )
    assert unbound.coverage == "control_plane"
    assert unbound.prepared_payload is None
    assert bound.coverage == "control_plane+prepared_payload"
    assert bound.prepared_payload is not None
    assert bound.prepared_payload.role == "prepared_payload"
    assert unbound.manifest_digest != bound.manifest_digest


def test_serialized_manifest_verifies_its_own_content_digest():
    manifest = ExecutionManifest.from_execution(
        _prepared(),
        _raw(),
        artifact_bytes={"report.json": b"x"},
        environment={"python": "3.12"},
        realization_id="realization-7",
    )
    payload = manifest.to_dict()
    assert ExecutionManifest.from_dict(payload) == manifest

    tampered = dict(payload)
    tampered["problem_digest"] = "0" * 64
    with pytest.raises(ScientificCoreError, match="digest mismatch"):
        ExecutionManifest.from_dict(tampered)


def test_verify_execution_rejects_any_bound_fact_that_changed():
    prepared, raw = _prepared(), _raw()
    manifest = ExecutionManifest.from_execution(
        prepared,
        raw,
        artifact_bytes={"report.json": b"x"},
        environment={"python": "3.12"},
    )
    manifest.verify_execution(
        prepared,
        raw,
        artifact_bytes={"report.json": b"x"},
        environment={"python": "3.12"},
    )
    with pytest.raises(ScientificCoreError, match="does not match"):
        manifest.verify_execution(
            prepared,
            raw,
            artifact_bytes={"report.json": b"y"},
            environment={"python": "3.12"},
        )


def test_failed_solver_nonfinite_values_still_have_a_deterministic_record_digest():
    raw = RawSolverOutput(
        convergence=ConvergenceState.DIVERGED,
        values={"answer": float("nan")},
        residuals={"residual": float("inf")},
    )
    digest_a = canonical_record_digest(raw.to_dict())
    digest_b = canonical_record_digest(raw.to_dict())
    assert len(digest_a) == 64
    assert digest_a == digest_b


def test_artifact_digest_refuses_text_coercion():
    with pytest.raises(ScientificCoreError, match="must be bytes"):
        ArtifactDigest.from_bytes("report", "abc")  # type: ignore[arg-type]
