"""Steady 1D conduction on a NON-UNIFORM grid, so local mesh adaptation can drive it.

Adaptive mesh control, slice 3 (active-epic exception EXC-1, amendment A2).
A new solver path beside the uniform ones.  ``engcore.domains.thermal`` (the
frozen ``conduction1d``) and ``conduction1d_schemes`` are not touched, and this
module registers no model, no capability and no validation check.  It solves
the declared equation; it holds no authority over whether that equation is the
right model of anything.

Equation and boundaries
    ``-(k(x) u'(x))' = q(x)`` on ``[0, L]``.  ``k`` is in W/(m K), ``q`` in
    W/m**3, ``x`` in metres, ``u`` in kelvin.  Each end carries an EXPLICIT
    boundary condition: a temperature, or a heat flux INTO the slab through that
    face.  Nothing is defaulted.  Two flux ends are refused, because they fix
    the temperature only up to a constant.

Discretisation
    Vertex-centred finite volumes on the grid nodes.  Node ``i`` owns the
    control volume between the midpoints of its two cells (half a cell at an
    end).  The face conductance of cell ``i`` is ``k(midpoint) / h_i`` and the
    source is ``q(x_i)`` times the control-volume width.  With constant ``k`` and
    a quadratic solution (constant ``q``) the nodal values are exact on ANY
    grid, flux ends included.  Otherwise the scheme is second order on smooth
    data.  The tridiagonal system is solved by the Thomas algorithm.  It is an
    M-matrix, so no pivoting is needed.

Adaptation
    :func:`temperature_evaluator` returns the ``grid -> nodal temperatures (K)``
    callable that :func:`engcore.numerical.mesh_adaptation.adapt_grid` takes,
    and :func:`adapt_conduction` is that call.  The adaptation indicator assumes
    a smooth solution: at a jump in ``k`` the curvature it reads is not the
    solution's, and the record says so (an ESTIMATE, never a bound, never
    validation).

Declaration (slice 4, EXC-1 amendment A3)
    :data:`STEADY_CONDUCTION_MODEL` states the equation as a model record, and
    :data:`NONUNIFORM_FV_REALIZATION` is this module's realization of it.  Both
    sit in fresh local registries (no global singleton), as in ``lumped`` and
    ``conduction1d_schemes``.  The model declares NO validity conditions, so its
    applicability assesses as UNKNOWN: no applicability limit has been
    sourced, and an absent limit is not an unlimited one.  It is UNVALIDATED.
    No claims-layer capability declares it, so claims, SRIA and MCP cannot reach
    it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

import numpy as np

from ...numerical.mesh_adaptation import AdaptationPolicy, AdaptationRecord, Grid1D, adapt_grid
from ...scientific.capabilities import ScientificCapability
from ...scientific.errors import InvalidScientificProblem
from ...scientific.ir.problem import ModelReference
from ...scientific.models.definition import (
    InputSourceKind,
    ModelInputSpec,
    ModelOutputSpec,
    ModelType,
    ScientificModelDefinition,
    ValidityDomain,
)
from ...scientific.models.registry import ModelRegistry
from ...scientific.realizations.definition import (
    ImplementationReference,
    ModelFormulation,
    ModelRealizationDefinition,
)
from ...scientific.realizations.registry import RealizationRegistry
from ...scientific.solvers.capability import CoreCapabilities, SolverCapability, SolverCapabilityId
from ...scientific.units.quantity import Quantity

_END_TOLERANCE = 1e-12  # relative: a grid end must sit on the slab face, not merely near it


# =====================================================================
# Declaration: model, capabilities, realization (slice 4)
# =====================================================================

#: What science the realization claims to provide: a steady temperature profile
#: across a 1D slab.  Distinct from ``thermal:transient_conduction_1d``, which
#: the two transient schemes provide: a steady profile does not satisfy a
#: consumer of a transient, nor the reverse.
STEADY_CONDUCTION_1D = ScientificCapability.parse("thermal:steady_conduction_1d")

#: What a backend must be able to do: assemble and solve this module's
#: non-uniform finite-volume system.  A *solver* capability.
NONUNIFORM_STEADY_CONDUCTION = SolverCapability(
    "thermal:nonuniform_steady_conduction_1d",
    "Vertex-centred finite volumes for steady 1D conduction on a non-uniform grid",
)

STEADY_CONDUCTION_MODEL = ScientificModelDefinition(
    model_id="thermal.conduction1d.steady_variable_conductivity",
    version="0.1.0",
    name="1D steady conduction with position-dependent conductivity and source",
    domain="thermal",
    # FUNDAMENTAL_RELATION: steady energy conservation with Fourier's law, as for
    # the transient diffusion record.  The approximation is the discretisation,
    # which belongs to the realization, not to the model.
    model_type=ModelType.FUNDAMENTAL_RELATION,
    description=(
        "-(k(x) dT/dx)' = q(x) on [0, L], with an explicit temperature or inward heat flux at each end and a "
        "temperature at one end at least."
    ),
    inputs=(
        ModelInputSpec(name="length", source_kind=InputSourceKind.PARAMETER, unit_exemplar="meter",
                       description="Slab thickness; strictly positive."),
        ModelInputSpec(name="thermal_conductivity", source_kind=InputSourceKind.PARAMETER,
                       unit_exemplar="watt/meter/kelvin", varies_with="position",
                       description="k(x); strictly positive and finite on the slab."),
        ModelInputSpec(name="volumetric_heat_source", source_kind=InputSourceKind.PARAMETER,
                       unit_exemplar="watt/meter**3", varies_with="position",
                       description="q(x); finite on the slab."),
        ModelInputSpec(name="left_temperature", source_kind=InputSourceKind.PARAMETER, unit_exemplar="kelvin",
                       required=False, description="Temperature at x = 0; exactly one of the two left inputs."),
        ModelInputSpec(name="left_inward_heat_flux", source_kind=InputSourceKind.PARAMETER,
                       unit_exemplar="watt/meter**2", required=False,
                       description="Heat flux into the slab at x = 0; exactly one of the two left inputs."),
        ModelInputSpec(name="right_temperature", source_kind=InputSourceKind.PARAMETER, unit_exemplar="kelvin",
                       required=False, description="Temperature at x = L; exactly one of the two right inputs."),
        ModelInputSpec(name="right_inward_heat_flux", source_kind=InputSourceKind.PARAMETER,
                       unit_exemplar="watt/meter**2", required=False,
                       description="Heat flux into the slab at x = L; exactly one of the two right inputs."),
    ),
    outputs=(
        ModelOutputSpec(metric="temperature", unit_exemplar="kelvin",
                        description="Steady temperature at the grid nodes."),
    ),
    assumptions=(
        "one spatial dimension; no lateral transport",
        "steady state",
        "Fourier conduction with a conductivity that depends on position only",
        "an explicit temperature or inward heat flux at each end, and a temperature at one end at least",
    ),
    exclusions=(
        "temperature dependence of the conductivity",
        "transient behaviour, thermal capacity and diffusivity",
        "convection and radiation, except as an imposed boundary heat flux",
        "contact resistance between layers",
        "phase change",
        "multidimensional conduction",
    ),
    validity=ValidityDomain(
        description=(
            "No applicability conditions are declared: none has been sourced.  Applicability therefore "
            "assesses as UNKNOWN, never as valid."
        ),
    ),
)

NONUNIFORM_FV_REALIZATION = ModelRealizationDefinition(
    realization_id="thermal.conduction1d.steady_variable_conductivity.nonuniform_fv",
    version="0.1.0",
    model=ModelReference(STEADY_CONDUCTION_MODEL.model_id, STEADY_CONDUCTION_MODEL.version),
    # The model poses a two-point boundary-value ODE in x.  That is what
    # `formulation` records; the realization discharges it with one linear solve.
    formulation=ModelFormulation.ODE,
    name="Vertex-centred finite volumes on a non-uniform grid",
    description=(
        "Face conductances k(midpoint)/h, the source at the node times the control-volume width, and one "
        "tridiagonal solve (Thomas)."
    ),
    provided_capabilities=frozenset({STEADY_CONDUCTION_1D}),
    required_solver_capabilities=frozenset({
        SolverCapabilityId.coerce(NONUNIFORM_STEADY_CONDUCTION),
        SolverCapabilityId.coerce(CoreCapabilities.LINEAR_SYSTEM),
    }),
    assumptions=(
        "exact at the nodes for constant k and constant q on any grid",
        "second order on smooth data; at a jump in k the error is not second order",
        "the grid ends lie on the slab faces",
    ),
    implementation=ImplementationReference(
        implementation_id="engcore.domains.thermal_models.conduction1d_nonuniform",
        version="0.1.0",
        reference="vertex-centred finite volumes; see module docstring",
    ),
)


def steady_conduction_models() -> ModelRegistry:
    """A fresh registry. No global singleton exists."""
    return ModelRegistry((STEADY_CONDUCTION_MODEL,))


def nonuniform_conduction_realizations() -> RealizationRegistry:
    """A fresh registry. No global singleton exists."""
    return RealizationRegistry((NONUNIFORM_FV_REALIZATION,))


def nonuniform_conduction_solver_capabilities() -> frozenset[SolverCapability]:
    return frozenset({NONUNIFORM_STEADY_CONDUCTION, CoreCapabilities.LINEAR_SYSTEM})


class BoundaryKind(str, Enum):
    TEMPERATURE = "temperature"
    #: heat flux INTO the slab through this face, W/m**2
    INWARD_HEAT_FLUX = "inward_heat_flux"


@dataclass(frozen=True)
class ConductionBoundary:
    """One end's declared condition: an absolute temperature, or an inward heat flux."""

    kind: BoundaryKind
    value: Quantity

    def __post_init__(self) -> None:
        if not isinstance(self.kind, BoundaryKind):
            raise InvalidScientificProblem("a conduction boundary states its kind (temperature or inward heat flux)")
        if not isinstance(self.value, Quantity):
            raise InvalidScientificProblem("a conduction boundary value is a Quantity, never a bare number")
        magnitude = self.si_value()  # refuses a value in the wrong dimension
        if not math.isfinite(magnitude):
            raise InvalidScientificProblem("a conduction boundary value must be finite")
        if self.kind is BoundaryKind.TEMPERATURE and magnitude <= 0.0:
            raise InvalidScientificProblem("a boundary temperature must be above absolute zero")

    def si_value(self) -> float:
        if self.kind is BoundaryKind.TEMPERATURE:
            return float(self.value.magnitude_in("kelvin"))  # absolute: the whole affine map
        return float(self.value.magnitude_in("watt/meter**2"))

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "value": self.value.to_dict()}


