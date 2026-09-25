"""Code_Aster structural provider (BIG 11, second wave), process-based.

Consumes the provider-neutral :class:`engcore.pde.cases.PlaneStressProblem`
(BIG 7 mesh + BIG 5 resolved region materials) -> generated ASTER-format mesh
(``.mail``, TRIA3 + SEG2 edge groups), command file (``.comm``: C_PLAN plane
stress, one DEFI_MATERIAU per region, clamped nodes, FORCE_CONTOUR traction)
and ``.export`` -> ``run_aster`` in a fresh workspace -> nodal displacement
parsed from the RESULTAT file THIS run produced.

C_PLAN works per unit thickness: with a uniform thickness, traction loads and
stiffness scale together, so plane-stress displacements do not depend on it
(recorded; the thickness still enters the identity).  Success requires exit 0,
"DIAGNOSTIC JOB : OK", and a complete finite displacement table.  Element
stresses are NOT parsed by this adapter (declared gap).
"""

from __future__ import annotations

import os
import re
import time

import numpy as np

from engcore.pde.cases import PlaneStressProblem
from engcore.providers import (
    GeneratedFile, ProcessInvocation, ProcessWorkspace, ProviderExecutionIdentity, ProviderExecutionRecord, ProviderRefusal, failed,
)

ADAPTER = ("forge_code_aster", "0.1")


def generate_mesh(problem: PlaneStressProblem) -> str:
    mesh = problem.mesh
    if getattr(mesh.cell_type, "value", str(mesh.cell_type)) != "triangle":
        raise ProviderRefusal("this adapter writes TRIA3 meshes only")
    xy = np.asarray(mesh.coordinates, dtype=float)
    cells = np.asarray(mesh.cells, dtype=int).copy()
    a, b, c = xy[cells[:, 0]], xy[cells[:, 1]], xy[cells[:, 2]]
    flip = ((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])) < 0
    cells[flip] = cells[flip][:, [0, 2, 1]]
    facets = np.asarray(mesh.facets)
    lines = ["TITRE", "FORGE GENERATED", "FINSF", "COOR_2D", *(f"N{i + 1} {float(x)!r} {float(y)!r}" for i, (x, y) in enumerate(xy)), "FINSF",
             "TRIA3", *(f"M{i + 1} N{t[0] + 1} N{t[1] + 1} N{t[2] + 1}" for i, t in enumerate(cells)), "FINSF"]
    traction = facets[mesh.facet_indices(mesh.region(problem.traction_group))]
    lines += ["SEG2", *(f"E{i + 1} N{int(f[0]) + 1} N{int(f[1]) + 1}" for i, f in enumerate(traction)), "FINSF"]
    covered, names = set(), set()
    for m in problem.materials:
        ids = [int(ci) for ci in mesh.cell_indices(mesh.region(m.region))]
        name = f"R_{m.region.upper()[:20]}"
        if covered & set(ids) or name in names:
            raise ProviderRefusal(f"region {m.region!r} overlaps another material region or collides as Code_Aster group {name!r}")
        covered |= set(ids)
        names.add(name)
        lines += ["GROUP_MA", f"R_{m.region.upper()[:20]}", *(f"M{ci + 1}" for ci in ids), "FINSF"]
    if len(covered) != len(cells):
        raise ProviderRefusal("cells without a material region; nothing is defaulted")
    lines += ["GROUP_MA", "TRACTION", *(f"E{i + 1}" for i in range(len(traction))), "FINSF"]
    clamped = sorted({int(n) for f in facets[mesh.facet_indices(mesh.region(problem.clamped_group))] for n in f})
    lines += ["GROUP_NO", "CLAMPED", *(f"N{n + 1}" for n in clamped), "FINSF", "FIN", ""]
    return "\n".join(lines)


