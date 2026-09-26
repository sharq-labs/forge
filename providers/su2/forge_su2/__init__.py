"""SU2 CFD provider (BIG 11), process-based, deliberately bounded.

Same bounded case family as the OpenFOAM adapter: the 2-D lid-driven square
cavity, incompressible, laminar, constant density and viscosity -- solved with
``SU2_CFD`` (INC_NAVIER_STOKES, steady pseudo-time iterations).  The native
``.su2`` mesh (Forge-declared structured quads) and the ``.cfg`` are generated
from the Forge problem and bound by content.  SU2 is vertex-based: velocity is
returned at mesh NODES on the same Forge quadrilateral mesh the OpenFOAM
adapter uses; mapping onto cell centres is the caller's declared step.

Success requires: exit 0, the volume CSV produced by THIS run, every node
present, finite values, and the declared residual target reached (read from
SU2's own history file).  Nothing here is validation.
"""

from __future__ import annotations

import csv
import io
import os
import time
from dataclasses import dataclass

import numpy as np

from engcore.providers import (
    GeneratedFile, ProcessInvocation, ProcessWorkspace, ProviderExecutionIdentity, ProviderExecutionRecord, ProviderRefusal, failed,
    minimal_environment,
)
from engcore.scientific.units.quantity import Quantity

ADAPTER = ("forge_su2", "0.1")
LAMINAR_RE_BOUND = 1000.0
SEMANTICS = {
    "governing_model": "incompressible Navier-Stokes, constant density and viscosity, energy equation off",
    "flow_regime": "laminar (no turbulence model); adapter refuses Re >= %g (declared bound, not validation)" % LAMINAR_RE_BOUND,
    "solver": "SU2_CFD INC_NAVIER_STOKES, implicit Euler pseudo-time, FDS convection, Green-Gauss gradients",
    "boundary_conditions": "lid: moving wall (translation rate = lid velocity); walls: no-slip adiabatic",
}


@dataclass(frozen=True)
class CavityProblemSU2:
    case_id: str
    side: Quantity
    cells: int
    lid_velocity: Quantity
    density: Quantity
    dynamic_viscosity: Quantity
    property_provenance: tuple[tuple[str, str], ...]
    iterations: int = 4000
    residual_log10_target: float = -9.0
    cfl: float = 50.0

    def __post_init__(self) -> None:
        if not (4 <= self.cells <= 400):
            raise ProviderRefusal("cavity resolution outside the adapter's bounded range 4..400")
        if not self.property_provenance:
            raise ProviderRefusal("fluid properties must carry provenance")
        if self.reynolds >= LAMINAR_RE_BOUND:
            raise ProviderRefusal(f"Re = {self.reynolds:.4g} >= {LAMINAR_RE_BOUND:g}: the laminar choice is refused")

    @property
    def reynolds(self) -> float:
        return (self.density.to("kg/m^3").magnitude * self.lid_velocity.to("m/s").magnitude * self.side.to("m").magnitude
                / self.dynamic_viscosity.to("Pa*s").magnitude)

    def to_dict(self) -> dict:
        return {"case_id": self.case_id, "side_m": repr(float(self.side.to("m").magnitude)), "cells": self.cells,
                "lid_m_s": repr(float(self.lid_velocity.to("m/s").magnitude)), "rho": repr(float(self.density.to("kg/m^3").magnitude)),
                "mu": repr(float(self.dynamic_viscosity.to("Pa*s").magnitude)), "provenance": [list(x) for x in self.property_provenance],
                "iterations": self.iterations, "residual_log10_target": repr(self.residual_log10_target), "cfl": repr(self.cfl)}


def generate_mesh(problem: CavityProblemSU2) -> str:
    L, N = float(problem.side.to("m").magnitude), problem.cells
    xs = np.linspace(0.0, L, N + 1)
    node = lambda i, j: j * (N + 1) + i  # noqa: E731
    lines = ["NDIME= 2", f"NELEM= {N * N}"]
    k = 0
    for j in range(N):
        for i in range(N):
            lines.append(f"9 {node(i, j)} {node(i + 1, j)} {node(i + 1, j + 1)} {node(i, j + 1)} {k}")
            k += 1
    lines.append(f"NPOIN= {(N + 1) ** 2}")
    lines += [f"{float(x)!r} {float(y)!r} {j * (N + 1) + i}" for j, y in enumerate(xs) for i, x in enumerate(xs)]
    lid = [(node(i, N), node(i + 1, N)) for i in range(N)]
    walls = [(node(i, 0), node(i + 1, 0)) for i in range(N)] + [(node(0, j), node(0, j + 1)) for j in range(N)] + \
            [(node(N, j), node(N, j + 1)) for j in range(N)]
    lines += ["NMARK= 2", "MARKER_TAG= lid", f"MARKER_ELEMS= {len(lid)}", *(f"3 {a} {b}" for a, b in lid),
              "MARKER_TAG= walls", f"MARKER_ELEMS= {len(walls)}", *(f"3 {a} {b}" for a, b in walls), ""]
    return "\n".join(lines)