@dataclass(frozen=True)
class SteadyConductionProblem:
    """``-(k u')' = q`` on ``[0, length]``.  ``conductivity`` and ``source`` take ``x`` in metres and return SI."""

    length: Quantity
    conductivity: Callable[[float], float]   # W/(m K), strictly positive
    source: Callable[[float], float]         # W/m**3
    left: ConductionBoundary
    right: ConductionBoundary
    description: str

    def __post_init__(self) -> None:
        if not isinstance(self.length, Quantity):
            raise InvalidScientificProblem("the slab length is a Quantity")
        length = float(self.length.magnitude_in("meter"))
        if not (math.isfinite(length) and length > 0.0):
            raise InvalidScientificProblem("the slab length must be finite and positive")
        if not callable(self.conductivity) or not callable(self.source):
            raise InvalidScientificProblem("conductivity and source are functions of position (metres)")
        for label in ("left", "right"):
            if not isinstance(getattr(self, label), ConductionBoundary):
                raise InvalidScientificProblem(
                    f"the {label} boundary condition must be declared; it is never defaulted")
        if (self.left.kind is BoundaryKind.INWARD_HEAT_FLUX
                and self.right.kind is BoundaryKind.INWARD_HEAT_FLUX):
            raise InvalidScientificProblem(
                "two heat-flux ends fix the temperature only up to a constant; declare a temperature at one end")
        if not str(self.description).strip():
            raise InvalidScientificProblem("the problem states what it describes")

    @property
    def length_m(self) -> float:
        return float(self.length.magnitude_in("meter"))

    def to_dict(self) -> dict[str, Any]:
        # the two functions are code, not data: the record names them and does not pretend to serialise them
        return {"length": self.length.to_dict(), "left": self.left.to_dict(), "right": self.right.to_dict(),
                "conductivity": getattr(self.conductivity, "__qualname__", repr(self.conductivity)),
                "source": getattr(self.source, "__qualname__", repr(self.source)),
                "description": self.description}


