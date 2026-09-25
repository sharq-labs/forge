"""OpenFOAM CFD provider (BIG 11), process-based, deliberately bounded.

Exactly one case family: the 2-D lid-driven square cavity, incompressible,
laminar, Newtonian, solved with ``icoFoam`` (PISO).  Every dictionary
(blockMeshDict, controlDict, fvSchemes, fvSolution, transportProperties, 0/U,
0/p) is generated from the Forge :class:`CavityProblem` and bound by content
into the execution identity; the provider environment is built explicitly from
the provider prefix and recorded.  This is not "arbitrary CFD support".

Scientific semantics recorded with every execution (see :data:`SEMANTICS`):
governing model, laminar choice, incompressibility, fluid-property source, BCs,
schemes, solver controls.  Successful completion is not evidence that any of
those choices is valid; the adapter only refuses the laminar choice outside its
DECLARED Reynolds bound.

Results: velocity and kinematic pressure (p/rho, m^2/s^2) at the final time as
BIG 7 cell fields on a Forge quadrilateral mesh whose cell centres are verified
against OpenFOAM's own ``writeCellCentres`` output before any value is mapped.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass

import numpy as np

from engcore.providers import (
    GeneratedFile, ProcessInvocation, ProcessWorkspace, ProviderExecutionIdentity, ProviderExecutionRecord, ProviderRefusal, failed,
)
from engcore.providers.catalog import _sha256_file
from engcore.scientific.units.quantity import Quantity

ADAPTER = ("forge_openfoam", "0.1")
LAMINAR_RE_BOUND = 1000.0
SEMANTICS = {
    "governing_model": "incompressible Navier-Stokes, Newtonian, constant kinematic viscosity",
    "flow_regime": "laminar (no turbulence model); adapter refuses Re >= %g (declared bound, not validation)" % LAMINAR_RE_BOUND,
    "compressibility": "incompressible (kinematic pressure p/rho)",
    "pressure_output": "kinematic pressure p/rho in m^2/s^2, defined up to a constant: pRefCell 0, pRefValue 0 "
                       "(closed cavity); NOT a thermodynamic or gauge pressure in Pa",
    "time_state": "the icoFoam state at endTime; it is called steady only when a declared steady_tolerance "
                  "bounds max|dU| over the last write interval",
    "solver": "icoFoam (PISO, transient, time-marched to endTime)",
    "boundary_conditions": "lid: fixedValue (U_lid, 0, 0); walls: noSlip; front/back: empty; p: zeroGradient walls",
    "schemes": "Euler; Gauss linear; Gauss linear corrected",
}


def openfoam_environment(prefix: str) -> dict[str, str]:
    """The explicit, recorded environment an OpenFOAM (conda) executable needs; nothing is inherited."""
    e = {"WM_PROJECT": "OpenFOAM", "WM_PROJECT_DIR": prefix, "FOAM_ETC": f"{prefix}/etc", "FOAM_APPBIN": f"{prefix}/bin",
         "FOAM_LIBBIN": f"{prefix}/lib", "FOAM_SITE_APPBIN": f"{prefix}/bin", "FOAM_SITE_LIBBIN": f"{prefix}/lib",
         "FOAM_USER_APPBIN": f"{prefix}/bin", "FOAM_USER_LIBBIN": f"{prefix}/lib", "WM_ARCH": "linux64", "WM_COMPILER": "Gcc",
         "WM_PRECISION_OPTION": "DP", "WM_LABEL_SIZE": "32", "WM_COMPILE_OPTION": "Opt", "WM_OPTIONS": "linux64GccDPInt32Opt",
         "WM_MPLIB": "MPICH", "FOAM_MPI": "sys-mpich", "LD_LIBRARY_PATH": f"{prefix}/lib", "PATH": f"{prefix}/bin:/usr/bin:/bin",
         "HOME": "/tmp", "LC_ALL": "C", "OMP_NUM_THREADS": "1"}
    return e


@dataclass(frozen=True)
class CavityProblem:
    case_id: str
    side: Quantity
    cells: int
    lid_velocity: Quantity
    kinematic_viscosity: Quantity
    viscosity_provenance: tuple[tuple[str, str], ...]
    end_time: Quantity
    delta_t: Quantity
    write_steps: int = 50
    p_tolerance: float = 1e-8
    u_tolerance: float = 1e-8
    n_correctors: int = 2
    #: max |dU| over the last write interval (m/s) below which the end state is
    #: reported as steady; None = no steadiness is claimed (transient end state)
    steady_tolerance: Quantity | None = None

    def __post_init__(self) -> None:
        if not (4 <= self.cells <= 400):
            raise ProviderRefusal("cavity resolution outside the adapter's bounded range 4..400")
        if not self.viscosity_provenance:
            raise ProviderRefusal("the fluid viscosity must carry provenance (a property record or a declaration)")
        if self.reynolds >= LAMINAR_RE_BOUND:
            raise ProviderRefusal(f"Re = {self.reynolds:.4g} >= {LAMINAR_RE_BOUND:g}: the laminar icoFoam choice is refused")
        steps = self.end_time.to("s").magnitude / self.delta_t.to("s").magnitude
        if abs(steps - round(steps)) > 1e-9 or round(steps) % self.write_steps:
            raise ProviderRefusal("endTime must be a whole number of write intervals")

    @property
    def reynolds(self) -> float:
        return self.lid_velocity.to("m/s").magnitude * self.side.to("m").magnitude / self.kinematic_viscosity.to("m^2/s").magnitude

    def to_dict(self) -> dict:
        return {"case_id": self.case_id, "side_m": repr(float(self.side.to("m").magnitude)), "cells": self.cells,
                "lid_m_s": repr(float(self.lid_velocity.to("m/s").magnitude)), "nu_m2_s": repr(float(self.kinematic_viscosity.to("m^2/s").magnitude)),
                "viscosity_provenance": [list(x) for x in self.viscosity_provenance], "end_s": repr(float(self.end_time.to("s").magnitude)),
                "dt_s": repr(float(self.delta_t.to("s").magnitude)), "write_steps": self.write_steps, "p_tol": repr(self.p_tolerance),
                "u_tol": repr(self.u_tolerance), "nCorrectors": self.n_correctors,
                "steady_tolerance_m_s": None if self.steady_tolerance is None else repr(float(self.steady_tolerance.to("m/s").magnitude))}


_HEADER = "FoamFile\n{{\n    version 2.0;\n    format ascii;\n    class {cls};\n    object {obj};\n}}\n"


def generate_case(problem: CavityProblem, tag: str) -> dict[str, str]:
    L = float(problem.side.to("m").magnitude)
    N = problem.cells
    dz = L / N
    U = float(problem.lid_velocity.to("m/s").magnitude)
    nu = float(problem.kinematic_viscosity.to("m^2/s").magnitude)
    dt = float(problem.delta_t.to("s").magnitude)
    end = float(problem.end_time.to("s").magnitude)
    head = lambda cls, obj: f"// Forge execution {tag}\n" + _HEADER.format(cls=cls, obj=obj)  # noqa: E731
    return {
        "system/blockMeshDict": head("dictionary", "blockMeshDict") + f"""scale 1;
