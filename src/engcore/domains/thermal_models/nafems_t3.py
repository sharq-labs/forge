"""Executable NAFEMS P18.T3 transient-thermal verification vertical.

This is deliberately a benchmark-specific execution path, not a general
thermal solver API.  The scientific case is fixed to the repository-reviewed
NAFEMS T3 evidence pack and only the numerical resolution is configurable.

Physics
-------
For a uniform 1D bar,

    rho * cp * dT/dt = k * d2T/dx2

with the NAFEMS T3 initial/boundary declarations:

    T(x, 0) = 0 degC
    T(0, t) = 0 degC
    T(L, t) = 100 sin(pi t / 40) degC

and zero internal generation / zero lateral heat flux.

Execution uses Crank-Nicolson in time and second-order central differences in
space.  Temperatures are marched as excursions from 0 degC, then reported on
the absolute kelvin scale.  A companion refined solve is used only as a
sensitivity check; it does not grant a validation level.

The external validation level comes exclusively from the repository-pinned
NAFEMS oracle in nafems_t3_oracle.py.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np
from scipy.linalg import solve_banded

from ...scientific.models.definition import (
    InputSourceKind,
    ModelInputSpec,
    ModelOutputSpec,
    ModelType,
    ModelValidationStatus,
    RangeCondition,
    ScientificModelDefinition,
    ValidityDomain,
)
from ...scientific.results.provenance import ProvenanceRecord
from ...scientific.results.result import ScientificResult
from ...scientific.results.uncertainty import Uncertainty
from ...scientific.results.validation import (
    ValidationCheck,
    ValidationLevel,
    ValidationOutcome,
    ValidationReport,
)
from ...scientific.solvers.protocol import ConvergenceState, SolverIdentity
from ...scientific.units.quantity import Quantity
from .nafems_t3_oracle import CONDITIONS, EVIDENCE_DIGEST, nafems_t3_evidence

MODEL_ID = "thermal.nafems_t3.transient_heat_1d"
MODEL_VERSION = "1.0.0"
SOLVER_ID = "thermal_models.nafems_t3.crank_nicolson"
SOLVER_VERSION = "1.0.0"
PROBLEM_ID = "nafems.p18.t3"
QOI = "temperature_at_probe"

# The benchmark target is printed to one decimal degC.  Keep the internal
# discretisation sensitivity below half that recording interval before the
# result is even compared with the external oracle.
REFINEMENT_DELTA_LIMIT_K = 0.025

_ASSUMPTIONS = (
    "one-dimensional heat conduction in a uniform bar",
    "constant isotropic conductivity, density and specific heat",
    "no internal heat generation",
    "zero heat flux perpendicular to the bar axis",
    "Dirichlet boundary temperatures exactly as declared by NAFEMS T3",
)

_EXCLUSIONS = (
    "temperature-dependent material properties",
    "phase change",
    "radiation and convection losses from the lateral surface",
    "multidimensional temperature gradients",
    "contact thermal resistance",
)

_INPUT_UNITS = {
    "length": "meter",
    "width": "meter",
    "depth": "meter",
    "conductivity": "watt/meter/kelvin",
    "density": "kilogram/meter**3",
    "specific_heat": "joule/kilogram/kelvin",
    "end_time": "second",
    "probe_position": "meter",
    "initial_temperature": "kelvin",
    "left_boundary_temperature": "kelvin",
    "right_boundary_offset": "kelvin",
    "right_boundary_amplitude": "kelvin",
    "right_boundary_sine_time_scale": "second",
    "lateral_heat_flux": "watt/meter**2",
    "internal_heat_generation": "watt/meter**3",
}

MODEL = ScientificModelDefinition(
    model_id=MODEL_ID,
    version=MODEL_VERSION,
    name="NAFEMS P18.T3 one-dimensional transient heat conduction",
    domain="thermal",
    model_type=ModelType.FUNDAMENTAL_RELATION,
    description=(
        "Benchmark-specific 1D transient heat equation with the exact NAFEMS "
        "P18.T3 material, geometry, initial condition and boundary law."
    ),
    inputs=tuple(
        ModelInputSpec(
            name=name,
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=unit,
            description="NAFEMS P18.T3 fixed benchmark declaration.",
        )
        for name, unit in _INPUT_UNITS.items()
    ),
    outputs=(
        ModelOutputSpec(
            metric=QOI,
            unit_exemplar="kelvin",
            description="Absolute temperature at x=0.08 m and t=32 s.",
        ),
    ),
    assumptions=_ASSUMPTIONS,
    exclusions=_EXCLUSIONS,
    validity=ValidityDomain(
        conditions=tuple(
            RangeCondition(
                name=name,
                minimum=value,
                maximum=value,
                description="Exact repository-reviewed NAFEMS P18.T3 operating point.",
            )
            for name, value in CONDITIONS.items()
        ),
        description=(
            "This executable model is intentionally restricted to the exact "
            "NAFEMS P18.T3 benchmark declaration."
        ),
    ),
    references=(
        "NAFEMS P18.T3, The Standard NAFEMS Benchmarks, Rev. 3 (1990)",
        "Altair OptiStruct OS-V:0110 / NAFEMS T3 public verification case",
        "MOOSE Heat Transfer NAFEMS T3 verification example",
    ),
    validation_status=ModelValidationStatus.UNVALIDATED,
)


@dataclass(frozen=True)
class NAFEMST3Numerics:
    """Numerical resolution only; the benchmark physics is not configurable."""

    n_cells: int = 160
    n_steps: int = 640

    def __post_init__(self) -> None:
        if isinstance(self.n_cells, bool) or not isinstance(self.n_cells, int):
            raise TypeError("n_cells must be an integer")
        if isinstance(self.n_steps, bool) or not isinstance(self.n_steps, int):
            raise TypeError("n_steps must be an integer")
        if self.n_cells < 10:
            raise ValueError("n_cells must be at least 10")
        if self.n_steps < 1:
            raise ValueError("n_steps must be positive")
        if self.n_cells % 5:
            raise ValueError(
                "n_cells must be divisible by 5 so the x=0.08 m QoI is a grid node"
            )


def _magnitude(name: str, unit: str) -> float:
    return CONDITIONS[name].magnitude_in(unit)


def _right_excursion(time_s: float) -> float:
    amplitude = _magnitude("right_boundary_amplitude", "kelvin")
    scale = _magnitude("right_boundary_sine_time_scale", "second")
    return amplitude * math.sin(math.pi * time_s / scale)


def _integrate(numerics: NAFEMST3Numerics) -> tuple[float, dict[str, float]]:
    length = _magnitude("length", "meter")
    conductivity = _magnitude("conductivity", "watt/meter/kelvin")
    density = _magnitude("density", "kilogram/meter**3")
    heat_capacity = _magnitude("specific_heat", "joule/kilogram/kelvin")
    end_time = _magnitude("end_time", "second")
    probe = _magnitude("probe_position", "meter")

    diffusivity = conductivity / (density * heat_capacity)
    dx = length / numerics.n_cells
    dt = end_time / numerics.n_steps
    r = diffusivity * dt / (dx * dx)

    n_interior = numerics.n_cells - 1
    diagonal = np.full(n_interior, 1.0 + r, dtype=float)
    off = np.full(max(n_interior - 1, 0), -0.5 * r, dtype=float)
    banded = np.zeros((3, n_interior), dtype=float)
    banded[0, 1:] = off
    banded[1, :] = diagonal
    banded[2, :-1] = off

    excursion = np.zeros(n_interior, dtype=float)
    for step in range(numerics.n_steps):
        t0 = step * dt
        t1 = (step + 1) * dt

        rhs = (1.0 - r) * excursion
        rhs = rhs.copy()
        rhs[:-1] += 0.5 * r * excursion[1:]
        rhs[1:] += 0.5 * r * excursion[:-1]

        # Left boundary excursion is zero.  The right boundary contributes at
        # both Crank-Nicolson time levels.
        rhs[-1] += 0.5 * r * (_right_excursion(t0) + _right_excursion(t1))
        excursion = np.asarray(solve_banded((1, 1), banded, rhs), dtype=float)

    full = np.concatenate(
        (
            np.array([0.0]),
            excursion,
            np.array([_right_excursion(end_time)]),
        )
    )
    probe_index = int(round(probe / dx))
    if not math.isclose(probe_index * dx, probe, rel_tol=0.0, abs_tol=1.0e-14):
        raise ValueError("configured mesh does not place the T3 probe on a node")

    absolute_offset = _magnitude("initial_temperature", "kelvin")
    probe_kelvin = absolute_offset + float(full[probe_index])
    return probe_kelvin, {
        "dx_m": dx,
        "dt_s": dt,
        "fourier_number_per_step": r,
        "probe_index": float(probe_index),
        "max_excursion_k": float(np.max(full)),
        "right_boundary_final_excursion_k": float(full[-1]),
    }


def solve_nafems_t3(
    *,
    run_id: str = "nafems-t3",
    numerics: NAFEMST3Numerics | None = None,
    software_version: str = "engcore.domains.thermal_models.nafems_t3/1.0.0",
    git_commit: str | None = None,
    timestamp: str | None = None,
) -> ScientificResult:
    """Execute the benchmark and attach its trusted external comparison."""

    numerics = numerics or NAFEMST3Numerics()
    fine_temperature, diagnostics = _integrate(numerics)
    coarse = NAFEMST3Numerics(
        n_cells=numerics.n_cells // 2,
        n_steps=max(1, numerics.n_steps // 2),
    )
    # Preserve the exact probe-node contract on the companion study.
    if coarse.n_cells % 5:
        raise ValueError(
            "the companion refinement level does not place the T3 probe on a node"
        )
    coarse_temperature, _ = _integrate(coarse)
    refinement_delta = abs(fine_temperature - coarse_temperature)

    finite = math.isfinite(fine_temperature)
    right_expected = _right_excursion(_magnitude("end_time", "second"))
    right_error = abs(
        diagnostics["right_boundary_final_excursion_k"] - right_expected
    )

    self_checks = (
        ValidationCheck(
            name="nafems_t3_field_finite",
            outcome=ValidationOutcome.PASS if finite else ValidationOutcome.FAIL,
            detail=f"reported probe temperature = {fine_temperature:.12g} K",
        ),
        ValidationCheck(
            name="nafems_t3_boundary_conditions_held",
            outcome=(
                ValidationOutcome.PASS
                if right_error <= 1.0e-12
                else ValidationOutcome.FAIL
            ),
            residual=right_error,
            tolerance=1.0e-12,
            detail="time-dependent right Dirichlet boundary is imposed exactly",
        ),
        ValidationCheck(
            name="nafems_t3_refinement_sensitivity",
            outcome=(
                ValidationOutcome.PASS
                if refinement_delta <= REFINEMENT_DELTA_LIMIT_K
                else ValidationOutcome.FAIL
            ),
            residual=refinement_delta,
            tolerance=REFINEMENT_DELTA_LIMIT_K,
            detail=(
                "difference between the reported solve and a 2x coarser "
                "space/time companion; this is a sensitivity gate, not a "
                "NUMERICALLY_CONVERGED level"
            ),
        ),
    )

    solver = SolverIdentity(SOLVER_ID, SOLVER_VERSION, backend="scipy.linalg.solve_banded")
    provenance = ProvenanceRecord(
        run_id=run_id,
        software_version=software_version,
        git_commit=git_commit,
        models=(MODEL.key,),
        solvers=(solver.key,),
        inputs=dict(CONDITIONS),
        assumptions=MODEL.assumptions,
        tolerances={
            "refinement_delta_limit_k": REFINEMENT_DELTA_LIMIT_K,
            "oracle_recording_envelope_k": 0.05,
        },
        timestamp=timestamp,
        metadata={
            "benchmark": "NAFEMS P18.T3",
            "oracle_digest": EVIDENCE_DIGEST,
            "n_cells": numerics.n_cells,
            "n_steps": numerics.n_steps,
            "coarse_n_cells": coarse.n_cells,
            "coarse_n_steps": coarse.n_steps,
            **diagnostics,
            "refinement_delta_k": refinement_delta,
        },
    )

    base = ScientificResult(
        result_id=run_id,
        problem_id=PROBLEM_ID,
        values={QOI: Quantity(fine_temperature, "kelvin")},
        models=(MODEL.key,),
        validity={
            MODEL.model_id: MODEL.validity.assess(
                dict(CONDITIONS), record_values=True
            )
        },
        solver=solver,
        convergence=ConvergenceState.CONVERGED,
        validation=ValidationReport(checks=self_checks),
        uncertainty={
            QOI: Uncertainty.unknown(
                "T3 execution does not yet quantify numerical, parameter or "
                "model-form uncertainty; the refinement study is a validation "
                "check and is not converted into a standard uncertainty"
            )
        },
        assumptions=MODEL.assumptions,
        provenance=provenance,
        metadata={
            "benchmark": "NAFEMS P18.T3",
            "oracle_digest": EVIDENCE_DIGEST,
        },
    )

    oracle_check = nafems_t3_evidence().compare(
        base.values,
        conditions=CONDITIONS,
        predicted_from=base,
        name="nafems_t3_external_benchmark",
    )
    return replace(
        base,
        validation=base.validation.with_check(oracle_check),
    )


__all__ = [
    "MODEL",
    "MODEL_ID",
    "MODEL_VERSION",
    "NAFEMST3Numerics",
    "PROBLEM_ID",
    "QOI",
    "REFINEMENT_DELTA_LIMIT_K",
    "SOLVER_ID",
    "SOLVER_VERSION",
    "solve_nafems_t3",
]
