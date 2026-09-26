"""FLAGSHIP B - a heated aluminium plate: temperature -> thermal expansion -> displacement and stress, three structural providers.

Engineering question
    A plate carries a heat load into one end and rejects it at the other.  How does its temperature field deform it, how
    hard does a restraint have to push back, and do independent structural solvers agree on the answer?

Physical system (a symmetric half of a plate, plane stress, thickness ``THICKNESS``)
    x = 0        heat input ``q`` (W/m^2) - Neumann;         x = L   held at ``T_COLD`` - Dirichlet
    y = 0        symmetry (adiabatic, u_y = 0);              y = W/2 adiabatic and traction free
    structure    ``constrained``: rollers at both ends (u_x = 0 on x = 0 and x = L) - the plate cannot lengthen, so it is compressed
                 ``free_roller``: a roller at x = 0 only - the plate grows freely; with a UNIFORM temperature the exact solution has ZERO stress

BIG 12 request
    thermal (FEniCSx steady conduction) -> struct_fenicsx / struct_calculix / struct_code_aster (same mesh, same temperature field, same
    material records) -> cross-provider comparison nodes.  Bulk fields travel outside the request (an in-process exchange keyed by the
    producer's execution identity); only scalars and digests are request-visible.

Material properties are ILLUSTRATIVE typical values for 6061 aluminium declared as ASSUMED records: not from a controlled datasheet and not
measured.  This flagship demonstrates coupled thermo-mechanical execution, verification against exact limits, discretisation
convergence and independent-solver corroboration.  It validates nothing physical.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from engcore.materials import MaterialIdentity, MaterialState
from engcore.materials.properties import PropertyDerivation, ResolvedProperty
from engcore.scenarios import NamedQuantity
from engcore.scientific.units.quantity import Quantity
from engcore.spatial import Location, Rank, SpatialField, SpatialFieldDefinition
from engcore.spatial.fields import Derivation
from engcore.spatial.mesh import CellType, CoordinateFrame, GroupKind, PhysicalGroup, SpatialMesh

LENGTH = 0.2            # m
HALF_WIDTH = 0.02       # m, modelled half-width (the full plate is 40 mm wide, symmetric about y = 0)
THICKNESS = Quantity(5, "mm")
T_REF = 293.15          # K, stress-free temperature (DECLARED)
T_COLD = 303.15         # K, sink end
FLUX = 40000.0          # W/m^2 heat input at x = 0
K_COND = 167.0          # W/(m K)   ILLUSTRATIVE
E_MOD = 68.9e9          # Pa        ILLUSTRATIVE
NU = 0.33               #           ILLUSTRATIVE
ALPHA = 23.6e-6         # 1/K       ILLUSTRATIVE
PROPERTY_RANGE_K = (250.0, 450.0)   # DECLARED validity range of the constant property records
YIELD_PA = 275e6        # ILLUSTRATIVE yield strength used only for the stress constraint
SAFETY_FACTOR = 2.0


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# ==================================================================================================== mesh (BIG 7)
def plate_mesh(nx: int, ny: int, *, length: float = LENGTH, half_width: float = HALF_WIDTH) -> SpatialMesh:
    """Structured right-diagonal triangles on [0, L] x [0, W/2].  Cells: ``plate`` (1).  Facets: left 11, right 12, bottom 13, top 14."""
    xs, ys = np.linspace(0.0, length, nx + 1), np.linspace(0.0, half_width, ny + 1)
    coords = np.array([(x, y) for y in ys for x in xs])
    node = lambda i, j: j * (nx + 1) + i  # noqa: E731
    cells = []
    for j in range(ny):
        for i in range(nx):
            n00, n10, n11, n01 = node(i, j), node(i + 1, j), node(i + 1, j + 1), node(i, j + 1)
            cells += [(n00, n10, n11), (n00, n11, n01)]
    facets, tags = [], []
    for j in range(ny):
        facets.append((node(0, j), node(0, j + 1))); tags.append(11)
        facets.append((node(nx, j), node(nx, j + 1))); tags.append(12)
    for i in range(nx):
        facets.append((node(i, 0), node(i + 1, 0))); tags.append(13)
        facets.append((node(i, ny), node(i + 1, ny))); tags.append(14)
    groups = (PhysicalGroup("plate", GroupKind.CELLS, 1), PhysicalGroup("left", GroupKind.FACETS, 11), PhysicalGroup("right", GroupKind.FACETS, 12),
              PhysicalGroup("bottom", GroupKind.FACETS, 13), PhysicalGroup("top", GroupKind.FACETS, 14))
    return SpatialMesh(coordinates=coords, cells=np.array(cells), cell_type=CellType.TRIANGLE, frame=CoordinateFrame("plate-xy", 2, description="plate plane"),
                       cell_tags=np.ones(len(cells), dtype=int), facets=np.array(facets), facet_tags=np.array(tags), groups=groups)


# ==================================================================================================== materials (BIG 5): ASSUMED records
@dataclass(frozen=True)
class PlateMaterial:
    state: MaterialState
    youngs: ResolvedProperty
    poisson: ResolvedProperty
    expansion: ResolvedProperty
    conductivity: ResolvedProperty


def plate_material(*, youngs=E_MOD, poisson=NU, alpha=ALPHA, k=K_COND) -> PlateMaterial:
    state = MaterialState(MaterialIdentity("aluminium", grade="6061"))
    # the declared assumption DOCUMENT (its content is right here) is what the records' assumption identities digest - not a label
    document = {"statement": "illustrative typical values for 6061 aluminium; NOT from a controlled datasheet and NOT measured", "youngs_modulus_Pa": youngs, "poisson_ratio": poisson,
                "thermal_expansion_1_per_K": alpha, "thermal_conductivity_W_per_mK": k, "declared_validity_range_K": list(PROPERTY_RANGE_K)}
    from engcore.system_runtime._common import digest_of as _d
    doc = _d(document)

    def rec(pid, value, unit):
        return ResolvedProperty(pid, "known", PropertyDerivation.ASSUMED, NamedQuantity(pid, Quantity(value, unit)), doc, _d({"snapshot": document, "property": pid}),
                                state.digest, (_d({"assumption": document, "property": pid}),), ("assumed",), (), None)
    return PlateMaterial(state, rec("youngs_modulus", youngs, "Pa"), rec("poisson_ratio", poisson, "dimensionless"), rec("thermal_expansion", alpha, "1/K"),
                         rec("thermal_conductivity", k, "W/(m*K)"))


def node_field(name: str, quantity: str, unit: str, mesh: SpatialMesh, values, provenance: tuple[str, ...]) -> SpatialField:
    return SpatialField(SpatialFieldDefinition(name, quantity, unit, Location.NODE, Rank.SCALAR), mesh, np.asarray(values, dtype=float), Derivation.COMPUTED, provenance)


# ==================================================================================================== exact solutions (independent of every provider)
def linear_temperature(x: np.ndarray, flux: float = FLUX, k: float = K_COND, length: float = LENGTH, t_cold: float = T_COLD) -> np.ndarray:
    """Steady 1-D conduction with flux q in at x = 0 and T = T_cold at x = L:  T(x) = T_cold + q (L - x) / k."""
    return t_cold + flux * (length - np.asarray(x)) / k


def uniform_constrained_stress(t_uniform: float, e: float = E_MOD, alpha: float = ALPHA, t_ref: float = T_REF) -> float:
    """Exact axial stress of a plane-stress plate held between two rollers at a UNIFORM temperature: sigma_xx = -E alpha (T - T_ref)."""
    return -e * alpha * (t_uniform - t_ref)


# ==================================================================================================== cases
@dataclass(frozen=True)
class StructCase:
    name: str
    flux: float                 # W/m^2 into x = 0
    t_cold: float               # K at x = L
    support: str                # "constrained" (rollers at both ends) | "free_roller" (roller at x = 0 only)
    nx: int
    ny: int
    description: str = ""


STRUCT_CASES = {
    "flagship": StructCase("flagship", FLUX, T_COLD, "constrained", 80, 16, "40 kW/m2 into one end, 30 degC sink end, rollers at both ends"),
    "over_range": StructCase("over_range", 6 * FLUX, T_COLD, "constrained", 40, 8, "a heat load that drives the plate above the declared property range"),
    "uniform_free": StructCase("uniform_free", 0.0, 333.15, "free_roller", 20, 4, "uniform 60 degC, free to expand: exact u = alpha dT (x, y), zero stress"),
    "uniform_constrained": StructCase("uniform_constrained", 0.0, 333.15, "constrained", 20, 4, "uniform 60 degC between rollers: exact sigma_xx = -E alpha dT"),
}


# ==================================================================================================== provider problems
def _sq(q: Quantity, why: str, origin: str = "prescribed", **record):
    from engcore.pde import SourcedQuantity
    return SourcedQuantity(q, origin, {"declared": why, **record})


def _solver():
    from engcore.scientific.solvers.protocol import SolverSettings
    return SolverSettings({"rtol": 1e-12, "residual_rtol": 1e-9}, {"ksp_type": "preonly", "pc_type": "lu", "max_iterations": 1})


def _roles():
    from engcore.pde import FacetRole
    return {g: FacetRole.EXTERNAL_BOUNDARY for g in ("left", "right", "bottom", "top")}


def restraints_for(case: StructCase):
    from engcore.pde.cases import Restraint
    base = (Restraint("left", (0,)), Restraint("bottom", (1,)))
    return base + (Restraint("right", (0,)),) if case.support == "constrained" else base


def thermal_pde_problem(mesh, mat: PlateMaterial, case: StructCase):
    from engcore.pde import STEADY_DIFFUSION, BCKind, BoundaryCondition, CoefficientBinding, DiscretizationSpec, PDEProblem, PhysicalModel
    zero = _sq(Quantity(0.0, "W/m^2"), "adiabatic edge")
    return PDEProblem(
        f"plate-conduction-{case.name}", mesh, PhysicalModel("heat.plate_conduction", "1", "steady conduction, 2-D per unit thickness, constant conductivity"),
        STEADY_DIFFUSION, SpatialFieldDefinition("T", "temperature", "K", Location.NODE, Rank.SCALAR),
        (CoefficientBinding("conductivity", constant=_sq(mat.conductivity.value.value, "conductivity", "material_resolution", record=mat.conductivity.digest)),),
        (BoundaryCondition(BCKind.NEUMANN, "left", _sq(Quantity(case.flux, "W/m^2"), "heat input flux")),
         BoundaryCondition(BCKind.DIRICHLET, "right", _sq(Quantity(case.t_cold, "K"), "sink temperature")),
         BoundaryCondition(BCKind.NEUMANN, "top", zero), BoundaryCondition(BCKind.NEUMANN, "bottom", zero)),
        _roles(), DiscretizationSpec(degree=1), _solver())


def structural_pde_problem(mesh, mat: PlateMaterial, case: StructCase, temperature: SpatialField):
    from engcore.pde import THERMOELASTIC_PLANE_STRESS, BCKind, BoundaryCondition, CoefficientBinding, DiscretizationSpec, PDEProblem, PhysicalModel
    rec = lambda r: {"record": r.digest}  # noqa: E731
    free = _sq(Quantity(0.0, "Pa"), "traction free")
    zero_t = (Quantity(0, "Pa"), Quantity(0, "Pa"))
    roller = lambda g, comps: BoundaryCondition(BCKind.DIRICHLET, g, _sq(Quantity(0.0, "m"), "roller restraint"), components=comps)  # noqa: E731
    bcs = [roller("left", (0,)), roller("bottom", (1,)), BoundaryCondition(BCKind.NEUMANN, "top", free, vector_value=zero_t)]
    bcs.append(roller("right", (0,)) if case.support == "constrained" else BoundaryCondition(BCKind.NEUMANN, "right", free, vector_value=zero_t))
    return PDEProblem(
        f"plate-thermoelastic-{case.name}", mesh, PhysicalModel("solid.thermoelastic", "1", "small strain, isotropic linear thermal expansion, plane stress"),
        THERMOELASTIC_PLANE_STRESS, SpatialFieldDefinition("u", "displacement", "m", Location.NODE, Rank.VECTOR, frame_id="plate-xy"),
        (CoefficientBinding("youngs_modulus", constant=_sq(mat.youngs.value.value, "E", "material_resolution", **rec(mat.youngs))),
         CoefficientBinding("poisson_ratio", constant=_sq(mat.poisson.value.value, "nu", "material_resolution", **rec(mat.poisson))),
         CoefficientBinding("thickness", constant=_sq(THICKNESS, "plate thickness")),
         CoefficientBinding("thermal_expansion", constant=_sq(mat.expansion.value.value, "alpha", "material_resolution", **rec(mat.expansion))),
         CoefficientBinding("reference_temperature", constant=_sq(Quantity(T_REF, "K"), "stress-free temperature"))),
        tuple(bcs), _roles(), DiscretizationSpec(degree=1), _solver(), field_inputs={"temperature": temperature})


def thermoelastic_case(mesh, mat: PlateMaterial, case: StructCase, temperature: SpatialField):
    from engcore.pde.cases import RegionExpansion, RegionMaterial, ThermoelasticPlaneStressProblem
    return ThermoelasticPlaneStressProblem(
        mesh, (RegionMaterial("plate", mat.youngs, mat.poisson),), (RegionExpansion("plate", mat.expansion),), THICKNESS, restraints_for(case),
        tuple(float(v) for v in temperature.values), temperature.definition.unit, temperature.digest, Quantity(T_REF, "K"))


# ==================================================================================================== quantities of interest
def element_stress_of(mesh, mat: PlateMaterial, u, temperature):
    from engcore.pde.postprocess import plane_stress_recovery
    return plane_stress_recovery(mesh, u, mat.youngs.value.value.to("Pa").magnitude, mat.poisson.value.value.to("dimensionless").magnitude,
                                 mat.expansion.value.value.to("1/K").magnitude, np.asarray(temperature, dtype=float), T_REF)


def section_forces(mesh, sxx: np.ndarray, fractions=(0.25, 0.5, 0.75)) -> list[float]:
    from engcore.pde.postprocess import cross_section_force
    return [cross_section_force(mesh, sxx, f * LENGTH, THICKNESS.to("m").magnitude, HALF_WIDTH) for f in fractions]


def structural_qoi(mesh, mat: PlateMaterial, u, temperature, native_sigma=None) -> dict[str, Quantity]:
    """Scalar quantities of interest.  Stress is the provider's own where it exports one, else recovered from its displacement."""
    from engcore.pde.postprocess import ElementStress
    u = np.asarray(u, dtype=float)
    rec = element_stress_of(mesh, mat, u, temperature)
    cells = np.asarray(mesh.cells, dtype=int)
    cx = np.asarray(mesh.coordinates)[cells][:, :, 0].mean(axis=1)
    mid = (cx >= 0.4 * LENGTH) & (cx <= 0.6 * LENGTH)
    if native_sigma is not None:
        s = np.asarray(native_sigma, dtype=float)
        sxx, syy, sxy = s[:, 0], s[:, 1], s[:, 2]
        vm = np.sqrt(np.maximum(sxx**2 - sxx * syy + syy**2 + 3 * sxy**2, 0.0))
    else:
        sxx, vm = rec.sxx, rec.von_mises
    area = rec.area
    forces = section_forces(mesh, sxx)
    nx = int(round(LENGTH / (np.asarray(mesh.coordinates)[1, 0] - np.asarray(mesh.coordinates)[0, 0])))
    out = {"ux_max": Quantity(float(np.abs(u[:, 0]).max()), "m"), "disp_max": Quantity(float(np.linalg.norm(u, axis=1).max()), "m"),
           "ux_mid": Quantity(float(u[nx // 2, 0]), "m"), "sxx_mid": Quantity(float((sxx[mid] * area[mid]).sum() / area[mid].sum()), "Pa"),
           "vm_max": Quantity(float(vm.max()), "Pa"),
           "section_force_spread": Quantity(float((max(forces) - min(forces)) / max(abs(np.mean(forces)), FORCE_FLOOR_RATIO * FORCE_SCALE)), "dimensionless"),
           "section_force_ratio": Quantity(float(abs(np.mean(forces)) / FORCE_SCALE), "dimensionless")}
    if native_sigma is not None:
        scale = max(float(np.abs(rec.sxx).max()), 1.0)
        out["recovery_check"] = Quantity(float(np.abs(sxx - rec.sxx).max() / scale), "dimensionless")
    return out


class Exchange:
    """Bulk objects that must not travel inside a record: temperature fields and provider records, keyed by the producing node's execution identity."""

    def __init__(self) -> None:
        self.temperature: dict[str, SpatialField] = {}
        self.records: dict[str, Any] = {}
        self.solutions: dict[str, dict[str, Any]] = {}
        self.files: dict[str, bytes] = {}
        self.comparisons: dict[str, Any] = {}


PROP_OUT = (("ux_max", "m"), ("disp_max", "m"), ("ux_mid", "m"), ("sxx_mid", "Pa"), ("vm_max", "Pa"), ("section_force_spread", "dimensionless"),
            ("section_force_ratio", "dimensionless"))


# ==================================================================================================== the BIG 12 system
from engcore.engineering import (  # noqa: E402
    EnvelopeBound, EvidenceLink, LevelEntry, LevelStatus, PredeclaredCriterion, ReferenceCondition, ReferenceRecord, UncertaintyStatement,
    VerificationLadder, build_summary, compare_to_reference, contract_integrity_entry, write_vtu,
)
from engcore.scenarios import ScenarioSegment, ScenarioSpecification, TimeBasis, Timeline  # noqa: E402
from engcore.scientific.ir.constraints import ConstraintDefinition, ConstraintOperator  # noqa: E402
from engcore.scientific.oracles import OracleKind  # noqa: E402
from engcore.scientific.results.uncertainty import Uncertainty  # noqa: E402
from engcore.scientific.twins import ScientificTwin, TwinKind  # noqa: E402
from engcore.system_runtime import (  # noqa: E402
    ApplicabilityReport, ArtifactRef, AuthorityRegistry, CallbackAuthority, ConstraintObservation, ExecutionProfile, InitialStateSpec, MaterialPropertyRef,
    ModelSelection, NodeInput, NodeKind, NodeOutcome, NodeOutputSpec, NodeSpec, OutputValue, OwnerState, ProviderBinding, ProviderRecordRef, RequestedObservable,
    RuntimeContext, SystemRunRequest,
)
from engcore.system_runtime._common import digest_of  # noqa: E402
from engcore.systems import ComponentDefinition, ComponentInstance, ConstraintBinding, SystemDefinition  # noqa: E402
from engcore.execution.multiphysics import InitialStateValue  # noqa: E402

UNKNOWN = Uncertainty.unknown("declared or derived quantity; no uncertainty was quantified")
VM_ALLOWABLE_PA = YIELD_PA / SAFETY_FACTOR
DISP_LIMIT_M = 100e-6
# ---- criteria fixed BEFORE any run (see docs/flagships/thermo_mechanical_structure.md): scales come from the declared inputs only
DT_RANGE = FLUX * LENGTH / K_COND                          # K, exact temperature drop of the flagship plate
U_SCALE = ALPHA * DT_RANGE * LENGTH                        # m, thermal growth scale
S_SCALE = E_MOD * ALPHA * DT_RANGE                         # Pa, thermal stress scale
FORCE_SCALE = S_SCALE * THICKNESS.to("m").magnitude * 2.0 * HALF_WIDTH   # N, the axial force through the full section of a fully restrained plate at the full temperature drop
FORCE_FLOOR_RATIO = 0.1                                     # the equilibrium diagnostic is read only where the mean axial force is at least this fraction of FORCE_SCALE
NOISE_BAND_REL = 1e-6                                        # POST HOC reading only: a last relative change below this is 'converged to solver noise'
EQUILIBRIUM_SPREAD_TOL = 1e-3                               # relative spread of the axial force through three sections


def equilibrium_read(spread: float | None, ratio: float | None) -> bool:
    """The equilibrium diagnostic passes only where there IS an axial force to be constant: a solve that ignored the thermal load has
    zero force and a zero spread, which is not evidence of equilibrium."""
    return spread is not None and ratio is not None and spread <= EQUILIBRIUM_SPREAD_TOL and ratio >= FORCE_FLOOR_RATIO
DISP_AGREEMENT_TOL = Quantity(0.01 * U_SCALE, "m")          # cross-provider displacement, max over all nodes
STRESS_AGREEMENT_TOL = Quantity(0.01 * S_SCALE, "Pa")       # cross-provider element stress, max over all elements
BAR_THEORY_REL_TOL = 0.03                                   # mid-plate sigma_xx vs bar theory -E alpha (Tmean - Tref)
ANALYTIC_REL_TOL = 1e-6                                     # uniform-temperature exact cases, relative to the exact magnitude
HEAT_BALANCE_REL_TOL = 1e-6                                 # thermal energy balance, relative to the heat input
CONVERGENCE_ORDER_MIN = 0.9                                 # observed order of the mid-plate quantities under refinement


def system_definition():
    twin = lambda n: ScientificTwin(n, "1", TwinKind.CONCEPT).reference  # noqa: E731
    t = ConstraintDefinition("max_von_mises", "von_mises_stress", ConstraintOperator.LESS_EQUAL, Quantity(VM_ALLOWABLE_PA, "Pa"))
    d = ConstraintDefinition("max_displacement", "displacement_magnitude", ConstraintOperator.LESS_EQUAL, Quantity(DISP_LIMIT_M, "m"))
    system = SystemDefinition(
        "heated-plate", "1", (ComponentDefinition("assembly", "1"), ComponentDefinition("plate", "1")),
        (ComponentInstance("frame", "assembly", "1", twin("frame")), ComponentInstance("plate", "plate", "1", twin("plate"), parent_id="frame", participant_id="plate")),
        constraint_bindings=(ConstraintBinding("b_vm", "plate", "max_von_mises"), ConstraintBinding("b_disp", "plate", "max_displacement")), constraints=(t, d))
    return system, {"max_von_mises": t, "max_displacement": d}


@dataclass
class Structure:
    case: StructCase
    request: SystemRunRequest
    context: RuntimeContext
    exchange: Exchange
    mesh: SpatialMesh
    mat: PlateMaterial
    registry: Any
    constraints: dict


def build_structure(case: StructCase, registry=None, *, providers: tuple[str, ...] = ("fenicsx", "calculix", "code_aster")) -> Structure:
    from engcore.providers import default_registry
    registry = registry or default_registry()
    from forge_fenicsx import FenicsxProvider
    mesh = plate_mesh(case.nx, case.ny)
    mat = plate_material()
    ex = Exchange()
    fx = FenicsxProvider()
    status = {p: registry.status(p) for p in providers}
    vm_c, d_c = None, None
    system, defs = system_definition()
    fx_status = status["fenicsx"]

    def fx_ref(rec):
        return ProviderRecordRef("fenicsx", fx_status.version, fx_status.digest, rec.execution_identity, rec.digest, bool(rec.succeeded))

    # ---- thermal node (FEniCSx steady conduction)
    def thermal(call):
        rec = fx.execute(thermal_pde_problem(mesh, mat, case))
        if not rec.succeeded:
            return NodeOutcome.failed(rec.reason or "thermal solve failed", provider_records=(fx_ref(rec),))
        T = rec.field
        v = np.asarray(T.values)
        ex.temperature[call.execution_identity] = T
        ex.records[call.execution_identity] = rec
        # thermal energy balance: heat in at x = 0 vs heat out at x = L, from the solved field
        t_th = THICKNESS.to("m").magnitude
        q_in = case.flux * HALF_WIDTH * t_th
        cells = np.asarray(mesh.cells, dtype=int)
        xy = np.asarray(mesh.coordinates)
        a, b, c = xy[cells[:, 0]], xy[cells[:, 1]], xy[cells[:, 2]]
        det = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
        gx = ((b[:, 1] - c[:, 1]) * v[cells[:, 0]] + (c[:, 1] - a[:, 1]) * v[cells[:, 1]] + (a[:, 1] - b[:, 1]) * v[cells[:, 2]]) / det
        area = 0.5 * np.abs(det)
        last = xy[cells][:, :, 0].mean(axis=1) > LENGTH - 1.5 * (LENGTH / case.nx)
        q_out = float(-mat.conductivity.value.value.magnitude * (gx[last] * area[last]).sum() / area[last].sum() * HALF_WIDTH * t_th)
        lo, hi = PROPERTY_RANGE_K
        outputs = {"t_max": OutputValue(Quantity(float(v.max()), "K"), UNKNOWN, "fenicsx"), "t_min": OutputValue(Quantity(float(v.min()), "K"), UNKNOWN, "fenicsx"),
                   "t_mean": OutputValue(Quantity(float(v.mean()), "K"), UNKNOWN, "fenicsx"),
                   "t_exact_error": OutputValue(Quantity(float(np.abs(v - linear_temperature(np.asarray(mesh.coordinates)[:, 0], case.flux, mat.conductivity.value.value.magnitude, LENGTH, case.t_cold)).max()), "K"),
                                                UNKNOWN, "max |T - exact linear profile| (the exact 1-D conduction solution from the declared inputs)"),
                   "heat_in": OutputValue(Quantity(q_in, "W"), UNKNOWN, "declared flux x edge area"),
                   "heat_out": OutputValue(Quantity(q_out, "W"), UNKNOWN, "conductivity x recovered gradient at the sink end")}
        vtu = write_vtu(mesh, point_data={"temperature": ("K", v)}, metadata={"provider": f"fenicsx {fx_status.version}", "execution": rec.execution_identity, "case": case.name})
        ex.files[f"{case.name}_temperature.vtu"] = vtu
        art = ArtifactRef(f"{case.name}_temperature.vtu", "vtu", hashlib.sha256(vtu).hexdigest(), "temperature on the plate mesh; presentation, not evidence")
        report = ApplicabilityReport("property_range", "within" if lo <= v.min() and v.max() <= hi else "outside", digest_of({"T": [float(v.min()), float(v.max())], "range": [lo, hi]}),
                                     f"plate temperature [{v.min():.2f}, {v.max():.2f}] K against the declared property range [{lo}, {hi}] K")
        return NodeOutcome("succeeded", outputs, provider_records=(fx_ref(rec),), applicability=(report,), artifacts=(art,), delegated_record_digest=rec.digest)

    declared = {"flux_W_m2": case.flux, "t_cold_K": case.t_cold, "support": case.support, "nx": case.nx, "ny": case.ny, "length_m": LENGTH, "half_width_m": HALF_WIDTH,
                "thickness_m": THICKNESS.to("m").magnitude, "t_ref_K": T_REF, "property_range_K": list(PROPERTY_RANGE_K)}
    thermal_auth = CallbackAuthority("plate-thermal-fenicsx", thermal, config={"pde": "steady conduction, P1", "mesh": mesh.digest, "case": case.name,
                                                                               "material": mat.conductivity.digest, "solver": "PETSc LU", **declared}, kind="provider", deterministic=True)

    def field_for(call):
        producer = call.inputs["t_max"].producer_identity
        T = ex.temperature.get(producer)
        if T is None:
            raise RuntimeError("the temperature field of the producing thermal execution is not held (never regenerated)")
        v = np.asarray(T.values)
        if not (math.isclose(float(v.max()), call.value("t_max").magnitude_in("K"), rel_tol=1e-12) and
                math.isclose(float(v.min()), call.value("t_min").magnitude_in("K"), rel_tol=1e-12) and
                math.isclose(float(v.mean()), call.value("t_mean").magnitude_in("K"), rel_tol=1e-12)):
            raise RuntimeError("the held temperature field does not match the scalars the node was handed")
        return T

    def struct_outcome(call, provider: str, record, u, native, ref):
        T = field_for(call)
        q = structural_qoi(mesh, mat, u, np.asarray(T.values), native)
        rec_s = element_stress_of(mesh, mat, u, np.asarray(T.values))
        ex.solutions[call.execution_identity] = {"u": np.asarray(u, dtype=float), "native": None if native is None else np.asarray(native, dtype=float), "record": record,
                                                 "temperature": np.asarray(T.values)}
        outputs = {n: OutputValue(q[n], UNKNOWN, f"{provider} plate displacement/stress") for n, _ in PROP_OUT}
        vtu = write_vtu(mesh, point_data={"temperature": ("K", np.asarray(T.values)), "displacement": ("m", u)},
                        cell_data={"von_mises": ("Pa", rec_s.von_mises if native is None else np.sqrt(np.maximum(
                            native[:, 0] ** 2 - native[:, 0] * native[:, 1] + native[:, 1] ** 2 + 3 * native[:, 2] ** 2, 0.0)))},
                        metadata={"provider": provider, "execution": ref.execution_identity_digest, "case": case.name})
        name = f"{case.name}_{provider}.vtu"
        ex.files[name] = vtu
        art = ArtifactRef(name, "vtu", hashlib.sha256(vtu).hexdigest(), f"{provider} displacement and von Mises on the plate mesh; presentation, not evidence")
        return NodeOutcome("succeeded", outputs, provider_records=(ref,), artifacts=(art,), delegated_record_digest=record.digest)

    def struct_fenicsx(call):
        T = field_for(call)
        rec = fx.execute(structural_pde_problem(mesh, mat, case, T))
        if not rec.succeeded:
            return NodeOutcome.failed(rec.reason or "structural solve failed", provider_records=(fx_ref(rec),))
        return struct_outcome(call, "fenicsx", rec, np.asarray(rec.field.values), None, fx_ref(rec))

    def process_struct(provider_id):
        def run(call):
            from forge_calculix import CalculixProvider
            from forge_code_aster import CodeAsterProvider
            T = field_for(call)
            prob = thermoelastic_case(mesh, mat, case, T)
            prov = CalculixProvider(registry) if provider_id == "calculix" else CodeAsterProvider(registry)
            rec = prov.execute_thermoelastic(prob)
            ref = ProviderRecordRef.of_record(rec)
            if not rec.succeeded:
                return NodeOutcome.failed(rec.reason, provider_records=(ref,))
            return struct_outcome(call, provider_id, rec, np.asarray(rec.arrays["displacement"][1]), np.asarray(rec.arrays["stress"][1]), ref)
        return run

    cfg = {"mesh": mesh.digest, "case": case.name, "materials": [mat.youngs.digest, mat.poisson.digest, mat.expansion.digest], "t_ref": T_REF, **declared}
    auths = {"fenicsx": CallbackAuthority("plate-struct-fenicsx", struct_fenicsx, config=cfg, kind="provider", deterministic=True),
             "calculix": CallbackAuthority("plate-struct-calculix", process_struct("calculix"), config=cfg, kind="provider", deterministic=True),
             "code_aster": CallbackAuthority("plate-struct-code-aster", process_struct("code_aster"), config=cfg, kind="provider", deterministic=True)}

    def compare(a, b):
        def run(call):
            from engcore.providers import ComparisonDeclaration, OutputSelection, compare_providers
            sa, sb = ex.solutions[call.inputs["ux_a"].producer_identity], ex.solutions[call.inputs["ux_b"].producer_identity]
            ra, rb = sa["record"], sb["record"]
            out_name = lambda r: "displacement"  # noqa: E731
            decl = ComparisonDeclaration(f"nodal displacement vector, all nodes ({a} vs {b})", "m", "identity: both solve on the same mesh nodes (P1 / CPS3 / TRIA3)",
                                         DISP_AGREEMENT_TOL, 0.0, f"plate {case.nx}x{case.ny}, mesh {mesh.digest[:12]}, temperature field {sa['temperature'].tobytes().hex()[:8]}")
            cmp_u = compare_providers(decl, ra, out_name(ra), rb, out_name(rb))
            ex.comparisons[f"{a}~{b}"] = cmp_u
            outs = {"max_abs_displacement_difference": OutputValue(Quantity(cmp_u.max_absolute, "m"), UNKNOWN, "compare_providers"),
                    "displacement_within_tolerance": OutputValue(Quantity(1.0 if cmp_u.within_tolerance else 0.0, "dimensionless"), UNKNOWN, "declared before the run")}
            if sa["native"] is not None and sb["native"] is not None:
                sdecl = ComparisonDeclaration(f"element stress components (sxx, syy, sxy), all elements ({a} vs {b})", "Pa", "identity: same triangles", STRESS_AGREEMENT_TOL, 0.0,
                                              f"plate {case.nx}x{case.ny}")
                cmp_s = compare_providers(sdecl, ra, "stress", rb, "stress")
                ex.comparisons[f"{a}~{b}:stress"] = cmp_s
                outs["max_abs_stress_difference"] = OutputValue(Quantity(cmp_s.max_absolute, "Pa"), UNKNOWN, "compare_providers")
            return NodeOutcome("succeeded", outs)
        return run

    pairs = (("fenicsx", "calculix"), ("fenicsx", "code_aster"), ("calculix", "code_aster"))
    cmp_auths = {f"{a}~{b}": CallbackAuthority(f"plate-compare-{a}-{b}".replace("_", "-"), compare(a, b), config={"tol_u": str(DISP_AGREEMENT_TOL), "tol_s": str(STRESS_AGREEMENT_TOL)},
                                                deterministic=True) for a, b in pairs}
    conf = digest_of({"mesh": mesh.digest, "case": case.name, **declared})
    mrefs = lambda *rs: tuple(MaterialPropertyRef(name, "plate", pid, r.digest, u) for name, pid, r, u in rs)  # noqa: E731
    e_ref = mrefs(("E", "youngs_modulus", mat.youngs, "Pa"), ("nu", "poisson_ratio", mat.poisson, "dimensionless"), ("alpha", "thermal_expansion", mat.expansion, "1/K"))
    t_inputs = tuple(NodeInput(n, "thermal", n, "K") for n in ("t_max", "t_min", "t_mean"))
    bind = {"fenicsx": "fx", "calculix": "ccx", "code_aster": "ca"}
    nodes = [NodeSpec("thermal", NodeKind.PROVIDER_EXECUTION, thermal_auth.ref,
                      tuple(NodeOutputSpec(n, u) for n, u in (("t_max", "K"), ("t_min", "K"), ("t_mean", "K"), ("t_exact_error", "K"), ("heat_in", "W"), ("heat_out", "W"))),
                      provider_binding_ids=("fx",), material_refs=mrefs(("k", "thermal_conductivity", mat.conductivity, "W/(m*K)")),
                      applicability_checks=("property_range",), configuration_digest=conf)]
    for p_id in providers:
        nodes.append(NodeSpec(f"struct_{p_id}", NodeKind.PROVIDER_EXECUTION, auths[p_id].ref, tuple(NodeOutputSpec(n, u) for n, u in PROP_OUT), inputs=t_inputs,
                              provider_binding_ids=(bind[p_id],), material_refs=e_ref,
                              applicability_waiver="linear elastic small-strain response inside the declared property range, which the thermal node checks at the solved temperatures",
                              configuration_digest=conf))
    for a, b in pairs:
        outs = [("max_abs_displacement_difference", "m"), ("displacement_within_tolerance", "dimensionless")]
        if a != "fenicsx":
            outs.append(("max_abs_stress_difference", "Pa"))
        nodes.append(NodeSpec(f"compare_{a}_{b}", NodeKind.AGGREGATE, cmp_auths[f"{a}~{b}"].ref, tuple(NodeOutputSpec(n, u) for n, u in outs),
                              inputs=(NodeInput("ux_a", f"struct_{a}", "ux_max", "m"), NodeInput("ux_b", f"struct_{b}", "ux_max", "m")), configuration_digest=conf))
    obs = [RequestedObservable(f"{n}", "thermal", n, u) for n, u in (("t_max", "K"), ("t_min", "K"), ("t_mean", "K"), ("t_exact_error", "K"), ("heat_in", "W"), ("heat_out", "W"))]
    for p_id in providers:
        obs += [RequestedObservable(f"{n}_{p_id}", f"struct_{p_id}", n, u) for n, u in PROP_OUT]
    for a, b in pairs:
        obs.append(RequestedObservable(f"max_abs_displacement_difference_{a}_{b}", f"compare_{a}_{b}", "max_abs_displacement_difference", "m"))
        obs.append(RequestedObservable(f"displacement_within_tolerance_{a}_{b}", f"compare_{a}_{b}", "displacement_within_tolerance", "dimensionless"))
        if a != "fenicsx":
            obs.append(RequestedObservable(f"max_abs_stress_difference_{a}_{b}", f"compare_{a}_{b}", "max_abs_stress_difference", "Pa"))
    cdig = {k: digest_of(v.to_dict()) for k, v in defs.items()}
    cobs = (ConstraintObservation("b_vm", "max_von_mises", cdig["max_von_mises"], "vm_max_fenicsx"), ConstraintObservation("b_disp", "max_displacement", cdig["max_displacement"], "disp_max_fenicsx"))
    scenario = ScenarioSpecification(f"plate-{case.name}", "1", Quantity(0, "s"), Quantity(1, "s"), segments=(ScenarioSegment("steady", Quantity(0, "s"), Quantity(1, "s")),))
    timeline = Timeline.from_scenario(scenario, timeline_id=f"plate-{case.name}", basis=TimeBasis("plate", "elapsed", "start"), histories=())
    initial = InitialStateSpec(Quantity(0, "s"), (OwnerState("plate", "component", (InitialStateValue("reference_temperature", Quantity(T_REF, "K"),
                                                                                                        Uncertainty.unknown("declared stress-free temperature")),)),),
                               (("plate", mat.state.digest),))
    bindings = tuple(ProviderBinding(bind[p_id], p_id, status[p_id].version, status[p_id].digest) for p_id in providers)
    if "fx" not in {b.binding_id for b in bindings}:
        bindings += (ProviderBinding("fx", "fenicsx", fx_status.version, fx_status.digest),)
    request = SystemRunRequest.build(
        request_id=f"flagship-b-thermo-mechanical-{case.name}", system=system, scenario=scenario, timeline=timeline, environment=None, initial_state=initial,
        nodes=tuple(nodes), observables=tuple(obs), materials=(mat.state,), model_selections=(ModelSelection("plate", "thermoelastic-plane-stress-p1", "1"),),
        provider_bindings=bindings, constraint_observations=cobs, profile=ExecutionProfile((), "off", True, ()),
        environment_absent_reason="steady problem: the thermal loads are prescribed boundary conditions of the request; no time-varying environment channel is read")
    resolved = {r.digest: r for r in (mat.youngs, mat.poisson, mat.expansion, mat.conductivity)}
    authorities = AuthorityRegistry((thermal_auth, *auths.values(), *cmp_auths.values()))
    context = RuntimeContext(authorities, system=system, scenario=scenario, timeline=timeline, environment=None, material_states={mat.state.digest: mat.state},
                             resolved_properties=resolved, constraints={v: defs[k] for k, v in cdig.items()}, providers=registry)
    return Structure(case, request, context, ex, mesh, mat, registry, defs)


# ==================================================================================================== verification, study, summary
def _run(case: StructCase, registry=None):
    from engcore.system_runtime import SystemExecutor, compile_plan, preflight
    st = build_structure(case, registry)
    report = preflight(st.request, compile_plan(st.request), st.context)
    result = SystemExecutor(st.context).run(st.request)
    return st, report, result


def analytic_references():
    common = (ReferenceCondition("temperature_rise", 40.0, "K"), ReferenceCondition("thermal_strain", ALPHA * 40.0, "dimensionless"))
    env = (EnvelopeBound("temperature_rise", 0.1, 300.0, "K"), EnvelopeBound("thermal_strain", 0.0, 1e-2, "dimensionless"))
    free = ReferenceRecord("uniform-free-thermal-expansion", "Free thermal growth of a uniformly heated isotropic body: u = alpha dT x", "textbook thermoelasticity (derived)",
                           "small-strain linear thermoelasticity", "", "derived relation, not copied data", OracleKind.ANALYTIC_REFERENCE, common,
                           (("max_displacement_error_relative", "dimensionless"),), (), "", "closed form; roller/symmetry restraints admit exactly this field", env,
                           comparable_quantities=("max_displacement_error_relative",))
    constrained = ReferenceRecord("uniform-constrained-thermal-stress", "Fully restrained uniform heating: sigma_xx = -E alpha dT", "textbook thermoelasticity (derived)",
                                  "small-strain linear thermoelasticity, plane stress", "", "derived relation, not copied data", OracleKind.ANALYTIC_REFERENCE, common,
                                  (("axial_stress_error_relative", "dimensionless"),), (), "", "closed form; uniform axial stress, free lateral expansion", env,
                                  comparable_quantities=("axial_stress_error_relative",))
    bar = ReferenceRecord("bar-theory-mid-plate-stress", "Bar theory for a restrained plate with an axial temperature gradient: sigma_xx = -E alpha (T_mean - T_ref)",
                          "textbook thermoelasticity (derived; APPROXIMATE away from the supports)", "Saint-Venant, mid-section only", "", "derived relation, not copied data",
                          OracleKind.ANALYTIC_REFERENCE, (ReferenceCondition("aspect_ratio", LENGTH / (2 * HALF_WIDTH), "dimensionless"), ReferenceCondition("section_position", 0.5, "dimensionless")),
                          (("mid_section_stress_error_relative", "dimensionless"),), (), "", "closed form; end effects near the supports are NOT represented. The envelope (aspect ratio >= 5, section within 0.4-0.6 of the length) is DECLARED by this flagship "
                          "with no external source, and this plate sits exactly on the inclusive aspect-ratio edge",
                          (EnvelopeBound("aspect_ratio", 5.0, 1e3, "dimensionless"), EnvelopeBound("section_position", 0.4, 0.6, "dimensionless")),
                          comparable_quantities=("mid_section_stress_error_relative",))
    return free, constrained, bar


@dataclass
class StructureRun:
    structure: Structure
    result: Any
    preflight: Any
    constraints: tuple
    conservation: tuple
    summary: Any = None
    ladder: Any = None
    comparisons: tuple = ()
    references: tuple = ()
    verification: dict = field(default_factory=dict)
    study: dict = field(default_factory=dict)
    uncertainty: Any = None


def exact_limit_check(kind: str, registry=None) -> dict:
    """Run the uniform-temperature case through BIG 12 and compare every provider with the exact field.  Returns per-provider errors."""
    case = STRUCT_CASES["uniform_free" if kind == "free" else "uniform_constrained"]
    st, report, result = _run(case, registry)
    out = {"case": case.name, "status": result.status.value, "request": result.request_digest, "result": result.digest, "errors": {}}
    dT = case.t_cold - T_REF
    exact_u = ALPHA * dT * np.asarray(st.mesh.coordinates)
    exact_s = uniform_constrained_stress(case.t_cold)
    for p_id in ("fenicsx", "calculix", "code_aster"):
        if result.receipt(f"struct_{p_id}").status.value != "succeeded":
            out["errors"][p_id] = None
            continue
        sol = next(v for v in st.exchange.solutions.values() if _provider_of(v["record"]) == p_id)
        if kind == "free":
            out["errors"][p_id] = float(np.abs(sol["u"] - exact_u).max() / np.abs(exact_u).max())
        else:
            sxx = st_sxx(st, sol)
            out["errors"][p_id] = float(np.abs(sxx - exact_s).max() / abs(exact_s))
    return out


def _provider_of(record) -> str:
    from engcore.pde import PDEExecutionRecord
    if isinstance(record, PDEExecutionRecord):
        return "fenicsx"
    return record.identity.provider_id


def st_sxx(st: Structure, sol) -> np.ndarray:
    if sol["native"] is not None:
        return sol["native"][:, 0]
    return element_stress_of(st.mesh, st.mat, sol["u"], sol["temperature"]).sxx


def mesh_study(levels=((20, 4), (40, 8), (80, 16), (160, 32)), registry=None) -> dict:
    """Refine the flagship mesh through BIG 12 and tabulate the mid-plate quantities per provider; observed order from the three finest levels."""
    from dataclasses import replace
    base = STRUCT_CASES["flagship"]
    rows = []
    for nx, ny in levels:
        st, report, result = _run(replace(base, name=f"flagship_{nx}x{ny}", nx=nx, ny=ny), registry)
        row = {"nx": nx, "ny": ny, "nodes": st.mesh.node_count, "status": result.status.value, "result": result.digest}
        for p_id in ("fenicsx", "calculix", "code_aster"):
            for q in ("ux_mid", "sxx_mid", "ux_max", "vm_max"):
                o = result.observable(f"{q}_{p_id}")
                row[f"{q}_{p_id}"] = None if o.value is None else o.value.value.magnitude
        rows.append(row)
    table = {"levels": rows, "orders": {}, "monotone": {}}
    for p_id in ("fenicsx", "calculix", "code_aster"):
        for q in ("ux_mid", "sxx_mid", "ux_max", "vm_max"):
            v = [r[f"{q}_{p_id}"] for r in rows]
            if any(x is None for x in v) or len(v) < 3:
                continue
            d1, d2 = abs(v[-2] - v[-3]), abs(v[-1] - v[-2])
            table["orders"][f"{q}_{p_id}"] = None if d2 == 0 or d1 == 0 else float(math.log2(d1 / d2))
            table["monotone"][f"{q}_{p_id}"] = bool(d2 < d1)
    return table


def run_structure(case_name: str, registry=None, *, verification: bool = False, study: bool = False) -> StructureRun:
    from engcore.system_runtime import BalanceSpec, TermSource, assess_conservation, assess_constraints
    case = STRUCT_CASES[case_name]
    st, report, result = _run(case, registry)
    constraints = assess_constraints(result, st.context.system, st.context.constraints)
    heat_in = result.observable("heat_in")
    tol = Quantity(max(HEAT_BALANCE_REL_TOL * (abs(heat_in.value.value.magnitude) if heat_in.value else 0.0), 1e-9), "W")
    conservation = assess_conservation(result, (BalanceSpec("thermal_energy", (TermSource("heat_in", "heat_in"),), (TermSource("heat_out", "heat_out"),), tol),))
    run = StructureRun(st, result, report, constraints, conservation)
    free_ref, constrained_ref, bar_ref = analytic_references()
    entries, comparisons, references = [], [], []
    entries.append(contract_integrity_entry(report, result))
    ran = result.status.value == "succeeded"           # evidence from OTHER requests (limits, mesh study) is attached only to a run that itself succeeded
    closed = [c for c in conservation if c.status == "closed"]
    equil = [result.observable(f"section_force_spread_{p}") for p in ("fenicsx", "calculix", "code_aster")]
    ratio = [result.observable(f"section_force_ratio_{p}") for p in ("fenicsx", "calculix", "code_aster")]
    # the diagnostic means something only where there IS an axial force: a solve that ignored the thermal load has zero force and a zero spread
    eq_ok = all(equilibrium_read(None if s.value is None else s.value.value.magnitude, None if r.value is None else r.value.value.magnitude) for s, r in zip(equil, ratio))
    if closed and eq_ok:
        spreads = {p: o.value.value.magnitude for p, o in zip(("fenicsx", "calculix", "code_aster"), equil)}
        ratios = {p: o.value.value.magnitude for p, o in zip(("fenicsx", "calculix", "code_aster"), ratio)}
        entries.append(LevelEntry(2, LevelStatus.REACHED, (EvidenceLink.of_record("conservation_assessment", closed[0].to_dict(), "conservation_residual", "met",
                                                                                  f"thermal energy: residual {closed[0].residual.magnitude:.2e} W"),
                                                            EvidenceLink.of_record("equilibrium_diagnostic", {"relative_spread": spreads, "mean_force_over_scale": ratios,
                                                                                                              "spread_tolerance": EQUILIBRIUM_SPREAD_TOL, "force_floor_ratio": FORCE_FLOOR_RATIO},
                                                                                   "conservation_residual", "met",
                                                                                   f"axial section force constant along the plate for all three solvers (relative spread <= {EQUILIBRIUM_SPREAD_TOL:g}, mean force >= {FORCE_FLOOR_RATIO:g} of the thermal force scale)")),
                                  "heat in = heat out (exact for a linear profile, so a weak check on its own); the axial force through three sections is constant to within a relative "
                                  f"spread of {max(spreads.values()):.1e} for all three solvers (criterion {EQUILIBRIUM_SPREAD_TOL:g}, fixed before the run; read only where the mean force is at least "
                                  f"{FORCE_FLOOR_RATIO:g} of the thermal force scale, observed {min(ratios.values()):.2f}) - the more informative diagnostic"))
    else:
        entries.append(LevelEntry(2, LevelStatus.ATTEMPTED_NOT_REACHED if conservation else LevelStatus.NOT_ATTEMPTED, (), "; ".join(
            f"{c.balance_id}: {c.status}" for c in conservation) or "not assessable"))
    if verification and ran:
        free = exact_limit_check("free", registry)
        cons = exact_limit_check("constrained", registry)
        run.verification = {"free": free, "constrained": cons}
    if verification and ran and run.verification["free"]["status"] == "succeeded" and run.verification["constrained"]["status"] == "succeeded":
        conds = {"temperature_rise": Quantity(40.0, "K"), "thermal_strain": Quantity(ALPHA * 40.0, "dimensionless")}
        links = []
        missing_limits: list[str] = []
        for kind, ref in (("free", free_ref), ("constrained", constrained_ref)):
            v = run.verification[kind]
            if not all(e is not None and math.isfinite(e) for e in v["errors"].values()):
                missing_limits.append(kind)                       # a provider produced no error for this limit: nothing is compared, and the level is not reached
                continue
            worst = max(v["errors"].values())
            crit = PredeclaredCriterion(f"uniform_{kind}_exact", ref.quantities[0][0], "max_relative_error", Quantity(ANALYTIC_REL_TOL, "dimensionless"),
                                        "flagships/forge_flagships/thermo_mechanical.py:ANALYTIC_REL_TOL (fixed before the first run)")
            cmp_ = compare_to_reference(ref, crit, conds, value=Quantity(worst, "dimensionless"), compared_identity=v["result"],
                                        note=f"{kind}: errors by provider {v['errors']}")
            comparisons.append(cmp_)
            references.append(ref)
            links.append(EvidenceLink.of_comparison(cmp_))
        bar_value = None
        if result.observable("sxx_mid_fenicsx").value is not None:
            tmean_exact = case.t_cold + case.flux * LENGTH / (2 * K_COND)
            s_exact = uniform_constrained_stress(tmean_exact)
            bar_value = max(abs(result.observable(f"sxx_mid_{p}").value.value.magnitude - s_exact) / abs(s_exact) for p in ("fenicsx", "calculix", "code_aster"))
            crit = PredeclaredCriterion("bar_theory_mid_plate", "mid_section_stress_error_relative", "max_relative_error", Quantity(BAR_THEORY_REL_TOL, "dimensionless"),
                                        "flagships/forge_flagships/thermo_mechanical.py:BAR_THEORY_REL_TOL (fixed before the first run)")
            cmp_b = compare_to_reference(bar_ref, crit, {"aspect_ratio": Quantity(LENGTH / (2 * HALF_WIDTH), "dimensionless"), "section_position": Quantity(0.5, "dimensionless")},
                                         value=Quantity(bar_value, "dimensionless"), compared_identity=result.digest, note="mid-plate sigma_xx, three providers")
            comparisons.append(cmp_b)
            references.append(bar_ref)
            links.append(EvidenceLink.of_comparison(cmp_b))
        all_met = not missing_limits and len(comparisons) == 3 and all(c.outcome == "met" for c in comparisons)      # the exact limits AND bar theory: a missing one is not a pass
        parts = [f"{c.criterion.criterion_id} {c.outcome.upper()} ({c.value.magnitude:.1e} vs {c.criterion.tolerance.magnitude:g})" for c in comparisons]
        if missing_limits:
            parts.append(f"NO COMPARISON for the {missing_limits} limit(s): a provider produced no error")
        if len(comparisons) < 3 and not missing_limits:
            parts.append("bar theory: NOT compared (no mid-plate stress from the run)")
        entries.append(LevelEntry(3, LevelStatus.REACHED if all_met else LevelStatus.ATTEMPTED_NOT_REACHED, tuple(links),
                                  "evidence from OTHER requests for the two exact uniform-temperature limits (request digests "
                                  f"{run.verification['free']['request'][:12]}.., {run.verification['constrained']['request'][:12]}..) and from this run for bar theory: " + "; ".join(parts)))
    else:
        entries.append(LevelEntry(3, LevelStatus.NOT_ATTEMPTED, (), "exact-limit verification requests were not run in this call"))
    if study and ran:
        run.study = mesh_study(registry=registry)
        ok_q = ("ux_mid", "sxx_mid")
        # PREDECLARED criterion (fixed before the first run): every provider's mid-plate displacement and stress converge monotonically at observed order >= 0.9
        good = all(run.study["monotone"].get(f"{q}_{p}") and (run.study["orders"].get(f"{q}_{p}") or 0) >= CONVERGENCE_ORDER_MIN
                   for q in ok_q for p in ("fenicsx", "calculix", "code_aster"))
        failing = sorted(f"{q}_{p}" for q in ok_q for p in ("fenicsx", "calculix", "code_aster")
                         if not (run.study["monotone"].get(f"{q}_{p}") and (run.study["orders"].get(f"{q}_{p}") or 0) >= CONVERGENCE_ORDER_MIN))
        # POST-HOC reading, added after the predeclared outcome was seen: a quantity whose last change is below 1e-6 (relative) has already converged to solver noise,
        # so an observed order is not defined for it.  Reported beside the predeclared outcome, never in place of it.
        last = run.study["levels"]
        def converged_to_noise(q: str, p: str) -> bool:
            v = [row[f"{q}_{p}"] for row in last]
            return abs(v[-1] - v[-2]) <= NOISE_BAND_REL * max(abs(v[-1]), 1e-30)
        post_good = all((run.study["monotone"].get(f"{q}_{p}") and (run.study["orders"].get(f"{q}_{p}") or 0) >= CONVERGENCE_ORDER_MIN) or converged_to_noise(q, p)
                        for q in ok_q for p in ("fenicsx", "calculix", "code_aster"))
        run.study["predeclared_criterion_met"] = good
        run.study["predeclared_failing"] = failing
        run.study["post_hoc_noise_aware_met"] = post_good
        st_ = run.study
        ux_orders = {p: st_["orders"][f"ux_mid_{p}"] for p in ("fenicsx", "calculix", "code_aster")}
        vm_orders = {p: st_["orders"][f"vm_max_{p}"] for p in ("fenicsx", "calculix", "code_aster")}
        sxx_rel = {p: abs(last[-1][f"sxx_mid_{p}"] - last[-2][f"sxx_mid_{p}"]) / abs(last[-1][f"sxx_mid_{p}"]) for p in ("fenicsx", "calculix", "code_aster")}
        vm_seq = [row["vm_max_fenicsx"] / 1e6 for row in last]
        vm_orders_txt = {p: round(v, 2) for p, v in vm_orders.items()}
        links4 = [EvidenceLink.of_record("mesh_study", run.study, "discretisation_convergence", "met" if good else "not_met", f"predeclared criterion; failing: {failing}")]
        if not good:      # a post-hoc reading may sit beside a level that is NOT reached; it can never be attached to a REACHED one
            links4.append(EvidenceLink.of_record("mesh_study_post_hoc", {"reading": "noise_aware", "relative_change_threshold": NOISE_BAND_REL, "met": post_good,
                                                                        "study_digest": digest_of(run.study)},
                                                 "post_hoc_discretisation_convergence", "met" if post_good else "not_met",
                                                 f"added after seeing the outcome: quantities already converged to solver noise (last change < {NOISE_BAND_REL:g} relative) are not judged by an observed order"))
        entries.append(LevelEntry(
            4, LevelStatus.REACHED if good else LevelStatus.ATTEMPTED_NOT_REACHED, tuple(links4),
            f"four uniformly refined meshes, each a separate BIG 12 request (evidence from OTHER requests). Predeclared criterion (monotone, observed order >= {CONVERGENCE_ORDER_MIN} for mid-plate "
            "displacement AND stress, every provider): " + ("MET" if good else f"NOT MET - {failing}") + f". Observed orders of the mid-length displacement {ux_orders}; last relative change of the mid-plate stress "
            f"{ {p: f'{v:.1e}' for p, v in sxx_rel.items()} }" + (" (at solver noise, so an order is undefined for it)" if all(v <= 1e-6 for v in sxx_rel.values()) else "")
            + f". Peak von Mises (FEniCSx, MPa) over the meshes {[round(x, 3) for x in vm_seq]}, observed orders {vm_orders_txt}"
            + (": it is NOT claimed converged and the cause of its slow behaviour was not investigated" if min(vm_orders.values()) < CONVERGENCE_ORDER_MIN else "")))
    else:
        entries.append(LevelEntry(4, LevelStatus.NOT_ATTEMPTED, (), "mesh study not run in this call"))
    pair_flags = [result.observable(f"displacement_within_tolerance_{a}_{b}") for a, b in (("fenicsx", "calculix"), ("fenicsx", "code_aster"), ("calculix", "code_aster"))]
    if all(o.value is not None and o.value.value.magnitude == 1.0 for o in pair_flags):
        links = [EvidenceLink.of_provider_comparison(cmp_, k) for k, cmp_ in sorted(st.exchange.comparisons.items())]
        dmax = max(result.observable(f"disp_max_{p}").value.value.magnitude for p in ("fenicsx", "calculix", "code_aster"))
        worst = max(result.observable(f"max_abs_displacement_difference_{a}_{b}").value.value.magnitude for a, b in (("fenicsx", "calculix"), ("fenicsx", "code_aster"), ("calculix", "code_aster")))
        entries.append(LevelEntry(5, LevelStatus.REACHED, tuple(links),
                                  "three structural implementations agree on displacement (and CalculiX/Code_Aster on element stress) within tolerances declared before the run: CORROBORATION, not validation. "
                                  f"Scale of the criterion: displacement tolerance {DISP_AGREEMENT_TOL.magnitude:.2e} m = {100 * DISP_AGREEMENT_TOL.magnitude / dmax:.1f} % of the peak displacement (it was set from the free-growth scale, "
                                  f"which is larger than this restrained plate's response); observed worst difference {worst:.2e} m ({100 * worst / dmax:.3f} %). All three solve the same P1 plane-stress discretisation on one mesh "
                                  "from ONE shared FEniCSx temperature field, so this corroborates the implementations, not the discretisation or the thermal solution, and FEniCSx/Code_Aster share one formulation"))
    elif any(o.value is not None for o in pair_flags):
        entries.append(LevelEntry(5, LevelStatus.ATTEMPTED_NOT_REACHED, (), "at least one provider pair disagreed beyond its declared tolerance; see the comparison nodes"))
    else:
        entries.append(LevelEntry(5, LevelStatus.NOT_ATTEMPTED, (), "no provider comparison was produced"))
    entries += [LevelEntry(6, LevelStatus.NOT_AVAILABLE, (), "no published thermo-structural numerical benchmark was integrated for this problem"),
                LevelEntry(7, LevelStatus.NOT_AVAILABLE, (), "no measured deformation or stress data for this plate exists")]
    run.ladder = VerificationLadder.of(**{f"l{e.level}": e for e in entries})
    run.comparisons, run.references = tuple(comparisons), tuple(references)
    run.uncertainty = UncertaintyStatement(
        (), ("heat flux and sink temperature (declared)", "stress-free temperature (declared)", "E, nu, alpha, k (ASSUMED illustrative records)", "plate thickness and geometry (declared)"),
        "NOT QUANTIFIED: linear small-strain plane-stress idealisation, isotropic constant properties, 2-D symmetric-half model (unknown, not zero)",
        (f"E {mat_digest(st, 'youngs')[:12]}.. nu {mat_digest(st, 'poisson')[:12]}.. alpha {mat_digest(st, 'expansion')[:12]}.. k {mat_digest(st, 'conductivity')[:12]}.. (all ASSUMED)",),
        f"thermal solution checked against the declared property range {list(PROPERTY_RANGE_K)} K on every run; small strain and linear elasticity are assumed (the peak thermal strain is reported)",
        ("exact analytic limits and a bar-theory estimate were used; both are analytic references, not numerical benchmarks and not experiments" if comparisons
         else "no reference comparison was made in this run (the exact-limit and mesh-study requests were not run here, or this run did not succeed); no numerical benchmark and no experiment exists for this plate"))
    run.summary = build_summary(
        f"Heated aluminium plate, {case.support}, {case.nx}x{case.ny} P1 mesh ({case.name})", st.request, result,
        outputs=[("Hot-end temperature", "t_max"), ("Sink-end temperature", "t_min"), ("Max displacement (FEniCSx)", "disp_max_fenicsx"), ("Max displacement (CalculiX)", "disp_max_calculix"),
                 ("Max displacement (Code_Aster)", "disp_max_code_aster"), ("Mid-plate axial stress (FEniCSx)", "sxx_mid_fenicsx"), ("Mid-plate axial stress (CalculiX)", "sxx_mid_calculix"),
                 ("Mid-plate axial stress (Code_Aster)", "sxx_mid_code_aster"), ("Peak von Mises (FEniCSx)", "vm_max_fenicsx"), ("Peak von Mises (CalculiX)", "vm_max_calculix"),
                 ("Max |displacement| difference FEniCSx-CalculiX", "max_abs_displacement_difference_fenicsx_calculix"),
                 ("Max |displacement| difference FEniCSx-Code_Aster", "max_abs_displacement_difference_fenicsx_code_aster"),
                 ("Max |stress| difference CalculiX-Code_Aster", "max_abs_stress_difference_calculix_code_aster")],
        constraints=constraints, conservation=conservation, ladder=run.ladder, comparisons=comparisons, references=tuple(dict.fromkeys(references)), uncertainty=run.uncertainty,
        trace_observable="sxx_mid_calculix" if result.observable("sxx_mid_calculix").value is not None else "t_max",
        notes=(f"case {case.name}: {case.description}", "material properties are illustrative ASSUMED records, not datasheet or measured values"))
    return run


def mat_digest(st: Structure, which: str) -> str:
    return getattr(st.mat, which).digest