vertices ( (0 0 0) ({L!r} 0 0) ({L!r} {L!r} 0) (0 {L!r} 0) (0 0 {dz!r}) ({L!r} 0 {dz!r}) ({L!r} {L!r} {dz!r}) (0 {L!r} {dz!r}) );
blocks ( hex (0 1 2 3 4 5 6 7) ({N} {N} 1) simpleGrading (1 1 1) );
edges ();
boundary
(
    movingWall {{ type wall; faces ( (3 7 6 2) ); }}
    fixedWalls {{ type wall; faces ( (0 4 7 3) (2 6 5 1) (1 5 4 0) ); }}
    frontAndBack {{ type empty; faces ( (0 3 2 1) (4 5 6 7) ); }}
);
mergePatchPairs ();
""",
        "system/controlDict": head("dictionary", "controlDict") + f"""application icoFoam;
startFrom startTime; startTime 0; stopAt endTime; endTime {end!r}; deltaT {dt!r};
writeControl timeStep; writeInterval {problem.write_steps}; purgeWrite 0; writeFormat ascii; writePrecision 12;
writeCompression off; timeFormat general; timePrecision 12; runTimeModifiable false;
""",
        "system/fvSchemes": head("dictionary", "fvSchemes") + """ddtSchemes { default Euler; }
gradSchemes { default Gauss linear; grad(p) Gauss linear; }
divSchemes { default none; div(phi,U) Gauss linear; }
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes { default corrected; }
""",
        "system/fvSolution": head("dictionary", "fvSolution") + f"""solvers
{{
    p {{ solver PCG; preconditioner DIC; tolerance {problem.p_tolerance!r}; relTol 0.05; }}
    pFinal {{ $p; relTol 0; }}
    U {{ solver smoothSolver; smoother symGaussSeidel; tolerance {problem.u_tolerance!r}; relTol 0; }}
}}
PISO {{ nCorrectors {problem.n_correctors}; nNonOrthogonalCorrectors 0; pRefCell 0; pRefValue 0; }}
""",
        "constant/transportProperties": head("dictionary", "transportProperties") + f"transportModel Newtonian;\nnu {nu!r};\n",
        "0/U": head("volVectorField", "U") + f"""dimensions [0 1 -1 0 0 0 0];
