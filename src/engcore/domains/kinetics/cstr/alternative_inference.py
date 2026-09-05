"""K4 model-specific inference bridge for the constant-rate CSTR approximation.

The existing CSTR numerical kernel evaluates

    k(T) = k0 * exp(-E / (R T)).

At exactly ``E = 0`` this reduces algebraically to ``k(T) = k0`` for every
positive temperature.  K4 reuses that already verified numerical machinery,
but it must not let the resulting scientific evidence pretend to belong to the
Arrhenius model family.  This module therefore performs two explicit steps:

1. cross the existing K1.5 CSTR numerical-admissibility boundary at ``E = 0``;
2. derive a new source result whose model/provenance binding is the separately
   declared constant-rate approximation.

The derived result keeps an explicit parent-run lineage to the numerical-kernel
execution.  It does not alter any numerical value, validation outcome, solver
identity or convergence evidence.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Mapping, Sequence

from ....inference.admissibility import (
    AdmissibleNumericalPrediction,
    InferenceAdmissibilityError,
)
from ....scientific.results.result import ScientificResult
from .alternatives import CONSTANT_RATE_CSTR_MODEL
from .inference import (
    CSTRInferenceForwardAdapter,
    CSTR_INFERENCE_DOMAIN,
    SUPPORTED_INFERENCE_OBSERVABLES,
)
from .problem import CSTR_MODEL, ReactorRun

CONSTANT_RATE_INFERENCE_ADAPTER_ID = (
    "kinetics.cstr.constant_rate.inference_forward/0.1.0"
)

_PRIMARY_MODEL_KEY = (CSTR_MODEL.model_id, CSTR_MODEL.version)
_CONSTANT_MODEL_KEY = (
    CONSTANT_RATE_CSTR_MODEL.model_id,
    CONSTANT_RATE_CSTR_MODEL.version,
)


def _require_exact_constant_rate_reduction(run: ReactorRun) -> None:
    """Require the exact E=0 reduction used by K4's competitor.

    The check is exact because ``activation_energy`` is a declaration, not a
    measured floating-point result.  K4 is not allowed to call a small positive
    activation energy "constant rate" by tolerance.
    """

    if not isinstance(run, ReactorRun):
        raise InferenceAdmissibilityError(
            "constant-rate CSTR inference requires a fully declared ReactorRun"
        )
    energy = run.chemistry.activation_energy.magnitude_in("J/mol")
    if energy != 0.0:
        raise InferenceAdmissibilityError(
            "constant-rate CSTR inference requires activation_energy == 0 exactly"
        )
    rate = run.chemistry.k0.magnitude_in("1/s")
    if not math.isfinite(rate) or rate <= 0.0:
        raise InferenceAdmissibilityError(
            "constant-rate CSTR inference requires a finite positive k_const"
        )


def derive_constant_rate_source_result(source: ScientificResult) -> ScientificResult:
    """Rebind one already-admitted E=0 numerical source to the K4 model.

    This is a provenance transformation, not a numerical transformation.  The
    values, solver, convergence, validation and uncertainty records are copied
    unchanged.  The new record identifies the model that scientifically
    interprets those values and keeps the original execution as its parent.
    """

    if not isinstance(source, ScientificResult):
        raise InferenceAdmissibilityError(
            "constant-rate model binding requires a ScientificResult source"
        )
    if tuple(source.models) != (_PRIMARY_MODEL_KEY,):
        raise InferenceAdmissibilityError(
            "constant-rate derivation expected one primary CSTR numerical source"
        )
    if tuple(source.provenance.models) != (_PRIMARY_MODEL_KEY,):
        raise InferenceAdmissibilityError(
            "constant-rate derivation source provenance has unexpected model binding"
        )

    source_inputs = dict(source.provenance.inputs)
    if "k0" not in source_inputs or "activation_energy" not in source_inputs:
        raise InferenceAdmissibilityError(
            "constant-rate derivation source is missing k0/activation_energy inputs"
        )
    energy = source_inputs["activation_energy"].magnitude_in("J/mol")
    if energy != 0.0:
        raise InferenceAdmissibilityError(
            "constant-rate derivation refuses a source whose activation energy is non-zero"
        )

    # The alternative model's scientific coordinate is k_const.  The gas
    # constant and activation energy are implementation details of the E=0
    # reduction and are therefore not presented as M2 model inputs.
    model_inputs = dict(source_inputs)
    model_inputs["k_const"] = model_inputs.pop("k0")
    model_inputs.pop("activation_energy", None)
    model_inputs.pop("molar_gas_constant", None)

    derived_id = f"{source.result_id}-constant-rate-model"
    provenance = source.provenance.derived(
        derived_id,
        software_version=CONSTANT_RATE_INFERENCE_ADAPTER_ID,
        models=(_CONSTANT_MODEL_KEY,),
        inputs=model_inputs,
        assumptions=CONSTANT_RATE_CSTR_MODEL.assumptions,
        environment={
            **dict(source.provenance.environment),
            "scientific_model_interpretation": "constant_rate_first_order",
            "model_binding_adapter": CONSTANT_RATE_INFERENCE_ADAPTER_ID,
        },
        metadata={
            **dict(source.provenance.metadata),
            "exact_numerical_reduction": (
                "the shared CSTR kernel was evaluated at activation_energy=0, "
                "for which k0*exp(-E/(R*T)) is algebraically k_const"
            ),
            "model_binding_semantics": (
                "numerical evidence is inherited unchanged from the admitted "
                "E=0 execution; model identity is the K4 constant-rate approximation"
            ),
        },
    )

    return replace(
        source,
        result_id=derived_id,
        problem_id=f"{source.problem_id}:constant-rate-model",
        models=(_CONSTANT_MODEL_KEY,),
        assumptions=CONSTANT_RATE_CSTR_MODEL.assumptions,
        provenance=provenance,
        metadata={
            **dict(source.metadata),
            "scientific_model_id": CONSTANT_RATE_CSTR_MODEL.model_id,
            "scientific_model_version": CONSTANT_RATE_CSTR_MODEL.version,
            "exact_numerical_reduction": "activation_energy=0",
            "parent_numerical_source_result_id": source.result_id,
        },
    )


class ConstantRateCSTRInferenceForwardAdapter:
    """Admit constant-rate CSTR predictions with model-specific provenance."""

    adapter_id = CONSTANT_RATE_INFERENCE_ADAPTER_ID

    def evaluate(
        self,
        run: ReactorRun,
        *,
        observable_names: Sequence[str] = SUPPORTED_INFERENCE_OBSERVABLES,
        run_id_prefix: str = "cstr-constant-rate-inference",
        source_commit: str | None = None,
        core_baseline_commit: str | None = None,
        timestamp: str | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> AdmissibleNumericalPrediction:
        _require_exact_constant_rate_reduction(run)
        prefix = str(run_id_prefix).strip()
        if not prefix:
            raise InferenceAdmissibilityError("run_id_prefix must be non-empty")

        # The primary adapter owns the complete K1.5 sequence gate.  It is used
        # only as the numerical-admission instrument at the exact E=0 reduction.
        admitted = CSTRInferenceForwardAdapter().evaluate(
            run,
            observable_names=observable_names,
            run_id_prefix=f"{prefix}-numerical-kernel",
            source_commit=source_commit,
            core_baseline_commit=core_baseline_commit,
            timestamp=timestamp,
            environment={
                **dict(environment or {}),
                "purpose": "k4-constant-rate-numerical-admission",
            },
        )
        rebound = derive_constant_rate_source_result(admitted.source_result)

        if tuple(rebound.models) != (_CONSTANT_MODEL_KEY,) or tuple(
            rebound.provenance.models
        ) != (_CONSTANT_MODEL_KEY,):
            raise InferenceAdmissibilityError(
                "constant-rate source did not retain model-specific provenance"
            )

        return AdmissibleNumericalPrediction(
            prediction_id=f"{prefix}-admitted",
            domain=CSTR_INFERENCE_DOMAIN,
            adapter_id=self.adapter_id,
            binding_ref=admitted.binding_ref,
            source_result=rebound,
            observable_names=admitted.observable_names,
            sequence_validation=admitted.sequence_validation,
            verification_ref=admitted.verification_ref,
            metadata={
                **dict(admitted.metadata),
                "scientific_model_id": CONSTANT_RATE_CSTR_MODEL.model_id,
                "scientific_model_version": CONSTANT_RATE_CSTR_MODEL.version,
                "exact_numerical_reduction": "activation_energy=0",
                "claim_boundary": (
                    "numerically admitted constant-rate approximation; no physical "
                    "validation or global adequacy claim"
                ),
            },
        )