@dataclass(frozen=True)
class NonUniformConductionSolution:
    grid: Grid1D
    temperatures_k: tuple[float, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"classification": "numerical_solution_not_scientific_evidence",
                "model": {"id": STEADY_CONDUCTION_MODEL.model_id, "version": STEADY_CONDUCTION_MODEL.version},
                "realization": {"id": NONUNIFORM_FV_REALIZATION.realization_id,
                                "version": NONUNIFORM_FV_REALIZATION.version},
                "grid": self.grid.to_dict(),
                "temperatures": {"unit": "kelvin", "values": list(self.temperatures_k)},
                "notice": ("the discrete solution of the declared equation on this grid; its discretisation error is "
                           "not quantified here; not validation")}


def _nodes_in_metres(problem: SteadyConductionProblem, grid: Grid1D) -> np.ndarray:
    if not isinstance(grid, Grid1D):
        raise InvalidScientificProblem("the solver takes a Grid1D")
    scale = float(Quantity(1.0, grid.unit).magnitude_in("meter"))  # a length has no offset
    x = np.asarray(grid.nodes, dtype=float) * scale
    length = problem.length_m
    if abs(x[0]) > _END_TOLERANCE * length or abs(x[-1] - length) > _END_TOLERANCE * length:
        raise InvalidScientificProblem(
            f"the grid spans [{x[0]:.12g}, {x[-1]:.12g}] m, not the slab [0, {length:.12g}] m")
    x[0], x[-1] = 0.0, length
    return x