internalField uniform (0 0 0);
boundaryField
{{
    movingWall {{ type fixedValue; value uniform ({U!r} 0 0); }}
    fixedWalls {{ type noSlip; }}
    frontAndBack {{ type empty; }}
}}
""",
        "0/p": head("volScalarField", "p") + """dimensions [0 2 -2 0 0 0 0];
internalField uniform 0;
boundaryField
{
    movingWall { type zeroGradient; }
    fixedWalls { type zeroGradient; }
    frontAndBack { type empty; }
}
""",
    }


def _parse_internal(text: str, n: int, vector: bool) -> np.ndarray:
    m = re.search(r"internalField\s+nonuniform\s+List<(vector|scalar)>\s*(\d+)\s*\(", text)
    if not m or int(m.group(2)) != n:
        raise ProviderRefusal("OpenFOAM field file lacks a complete nonuniform internalField")
    body = text[m.end():]
    if vector:
        vals = re.findall(r"\(\s*([^\s()]+)\s+([^\s()]+)\s+([^\s()]+)\s*\)", body)[:n]
        arr = np.array(vals, dtype=float)
    else:
        arr = np.array(body.split(")")[0].split(), dtype=float)
    if arr.shape[0] != n or not np.all(np.isfinite(arr)):
        raise ProviderRefusal("OpenFOAM field is incomplete or non-finite")
    return arr


def cavity_mesh(problem: CavityProblem):
    """Forge 2-D quadrilateral mesh of the declared grid (blockMesh cell order: x fastest)."""
    from engcore.spatial.mesh import CellType, CoordinateFrame, GroupKind, PhysicalGroup, SpatialMesh

    L, N = float(problem.side.to("m").magnitude), problem.cells
    xs = np.linspace(0.0, L, N + 1)
    coords = np.array([(x, y) for y in xs for x in xs])
    node = lambda i, j: j * (N + 1) + i  # noqa: E731
    cells = np.array([(node(i, j), node(i + 1, j), node(i + 1, j + 1), node(i, j + 1)) for j in range(N) for i in range(N)])
    return SpatialMesh(coordinates=coords, cells=cells, cell_type=CellType.QUADRILATERAL,
                       frame=CoordinateFrame("cavity-xy", 2, description="cavity plane"), cell_tags=np.ones(len(cells), dtype=int),
                       groups=(PhysicalGroup("fluid", GroupKind.CELLS, 1),))


class OpenFOAMProvider:
    def __init__(self, registry, *, timeout_s: float = 1800.0, workspace_root: str | None = None) -> None:
        self.status = registry.require("openfoam")
        self.prefix = os.path.dirname(os.path.dirname(self.status.location))
        self.timeout_s, self.workspace_root = timeout_s, workspace_root

    def run_cavity(self, problem: CavityProblem, *, preexisting: dict | None = None) -> tuple[ProviderExecutionRecord, dict]:
        from engcore.spatial import Derivation, Location, Rank, SpatialField, SpatialFieldDefinition

        bindir = os.path.join(self.prefix, "bin")
        exes = {name: os.path.realpath(os.path.join(bindir, name)) for name in ("blockMesh", "icoFoam", "postProcess")}
        env = tuple(sorted(openfoam_environment(self.prefix).items()))
        configuration = {"semantics": SEMANTICS, "executables": {k: _sha256_file(v) for k, v in exes.items()},
                         "environment": [list(x) for x in env if x[0] not in ("PATH", "LD_LIBRARY_PATH", "WM_PROJECT_DIR") and "/" not in x[1]]}
        base = ProviderExecutionIdentity.from_content(self.status, adapter_id=ADAPTER[0], adapter_version=ADAPTER[1],
                                                      problem=problem.to_dict(), configuration=configuration, output_request=("velocity", "pressure"))
        t0 = time.perf_counter()
        case = generate_case(problem, base.digest)
        identity = ProviderExecutionIdentity.from_content(self.status, adapter_id=ADAPTER[0], adapter_version=ADAPTER[1],
                                                          problem=problem.to_dict(), configuration=configuration, inputs=case,
                                                          output_request=("velocity", "pressure"))
        files = tuple(GeneratedFile(k, v.encode()) for k, v in sorted(case.items()))
        end = float(problem.end_time.to("s").magnitude)
        steps = (ProcessInvocation(exes["blockMesh"], _sha256_file(exes["blockMesh"]), self.status.version, (), files, env, self.timeout_s,
                                   ("constant/polyMesh/points", "constant/polyMesh/owner")),
                 ProcessInvocation(exes["icoFoam"], self.status.executable_digest, self.status.version, (), files, env, self.timeout_s, ()),
                 ProcessInvocation(exes["postProcess"], _sha256_file(exes["postProcess"]), self.status.version,
                                   ("-func", "writeCellCentres", "-time", f"{end:g}"), files, env, self.timeout_s, ()))
        ws = ProcessWorkspace(self.workspace_root, preexisting=preexisting)
        try:
            t1 = time.perf_counter()
            rec = ws.run_sequence(steps)
            t2 = time.perf_counter()
            if not rec.completed:
                return failed(identity, f"OpenFOAM sequence did not complete: steps {list(rec.steps)}; {rec.stdout_tail[-300:]}",
                              process_digest=rec.digest, artifacts=case), {}
            times = sorted({float(n.split("/")[0]) for n in ws.outputs_matching(r"[0-9.eE+-]+/U")})
            if not times or abs(times[-1] - end) > 1e-9 * max(1.0, end):
                return failed(identity, f"icoFoam did not write the end time {end:g} (wrote {times[-3:]})", process_digest=rec.digest), {}
            tname = next(n.split("/")[0] for n in ws.outputs_matching(r"[0-9.eE+-]+/U") if float(n.split("/")[0]) == times[-1])
            n = problem.cells ** 2
            U = _parse_internal(ws.read_output(f"{tname}/U").decode(), n, True)
            p = _parse_internal(ws.read_output(f"{tname}/p").decode(), n, False)
            C = _parse_internal(ws.read_output(f"{tname}/C").decode(), n, True)
            prev = [t for t in times if t < times[-1]]
            steady = None
            if prev:
                pname = next(x.split("/")[0] for x in ws.outputs_matching(r"[0-9.eE+-]+/U") if float(x.split("/")[0]) == prev[-1])
                steady = float(np.abs(_parse_internal(ws.read_output(f"{pname}/U").decode(), n, True) - U).max())
            t3 = time.perf_counter()
        finally:
            ws.cleanup()
        if problem.steady_tolerance is not None:
            tol = float(problem.steady_tolerance.to("m/s").magnitude)
            if steady is None or not steady <= tol:
                return failed(identity, f"declared steadiness not reached: max|dU| over the last write interval = {steady!r} m/s "
                                        f"> {tol!r} m/s", process_digest=rec.digest), {}
        mesh = cavity_mesh(problem)
        centres = mesh.coordinates[mesh.cells].mean(axis=1)
        if not np.allclose(C[:, :2], centres, rtol=0, atol=1e-9 * float(problem.side.to("m").magnitude)):
            return failed(identity, "OpenFOAM cell centres do not match the Forge mesh; values are not mapped"), {}
        if np.abs(U[:, 2]).max() > 1e-12 * max(1.0, np.abs(U).max()):
            return failed(identity, "non-zero out-of-plane velocity in a 2-D case"), {}
        record = ProviderExecutionRecord(identity, True, "", arrays={"velocity": ("m/s", U[:, :2]), "pressure": ("m^2/s^2", p)},
                                         artifacts=case, process_digest=rec.digest,
                                         metrics={"generate_s": t1 - t0, "process_s": t2 - t1, "parse_s": t3 - t2, "cells": n,
                                                  "time_steps": int(round(end / float(problem.delta_t.to("s").magnitude))),
                                                  "steadiness_max_dU_last_interval_m_s": steady, "reynolds": problem.reynolds,
                                                  "end_state": "transient" if problem.steady_tolerance is None else "steady_by_declared_tolerance"})
        prov = (f"openfoam_execution:{identity.digest}", f"process:{rec.digest}")
        fields = {"velocity": SpatialField(SpatialFieldDefinition("U", "velocity", "m/s", Location.CELL, Rank.VECTOR, frame_id="cavity-xy"),
                                           mesh, U[:, :2], Derivation.COMPUTED, prov),
                  "pressure": SpatialField(SpatialFieldDefinition("p_kin", "kinematic_pressure", "m^2/s^2", Location.CELL, Rank.SCALAR),
                                           mesh, p, Derivation.COMPUTED, prov)}
        return record, fields
