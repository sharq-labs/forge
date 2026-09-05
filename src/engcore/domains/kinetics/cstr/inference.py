"""Kinetics-owned bridge from CSTR solves to shared numerical inference.

The shared inference layer is intentionally unable to interpret a CSTR metric.
This module owns that meaning.  It is the only place that turns a fully
declared :class:`ReactorRun` into an :class:`AdmissibleNumericalPrediction`.

Admission requires both facts K1 kept separate:

* the ordinary source ``ScientificResult`` is usable; and
* the existing multi-solve verification gate actually establishes
  ``NUMERICALLY_CONVERGED`` for the same reactor declaration.

No posterior arithmetic lives here.  K2 may consume this adapter; it must not
bypass it by passing solver arrays directly to a likelihood.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

from ....inference.admissibility import (
    AdmissibleNumericalPrediction,
    InferenceAdmissibilityError,
)
from ....scientific.results.validation import ValidationLevel
from .problem import METRIC_UNITS, ReactorRun
from .solver import solve_reactor
from .validation import CONVERGENCE_QOIS, CSTRVerificationReport, run_verification_gate

CSTR_INFERENCE_ADAPTER_ID = "kinetics.cstr.inference_forward/0.1.0"
CSTR_INFERENCE_DOMAIN = "kinetics.cstr"

#: Only QoIs that the existing tolerance ladder actually checks may be exposed
#: by this adapter.  Adding an observable here requires adding sequence-level
#: evidence for it first; it is not a UI allow-list.
SUPPORTED_INFERENCE_OBSERVABLES = tuple(CONVERGENCE_QOIS)


@dataclass(frozen=True)
class CSTRInferenceForwardAdapter:
    """Admit CSTR forward predictions only after domain verification."""

    adapter_id: str = CSTR_INFERENCE_ADAPTER_ID

    def evaluate(
        self,
        run: ReactorRun,
        *,
        observable_names: Sequence[str] = SUPPORTED_INFERENCE_OBSERVABLES,
        run_id_prefix: str = "cstr-inference",
        source_commit: str | None = None,
        core_baseline_commit: str | None = None,
        timestamp: str | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> AdmissibleNumericalPrediction:
        if not isinstance(run, ReactorRun):
            raise InferenceAdmissibilityError(
                "CSTR inference requires a fully declared ReactorRun"
            )
        prefix = str(run_id_prefix).strip()
        if not prefix:
            raise InferenceAdmissibilityError("run_id_prefix must be non-empty")

        names = tuple(str(name).strip() for name in observable_names)
        if not names:
            raise InferenceAdmissibilityError(
                "CSTR inference requires at least one observable"
            )
        unknown = [name for name in names if name not in SUPPORTED_INFERENCE_OBSERVABLES]
        if unknown:
            raise InferenceAdmissibilityError(
                "CSTR inference can expose only observables covered by the "
                f"tolerance sequence {SUPPORTED_INFERENCE_OBSERVABLES}; got {unknown}"
            )

        # 1. Ordinary scientific lifecycle.  This is deliberately not replaced
        # by the verification gate: it is the attributable source result whose
        # unit-bearing values downstream inference will read.
        source = solve_reactor(
            run,
            run_id=f"{prefix}-source",
            software_version=CSTR_INFERENCE_ADAPTER_ID,
            source_commit=source_commit,
            core_baseline_commit=core_baseline_commit,
            timestamp=timestamp,
            environment={
                **dict(environment or {}),
                "purpose": "numerical-inference-source",
                "inference_adapter": self.adapter_id,
            },
        )
        if not source.is_usable:
            failures = "; ".join(
                f"{check.name}: {check.detail}" for check in source.validation.failures
            )
            raise InferenceAdmissibilityError(
                f"CSTR source result {source.result_id!r} is not scientifically "
                f"usable ({failures or source.convergence.value})"
            )

        expected_fingerprint = run.physics_fingerprint()
        result_fingerprint = str(source.metadata.get("physics_fingerprint", ""))
        provenance_fingerprint = str(
            source.provenance.metadata.get("physics_fingerprint", "")
        )
        if (
            result_fingerprint != expected_fingerprint
            or provenance_fingerprint != expected_fingerprint
        ):
            raise InferenceAdmissibilityError(
                "CSTR source provenance is not bound to the reactor physics "
                "fingerprint supplied to the inference adapter"
            )

        expected_units = {name: METRIC_UNITS[name] for name in names}
        try:
            source.check_units_against(expected_units)
        except Exception as exc:
            raise InferenceAdmissibilityError(
                f"CSTR source observable units do not match the domain: {exc}"
            ) from exc

        # 2. Sequence-level evidence.  The existing gate owns all tolerance,
        # invariant and independent-reference semantics; inference invents none.
        verification: CSTRVerificationReport = run_verification_gate(
            run,
            run_id_prefix=f"{prefix}-sequence",
        )
        sequence_report = verification.to_report()
        if not sequence_report.claims(ValidationLevel.NUMERICALLY_CONVERGED):
            raise InferenceAdmissibilityError(
                "CSTR verification sequence did not establish "
                f"NUMERICALLY_CONVERGED: {verification.tolerance_detail}"
            )

        # The attributable source solve must itself be one of the declarations
        # witnessed by the sequence.  This is a declaration-level equality,
        # not a fitted numerical threshold.
        witnessed = [
            row
            for row in verification.rungs
            if row.rung.rtol == run.integration.rtol
            and row.rung.atol_concentration == run.integration.atol_concentration
            and row.rung.atol_temperature == run.integration.atol_temperature
        ]
        if len(witnessed) != 1:
            raise InferenceAdmissibilityError(
                "the source integration declaration is not represented exactly "
                "once in the CSTR verification sequence"
            )
        witness = witnessed[0]
        if not witness.counts_toward_verification:
            raise InferenceAdmissibilityError(
                "the verification rung matching the source solve is not usable "
                "evidence about numerical accuracy"
            )

        # Same physics + same deterministic solver declaration should reproduce
        # the same QoIs.  Use the gate's already-declared convergence tolerance
        # rather than inventing a new K1.5 scientific threshold.
        mismatches: list[str] = []
        for name in names:
            if name not in witness.qois:
                mismatches.append(f"{name}: missing from sequence witness")
                continue
            source_value = source.value(name).magnitude_in(METRIC_UNITS[name])
            witness_value = float(witness.qois[name])
            scale = max(abs(source_value), abs(witness_value), 1e-300)
            relative = abs(source_value - witness_value) / scale
            if not math.isfinite(relative) or relative > verification.tolerance_rel_tol:
                mismatches.append(
                    f"{name}: source/witness relative difference {relative:.3e} "
                    f"> {verification.tolerance_rel_tol:.3e}"
                )
        if mismatches:
            raise InferenceAdmissibilityError(
                "CSTR source result is not consistent with its matching "
                "verification rung: " + "; ".join(mismatches)
            )

        return AdmissibleNumericalPrediction(
            prediction_id=f"{prefix}-admitted",
            domain=CSTR_INFERENCE_DOMAIN,
            adapter_id=self.adapter_id,
            binding_ref=expected_fingerprint,
            source_result=source,
            observable_names=names,
            sequence_validation=sequence_report,
            verification_ref=f"{prefix}-sequence",
            metadata={
                "physics_fingerprint": expected_fingerprint,
                "source_matching_rung": witness.rung.to_dict(),
                "verification": verification.to_dict(),
                "claim_boundary": (
                    "numerical inference only; no physical measurement or "
                    "experimental validation was performed"
                ),
            },
        )
