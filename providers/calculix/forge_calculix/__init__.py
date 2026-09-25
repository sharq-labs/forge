"""CalculiX structural provider (BIG 11), process-based.

Forge plane-stress problem (BIG 7 mesh + regions, BIG 5 RESOLVED Young's
modulus / Poisson ratio per region, clamped and traction boundaries, thickness)
-> deterministic CalculiX ``.inp`` deck (CPS3 elements, one material card per
region generated from the exact resolved-property records) -> ``ccx`` through
the process boundary -> ``.dat`` parsed only if THIS execution produced it
(digest-verified) -> Forge nodal displacement field + element stresses.

Boundary tractions are converted to consistent nodal forces for linear edges
(half the edge resultant to each node) -- recorded in the deck, so the load
CalculiX saw is inspectable.  Exit code 0 is not success: the deck heading
carries the execution identity, the ``.dat`` must contain complete displacement
and stress tables, and every value must be finite.
"""

from __future__ import annotations

import os
import re
import time

import numpy as np

from engcore.providers import (
    GeneratedFile, ProcessInvocation, ProcessWorkspace, ProviderExecutionIdentity, ProviderExecutionRecord, ProviderRefusal,
    failed, minimal_environment,
)
from engcore.pde.cases import PlaneStressProblem, RegionMaterial  # noqa: F401
from engcore.scientific.units.quantity import Quantity

ADAPTER = ("forge_calculix", "0.1")


# the case record is provider-neutral (engcore.pde.cases); re-exported for callers of this adapter


def _facet_nodes(mesh, group: str) -> np.ndarray:
    return np.asarray(mesh.facets)[mesh.facet_indices(mesh.region(group))]


def generate_deck(problem: PlaneStressProblem, identity_tag: str) -> str:
    mesh = problem.mesh
    if getattr(mesh.cell_type, "value", str(mesh.cell_type)) != "triangle":
        raise ProviderRefusal("this adapter generates CPS3 decks for triangle meshes only")
    xy = np.asarray(mesh.coordinates, dtype=float)
    cells = np.asarray(mesh.cells, dtype=int).copy()
    # counter-clockwise ordering (CalculiX needs a positive Jacobian)
    a = xy[cells[:, 0]]; b = xy[cells[:, 1]]; c = xy[cells[:, 2]]
    area2 = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    flip = area2 < 0
    cells[flip] = cells[flip][:, [0, 2, 1]]
    t = float(problem.thickness.to("m").magnitude)
    lines = ["*HEADING", f"Forge execution {identity_tag}", "*NODE"]
    lines += [f"{i + 1}, {float(x)!r}, {float(y)!r}, 0.0" for i, (x, y) in enumerate(xy)]
    region_of = {}
    for m in problem.materials:
        for ci in np.asarray(mesh.cell_indices(mesh.region(m.region)), dtype=int):
            if ci in region_of:
                raise ProviderRefusal("a cell belongs to two material regions")
            region_of[int(ci)] = m.region
    if len(region_of) != len(cells):
        raise ProviderRefusal(f"{len(cells) - len(region_of)} cells have no material; nothing is defaulted")
    for m in problem.materials:
        ids = [ci for ci, r in sorted(region_of.items()) if r == m.region]
        lines.append(f"*ELEMENT, TYPE=CPS3, ELSET=E_{m.region}")
        lines += [f"{ci + 1}, {cells[ci, 0] + 1}, {cells[ci, 1] + 1}, {cells[ci, 2] + 1}" for ci in ids]
    for m in problem.materials:
        E = float(m.youngs_modulus.to("Pa").magnitude)
        nu = float(m.poisson_ratio.to("dimensionless").magnitude)
        lines += [f"*MATERIAL, NAME=M_{m.region}", "*ELASTIC", f"{E!r}, {nu!r}",
                  f"*SOLID SECTION, ELSET=E_{m.region}, MATERIAL=M_{m.region}", f"{t!r}"]
    clamped = sorted({int(n) for f in _facet_nodes(mesh, problem.clamped_group) for n in f})
    lines.append("*NSET, NSET=N_CLAMPED")
    lines += [f"{n + 1}," for n in clamped]
    tx, ty = (float(q.to("Pa").magnitude) for q in problem.traction)
    forces: dict[int, list[float]] = {}
    for f in _facet_nodes(mesh, problem.traction_group):
        n0, n1 = int(f[0]), int(f[1])
        length = float(np.hypot(*(xy[n1] - xy[n0])))
        for n in (n0, n1):
            acc = forces.setdefault(n, [0.0, 0.0])
            acc[0] += 0.5 * tx * t * length
            acc[1] += 0.5 * ty * t * length
    lines += ["*NSET, NSET=N_ALL", *(f"{i + 1}," for i in range(len(xy))),
              "*ELSET, ELSET=E_ALL", *(f"E_{m.region}," for m in problem.materials),
              "*STEP", "*STATIC", "*BOUNDARY", "N_CLAMPED, 1, 2, 0.0", "*CLOAD"]
    for n in sorted(forces):
        fx, fy = forces[n]
        if fx:
            lines.append(f"{n + 1}, 1, {fx!r}")
        if fy:
            lines.append(f"{n + 1}, 2, {fy!r}")
    lines += ["*NODE PRINT, NSET=N_ALL", "U", "*EL PRINT, ELSET=E_ALL", "S", "*END STEP", ""]
    return "\n".join(lines)


