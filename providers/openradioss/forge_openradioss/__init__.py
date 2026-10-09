"""OpenRadioss adapter: a bounded explicit impact case -> starter/engine decks -> process run -> parsed histories.

Bounded scope, stated so it is not mistaken for crash simulation support:
ONE deformable body meshed with linear tetrahedra, ONE elastic-plastic
material with linear hardening (Johnson-Cook form with n = 1, no rate or
thermal terms), a uniform initial translational velocity, ONE planar rigid
wall, global energy time histories.  Contact between parts, failure/erosion,
shells, beams, composites, airbags and spot welds are refused.

Units: the decks declare kg / m / s for input and working units.  Every value
is converted from a Quantity; nothing is written in an undeclared unit.

STATUS: the deck syntax follows the OpenRadioss 2022+ reference format and has
NOT been run through a real starter in the environment that built this adapter
(OpenRadioss was unavailable there).  ``translation_status`` is
``unverified_against_running_provider`` until this distribution's provider
tests pass against a real install.  The parsers are tested against declared
text fixtures; a fixture is a parser contract, never a provider result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
from typing import Any, Mapping

import numpy as np

from engcore.providers import (
    GeneratedFile, ProcessInvocation, conda_environment_of, ProcessWorkspace, ProviderExecutionIdentity, ProviderExecutionRecord, ProviderRefusal,
    ProviderStatus, QuantitySeries, failed, minimal_environment,
)
from engcore.scientific.fields import CellType
from engcore.scientific.units.quantity import Quantity, dimensionality
from engcore.spatial.mesh import SpatialMesh

ADAPTER_ID = "forge_openradioss"
ADAPTER_VERSION = "0.1.0"
TRANSLATION_STATUS = "unverified_against_running_provider"
HISTORY_UNITS = {"kinetic_energy": "J", "internal_energy": "J", "total_energy": "J", "rigid_wall_force": "N"}
_TH_COLUMNS = {"kinetic_energy": "KE", "internal_energy": "IE", "total_energy": "TE", "rigid_wall_force": "FNORMAL"}


def _v(q: Quantity, unit: str, label: str, *, positive: bool = False) -> float:
    if not isinstance(q, Quantity) or q.dimensionality != dimensionality(unit):
        raise ProviderRefusal(f"{label} must be a Quantity in a unit of {unit}")
    v = q.magnitude_in(unit)
    if not math.isfinite(v) or (positive and not v > 0):
        raise ProviderRefusal(f"{label} must be finite{' and > 0' if positive else ''}")
    return v


@dataclass(frozen=True)
class ElasticPlasticMaterial:
    material_id: str
    density: Quantity
    youngs_modulus: Quantity
    poisson_ratio: Quantity
    yield_stress: Quantity
    hardening_modulus: Quantity
    source_ref: str

    def canonical(self) -> dict[str, float]:
        if not str(self.source_ref).strip():
            raise ProviderRefusal(f"material {self.material_id!r} has no source reference; unsourced properties are refused")
        nu = _v(self.poisson_ratio, "dimensionless", "Poisson ratio")
        if not 0 <= nu < 0.5:
            raise ProviderRefusal("Poisson ratio must lie in [0, 0.5)")
        out = {"rho": _v(self.density, "kg/m^3", "density", positive=True), "E": _v(self.youngs_modulus, "Pa", "Young's modulus", positive=True),
               "nu": nu, "a": _v(self.yield_stress, "Pa", "yield stress", positive=True),
               "b": _v(self.hardening_modulus, "Pa", "hardening modulus")}
        if out["b"] < 0:
            raise ProviderRefusal("negative hardening (softening) is outside this adapter's bounded scope")
        return out


@dataclass(frozen=True)
class RigidWall:
    point: tuple[Quantity, Quantity, Quantity]
    normal: tuple[float, float, float]

    def canonical(self) -> dict[str, list[float]]:
        n = tuple(float(v) for v in self.normal)
        norm = math.sqrt(sum(v * v for v in n))
        if len(n) != 3 or abs(norm - 1.0) > 1e-9:
            raise ProviderRefusal("rigid wall normal must be a unit 3-vector")
        return {"point_m": [_v(q, "m", "wall point") for q in self.point], "normal": list(n)}


@dataclass(frozen=True)
class ExplicitImpactCase:
    case_id: str
    mesh: SpatialMesh
    material: ElasticPlasticMaterial
    initial_velocity: tuple[Quantity, Quantity, Quantity]
    wall: RigidWall
    end_time: Quantity
    output_interval: Quantity
    histories: tuple[str, ...]
    solver_options: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,40}", self.case_id):
            raise ProviderRefusal("case_id must be a short identifier (it names provider files)")
        if not isinstance(self.mesh, SpatialMesh) or self.mesh.cell_type is not CellType.TETRAHEDRON:
            raise ProviderRefusal("the bounded explicit case takes a 3D linear-tetrahedron SpatialMesh")
        bad = sorted(set(self.histories) - set(HISTORY_UNITS))
        if not self.histories or bad:
            raise ProviderRefusal(f"histories must be a non-empty subset of {sorted(HISTORY_UNITS)}; refused {bad}")
        if "timestep_scale_factor" not in self.solver_options:
            raise ProviderRefusal("solver option 'timestep_scale_factor' is required; the provider default is never used silently")
        sf = float(self.solver_options["timestep_scale_factor"])
        if not 0 < sf <= 0.9:
            raise ProviderRefusal("timestep_scale_factor must lie in (0, 0.9]")
        end, dt = _v(self.end_time, "s", "end time", positive=True), _v(self.output_interval, "s", "output interval", positive=True)
        if dt > end:
            raise ProviderRefusal("output interval exceeds the end time")
        self.material.canonical()
        self.wall.canonical()

    def canonical(self) -> dict[str, Any]:
        return {"case_id": self.case_id, "mesh_digest": self.mesh.digest, "material": self.material.canonical(),
                "material_source": self.material.source_ref,
                "initial_velocity_m_s": [_v(q, "m/s", "initial velocity") for q in self.initial_velocity], "wall": self.wall.canonical(),
                "end_time_s": _v(self.end_time, "s", "end"), "output_interval_s": _v(self.output_interval, "s", "interval"),
                "histories": sorted(self.histories), "solver_options": dict(sorted(self.solver_options.items()))}


def _f(v: float) -> str:
    return f"{v:20.10E}"


def _i(v: int) -> str:
    return f"{v:10d}"


def starter_deck(case: ExplicitImpactCase) -> str:
    c = case.canonical()
    m = c["material"]
    lines = ["#RADIOSS STARTER", "/BEGIN", case.case_id, _i(2022) + _i(0),
             f"{'kg':>20}{'m':>20}{'s':>20}", f"{'kg':>20}{'m':>20}{'s':>20}", "/NODE"]
    for i, (x, y, z) in enumerate(case.mesh.coordinates, start=1):
        lines.append(_i(i) + _f(float(x)) + _f(float(y)) + _f(float(z)))
    lines += ["/PART/1", "body", _i(1) + _i(1), "/PROP/SOLID/1", "solid_prop", _i(14), "/MAT/PLAS_JOHNS/1", "body_material",
              _f(m["rho"]), _f(m["E"]) + _f(m["nu"]), _f(m["a"]) + _f(m["b"]) + _f(1.0) + _f(0.0) + _f(0.0), "/TETRA4/1"]
    for e, (a, b, d, g) in enumerate(case.mesh.cells, start=1):
        lines.append(_i(e) + _i(int(a) + 1) + _i(int(b) + 1) + _i(int(d) + 1) + _i(int(g) + 1))
    lines += ["/GRNOD/PART/1", "all_nodes", _i(1)]
    vx, vy, vz = c["initial_velocity_m_s"]
    lines += ["/INIVEL/TRA/1", "initial_velocity", _f(vx) + _f(vy) + _f(vz) + _i(1)]
    p, n = c["wall"]["point_m"], c["wall"]["normal"]
    lines += ["/RWALL/PLANE/1", "wall", _i(0) + _i(0) + _i(1), _f(p[0]) + _f(p[1]) + _f(p[2]),
              _f(p[0] + n[0]) + _f(p[1] + n[1]) + _f(p[2] + n[2])]
    lines += ["/TH/PART/1", "energies", "DEF", _i(1), "/END"]
    return "\n".join(lines) + "\n"


def engine_deck(case: ExplicitImpactCase) -> str:
    c = case.canonical()
    return "\n".join([
        f"/RUN/{case.case_id}/1", _f(c["end_time_s"]), "/TFILE/0", _f(c["output_interval_s"]),
        "/DT/NODA/CST/0", _f(float(c["solver_options"]["timestep_scale_factor"])) + _f(0.0), "/ANIM/DT", _f(0.0) + _f(c["end_time_s"]),
        "/END/ENGINE"]) + "\n"


# --------------------------------------------------------------------------
# Parsers (contracts tested against declared text fixtures)
# --------------------------------------------------------------------------


def parse_starter_listing(text: str) -> tuple[bool, str]:
    errors = re.findall(r"^\s*ERROR\s+ID\s*:\s*(\d+)", text, flags=re.MULTILINE)
    if errors:
        return False, f"starter reported {len(errors)} error(s): ids {sorted(set(errors))}"
    if "TERMINATION" in text.upper() and "NORMAL TERMINATION" not in text.upper():
        return False, "starter did not terminate normally"
    if "NORMAL TERMINATION" not in text.upper():
        return False, "starter listing has no NORMAL TERMINATION line; an incomplete listing is not success"
    return True, "normal termination"


def parse_engine_listing(text: str) -> tuple[bool, str]:
    up = text.upper()
    if "ERROR TERMINATION" in up:
        return False, "engine reported ERROR TERMINATION"
    if "NORMAL TERMINATION" not in up:
        return False, "engine listing has no NORMAL TERMINATION line; a truncated run is not success"
    return True, "normal termination"


def parse_time_history_csv(text: str, histories: tuple[str, ...], end_time_s: float) -> dict[str, QuantitySeries]:
    """Parse a th_to_csv export.  Requires a TIME column and the declared column of every requested history."""
    rows = [r.strip() for r in text.strip().splitlines() if r.strip()]
    if len(rows) < 2:
        raise ProviderRefusal("time-history file has no data rows")
    header = [h.strip().strip('"').upper() for h in rows[0].split(",")]
    if "TIME" not in header:
        raise ProviderRefusal("time-history file has no TIME column")
    need = {h: _TH_COLUMNS[h] for h in histories}
    missing = [col for col in need.values() if col not in header]
    if missing:
        raise ProviderRefusal(f"time-history file lacks columns {missing}; a missing history is never defaulted")
    try:
        data = np.array([[float(v) for v in r.split(",")] for r in rows[1:]], dtype=float)
    except ValueError as exc:
        raise ProviderRefusal(f"time-history file has a non-numeric value: {exc}") from exc
    if data.shape[1] != len(header):
        raise ProviderRefusal("time-history rows do not match the header width")
    t = data[:, header.index("TIME")]
    if t[0] != 0.0 or abs(t[-1] - end_time_s) > 1e-9 * max(1.0, end_time_s):
        raise ProviderRefusal(f"histories span [{t[0]}, {t[-1]}] s, not the requested [0, {end_time_s}] s; a truncated run is refused")
    out = {}
    for h, col in need.items():
        out[h] = QuantitySeries(h, HISTORY_UNITS[h], tuple(float(x) for x in t), tuple(float(x) for x in data[:, header.index(col)]))
    return out


class OpenRadiossProvider:
    """Process provider: starter -> engine -> th_to_csv inside one ProcessWorkspace."""

    def __init__(self, starter: ProviderStatus, engine: ProviderStatus, th_to_csv: ProviderStatus) -> None:
        for s, name in ((starter, "openradioss_starter"), (engine, "openradioss"), (th_to_csv, "openradioss_th_to_csv")):
            if not isinstance(s, ProviderStatus) or s.capability.provider_id != name:
                raise ProviderRefusal(f"OpenRadiossProvider needs the registry status of {name!r}")
        self.starter, self.engine, self.th = starter, engine, th_to_csv

    def identity(self, case: ExplicitImpactCase) -> ProviderExecutionIdentity:
        decks = {"starter": starter_deck(case), "engine": engine_deck(case)}
        return ProviderExecutionIdentity.from_content(self.engine, adapter_id=ADAPTER_ID, adapter_version=ADAPTER_VERSION,
                                                      problem=case.canonical(), configuration=decks, output_request=tuple(sorted(case.histories)),
                                                      environment={"starter": self.starter.digest, "th_to_csv": self.th.digest})

    def execute(self, case: ExplicitImpactCase, *, timeout_s: float = 3600.0) -> ProviderExecutionRecord:
        for s in (self.starter, self.engine, self.th):
            if not s.available:
                raise ProviderRefusal(f"OpenRadioss is unavailable: {s.capability.provider_id}: {s.reason}; nothing is synthesized")
        ident = self.identity(case)
        name = case.case_id
        inputs = (GeneratedFile(f"{name}_0000.rad", starter_deck(case).encode()), GeneratedFile(f"{name}_0001.rad", engine_deck(case).encode()))
        steps = (
            ProcessInvocation(self.starter.location, self.starter.executable_digest, self.starter.version, ("-i", f"{name}_0000.rad", "-np", "1"),
                              inputs, minimal_environment(self.starter.location), timeout_s, (f"{name}_0000.out",),
                              conda_environment=conda_environment_of(self.starter)),
            ProcessInvocation(self.engine.location, self.engine.executable_digest, self.engine.version, ("-i", f"{name}_0001.rad"),
                              inputs, minimal_environment(self.engine.location), timeout_s, (f"{name}_0001.out", f"{name}T01"),
                              conda_environment=conda_environment_of(self.engine)),
            ProcessInvocation(self.th.location, self.th.executable_digest, self.th.version, (f"{name}T01",),
                              inputs, minimal_environment(self.th.location), timeout_s, (f"{name}T01.csv",),
                              conda_environment=conda_environment_of(self.th)),
        )
        ws = ProcessWorkspace()
        try:
            rec = ws.run_sequence(steps)
            if not rec.completed:
                return failed(ident, f"process sequence did not complete (exit {rec.exit_code}, timed out {rec.timed_out}, missing {list(rec.missing_outputs)})",
                              process_digest=rec.digest)
            ok, why = parse_starter_listing(ws.read_output(f"{name}_0000.out").decode("utf-8", "replace"))
            if not ok:
                return failed(ident, why, process_digest=rec.digest)
            ok, why = parse_engine_listing(ws.read_output(f"{name}_0001.out").decode("utf-8", "replace"))
            if not ok:
                return failed(ident, why, process_digest=rec.digest)
            series = parse_time_history_csv(ws.read_output(f"{name}T01.csv").decode("utf-8", "replace"), tuple(case.histories),
                                            case.canonical()["end_time_s"])
            return ProviderExecutionRecord(ident, True, f"normal termination ({TRANSLATION_STATUS})", series=tuple(series.values()),
                                           artifacts={"starter.rad": starter_deck(case), "engine.rad": engine_deck(case)}, process_digest=rec.digest)
        finally:
            ws.cleanup()


__all__ = ["ADAPTER_ID", "ADAPTER_VERSION", "ElasticPlasticMaterial", "ExplicitImpactCase", "HISTORY_UNITS", "OpenRadiossProvider", "RigidWall",
           "TRANSLATION_STATUS", "engine_deck", "parse_engine_listing", "parse_starter_listing", "parse_time_history_csv", "starter_deck"]