def _sample(function: Callable[[float], float], points: np.ndarray, label: str) -> np.ndarray:
    values = np.array([float(function(float(p))) for p in points])
    if not np.all(np.isfinite(values)):
        raise InvalidScientificProblem(f"{label} is not finite somewhere on the grid")
    return values


def _thomas(lower: np.ndarray, diagonal: np.ndarray, upper: np.ndarray, rhs: np.ndarray) -> np.ndarray:
    n = diagonal.size
    c, d = np.zeros(n), np.zeros(n)
    c[0], d[0] = upper[0] / diagonal[0], rhs[0] / diagonal[0]
    for i in range(1, n):
        pivot = diagonal[i] - lower[i] * c[i - 1]
        c[i] = upper[i] / pivot if i < n - 1 else 0.0
        d[i] = (rhs[i] - lower[i] * d[i - 1]) / pivot
    u = np.zeros(n)
    u[-1] = d[-1]
    for i in range(n - 2, -1, -1):
        u[i] = d[i] - c[i] * u[i + 1]
    return u


def solve_steady_conduction(problem: SteadyConductionProblem, grid: Grid1D) -> NonUniformConductionSolution:
    """Nodal temperatures (K) of ``problem`` on ``grid`` (see the module docstring)."""
    if not isinstance(problem, SteadyConductionProblem):
        raise InvalidScientificProblem("the solver takes a SteadyConductionProblem")
    x = _nodes_in_metres(problem, grid)
    h = np.diff(x)
    k = _sample(problem.conductivity, 0.5 * (x[:-1] + x[1:]), "conductivity")
    if np.any(k <= 0.0):
        raise InvalidScientificProblem("conductivity must be strictly positive at every cell midpoint")
    q = _sample(problem.source, x, "source")
    conductance = k / h
    volume = np.zeros_like(x)
    volume[:-1] += 0.5 * h
    volume[1:] += 0.5 * h

    n = x.size
    lower, diagonal, upper, rhs = np.zeros(n), np.zeros(n), np.zeros(n), q * volume
    diagonal[:-1] += conductance
    diagonal[1:] += conductance
    upper[:-1] = -conductance
    lower[1:] = -conductance
    for index, boundary in ((0, problem.left), (n - 1, problem.right)):
        value = boundary.si_value()
        if boundary.kind is BoundaryKind.TEMPERATURE:
            lower[index] = upper[index] = 0.0
            diagonal[index], rhs[index] = 1.0, value
        else:
            rhs[index] += value  # an inward flux is a source on the boundary half-cell
    temperatures = _thomas(lower, diagonal, upper, rhs)
    if not np.all(np.isfinite(temperatures)):
        raise InvalidScientificProblem("the discrete conduction system produced a non-finite temperature")
    return NonUniformConductionSolution(grid, tuple(float(t) for t in temperatures))


def temperature_evaluator(problem: SteadyConductionProblem) -> Callable[[Grid1D], tuple[float, ...]]:
    """``grid -> nodal temperatures (K)``: a fresh solve per grid, for ``adapt_grid(..., value_unit="kelvin")``."""
    if not isinstance(problem, SteadyConductionProblem):
        raise InvalidScientificProblem("the evaluator takes a SteadyConductionProblem")

    def evaluate(grid: Grid1D) -> tuple[float, ...]:
        return solve_steady_conduction(problem, grid).temperatures_k

    return evaluate


def adapt_conduction(problem: SteadyConductionProblem, initial: Grid1D, policy: AdaptationPolicy) -> AdaptationRecord:
    """Locally adapt ``initial`` to ``problem``'s solution.  The record is an ESTIMATE, never evidence."""
    return adapt_grid(temperature_evaluator(problem), initial, policy, value_unit="kelvin")


__all__ = [
    "NONUNIFORM_FV_REALIZATION",
    "NONUNIFORM_STEADY_CONDUCTION",
    "STEADY_CONDUCTION_1D",
    "STEADY_CONDUCTION_MODEL",
    "BoundaryKind",
    "ConductionBoundary",
    "NonUniformConductionSolution",
    "SteadyConductionProblem",
    "adapt_conduction",
    "nonuniform_conduction_realizations",
    "nonuniform_conduction_solver_capabilities",
    "solve_steady_conduction",
    "steady_conduction_models",
    "temperature_evaluator",
]