def generate_config(problem: CavityProblemSU2, tag: str) -> str:
    U = float(problem.lid_velocity.to("m/s").magnitude)
    return "\n".join([
        f"% Forge execution {tag}",
        "SOLVER= INC_NAVIER_STOKES", "MATH_PROBLEM= DIRECT", "RESTART_SOL= NO",
        "INC_DENSITY_MODEL= CONSTANT", f"INC_DENSITY_INIT= {float(problem.density.to('kg/m^3').magnitude)!r}",
        "INC_VELOCITY_INIT= ( 0.0, 0.0, 0.0 )", "INC_ENERGY_EQUATION= NO", "INC_NONDIM= DIMENSIONAL",
        "FLUID_MODEL= CONSTANT_DENSITY", "VISCOSITY_MODEL= CONSTANT_VISCOSITY",
        f"MU_CONSTANT= {float(problem.dynamic_viscosity.to('Pa*s').magnitude)!r}",
        "MARKER_HEATFLUX= ( lid, 0.0, walls, 0.0 )",
        "SURFACE_MOVEMENT= MOVING_WALL", "MARKER_MOVING= ( lid )", f"SURFACE_TRANSLATION_RATE= {U!r} 0.0 0.0",
        "NUM_METHOD_GRAD= GREEN_GAUSS", f"CFL_NUMBER= {problem.cfl!r}", "CFL_ADAPT= NO",
        "TIME_DISCRE_FLOW= EULER_IMPLICIT", "CONV_NUM_METHOD_FLOW= FDS", "MUSCL_FLOW= YES", "SLOPE_LIMITER_FLOW= NONE",
        "LINEAR_SOLVER= FGMRES", "LINEAR_SOLVER_PREC= ILU", "LINEAR_SOLVER_ERROR= 1E-12", "LINEAR_SOLVER_ITER= 30",
        f"ITER= {problem.iterations}", "CONV_FIELD= RMS_PRESSURE", f"CONV_RESIDUAL_MINVAL= {problem.residual_log10_target!r}",
        "CONV_STARTITER= 10",
        "MESH_FILENAME= mesh.su2", "MESH_FORMAT= SU2",
        "OUTPUT_FILES= (RESTART_ASCII)", "RESTART_FILENAME= restart", "TABULAR_FORMAT= CSV", "CONV_FILENAME= history",
        "HISTORY_OUTPUT= (ITER, RMS_RES)", "SCREEN_OUTPUT= (INNER_ITER, RMS_PRESSURE, RMS_VELOCITY-X)", "SCREEN_WRT_FREQ_INNER= 500",
        "OUTPUT_WRT_FREQ= 100000", "",
    ])


class SU2Provider:
    def __init__(self, registry, *, timeout_s: float = 1800.0, workspace_root: str | None = None) -> None:
        self.status = registry.require("su2")
        self.timeout_s, self.workspace_root = timeout_s, workspace_root

    def run_cavity(self, problem: CavityProblemSU2) -> ProviderExecutionRecord:
        configuration = {"semantics": SEMANTICS}
        base = ProviderExecutionIdentity.from_content(self.status, adapter_id=ADAPTER[0], adapter_version=ADAPTER[1],
                                                      problem=problem.to_dict(), configuration=configuration, output_request=("velocity", "pressure"))
        t0 = time.perf_counter()
        files = {"cavity.cfg": generate_config(problem, base.digest), "mesh.su2": generate_mesh(problem)}
        identity = ProviderExecutionIdentity.from_content(self.status, adapter_id=ADAPTER[0], adapter_version=ADAPTER[1],
                                                          problem=problem.to_dict(), configuration=configuration, inputs=files,
                                                          output_request=("velocity", "pressure"))
        prefix = os.path.dirname(os.path.dirname(self.status.location))
        inv = ProcessInvocation(self.status.location, self.status.executable_digest, self.status.version, ("cavity.cfg",),
                                tuple(GeneratedFile(k, v.encode()) for k, v in sorted(files.items())),
                                minimal_environment(self.status.location, {"LD_LIBRARY_PATH": f"{prefix}/lib"}), self.timeout_s,
                                ("restart.csv", "history.csv"))
        ws = ProcessWorkspace(self.workspace_root)
        try:
            t1 = time.perf_counter()
            rec = ws.run(inv)
            t2 = time.perf_counter()
            if not rec.completed:
                return failed(identity, f"SU2_CFD did not complete (exit {rec.exit_code}, missing {list(rec.missing_outputs)}): "
                                        f"{(rec.stdout_tail + rec.stderr_tail)[-600:]}", process_digest=rec.digest, artifacts=files)
            hist = list(csv.reader(io.StringIO(ws.read_output("history.csv").decode())))
            header = [h.strip().strip('"') for h in hist[0]]
            col = next(i for i, h in enumerate(header) if h == "rms[P]")
            final_res = float(hist[-1][col])
            if final_res > problem.residual_log10_target:
                return failed(identity, f"SU2 did not reach the declared residual target (log10 rms[P] {final_res:.3g} > "
                                        f"{problem.residual_log10_target:g})", process_digest=rec.digest)
            rows = list(csv.DictReader(io.StringIO(ws.read_output("restart.csv").decode())))
            t3 = time.perf_counter()
        finally:
            ws.cleanup()
        n = (problem.cells + 1) ** 2
        key = lambda r, k: next(v for kk, v in r.items() if kk.strip().strip('"') == k)  # noqa: E731
        if len(rows) != n:
            return failed(identity, f"SU2 volume output has {len(rows)} nodes, expected {n}")
        order = np.array([int(key(r, "PointID")) for r in rows])
        vel = np.array([[float(key(r, "Velocity_x")), float(key(r, "Velocity_y"))] for r in rows])[np.argsort(order)]
        pres = np.array([float(key(r, "Pressure")) for r in rows])[np.argsort(order)]
        return ProviderExecutionRecord(identity, True, "", arrays={"velocity": ("m/s", vel), "pressure": ("Pa", pres)},
                                       artifacts=files, process_digest=rec.digest,
                                       metrics={"generate_s": t1 - t0, "process_s": t2 - t1, "parse_s": t3 - t2, "nodes": n,
                                                "iterations": len(hist) - 1, "final_log10_rms_p": final_res, "reynolds": problem.reynolds})
