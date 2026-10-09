"""OpenVSP adapter: canonical aerospace parameters -> OpenVSP geometry -> STEP -> Forge imported geometry.

Fuselage, wing, tail and pod are OpenVSP concepts.  They live in THIS
distribution, never in Forge Core: Core sees only the result, an
:class:`~engcore.spatial.geometry.ImportedSource` with a file digest, a
declared length unit (read from the STEP header the provider wrote, never
guessed) and a :class:`~engcore.spatial.geometry.GeometryReceipt`.

Pipeline::

    VSPModelRequest (Quantities, canonical metres/radians)
        -> operation list (deterministic, JSON-canonical; the identity of the translation)
        -> OpenVSP Python API (only when the registry says AVAILABLE)
        -> STEP export -> sha256 -> ImportedSource + receipt

STATUS: the OpenVSP parameter names used in :func:`operations` follow the
OpenVSP 3.x API as documented and have NOT been executed in the environment
that built this adapter (OpenVSP was unavailable there).  The STEP unit check
downstream (Gmsh adapter) catches a unit mismatch; a wrong parameter name
fails the run.  Until a real run passes this distribution's provider tests,
the translation status is ``unverified_against_running_provider``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import math
import os
import re
import tempfile
from typing import Any

from engcore.providers import ProviderRefusal, ProviderStatus
from engcore.scientific.units.quantity import Quantity, dimensionality
from engcore.spatial.geometry import GeometryReceipt, ImportedSource

ADAPTER_ID = "forge_openvsp"
ADAPTER_VERSION = "0.1.0"
TRANSLATION_STATUS = "unverified_against_running_provider"
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _len(q: Quantity, label: str, *, positive: bool = True) -> float:
    if not isinstance(q, Quantity) or q.dimensionality != dimensionality("m"):
        raise ProviderRefusal(f"{label} must be a length Quantity")
    v = q.magnitude_in("m")
    if not math.isfinite(v) or (positive and not v > 0):
        raise ProviderRefusal(f"{label} must be a finite{' positive' if positive else ''} length")
    return v


def _ang(q: Quantity, label: str) -> float:
    if not isinstance(q, Quantity) or str(q.units) not in ("radian", "degree"):
        raise ProviderRefusal(f"{label} must be an angle Quantity (rad or degree)")
    return q.magnitude_in("degree")  # OpenVSP angle parameters are in degrees


def _ratio(q: Quantity, label: str, lo: float, hi: float) -> float:
    if not isinstance(q, Quantity) or q.dimensionality != dimensionality("dimensionless"):
        raise ProviderRefusal(f"{label} must be a dimensionless Quantity")
    v = q.magnitude_in("dimensionless")
    if not lo < v < hi:
        raise ProviderRefusal(f"{label}={v} outside ({lo}, {hi})")
    return v


def _name(value: str) -> str:
    if not _NAME.fullmatch(str(value)):
        raise ProviderRefusal(f"component name {value!r} must be an identifier")
    return str(value)


@dataclass(frozen=True)
class Position:
    x: Quantity
    y: Quantity
    z: Quantity

    def canonical(self) -> list[float]:
        return [_len(self.x, "x", positive=False), _len(self.y, "y", positive=False), _len(self.z, "z", positive=False)]


@dataclass(frozen=True)
class BodyOfRevolution:
    """A fuselage or pod: length and maximum diameter (OpenVSP POD: Length + FineRatio)."""

    name: str
    length: Quantity
    max_diameter: Quantity
    position: Position
    role: str = "fuselage"   # fuselage | pod | nacelle -- a label for the component map, not physics

    def operations(self) -> list[list[Any]]:
        n = _name(self.name)
        L, D = _len(self.length, f"{n} length"), _len(self.max_diameter, f"{n} diameter")
        if D >= L:
            raise ProviderRefusal(f"{n}: max diameter must be smaller than length for a POD body")
        x, y, z = self.position.canonical()
        return [["AddGeom", n, "POD"], ["SetParmVal", n, "Length", "Design", L], ["SetParmVal", n, "FineRatio", "Design", L / D],
                ["SetParmVal", n, "X_Rel_Location", "XForm", x], ["SetParmVal", n, "Y_Rel_Location", "XForm", y],
                ["SetParmVal", n, "Z_Rel_Location", "XForm", z]]


@dataclass(frozen=True)
class LiftingSurface:
    """A wing or tail panel: span, chords, sweep, dihedral, thickness ratio.  ``vertical`` rotates it 90 deg about x."""

    name: str
    span: Quantity
    root_chord: Quantity
    tip_chord: Quantity
    sweep: Quantity
    dihedral: Quantity
    thickness_ratio: Quantity
    position: Position
    vertical: bool = False
    symmetric: bool = True

    def operations(self) -> list[list[Any]]:
        n = _name(self.name)
        span = _len(self.span, f"{n} span")
        rc, tc = _len(self.root_chord, f"{n} root chord"), _len(self.tip_chord, f"{n} tip chord")
        if tc > rc:
            raise ProviderRefusal(f"{n}: tip chord larger than root chord is refused (declare the reversed panel explicitly)")
        sweep, dih = _ang(self.sweep, f"{n} sweep"), _ang(self.dihedral, f"{n} dihedral")
        if not -60 <= sweep <= 60 or not -30 <= dih <= 30:
            raise ProviderRefusal(f"{n}: sweep/dihedral outside the adapter's declared range (|sweep|<=60, |dihedral|<=30 deg)")
        t = _ratio(self.thickness_ratio, f"{n} thickness ratio", 0.0, 0.4)
        x, y, z = self.position.canonical()
        half = span / 2 if self.symmetric else span
        ops = [["AddGeom", n, "WING"], ["SetParmVal", n, "Span", "XSec_1", half], ["SetParmVal", n, "Root_Chord", "XSec_1", rc],
               ["SetParmVal", n, "Tip_Chord", "XSec_1", tc], ["SetParmVal", n, "Sweep", "XSec_1", sweep],
               ["SetParmVal", n, "Dihedral", "XSec_1", dih], ["SetParmVal", n, "ThickChord", "XSecCurve_0", t],
               ["SetParmVal", n, "ThickChord", "XSecCurve_1", t], ["SetParmVal", n, "X_Rel_Location", "XForm", x],
               ["SetParmVal", n, "Y_Rel_Location", "XForm", y], ["SetParmVal", n, "Z_Rel_Location", "XForm", z],
               ["SetParmVal", n, "Sym_Planar_Flag", "Sym", 2.0 if self.symmetric else 0.0]]
        if self.vertical:
            ops.append(["SetParmVal", n, "X_Rel_Rotation", "XForm", 90.0])
        return ops


@dataclass(frozen=True)
class VSPModelRequest:
    model_id: str
    components: tuple[Any, ...]
    export_format: str = "step"
    options: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.components:
            raise ProviderRefusal("an OpenVSP model needs at least one component")
        names = [c.name for c in self.components]
        if len(set(names)) != len(names):
            raise ProviderRefusal("component names must be unique")
        if self.export_format != "step":
            raise ProviderRefusal("only STEP export is supported (it carries its length unit)")


def operations(request: VSPModelRequest) -> list[list[Any]]:
    """The deterministic operation list: what OpenVSP is asked to do, in order."""
    ops: list[list[Any]] = [["VSPRenew"], ["SetSTEPLengthUnit", "m"]]
    for c in request.components:
        if not isinstance(c, (BodyOfRevolution, LiftingSurface)):
            raise ProviderRefusal(f"unsupported component {type(c).__name__}")
        ops.extend(c.operations())
    ops.extend([["Update"], ["ExportFile", "model.stp", "SET_ALL", "EXPORT_STEP"]])
    return ops


def translation_digest(request: VSPModelRequest) -> str:
    import json

    return hashlib.sha256(json.dumps(operations(request), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class VSPGeometryResult:
    source: ImportedSource
    receipt: GeometryReceipt
    step_path: str
    component_map: dict


class OpenVSPProvider:
    def __init__(self, status: ProviderStatus) -> None:
        if not isinstance(status, ProviderStatus) or status.capability.provider_id != "openvsp":
            raise ProviderRefusal("OpenVSPProvider needs the registry status of the 'openvsp' provider")
        self.status = status

    def build(self, request: VSPModelRequest, out_dir: str | None = None) -> VSPGeometryResult:
        if not self.status.available:
            raise ProviderRefusal(f"OpenVSP is unavailable: {self.status.reason}; no geometry is synthesized")
        from engcore.providers import require_library_unchanged

        require_library_unchanged(self.status, "openvsp")
        import openvsp as vsp  # pragma: no cover - requires OpenVSP

        ops = operations(request)  # pragma: no cover
        out = out_dir or tempfile.mkdtemp(prefix="forge-vsp-")  # pragma: no cover
        ids: dict[str, str] = {}  # pragma: no cover
        for op in ops:  # pragma: no cover
            kind = op[0]
            if kind == "VSPRenew":
                vsp.VSPRenew()
            elif kind == "SetSTEPLengthUnit":
                vsp.SetParmVal(vsp.FindContainer("Vehicle", 0), "LenUnit", "STEPSettings", vsp.LEN_M)
            elif kind == "AddGeom":
                ids[op[1]] = vsp.AddGeom(op[2])
                vsp.SetGeomName(ids[op[1]], op[1])
            elif kind == "SetParmVal":
                vsp.SetParmVal(ids[op[1]], op[2], op[3], float(op[4]))
            elif kind == "Update":
                vsp.Update()
            elif kind == "ExportFile":
                vsp.ExportFile(os.path.join(out, op[1]), vsp.SET_ALL, vsp.EXPORT_STEP)
        return self._result(request, os.path.join(out, "model.stp"))  # pragma: no cover

    def _result(self, request: VSPModelRequest, step_path: str) -> VSPGeometryResult:
        """Bind an exported STEP file: digest, unit from its header (refused when absent), receipt."""
        from engcore.spatial.gmsh_adapter import step_length_unit

        if not os.path.isfile(step_path):
            raise ProviderRefusal("OpenVSP produced no STEP file; nothing is admitted")
        with open(step_path, "rb") as fh:
            data = fh.read()
        unit = step_length_unit(data)
        if unit is None:
            raise ProviderRefusal("the exported STEP states no single length unit; units are never guessed")
        digest = hashlib.sha256(data).hexdigest()
        source = ImportedSource(digest, "step", unit, 3, {"producer": "openvsp", "translation_status": TRANSLATION_STATUS})
        receipt = GeometryReceipt("openvsp", self.status.version, "parametric_aero_build",
                                  {"translation": translation_digest(request)}, {"step": digest},
                                  {"adapter_version": ADAPTER_VERSION, "translation_status": TRANSLATION_STATUS, "model_id": request.model_id},
                                  provider_digest=self.status.digest)
        return VSPGeometryResult(source, receipt, step_path, {c.name: type(c).__name__ for c in request.components})


__all__ = ["ADAPTER_ID", "ADAPTER_VERSION", "BodyOfRevolution", "LiftingSurface", "OpenVSPProvider", "Position", "TRANSLATION_STATUS",
           "VSPGeometryResult", "VSPModelRequest", "operations", "translation_digest"]
