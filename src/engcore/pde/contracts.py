"""Provider-neutral PDE/FEM problem contracts (BIG 8).

Forge owns the scientific identity of a PDE problem; a provider (FEniCSx
today; CalculiX / Code_Aster / Elmer / OpenFOAM later) owns only assembly and
the numerical solve.  Nothing here imports a provider type.

Four layers are kept apart:

* the DECLARED physical model (:class:`PhysicalModel`) -- a statement, not a proof;
* the OPERATOR TEMPLATE (:class:`OperatorTemplate`) -- a Forge-defined PDE
  form with dimensioned coefficient slots.  Its identity is its content
  (template id, version, slot table), never an opaque caller digest or code;
* the DISCRETIZATION (:class:`DiscretizationSpec`);
* the provider EXECUTION (:class:`PDEExecutionRecord`).

Every scientifically relevant input -- mesh digest, facet roles, coefficient
field digests and their material-resolution provenance, constants with their
declared origin, boundary values with their source records, sources, initial
condition, discretization, solver settings, time window -- enters
:meth:`PDEProblem.identity`.  A solve is numerical; it grants no evidence,
validation or applicability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

import numpy as np

from ..scenarios.timeline import TimePoint, TimeWindow, canonical_digest, exact_seconds
from ..scientific.errors import InvalidScientificProblem
from ..scientific.solvers.protocol import ConvergenceState, SolverIdentity, SolverSettings
from ..scientific.units.quantity import Quantity, dimensionality, is_ratio_scale, normalize_unit
from ..spatial import Derivation, GroupKind, Location, Rank, SpatialField, SpatialFieldDefinition, SpatialMesh
from ..spatial.mesh import _cell_facets


class PDERefusal(InvalidScientificProblem):
    """A PDE problem that cannot be executed as posed without inventing something."""


# --------------------------------------------------------------------------
# Model, operator templates, discretization
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PhysicalModel:
    """What physics is claimed.  Declared by a person or domain; never proven by a solve."""

    model_id: str
    version: str
    statement: str
    assumptions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"model_id": self.model_id, "version": self.version, "statement": self.statement,
                "assumptions": list(self.assumptions), "classification": "declared_model_not_proof"}


@dataclass(frozen=True)
class CoefficientSlot:
    name: str
    reference_unit: str   # dimension the slot requires; values are normalized to it
    required: bool = True

    @property
    def dimension(self) -> str:
        return dimensionality(self.reference_unit)


@dataclass(frozen=True)
class OperatorTemplate:
    """A Forge-defined PDE form.  Providers implement templates; callers cannot supply code."""

    template_id: str
    version: str
    rank: Rank
    unknown_unit: str
    slots: tuple[CoefficientSlot, ...]
    transient: bool
    neumann_unit: str       # unit of the natural (flux/traction) boundary datum
    robin_supported: bool
    weak_form_text: str     # the form as written; auditable, not proof of physics

    def slot(self, name: str) -> CoefficientSlot:
        for s in self.slots:
            if s.name == name:
                return s
        raise PDERefusal(f"operator {self.template_id} has no coefficient slot {name!r}")

    def to_dict(self) -> dict[str, Any]:
        return {"template_id": self.template_id, "version": self.version, "rank": self.rank.value, "unknown_unit": self.unknown_unit,
                "slots": [[s.name, normalize_unit(s.reference_unit), s.required] for s in self.slots], "transient": self.transient,
                "neumann_unit": normalize_unit(self.neumann_unit), "robin_supported": self.robin_supported, "weak_form_text": self.weak_form_text}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())


STEADY_DIFFUSION = OperatorTemplate(
    "scalar_diffusion_steady", "1", Rank.SCALAR, "kelvin",
    (CoefficientSlot("conductivity", "W/(m*K)"), CoefficientSlot("source", "W/m^3", required=False)),
    False, "W/m^2", True,
    "find u: int k grad(u).grad(v) dx + int_R h u v ds = int f v dx + int_N g v ds + int_R h u_inf v ds",
)
TRANSIENT_DIFFUSION = OperatorTemplate(
    "scalar_diffusion_transient", "1", Rank.SCALAR, "kelvin",
    (CoefficientSlot("conductivity", "W/(m*K)"), CoefficientSlot("volumetric_heat_capacity", "J/(m^3*K)"),
     CoefficientSlot("source", "W/m^3", required=False)),
    True, "W/m^2", True,
    "backward Euler: int c (u - u_prev)/dt v dx + int k grad(u).grad(v) dx + int_R h u v ds = int f v dx + int_N g v ds + int_R h u_inf v ds",
)
PLANE_STRESS_ELASTICITY = OperatorTemplate(
    "linear_elasticity_plane_stress", "1", Rank.VECTOR, "meter",
    (CoefficientSlot("youngs_modulus", "Pa"), CoefficientSlot("poisson_ratio", "dimensionless"),
     CoefficientSlot("thickness", "m")),
    False, "Pa", False,
    "find u: int t sigma(u):eps(v) dx = int_N t g.v ds, sigma = E/(1-nu^2)[(1-nu) eps + nu tr(eps) I] (plane stress)",
)
TEMPLATES = {t.template_id: t for t in (STEADY_DIFFUSION, TRANSIENT_DIFFUSION, PLANE_STRESS_ELASTICITY)}


@dataclass(frozen=True)
class DiscretizationSpec:
    family: str = "lagrange"
    degree: int = 1
    geometry_order: int = 1
    quadrature_degree: int | None = None
    stabilization: str = "none"

    def __post_init__(self) -> None:
        if self.family != "lagrange" or self.degree not in (1, 2) or self.geometry_order != 1 or self.stabilization != "none":
            raise PDERefusal("supported discretization: continuous Lagrange P1/P2 on affine triangles, no stabilization")

    def to_dict(self) -> dict[str, Any]:
        return {"family": self.family, "degree": self.degree, "geometry_order": self.geometry_order,
                "quadrature_degree": self.quadrature_degree, "stabilization": self.stabilization}


# --------------------------------------------------------------------------
# Facet roles, coefficients, boundary conditions
# --------------------------------------------------------------------------


class FacetRole(str, Enum):
    EXTERNAL_BOUNDARY = "external_boundary"
    INTERNAL_INTERFACE = "internal_interface"
    OTHER = "other"


class BCKind(str, Enum):
    DIRICHLET = "dirichlet"
    NEUMANN = "neumann"
    ROBIN = "robin"


@dataclass(frozen=True)
class SourcedQuantity:
    """A value plus the record it came from.  Anonymous constants are refused."""

    value: Quantity
    origin: str            # "material_resolution" | "environment" | "prescribed" | "assumed"
    source_record: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.value, Quantity):
            raise PDERefusal("a sourced quantity needs a Quantity")
        if self.origin not in ("material_resolution", "environment", "prescribed", "assumed"):
            raise PDERefusal(f"unsupported origin {self.origin!r}")
        if not self.source_record:
            raise PDERefusal("a value with no source record is an anonymous constant; refused")

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value.to_dict(), "origin": self.origin, "source_record_digest": canonical_digest(dict(self.source_record))}


@dataclass(frozen=True)
class CoefficientBinding:
    """A slot filled by a RESOLVED cell field (material provenance kept) or a sourced constant."""

    slot: str
    field: SpatialField | None = None
    constant: SourcedQuantity | None = None

    def __post_init__(self) -> None:
        if (self.field is None) == (self.constant is None):
            raise PDERefusal(f"coefficient {self.slot!r} needs exactly one of a field or a sourced constant")
        if self.field is not None:
            f = self.field
            if f.definition.location is not Location.CELL or f.definition.rank is not Rank.SCALAR:
                raise PDERefusal(f"coefficient field for {self.slot!r} must be a scalar cell field")
            if f.derivation not in (Derivation.RESOLVED, Derivation.PRESCRIBED, Derivation.ASSUMED):
                raise PDERefusal(f"coefficient {self.slot!r} derivation {f.derivation.value} is not a declared input")

    @property
    def unit(self) -> str:
        return self.field.definition.unit if self.field is not None else self.constant.value.units

    def normalized_cell_values(self, mesh: SpatialMesh, reference_unit: str) -> np.ndarray:
        if dimensionality(self.unit) != dimensionality(reference_unit):
            raise PDERefusal(f"coefficient {self.slot!r} is in {self.unit}; slot requires the dimension of {reference_unit}")
        if not is_ratio_scale(self.unit):
            raise PDERefusal(f"coefficient {self.slot!r} uses an affine unit")
        factor = Quantity(1.0, self.unit).magnitude_in(reference_unit)
        if self.field is not None:
            if self.field.mesh.digest != mesh.digest:
                raise PDERefusal(f"coefficient field {self.slot!r} is on a different mesh")
            return np.asarray(self.field.values) * factor
        return np.full(mesh.cell_count, self.constant.value.magnitude * factor)

    def to_dict(self) -> dict[str, Any]:
        return {"slot": self.slot, "field_digest": None if self.field is None else self.field.digest,
                "field_provenance": None if self.field is None else list(self.field.provenance),
                "field_derivation": None if self.field is None else self.field.derivation.value,
                "constant": None if self.constant is None else self.constant.to_dict()}


@dataclass(frozen=True)
class BoundaryCondition:
    kind: BCKind
    group: str
    value: SourcedQuantity                   # Dirichlet: unknown unit; Neumann: flux/traction; Robin: ambient (unknown unit)
    coefficient: SourcedQuantity | None = None  # Robin h
    components: tuple[int, ...] | None = None   # vector Dirichlet: which components are fixed (all if None)
    vector_value: tuple[Quantity, ...] | None = None  # vector Neumann traction components

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", BCKind(self.kind))
        if (self.kind is BCKind.ROBIN) != (self.coefficient is not None):
            raise PDERefusal("Robin conditions (and only Robin conditions) carry a transfer coefficient")

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "group": self.group, "value": self.value.to_dict(),
                "coefficient": None if self.coefficient is None else self.coefficient.to_dict(),
                "components": None if self.components is None else list(self.components),
                "vector_value": None if self.vector_value is None else [q.to_dict() for q in self.vector_value]}


# --------------------------------------------------------------------------
# Transient specification
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TransientSpec:
    """BIG 2 owns the window, breakpoints and output instants; the provider only steps inside."""

    window: TimeWindow
    step: Quantity
    initial: SourcedQuantity
    output_times: tuple[Quantity, ...]
    breakpoints: tuple[Quantity, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.window, TimeWindow):
            raise PDERefusal("a transient PDE needs a BIG 2 TimeWindow")
        start, end = self.window.start.seconds, self.window.end.seconds
        dt = exact_seconds(self.step, "time step")
        if dt <= 0:
            raise PDERefusal("time step must be positive")
        for label, times in (("output time", self.output_times), ("breakpoint", self.breakpoints)):
            for t in times:
                s = exact_seconds(t, label)
                if not start < s <= end:
                    raise PDERefusal(f"{label} {float(s)} s is outside the authorized window (start, end]")
        edges = sorted({start, end, *(exact_seconds(b) for b in self.breakpoints)})
        for a, b in zip(edges, edges[1:]):
            n = (b - a) / dt
            if n.denominator != 1:
                raise PDERefusal(f"segment [{float(a)}, {float(b)}] s is not an integer number of steps; steps may not straddle a breakpoint")
        outs = {exact_seconds(t) for t in self.output_times}
        for t in outs:
            if ((t - start) / dt).denominator != 1:
                raise PDERefusal(f"output time {float(t)} s is not on the step grid; interpolating in time would invent a state")

    def segments(self) -> list[tuple[float, float]]:
        edges = sorted({self.window.start.seconds, self.window.end.seconds, *(exact_seconds(b) for b in self.breakpoints)})
        return [(float(a), float(b)) for a, b in zip(edges, edges[1:])]

    def to_dict(self) -> dict[str, Any]:
        return {"window": self.window.to_dict(), "step": self.step.to_dict(), "initial": self.initial.to_dict(),
                "output_times": [t.to_dict() for t in self.output_times], "breakpoints": [b.to_dict() for b in self.breakpoints]}


# --------------------------------------------------------------------------
# Problem
# --------------------------------------------------------------------------


def facet_cell_counts(mesh: SpatialMesh) -> dict[tuple[int, ...], int]:
    all_f = np.sort(_cell_facets(mesh.cell_type, mesh.cells), axis=1)
    keys, counts = np.unique(all_f, axis=0, return_counts=True)
    return {tuple(int(v) for v in k): int(c) for k, c in zip(keys, counts)}


@dataclass(frozen=True)
class PDEProblem:
    problem_id: str
    mesh: SpatialMesh
    model: PhysicalModel
    operator: OperatorTemplate
    unknown: SpatialFieldDefinition
    coefficients: tuple[CoefficientBinding, ...]
    boundary_conditions: tuple[BoundaryCondition, ...]
    facet_roles: Mapping[str, FacetRole]
    discretization: DiscretizationSpec
    solver: SolverSettings
    transient: TransientSpec | None = None
    boundary_schedule: Mapping[str, tuple[tuple[float, SourcedQuantity], ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        m, op = self.mesh, self.operator
        if m.cell_type.value != "triangle":
            raise PDERefusal("BIG 8 supports 2D triangle meshes only; other cell types are refused, not approximated")
        if op.template_id not in TEMPLATES or TEMPLATES[op.template_id] != op:
            raise PDERefusal("operators must be Forge templates; a modified or foreign template is refused")
        u = self.unknown
        if u.location is not Location.NODE or u.rank is not op.rank:
            raise PDERefusal(f"unknown must be a {op.rank.value} node field")
        if dimensionality(u.unit) != dimensionality(op.unknown_unit) or not is_ratio_scale(u.unit):
            raise PDERefusal(f"unknown unit {u.unit} must be a ratio-scale unit of {op.unknown_unit} (no Celsius inside the solve)")
        if u.rank is Rank.VECTOR and u.frame_id != m.frame.frame_id:
            raise PDERefusal("vector unknown must be expressed in the mesh frame")
        if (self.transient is not None) != op.transient:
            raise PDERefusal("transient operators require (and only they accept) a TransientSpec")
        # coefficients
        bound = {c.slot: c for c in self.coefficients}
        if len(bound) != len(self.coefficients):
            raise PDERefusal("a coefficient slot is bound twice")
        for s in op.slots:
            if s.required and s.name not in bound:
                raise PDERefusal(f"required coefficient {s.name!r} is not bound; it is never defaulted")
        for name, c in bound.items():
            c.normalized_cell_values(m, op.slot(name).reference_unit)  # dimension/mesh check now
            if c.field is not None and not np.all(np.isfinite(c.field.values)):
                raise PDERefusal(f"coefficient {name!r} has non-finite values")
        # facet roles checked against topology
        groups = {g.name: g for g in m.groups if g.kind is GroupKind.FACETS}
        counts = facet_cell_counts(m)
        for name, role in dict(self.facet_roles).items():
            if name not in groups:
                raise PDERefusal(f"facet group {name!r} is not declared on this mesh")
            idx = m.facet_indices(m.region(name))
            owners = {counts[tuple(int(v) for v in m.facets[i])] for i in idx}
            role = FacetRole(role)
            if role is FacetRole.EXTERNAL_BOUNDARY and owners != {1}:
                raise PDERefusal(f"group {name!r} is declared external but has facets shared by two cells")
            if role is FacetRole.INTERNAL_INTERFACE and owners != {2}:
                raise PDERefusal(f"group {name!r} is declared an interface but has facets on the outer boundary")
        # boundary conditions
        used = set()
        for bc in self.boundary_conditions:
            if bc.group not in dict(self.facet_roles):
                raise PDERefusal(f"boundary condition on {bc.group!r} without a declared facet role; ambiguous use refused")
            if FacetRole(self.facet_roles[bc.group]) is not FacetRole.EXTERNAL_BOUNDARY:
                raise PDERefusal(f"Dirichlet/Neumann/Robin conditions apply to external boundaries; {bc.group!r} is not one")
            if bc.group in used:
                raise PDERefusal(f"group {bc.group!r} carries two boundary conditions")
            used.add(bc.group)
            self._check_bc_units(bc)
        covered = set()
        for bc in self.boundary_conditions:
            for i in m.facet_indices(m.region(bc.group)):
                covered.add(tuple(int(v) for v in m.facets[i]))
        outer = {k for k, c in counts.items() if c == 1}
        if outer - covered:
            raise PDERefusal(
                f"{len(outer - covered)} outer boundary facet(s) have no declared condition; a natural (zero-flux) "
                f"condition is never implied -- declare it as a Neumann condition with its source"
            )
        if not any(bc.kind in (BCKind.DIRICHLET, BCKind.ROBIN) for bc in self.boundary_conditions):
            raise PDERefusal("no Dirichlet or Robin condition: the operator is singular (pure Neumann is not supported)")
        for name, schedule in dict(self.boundary_schedule).items():
            if self.transient is None or name not in used:
                raise PDERefusal("a boundary schedule needs a transient problem and a boundary condition on that group")
            for _, sq in schedule:
                dimensionality(sq.value.units)  # parse
        self._check_solver()

    def _check_bc_units(self, bc: BoundaryCondition) -> None:
        op = self.operator
        if bc.kind is BCKind.DIRICHLET or bc.kind is BCKind.ROBIN:
            if dimensionality(bc.value.value.units) != dimensionality(op.unknown_unit):
                raise PDERefusal(f"{bc.kind.value} value on {bc.group!r} is {bc.value.value.units}; the unknown is {op.unknown_unit}")
        if bc.kind is BCKind.NEUMANN:
            q = bc.vector_value or (bc.value.value,)
            for c in q:
                if dimensionality(c.units) != dimensionality(op.neumann_unit):
                    raise PDERefusal(f"Neumann datum on {bc.group!r} is {c.units}; the operator's natural datum is {op.neumann_unit}")
        if bc.kind is BCKind.ROBIN:
            if not op.robin_supported:
                raise PDERefusal(f"operator {op.template_id} does not support Robin conditions")
            if dimensionality(bc.coefficient.value.units) != dimensionality("W/(m^2*K)"):
                raise PDERefusal("Robin transfer coefficient must be a heat transfer coefficient")

    def _check_solver(self) -> None:
        t = self.solver.tolerances
        o = self.solver.options
        for key in ("rtol", "residual_rtol"):
            if key not in t:
                raise PDERefusal(f"solver tolerance {key!r} is required; none is defaulted")
        for key in ("ksp_type", "pc_type", "max_iterations"):
            if key not in o:
                raise PDERefusal(f"solver option {key!r} is required; none is defaulted")

    def dirichlet_value(self, bc: BoundaryCondition) -> float:
        return bc.value.value.to(normalize_unit(self.operator.unknown_unit)).magnitude

    def identity(self) -> dict[str, Any]:
        return {
            "problem_id": self.problem_id, "mesh": self.mesh.digest, "model": self.model.to_dict(),
            "operator": self.operator.to_dict(), "operator_digest": self.operator.digest, "unknown": self.unknown.to_dict(),
            "coefficients": sorted((c.to_dict() for c in self.coefficients), key=lambda d: d["slot"]),
            "boundary_conditions": sorted((b.to_dict() for b in self.boundary_conditions), key=lambda d: d["group"]),
            "facet_roles": {k: FacetRole(v).value for k, v in sorted(dict(self.facet_roles).items())},
            "discretization": self.discretization.to_dict(), "solver": self.solver.to_dict(),
            "transient": None if self.transient is None else self.transient.to_dict(),
            "boundary_schedule": {k: [[t, sq.to_dict()] for t, sq in v] for k, v in sorted(dict(self.boundary_schedule).items())},
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.identity())


# --------------------------------------------------------------------------
# Execution record
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PDEDiagnostics:
    ksp_iterations: tuple[int, ...] = ()
    ksp_reasons: tuple[int, ...] = ()
    relative_true_residuals: tuple[float, ...] = ()
    steps: int = 0
    dofs: int = 0
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"ksp_iterations": list(self.ksp_iterations), "ksp_reasons": list(self.ksp_reasons),
                "relative_true_residuals": list(self.relative_true_residuals), "steps": self.steps, "dofs": self.dofs,
                "warnings": list(self.warnings)}


@dataclass(frozen=True)
class PDEExecutionRecord:
    problem_digest: str
    provider: SolverIdentity
    convergence: ConvergenceState
    diagnostics: PDEDiagnostics
    fields: tuple[tuple[float, SpatialField], ...]   # (time seconds or 0 for steady, field)
    reason: str = ""

    def __post_init__(self) -> None:
        ok = self.convergence in (ConvergenceState.CONVERGED, ConvergenceState.NOT_APPLICABLE)
        if not ok and self.fields:
            raise PDERefusal("a failed PDE execution exposes no fields; the last iterate is withheld")
        if ok and not self.fields:
            raise PDERefusal("a successful PDE execution must return its fields")

    @property
    def succeeded(self) -> bool:
        return bool(self.fields)

    @property
    def execution_identity(self) -> str:
        return canonical_digest({"problem": self.problem_digest, "provider": self.provider.to_dict()})

    @property
    def field(self) -> SpatialField:
        if not self.fields:
            raise PDERefusal(f"execution failed: {self.reason}")
        return self.fields[-1][1]

    def to_dict(self) -> dict[str, Any]:
        return {"classification": "pde_execution_not_scientific_evidence", "execution_identity": self.execution_identity,
                "problem_digest": self.problem_digest, "provider": self.provider.to_dict(), "convergence": self.convergence.value,
                "diagnostics": self.diagnostics.to_dict(), "fields": [[t, f.digest] for t, f in self.fields], "reason": self.reason}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())


def computed_field(problem: PDEProblem, values: Any, execution_identity: str) -> SpatialField:
    return SpatialField(problem.unknown, problem.mesh, values, Derivation.COMPUTED, (execution_identity, problem.digest))
