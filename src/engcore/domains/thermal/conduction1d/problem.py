"""The 1D transient conduction benchmark: slab, model, and problem statement.

THE PHYSICS, STATED ONCE
------------------------
On a slab of length ``L`` the normalized field ``u`` obeys

    du/dt = alpha * d2u/dx2        x in [0, L], t in [0, t_end]
    u(0, t) = u(L, t) = 0
    u(x, 0) = sin(pi x / L)

``u`` IS DIMENSIONLESS. It is a normalized field, not a temperature in kelvin,
and it carries the unit ``dimensionless`` everywhere it appears as a
:class:`~engcore.scientific.units.quantity.Quantity`. Calling it kelvin would
imply an absolute scale, a reference state and a material this benchmark does
not have, and would invite exactly the physical over-reading this milestone is
supposed to avoid.

WHY THE BOUNDARY AND INITIAL CONDITIONS ARE FIXED
-------------------------------------------------
They are not configurable, and that is the point. This benchmark exists to
verify a solver against an independent closed form, and it was chosen because
one Fourier mode in gives exactly one Fourier mode out:

    u(x, t) = sin(pi x / L) * exp(-alpha pi^2 t / L^2)

No series, no truncation, no special functions — so the reference carries no
approximation of its own to be confused with the solver's discretization
error. Making the conditions configurable would buy generality this milestone
has no use for and would put a truncated series between the solver and the
only thing verifying it.

WHAT IS CONFIGURABLE
--------------------
The physical declaration (``length``, ``diffusivity``, ``end_time``) and the
numerical declaration (``n_cells``, ``n_steps``). These are separate on
purpose: the first says what problem is being posed, the second says how
finely it is being resolved, and a domain that cannot tell those apart cannot
report a discretization error.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

from ....scientific.ir.problem import ModelReference, ScientificProblem
from ....scientific.ir.variables import (
    ScientificParameter,
    ScientificVariable,
    VariableRole,
)
from ....scientific.models.definition import (
    InputSourceKind,
    ModelInputSpec,
    ModelOutputSpec,
    ModelType,
    ModelValidationStatus,
    RangeCondition,
    ScientificModelDefinition,
    ValidityDomain,
)
from ....scientific.solvers.capability import SolverCapability
from ....scientific.units.quantity import Quantity
from .errors import SlabConfigurationError

# --- units -------------------------------------------------------------------
FIELD_UNIT = "dimensionless"
LENGTH_UNIT = "meter"
TIME_UNIT = "second"
DIFFUSIVITY_UNIT = "m**2/s"

# --- capability, declared in this package and nowhere else -------------------
THERMAL_CONDUCTION_1D = SolverCapability(
    "thermal:conduction_1d_transient",
    "1D transient linear diffusion with fixed Dirichlet ends",
)

MODEL_VERSION = "0.1.0"

_ASSUMPTIONS = (
    "one spatial dimension; no lateral or multidimensional transport",
    "linear diffusion with a constant, field-independent diffusivity",
    "no source or sink term",
    "homogeneous Dirichlet boundaries held exactly at zero for all time",
    "single-mode sinusoidal initial condition",
    "normalized dimensionless field; no absolute temperature scale, no "
    "material properties and no thermodynamic state are claimed",
    "no convection, no radiation, no phase change",
)

DIFFUSION_MODEL = ScientificModelDefinition(
    model_id="thermal.conduction1d.linear_diffusion",
    version=MODEL_VERSION,
    name="1D linear transient diffusion",
    domain="thermal",
    # FUNDAMENTAL_RELATION: the diffusion equation is a conservation statement,
    # not a fitted correlation and not an approximation of something else. The
    # APPROXIMATION in this domain is the discretization, which belongs to the
    # solver, not to the model.
    model_type=ModelType.FUNDAMENTAL_RELATION,
    description=(
        "The 1D diffusion equation du/dt = alpha d2u/dx2 on a finite slab "
        "with homogeneous Dirichlet boundaries, for a normalized "
        "dimensionless field."
    ),
    inputs=(
        ModelInputSpec(
            name="alpha",
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=DIFFUSIVITY_UNIT,
            description="Thermal diffusivity; strictly positive.",
        ),
        ModelInputSpec(
            name="length",
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=LENGTH_UNIT,
            description="Slab length.",
        ),
        ModelInputSpec(
            name="end_time",
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=TIME_UNIT,
            description="Final time of the transient.",
        ),
    ),
    outputs=(
        ModelOutputSpec(
            metric="u",
            unit_exemplar=FIELD_UNIT,
            description=(
                "Normalized dimensionless field over the slab. Not a "
                "temperature: no absolute scale or reference state is implied."
            ),
        ),
    ),
    assumptions=_ASSUMPTIONS,
    validity=ValidityDomain(
        conditions=(
            RangeCondition(
                name="alpha",
                minimum=Quantity(0.0, DIFFUSIVITY_UNIT),
                minimum_inclusive=False,
                description=(
                    "Strictly positive diffusivity; zero is no transport and "
                    "negative is anti-diffusion, which is ill-posed."
                ),
            ),
        ),
        description=(
            "Linear diffusion with constant coefficients on a bounded slab."
        ),
    ),
    required_capabilities=frozenset({THERMAL_CONDUCTION_1D.name}),
    # SELF_CONSISTENT, not BENCHMARK_VALIDATED: agreement with a closed-form
    # solution of the same equation shows the discretization solves what it
    # claims to solve. It is not an external benchmark and involves no
    # measurement of anything physical.
    validation_status=ModelValidationStatus.SELF_CONSISTENT,
    references=(),
)

CONDUCTION_MODELS = (DIFFUSION_MODEL,)


def conduction_solver_capabilities() -> frozenset[SolverCapability]:
    return frozenset({THERMAL_CONDUCTION_1D})


# =====================================================================
# Declarations
# =====================================================================

@dataclass(frozen=True)
class SlabDiscretization:
    """How finely the slab is resolved. Purely numerical.

    ``n_cells`` must be even so that the midpoint x = L/2 is a grid node. The
    primary QoI is read there, and an even mesh makes it an exact nodal value
    rather than an interpolation — which keeps interpolation error out of a
    measurement whose entire purpose is to expose discretization error.
    """

    n_cells: int
    n_steps: int

    def __post_init__(self) -> None:
        for label in ("n_cells", "n_steps"):
            raw = getattr(self, label)
            if isinstance(raw, bool) or not isinstance(raw, int):
                raise SlabConfigurationError(
                    f"{label} must be an int, got {type(raw).__name__}"
                )
        if self.n_cells < 2:
            raise SlabConfigurationError(
                f"n_cells must be at least 2 (one interior node), got "
                f"{self.n_cells}"
            )
        if self.n_cells % 2 != 0:
            raise SlabConfigurationError(
                f"n_cells must be even so that x = L/2 is a grid node, got "
                f"{self.n_cells}; the midpoint QoI is read as a nodal value"
            )
        if self.n_steps < 1:
            raise SlabConfigurationError(
                f"n_steps must be at least 1, got {self.n_steps}"
            )

    @property
    def n_interior(self) -> int:
        return self.n_cells - 1

    @property
    def work_proxy(self) -> int:
        """Deterministic proxy for computational work: cells x steps.

        Used instead of wall-clock wherever a reproducible cost figure is
        wanted. Wall-clock is recorded as telemetry and is not a score.
        """
        return self.n_cells * self.n_steps

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_cells": self.n_cells,
            "n_steps": self.n_steps,
            "n_interior": self.n_interior,
            "work_proxy": self.work_proxy,
        }


def _positive_quantity(value: Any, unit: str, label: str) -> Quantity:
    if not isinstance(value, Quantity):
        raise SlabConfigurationError(
            f"{label} must be a Quantity carrying {unit!r}, got "
            f"{type(value).__name__} — a bare number is not a declaration"
        )
    magnitude = value.magnitude_in(unit)
    if not math.isfinite(magnitude) or magnitude <= 0.0:
        raise SlabConfigurationError(
            f"{label} must be finite and strictly positive, got {magnitude!r} "
            f"{unit}"
        )
    return value


@dataclass(frozen=True)
class ConductionSlab:
    """One fully declared benchmark instance.

    Boundary and initial conditions are not fields: they are fixed by this
    benchmark and documented in the module docstring.
    """

    slab_id: str
    length: Quantity
    diffusivity: Quantity
    end_time: Quantity
    discretization: SlabDiscretization

    def __post_init__(self) -> None:
        if not str(self.slab_id).strip():
            raise SlabConfigurationError("slab requires a non-empty slab_id")
        object.__setattr__(self, "slab_id", str(self.slab_id).strip())
        _positive_quantity(self.length, LENGTH_UNIT, "length")
        _positive_quantity(self.diffusivity, DIFFUSIVITY_UNIT, "diffusivity")
        _positive_quantity(self.end_time, TIME_UNIT, "end_time")
        if not isinstance(self.discretization, SlabDiscretization):
            raise SlabConfigurationError(
                "discretization must be a SlabDiscretization"
            )

    # -- convenience accessors in base units --------------------------------
    @property
    def length_m(self) -> float:
        return self.length.magnitude_in(LENGTH_UNIT)

    @property
    def alpha_m2_s(self) -> float:
        return self.diffusivity.magnitude_in(DIFFUSIVITY_UNIT)

    @property
    def end_time_s(self) -> float:
        return self.end_time.magnitude_in(TIME_UNIT)

    @property
    def dx_m(self) -> float:
        return self.length_m / self.discretization.n_cells

    @property
    def dt_s(self) -> float:
        return self.end_time_s / self.discretization.n_steps

    @property
    def fourier_number(self) -> float:
        """alpha dt / dx^2. Reported for provenance.

        Backward Euler is unconditionally stable, so this is not a stability
        constraint here — it is recorded because it is the number that would
        constrain an explicit scheme, and a reader comparing schemes will
        want it.
        """
        return self.alpha_m2_s * self.dt_s / (self.dx_m**2)

    def with_discretization(
        self, discretization: SlabDiscretization
    ) -> "ConductionSlab":
        """The same physical slab at a different resolution.

        The refinement gate uses this: every rung must be the same physics,
        differing only numerically, or the comparison across rungs would not
        be a discretization study.
        """
        return ConductionSlab(
            slab_id=self.slab_id,
            length=self.length,
            diffusivity=self.diffusivity,
            end_time=self.end_time,
            discretization=discretization,
        )

    def fingerprint(self) -> str:
        """Identity of the PHYSICAL problem, excluding the discretization."""
        import hashlib
        import json

        blob = json.dumps(
            {
                "slab_id": self.slab_id,
                "length_m": self.length_m,
                "alpha_m2_s": self.alpha_m2_s,
                "end_time_s": self.end_time_s,
                "boundary": "dirichlet_zero_both_ends",
                "initial": "sin(pi x / L)",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "slab_id": self.slab_id,
            "length_m": self.length_m,
            "alpha_m2_s": self.alpha_m2_s,
            "end_time_s": self.end_time_s,
            "boundary_conditions": "u(0,t) = u(L,t) = 0",
            "initial_condition": "u(x,0) = sin(pi x / L)",
            "field_unit": FIELD_UNIT,
            "discretization": self.discretization.to_dict(),
            "dx_m": self.dx_m,
            "dt_s": self.dt_s,
            "fourier_number": self.fourier_number,
            "fingerprint": self.fingerprint(),
        }


# =====================================================================
# The universal problem statement
# =====================================================================

MIDPOINT_METRIC = "u:midpoint"
MAX_METRIC = "u:max_abs"
LEFT_METRIC = "u:boundary_left"
RIGHT_METRIC = "u:boundary_right"


def build_conduction_problem(
    slab: ConductionSlab, *, problem_id: str | None = None
) -> ScientificProblem:
    """Express the benchmark in the domain-neutral IR.

    The discretization is carried as metadata, not as a parameter: it is a
    property of how the problem is being solved, not of the problem.
    """
    variables = (
        ScientificVariable(
            name=MIDPOINT_METRIC,
            unit=FIELD_UNIT,
            role=VariableRole.OBSERVABLE,
            description="Normalized field at the slab midpoint at the final time",
        ),
        ScientificVariable(
            name=MAX_METRIC,
            unit=FIELD_UNIT,
            role=VariableRole.OBSERVABLE,
            description="Maximum absolute field value at the final time",
        ),
    )
    parameters = (
        ScientificParameter(
            name="alpha",
            value=slab.diffusivity,
            description="Thermal diffusivity",
        ),
        ScientificParameter(
            name="length",
            value=slab.length,
            description="Slab length",
        ),
        ScientificParameter(
            name="end_time",
            value=slab.end_time,
            description="Final time of the transient",
        ),
    )
    return ScientificProblem(
        problem_id=problem_id or f"thermal-conduction1d-{slab.slab_id}",
        name="1D transient linear diffusion on a slab",
        description=(
            "Normalized dimensionless field on [0, L] with homogeneous "
            "Dirichlet ends and a single-mode sinusoidal initial condition."
        ),
        variables=variables,
        parameters=parameters,
        models=tuple(
            ModelReference(model.model_id, model.version)
            for model in CONDUCTION_MODELS
        ),
        required_capabilities=frozenset({THERMAL_CONDUCTION_1D.name}),
        validation_requirements=frozenset(
            {
                "dimensional_consistency",
                "linear_system_residual",
                "boundary_conditions_held",
                "field_finite",
                "amplitude_decay",
            }
        ),
        metadata={
            "domain": "thermal",
            "slab_id": slab.slab_id,
            "slab_fingerprint": slab.fingerprint(),
            "boundary_conditions": "u(0,t) = u(L,t) = 0",
            "initial_condition": "u(x,0) = sin(pi x / L)",
            "field_unit": FIELD_UNIT,
            "n_cells": str(slab.discretization.n_cells),
            "n_steps": str(slab.discretization.n_steps),
            "work_proxy": str(slab.discretization.work_proxy),
        },
    )


def verify_problem_matches_slab(
    problem: ScientificProblem, slab: ConductionSlab
) -> None:
    """Refuse a problem/slab pairing that describes different physics."""
    declared = problem.metadata.get("slab_fingerprint")
    actual = slab.fingerprint()
    if declared and declared != actual:
        raise SlabConfigurationError(
            f"problem {problem.problem_id!r} declares slab fingerprint "
            f"{str(declared)[:12]}… but was paired with {actual[:12]}…; the "
            f"problem and the slab describe different physical systems"
        )