_NUM = r"[-+]?\d+(?:\.\d*)?(?:[Ee][-+]?\d+)?"


def parse_dat(text: str, nodes: int, cells: int) -> tuple[np.ndarray, np.ndarray]:
    blocks = re.split(r"\n\s*(?=displacements|stresses)", text)
    disp = next((b for b in blocks if b.lstrip().startswith("displacements")), None)
    stress = next((b for b in blocks if b.lstrip().startswith("stresses")), None)
    if disp is None or stress is None:
        raise ProviderRefusal("CalculiX .dat lacks the displacement or stress table")
    u = np.full((nodes, 2), np.nan)
    for line in disp.splitlines()[1:]:
        parts = line.split()
        if len(parts) == 4 and parts[0].isdigit():
            u[int(parts[0]) - 1] = float(parts[1]), float(parts[2])
    s: dict[int, list[list[float]]] = {}
    for line in stress.splitlines()[1:]:
        parts = line.split()
        if len(parts) == 8 and parts[0].isdigit():
            s.setdefault(int(parts[0]), []).append([float(parts[2]), float(parts[3]), float(parts[5])])  # sxx, syy, sxy
    if np.isnan(u).any() or len(s) != cells:
        raise ProviderRefusal("CalculiX output is incomplete (missing nodes or elements)")
    sig = np.array([np.mean(s[k], axis=0) for k in sorted(s)])
    if not (np.all(np.isfinite(u)) and np.all(np.isfinite(sig))):
        raise ProviderRefusal("CalculiX output contains non-finite values")
    return u, sig


class CalculixProvider:
    def __init__(self, registry, *, timeout_s: float = 600.0, workspace_root: str | None = None) -> None:
        self.status = registry.require("calculix")
        self.timeout_s = timeout_s
        self.workspace_root = workspace_root

    def execute(self, problem: PlaneStressProblem, *, preexisting: dict | None = None) -> ProviderExecutionRecord:
        configuration = {"element": "CPS3", "procedure": "*STATIC linear", "solver": "ccx default (SPOOLES/PaStiX as built)",
                         "load": "consistent nodal forces from uniform edge traction"}
        # identity from content; the deck is derived from the problem, then bound itself
        base = ProviderExecutionIdentity.from_content(self.status, adapter_id=ADAPTER[0], adapter_version=ADAPTER[1],
                                                      problem=problem.to_dict(), configuration=configuration,
                                                      output_request=("displacement", "stress"))
        t0 = time.perf_counter()
        deck = generate_deck(problem, base.digest)
        identity = ProviderExecutionIdentity.from_content(self.status, adapter_id=ADAPTER[0], adapter_version=ADAPTER[1],
                                                          problem=problem.to_dict(), configuration=configuration,
                                                          inputs={"job.inp": deck}, output_request=("displacement", "stress"))
        invocation = ProcessInvocation(self.status.location, self.status.executable_digest, self.status.version, ("-i", "job"),
                                       (GeneratedFile("job.inp", deck.encode()),), minimal_environment(self.status.location),
                                       self.timeout_s, ("job.dat",))
        ws = ProcessWorkspace(self.workspace_root, preexisting=preexisting)
        try:
            t1 = time.perf_counter()
            rec = ws.run(invocation)
            t2 = time.perf_counter()
            if not rec.completed:
                return failed(identity, f"ccx did not complete (exit {rec.exit_code}, timed out {rec.timed_out}, missing "
                                        f"{list(rec.missing_outputs)}): {rec.stdout_tail[-400:]}", process_digest=rec.digest,
                              artifacts={"job.inp": deck})
            text = ws.read_output("job.dat").decode("utf-8", "replace")  # digest-verified output of THIS run
            u, sig = parse_dat(text, problem.mesh.node_count, len(problem.mesh.cells))
            t3 = time.perf_counter()
        finally:
            ws.cleanup()
        return ProviderExecutionRecord(identity, True, "", arrays={"displacement": ("m", u), "stress": ("Pa", sig)},
                                       artifacts={"job.inp": deck}, process_digest=rec.digest,
                                       metrics={"generate_s": t1 - t0, "process_s": t2 - t1, "parse_s": t3 - t2,
                                                "nodes": problem.mesh.node_count, "elements": len(problem.mesh.cells)})
