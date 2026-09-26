"""FLAGSHIP C - lid-driven cavity at Re = 100: OpenFOAM vs SU2 vs a published numerical benchmark, with a mesh study.

Engineering question
    Do two independent CFD codes, given exactly the same declared cavity, fluid records and Reynolds number, predict the same flow,
    how does each converge under refinement, and how close does each come to the published Ghia et al. (1982) centerline benchmark?

Why it is a flagship: the two codes DISAGREE near the moving lid.  BIG 11 recorded a pre-declared whole-field 3 %-of-lid-speed
comparison that FAILED (max ~25 % in lid-adjacent cells at Re ~ 10).  That negative result is preserved here: the same
pre-declared whole-field criterion is applied at every mesh level and its outcome is reported as it comes out.  A lower-half
comparison chosen after the fact is labelled POST HOC and can never count as corroboration.

Fluid: water at 20 degC, 1 atm, density and viscosity from CoolProp (provider-derived property records, not measurements).
Re is set to exactly 100 by declaring the lid speed U = Re nu / L.  Mesh: N x N cells, N in {20, 40, 80}.

BIG 12 request: fluid_properties -> openfoam_N / su2_N (N = 20, 40, 80) -> compare_N, plus a convergence aggregate.  Bulk fields and the
provider records travel outside the request (an exchange keyed by execution identity); the request sees scalars and digests.

Ghia et al. is a NUMERICAL benchmark (multigrid finite difference on 129 x 129 points), not an experiment.  Agreement with it would
support the model's numerics at Re = 100 for this configuration only; nothing here is experimental validation.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from engcore.engineering import (
    EnvelopeBound, EvidenceLink, LevelEntry, LevelStatus, PredeclaredCriterion, ReferenceCondition, ReferenceRecord, UncertaintyStatement, VerificationLadder,
    build_summary, compare_to_reference, contract_integrity_entry, write_vtu,
)
from engcore.execution.multiphysics import InitialStateValue
from engcore.materials import FluidIdentity, FluidState
from engcore.scenarios import NamedQuantity, ScenarioSegment, ScenarioSpecification, TimeBasis, Timeline
from engcore.scientific.ir.constraints import ConstraintDefinition, ConstraintOperator
from engcore.scientific.oracles import OracleKind
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.twins import ScientificTwin, TwinKind
from engcore.scientific.units.quantity import Quantity
from engcore.system_runtime import (
    ApplicabilityReport, ArtifactRef, AuthorityRegistry, CallbackAuthority, ConstraintObservation, ExecutionProfile, InitialStateSpec, LiteralInput, ModelSelection,
    NodeInput, NodeKind, NodeOutcome, NodeOutputSpec, NodeSpec, OutputValue, OwnerState, ProviderBinding, ProviderRecordRef, RequestedObservable, RuntimeContext,
    SystemRunRequest,
)
from engcore.system_runtime._common import digest_of
from engcore.systems import ComponentDefinition, ComponentInstance, ConstraintBinding, SystemDefinition

SIDE = 0.1                     # m
REYNOLDS = 100.0
LEVELS = (20, 40, 80)
UNKNOWN = Uncertainty.unknown("declared or derived quantity; no uncertainty was quantified")
# ---- criteria fixed BEFORE any run ------------------------------------------------------------------------------------------------
WHOLE_FIELD_TOL = 0.03         # of lid speed: OpenFOAM vs SU2 cell-centre velocity, whole field (the BIG 11 criterion, NOT loosened)
GHIA_TOL = 0.02                # of lid speed: max |profile - Ghia| on each centerline at the finest mesh
INTRINSIC_ORDER_MIN = 0.9         # POST HOC reading only: observed order of the fixed centre-velocity sequence
FLUX_TOL = 1e-3                # of U L: net flux through each mid-plane (mass conservation of the sampled profile)
STEADY_TOL_M_S = 1e-7          # OpenFOAM max|dU| over the last write interval
SU2_TARGET = -10.0             # log10 rms residual
SU2_ITERATIONS = 20000         # iteration cap (a run that stops on the cap without reaching the target is FAILED)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# ==================================================================================================== reference (published numerical benchmark)
def load_ghia() -> tuple[ReferenceRecord, dict]:
    path = os.path.join(os.path.dirname(__file__), "data", "ghia_1982_re100_excerpt.json")
    raw = open(path, "rb").read()
    d = json.loads(raw.decode())
    y = tuple(r[0] for r in d["u_vs_y"]); u = tuple(r[1] for r in d["u_vs_y"])
    x = tuple(r[0] for r in d["v_vs_x"]); v = tuple(r[1] for r in d["v_vs_x"])
    sd = d["source_digests"]
    ref = ReferenceRecord(
        d["reference_id"], d["title"], d["authors"], d["publication"], d["access_urls"][0], d["license_status"], OracleKind.BENCHMARK_DATASET,
        (ReferenceCondition("reynolds", 100.0, "dimensionless"), ReferenceCondition("cavity_aspect_ratio", 1.0, "dimensionless")), (("y", "dimensionless"), ("u", "dimensionless"), ("x", "dimensionless"), ("v", "dimensionless")),
        (("y", y), ("u", u), ("x", x), ("v", v)), sha(sd["table_I_transcription_sha256"] + sd["table_II_transcription_sha256"]),
        "Re=100 columns of Tables I and II typed from a public transcription and cross-checked against a second independent transcription; "
        f"transcription sha256: {sd['table_I_transcription_sha256'][:16]}.. / {sd['table_II_transcription_sha256'][:16]}..; excerpt file sha256 {hashlib.sha256(raw).hexdigest()[:16]}..; "
        "a NUMERICAL benchmark (129 x 129 multigrid finite difference), not an experiment; the applicability envelope (Re 99-101, square cavity) is AUTHORED by this flagship from the paper's stated case, "
        "not a machine-readable statement of the source, and covers Re and aspect ratio only (boundary conditions, steadiness and dimensionality are not enforced)",
        (EnvelopeBound("reynolds", 99.0, 101.0, "dimensionless"), EnvelopeBound("cavity_aspect_ratio", 0.999, 1.001, "dimensionless")),
        comparable_quantities=("centerline_velocity_over_lid_speed",))
    return ref, d


# ==================================================================================================== samplers (declared, piecewise linear)
def line_from_cells(field_xy: np.ndarray, n: int, side: float, lid: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """u on x = L/2 and v on y = L/2 from cell-centre velocity (x fastest).  Wall values (no-slip / lid) close each line.  Returns (y, u, x, v) in metres."""
    g = field_xy.reshape(n, n, 2)                       # [j (y), i (x), comp]
    h = side / n
    u_col = 0.5 * (g[:, n // 2 - 1, 0] + g[:, n // 2, 0])
    y = np.concatenate([[0.0], (np.arange(n) + 0.5) * h, [side]])
    u = np.concatenate([[0.0], u_col, [lid]])
    v_row = 0.5 * (g[n // 2 - 1, :, 1] + g[n // 2, :, 1])
    x = np.concatenate([[0.0], (np.arange(n) + 0.5) * h, [side]])
    v = np.concatenate([[0.0], v_row, [0.0]])
    return y, u, x, v


def line_from_nodes(field_xy: np.ndarray, n: int, side: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    g = field_xy.reshape(n + 1, n + 1, 2)               # [j, i, comp]
    c = np.linspace(0.0, side, n + 1)
    return c, g[:, n // 2, 0], c, g[n // 2, :, 1]


def sample_at(coord: np.ndarray, values: np.ndarray, at: np.ndarray) -> np.ndarray:
    return np.interp(at, coord, values)


def flux_residual(coord: np.ndarray, values: np.ndarray, side: float, lid: float) -> float:
    """Net flux through a mid-plane relative to U L (trapezoid on the sampled profile).  Mass conservation demands 0."""
    return float(np.trapezoid(values, coord) / (lid * side))


def streamfunction_extremum(field_xy: np.ndarray, n: int, side: float) -> tuple[float, float, float]:
    """(x, y, psi/(U L-normalised by caller)) of the extremum of psi = int_0^y u dy on the cell-centre grid (grid resolution, diagnostic only)."""
    g = field_xy.reshape(n, n, 2)
    h = side / n
    psi = np.cumsum(g[:, :, 0], axis=0) * h - 0.5 * g[:, :, 0] * h
    j, i = np.unravel_index(np.argmax(np.abs(psi)), psi.shape)
    return float((i + 0.5) * h), float((j + 0.5) * h), float(psi[j, i])


def cell_from_nodes(field_xy: np.ndarray, n: int) -> np.ndarray:
    """Declared 4-corner average of nodal values onto cell centres (x fastest)."""
    g = field_xy.reshape(n + 1, n + 1, 2)
    return 0.25 * (g[:-1, :-1] + g[1:, :-1] + g[:-1, 1:] + g[1:, 1:]).reshape(n * n, 2)


# ==================================================================================================== the BIG 12 system
class Exchange:
    def __init__(self) -> None:
        self.fields: dict[str, dict[str, Any]] = {}
        self.records: dict[str, Any] = {}
        self.files: dict[str, bytes] = {}
        self.comparisons: dict[str, Any] = {}
        self.profiles: dict[str, dict] = {}
        self.fluid: dict[str, Any] = {}


def system_definition():
    twin = lambda n: ScientificTwin(n, "1", TwinKind.CONCEPT).reference  # noqa: E731
    flux = ConstraintDefinition("max_midplane_flux", "midplane_flux_residual", ConstraintOperator.LESS_EQUAL, Quantity(FLUX_TOL, "dimensionless"))
    system = SystemDefinition("lid-driven-cavity", "1", (ComponentDefinition("cavity", "1"),), (ComponentInstance("cavity", "cavity", "1", twin("cavity"), participant_id="cavity"),),
                              constraint_bindings=(ConstraintBinding("b_flux_openfoam", "cavity", "max_midplane_flux"), ConstraintBinding("b_flux_su2", "cavity", "max_midplane_flux")),
                              constraints=(flux,))
    return system, flux


@dataclass
class Cavity:
    request: SystemRunRequest
    context: RuntimeContext
    exchange: Exchange
    reference: ReferenceRecord
    reynolds: float
    levels: tuple[int, ...]
    registry: Any


def build_cavity(reynolds: float = REYNOLDS, levels: tuple[int, ...] = LEVELS, registry=None, *, tag: str = "re100") -> Cavity:
    from engcore.providers import default_registry
    from forge_coolprop import CoolPropProvider
    from forge_openfoam import CavityProblem, OpenFOAMProvider
    from forge_su2 import CavityProblemSU2, SU2Provider

    registry = registry or default_registry()
    ref, _ = load_ghia()
    ex = Exchange()
    st = {p: registry.status(p) for p in ("coolprop", "openfoam", "su2")}
    system, flux_c = system_definition()
    cp = CoolPropProvider(registry)
    state = FluidState(FluidIdentity("water"), (NamedQuantity("temperature", Quantity(20, "degC")), NamedQuantity("pressure", Quantity(101325, "Pa"))))
    of_status, su2_status, cp_status = st["openfoam"], st["su2"], st["coolprop"]

    def fluid(call):
        rho, mu = cp.resolve(state, "density"), cp.resolve(state, "dynamic_viscosity")
        refs = tuple(ProviderRecordRef("coolprop", cp_status.version, cp_status.digest, r.provider_execution_identity, r.digest, r.status == "known") for r in (rho, mu))
        if rho.status != "known" or mu.status != "known":
            return NodeOutcome.failed("CoolProp returned no usable water property", provider_records=refs)
        nu = mu.value.magnitude_in("Pa*s") / rho.value.magnitude_in("kg/m^3")
        re = call.value("reynolds").magnitude_in("dimensionless")
        side = call.value("side").magnitude_in("m")
        u_lid = re * nu / side
        ex.fluid[call.execution_identity] = {"rho": rho, "mu": mu}
        outs = {"density": OutputValue(rho.value, UNKNOWN, "CoolProp record"), "dynamic_viscosity": OutputValue(mu.value, UNKNOWN, "CoolProp record"),
                "kinematic_viscosity": OutputValue(Quantity(nu, "m^2/s"), UNKNOWN, "mu / rho"),
                "lid_velocity": OutputValue(Quantity(u_lid, "m/s"), UNKNOWN, "declared: U = Re nu / L so that Re is exactly the declared value")}
        return NodeOutcome("succeeded", outs, provider_records=refs)

    fluid_auth = CallbackAuthority("cavity-fluid", fluid, config={"fluid": "water", "T": "20 degC", "p": "101325 Pa", "provider": f"coolprop {cp_status.version}"}, kind="provider", deterministic=True)

    def properties(call):
        rec = ex.fluid[call.inputs["rho"].producer_identity]
        return rec["rho"], rec["mu"]

    U_OUT = (("ghia_u_max_error", "dimensionless"), ("ghia_v_max_error", "dimensionless"), ("u_center", "dimensionless"), ("v_center", "dimensionless"),
             ("vortex_x", "dimensionless"), ("vortex_y", "dimensionless"), ("u_flux_residual", "dimensionless"), ("v_flux_residual", "dimensionless"),
             ("flux_residual_abs", "dimensionless"), ("max_speed", "m/s"), ("wall_seconds", "s"))

    def analyse(call, n: int, provider: str, u_lid: float, cells_xy: np.ndarray, line: tuple, record, ref_id: ProviderRecordRef, file_pairs) -> NodeOutcome:
        y, u, x, v = line
        U = u_lid
        gu = np.array(ref.values("u")); gy = np.array(ref.values("y")); gx = np.array(ref.values("x")); gv = np.array(ref.values("v"))
        u_at = sample_at(y, u, gy * SIDE) / U
        v_at = sample_at(x, v, gx * SIDE) / U
        vx, vy, psi = streamfunction_extremum(cells_xy, n, SIDE)
        outs = {"ghia_u_max_error": np.abs(u_at - gu).max(), "ghia_v_max_error": np.abs(v_at - gv).max(), "u_center": float(sample_at(y, u, np.array([0.5 * SIDE]))[0] / U),
                "v_center": float(sample_at(x, v, np.array([0.5 * SIDE]))[0] / U), "vortex_x": vx / SIDE, "vortex_y": vy / SIDE,
                "u_flux_residual": flux_residual(y, u, SIDE, U), "v_flux_residual": flux_residual(x, v, SIDE, U)}
        outs["flux_residual_abs"] = max(abs(outs["u_flux_residual"]), abs(outs["v_flux_residual"]))
        ex.profiles[call.execution_identity] = {"provider": provider, "n": n, "y_over_L": (y / SIDE).tolist(), "u_over_U": (u / U).tolist(), "x_over_L": (x / SIDE).tolist(),
                                                "v_over_U": (v / U).tolist(), "ghia_y": gy.tolist(), "ghia_u": gu.tolist(), "ghia_x": gx.tolist(), "ghia_v": gv.tolist(),
                                                "u_at_ghia_points": u_at.tolist(), "v_at_ghia_points": v_at.tolist()}
        outputs = {k: OutputValue(Quantity(float(val), "dimensionless"), UNKNOWN, f"{provider} {n}x{n}") for k, val in outs.items()}
        outputs["max_speed"] = OutputValue(Quantity(float(np.linalg.norm(cells_xy, axis=1).max()), "m/s"), UNKNOWN, provider)
        outputs["wall_seconds"] = OutputValue(Quantity(float(record.metrics.get("process_s", 0.0)), "s"), UNKNOWN, "operational, not evidence")
        arts = []
        for name, data in file_pairs:
            ex.files[name] = data
            arts.append(ArtifactRef(name, name.rsplit(".", 1)[-1], hashlib.sha256(data).hexdigest(), "presentation of the run; not evidence"))
        return NodeOutcome("succeeded", outputs, provider_records=(ref_id,), artifacts=tuple(arts), delegated_record_digest=record.digest)

    def csv_profiles(call_id, n, provider, prof):
        rows = ["y_over_L,u_over_U,x_over_L,v_over_U"] + [f"{a!r},{b!r},{c!r},{d!r}" for a, b, c, d in zip(prof["y_over_L"], prof["u_over_U"], prof["x_over_L"], prof["v_over_U"])]
        return ("\n".join(rows) + "\n").encode()

    def make_of(n):
        def run(call):
            rho, mu = properties(call)
            u_lid = call.value("lid_velocity").magnitude_in("m/s")
            nu = call.value("nu").magnitude_in("m^2/s")
            of = OpenFOAMProvider(registry)
            # the case is one fixed number of PISO steps: dt chosen so that Courant <= ~4 at the finest mesh, end time 30000 s (about 60 e-folds of the slowest viscous mode)
            dt = 5.0
            steps = 6000
            prob = CavityProblem(f"cavity-{tag}-{n}", Quantity(SIDE, "m"), n, Quantity(u_lid, "m/s"), Quantity(nu, "m^2/s"),
                                 (("dynamic_viscosity", mu.digest), ("density", rho.digest)), Quantity(dt * steps, "s"), Quantity(dt, "s"), write_steps=500,
                                 steady_tolerance=Quantity(STEADY_TOL_M_S, "m/s"))
            rec, fields = of.run_cavity(prob)
            ref_id = ProviderRecordRef.of_record(rec)
            if not rec.succeeded:
                return NodeOutcome.failed(rec.reason, provider_records=(ref_id,))
            cells = np.asarray(fields["velocity"].values)
            line = line_from_cells(cells, n, SIDE, u_lid)
            ex.records[call.execution_identity] = rec
            ex.fields[call.execution_identity] = {"cells_xy": cells, "mesh": fields["velocity"].mesh, "kind": "cell", "n": n, "u_lid": u_lid,
                                                  "pressure": np.asarray(fields["pressure"].values), "record": rec}
            out = analyse(call, n, "openfoam", u_lid, cells, line, rec, ref_id, ())
            prof = ex.profiles[call.execution_identity]
            vtu = write_vtu(fields["velocity"].mesh, cell_data={"velocity": ("m/s", cells), "kinematic_pressure": ("m^2/s^2", np.asarray(fields["pressure"].values))},
                            metadata={"provider": f"openfoam {of_status.version}", "execution": rec.identity.digest, "case": f"{tag}-{n}", "note": "steady_by_declared_tolerance"})
            files = ((f"openfoam_{n}.vtu", vtu), (f"openfoam_{n}_centerlines.csv", csv_profiles(0, n, "openfoam", prof)))
            for name, data in files:
                ex.files[name] = data
            arts = tuple(ArtifactRef(nm, nm.rsplit(".", 1)[-1], hashlib.sha256(d).hexdigest(), "presentation of the run; not evidence") for nm, d in files)
            return NodeOutcome("succeeded", out.outputs, provider_records=out.provider_records, artifacts=arts, delegated_record_digest=out.delegated_record_digest)
        return run

    def make_su2(n):
        def run(call):
            rho, mu = properties(call)
            u_lid = call.value("lid_velocity").magnitude_in("m/s")
            prob = CavityProblemSU2(f"cavity-{tag}-{n}", Quantity(SIDE, "m"), n, Quantity(u_lid, "m/s"), rho.value, mu.value,
                                    (("dynamic_viscosity", mu.digest), ("density", rho.digest)), iterations=SU2_ITERATIONS, residual_log10_target=SU2_TARGET)
            rec = SU2Provider(registry).run_cavity(prob)
            ref_id = ProviderRecordRef.of_record(rec)
            if not rec.succeeded:
                return NodeOutcome.failed(rec.reason, provider_records=(ref_id,))
            nodes = np.asarray(rec.arrays["velocity"][1])
            cells = cell_from_nodes(nodes, n)
            line = line_from_nodes(nodes, n, SIDE)
            ex.records[call.execution_identity] = rec
            ex.fields[call.execution_identity] = {"cells_xy": cells, "nodes_xy": nodes, "kind": "node", "n": n, "u_lid": u_lid, "pressure": np.asarray(rec.arrays["pressure"][1]),
                                                  "record": rec}
            out = analyse(call, n, "su2", u_lid, cells, line, rec, ref_id, ())
            prof = ex.profiles[call.execution_identity]
            from forge_openfoam import CavityProblem, cavity_mesh  # the same declared quadrilateral mesh
            mesh = cavity_mesh(CavityProblem("m", Quantity(SIDE, "m"), n, Quantity(u_lid, "m/s"), Quantity(1e-6, "m^2/s"), (("x", "y"),), Quantity(500, "s"), Quantity(1, "s"), write_steps=500))
            vtu = write_vtu(mesh, point_data={"velocity": ("m/s", nodes), "pressure": ("Pa", np.asarray(rec.arrays["pressure"][1]))},
                            metadata={"provider": f"su2 {su2_status.version}", "execution": rec.identity.digest, "case": f"{tag}-{n}"})
            files = ((f"su2_{n}.vtu", vtu), (f"su2_{n}_centerlines.csv", csv_profiles(0, n, "su2", prof)))
            for name, data in files:
                ex.files[name] = data
            arts = tuple(ArtifactRef(nm, nm.rsplit(".", 1)[-1], hashlib.sha256(d).hexdigest(), "presentation of the run; not evidence") for nm, d in files)
            return NodeOutcome("succeeded", out.outputs, provider_records=out.provider_records, artifacts=arts, delegated_record_digest=out.delegated_record_digest)
        return run

    def make_compare(n):
        def run(call):
            from engcore.providers import ComparisonDeclaration, OutputSelection, compare_providers
            a = ex.fields[call.inputs["ofx"].producer_identity]
            b = ex.fields[call.inputs["su2x"].producer_identity]
            mesh = a["mesh"]
            u_lid = a["u_lid"]
            corners = tuple(tuple((int(k), 0.25) for k in cell) for cell in mesh.cells)
            decl = ComparisonDeclaration(f"cell-centre velocity (x, y) of the lid-driven cavity, WHOLE FIELD, {n}x{n}", "m/s",
                                         "SU2 nodal velocity -> OpenFOAM cell centres by the mean of the 4 cell corners", Quantity(WHOLE_FIELD_TOL * u_lid, "m/s"), 0.0,
                                         f"Re={reynolds:g}, {n}x{n}, water 20 C from CoolProp {cp_status.version}")
            whole = compare_providers(decl, a["record"], "velocity", b["record"], "velocity", b_select=OutputSelection(weights=corners))
            ex.comparisons[f"whole_{n}"] = whole
            cy = mesh.coordinates[mesh.cells].mean(axis=1)[:, 1]
            rows = tuple(int(i) for i in np.flatnonzero(cy < SIDE / 2))
            hdecl = ComparisonDeclaration(f"cell-centre velocity, LOWER HALF y < L/2 (region chosen POST HOC, after the whole-field result), {n}x{n}", "m/s",
                                          "SU2 nodal velocity -> OpenFOAM cell centres by the mean of the 4 cell corners", Quantity(WHOLE_FIELD_TOL * u_lid, "m/s"), 0.0,
                                          f"Re={reynolds:g}, {n}x{n}", post_hoc=True)
            lower = compare_providers(hdecl, a["record"], "velocity", b["record"], "velocity", a_select=OutputSelection(rows=rows), b_select=OutputSelection(rows=rows, weights=corners))
            ex.comparisons[f"lower_{n}"] = lower
            diff = np.linalg.norm(np.asarray(a["cells_xy"]) - cell_from_nodes(b["nodes_xy"], n), axis=1)
            near_lid = np.flatnonzero(cy > 0.9 * SIDE)
            worst = int(np.argmax(np.abs(np.asarray(a["cells_xy"]) - cell_from_nodes(b["nodes_xy"], n)).max(axis=1)))
            outs = {"whole_field_max_difference": OutputValue(Quantity(whole.max_absolute / u_lid, "dimensionless"), UNKNOWN, "compare_providers, of lid speed"),
                    "whole_field_within_tolerance": OutputValue(Quantity(1.0 if whole.within_tolerance else 0.0, "dimensionless"), UNKNOWN, "criterion fixed before the run"),
                    "lower_half_max_difference_post_hoc": OutputValue(Quantity(lower.max_absolute / u_lid, "dimensionless"), UNKNOWN, "POST HOC region"),
                    "max_difference_cell_y": OutputValue(Quantity(float(cy[worst] / SIDE), "dimensionless"), UNKNOWN, "where the two codes differ most, in y/L"),
                    "rms_difference": OutputValue(Quantity(float(np.sqrt((diff**2).mean()) / u_lid), "dimensionless"), UNKNOWN, "of lid speed")}
            return NodeOutcome("succeeded", outs)
        return run

    def convergence(call):
        table = {}
        for p in ("of", "su2"):
            for q in ("ghia_u_max_error", "ghia_v_max_error", "u_center", "v_center"):
                table[f"{q}_{p}"] = [call.value(f"{q}_{p}_{n}").magnitude_in("dimensionless") for n in levels]
        outs = {}
        for p in ("of", "su2"):
            for q in ("ghia_u_max_error", "ghia_v_max_error"):
                seq = table[f"{q}_{p}"]
                outs[f"{q}_{p}_decreasing"] = OutputValue(Quantity(1.0 if all(b < a for a, b in zip(seq, seq[1:])) else 0.0, "dimensionless"), UNKNOWN, "monotone under refinement")
            c = table[f"u_center_{p}"]
            d1, d2 = abs(c[-2] - c[-3]), abs(c[-1] - c[-2])
            order = float(math.log2(d1 / d2)) if d1 > 0 and d2 > 0 else 0.0
            outs[f"u_center_{p}_observed_order"] = OutputValue(Quantity(order, "dimensionless"), UNKNOWN, "log2 of successive changes of u(0.5, 0.5) under halving")
        return NodeOutcome("succeeded", outs)

    cfg = {"side_m": SIDE, "reynolds": reynolds, "ghia": ref.digest, "fluid": "water 20 C 1 atm CoolProp", "openfoam": of_status.version, "su2": su2_status.version}
    of_auth = {n: CallbackAuthority(f"cavity-openfoam-{n}", make_of(n), config={**cfg, "n": n, "steady_tol": STEADY_TOL_M_S, "dt_s": 5.0, "steps": 6000}, kind="provider") for n in levels}
    su2_auth = {n: CallbackAuthority(f"cavity-su2-{n}", make_su2(n), config={**cfg, "n": n, "target": SU2_TARGET, "iterations": SU2_ITERATIONS, "cfl": 50.0}, kind="provider") for n in levels}
    cmp_auth = {n: CallbackAuthority(f"cavity-compare-{n}", make_compare(n), config={**cfg, "n": n, "whole_tol": WHOLE_FIELD_TOL}, deterministic=True) for n in levels}
    conv_auth = CallbackAuthority("cavity-convergence", convergence, config={"levels": list(levels)}, deterministic=True)

    conf = digest_of({"case": tag, "reynolds": reynolds})
    fluid_node = NodeSpec("fluid_properties", NodeKind.PROVIDER_EXECUTION, fluid_auth.ref,
                          tuple(NodeOutputSpec(n, u) for n, u in (("density", "kg/m^3"), ("dynamic_viscosity", "Pa*s"), ("kinematic_viscosity", "m^2/s"), ("lid_velocity", "m/s"))),
                          literals=(LiteralInput("reynolds", Quantity(reynolds, "dimensionless"), Uncertainty.unknown("declared Reynolds number")),
                                    LiteralInput("side", Quantity(SIDE, "m"), Uncertainty.unknown("declared cavity side"))),
                          provider_binding_ids=("coolprop",), configuration_digest=conf)
    nodes = [fluid_node]
    u_inputs = (NodeInput("rho", "fluid_properties", "density", "kg/m^3"), NodeInput("lid_velocity", "fluid_properties", "lid_velocity", "m/s"),
                NodeInput("nu", "fluid_properties", "kinematic_viscosity", "m^2/s"))
    laminar = "laminar Navier-Stokes (adapter refuses Re >= 1000): inside the declared regime for every case this flagship runs"
    for n in levels:
        nodes.append(NodeSpec(f"openfoam_{n}", NodeKind.PROVIDER_EXECUTION, of_auth[n].ref, tuple(NodeOutputSpec(k, u) for k, u in U_OUT), inputs=u_inputs,
                              provider_binding_ids=("openfoam",), applicability_waiver=laminar, configuration_digest=conf))
        nodes.append(NodeSpec(f"su2_{n}", NodeKind.PROVIDER_EXECUTION, su2_auth[n].ref, tuple(NodeOutputSpec(k, u) for k, u in U_OUT), inputs=u_inputs,
                              provider_binding_ids=("su2",), applicability_waiver=laminar, configuration_digest=conf))
        nodes.append(NodeSpec(f"compare_{n}", NodeKind.AGGREGATE, cmp_auth[n].ref,
                              tuple(NodeOutputSpec(k, "dimensionless") for k in ("whole_field_max_difference", "whole_field_within_tolerance", "lower_half_max_difference_post_hoc",
                                                                              "max_difference_cell_y", "rms_difference")),
                              inputs=(NodeInput("ofx", f"openfoam_{n}", "u_center", "dimensionless"), NodeInput("su2x", f"su2_{n}", "u_center", "dimensionless")),
                              configuration_digest=conf))
    conv_inputs = tuple(NodeInput(f"{q}_{p}_{n}", f"{'openfoam' if p == 'of' else 'su2'}_{n}", q, "dimensionless") for p in ("of", "su2") for q in
                        ("ghia_u_max_error", "ghia_v_max_error", "u_center", "v_center") for n in levels)
    conv_out = tuple(NodeOutputSpec(f"{q}_{p}_decreasing", "dimensionless") for p in ("of", "su2") for q in ("ghia_u_max_error", "ghia_v_max_error")) + \
        tuple(NodeOutputSpec(f"u_center_{p}_observed_order", "dimensionless") for p in ("of", "su2"))
    nodes.append(NodeSpec("convergence", NodeKind.AGGREGATE, conv_auth.ref, conv_out, inputs=conv_inputs, configuration_digest=conf))
    obs = [RequestedObservable(k, "fluid_properties", k, u) for k, u in (("density", "kg/m^3"), ("dynamic_viscosity", "Pa*s"), ("kinematic_viscosity", "m^2/s"), ("lid_velocity", "m/s"))]
    for n in levels:
        for prov in ("openfoam", "su2"):
            obs += [RequestedObservable(f"{k}_{prov}_{n}", f"{prov}_{n}", k, u) for k, u in U_OUT]
        obs += [RequestedObservable(f"{k}_{n}", f"compare_{n}", k, "dimensionless") for k in ("whole_field_max_difference", "whole_field_within_tolerance", "lower_half_max_difference_post_hoc",
                                                                                              "max_difference_cell_y", "rms_difference")]
    obs += [RequestedObservable(s.name, "convergence", s.name, "dimensionless") for s in conv_out]
    cdig = digest_of(flux_c.to_dict())
    finest = levels[-1]
    cobs = tuple(ConstraintObservation(f"b_flux_{prov}", "max_midplane_flux", cdig, f"flux_residual_abs_{prov}_{finest}") for prov in ("openfoam", "su2"))
    scenario = ScenarioSpecification(f"cavity-{tag}", "1", Quantity(0, "s"), Quantity(1, "s"), segments=(ScenarioSegment("steady", Quantity(0, "s"), Quantity(1, "s")),))
    timeline = Timeline.from_scenario(scenario, timeline_id=f"cavity-{tag}", basis=TimeBasis("cavity", "elapsed", "start"), histories=())
    initial = InitialStateSpec(Quantity(0, "s"), (OwnerState("cavity", "component", (InitialStateValue("reference", Quantity(0.0, "dimensionless"), Uncertainty.unknown("declared placeholder")),)),))
    bindings = (ProviderBinding("coolprop", "coolprop", cp_status.version, cp_status.digest), ProviderBinding("openfoam", "openfoam", of_status.version, of_status.digest),
                ProviderBinding("su2", "su2", su2_status.version, su2_status.digest))
    request = SystemRunRequest.build(
        request_id=f"flagship-c-cavity-cfd-{tag}", system=system, scenario=scenario, timeline=timeline, environment=None, initial_state=initial, nodes=tuple(nodes),
        observables=tuple(obs), model_selections=(ModelSelection("cavity", "incompressible-laminar-navier-stokes", "1"),), provider_bindings=bindings, constraint_observations=cobs,
        profile=ExecutionProfile((), "off", True, ()), environment_absent_reason="steady lid-driven cavity: all conditions are declared boundary conditions; no environment channel is read")
    authorities = AuthorityRegistry((fluid_auth, *of_auth.values(), *su2_auth.values(), *cmp_auth.values(), conv_auth))
    context = RuntimeContext(authorities, system=system, scenario=scenario, timeline=timeline, environment=None, constraints={cdig: flux_c}, providers=registry)
    return Cavity(request, context, ex, ref, reynolds, levels, registry)


# ==================================================================================================== verification, reference comparison, summary
@dataclass
class CavityRun:
    cavity: Cavity
    result: Any
    preflight: Any
    constraints: tuple
    summary: Any = None
    ladder: Any = None
    comparisons: tuple = ()
    references: tuple = ()
    uncertainty: Any = None
    table: dict = field(default_factory=dict)
    l2_failing: tuple = ()


def _obs(result, oid) -> float | None:
    o = result.observable(oid)
    return None if o.value is None else o.value.value.magnitude


def run_cavity(reynolds: float = REYNOLDS, levels: tuple[int, ...] = LEVELS, registry=None, *, tag: str = "re100") -> CavityRun:
    from engcore.system_runtime import SystemExecutor, assess_constraints, compile_plan, preflight

    cv = build_cavity(reynolds, levels, registry, tag=tag)
    report = preflight(cv.request, compile_plan(cv.request), cv.context)
    result = SystemExecutor(cv.context).run(cv.request)
    constraints = assess_constraints(result, cv.context.system, cv.context.constraints)
    run = CavityRun(cv, result, report, constraints)
    ref = cv.reference
    finest = levels[-1]
    entries = [contract_integrity_entry(report, result)]
    # ---- level 2: mass conservation of the sampled mid-plane profiles, criterion FLUX_TOL fixed before the run
    flux = {p: max(abs(x) if x is not None else math.inf for x in (_obs(result, f"u_flux_residual_{p}_{finest}"), _obs(result, f"v_flux_residual_{p}_{finest}"))) for p in ("openfoam", "su2")}
    l2_ok = all(v <= FLUX_TOL for v in flux.values())
    l2_failing = sorted(p for p, v in flux.items() if not v <= FLUX_TOL)
    run.l2_failing = tuple(l2_failing)
    flux_record = {p: (None if math.isinf(v) else v) for p, v in flux.items()}          # None = the profile was not produced (never a pass)
    entries.append(LevelEntry(2, LevelStatus.REACHED if l2_ok else LevelStatus.ATTEMPTED_NOT_REACHED,
                              (EvidenceLink.of_record("midplane_flux", {"mesh": f"{finest}x{finest}", "max_abs_net_flux_over_UL": flux_record, "criterion": FLUX_TOL},
                                                      "conservation_residual", "met" if l2_ok else "not_met", f"net flux / (U L) at {finest}x{finest}: {flux_record}"),),
                              f"net flux through each mid-plane relative to U L (criterion {FLUX_TOL:g}, fixed before the run): {flux}"
                              + ("" if l2_ok else f". NOT MET by {l2_failing} (its sampled profile is not mass-conserving to the criterion; cause not investigated)")))
    entries.append(LevelEntry(3, LevelStatus.NOT_AVAILABLE, (), "there is no closed-form solution of the cavity at Re = 100 to compare with"))
    # ---- level 4: PREDECLARED criterion = error against the benchmark decreases monotonically under refinement (fixed before the first run).
    # That criterion is BENCHMARK-RELATIVE: it mixes each code's discretisation error with the benchmark's own truncation error, so it is a weak stand-in for convergence.
    decs = {f"{q}_{p}": _obs(result, f"{q}_{p}_decreasing") for p in ("of", "su2") for q in ("ghia_u_max_error", "ghia_v_max_error")}
    if all(v is not None for v in decs.values()):
        ok = all(v == 1.0 for v in decs.values())
        orders = {p: _obs(result, f"u_center_{p}_observed_order") for p in ("of", "su2")}
        links4 = [EvidenceLink.of_record("grid_study", {"levels": list(levels), "monotone_decrease_flags": decs}, "discretisation_convergence", "met" if ok else "not_met", f"monotone decrease flags {decs}")]
        if not ok:
            seq = {p: [_obs(result, f"u_center_{prov}_{n}") for n in levels] for p, prov in (("of", "openfoam"), ("su2", "su2"))}
            intrinsic = all(orders[p] is not None and orders[p] >= INTRINSIC_ORDER_MIN for p in orders) and all(abs(s[-1] - s[-2]) < abs(s[-2] - s[-3]) for s in seq.values())
            links4.append(EvidenceLink.of_record("grid_study_intrinsic_post_hoc", {"orders": orders, "seq": seq}, "post_hoc_discretisation_convergence", "met" if intrinsic else "not_met",
                                                 f"POST HOC intrinsic reading (added after seeing the outcome): u(0.5, 0.5)/U over {list(levels)}: {seq}, observed orders {orders}"))
        entries.append(LevelEntry(4, LevelStatus.REACHED if ok else LevelStatus.ATTEMPTED_NOT_REACHED, tuple(links4),
                                  f"{list(levels)} cells per side. Predeclared criterion (max centerline error against the BENCHMARK decreases monotonically for both codes and both lines): "
                                  + ("MET" if ok else f"NOT MET - flags {decs}") + ". It is benchmark-relative, so it also folds in the benchmark's own truncation error; "
                                  "an intrinsic reading (successive changes of a fixed quantity) is recorded beside it as post hoc, never in its place"))
    else:
        entries.append(LevelEntry(4, LevelStatus.NOT_ATTEMPTED, (), "the convergence aggregate was not produced"))
    # ---- level 5: whole-field OpenFOAM vs SU2, pre-declared 3 % of lid speed at every level; the lower-half comparison is post hoc
    flags = {n: _obs(result, f"whole_field_within_tolerance_{n}") for n in levels}
    if all(v is not None for v in flags.values()):
        ok = all(v == 1.0 for v in flags.values())
        links = [EvidenceLink.of_provider_comparison(cv.exchange.comparisons[f"whole_{n}"],
                                                     f"whole field {n}x{n}: max difference {_obs(result, f'whole_field_max_difference_{n}'):.4f} of lid speed at y/L={_obs(result, f'max_difference_cell_y_{n}'):.3f}")
                 for n in levels]
        if not ok:       # post-hoc readings sit beside a level that is NOT reached; they can never be attached to a reached one
            links += [EvidenceLink.of_provider_comparison(cv.exchange.comparisons[f"lower_{n}"], f"POST HOC lower half {n}x{n}") for n in levels]
        entries.append(LevelEntry(5, LevelStatus.REACHED if ok else LevelStatus.ATTEMPTED_NOT_REACHED, tuple(links),
                                  "OpenFOAM vs SU2 on identical declared inputs, whole field, 3 % of lid speed fixed before any run (the BIG 11 criterion, not loosened): "
                                  + ("MET at every level" if ok else "NOT MET - the codes disagree, most near the lid; the disagreement is the result")
                                  + ". The lower-half comparisons were chosen after seeing this and are recorded as post hoc observations only"))
    else:
        entries.append(LevelEntry(5, LevelStatus.NOT_ATTEMPTED, (), "no whole-field comparison was produced"))
    # ---- level 6: Ghia et al., a NUMERICAL benchmark, judged only if it applies
    comparisons, references = [], []
    conditions = {"reynolds": Quantity(reynolds, "dimensionless"), "cavity_aspect_ratio": Quantity(1.0, "dimensionless")}          # the flagship's own declared square cavity
    links6 = []
    finest_ok: dict[str, bool] = {}
    for prov in ("openfoam", "su2"):
        eu, ev = _obs(result, f"ghia_u_max_error_{prov}_{finest}"), _obs(result, f"ghia_v_max_error_{prov}_{finest}")
        if eu is None or ev is None:
            continue
        crit = PredeclaredCriterion(f"ghia_{prov}_{finest}", "centerline_velocity_over_lid_speed", "max_absolute_error", Quantity(GHIA_TOL, "dimensionless"),
                                    "flagships/forge_flagships/cavity_cfd.py:GHIA_TOL (fixed before the first run)")
        cmp_ = compare_to_reference(ref, crit, conditions, value=Quantity(max(eu, ev), "dimensionless"), compared_identity=result.receipt(f"{prov}_{finest}").execution_identity_digest,
                                    note=f"{prov} {finest}x{finest}: max |u - Ghia| = {eu:.4f}, max |v - Ghia| = {ev:.4f} (of lid speed)")
        comparisons.append(cmp_)
        references.append(ref)
        links6.append(EvidenceLink.of_comparison(cmp_))
        finest_ok[prov] = cmp_.outcome == "met"
    if comparisons and all(c.outcome == "not_applicable" for c in comparisons):
        entries.append(LevelEntry(6, LevelStatus.NOT_AVAILABLE, tuple(links6), f"the benchmark does not apply to Re = {reynolds:g} (its envelope is Re = 100): not compared, neither met nor unmet"))
    elif comparisons:
        ok = all(finest_ok.values()) and len(finest_ok) == 2
        entries.append(LevelEntry(6, LevelStatus.REACHED if ok else LevelStatus.ATTEMPTED_NOT_REACHED, tuple(links6),
                                  f"Ghia et al. (1982) Re = 100 centerlines, a NUMERICAL benchmark, at the finest mesh, tolerance {GHIA_TOL:g} of lid speed fixed before the run: {finest_ok}. "
                                  "Agreement would support this configuration's numerics only; it is not experimental validation"))
    else:
        entries.append(LevelEntry(6, LevelStatus.NOT_ATTEMPTED, (), "no provider produced centerline data"))
    entries.append(LevelEntry(7, LevelStatus.NOT_AVAILABLE, (), "no experimental data for this cavity was integrated"))
    run.ladder = VerificationLadder.of(**{f"l{e.level}": e for e in entries})
    run.comparisons, run.references = tuple(comparisons), tuple(dict.fromkeys(references))
    run.uncertainty = UncertaintyStatement(
        (), ("fluid state (declared 20 degC, 1 atm)", "lid speed and cavity size (declared)", "water density and viscosity: CoolProp equation-of-state values, uncertainty not propagated"),
        "NOT QUANTIFIED: incompressible laminar model, 2-D idealisation, no discretisation-error bound (only a grid study), each code's own scheme error",
        ("water density / viscosity: provider-derived CoolProp records (not measurements)",),
        f"laminar regime declared for Re < 1000 by both adapters; this case has Re = {reynolds:g}", f"Ghia et al. (1982) applies at Re = 100 only; this case is Re = {reynolds:g}")
    ex = cv.exchange
    ladder_levels = [f"{n}x{n}" for n in levels]
    outputs = [("Water density", "density"), ("Lid velocity for the declared Re", "lid_velocity")]
    for n in levels:
        outputs += [(f"OpenFOAM max centerline error vs Ghia {n}x{n}", f"ghia_u_max_error_openfoam_{n}"), (f"SU2 max u-centerline error vs Ghia {n}x{n}", f"ghia_u_max_error_su2_{n}"),
                    (f"OpenFOAM vs SU2 whole-field max difference {n}x{n} (of lid speed)", f"whole_field_max_difference_{n}"),
                    (f"...where the two differ most (y/L) {n}x{n}", f"max_difference_cell_y_{n}")]
    outputs += [(f"OpenFOAM u(0.5,0.5)/U {finest}x{finest}", f"u_center_openfoam_{finest}"), (f"SU2 u(0.5,0.5)/U {finest}x{finest}", f"u_center_su2_{finest}"),
                (f"OpenFOAM vortex centre x/L {finest}x{finest}", f"vortex_x_openfoam_{finest}"), (f"OpenFOAM vortex centre y/L {finest}x{finest}", f"vortex_y_openfoam_{finest}"),
                (f"SU2 vortex centre x/L {finest}x{finest}", f"vortex_x_su2_{finest}"), (f"SU2 vortex centre y/L {finest}x{finest}", f"vortex_y_su2_{finest}")]
    outputs = [(l, o) for l, o in outputs if not result.observable(o).availability.value == "unavailable"]
    trace_id = f"ghia_u_max_error_openfoam_{finest}" if _obs(result, f"ghia_u_max_error_openfoam_{finest}") is not None else "density"
    run.summary = build_summary(f"Lid-driven cavity, Re = {reynolds:g}, water 20 degC, {ladder_levels} cells ({tag})", cv.request, result, outputs=outputs, constraints=constraints,
                                ladder=run.ladder, comparisons=comparisons, references=run.references, uncertainty=run.uncertainty, trace_observable=trace_id,
                                notes=("OpenFOAM and SU2 receive identical declared geometry, fluid records, Reynolds number and comparison quantities",
                                       "the whole-field disagreement between the two codes is preserved, not tuned away"))
    return run


def negative_controls(registry=None) -> dict:
    """(a) a regime the adapters refuse; (b) a benchmark that does not apply to the case.  Both through BIG 12."""
    from engcore.system_runtime import SystemExecutor

    out = {}
    cv = build_cavity(1500.0, (20,), registry, tag="re1500")
    res = SystemExecutor(cv.context).run(cv.request)
    out["unsupported_regime"] = {"status": res.status.value, "openfoam": res.receipt("openfoam_20").status.value, "reason": res.receipt("openfoam_20").reason,
                                 "su2": res.receipt("su2_20").status.value, "outputs_available": [o.observable_id for o in res.observables if o.availability.value == "available"
                                                                                                   and o.observable_id.startswith(("ghia", "whole"))]}
    ref, _ = load_ghia()
    cmp_ = compare_to_reference(ref, PredeclaredCriterion("ghia_wrong_re", "centerline_velocity_over_lid_speed", "max_absolute_error", Quantity(GHIA_TOL, "dimensionless"),
                                                          "flagships/forge_flagships/cavity_cfd.py:GHIA_TOL"),
                                {"reynolds": Quantity(10.0, "dimensionless")}, value=Quantity(0.0, "dimensionless"), compared_identity=sha("re10"))
    out["benchmark_not_applicable"] = {"outcome": cmp_.outcome, "applicability": cmp_.applicability.to_dict(), "value_ignored": cmp_.value.magnitude}
    return out