def generate_comm(problem: PlaneStressProblem, tag: str) -> str:
    tx, ty = (float(q.to("Pa").magnitude) for q in problem.traction)
    mats = [f"mat_{i} = DEFI_MATERIAU(ELAS=_F(E={float(m.youngs_modulus.to('Pa').magnitude)!r}, "
            f"NU={float(m.poisson_ratio.to('dimensionless').magnitude)!r}))" for i, m in enumerate(problem.materials)]
    affe = ", ".join(f"_F(GROUP_MA='R_{m.region.upper()[:20]}', MATER=mat_{i})" for i, m in enumerate(problem.materials))
    return "\n".join([
        f"# Forge execution {tag}", "DEBUT(LANG='EN')", "mesh = LIRE_MAILLAGE(FORMAT='ASTER', UNITE=20)",
        "model = AFFE_MODELE(MAILLAGE=mesh, AFFE=_F(TOUT='OUI', PHENOMENE='MECANIQUE', MODELISATION='C_PLAN'))",
        *mats, f"chmat = AFFE_MATERIAU(MAILLAGE=mesh, AFFE=({affe},))",
        f"load = AFFE_CHAR_MECA(MODELE=model, DDL_IMPO=_F(GROUP_NO='CLAMPED', DX=0.0, DY=0.0), "
        f"FORCE_CONTOUR=_F(GROUP_MA='TRACTION', FX={tx!r}, FY={ty!r}))",
        "res = MECA_STATIQUE(MODELE=model, CHAM_MATER=chmat, EXCIT=_F(CHARGE=load))",
        "IMPR_RESU(FORMAT='RESULTAT', UNITE=8, RESU=_F(RESULTAT=res, NOM_CHAM='DEPL', NOM_CMP=('DX', 'DY')))",
        "FIN()", ""])


def parse_displacement(text: str, nodes: int) -> np.ndarray:
    u = np.full((nodes, 2), np.nan)
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0].isdigit():
            i = int(parts[0]) - 1
            if 0 <= i < nodes:
                u[i] = float(parts[1]), float(parts[2])
    if np.isnan(u).any():
        raise ProviderRefusal("Code_Aster displacement table is incomplete")
    return u


class CodeAsterProvider:
    def __init__(self, registry, *, timeout_s: float = 900.0, workspace_root: str | None = None) -> None:
        self.status = registry.require("code_aster")
        self.timeout_s, self.workspace_root = timeout_s, workspace_root

    def execute(self, problem: PlaneStressProblem) -> ProviderExecutionRecord:
        configuration = {"modelisation": "C_PLAN (per unit thickness)", "operator": "MECA_STATIQUE", "load": "FORCE_CONTOUR uniform traction",
                         "stress_output": "not parsed by this adapter"}
        base = ProviderExecutionIdentity.from_content(self.status, adapter_id=ADAPTER[0], adapter_version=ADAPTER[1], problem=problem.to_dict(),
                                                      configuration=configuration, output_request=("displacement",))
        t0 = time.perf_counter()
        ws = ProcessWorkspace(self.workspace_root)
        files = {"case.comm": generate_comm(problem, base.digest), "mesh.mail": generate_mesh(problem)}
        # workspace-relative paths (run_aster runs with cwd = the workspace): the .export is content, not a temp path
        export = "\n".join(["P time_limit 300", "P memory_limit 2048", "P ncpus 1", "P mpi_nbcpu 1", "P mode interactif",
                            "F comm case.comm D 1", "F mail mesh.mail D 20", "F resu result.resu R 8", "F mess message R 6", ""])
        identity = ProviderExecutionIdentity.from_content(self.status, adapter_id=ADAPTER[0], adapter_version=ADAPTER[1], problem=problem.to_dict(),
                                                          configuration=configuration, inputs=files, output_request=("displacement",))
        prefix = os.path.dirname(os.path.dirname(self.status.location))
        env = (("HOME", "/tmp"), ("LC_ALL", "C"), ("OMP_NUM_THREADS", "1"), ("PATH", f"{prefix}/bin:/usr/bin:/bin"))
        inv = ProcessInvocation(self.status.location, self.status.executable_digest, self.status.version, ("case.export",),
                                tuple(GeneratedFile(k, v.encode()) for k, v in sorted({**files, "case.export": export}.items())),
                                env, self.timeout_s, ("result.resu", "message"))
        try:
            t1 = time.perf_counter()
            rec = ws.run(inv)
            t2 = time.perf_counter()
            if not rec.completed or "DIAGNOSTIC JOB : OK" not in rec.stdout_tail:
                return failed(identity, f"run_aster did not finish OK (exit {rec.exit_code}): {rec.stdout_tail[-500:]}",
                              process_digest=rec.digest, artifacts=files)
            u = parse_displacement(ws.read_output("result.resu").decode("utf-8", "replace"), problem.mesh.node_count)
            t3 = time.perf_counter()
        finally:
            ws.cleanup()
        return ProviderExecutionRecord(identity, True, "", arrays={"displacement": ("m", u)}, artifacts=files, process_digest=rec.digest,
                                       metrics={"generate_s": t1 - t0, "process_s": t2 - t1, "parse_s": t3 - t2, "nodes": problem.mesh.node_count})
