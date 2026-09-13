"""Trusted execution orchestration above the frozen Scientific Core.

The scientific layer already defines the individual contracts: model/realization/
solver admission, the solver lifecycle, validation, and execution manifests.
This module makes their *order* one runtime invariant:

    admission -> prepare -> binding checks -> solve -> attestation
              -> metric extraction -> validation

A caller using :class:`TrustedExecutionRuntime` cannot obtain a
``TrustedExecutionRecord`` by calling only the pleasant parts of that chain.
Every returned record has passed claim/capability admission and carries a
content-addressed execution manifest.

This remains an architectural trust boundary, not remote attestation.  Artifact
bytes and environment facts are explicit inputs; no host state is scraped and
no digest is described as proof that a computation physically happened.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable, Iterable, Mapping

from ..scientific.capabilities import ScientificCapability
from ..scientific.errors import ScientificCoreError
from ..scientific.ir.problem import ScientificProblem
from ..scientific.models.definition import ScientificModelDefinition
from ..scientific.realizations.admission import (
    ExecutionAdmissionReport,
    require_execution_admission,
)
from ..scientific.realizations.definition import ModelRealizationDefinition
from ..scientific.results.execution_manifest import (
    ExecutionManifest,
    canonical_record_digest,
)
from ..scientific.results.validation import ValidationReport
from ..scientific.solvers.protocol import (
    PreparedSolve,
    RawSolverOutput,
    ScientificSolver,
)
from ..scientific.units.quantity import Quantity

ArtifactResolver = Callable[[PreparedSolve, RawSolverOutput], Mapping[str, bytes]]
PreparedPayloadEncoder = Callable[[PreparedSolve], bytes]


@dataclass(frozen=True)
class TrustedExecutionRecord:
    """One execution that passed the complete runtime trust path."""

    admission: ExecutionAdmissionReport
    prepared: PreparedSolve
    raw: RawSolverOutput
    metrics: Mapping[str, Quantity]
    validation: ValidationReport
    manifest: ExecutionManifest

    def __post_init__(self) -> None:
        if not self.admission.admitted:
            raise ScientificCoreError(
                "a TrustedExecutionRecord cannot contain a refused admission"
            )
        if not isinstance(self.prepared, PreparedSolve):
            raise ScientificCoreError("trusted execution prepared value must be PreparedSolve")
        if not isinstance(self.raw, RawSolverOutput):
            raise ScientificCoreError("trusted execution raw value must be RawSolverOutput")
        if not isinstance(self.validation, ValidationReport):
            raise ScientificCoreError(
                "trusted execution validation must be a ValidationReport"
            )
        if not isinstance(self.manifest, ExecutionManifest):
            raise ScientificCoreError(
                "trusted execution manifest must be an ExecutionManifest"
            )

        normalized: dict[str, Quantity] = {}
        for raw_name, value in self.metrics.items():
            name = str(raw_name).strip()
            if not name:
                raise ScientificCoreError("trusted execution metric names must be non-empty")
            if not isinstance(value, Quantity):
                raise ScientificCoreError(
                    f"trusted execution metric {name!r} is a {type(value).__name__}, "
                    "not a Quantity; raw numbers must not cross the metric boundary"
                )
            if name in normalized:
                raise ScientificCoreError(f"duplicate trusted execution metric {name!r}")
            normalized[name] = value
        object.__setattr__(
            self,
            "metrics",
            MappingProxyType(dict(sorted(normalized.items()))),
        )

    @property
    def trusted(self) -> bool:
        """True by construction; exposed to make the call-site intent explicit."""
        return True


class TrustedExecutionRuntime:
    """Run one selected model/realization/solver stack without bypasses.

    Version 1 is intentionally a *single selected model* runtime.  A problem may
    mention several models, but the caller must identify the one this solve is
    executing and the exact realization that implements it.  Multi-model
    orchestration belongs above this class; silently iterating a problem's model
    list here would invent scheduling semantics the core does not declare.
    """

    @staticmethod
    def _require_prepared_binding(
        prepared: PreparedSolve,
        *,
        problem: ScientificProblem,
        solver: ScientificSolver,
    ) -> None:
        if not isinstance(prepared, PreparedSolve):
            raise ScientificCoreError(
                f"solver.prepare returned {type(prepared).__name__}, not PreparedSolve"
            )
        if not isinstance(prepared.problem, ScientificProblem):
            raise ScientificCoreError(
                "prepared solve does not carry a ScientificProblem; execution binding is unverifiable"
            )
        expected_problem = canonical_record_digest(problem.to_dict())
        prepared_problem = canonical_record_digest(prepared.problem.to_dict())
        if prepared_problem != expected_problem:
            raise ScientificCoreError(
                "solver.prepare changed or replaced the admitted scientific problem; "
                "refusing to solve a payload whose problem binding differs from admission"
            )
        if prepared.solver != solver.identity:
            raise ScientificCoreError(
                "prepared solve solver identity does not match the admitted solver: "
                f"prepared={prepared.solver.key}, admitted={solver.identity.key}"
            )

    def run(
        self,
        *,
        problem: ScientificProblem,
        model: ScientificModelDefinition,
        realization: ModelRealizationDefinition,
        solver: ScientificSolver,
        available_scientific_capabilities: Iterable[ScientificCapability | str] = (),
        artifact_resolver: ArtifactResolver | None = None,
        prepared_payload_encoder: PreparedPayloadEncoder | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> TrustedExecutionRecord:
        # Admission is first on purpose.  Nothing solver-specific has been
        # prepared or executed before the cross-layer claim/capability contract
        # says this exact stack is coherent.
        admission = require_execution_admission(
            problem=problem,
            model=model,
            realization=realization,
            solver=solver,
            available_scientific_capabilities=available_scientific_capabilities,
        )

        prepared = solver.prepare(problem)
        self._require_prepared_binding(prepared, problem=problem, solver=solver)

        raw = solver.solve(prepared)
        if not isinstance(raw, RawSolverOutput):
            raise ScientificCoreError(
                f"solver.solve returned {type(raw).__name__}, not RawSolverOutput"
            )

        if raw.artifacts and artifact_resolver is None:
            raise ScientificCoreError(
                "solver declared execution artifacts but no artifact_resolver was supplied; "
                "a trusted record may not attest names whose bytes were never bound"
            )
        artifact_bytes = (
            dict(artifact_resolver(prepared, raw))
            if artifact_resolver is not None
            else {}
        )

        prepared_payload_bytes: bytes | None = None
        if prepared_payload_encoder is not None:
            prepared_payload_bytes = prepared_payload_encoder(prepared)
            if not isinstance(prepared_payload_bytes, bytes):
                raise ScientificCoreError(
                    "prepared_payload_encoder must return bytes; text/object coercion would "
                    "make artifact identity depend on an implicit representation"
                )

        # Build the manifest immediately after raw execution, before derived
        # metrics or validation.  If either later stage fails no trusted record
        # is returned, but the raw execution facts were still bound consistently.
        manifest = ExecutionManifest.from_execution(
            prepared,
            raw,
            artifact_bytes=artifact_bytes,
            prepared_payload_bytes=prepared_payload_bytes,
            environment=environment,
            realization_id=f"{realization.realization_id}@{realization.version}",
        )

        metrics = solver.extract_metrics(prepared, raw)
        if not isinstance(metrics, Mapping):
            raise ScientificCoreError(
                f"solver.extract_metrics returned {type(metrics).__name__}, not a mapping"
            )

        validation = solver.validate(prepared, raw)
        if not isinstance(validation, ValidationReport):
            raise ScientificCoreError(
                f"solver.validate returned {type(validation).__name__}, not ValidationReport"
            )

        return TrustedExecutionRecord(
            admission=admission,
            prepared=prepared,
            raw=raw,
            metrics=metrics,
            validation=validation,
            manifest=manifest,
        )


__all__ = [
    "ArtifactResolver",
    "PreparedPayloadEncoder",
    "TrustedExecutionRecord",
    "TrustedExecutionRuntime",
]
